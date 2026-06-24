import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.db.models import Q

from recommendations.models import Place
from recommendations.services.ai_candidate_reranker import semantic_rerank_candidates
from recommendations.services.ai_intent_planner import (
    build_ai_intent_plan,
    repair_search_queries,
    to_search_plan,
)
from recommendations.services.ai_web_search_provider import (
    get_ai_web_search_result,
    get_ai_web_search_status,
)
from recommendations.services.kakao_local import search_places_by_keyword
from recommendations.services.place_urls import get_kakao_place_url
from recommendations.services.smoking_area_data import calculate_distance_m


logger = logging.getLogger(__name__)


VERIFIED_TAG_SOURCES = {"checked", "user_verified"}
SUGGESTED_TAG_SOURCES = {"ai_suggested", "blog_search"}
COORDINATE_PAIR_RE = re.compile(
    r"[-+]?\d{1,3}(?:\.\d+)?\s*[,，]\s*[-+]?\d{1,3}(?:\.\d+)?"
)


def _clean_text(value, max_length=240):
    text = str(value or "").strip()
    if max_length and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _compact(value):
    return _clean_text(value, 500).lower().replace(" ", "")


def _as_list(value, max_items=20):
    if value in (None, ""):
        return []
    if isinstance(value, (str, int, float, bool)):
        value = [value]
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("value") or item.get("text") or item.get("label")
        text = _clean_text(item)
        key = _compact(text)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coordinate_pair(value):
    text = _clean_text(value, 120)
    if not text:
        return None
    parts = [
        part.strip()
        for part in text.replace("，", ",").replace(";", ",").split(",")
        if part.strip()
    ]
    if len(parts) != 2:
        return None
    first = _as_float(parts[0])
    second = _as_float(parts[1])
    if first is None or second is None:
        return None
    if -90 <= first <= 90 and -180 <= second <= 180:
        return first, second
    if -90 <= second <= 90 and -180 <= first <= 180:
        return second, first
    return None


def _strip_coordinate_literals(value):
    text = _clean_text(value, 160)
    if not text:
        return ""
    text = COORDINATE_PAIR_RE.sub(" ", text)
    text = re.sub(
        r"^\s*(?:현재\s*위치|현위치|내\s*위치|current\s+location)\s*(?:근처|인근|주변)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(?:near|around|within)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\s*m\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:근처|인근|주변)\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.-")
    return text


def _normalize_search_queries(queries):
    normalized = []
    seen = set()
    for query in _as_list(queries, max_items=10):
        cleaned = _strip_coordinate_literals(query)
        key = _compact(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _context_coordinates(lat=None, lng=None, map_center=None):
    parsed_lat = _as_float(lat)
    parsed_lng = _as_float(lng)
    if parsed_lat is not None and parsed_lng is not None:
        return parsed_lat, parsed_lng
    if isinstance(map_center, dict):
        parsed_lat = _as_float(map_center.get("lat"))
        parsed_lng = _as_float(map_center.get("lng"))
        if parsed_lat is not None and parsed_lng is not None:
            return parsed_lat, parsed_lng
    return None, None


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _limit(value, default=15):
    return min(max(_as_int(value, default), 1), 50)


def _radius(value):
    parsed = _as_int(value, 8000)
    return min(max(parsed, 300), 20000)


def _resolve_anchor_location(anchor_location, *, lat=None, lng=None):
    anchor_location = _clean_text(anchor_location, 100)
    if not anchor_location:
        return {
            "status": "skipped",
            "reason": "missing_anchor_location",
            "lat": None,
            "lng": None,
            "label": "",
        }

    coordinates = _coordinate_pair(anchor_location)
    if coordinates:
        resolved_lat, resolved_lng = coordinates
        return {
            "status": "resolved",
            "reason": "",
            "lat": resolved_lat,
            "lng": resolved_lng,
            "label": anchor_location,
            "source": "coordinate_anchor",
            "external_id": "",
            "address": "",
        }

    anchor_key = _compact(anchor_location)

    search_attempts = [{"lat": None, "lng": None, "source": "kakao_keyword"}]
    if lat not in (None, "") and lng not in (None, ""):
        search_attempts.append({"lat": lat, "lng": lng, "source": "kakao_keyword_nearby"})

    last_error_reason = ""
    for attempt in search_attempts:
        try:
            response = search_places_by_keyword(
                keyword=anchor_location,
                lat=attempt["lat"],
                lng=attempt["lng"],
                radius=20000,
                size=5,
            )
        except Exception as exc:
            logger.info("Anchor location resolution failed. anchor=%s", anchor_location, exc_info=True)
            last_error_reason = f"anchor_resolution_failed:{exc.__class__.__name__}"
            continue

        documents = response.get("documents") if isinstance(response, dict) else []
        documents = documents if isinstance(documents, list) else []
        for item in documents:
            if not isinstance(item, dict):
                continue
            searchable_text = _compact(
                " ".join([
                    _clean_text(item.get("place_name")),
                    _clean_text(item.get("address_name")),
                    _clean_text(item.get("road_address_name")),
                    _clean_text(item.get("category_name")),
                ])
            )
            if anchor_key and anchor_key not in searchable_text:
                continue
            resolved_lat = _as_float(item.get("y"))
            resolved_lng = _as_float(item.get("x"))
            if resolved_lat is None or resolved_lng is None:
                continue
            label = _clean_text(item.get("place_name") or item.get("address_name") or anchor_location)
            return {
                "status": "resolved",
                "reason": "",
                "lat": resolved_lat,
                "lng": resolved_lng,
                "label": label,
                "source": attempt["source"],
                "external_id": _clean_text(item.get("id")),
                "address": _clean_text(item.get("road_address_name") or item.get("address_name")),
            }

    return {
        "status": "failed",
        "reason": last_error_reason or "anchor_location_not_found",
        "lat": None,
        "lng": None,
        "label": anchor_location,
    }


def _broad_terms():
    return {
        "place",
        "places",
        "somewhere",
        "recommendation",
        "spot",
        "place to go",
        "things to do",
        "\uc7a5\uc18c",
        "\ucd94\ucc9c\uc7a5\uc18c",
        "\uac08\ub9cc\ud55c\uacf3",
        "\uac08\ub9cc\ud55c\ub370",
        "\uac00\ubcfc\ub9cc\ud55c\uacf3",
        "\uc5b4\ub514",
        "\uc5b4\ub518\uac00",
        "\uacf3",
        "\uacf5\uac04",
        "장소",
        "추천장소",
        "어디",
        "어딘가",
        "갈만한곳",
        "갈만한데",
        "곳",
        "공간",
    }


def _is_broad_term(value):
    compact = _compact(value)
    if not compact:
        return False
    broad = {_compact(item) for item in _broad_terms()}
    if compact in broad:
        return True
    return any(item and len(item) >= 4 and item in compact for item in broad)


def _frame_terms(frame, *names):
    values = []
    for name in names:
        values.extend(_as_list(frame.get(name)))
    return values


def _evidence_terms(frame):
    return {
        "target": _frame_terms(frame, "target_objects"),
        "result": _frame_terms(frame, "result_match_terms"),
        "candidate": _frame_terms(frame, "candidate_place_types"),
        "constraints": _frame_terms(frame, "constraints"),
        "exclusions": _frame_terms(frame, "exclusions"),
    }


def _generic_evidence_modifiers():
    return {
        "near",
        "nearby",
        "around",
        "recommend",
        "recommendation",
        "best",
        "find",
        "search",
        "place",
        "places",
        "\ub9db\uc9d1",
        "\ucd94\ucc9c",
        "\ucd94\ucc9c\ud574\uc918",
        "\ucc3e\uc544\uc918",
        "\ucc3e\uc544",
        "\uac80\uc0c9",
        "\uadfc\ucc98",
        "\uc8fc\ubcc0",
        "\uac00\uae4c\uc6b4",
        "\uac00\uae4c\uc774",
        "\uba40\uc9c0",
        "\uc54a\uc740",
        "\ubc14\ub85c",
        "\uc9c0\uae08",
        "\ud604\uc7ac",
        "\uc704\uce58",
        "\uae30\uc900",
        "\uae09\ud55c",
        "\uae09\ud574",
        "\uae09\ud558\uac8c",
        "\uac00\uace0",
        "\uac00\uace0\uc2f6\uc5b4",
        "\uac00\uace0\uc2f6",
        "\uba39\uace0",
        "\uba39\uace0\uc2f6\uc5b4",
        "\uba39\uace0\uc2f6",
        "\uc2f6\uc5b4",
        "\uc2f6\uc740",
        "\uc88b\uc740",
        "\uc88b\uc744",
        "\uac08",
        "\uc218",
        "\uc788\ub294",
        "\uc788\uc5b4",
        "\uc788\ub0d0",
        "\uc788\uc744",
        "\uc5c6\ub294",
        "\ud53c\uc6b8",
        "\ud544",
        "\ud544\uc694\ud574",
        "\ud544\uc694\ud55c",
        "\uc880",
        "\ub108\ubb34",
        "\ub370",
        "\ub370\ub85c",
        "\ub300\ub85c",
        "\uac83",
        "\uacf3",
        "\uc7a5\uc18c",
        "\uc5b4\ub514",
        "\uc5b4\ub518\uac00",
        "\uc5d0\uc11c",
    }


def _trim_evidence_suffixes(value):
    text = _clean_text(value, 80).strip(" ,.-_")
    for suffix in (
        "\uc5d0\uc11c",
        "\uc73c\ub85c",
        "\uae4c\uc9c0",
        "\ubd80\ud130",
    ):
        if len(text) > len(suffix) + 1 and text.endswith(suffix):
            text = text[: -len(suffix)].strip(" ,.-_")
    for suffix in (
        "\uc744",
        "\ub97c",
        "\uc740",
        "\ub294",
        "\uc774",
        "\uac00",
        "\uc758",
        "\uc5d0",
        "\ub85c",
    ):
        if len(text) >= 4 and text.endswith(suffix):
            text = text[: -len(suffix)].strip(" ,.-_")
    return text


def _split_specific_evidence_terms(value, frame=None):
    text = _clean_text(value, 160)
    if not text:
        return []

    anchors = _as_list((frame or {}).get("anchor_location"), max_items=3)
    for anchor in anchors:
        if anchor:
            text = re.sub(re.escape(anchor), " ", text, flags=re.IGNORECASE)

    for marker in sorted(_generic_evidence_modifiers(), key=len, reverse=True):
        if marker:
            if len(_compact(marker)) <= 1:
                continue
            text = re.sub(re.escape(marker), " ", text, flags=re.IGNORECASE)

    parts = [
        _trim_evidence_suffixes(part)
        for part in re.split(r"[\s,;/|]+", text)
        if _clean_text(part)
    ]
    if not parts and _clean_text(text):
        parts = [_trim_evidence_suffixes(text)]

    terms = []
    seen = set()
    for part in parts:
        key = _compact(part)
        if not key or key in seen:
            continue
        if _is_broad_term(part):
            continue
        if key in {_compact(item) for item in _generic_evidence_modifiers()}:
            continue
        if len(part) > 30:
            continue
        seen.add(key)
        terms.append(part)
    return terms


def _specific_evidence_terms(values, frame=None, max_items=12):
    result = []
    seen = set()
    for value in values or []:
        for term in _split_specific_evidence_terms(value, frame=frame):
            key = _compact(term)
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(term)
            if len(result) >= max_items:
                return result
    return result


def _db_evidence_terms(frame):
    terms = _evidence_terms(frame)
    target_terms = _specific_evidence_terms([*terms["target"], *terms["result"]], frame=frame)
    candidate_terms = _specific_evidence_terms(terms["candidate"], frame=frame)
    constraint_terms = _specific_evidence_terms(terms["constraints"], frame=frame)
    search_terms = target_terms or candidate_terms or constraint_terms
    return {
        "target": target_terms,
        "candidate": candidate_terms,
        "constraints": constraint_terms,
        "search": search_terms,
    }


def _has_actionable_place_target(frame):
    terms = _evidence_terms(frame)
    target_terms = [term for term in [*terms["target"], *terms["result"]] if not _is_broad_term(term)]
    queries = _as_list(frame.get("primary_search_queries"))
    if not target_terms or not queries:
        return False
    return True


def _is_under_specified_place_request(raw_query, frame):
    compact_query = _compact(raw_query)
    if not compact_query:
        return False
    broad_markers = {
        _compact(item)
        for item in {
            "somewhere",
            "place to go",
            "things to do",
            "\uc5b4\ub514",
            "\uc5b4\ub518\uac00",
            "\uac08\ub9cc\ud55c",
            "\uac00\ubcfc\ub9cc\ud55c",
            "\ub4e4\ub97c\ub9cc\ud55c",
            "\ubb50\ud558\uc9c0",
        }
    }
    if not any(marker and marker in compact_query for marker in broad_markers):
        return False
    terms = _evidence_terms(frame)
    if terms["constraints"] or terms["exclusions"]:
        return False
    specific_terms = [
        term
        for term in [*terms["target"], *terms["result"]]
        if term and not _is_broad_term(term)
    ]
    if any(_compact(term) and _compact(term) in compact_query for term in specific_terms):
        return False
    return True


def _contains_any(text, terms):
    compact_text = _compact(text)
    if not compact_text:
        return False
    return any(_compact(term) and _compact(term) in compact_text for term in terms)


def _matched_terms(text, terms):
    compact_text = _compact(text)
    matched = []
    for term in terms:
        compact_term = _compact(term)
        if compact_term and compact_term in compact_text:
            matched.append(term)
    return matched


def _distance(lat, lng, place_lat, place_lng):
    lat = _as_float(lat)
    lng = _as_float(lng)
    place_lat = _as_float(place_lat)
    place_lng = _as_float(place_lng)
    if lat is None or lng is None or place_lat is None or place_lng is None:
        return None
    return calculate_distance_m(lat, lng, place_lat, place_lng)


def _source_label(source):
    if source == "db":
        return "DB 후보"
    if source == "kakao":
        return "카카오 검색 근거 후보, 세부 정보 확인 필요"
    if source == "web":
        return "웹 검색 근거 후보, 세부 정보 확인 필요"
    return source


def _confidence_label(level, source):
    if source in {"kakao", "web"}:
        return _source_label(source)
    if level == "strong":
        return "추천 근거 높음"
    if level == "medium":
        return "추천 후보, 확인 필요"
    return "관련 근거 부족 후보"


def _tag_strength(place_tag):
    if getattr(place_tag, "is_verified", False):
        return "verified"
    if place_tag.source in VERIFIED_TAG_SOURCES and place_tag.status == "confirmed":
        return "verified"
    if place_tag.source in SUGGESTED_TAG_SOURCES or place_tag.status != "confirmed":
        return "suggested"
    return "candidate"


def _db_tag_lists(place):
    verified = []
    suggested = []
    candidate = []
    warnings = []
    for place_tag in getattr(place, "place_tags", []).all():
        tag_name = _clean_text(getattr(place_tag.tag, "name", ""))
        if not tag_name:
            continue
        if place_tag.source == "warning_tags":
            warnings.append(tag_name)
            continue
        strength = _tag_strength(place_tag)
        if strength == "verified":
            verified.append(tag_name)
        elif strength == "suggested":
            suggested.append(tag_name)
        else:
            candidate.append(tag_name)
    return {
        "verified": list(dict.fromkeys(verified)),
        "suggested": list(dict.fromkeys(suggested)),
        "candidate": list(dict.fromkeys(candidate)),
        "warning": list(dict.fromkeys(warnings)),
    }


def _db_evidence(place, tag_lists, frame):
    terms = _db_evidence_terms(frame)
    target_terms = terms["target"]
    candidate_terms = terms["candidate"]
    text_fields = {
        "name": _clean_text(place.name),
        "category": _clean_text(place.category),
        "address": _clean_text(place.address),
        "detail_location": _clean_text(place.detail_location),
        "source_name": _clean_text(place.source_name),
        "raw": _clean_text(json.dumps(place.raw or {}, ensure_ascii=False), 500),
    }
    matched = []
    level = "weak"

    for field_name, text in text_fields.items():
        for term in _matched_terms(text, target_terms):
            matched.append({
                "type": "target_direct",
                "field": field_name,
                "value": term,
                "source_strength": "verified",
            })
            level = "strong"

    for term in _matched_terms(" ".join(tag_lists["verified"]), target_terms):
        matched.append({
            "type": "verified_tag_direct",
            "field": "verified_tags",
            "value": term,
            "source_strength": "verified",
        })
        level = "strong"

    for term in _matched_terms(" ".join(tag_lists["suggested"]), target_terms):
        matched.append({
            "type": "suggested_tag_direct",
            "field": "suggested_tags",
            "value": term,
            "source_strength": "suggested",
        })
        if level != "strong":
            level = "medium"

    for term in _matched_terms(" ".join(tag_lists["candidate"]), target_terms):
        matched.append({
            "type": "candidate_tag_direct",
            "field": "candidate_tags",
            "value": term,
            "source_strength": "candidate",
        })
        if level == "weak":
            level = "medium"

    if level == "weak":
        category_text = " ".join([place.category, *tag_lists["verified"], *tag_lists["suggested"], *tag_lists["candidate"]])
        for term in _matched_terms(category_text, candidate_terms):
            matched.append({
                "type": "category_or_type_match",
                "field": "category_or_tags",
                "value": term,
                "source_strength": "category_only",
            })
        if matched:
            level = "weak"

    return level, matched


def _candidate_base(candidate_id, source, name, category, address, lat=None, lng=None, distance=None):
    return {
        "id": candidate_id,
        "candidate_source": source,
        "unified_candidate_source": source,
        "source": source,
        "source_type": f"{source}_candidate",
        "source_label": _source_label(source),
        "name": name,
        "category": category,
        "address": address,
        "detail_location": address,
        "lat": lat,
        "lng": lng,
        "distance": distance,
        "distance_m": distance,
        "can_show_on_map": lat is not None and lng is not None,
        "is_external": source in {"kakao", "web"},
    }


def collect_db_candidates(frame, *, lat=None, lng=None, limit=50, radius=None):
    terms = _db_evidence_terms(frame)
    search_terms = terms["search"]
    if not search_terms:
        return []

    query = Q()
    for term in search_terms[:8]:
        query |= (
            Q(name__icontains=term)
            | Q(category__icontains=term)
            | Q(address__icontains=term)
            | Q(detail_location__icontains=term)
            | Q(source_name__icontains=term)
            | Q(place_tags__tag__name__icontains=term)
            | Q(place_tags__evidence__icontains=term)
        )

    queryset = (
        Place.objects
        .filter(query)
        .distinct()
        .prefetch_related("place_tags__tag")
        .order_by("-data_quality_score", "-updated_at")
    )
    radius = _radius(radius)
    candidates = []
    for place in queryset[: max(limit * 5, 100)]:
        distance = _distance(lat, lng, place.lat, place.lng)
        if distance is not None and distance > radius:
            continue
        tag_lists = _db_tag_lists(place)
        level, matched = _db_evidence(place, tag_lists, frame)
        candidate = {
            **_candidate_base(
                f"db:{place.id}",
                "db",
                place.name,
                place.category,
                place.address or place.detail_location,
                lat=place.lat,
                lng=place.lng,
                distance=distance,
            ),
            "place_id": place.id,
            "external_id": place.external_id,
            "source_name": place.source_name,
            "kakao_place_url": get_kakao_place_url(place),
            "place_url": get_kakao_place_url(place),
            "verified_tags": tag_lists["verified"],
            "verified_tag_labels": tag_lists["verified"],
            "suggested_tags": tag_lists["suggested"],
            "suggested_tag_labels": tag_lists["suggested"],
            "candidate_tags": tag_lists["candidate"],
            "candidate_tag_labels": tag_lists["candidate"],
            "warning_tags": tag_lists["warning"],
            "matched_evidence": matched,
            "matched_tags": [item["value"] for item in matched],
            "matched_tag_labels": [item["value"] for item in matched],
            "pre_ai_evidence_level": level,
            "evidence_level": level,
            "frame_match_strength": level,
            "recommendation_confidence": "high" if level == "strong" else "medium" if level == "medium" else "low",
            "confidence": "high" if level == "strong" else "medium" if level == "medium" else "low",
            "confidence_label": _confidence_label(level, "db"),
            "recommendation_reason": _confidence_label(level, "db"),
            "recommend_reason": _confidence_label(level, "db"),
            "score": {"strong": 80, "medium": 55, "weak": 25}.get(level, 25),
            "score_breakdown": {
                "collector": "db",
                "pre_ai_evidence_level": level,
                "personalization_boost": 0,
            },
        }
        candidates.append(candidate)
        if len(candidates) >= limit:
            break
    return candidates


def _candidate_text(candidate):
    return " ".join(
        _clean_text(candidate.get(key))
        for key in ("name", "category", "address", "detail_location", "evidence_text")
        if _clean_text(candidate.get(key))
    )


def _external_pre_ai_evidence(candidate, frame):
    db_terms = _db_evidence_terms(frame)
    target_terms = db_terms["target"]
    candidate_terms = db_terms["candidate"]
    text = _candidate_text(candidate)
    retrieval_query = _clean_text(candidate.get("retrieval_query"))
    matched = []
    for term in _matched_terms(text, target_terms):
        matched.append({"type": "target_direct", "value": term, "source_strength": "external"})
    if matched:
        return "strong", matched
    for term in _matched_terms(text, candidate_terms):
        matched.append({"type": "candidate_type", "value": term, "source_strength": "external"})
    if matched:
        return "medium", matched
    for term in _matched_terms(retrieval_query, target_terms):
        matched.append({"type": "retrieval_query_target", "value": term, "source_strength": "external_query"})
    if matched:
        return "medium", matched
    return "weak", []


def collect_kakao_candidates(frame, queries, *, lat=None, lng=None, radius=None):
    max_queries = _as_int(getattr(settings, "AI_SEARCH_KAKAO_MAX_QUERIES", 2), 2)
    max_queries = min(max(max_queries, 1), 5)
    size = _as_int(getattr(settings, "AI_SEARCH_KAKAO_QUERY_SIZE", 10), 10)
    size = min(max(size, 1), 15)
    radius = _radius(radius or getattr(settings, "AI_SEARCH_KAKAO_RADIUS", 5000))
    candidates = []
    query_counts = []
    selected_queries = list(queries[:max_queries])

    def fetch_query(query):
        try:
            response = search_places_by_keyword(
                keyword=query,
                lat=lat,
                lng=lng,
                radius=radius,
                size=size,
            )
        except Exception as exc:
            logger.info("Kakao candidate collection failed. query=%s", query, exc_info=True)
            return query, [], {"query": query, "count": 0, "error": exc.__class__.__name__}
        documents = response.get("documents") if isinstance(response, dict) else []
        documents = documents if isinstance(documents, list) else []
        return query, documents, {"query": query, "count": len(documents)}

    fetched = []
    if len(selected_queries) <= 1:
        fetched = [fetch_query(query) for query in selected_queries]
    else:
        with ThreadPoolExecutor(max_workers=min(len(selected_queries), 3)) as executor:
            future_map = {executor.submit(fetch_query, query): query for query in selected_queries}
            for future in as_completed(future_map):
                fetched.append(future.result())
        order = {query: index for index, query in enumerate(selected_queries)}
        fetched.sort(key=lambda item: order.get(item[0], 999))

    for query, documents, count_row in fetched:
        query_counts.append(count_row)
        for place in documents:
            if not isinstance(place, dict):
                continue
            place_id = _clean_text(place.get("id"))
            name = _clean_text(place.get("place_name"))
            if not name:
                continue
            distance = _as_int(place.get("distance"), 0) if _clean_text(place.get("distance")) else None
            candidate = {
                **_candidate_base(
                    f"kakao:{place_id or name}:{_compact(query)}",
                    "kakao",
                    name,
                    _clean_text(place.get("category_name")),
                    _clean_text(place.get("road_address_name") or place.get("address_name")),
                    lat=_as_float(place.get("y")),
                    lng=_as_float(place.get("x")),
                    distance=distance,
                ),
                "external_id": place_id,
                "retrieval_query": query,
                "external_url": _clean_text(place.get("place_url")) or (f"https://place.map.kakao.com/{place_id}" if place_id else ""),
                "kakao_place_url": _clean_text(place.get("place_url")) or (f"https://place.map.kakao.com/{place_id}" if place_id else ""),
                "place_url": _clean_text(place.get("place_url")) or (f"https://place.map.kakao.com/{place_id}" if place_id else ""),
                "kakao_category": _clean_text(place.get("category_name")),
            }
            level, matched = _external_pre_ai_evidence(candidate, frame)
            candidate.update({
                "pre_ai_evidence_level": level,
                "evidence_level": level,
                "matched_evidence": matched,
                "matched_tags": [item["value"] for item in matched],
                "matched_tag_labels": [item["value"] for item in matched],
                "confidence": "medium" if level in {"strong", "medium"} else "low",
                "recommendation_confidence": "medium" if level in {"strong", "medium"} else "low",
                "confidence_label": _confidence_label(level, "kakao"),
                "recommendation_reason": _confidence_label(level, "kakao"),
                "recommend_reason": _confidence_label(level, "kakao"),
                "score": {"strong": 72, "medium": 50, "weak": 20}.get(level, 20),
                "score_breakdown": {
                    "collector": "kakao",
                    "retrieval_query": query,
                    "pre_ai_evidence_level": level,
                },
            })
            candidates.append(candidate)
    return candidates, query_counts


def collect_web_candidates(frame, queries, *, lat=None, lng=None, existing_counts=None):
    if not getattr(settings, "AI_WEB_SEARCH_AUTO_MERGE_ENABLED", False):
        return []
    if not getattr(settings, "AI_WEB_SEARCH_AVAILABLE", False):
        return []
    candidates = []
    max_queries = _as_int(getattr(settings, "AI_SEARCH_WEB_MAX_QUERIES", 1), 1)
    max_queries = min(max(max_queries, 1), 3)
    for query in queries[:max_queries]:
        try:
            response = get_ai_web_search_result(
                query=query,
                lat=lat,
                lng=lng,
                location_hint=_clean_text(frame.get("anchor_location")),
                search_plan={
                    "place_intent_frame": frame,
                    "targetQuery": (frame.get("target_objects") or [""])[0],
                    "search_queries": queries,
                    "plan_source": "ai",
                },
                condition={},
                existing_results_summary=existing_counts or {},
                manual=True,
            )
        except Exception:
            logger.info("Web candidate collection failed. query=%s", query, exc_info=True)
            continue
        for index, item in enumerate(response.get("candidates") or []):
            if not isinstance(item, dict):
                continue
            name = _clean_text(item.get("name") or item.get("title"))
            if not name:
                continue
            candidate = {
                **_candidate_base(
                    f"web:{_compact(item.get('source_url') or name)}:{index}",
                    "web",
                    name,
                    _clean_text(item.get("category")),
                    _clean_text(item.get("address_hint")),
                    lat=None,
                    lng=None,
                    distance=None,
                ),
                "retrieval_query": query,
                "external_url": _clean_text(item.get("source_url")),
                "place_url": _clean_text(item.get("source_url")),
                "evidence_text": _clean_text(item.get("summary") or item.get("evidence_text"), 500),
                "web_snippet": _clean_text(item.get("summary") or item.get("evidence_text"), 500),
            }
            level, matched = _external_pre_ai_evidence(candidate, frame)
            candidate.update({
                "pre_ai_evidence_level": level,
                "evidence_level": level,
                "matched_evidence": matched,
                "confidence": "medium" if level in {"strong", "medium"} else "low",
                "recommendation_confidence": "medium" if level in {"strong", "medium"} else "low",
                "confidence_label": _confidence_label(level, "web"),
                "recommendation_reason": _confidence_label(level, "web"),
                "recommend_reason": _confidence_label(level, "web"),
                "score": {"strong": 68, "medium": 45, "weak": 20}.get(level, 20),
                "score_breakdown": {
                    "collector": "web",
                    "retrieval_query": query,
                    "pre_ai_evidence_level": level,
                },
            })
            candidates.append(candidate)
    return candidates


def _dedupe_candidates(candidates):
    seen = set()
    deduped = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        external_id = _clean_text(candidate.get("external_id"))
        name = _compact(candidate.get("name"))
        address = _compact(candidate.get("address") or candidate.get("detail_location"))
        key = ("external_id", external_id) if external_id else ("name_address", name, address)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _strong_medium_count(candidates):
    return sum(
        1
        for candidate in candidates or []
        if candidate.get("pre_ai_evidence_level") in {"strong", "medium"}
    )


def _needs_candidate_recall_boost(candidates, *, limit=15):
    candidates = candidates or []
    desired_total = min(max(_as_int(limit, 15), 8), 15)
    desired_strong_medium = min(max(desired_total // 2, 4), 8)
    return (
        len(candidates) < desired_total
        or _strong_medium_count(candidates) < desired_strong_medium
    )


def _query_needs_repair(queries):
    for query in queries or []:
        text = _clean_text(query, 160)
        if not text:
            return True
        if COORDINATE_PAIR_RE.search(text):
            return True
        if len(text) > 36:
            return True
        if re.search(r"[,/;|]", text):
            return True
    return False


def _explicit_external_verification_requested(query, frame):
    text = _compact(" ".join([
        query,
        *frame.get("constraints", []),
        *frame.get("result_match_terms", []),
    ]))
    markers = {
        "web",
        "external",
        "official",
        "verify",
        "latest",
        "웹",
        "외부",
        "공식",
        "확인",
        "최신",
    }
    return any(_compact(marker) in text for marker in markers)


def _candidate_sort_key(candidate):
    return (
        {"strong": 0, "medium": 1, "weak": 2}.get(candidate.get("pre_ai_evidence_level"), 9),
        candidate.get("distance") if candidate.get("distance") is not None else 999999999,
        str(candidate.get("id")),
    )


def _balanced_rerank_shortlist(candidates, limit):
    limit = max(_as_int(limit, 20), 1)
    valid = [
        candidate
        for candidate in candidates or []
        if isinstance(candidate, dict) and _clean_text(candidate.get("id"))
    ]
    if len(valid) <= limit:
        return sorted(valid, key=_candidate_sort_key)

    buckets = {}
    for candidate in sorted(valid, key=_candidate_sort_key):
        source = _clean_text(candidate.get("candidate_source") or candidate.get("source") or "unknown")
        retrieval_query = _clean_text(candidate.get("retrieval_query") or "no_query")
        buckets.setdefault(source, {}).setdefault(retrieval_query, []).append(candidate)

    source_order = sorted(
        buckets,
        key=lambda source: min(_candidate_sort_key(item) for query_items in buckets[source].values() for item in query_items),
    )
    query_order = {
        source: sorted(
            query_map,
            key=lambda query: min(_candidate_sort_key(item) for item in query_map[query]),
        )
        for source, query_map in buckets.items()
    }

    selected = []
    selected_ids = set()
    while len(selected) < limit:
        progressed = False
        for source in source_order:
            for query in query_order[source]:
                queue = buckets[source][query]
                while queue and _clean_text(queue[0].get("id")) in selected_ids:
                    queue.pop(0)
                if not queue:
                    continue
                candidate = queue.pop(0)
                selected.append(candidate)
                selected_ids.add(_clean_text(candidate.get("id")))
                progressed = True
                break
            if len(selected) >= limit:
                break
        if not progressed:
            break

    if len(selected) < limit:
        for candidate in sorted(valid, key=_candidate_sort_key):
            candidate_id = _clean_text(candidate.get("id"))
            if candidate_id in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(candidate_id)
            if len(selected) >= limit:
                break
    return selected


def _minimum_result_count(limit):
    configured = _as_int(getattr(settings, "AI_SEARCH_MIN_RESULTS", 10), 10)
    return min(max(configured, 1), max(_as_int(limit, 15), 1), 20)


def _top_up_ranked_candidates(ranked_candidates, candidate_pool, excluded_candidates, *, limit=15):
    desired_count = _minimum_result_count(limit)
    ranked_candidates = list(ranked_candidates or [])
    if len(ranked_candidates) >= desired_count:
        return ranked_candidates, []

    ranked_ids = {_clean_text(candidate.get("id")) for candidate in ranked_candidates}
    excluded_ids = {
        _clean_text(candidate.get("id"))
        for candidate in excluded_candidates or []
        if _clean_text(candidate.get("id"))
    }
    additions = []
    for candidate in sorted(candidate_pool or [], key=_candidate_sort_key):
        candidate_id = _clean_text(candidate.get("id"))
        if not candidate_id or candidate_id in ranked_ids or candidate_id in excluded_ids:
            continue
        level = _clean_text(candidate.get("pre_ai_evidence_level") or candidate.get("evidence_level"))
        if level not in {"strong", "medium"}:
            continue
        matched_evidence = candidate.get("matched_evidence") if isinstance(candidate.get("matched_evidence"), list) else []
        if matched_evidence and all(item.get("type") == "retrieval_query_target" for item in matched_evidence if isinstance(item, dict)):
            continue
        evidence_level = "medium" if level == "strong" else level
        reason = (
            "Collected candidate has compatible evidence, but details need verification."
        )
        additions.append({
            **candidate,
            "semantic_score": max(float(candidate.get("score") or 0), 45.0),
            "evidence_level": evidence_level,
            "frame_evidence_tier": evidence_level,
            "semantic_reason": reason,
            "verification_required": True,
            "recommendation_reason": reason,
            "recommend_reason": reason,
            "compatibility_gate": "needs_verification",
            "compatibility_gate_reason": "top_up_needs_verification",
            "unified_ranker_applied": True,
            "semantic_reranker": {
                "decision": "needs_verification",
                "semantic_score": max(float(candidate.get("score") or 0), 45.0),
                "evidence_level": evidence_level,
                "matched_fields": ["pre_ai_evidence"],
                "unmet_constraints": ["details_need_verification"],
                "reason": reason,
            },
        })
        ranked_ids.add(candidate_id)
        if len(ranked_candidates) + len(additions) >= desired_count:
            break

    merged = [*ranked_candidates, *additions]
    merged = [
        {
            **candidate,
            "backend_rank": index + 1,
            "unified_rank": index + 1,
        }
        for index, candidate in enumerate(merged)
    ]
    return merged, additions


def _has_only_retrieval_query_evidence(candidate):
    matched_evidence = candidate.get("matched_evidence") if isinstance(candidate.get("matched_evidence"), list) else []
    if not matched_evidence:
        return False
    evidence_types = [
        item.get("type")
        for item in matched_evidence
        if isinstance(item, dict) and item.get("type")
    ]
    return bool(evidence_types) and all(item == "retrieval_query_target" for item in evidence_types)


def _markers(results):
    markers = []
    for result in results or []:
        if result.get("lat") is None or result.get("lng") is None:
            continue
        markers.append({
            "id": result.get("id"),
            "name": result.get("name"),
            "lat": result.get("lat"),
            "lng": result.get("lng"),
            "source": result.get("candidate_source"),
            "rank": result.get("backend_rank"),
        })
    return markers


def _debug_pipeline(
    *,
    intent_plan,
    search_plan,
    frame,
    query_generation=None,
    candidate_counts=None,
    reranker_debug=None,
    top_results=None,
    hidden_weak=None,
    location_resolution=None,
    fallback_used=False,
    fallback_created_candidates=False,
    timings=None,
    ai_call_count=0,
):
    candidate_counts = candidate_counts or {}
    top_results = top_results or []
    hidden_weak = hidden_weak or []
    return {
        "used_path": "ai_first_orchestrator",
        "legacy_path_used": False,
        "ai_call_failed": intent_plan.get("decision_action") == "ai_unavailable",
        "ai_retry_count": intent_plan.get("ai_retry_count", 0),
        "fallback_used": bool(fallback_used),
        "fallback_created_candidates": bool(fallback_created_candidates),
        "has_actionable_place_target": _has_actionable_place_target(frame),
        "evidence_terms": {
            "trusted": [
                *frame.get("target_objects", []),
                *frame.get("result_match_terms", []),
                *frame.get("candidate_place_types", []),
            ],
            "db_search_terms": _db_evidence_terms(frame)["search"],
            "fallback_placeholder": [],
            "legacy_inferred": [],
            "raw_query_repeat": [],
            "broad_default": [],
        },
        "query_generation": query_generation or {
            "primary_queries": [],
            "fallback_queries": [],
            "blocked_queries": [],
        },
        "location_resolution": location_resolution or {
            "status": "skipped",
            "reason": "",
        },
        "candidate_counts": {
            "db": _as_int(candidate_counts.get("db"), 0),
            "kakao": _as_int(candidate_counts.get("kakao"), 0),
            "web": _as_int(candidate_counts.get("web"), 0),
            "top_results": _as_int(candidate_counts.get("top_results"), len(top_results)),
            "hidden_weak": _as_int(candidate_counts.get("hidden_weak"), len(hidden_weak)),
            "removed_incompatible": _as_int(candidate_counts.get("removed_incompatible"), len(hidden_weak)),
            "unresolved": _as_int(candidate_counts.get("unresolved"), 0),
        },
        "reranker": reranker_debug or {},
        "ai_included_count": _as_int((reranker_debug or {}).get("ai_included_count"), 0),
        "ai_needs_verification_count": _as_int(
            (reranker_debug or {}).get("ai_needs_verification_count"),
            0,
        ),
        "ai_excluded_count": _as_int((reranker_debug or {}).get("ai_excluded_count"), 0),
        "unresolved_count": _as_int((reranker_debug or {}).get("unresolved_count"), 0),
        "unresolved_candidate_ids": (reranker_debug or {}).get("unresolved_candidate_ids") or [],
        "reranker_partial": bool((reranker_debug or {}).get("reranker_partial")),
        "reranker_call_count": _as_int(
            (reranker_debug or {}).get("reranker_call_count")
            or (reranker_debug or {}).get("call_count"),
            0,
        ),
        "top_result_evidence": [
            {
                "id": result.get("id"),
                "name": result.get("name"),
                "source": result.get("candidate_source"),
                "semantic_score": result.get("semantic_score"),
                "evidence_level": result.get("evidence_level"),
                "reason": result.get("semantic_reason"),
            }
            for result in top_results[:15]
        ],
        "search_plan": {
            "plan_source": search_plan.get("plan_source"),
            "execution_mode": search_plan.get("execution_mode"),
        },
        "planner_latency_ms": (timings or {}).get("planner_latency_ms"),
        "retrieval_latency_ms": (timings or {}).get("retrieval_latency_ms"),
        "query_repair_latency_ms": (timings or {}).get("query_repair_latency_ms"),
        "web_latency_ms": (timings or {}).get("web_latency_ms"),
        "reranker_latency_ms": (timings or {}).get("reranker_latency_ms"),
        "total_latency_ms": (timings or {}).get("total_latency_ms"),
        "ai_call_count": ai_call_count,
    }


def _empty_response(action, *, intent_plan, search_plan, frame, message="", timings=None, ai_call_count=0):
    clarification = intent_plan.get("clarification") if isinstance(intent_plan.get("clarification"), dict) else {}
    debug_pipeline = _debug_pipeline(
        intent_plan=intent_plan,
        search_plan=search_plan,
        frame=frame,
        candidate_counts={"db": 0, "kakao": 0, "web": 0, "top_results": 0},
        timings=timings,
        ai_call_count=ai_call_count,
    )
    return {
        "scenario": action,
        "type": "clarification" if action == "ask_clarification" else action,
        "decision_action": action,
        "decisionAction": action,
        "blocked": action == "blocked",
        "can_search_now": False,
        "results": [],
        "markers": [],
        "count": 0,
        "result_count": 0,
        "relevant_result_count": 0,
        "unified_candidate_pipeline": True,
        "frontend_should_preserve_order": True,
        "frontend_should_skip_kakao_fallback": True,
        "execution_policy": {
            "run_search": False,
            "allow_kakao_fallback": False,
            "allow_ai_web_search_auto": False,
            "merge_ai_web_results": False,
        },
        "clarification_question": clarification.get("question", ""),
        "clarification_options": clarification.get("options", []),
        "message": message or clarification.get("question", ""),
        "search_plan": search_plan,
        "place_intent_frame": search_plan.get("place_intent_frame") or frame,
        "ai_parse": {
            "scenario": action,
            "is_searchable": False,
            "decision_action": action,
            "can_search_now": False,
            "parser_provider": "ai_intent_planner",
            "parser_fallback": False,
            "execution_mode": "ai_first_orchestrator",
            "plan_source": "ai",
            "search_plan": search_plan,
            "place_intent_frame": search_plan.get("place_intent_frame") or frame,
            "ai_fallback_reason": intent_plan.get("ai_fallback_reason", ""),
        },
        "execution_mode": "ai_first_orchestrator",
        "plan_source": "ai",
        "debug_pipeline": debug_pipeline,
        "ai_debug": intent_plan.get("ai_debug") or {},
        "ai_web_search": get_ai_web_search_status(),
    }


def _previous_context_from_request(data):
    previous_context = (
        data.get("previous_search_context")
        or data.get("previous_context")
        or data.get("previousContext")
        or {}
    )
    previous_context = previous_context if isinstance(previous_context, dict) else {}
    previous_search_plan = data.get("previous_search_plan")
    pending_frame = data.get("pending_clarification_frame")
    if isinstance(previous_search_plan, dict) or isinstance(pending_frame, dict):
        previous_context = {
            **previous_context,
            "search_plan": previous_search_plan or previous_context.get("search_plan") or {},
            "pending_clarification_frame": pending_frame or previous_context.get("pending_clarification_frame") or {},
            "is_clarification_followup": bool(data.get("is_clarification_followup")),
            "clarification_answer": data.get("clarification_answer", ""),
            "previous_user_query": data.get("previous_user_query", ""),
            "original_query": data.get("original_query") or data.get("originalQuery") or "",
            "pending_clarification_question": data.get("pending_clarification_question")
            or previous_context.get("pending_clarification_question")
            or previous_context.get("clarification_question")
            or "",
            "last_resolved_location_context": data.get("last_resolved_location_context") or {},
        }
    return previous_context


def run_ai_search(request_data, *, user=None):
    total_started = time.perf_counter()
    timings = {
        "planner_latency_ms": None,
        "retrieval_latency_ms": None,
        "query_repair_latency_ms": None,
        "web_latency_ms": None,
        "reranker_latency_ms": None,
        "total_latency_ms": None,
    }
    ai_call_count = 0

    def finish_timings():
        timings["total_latency_ms"] = round((time.perf_counter() - total_started) * 1000, 2)
        return timings

    query = _clean_text(request_data.get("query"), 500)
    original_query = _clean_text(request_data.get("originalQuery") or request_data.get("original_query") or query, 500)
    lat = request_data.get("lat")
    lng = request_data.get("lng")
    radius = request_data.get("radius")
    limit = _limit(request_data.get("limit"), default=15)
    map_center = request_data.get("map_center") or request_data.get("mapCenter")
    previous_context = _previous_context_from_request(request_data)

    planner_started = time.perf_counter()
    intent_plan = build_ai_intent_plan(
        query,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )
    timings["planner_latency_ms"] = round((time.perf_counter() - planner_started) * 1000, 2)
    ai_call_count += _as_int(
        ((intent_plan.get("ai_debug") or {}).get("planner") or {}).get("call_count"),
        0,
    )
    action = intent_plan.get("decision_action") or intent_plan.get("action")
    search_plan = to_search_plan(intent_plan, raw_query=original_query or query)
    frame = intent_plan.get("frame") if isinstance(intent_plan.get("frame"), dict) else {}

    if action in {"ai_unavailable", "ask_clarification", "out_of_scope", "blocked"}:
        message = ""
        if action == "out_of_scope":
            message = "이 서비스는 상황에 맞는 생활 장소 추천을 도와드리는 기능입니다. 장소 추천 의도가 있는 상황을 입력해 주세요."
        elif action == "blocked":
            message = "해당 요청은 안전하게 안내하기 어렵습니다."
        elif action == "ai_unavailable":
            message = "AI 해석을 완료하지 못해 검색을 실행하지 않았습니다. 잠시 뒤 다시 시도해 주세요."
        return _empty_response(
            action,
            intent_plan=intent_plan,
            search_plan=search_plan,
            frame=frame,
            message=message,
            timings=finish_timings(),
            ai_call_count=ai_call_count,
        )

    if action != "search" or not _has_actionable_place_target(frame):
        clarification = intent_plan.get("clarification") if isinstance(intent_plan.get("clarification"), dict) else {}
        if not clarification.get("question"):
            intent_plan = {
                **intent_plan,
                "action": "ask_clarification",
                "decision_action": "ask_clarification",
                "clarification": {
                    "question": "현재 문장만으로는 찾을 장소의 목적이 충분히 분명하지 않습니다. 어떤 장소를 찾고 싶은지 조금 더 구체적으로 알려주세요.",
                    "options": [],
                    "missing_fields": ["target_objects"],
                    "expected_patch_fields": ["target_objects", "primary_search_queries"],
                },
            }
            search_plan = to_search_plan(intent_plan, raw_query=original_query or query)
        return _empty_response(
            "ask_clarification",
            intent_plan=intent_plan,
            search_plan=search_plan,
            frame=frame,
            timings=finish_timings(),
            ai_call_count=ai_call_count,
        )

    if _is_under_specified_place_request(original_query or query, frame):
        intent_plan = {
            **intent_plan,
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "can_search_now": False,
            "clarification": {
                "question": "\uc5b4\ub5a4 \ubaa9\uc801\uc758 \uc7a5\uc18c\ub97c \ucc3e\uc73c\uc2dc\ub098\uc694? \uba39\uc744 \uacf3, \uc26c\uc5b4\uac08 \uacf3, \uc791\uc5c5\ud560 \uacf3\ucc98\ub7fc \uc6d0\ud558\ub294 \ubc29\ud5a5\uc744 \uc54c\ub824\uc8fc\uc138\uc694.",
                "options": [
                    {"label": "\uba39\uc744 \uacf3", "value": "\uba39\uc744 \uacf3"},
                    {"label": "\uc26c\uc5b4\uac08 \uacf3", "value": "\uc26c\uc5b4\uac08 \uacf3"},
                    {"label": "\uc791\uc5c5\ud560 \uacf3", "value": "\uc791\uc5c5\ud560 \uacf3"},
                ],
                "missing_fields": ["target_objects"],
                "expected_patch_fields": ["target_objects", "primary_search_queries"],
            },
        }
        search_plan = to_search_plan(intent_plan, raw_query=original_query or query)
        data = _empty_response(
            "ask_clarification",
            intent_plan=intent_plan,
            search_plan=search_plan,
            frame=frame,
            timings=finish_timings(),
            ai_call_count=ai_call_count,
        )
        data["debug_pipeline"]["post_gate_reason"] = "under_specified_place_request"
        data["debug_pipeline"]["query_generation"] = {
            "primary_queries": frame.get("primary_search_queries") or [],
            "fallback_queries": [],
            "blocked_queries": frame.get("primary_search_queries") or [],
        }
        return data

    context_lat, context_lng = _context_coordinates(lat=lat, lng=lng, map_center=map_center)
    if frame.get("location_mode") == "current_context" and (context_lat is None or context_lng is None):
        intent_plan = {
            **intent_plan,
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "can_search_now": False,
            "clarification": {
                "question": "현재 위치 기준으로 찾으려면 기준 위치가 필요합니다. 어느 동네, 역, 건물 근처에서 찾을까요?",
                "options": [],
                "missing_fields": ["anchor_location"],
                "expected_patch_fields": ["anchor_location"],
            },
        }
        search_plan = to_search_plan(intent_plan, raw_query=original_query or query)
        data = _empty_response(
            "ask_clarification",
            intent_plan=intent_plan,
            search_plan=search_plan,
            frame=frame,
            timings=finish_timings(),
            ai_call_count=ai_call_count,
        )
        data["debug_pipeline"]["location_resolution"] = {
            "status": "failed",
            "reason": "missing_current_context_coordinates",
        }
        return data

    search_lat = context_lat
    search_lng = context_lng
    location_resolution = {"status": "skipped", "reason": "current_context"}
    if frame.get("location_mode") == "explicit":
        location_resolution = _resolve_anchor_location(
            frame.get("anchor_location"),
            lat=context_lat,
            lng=context_lng,
        )
        if location_resolution.get("status") != "resolved":
            intent_plan = {
                **intent_plan,
                "action": "ask_clarification",
                "decision_action": "ask_clarification",
                "can_search_now": False,
                "clarification": {
                    "question": "말씀하신 기준 위치를 지도에서 확인하지 못했습니다. 기준이 될 역, 동네, 건물명을 한 번 더 정확히 알려주세요.",
                    "options": [],
                    "missing_fields": ["anchor_location"],
                    "expected_patch_fields": ["anchor_location"],
                },
            }
            search_plan = to_search_plan(intent_plan, raw_query=original_query or query)
            data = _empty_response(
                "ask_clarification",
                intent_plan=intent_plan,
                search_plan=search_plan,
                frame=frame,
                timings=finish_timings(),
                ai_call_count=ai_call_count,
            )
            data["debug_pipeline"]["location_resolution"] = location_resolution
            return data
        search_lat = location_resolution.get("lat")
        search_lng = location_resolution.get("lng")
        search_plan["resolved_anchor_location"] = location_resolution
        search_plan["resolvedAnchorLocation"] = location_resolution

    primary_queries = _normalize_search_queries(frame.get("primary_search_queries"))
    primary_limit = _as_int(getattr(settings, "AI_SEARCH_PRIMARY_QUERY_LIMIT", 2), 2)
    primary_limit = min(max(primary_limit, 1), 5)
    primary_queries = primary_queries[:primary_limit]
    query_generation = {
        "primary_queries": primary_queries,
        "fallback_queries": [],
        "blocked_queries": [],
    }

    retrieval_started = time.perf_counter()
    if getattr(settings, "IS_TESTING", False):
        db_candidates = collect_db_candidates(
            frame,
            lat=search_lat,
            lng=search_lng,
            limit=max(limit * 3, 30),
            radius=radius,
        )
        kakao_candidates, query_counts = collect_kakao_candidates(
            frame,
            primary_queries,
            lat=search_lat,
            lng=search_lng,
            radius=radius,
        )
    else:
        with ThreadPoolExecutor(max_workers=2) as executor:
            db_future = executor.submit(
                collect_db_candidates,
                frame,
                lat=search_lat,
                lng=search_lng,
                limit=max(limit * 3, 30),
                radius=radius,
            )
            kakao_future = executor.submit(
                collect_kakao_candidates,
                frame,
                primary_queries,
                lat=search_lat,
                lng=search_lng,
                radius=radius,
            )
            db_candidates = db_future.result()
            kakao_candidates, query_counts = kakao_future.result()
    timings["retrieval_latency_ms"] = round((time.perf_counter() - retrieval_started) * 1000, 2)

    initial_candidates = _dedupe_candidates([*db_candidates, *kakao_candidates])
    candidate_counts = {
        "db": len(db_candidates),
        "kakao": len(kakao_candidates),
        "web": 0,
    }

    query_repair_debug = {"status": "skipped"}
    should_repair_queries = (
        not initial_candidates
        or _query_needs_repair(primary_queries)
    )
    if should_repair_queries:
        query_repair_started = time.perf_counter()
        repaired_queries, query_repair_debug = repair_search_queries(
            original_query or query,
            frame,
            candidate_counts=candidate_counts,
        )
        timings["query_repair_latency_ms"] = round((time.perf_counter() - query_repair_started) * 1000, 2)
        ai_call_count += _as_int(query_repair_debug.get("call_count"), 0)
        repaired_queries = [
            item
            for item in _normalize_search_queries(repaired_queries)
            if item not in primary_queries
        ]
        if repaired_queries:
            repaired_kakao, repaired_counts = collect_kakao_candidates(
                frame,
                repaired_queries,
                lat=search_lat,
                lng=search_lng,
                radius=radius,
            )
            query_generation["fallback_queries"] = repaired_queries
            query_counts.extend(repaired_counts)
            kakao_candidates.extend(repaired_kakao)
            candidate_counts["kakao"] = len(kakao_candidates)
            initial_candidates = _dedupe_candidates([*db_candidates, *kakao_candidates])

    web_candidates = []
    external_verification_requested = _explicit_external_verification_requested(original_query or query, frame)
    can_use_web_for_location = bool(frame.get("anchor_location")) or frame.get("location_mode") == "explicit"
    should_collect_web = (
        external_verification_requested
        or (can_use_web_for_location and _needs_candidate_recall_boost(initial_candidates, limit=limit))
    )
    if should_collect_web:
        web_started = time.perf_counter()
        web_candidates = collect_web_candidates(
            frame,
            [*primary_queries, *query_generation["fallback_queries"]],
            lat=search_lat,
            lng=search_lng,
            existing_counts={
                "db_count": len(db_candidates),
                "kakao_count": len(kakao_candidates),
                "total_count": len(initial_candidates),
            },
        )
        timings["web_latency_ms"] = round((time.perf_counter() - web_started) * 1000, 2)
        candidate_counts["web"] = len(web_candidates)

    candidate_pool = _dedupe_candidates([*db_candidates, *kakao_candidates, *web_candidates])
    retrieval_only_candidates = [
        candidate
        for candidate in candidate_pool
        if _has_only_retrieval_query_evidence(candidate)
    ]
    all_candidates = [
        candidate
        for candidate in candidate_pool
        if not _has_only_retrieval_query_evidence(candidate)
    ]
    pre_rerank_limit = _as_int(getattr(settings, "AI_SEARCH_RERANK_MAX_CANDIDATES", 20), 20)
    pre_rerank_limit = min(max(pre_rerank_limit, 5), 30)
    all_candidates = _balanced_rerank_shortlist(all_candidates, pre_rerank_limit)

    ranking_policy = frame.get("ranking_policy") or "evidence_first"
    if all_candidates:
        reranker_started = time.perf_counter()
        ranked_candidates, reranker_debug = semantic_rerank_candidates(
            frame,
            all_candidates,
            ranking_policy=ranking_policy,
            max_candidates=pre_rerank_limit,
        )
        timings["reranker_latency_ms"] = round((time.perf_counter() - reranker_started) * 1000, 2)
        ai_call_count += _as_int(reranker_debug.get("call_count"), 0)
    else:
        ranked_candidates = []
        reranker_debug = {
            "status": "skipped",
            "reason": "no_candidates_collected",
            "input_count": 0,
            "included_count": 0,
            "excluded_count": 0,
            "excluded_candidates": [],
        }

    if reranker_debug.get("status") not in {"executed", "partial_executed", "degraded_success", "skipped"}:
        intent_plan = {
            **intent_plan,
            "action": "ai_unavailable",
            "decision_action": "ai_unavailable",
            "ai_fallback_reason": reranker_debug.get("reason") or "ai_reranker_unavailable",
        }
        data = _empty_response(
            "ai_unavailable",
            intent_plan=intent_plan,
            search_plan=search_plan,
            frame=frame,
            message="AI 후보 평가를 완료하지 못해 검색 결과를 표시하지 않았습니다. 잠시 뒤 다시 시도해 주세요.",
        )
        data["debug_pipeline"]["candidate_counts"].update({
            **candidate_counts,
            "top_results": 0,
            "hidden_weak": 0,
            "removed_incompatible": 0,
            "unresolved": len(all_candidates),
        })
        data["debug_pipeline"]["query_generation"] = query_generation
        data["debug_pipeline"]["location_resolution"] = location_resolution
        data["debug_pipeline"]["reranker"] = reranker_debug
        data["debug_pipeline"].update({
            "ai_included_count": _as_int(reranker_debug.get("ai_included_count"), 0),
            "ai_needs_verification_count": _as_int(
                reranker_debug.get("ai_needs_verification_count"),
                0,
            ),
            "ai_excluded_count": _as_int(reranker_debug.get("ai_excluded_count"), 0),
            "unresolved_count": _as_int(
                reranker_debug.get("unresolved_count"),
                len(all_candidates),
            ),
            "unresolved_candidate_ids": reranker_debug.get("unresolved_candidate_ids") or [],
            "reranker_partial": bool(reranker_debug.get("reranker_partial")),
            "reranker_call_count": _as_int(
                reranker_debug.get("reranker_call_count") or reranker_debug.get("call_count"),
                0,
            ),
            **finish_timings(),
            "ai_call_count": ai_call_count,
        })
        return data

    hidden_weak = reranker_debug.get("excluded_candidates") or []
    unresolved_candidates = reranker_debug.get("unresolved_candidates") or []
    ranked_candidates, top_up_candidates = _top_up_ranked_candidates(
        ranked_candidates,
        candidate_pool,
        hidden_weak,
        limit=limit,
    )
    if top_up_candidates:
        reranker_debug = {
            **reranker_debug,
            "top_up_count": len(top_up_candidates),
            "top_up_candidate_ids": [candidate.get("id") for candidate in top_up_candidates],
        }
    results = ranked_candidates[:limit]
    candidate_counts.update({
        "top_results": len(results),
        "hidden_weak": len(hidden_weak),
        "removed_incompatible": len(hidden_weak),
        "unresolved": len(unresolved_candidates),
    })

    debug_pipeline = _debug_pipeline(
        intent_plan=intent_plan,
        search_plan=search_plan,
        frame=frame,
        query_generation=query_generation,
        candidate_counts=candidate_counts,
        reranker_debug={
            **reranker_debug,
            "query_repair": query_repair_debug,
            "kakao_query_result_counts": query_counts,
            "retrieval_only_filtered_count": len(retrieval_only_candidates),
        },
        top_results=results,
        hidden_weak=hidden_weak,
        location_resolution=location_resolution,
        fallback_used=query_repair_debug.get("status") == "executed",
        fallback_created_candidates=False,
        timings=finish_timings(),
        ai_call_count=ai_call_count,
    )

    parsed = {
        "scenario": "ai_place_search",
        "situation_summary": intent_plan.get("normalized_query") or original_query or query,
        "is_searchable": True,
        "parser_provider": "ai_intent_planner",
        "parser_fallback": False,
        "plan_source": "ai",
        "execution_mode": "ai_first_orchestrator",
        "search_plan": search_plan,
        "place_intent_frame": search_plan.get("place_intent_frame") or frame,
    }

    return {
        "scenario": "ai_place_search",
        "type": "search",
        "decision_action": "search",
        "decisionAction": "search",
        "blocked": False,
        "can_search_now": True,
        "candidate_pipeline": "ai_first_unified_evidence",
        "unified_candidate_pipeline": True,
        "frontend_should_preserve_order": True,
        "frontend_should_skip_kakao_fallback": True,
        "execution_policy": {
            "run_search": True,
            "allow_kakao_fallback": False,
            "allow_ai_web_search_auto": False,
            "merge_ai_web_results": False,
        },
        "collector_names": ["db", "kakao", "web"],
        "candidate_source_counts": {
            "db": len(db_candidates),
            "kakao": len(kakao_candidates),
            "web": len(web_candidates),
        },
        "external_search_triggered": bool(kakao_candidates or web_candidates),
        "external_query_count": len(primary_queries),
        "external_queries": primary_queries,
        "query_generation": query_generation,
        "external_query_result_counts": query_counts,
        "external_candidates": [candidate for candidate in [*kakao_candidates, *web_candidates]],
        "hidden_weak_candidates": hidden_weak,
        "hidden_weak_count": len(hidden_weak),
        "compatibility_removed_count": len(hidden_weak),
        "results": results,
        "markers": _markers(results),
        "count": len(results),
        "result_count": len(results),
        "relevant_result_count": len(results),
        "search_plan": search_plan,
        "place_intent_frame": search_plan.get("place_intent_frame") or frame,
        "ai_parse": parsed,
        "ai_web_search": get_ai_web_search_status(),
        "execution_mode": "ai_first_orchestrator",
        "plan_source": "ai",
        "debug_pipeline": debug_pipeline,
        "ai_debug": {
            **(intent_plan.get("ai_debug") or {}),
            "reranker": reranker_debug,
            "query_repair": query_repair_debug,
        },
    }
