import json
import logging
import math
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
from recommendations.services.map_search import get_matching_categories
from recommendations.services.place_urls import get_kakao_place_url
from recommendations.services.smoking_area_data import calculate_distance_m
from recommendations.services.tag_utils import get_category_display_name


logger = logging.getLogger(__name__)


VERIFIED_TAG_SOURCES = {"checked", "user_verified"}
SUGGESTED_TAG_SOURCES = {"ai_suggested", "blog_search"}
# 카테고리와 거리만으로 답이 정해지는 생활 유틸리티 카테고리입니다.
# 카페/공원/관광지/해수욕장은 `조용한`, `야경 좋은` 같은 주관적 조건이 붙으므로 넣지 않습니다.
DETERMINISTIC_CATEGORY_CODES = {
    "toilet",
    "parking",
    "freewifi",
    "shelter",
    "smoking_area",
}
# 후보를 걸러내지 않는 조건입니다. 거리/긴급도는 이미 정렬 정책에 반영되어 있어
# 후보마다 따로 판단할 내용이 없습니다. 이 목록 밖의 조건이 하나라도 있으면 AI가 판단합니다.
NON_DISCRIMINATING_CONSTRAINTS = frozenset({
    "긴급",
    "급함",
    "급해",
    "가까운",
    "가까운곳",
    "가장가까운",
    "제일가까운",
    "근처",
    "주변",
    "인근",
    "즉시",
    "지금",
    "빠르게",
    "빨리",
    "도보",
    "도보거리",
    "가까움",
})
DB_FIRST_CATEGORY_CODES = {"smoking_area"}
DB_CATEGORY_SEARCH_CODES = {
    "cafe",
    "restaurant",
    "shelter",
    "city_park",
    "beach",
    "tourism",
    "toilet",
    "freewifi",
    "parking",
    "pharmacy",
    "smoking_area",
    "shopping",
    "karaoke",
}
STRUCTURED_PLACE_TYPE_TERMS = {
    "카페",
    "커피",
    "식당",
    "음식점",
    "맛집",
    "약국",
    "화장실",
    "공중화장실",
    "개방화장실",
    "흡연구역",
    "흡연실",
    "노래방",
    "코인노래방",
    "쇼핑몰",
    "백화점",
    "아울렛",
    "쇼핑센터",
    "대형마트",
    "도서관",
    "공공도서관",
    "코워킹스페이스",
    "주차장",
    "공원",
    "산책로",
    "박물관",
    "미술관",
    "갤러리",
}
POLICY_AWARE_CATEGORY_CODES = {"smoking_area"}
PLACE_POLICY_TERMS = {
    "outdoor": {
        "label": "실외/외부 이용",
        "terms": {
            "실외",
            "실외흡연구역",
            "외부",
            "밖",
            "바깥",
            "야외",
            "옥외",
            "개방형",
            "개방형흡연구역",
            "부스형",
            "부스형흡연구역",
            "흡연부스",
            "도로변",
        },
    },
    "indoor": {
        "label": "실내 이용",
        "terms": {
            "실내",
            "실내흡연실",
            "내부",
            "실내형",
            "건물내",
            "건물 내",
            "음식점 내부",
            "매장 내부",
        },
    },
}
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


def _is_current_context_anchor(value):
    key = _compact(value).replace("_", "").replace("-", "")
    return key in {
        "currentcoordinates",
        "currentcoordinate",
        "currentcontext",
        "currentlocation",
        "현재좌표",
        "현재위치",
        "현위치",
        "내위치",
    }


def _normalize_current_context_anchor_frame(frame):
    if not isinstance(frame, dict):
        return {}
    location_mode = _clean_text(frame.get("location_mode") or frame.get("locationMode")).lower()
    anchor_location = _clean_text(frame.get("anchor_location") or frame.get("anchorLocation"))
    if location_mode != "explicit" or not _is_current_context_anchor(anchor_location):
        return frame
    normalized = {
        **frame,
        "location_mode": "current_context",
        "locationMode": "current_context",
        "anchor_location": "",
        "anchorLocation": "",
    }
    return normalized


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


def _context_coordinate_source(lat=None, lng=None, map_center=None):
    if _as_float(lat) is not None and _as_float(lng) is not None:
        return "request_coordinates"
    if isinstance(map_center, dict):
        if _as_float(map_center.get("lat")) is not None and _as_float(map_center.get("lng")) is not None:
            return "map_center"
    return ""


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


REGION_PREFIXES = (
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
)


LOCATION_ANCHOR_CATEGORY_HINTS = (
    "지하철",
    "전철",
    "철도",
    "도시철도",
    "역",
    "터미널",
    "공항",
    "관광",
    "명소",
    "관광안내",
    "해수욕장",
    "공원",
    "시장",
    "광장",
)


def _has_region_prefix(value):
    key = _compact(value)
    return any(_compact(prefix) and _compact(prefix) in key for prefix in REGION_PREFIXES)


def _address_only_anchor_is_too_weak(anchor_location, *, name_key, address_key, category_key, anchor_key, anchor_tokens, alias_key, alias_match, transit_match):
    if transit_match:
        return False
    if anchor_key and anchor_key in name_key:
        return False
    if alias_match and alias_key and alias_key in name_key:
        return False
    if any(_compact(term) and _compact(term) in category_key for term in LOCATION_ANCHOR_CATEGORY_HINTS):
        return False
    if not ((anchor_key and anchor_key in address_key) or (anchor_tokens and all(token in address_key for token in anchor_tokens))):
        return False
    if _has_region_prefix(anchor_location) or len(anchor_tokens) >= 2:
        return False
    return True


def _anchor_location_aliases(anchor_location):
    text = _clean_text(anchor_location, 100)
    compact_text = _compact(text)
    aliases = []
    seen = set()

    def add_alias(value, area_tokens=None):
        value = _clean_text(value, 100)
        key = _compact(value)
        if not key or key in seen:
            return
        seen.add(key)
        aliases.append({
            "text": value,
            "key": key,
            "area_tokens": [_compact(token) for token in (area_tokens or []) if _compact(token)],
        })

    add_alias(text)
    tokens = [token for token in re.split(r"[\s,;/|]+", text) if _clean_text(token)]
    if len(tokens) >= 2 and _compact(tokens[-1]).endswith("역"):
        area_tokens = tokens[:-1]
        if len(_compact(tokens[-1])) >= 3:
            add_alias(tokens[-1], area_tokens=area_tokens)

    for prefix in REGION_PREFIXES:
        prefix_key = _compact(prefix)
        if not compact_text.startswith(prefix_key):
            continue
        remainder = compact_text[len(prefix_key):]
        if len(remainder) >= 3 and remainder.endswith("역"):
            add_alias(remainder, area_tokens=[prefix])
            break

    return aliases


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
    anchor_tokens = [
        _compact(token)
        for token in re.split(r"[\s,;/|]+", anchor_location)
        if len(_compact(token)) >= 2
    ]

    anchor_aliases = _anchor_location_aliases(anchor_location)
    search_attempts = []
    seen_attempts = set()
    for alias in anchor_aliases:
        for attempt in (
            {"lat": None, "lng": None, "source": "kakao_keyword", "keyword": alias["text"], "alias": alias},
            {"lat": lat, "lng": lng, "source": "kakao_keyword_nearby", "keyword": alias["text"], "alias": alias},
        ):
            if attempt["source"] == "kakao_keyword_nearby" and (lat in (None, "") or lng in (None, "")):
                continue
            key = (attempt["source"], _compact(attempt["keyword"]), attempt["lat"], attempt["lng"])
            if key in seen_attempts:
                continue
            seen_attempts.add(key)
            search_attempts.append(attempt)

    last_error_reason = ""
    resolved_candidates = []
    for attempt in search_attempts:
        try:
            response = search_places_by_keyword(
                keyword=attempt["keyword"],
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
            place_name = _clean_text(item.get("place_name"))
            address = _clean_text(item.get("road_address_name") or item.get("address_name"))
            category_name = _clean_text(item.get("category_name"))
            searchable_values = [place_name, address, category_name]
            searchable_text = _compact(" ".join(searchable_values))
            token_match = bool(anchor_tokens) and all(token in searchable_text for token in anchor_tokens)
            alias = attempt["alias"]
            alias_key = alias.get("key")
            alias_area_tokens = alias.get("area_tokens") or []
            alias_area_match = not alias_area_tokens or all(token in searchable_text for token in alias_area_tokens)
            alias_match = (
                bool(alias_key)
                and alias_key != anchor_key
                and alias_area_match
                and (alias_key in _compact(place_name) or alias_key in _compact(address))
            )
            if (
                anchor_key
                and not any(anchor_key in _compact(value) for value in searchable_values)
                and anchor_key not in searchable_text
                and not token_match
                and not alias_match
            ):
                continue
            resolved_lat = _as_float(item.get("y"))
            resolved_lng = _as_float(item.get("x"))
            if resolved_lat is None or resolved_lng is None:
                continue
            name_key = _compact(place_name)
            address_key = _compact(address)
            category_key = _compact(category_name)
            transit_match = alias_key and alias_key.endswith("역") and (
                "지하철" in category_name
                or "전철" in category_name
                or "철도" in category_name
                or "도시철도" in category_name
                or name_key == alias_key
                or name_key.startswith(f"{alias_key} ")
            )
            if _address_only_anchor_is_too_weak(
                anchor_location,
                name_key=name_key,
                address_key=address_key,
                category_key=category_key,
                anchor_key=anchor_key,
                anchor_tokens=anchor_tokens,
                alias_key=alias_key,
                alias_match=alias_match,
                transit_match=transit_match,
            ):
                last_error_reason = "ambiguous_address_only_anchor"
                continue
            score = 0
            if name_key == anchor_key:
                score += 100
            elif name_key.startswith(anchor_key):
                score += 80
            elif anchor_key and anchor_key in name_key:
                score += 60
            if address_key == anchor_key:
                score += 50
            elif anchor_key and anchor_key in address_key:
                score += 30
            if alias_match:
                if name_key == alias_key:
                    score += 95
                elif name_key.startswith(alias_key):
                    score += 70
                elif alias_key in name_key:
                    score += 45
                elif alias_key in address_key:
                    score += 25
            if transit_match:
                score += 60
            if category_key and "부동산" in category_key and not transit_match:
                score -= 25
            if token_match:
                score += 20 * len(anchor_tokens)
                if all(token in address_key for token in anchor_tokens):
                    score += 15
            score -= max(len(name_key) - len(anchor_key), 0) / 100
            label = _clean_text(place_name or item.get("address_name") or anchor_location)
            source = attempt["source"]
            if alias_match and alias_key != anchor_key:
                source = f"{source}_alias"
            if token_match and anchor_key not in name_key and anchor_key not in address_key:
                source = f"{source}_address_tokens"
            resolved_candidates.append({
                "score": score,
                "name_length": len(name_key),
                "status": "resolved",
                "reason": "",
                "lat": resolved_lat,
                "lng": resolved_lng,
                "label": label,
                "source": source,
                "external_id": _clean_text(item.get("id")),
                "address": address,
            })

    if resolved_candidates:
        resolved_candidates.sort(key=lambda item: (-item["score"], item["name_length"]))
        selected = dict(resolved_candidates[0])
        selected.pop("score", None)
        selected.pop("name_length", None)
        return selected

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


def _frame_category_codes(frame):
    return _frame_terms(frame, "candidate_category_codes")


def _db_first_category_codes(frame):
    return [
        code
        for code in _frame_category_codes(frame)
        if code in DB_FIRST_CATEGORY_CODES
    ]


def _direct_db_category_codes(frame):
    direct_text = _compact(" ".join([
        *_frame_terms(frame, "target_objects", "targetObjects"),
        *_frame_terms(frame, "result_match_terms", "resultMatchTerms"),
    ]))
    if not direct_text:
        return []

    direct_codes = []
    for code in _frame_category_codes(frame):
        if code not in DB_CATEGORY_SEARCH_CODES:
            continue
        code_text = _compact(code)
        label_text = _compact(get_category_display_name(code))
        if (code_text and code_text in direct_text) or (label_text and label_text in direct_text):
            direct_codes.append(code)

    return list(dict.fromkeys(direct_codes))


def _evidence_terms(frame):
    return {
        "target": _frame_terms(frame, "target_objects"),
        "result": _frame_terms(frame, "result_match_terms"),
        "candidate": _frame_terms(frame, "candidate_place_types"),
        "constraints": _frame_terms(frame, "constraints"),
        "exclusions": _frame_terms(frame, "exclusions"),
    }


def _search_radius_for_frame(request_radius, frame, raw_query):
    if request_radius not in (None, ""):
        return _radius(request_radius)

    text = _compact(" ".join([
        raw_query or "",
        *_frame_terms(frame, "constraints"),
        *_frame_terms(frame, "result_match_terms"),
        *_frame_terms(frame, "target_objects"),
    ]))
    urgent_markers = ["긴급", "급한", "급해", "바로", "즉시"]
    walking_markers = ["도보", "걸어서", "걸어", "멀지", "너무멀"]
    nearby_markers = ["근처", "가까운", "가까이", "인근", "주변"]
    toilet_markers = ["화장실", "공중화장실", "개방화장실", "대변", "소변", "마려"]
    is_toilet_search = any(_compact(marker) in text for marker in toilet_markers)

    if any(_compact(marker) in text for marker in urgent_markers):
        return 1500
    if any(_compact(marker) in text for marker in walking_markers):
        return 2000
    if any(_compact(marker) in text for marker in nearby_markers):
        return 1500 if is_toilet_search else 3000
    return None


def _policy_enabled(frame):
    if any(
        code in POLICY_AWARE_CATEGORY_CODES
        for code in _frame_category_codes(frame)
    ):
        return True
    policy_text = _compact(" ".join([
        *_frame_terms(frame, "target_objects", "targetObjects"),
        *_frame_terms(frame, "result_match_terms", "resultMatchTerms"),
        *_frame_terms(frame, "candidate_place_types", "candidatePlaceTypes"),
        *_frame_terms(frame, "constraints"),
        *_frame_terms(frame, "exclusions", "excluded_place_natures", "avoid"),
    ]))
    return bool("흡연" in policy_text or "담배" in policy_text)


def _contains_policy_term(text, policy_name):
    compact_text = _compact(text)
    if not compact_text:
        return False
    terms = PLACE_POLICY_TERMS.get(policy_name, {}).get("terms") or set()
    return any(
        _compact(term) and _compact(term) in compact_text
        for term in terms
    )


def _frame_policy_requirements(frame):
    if not _policy_enabled(frame):
        return {
            "desired": [],
            "excluded": [],
        }

    terms = _evidence_terms(frame)
    positive_text = " ".join([
        *terms["target"],
        *terms["result"],
        *terms["constraints"],
    ])
    exclusion_text = " ".join(terms["exclusions"])
    desired = []
    excluded = []

    for policy_name in PLACE_POLICY_TERMS:
        if _contains_policy_term(positive_text, policy_name):
            desired.append(policy_name)
        if _contains_policy_term(exclusion_text, policy_name):
            excluded.append(policy_name)

    if "indoor" in excluded and "outdoor" not in desired:
        desired.append("outdoor")
    if "outdoor" in excluded and "indoor" not in desired:
        desired.append("indoor")

    desired = list(dict.fromkeys(desired))
    excluded = list(dict.fromkeys(excluded))

    return {
        "desired": desired,
        "excluded": excluded,
    }


def _policy_label(policy_name):
    return PLACE_POLICY_TERMS.get(policy_name, {}).get("label") or policy_name


def _policy_review(text, frame, *, field="policy", source_strength="candidate"):
    requirements = _frame_policy_requirements(frame)
    desired = requirements.get("desired") or []
    excluded = requirements.get("excluded") or []
    if not desired and not excluded:
        return [], [], []

    present = {
        policy_name: _contains_policy_term(text, policy_name)
        for policy_name in PLACE_POLICY_TERMS
    }
    matched = []
    unmet = []
    verification_needed = []

    for policy_name in desired:
        if present.get(policy_name):
            matched.append({
                "type": "policy_constraint",
                "field": field,
                "value": _policy_label(policy_name),
                "source_strength": source_strength,
            })
        else:
            conflicting = [
                excluded_policy
                for excluded_policy in excluded
                if present.get(excluded_policy)
            ]
            if conflicting:
                unmet.append(f"{_policy_label(policy_name)} 요청과 다른 {_policy_label(conflicting[0])} 정보")
            else:
                verification_needed.append(f"{_policy_label(policy_name)} 여부 확인 필요")

    for policy_name in excluded:
        if present.get(policy_name) and not any(
            present.get(desired_policy)
            for desired_policy in desired
        ):
            unmet.append(f"제외 조건과 맞지 않는 {_policy_label(policy_name)} 정보")

    return matched, list(dict.fromkeys(unmet)), list(dict.fromkeys(verification_needed))


def _adjust_evidence_level_for_policy(level, matched_policy, unmet_policy):
    if unmet_policy and not matched_policy:
        return "weak"
    if matched_policy and level == "weak":
        return "medium"
    return level


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

    text = re.sub(r"[\(\[\{（［【][^\)\]\}）］】]*[\)\]\}）］】]", " ", text)

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


def _frame_support_buckets(frame):
    return {
        "target": _frame_terms(frame, "target_objects"),
        "result": _frame_terms(frame, "result_match_terms"),
        "candidate": _frame_terms(frame, "candidate_place_types"),
        "query": _frame_terms(frame, "primary_search_queries", "secondary_search_queries"),
    }


def _term_support(term, buckets):
    compact_term = _compact(term)
    support = {key: 0 for key in buckets}
    if not compact_term:
        return support
    for key, values in buckets.items():
        seen_values = set()
        for value in values or []:
            compact_value = _compact(value)
            if not compact_value or compact_value in seen_values:
                continue
            if compact_term in compact_value:
                support[key] += 1
                seen_values.add(compact_value)
    return support


def _drop_short_qualifiers_when_specific_terms_exist(terms, protected_terms=None):
    if not any(len(_compact(term)) >= 3 for term in terms):
        return terms
    protected_compacts = {
        _compact(term)
        for term in protected_terms or []
        if _compact(term)
    }
    return [
        term
        for term in terms
        if len(_compact(term)) >= 3 or _compact(term) in protected_compacts
    ]


def _prefer_result_supported_terms(terms, buckets):
    result_supported = [
        term
        for term in terms
        if _term_support(term, buckets).get("result", 0) >= 1
    ]
    return result_supported or terms


def _select_target_db_terms(frame, max_items=12):
    buckets = _frame_support_buckets(frame)
    raw_terms = _specific_evidence_terms(
        [
            *buckets["target"],
            *buckets["result"],
        ],
        frame=frame,
        max_items=30,
    )
    target_terms = _specific_evidence_terms(buckets["target"], frame=frame, max_items=30)
    selected = []
    seen = set()

    high_target_support = []
    for term in target_terms:
        support = _term_support(term, buckets)
        if support.get("target", 0) >= 2:
            high_target_support.append(term)

    cross_supported_terms = []
    for term in raw_terms:
        support = _term_support(term, buckets)
        if support.get("target", 0) >= 1 and (
            support.get("result", 0) >= 1
            or support.get("candidate", 0) >= 1
        ):
            cross_supported_terms.append(term)

    if high_target_support and all(len(_compact(term)) <= 2 for term in high_target_support):
        source_terms = [*high_target_support, *cross_supported_terms]
    else:
        source_terms = high_target_support or cross_supported_terms or raw_terms
    for term in source_terms:
        support = _term_support(term, buckets)
        keep = False
        if support.get("target", 0) >= 2:
            keep = True
        elif support.get("target", 0) >= 1 and (
            support.get("result", 0) >= 1
            or support.get("candidate", 0) >= 1
        ):
            keep = True
        elif not high_target_support and support.get("target", 0) == 0 and selected:
            keep = False
        elif not high_target_support and not selected and support.get("target", 0) >= 1:
            keep = True

        if not keep:
            continue
        key = _compact(term)
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(term)
        if len(selected) >= max_items:
            break

    selected = _prefer_result_supported_terms(selected, buckets)
    selected = _drop_short_qualifiers_when_specific_terms_exist(selected)
    if selected:
        return selected[:max_items]

    fallback = _prefer_result_supported_terms(target_terms or raw_terms, buckets)
    fallback = _drop_short_qualifiers_when_specific_terms_exist(fallback)
    return fallback[:max_items]


def _select_candidate_db_terms(frame, target_terms, max_items=12):
    raw_terms = _specific_evidence_terms(_frame_terms(frame, "candidate_place_types"), frame=frame, max_items=30)
    if not target_terms:
        return _drop_short_qualifiers_when_specific_terms_exist(raw_terms)[:max_items]

    selected = []
    seen = set()
    target_compacts = [_compact(term) for term in target_terms if _compact(term)]
    raw_target_value_compacts = {
        _compact(value)
        for value in _frame_terms(frame, "target_objects", "targetObjects")
        if _compact(value)
    }
    structured_place_type_compacts = {
        _compact(term)
        for term in STRUCTURED_PLACE_TYPE_TERMS
        if _compact(term)
    }
    for term in raw_terms:
        compact_term = _compact(term)
        if not compact_term:
            continue
        overlaps_selected_target = any(
            target in compact_term or compact_term in target
            for target in target_compacts
        )
        is_explicit_target_object = compact_term in raw_target_value_compacts
        is_structured_place_type = compact_term in structured_place_type_compacts
        if not overlaps_selected_target and not is_explicit_target_object and not is_structured_place_type:
            continue
        if compact_term in seen:
            continue
        seen.add(compact_term)
        selected.append(term)
        if len(selected) >= max_items:
            break
    return _drop_short_qualifiers_when_specific_terms_exist(
        selected,
        protected_terms=[
            *raw_target_value_compacts,
            *structured_place_type_compacts,
        ],
    )[:max_items]


def _append_non_redundant_terms(base_terms, extra_terms, max_items=12):
    result = []
    seen = set()

    for term in [*(base_terms or []), *(extra_terms or [])]:
        compact_term = _compact(term)
        if not compact_term or compact_term in seen:
            continue
        if any(
            existing != compact_term and (existing in compact_term or compact_term in existing)
            for existing in seen
        ):
            continue
        seen.add(compact_term)
        result.append(term)
        if len(result) >= max_items:
            break

    return result


def _db_evidence_terms(frame):
    boardgame_text = _compact(" ".join([
        *_frame_terms(frame, "target_objects", "targetObjects"),
    ]))
    if any(term in boardgame_text for term in ["보드게임", "보드카페", "보드게임카페"]):
        boardgame_terms = ["보드게임카페", "보드게임", "보드카페"]
        return {
            "target": boardgame_terms,
            "candidate": boardgame_terms,
            "constraints": [],
            "search": boardgame_terms,
        }

    if _is_indoor_experience_frame(frame):
        indoor_experience_terms = [
            "키즈카페",
            "보드게임카페",
            "만화카페",
            "방탈출",
            "공방",
            "VR",
            "도예",
            "공예",
            "클라이밍",
        ]
        return {
            "target": indoor_experience_terms,
            "candidate": indoor_experience_terms,
            "constraints": ["실내"],
            "search": indoor_experience_terms,
        }

    target_terms = _select_target_db_terms(frame)
    candidate_terms = _select_candidate_db_terms(frame, target_terms)
    constraint_terms = _specific_evidence_terms(_evidence_terms(frame)["constraints"], frame=frame)
    explicit_target_compacts = {
        _compact(term)
        for term in _specific_evidence_terms(
            _frame_terms(frame, "target_objects", "targetObjects"),
            frame=frame,
            max_items=30,
        )
        if _compact(term)
    }
    explicit_candidate_terms = [
        term
        for term in candidate_terms
        if _compact(term) in explicit_target_compacts
    ]
    if any(
        _compact(term) in {"화장실", "공중화장실", "개방화장실"}
        for term in target_terms
    ):
        explicit_candidate_terms = []
    search_terms = (
        _append_non_redundant_terms(target_terms, explicit_candidate_terms)
        or candidate_terms
        or constraint_terms
    )
    return {
        "target": target_terms,
        "candidate": candidate_terms,
        "constraints": constraint_terms,
        "search": search_terms,
    }


def _raw_target_evidence_terms(frame, max_items=12):
    terms = _specific_evidence_terms(
        [
            *_frame_terms(frame, "target_objects", "targetObjects"),
            *_frame_terms(frame, "result_match_terms", "resultMatchTerms"),
        ],
        frame=frame,
        max_items=30,
    )
    return _drop_short_qualifiers_when_specific_terms_exist(
        terms,
        protected_terms=_frame_terms(frame, "target_objects", "targetObjects"),
    )[:max_items]


def _clean_exclusion_text(value):
    text = _clean_text(value, 120)
    if not text:
        return ""
    for marker in (
        "제외해줘",
        "제외",
        "빼줘",
        "빼고",
        "빼",
        "말고",
        "아닌",
        "아니고",
        "않고",
        "없이",
    ):
        text = re.sub(re.escape(marker), " ", text, flags=re.IGNORECASE)
    return _clean_text(text, 120)


def _frame_exclusion_match_terms(frame):
    terms = []
    seen = set()
    for value in _frame_terms(frame, "exclusions", "excluded_place_natures", "avoid"):
        cleaned = _clean_exclusion_text(value)
        if not cleaned:
            continue
        parts = [part for part in re.split(r"[,/;|]+", cleaned) if _clean_text(part)]
        if len(parts) <= 1 and len(re.split(r"\s+", cleaned.strip())) > 1:
            parts = [cleaned]
        for part in parts:
            split_terms = _specific_evidence_terms([part], frame=frame, max_items=8)
            if not split_terms:
                split_terms = [_trim_evidence_suffixes(part)]
            for term in split_terms:
                compact_term = _compact(term)
                if not compact_term or compact_term in seen or _is_broad_term(term):
                    continue
                seen.add(compact_term)
                terms.append(term)
    return terms


def _source_excluded_by_frame(candidate, frame):
    source = _clean_text(candidate.get("candidate_source") or candidate.get("source"))
    if source != "web":
        return False
    exclusion_text = _compact(" ".join(_frame_terms(frame, "exclusions", "excluded_place_natures", "avoid")))
    return bool(exclusion_text and ("웹" in exclusion_text or "web" in exclusion_text))


def _generic_exclusion_review(text, frame, candidate=None):
    unmet = []
    if candidate and _source_excluded_by_frame(candidate, frame):
        unmet.append("제외 조건과 맞지 않는 웹 후보")
    for term in _matched_terms(text, _frame_exclusion_match_terms(frame)):
        unmet.append(f"제외 조건과 맞지 않는 {term} 정보")
    return list(dict.fromkeys(unmet))


def _frame_semantic_text(frame):
    return " ".join([
        *_frame_terms(frame, "target_objects", "targetObjects"),
        *_frame_terms(frame, "result_match_terms", "resultMatchTerms"),
        *_frame_terms(frame, "candidate_place_types", "candidatePlaceTypes"),
        *_frame_terms(frame, "constraints"),
        *_frame_terms(frame, "primary_search_queries", "search_queries", "searchQueries"),
    ])


def _candidate_semantic_text(candidate):
    return " ".join([
        _clean_text(candidate.get("name")),
        _clean_text(candidate.get("category")),
        _clean_text(candidate.get("kakao_category")),
        _clean_text(candidate.get("source_category")),
        _clean_text(candidate.get("external_category")),
        " ".join(_as_list(candidate.get("matched_tags"))),
        " ".join(_as_list(candidate.get("matched_tag_labels"))),
        " ".join(_as_list(candidate.get("verified_tags"))),
        " ".join(_as_list(candidate.get("suggested_tags"))),
        " ".join(_as_list(candidate.get("candidate_tags"))),
        " ".join(_as_list(candidate.get("place_natures"))),
    ])


_CASUAL_VISITOR_INTENT_TERMS = tuple(_compact(term) for term in [
    "\uce74\ud398",
    "\ucee4\ud53c",
    "\uc74c\ub8cc",
    "\uc2dd\uc0ac",
    "\uc74c\uc2dd",
    "\ub9db\uc9d1",
    "\uc1fc\ud551",
    "\ubc31\ud654\uc810",
    "\uc544\uc6b8\ub81b",
    "\uc804\uc2dc",
    "\ubc15\ubb3c\uad00",
    "\ubbf8\uc220\uad00",
    "\uac24\ub7ec\ub9ac",
    "\uc2e4\ub0b4\uccb4\ud5d8",
    "\uccb4\ud5d8",
    "\uc561\ud2f0\ube44\ud2f0",
    "\ub180\uac70\ub9ac",
    "\uc0b0\ucc45",
    "\uc270\uacf3",
    "\uc26c",
    "\uae30\ub2e4",
    "\ub370\uc774\ud2b8",
    "\ube44\ud53c",
    "\ub354\uc6cc",
    "\uc88b\uc740\uacf3",
    "\uc2dc\uac04\ubcf4\ub0bc",
    "\ucd94\ucc9c",
])

_CASUAL_VISITOR_UNFRIENDLY_TERMS = tuple(_compact(term) for term in [
    "\uacbd\ub85c\ub2f9",
    "\ub178\uc778\uc815",
    "\ub178\uc778\ud68c",
    "\ub178\uc778\ud68c\uad00",
    "\ub178\uc778\ubcf5\uc9c0",
    "\ub9c8\uc744\ud68c\uad00",
    "\ud589\uc815\ubcf5\uc9c0\uc13c\ud130",
    "\uc8fc\ubbfc\uc13c\ud130",
    "\ub3d9\uc8fc\ubbfc\uc13c\ud130",
    "\uad6c\uccad",
    "\uc2dc\uccad",
    "\uc0c1\ub2f4\uc13c\ud130",
    "\uccad\uc18c\ub144\uc0c1\ub2f4",
    "\uc815\uc2e0\uac74\uac15\ubcf5\uc9c0\uc13c\ud130",
    "\ub9c8\uc74c\uc270\ud130",
    "\ub9c8\uc74c\uac74\uac15",
    "\uac74\uac15\uac00\uc815\uc9c0\uc6d0\uc13c\ud130",
    "\uac00\uc871\uc13c\ud130",
    "\uace0\uc6a9\ubcf5\uc9c0\uc13c\ud130",
    "\uc790\ud65c\uc13c\ud130",
    "\uc9c0\uc5ed\uc544\ub3d9\uc13c\ud130",
    "\uc885\ud569\uc0ac\ud68c\ubcf5\uc9c0\uad00",
    "\ubcf5\uc9c0\uad00",
    "\uce58\ub9e4\uc548\uc2ec\uc13c\ud130",
])

_CASUAL_VISITOR_UNFRIENDLY_EXEMPT_TERMS = tuple(_compact(term) for term in [
    "\uacbd\ub85c\ub2f9",
    "\uc8fc\ubbfc\uc13c\ud130",
    "\ud589\uc815\ubcf5\uc9c0\uc13c\ud130",
    "\ubcf5\uc9c0\uad00",
    "\uc0c1\ub2f4",
    "\ub9c8\uc74c",
    "\uacf5\uacf5\uae30\uad00",
    "\ubbfc\uc6d0",
    "\ubb34\ub354\uc704\uc270\ud130",
    "\ud55c\ud30c\uc270\ud130",
    "\ud654\uc7a5\uc2e4",
    "\ud761\uc5f0",
    "\uc57d\uad6d",
    "\ubcd1\uc6d0",
    "\uc8fc\ucc28",
    "\uacbd\ucc30",
    "\uc18c\ubc29",
    "\ubcf4\uac74\uc18c",
])


def _casual_visitor_unfriendly_review(candidate_text, frame_text):
    if not any(term and term in frame_text for term in _CASUAL_VISITOR_INTENT_TERMS):
        return []
    if any(term and term in frame_text for term in _CASUAL_VISITOR_UNFRIENDLY_EXEMPT_TERMS):
        return []
    if any(term and term in candidate_text for term in _CASUAL_VISITOR_UNFRIENDLY_TERMS):
        return [
            "\uc77c\ubc18 \ubc29\ubb38 \ucd94\ucc9c \ub9e5\ub77d\uacfc \ub9de\uc9c0 \uc54a\ub294 "
            "\uacf5\uacf5/\ubcf5\uc9c0/\uc0c1\ub2f4 \uacc4\uc5f4 \ud6c4\ubcf4"
        ]
    return []


def _semantic_category_review(candidate, frame):
    frame_text = _compact(_frame_semantic_text(frame))
    candidate_text = _compact(_candidate_semantic_text(candidate))
    candidate_category_text = _compact(_clean_text(candidate.get("category")))
    frame_target_text = _compact(" ".join([
        *_frame_terms(frame, "target_objects", "targetObjects"),
    ]))
    frame_target_result_text = _compact(" ".join([
        *_frame_terms(frame, "target_objects", "targetObjects"),
        *_frame_terms(frame, "result_match_terms", "resultMatchTerms"),
    ]))
    unmet = []
    if not frame_text or not candidate_text:
        return unmet
    unmet.extend(_casual_visitor_unfriendly_review(candidate_text, frame_text))

    personal_power_request = any(
        term in frame_text
        for term in [
            "\ucf58\uc13c\ud2b8",
            "\ubc30\ud130\ub9ac",
            "\ud734\ub300\ud3f0\ucda9\uc804",
            "\ucda9\uc804\uac00\ub2a5",
            "\ub178\ud2b8\ubd81",
        ]
    )
    if personal_power_request:
        power_positive = ["\uce74\ud398", "\ub3c4\uc11c\uad00", "\ucf54\uc6cc\ud0b9", "\ucf58\uc13c\ud2b8", "\ub178\ud2b8\ubd81", "\uc640\uc774\ud30c\uc774"]
        power_forbidden = [
            "\uc804\uae30\ucc28\ucda9\uc804",
            "ev\ucda9\uc804",
            "lpg\ucda9\uc804",
            "\uac00\uc2a4\ucda9\uc804",
            "\ucda9\uc804\uc18c",
            "\uc8fc\uc720\uc18c",
            "\uc8fc\ucc28\uc7a5",
            "freewifi",
            "\uacf5\uacf5\uc640\uc774\ud30c\uc774",
            "\uc640\uc774\ud30c\uc774\uc874",
            "\ubc84\uc2a4\uc815\ub958\uc7a5",
            "\ucd08\ub4f1\ud559\uad50",
        ]
        if any(term in candidate_text for term in power_forbidden) and not any(
            term in candidate_text for term in power_positive
        ):
            unmet.append("\ud734\ub300\uae30\uae30 \ucda9\uc804/\ucf58\uc13c\ud2b8 \uc694\uccad\uacfc \ub9de\uc9c0 \uc54a\ub294 \ucc28\ub7c9 \ucda9\uc804\uc18c/\uc8fc\ucc28\uc7a5 \ud6c4\ubcf4")

    drink_cafe_request = (
        ("카페" in frame_target_text or "커피" in frame_target_result_text)
        and any(term in frame_target_result_text for term in ["음료", "커피", "마실", "마시"])
        and not any(term in frame_target_result_text for term in ["작업", "공부", "스터디", "노트북", "놋북", "카공"])
    )
    cafe_request = (
        "카페" in frame_target_text
        or "커피" in frame_target_result_text
        or "음료" in frame_target_result_text
    )
    if cafe_request:
        cafe_forbidden = [
            "사진관",
            "포토스튜디오",
            "즉석사진",
            "전문대행",
            "공간대여",
            "스터디룸",
            "독서실",
            "인터넷쇼핑몰",
            "통신판매",
            "카페거리",
            "카페골목",
            "freewifi",
            "공공와이파이",
            "와이파이존",
            "버스정류장",
            "초등학교",
            "중학교",
            "고등학교",
        ]
        if any(term in candidate_text for term in cafe_forbidden):
            unmet.append("카페 요청과 맞지 않는 비카페 후보")

    if drink_cafe_request:
        forbidden = ["스터디카페", "스터디룸", "공간대여", "전문대행", "독서실", "study_cafe", "studyroom"]
        if any(term in candidate_text for term in forbidden):
            unmet.append("음료 카페 요청과 맞지 않는 스터디/공간대여 후보")

    bar_request = any(term in frame_text for term in ["술집", "주점", "와인바", "칵테일바", "펍", "호프"])
    if bar_request:
        bar_positive = ["술집", "주점", "와인바", "칵테일바", "스포츠바", "펍", "호프", "포차", "이자카야", "bar"]
        if not any(term in candidate_text for term in bar_positive):
            unmet.append("술집/바 요청과 맞지 않는 후보")

    boardgame_request = any(term in frame_target_text for term in ["보드게임", "보드카페", "보드게임카페"])
    if boardgame_request and not any(term in candidate_text for term in ["보드게임", "보드카페", "보드게임카페"]):
        unmet.append("보드게임카페 요청과 맞지 않는 후보")

    restaurant_request = any(term in frame_target_text for term in ["식당", "음식점", "밥", "맛집", "회식", "단체식사"])
    if restaurant_request and ("카페" in candidate_category_text or candidate_category_text == "cafe"):
        if not any(term in frame_text for term in ["카페", "커피", "디저트", "브런치"]):
            unmet.append("식당 요청과 맞지 않는 카페 카테고리 후보")

    group_dining_request = any(term in frame_text for term in ["회식", "단체식사", "단체석", "모임식사", "모임장소"])
    if group_dining_request:
        group_dining_positive = [
            "회식",
            "단체",
            "단체석",
            "고기",
            "고깃",
            "육류",
            "삼겹",
            "갈비",
            "한우",
            "소고기",
            "돼지",
            "구이",
            "횟집",
            "회",
            "해물",
            "전골",
            "부대찌개",
            "이자카야",
            "포차",
            "주점",
        ]
        group_dining_light_meal_negative = [
            "국수",
            "분식",
            "김밥",
            "순두부",
            "비빔밥",
            "샌드위치",
            "버거",
            "카페",
            "디저트",
            "도시락",
            "죽",
            "라면",
        ]
        has_group_dining_signal = any(term in candidate_text for term in group_dining_positive)
        if any(term in candidate_text for term in group_dining_light_meal_negative) and not has_group_dining_signal:
            unmet.append("회식/단체 식사 요청과 맞지 않는 간단한 식사 후보")
        elif not has_group_dining_signal:
            unmet.append("회식/단체 식사에 적합하다는 근거가 부족한 후보")

    shopping_request = any(term in frame_target_text for term in ["쇼핑몰", "백화점", "아울렛", "복합쇼핑몰", "대형마트", "쇼핑할곳"])
    if shopping_request:
        shopping_positive = ["쇼핑몰", "백화점", "아울렛", "복합쇼핑", "쇼핑센터", "대형마트", "몰링"]
        shopping_forbidden = [
            "인터넷쇼핑몰",
            "온라인쇼핑",
            "전자상거래",
            "통신판매",
            "쇼핑몰제작",
            "쇼핑몰관리",
            "쇼핑몰솔루션",
            "온라인몰",
            "부동산",
            "공인중개",
            "제조업",
            "산업용품",
            "비닐",
            "종교용품",
            "약국",
            "의약품",
            "네일",
            "미용",
            "반려동물",
            "휴대폰",
            "전자제품판매",
            "통신기기",
        ]
        shopping_tenant_forbidden = [
            "음식점",
            "식당",
            "카페",
            "약국",
            "병원",
            "치과",
            "의원",
            "주차장",
            "찌개",
            "국밥",
            "분식",
            "고기",
            "의류판매",
            "스포츠용품",
            "생활용품점",
            "주방용품",
            "패션잡화점",
            "상설할인매장",
            "안경",
            "화장품",
        ]
        if any(term in candidate_text for term in shopping_forbidden):
            unmet.append("오프라인 쇼핑몰/백화점 요청과 맞지 않는 온라인 쇼핑 후보")
        elif any(term in candidate_text for term in shopping_tenant_forbidden):
            unmet.append("쇼핑몰/백화점 요청과 맞지 않는 입점 식음료/편의시설 후보")
        elif not any(term in candidate_text for term in shopping_positive):
            unmet.append("쇼핑몰/백화점 요청과 맞지 않는 후보")

    exhibition_request = any(term in frame_target_text for term in ["전시", "전시관", "전시장", "전시회", "박물관", "미술관", "갤러리"])
    if exhibition_request:
        exhibition_positive = [
            "전시관",
            "전시회",
            "전시실",
            "전시센터",
            "박물관",
            "미술관",
            "갤러리",
            "아트센터",
            "문화회관",
        ]
        exhibition_forbidden = [
            "패션잡화점",
            "구두",
            "신발",
            "의류판매",
            "생활용품점",
            "상설할인매장",
            "도매",
            "시장",
        ]
        if any(term in candidate_text for term in exhibition_forbidden):
            unmet.append("전시/박물관 요청과 맞지 않는 판매/시장 후보")
        elif not any(term in candidate_text for term in exhibition_positive):
            unmet.append("전시/박물관 요청과 맞지 않는 후보")

    smoking_request = "흡연" in frame_text or "담배" in frame_text
    if smoking_request:
        policy_requirements = _frame_policy_requirements(frame)
        wants_outdoor = "outdoor" in policy_requirements.get("desired", [])
        wants_indoor = "indoor" in policy_requirements.get("desired", [])
        outdoor_positive = ["실외", "외부", "야외", "옥외", "흡연부스", "개방형", "도로변", "보도"]
        indoor_positive = ["실내", "내부", "건물내", "건물안", "실내흡연실"]
        likely_indoor_venue = [
            "pc",
            "pc방",
            "pc카페",
            "pc클럽",
            "pccafe",
            "피씨방",
            "피씨",
            "피씨까페",
            "피씨카페",
            "당구장",
            "카페",
            "음식점",
            "주점",
            "노래방",
            "게임장",
            "호텔",
            "상가",
            "건물",
        ]
        if wants_outdoor:
            has_outdoor = any(term in candidate_text for term in outdoor_positive)
            if any(term in candidate_text for term in indoor_positive):
                unmet.append("실외 흡연구역 요청과 다른 실내 흡연 후보")
            elif any(term in candidate_text for term in likely_indoor_venue) and not has_outdoor:
                unmet.append("실외 흡연구역 요청에 실외 근거가 부족한 실내 업장 후보")
        if wants_indoor and any(term in candidate_text for term in outdoor_positive) and not any(
            term in candidate_text for term in indoor_positive
        ):
            unmet.append("실내 흡연실 요청과 다른 실외 흡연 후보")

    indoor_experience_request = _is_indoor_experience_frame_text(frame_text)
    if indoor_experience_request:
        experience_positive = [
            "체험",
            "액티비티",
            "도예",
            "공예",
            "vr",
            "브이알",
            "공방",
            "원데이클래스",
            "클래스",
            "스튜디오",
            "방탈출",
            "실내놀이터",
            "키즈카페",
            "보드게임",
            "만화카페",
            "클라이밍",
            "메이커",
            "만들기",
        ]
        indoor_positive = [
            "실내",
            "도예",
            "공예",
            "vr",
            "브이알",
            "공방",
            "원데이클래스",
            "클래스",
            "스튜디오",
            "방탈출",
            "실내놀이터",
            "키즈카페",
            "보드게임",
            "클라이밍",
            "만화카페",
            "박물관",
            "미술관",
            "전시관",
        ]
        outdoor_negative = ["공원", "산책", "해수욕장", "등산", "야외", "광장", "시장", "거리"]
        has_experience = any(term in candidate_text for term in experience_positive)
        has_indoor = any(term in candidate_text for term in indoor_positive)
        has_outdoor = any(term in candidate_text for term in outdoor_negative)
        if not has_experience:
            unmet.append("실내 체험 요청과 맞지 않는 후보")
        if has_outdoor and not has_indoor:
            unmet.append("실내 체험 요청과 맞지 않는 야외/산책형 후보")

    return list(dict.fromkeys(unmet))


def _is_indoor_experience_frame_text(frame_text):
    return (
        any(term in frame_text for term in ["실내체험", "실내액티비티"])
        or (
            any(term in frame_text for term in ["실내", "indoors", "indoor"])
            and any(term in frame_text for term in ["체험", "액티비티", "놀거리", "도예", "공예", "vr", "방탈출", "보드게임", "만화카페"])
        )
    )


def _is_indoor_experience_frame(frame):
    return _is_indoor_experience_frame_text(_compact(_frame_semantic_text(frame)))


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


def _term_matches_text(term, text):
    compact_term = _compact(term)
    compact_text = _compact(text)
    if not compact_term or not compact_text:
        return False
    if compact_term == "전시":
        return any(
            marker in compact_text
            for marker in ["전시관", "전시장", "전시회", "전시실", "전시센터", "전시공간", "전시홀"]
        )
    if compact_term == "바":
        return any(
            marker in compact_text
            for marker in ["와인바", "칵테일바", "스포츠바", "펍", "bar"]
        ) or bool(re.search(r"(^|[^가-힣a-zA-Z0-9])바($|[^가-힣a-zA-Z0-9])", _clean_text(text)))
    return compact_term in compact_text


def _matched_terms(text, terms):
    matched = []
    for term in terms:
        if _term_matches_text(term, text):
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


def _nearby_bounds(lat, lng, radius):
    lat = _as_float(lat)
    lng = _as_float(lng)
    radius = _radius(radius)
    if lat is None or lng is None:
        return None
    lat_delta = radius / 111_000
    lng_scale = max(math.cos(math.radians(lat)), 0.2)
    lng_delta = radius / (111_000 * lng_scale)
    return {
        "lat_min": lat - lat_delta,
        "lat_max": lat + lat_delta,
        "lng_min": lng - lng_delta,
        "lng_max": lng + lng_delta,
    }


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
    raw_target_terms = _specific_evidence_terms(
        [
            *_frame_terms(frame, "target_objects", "targetObjects"),
            *_frame_terms(frame, "result_match_terms", "resultMatchTerms"),
        ],
        frame=frame,
        max_items=30,
    )
    raw_candidate_terms = _specific_evidence_terms(
        _frame_terms(frame, "candidate_place_types", "candidatePlaceTypes"),
        frame=frame,
        max_items=30,
    )
    frame_category_codes = _frame_category_codes(frame)
    db_first_category_codes = _db_first_category_codes(frame)
    direct_category_codes = _direct_db_category_codes(frame)
    category_label = _clean_text(get_category_display_name(place.category))
    category_text = " ".join([_clean_text(place.category), category_label])
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
    policy_text = " ".join([
        *text_fields.values(),
        *tag_lists["verified"],
        *tag_lists["suggested"],
        *tag_lists["candidate"],
    ])
    policy_matched, policy_unmet, policy_verification_needed = _policy_review(
        policy_text,
        frame,
        field="db_tags_or_place_text",
        source_strength="verified",
    )
    policy_unmet = [
        *policy_unmet,
        *_generic_exclusion_review(policy_text, frame),
        *_semantic_category_review(
            {
                "name": place.name,
                "category": " ".join([place.category, category_label]),
                "matched_tags": [
                    *tag_lists["verified"],
                    *tag_lists["suggested"],
                    *tag_lists["candidate"],
                ],
            },
            frame,
        ),
    ]

    if place.category in direct_category_codes or place.category in db_first_category_codes:
        matched.append({
            "type": "structured_category_direct",
            "field": "category",
            "value": place.category,
            "source_strength": "verified",
        })
        level = "strong"

    if place.category in frame_category_codes and place.category not in db_first_category_codes:
        matched.append({
            "type": "category_code",
            "field": "category",
            "value": place.category,
            "label": category_label,
            "source_strength": "category_only",
        })

    for term in _matched_terms(category_text, raw_target_terms):
        matched.append({
            "type": "target_category_label",
            "field": "category",
            "value": term,
            "label": category_label,
            "source_strength": "category_only",
        })

    for term in _matched_terms(category_text, raw_candidate_terms or candidate_terms):
        matched.append({
            "type": "category_label",
            "field": "category",
            "value": term,
            "label": category_label,
            "source_strength": "category_only",
        })

    for field_name, text in text_fields.items():
        for term in _matched_terms(text, target_terms or raw_target_terms):
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
        term_is_direct_category = any(
            _compact(term) in {
                _compact(code),
                _compact(get_category_display_name(code)),
            }
            for code in direct_category_codes
        )
        if term_is_direct_category and place.category not in direct_category_codes:
            continue
        matched.append({
            "type": "suggested_tag_direct",
            "field": "suggested_tags",
            "value": term,
            "source_strength": "suggested",
        })
        if level != "strong":
            level = "medium"

    for term in _matched_terms(" ".join(tag_lists["candidate"]), target_terms):
        term_is_direct_category = any(
            _compact(term) in {
                _compact(code),
                _compact(get_category_display_name(code)),
            }
            for code in direct_category_codes
        )
        if term_is_direct_category and place.category not in direct_category_codes:
            continue
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

    if policy_matched:
        matched.extend(policy_matched)
    level = _adjust_evidence_level_for_policy(level, policy_matched, policy_unmet)

    return level, matched, policy_unmet, policy_verification_needed


def _candidate_base(candidate_id, source, name, category, address, lat=None, lng=None, distance=None):
    source_type = {
        "db": "db_candidate",
        "kakao": "kakao_candidate",
        "web": "web_evidence_candidate",
    }.get(source, f"{source}_candidate")
    return {
        "id": candidate_id,
        "candidate_source": source,
        "unified_candidate_source": source,
        "source": source,
        "source_type": source_type,
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


def _candidate_has_invalid_display(candidate):
    pieces = [
        _clean_text(candidate.get("name")),
        _clean_text(candidate.get("address")),
        _clean_text(candidate.get("detail_location")),
    ]
    if any("??" in piece for piece in pieces if piece):
        return True
    name = _clean_text(candidate.get("name"))
    address = _clean_text(candidate.get("address") or candidate.get("detail_location"))
    return "검증 태그" in name or "테스트로" in address


def collect_db_candidates(frame, *, lat=None, lng=None, limit=50, radius=None):
    terms = _db_evidence_terms(frame)
    search_terms = terms["search"]
    db_first_category_codes = _db_first_category_codes(frame)
    direct_category_codes = _direct_db_category_codes(frame)
    if not search_terms and not db_first_category_codes and not direct_category_codes:
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
    if db_first_category_codes:
        query |= Q(category__in=db_first_category_codes)
    if direct_category_codes:
        query |= Q(category__in=direct_category_codes)

    radius = _radius(radius)
    bounds = _nearby_bounds(lat, lng, radius)
    queryset = (
        Place.objects
        .filter(query)
        .distinct()
        .prefetch_related("place_tags__tag")
    )
    if bounds:
        queryset = queryset.filter(
            lat__gte=bounds["lat_min"],
            lat__lte=bounds["lat_max"],
            lng__gte=bounds["lng_min"],
            lng__lte=bounds["lng_max"],
        )

    queryset = queryset.order_by("-data_quality_score", "-updated_at")
    candidates = []
    for place in queryset[: max(limit * 5, 100)]:
        distance = _distance(lat, lng, place.lat, place.lng)
        if distance is not None and distance > radius:
            continue
        tag_lists = _db_tag_lists(place)
        level, matched, policy_unmet, policy_verification_needed = _db_evidence(place, tag_lists, frame)
        if direct_category_codes and place.category not in direct_category_codes:
            has_strong_non_category_evidence = any(
                item.get("type") in {"target_direct", "verified_tag_direct"}
                for item in matched
            )
            if not has_strong_non_category_evidence:
                continue
        policy_matched = [
            item["value"]
            for item in matched
            if item.get("type") == "policy_constraint"
        ]
        score = {"strong": 80, "medium": 55, "weak": 25}.get(level, 25)
        if policy_unmet:
            score = min(score, 35)
        elif policy_matched:
            score = min(score + 8, 92)
        elif policy_verification_needed:
            score = max(score - 8, 20)
        confidence_level = "high" if level == "strong" else "medium" if level == "medium" else "low"
        if policy_unmet:
            confidence_level = "low"
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
            "policy_matched_constraints": policy_matched,
            "pre_ai_unmet_constraints": policy_unmet,
            "policy_verification_needed": policy_verification_needed,
            "pre_ai_evidence_level": level,
            "evidence_level": level,
            "frame_match_strength": level,
            "recommendation_confidence": confidence_level,
            "confidence": confidence_level,
            "confidence_label": _confidence_label(level, "db"),
            "recommendation_reason": _confidence_label(level, "db"),
            "recommend_reason": _confidence_label(level, "db"),
            "score": score,
            "score_breakdown": {
                "collector": "db",
                "pre_ai_evidence_level": level,
                "policy_matched_constraints": policy_matched,
                "pre_ai_unmet_constraints": policy_unmet,
                "policy_verification_needed": policy_verification_needed,
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


def _candidate_has_location_text_evidence(candidate, frame):
    location_mode = _clean_text(frame.get("location_mode"))
    anchor_locations = _as_list(frame.get("anchor_location"), max_items=3)
    if not anchor_locations:
        return location_mode != "explicit"
    text = _compact(_candidate_text(candidate))
    if not text:
        return False

    for anchor in anchor_locations:
        anchor_key = _compact(anchor)
        if anchor_key and anchor_key in text:
            return True
        tokens = [
            _compact(token)
            for token in re.split(r"[\s,;/|]+", anchor)
            if len(_compact(token)) >= 2
        ]
        if len(tokens) >= 2 and all(token in text for token in tokens):
            return True
        for alias in _anchor_location_aliases(anchor):
            alias_key = alias.get("key")
            area_tokens = alias.get("area_tokens") or []
            if not alias_key or alias_key == anchor_key:
                continue
            if alias_key in text and all(token in text for token in area_tokens):
                return True
    return False


def _external_pre_ai_evidence(candidate, frame):
    db_terms = _db_evidence_terms(frame)
    target_terms = db_terms["target"]
    candidate_terms = db_terms["candidate"]
    raw_target_terms = [
        term
        for term in _raw_target_evidence_terms(frame, max_items=20)
        if _compact(term) not in {_compact(item) for item in target_terms}
    ]
    text = _candidate_text(candidate)
    retrieval_query = _clean_text(candidate.get("retrieval_query"))
    source = _clean_text(candidate.get("candidate_source") or candidate.get("source"))
    has_location_text_evidence = source != "web" or _candidate_has_location_text_evidence(candidate, frame)
    matched = []
    if has_location_text_evidence:
        for term in _matched_terms(text, target_terms):
            matched.append({"type": "target_direct", "value": term, "source_strength": "external"})
        if matched:
            return "strong", matched
        for term in _matched_terms(text, raw_target_terms):
            matched.append({"type": "target_context", "value": term, "source_strength": "external"})
        if matched:
            return "medium", matched
        for term in _matched_terms(text, candidate_terms):
            matched.append({"type": "candidate_type", "value": term, "source_strength": "external"})
        if matched:
            return "medium", matched
    for term in _matched_terms(retrieval_query, target_terms):
        matched.append({"type": "retrieval_query_target", "value": term, "source_strength": "external_query"})
    if matched:
        return "medium", matched
    return "weak", []


def _merge_candidate_policy_review(candidate, frame, level, matched, *, field, source_strength):
    policy_matched_evidence, policy_unmet, policy_verification_needed = _policy_review(
        _candidate_text(candidate),
        frame,
        field=field,
        source_strength=source_strength,
    )
    policy_unmet = [
        *policy_unmet,
        *_generic_exclusion_review(_candidate_text(candidate), frame, candidate=candidate),
        *_semantic_category_review(candidate, frame),
    ]
    merged_matched = [*matched, *policy_matched_evidence]
    adjusted_level = _adjust_evidence_level_for_policy(
        level,
        policy_matched_evidence,
        policy_unmet,
    )
    return (
        adjusted_level,
        merged_matched,
        [item["value"] for item in policy_matched_evidence],
        policy_unmet,
        policy_verification_needed,
    )


def _policy_adjusted_score(base_score, *, policy_matched=None, policy_unmet=None, policy_verification_needed=None):
    score = float(base_score or 0)
    if policy_unmet:
        return min(score, 35)
    if policy_matched:
        return min(score + 8, 92)
    if policy_verification_needed:
        return max(score - 8, 20)
    return score


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
            level, matched, policy_matched, policy_unmet, policy_verification_needed = _merge_candidate_policy_review(
                candidate,
                frame,
                level,
                matched,
                field="kakao_text",
                source_strength="external",
            )
            base_score = {"strong": 72, "medium": 50, "weak": 20}.get(level, 20)
            score = _policy_adjusted_score(
                base_score,
                policy_matched=policy_matched,
                policy_unmet=policy_unmet,
                policy_verification_needed=policy_verification_needed,
            )
            confidence_level = "medium" if level in {"strong", "medium"} else "low"
            if policy_unmet:
                confidence_level = "low"
            candidate.update({
                "pre_ai_evidence_level": level,
                "evidence_level": level,
                "matched_evidence": matched,
                "matched_tags": [item["value"] for item in matched],
                "matched_tag_labels": [item["value"] for item in matched],
                "policy_matched_constraints": policy_matched,
                "pre_ai_unmet_constraints": policy_unmet,
                "policy_verification_needed": policy_verification_needed,
                "confidence": confidence_level,
                "recommendation_confidence": confidence_level,
                "confidence_label": _confidence_label(level, "kakao"),
                "recommendation_reason": _confidence_label(level, "kakao"),
                "recommend_reason": _confidence_label(level, "kakao"),
                "score": score,
                "score_breakdown": {
                    "collector": "kakao",
                    "retrieval_query": query,
                    "pre_ai_evidence_level": level,
                    "policy_matched_constraints": policy_matched,
                    "pre_ai_unmet_constraints": policy_unmet,
                    "policy_verification_needed": policy_verification_needed,
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
            level, matched, policy_matched, policy_unmet, policy_verification_needed = _merge_candidate_policy_review(
                candidate,
                frame,
                level,
                matched,
                field="web_text",
                source_strength="external",
            )
            base_score = {"strong": 68, "medium": 45, "weak": 20}.get(level, 20)
            score = _policy_adjusted_score(
                base_score,
                policy_matched=policy_matched,
                policy_unmet=policy_unmet,
                policy_verification_needed=policy_verification_needed,
            )
            confidence_level = "medium" if level in {"strong", "medium"} else "low"
            if policy_unmet:
                confidence_level = "low"
            candidate.update({
                "pre_ai_evidence_level": level,
                "evidence_level": level,
                "matched_evidence": matched,
                "policy_matched_constraints": policy_matched,
                "pre_ai_unmet_constraints": policy_unmet,
                "policy_verification_needed": policy_verification_needed,
                "confidence": confidence_level,
                "recommendation_confidence": confidence_level,
                "confidence_label": _confidence_label(level, "web"),
                "recommendation_reason": _confidence_label(level, "web"),
                "recommend_reason": _confidence_label(level, "web"),
                "score": score,
                "score_breakdown": {
                    "collector": "web",
                    "retrieval_query": query,
                    "pre_ai_evidence_level": level,
                    "policy_matched_constraints": policy_matched,
                    "pre_ai_unmet_constraints": policy_unmet,
                    "policy_verification_needed": policy_verification_needed,
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
    text = _compact(query)
    markers = {
        "web",
        "external",
        "official",
        "verify",
        "latest",
        "review",
        "blog",
        "웹",
        "외부",
        "공식",
        "최신",
        "리뷰",
        "블로그",
        "후기",
    }
    return any(_compact(marker) in text for marker in markers)


def _candidate_sort_key(candidate):
    if candidate.get("pre_ai_unmet_constraints"):
        policy_rank = 3
    elif candidate.get("policy_matched_constraints"):
        policy_rank = 0
    elif candidate.get("policy_verification_needed"):
        policy_rank = 2
    else:
        policy_rank = 1
    return (
        policy_rank,
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


def _can_top_up_excluded_candidate(candidate):
    source = _clean_text(candidate.get("candidate_source") or candidate.get("source"))
    level = _clean_text(candidate.get("pre_ai_evidence_level") or candidate.get("evidence_level"))
    if candidate.get("pre_ai_unmet_constraints"):
        return False
    matched_evidence = candidate.get("matched_evidence") if isinstance(candidate.get("matched_evidence"), list) else []
    if source == "kakao" and level in {"strong", "medium"}:
        external_types = {
            "target_direct",
            "candidate_type",
            "target_context",
            "policy_constraint",
        }
        return any(
            isinstance(item, dict) and item.get("type") in external_types
            for item in matched_evidence
        )
    if source != "db":
        return False
    if level != "strong":
        return False
    direct_types = {
        "target_direct",
        "verified_tag_direct",
        "suggested_tag_direct",
        "candidate_tag_direct",
    }
    return any(
        isinstance(item, dict) and item.get("type") in direct_types
        for item in matched_evidence
    )


def _blocking_unmet_constraints(candidate):
    if not isinstance(candidate, dict):
        return []
    unmet = []
    unmet.extend(_as_list(candidate.get("pre_ai_unmet_constraints")))
    semantic = candidate.get("semantic_reranker") if isinstance(candidate.get("semantic_reranker"), dict) else {}
    unmet.extend(_as_list(semantic.get("unmet_constraints")))
    return [
        _clean_text(item, 120)
        for item in unmet
        if _clean_text(item, 120) and _clean_text(item, 120) != "details_need_verification"
    ]


def _minimum_result_count(limit):
    configured = _as_int(getattr(settings, "AI_SEARCH_MIN_RESULTS", 10), 10)
    return min(max(configured, 1), max(_as_int(limit, 15), 1), 20)


def _deterministic_category_codes(frame):
    """
    `가까운 화장실`처럼 카테고리와 거리만으로 답이 정해지는 요청이면 그 카테고리 목록을 돌려준다.

    이런 요청에서는 AI 후보 평가가 결과 순서를 바꾸지 않는다.
    `urgent_nearest`는 평가 후 어차피 거리순으로 재정렬하고, 후보도 이미 카테고리로 걸러져 들어오기 때문이다.
    조건이 하나라도 붙거나 카테고리로 떨어지지 않는 표현이 섞이면 평소대로 AI가 판단한다.
    """
    if not getattr(settings, "AI_SEARCH_ROUTE_CATEGORY_REQUESTS", True):
        return []
    if _as_list(frame.get("exclusions")):
        return []
    for constraint in _frame_terms(frame, "constraints"):
        if _compact(constraint) not in NON_DISCRIMINATING_CONSTRAINTS:
            return []

    terms = _frame_terms(frame, "target_objects", "result_match_terms", "candidate_place_types")
    if not terms:
        return []

    matched = set()
    for term in terms:
        categories = get_matching_categories(_clean_text(term, 80))
        if not categories:
            # 카테고리로 떨어지지 않는 표현이 있으면 의미 판단이 필요한 요청이다.
            return []
        matched.update(categories)

    if not matched or not matched.issubset(DETERMINISTIC_CATEGORY_CODES):
        return []
    return sorted(matched)


def _deterministic_ranked_candidates(evidence_candidates, category_codes, *, limit=15):
    """
    AI 호출 없이 후보를 가까운 순으로 정리한다.

    후보 집합은 AI가 평가했을 집합(`evidence_candidates`)을 그대로 쓴다.
    걸러내는 기준을 새로 만들지 않고 순서만 거리순으로 정한다.
    """
    codes = list(category_codes or [])
    category_label = get_category_display_name(codes[0]) if len(codes) == 1 else ""
    ranked = []
    for candidate in evidence_candidates or []:
        if not _clean_text(candidate.get("id")):
            continue
        if _blocking_unmet_constraints(candidate):
            continue
        distance = candidate.get("distance")
        if distance is None:
            distance = candidate.get("distance_m")
        place_label = category_label or "장소"
        if distance is None:
            reason = f"요청하신 {place_label} 후보예요."
        else:
            reason = f"기준 위치에서 약 {int(round(float(distance)))}m 거리의 {place_label}이에요."
        ranked.append({
            **candidate,
            "semantic_reason": reason,
            "recommendation_reason": reason,
            "recommend_reason": reason,
            "evidence_level": "medium",
            "frame_evidence_tier": "medium",
            "verification_required": False,
            "compatibility_gate": "passed",
            "compatibility_gate_reason": "",
            "unified_ranker_applied": True,
            "deterministic_category_match": True,
        })

    ranked.sort(key=lambda candidate: (
        candidate.get("distance") if candidate.get("distance") is not None else 999999999,
        {"strong": 0, "medium": 1, "weak": 2}.get(candidate.get("pre_ai_evidence_level"), 9),
        str(candidate.get("id")),
    ))
    ranked = ranked[:max(_as_int(limit, 15), 1)]
    return [
        {**candidate, "backend_rank": index + 1, "unified_rank": index + 1}
        for index, candidate in enumerate(ranked)
    ]


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
        if not candidate_id or candidate_id in ranked_ids:
            continue
        if _blocking_unmet_constraints(candidate):
            continue
        if candidate_id in excluded_ids and not _can_top_up_excluded_candidate(candidate):
            continue
        level = _clean_text(candidate.get("pre_ai_evidence_level") or candidate.get("evidence_level"))
        if level not in {"strong", "medium"}:
            continue
        matched_evidence = candidate.get("matched_evidence") if isinstance(candidate.get("matched_evidence"), list) else []
        if matched_evidence and all(item.get("type") == "retrieval_query_target" for item in matched_evidence if isinstance(item, dict)):
            continue
        evidence_level = "medium" if level == "strong" else level
        reason = "요청 조건과 맞아 보이는 후보예요. 세부 정보는 방문 전에 확인해 주세요."
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


def _candidate_debug_sample(candidates, *, source=None, limit=5):
    sample = []
    for candidate in candidates or []:
        if source and candidate.get("candidate_source") != source:
            continue
        matched_evidence = candidate.get("matched_evidence") if isinstance(candidate.get("matched_evidence"), list) else []
        sample.append({
            "id": candidate.get("id"),
            "name": candidate.get("name"),
            "source": candidate.get("candidate_source"),
            "category": candidate.get("category"),
            "retrieval_query": candidate.get("retrieval_query"),
            "pre_ai_evidence_level": candidate.get("pre_ai_evidence_level"),
            "policy_matched_constraints": candidate.get("policy_matched_constraints") or [],
            "pre_ai_unmet_constraints": candidate.get("pre_ai_unmet_constraints") or [],
            "policy_verification_needed": candidate.get("policy_verification_needed") or [],
            "matched_evidence": matched_evidence[:5],
        })
        if len(sample) >= limit:
            break
    return sample


def _search_origin_debug(frame, location_resolution, top_results):
    location_resolution = location_resolution if isinstance(location_resolution, dict) else {}
    markers = _markers(top_results)
    return {
        "location_mode": frame.get("location_mode"),
        "search_lat": location_resolution.get("lat"),
        "search_lng": location_resolution.get("lng"),
        "source": location_resolution.get("source") or location_resolution.get("reason") or "",
        "label": location_resolution.get("label") or "",
        "marker_count": len(markers),
        "marker_sources": list(dict.fromkeys(marker.get("source") for marker in markers if marker.get("source"))),
    }


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
    candidate_pool=None,
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
        "ai_call_failed": (
            intent_plan.get("decision_action") == "ai_unavailable"
            or bool((reranker_debug or {}).get("ranking_fallback_applied"))
        ),
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
        "search_origin": _search_origin_debug(
            frame,
            location_resolution or {"status": "skipped", "reason": ""},
            top_results,
        ),
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
                "category": result.get("category"),
                "retrieval_query": result.get("retrieval_query"),
                "semantic_score": result.get("semantic_score"),
                "evidence_level": result.get("evidence_level"),
                "matched_evidence": (
                    result.get("matched_evidence")[:6]
                    if isinstance(result.get("matched_evidence"), list)
                    else []
                ),
                "semantic_decision": (result.get("semantic_reranker") or {}).get("decision"),
                "semantic_unmet_constraints": (result.get("semantic_reranker") or {}).get("unmet_constraints") or [],
                "reason": result.get("semantic_reason"),
            }
            for result in top_results[:15]
        ],
        "candidate_samples": {
            "db": _candidate_debug_sample(candidate_pool, source="db"),
            "kakao": _candidate_debug_sample(candidate_pool, source="kakao"),
            "web": _candidate_debug_sample(candidate_pool, source="web"),
        },
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
    frame = _normalize_current_context_anchor_frame(
        intent_plan.get("frame") if isinstance(intent_plan.get("frame"), dict) else {}
    )
    if frame is not intent_plan.get("frame"):
        intent_plan = {**intent_plan, "frame": frame}
    search_plan = to_search_plan(intent_plan, raw_query=original_query or query)

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
    context_source = _context_coordinate_source(lat=lat, lng=lng, map_center=map_center)
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
    location_resolution = {
        "status": "resolved",
        "reason": "current_context",
        "lat": search_lat,
        "lng": search_lng,
        "label": "current_context",
        "source": context_source or "current_context",
    }
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

    radius = _search_radius_for_frame(radius, frame, original_query or query)

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

    min_strong_medium_candidates = _as_int(
        getattr(settings, "AI_SEARCH_MIN_STRONG_MEDIUM_CANDIDATES", 3),
        3,
    )
    query_repair_debug = {"status": "skipped"}
    should_repair_queries = (
        min_strong_medium_candidates > 0
        and (
            not initial_candidates
            or _query_needs_repair(primary_queries)
        )
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
    should_collect_web = external_verification_requested
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
    invalid_display_candidates = [
        candidate
        for candidate in candidate_pool
        if _candidate_has_invalid_display(candidate)
    ]
    if invalid_display_candidates:
        invalid_display_ids = {
            _clean_text(candidate.get("id"))
            for candidate in invalid_display_candidates
            if _clean_text(candidate.get("id"))
        }
        candidate_pool = [
            candidate
            for candidate in candidate_pool
            if _clean_text(candidate.get("id")) not in invalid_display_ids
        ]
        candidate_counts["removed_invalid_display"] = len(invalid_display_candidates)
    retrieval_only_candidates = [
        candidate
        for candidate in candidate_pool
        if _has_only_retrieval_query_evidence(candidate)
    ]
    all_candidates = [
        candidate
        for candidate in candidate_pool
        if not _has_only_retrieval_query_evidence(candidate)
        and (
            candidate.get("pre_ai_evidence_level") != "weak"
            or candidate.get("matched_evidence")
        )
    ]
    # 축약 전 근거 통과 후보. 카테고리 라우팅은 AI 평가와 같은 집합에서 고른다.
    evidence_candidates = list(all_candidates)
    pre_rerank_limit = _as_int(getattr(settings, "AI_SEARCH_RERANK_MAX_CANDIDATES", 20), 20)
    pre_rerank_limit = min(max(pre_rerank_limit, 5), 30)
    all_candidates = _balanced_rerank_shortlist(all_candidates, pre_rerank_limit)

    ranking_policy = frame.get("ranking_policy") or "evidence_first"
    # 카테고리 + 거리로 답이 정해지는 요청은 AI 후보 평가를 건너뛴다.
    # 평가해도 순서가 그대로라서 응답 시간과 토큰만 쓰게 된다.
    deterministic_codes = _deterministic_category_codes(frame)
    deterministic_results = (
        _deterministic_ranked_candidates(evidence_candidates, deterministic_codes, limit=limit)
        if deterministic_codes
        else []
    )

    if deterministic_results:
        ranked_candidates = deterministic_results
        reranker_debug = {
            "status": "skipped",
            "reason": "deterministic_category_request",
            "input_count": len(candidate_pool),
            "included_count": len(deterministic_results),
            "excluded_count": 0,
            "excluded_candidates": [],
            "deterministic_category_codes": deterministic_codes,
            "call_count": 0,
        }
        timings["reranker_latency_ms"] = 0.0
    elif all_candidates:
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
        skipped_reason = "no_candidates_collected"
        if candidate_pool and retrieval_only_candidates and len(retrieval_only_candidates) == len(candidate_pool):
            skipped_reason = "only_retrieval_query_evidence"
        ranked_candidates = []
        reranker_debug = {
            "status": "skipped",
            "reason": skipped_reason,
            "input_count": len(candidate_pool),
            "included_count": 0,
            "excluded_count": 0,
            "excluded_candidates": [],
        }

    reranker_available = reranker_debug.get("status") in {
        "executed",
        "partial_executed",
        "degraded_success",
        "skipped",
    }
    ranking_fallback_candidates = []
    if not reranker_available:
        # AI 후보 평가가 실패해도 수집한 후보를 버리지 않고 사전 근거/거리 순서로 보여준다.
        ranking_fallback_candidates, _ = _top_up_ranked_candidates(
            [],
            candidate_pool,
            [],
            limit=limit,
        )

    if not reranker_available and not ranking_fallback_candidates:
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
        data["debug_pipeline"]["search_origin"] = _search_origin_debug(frame, location_resolution, [])
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

    if ranking_fallback_candidates:
        ranked_candidates = ranking_fallback_candidates
        reranker_debug = {
            **reranker_debug,
            "ranking_fallback_applied": True,
            "ranking_fallback_count": len(ranking_fallback_candidates),
        }

    hidden_weak = reranker_debug.get("excluded_candidates") or []
    unresolved_candidates = reranker_debug.get("unresolved_candidates") or []
    policy_conflict_candidates = [
        candidate
        for candidate in ranked_candidates or []
        if _blocking_unmet_constraints(candidate)
    ]
    if policy_conflict_candidates:
        policy_conflict_ids = {_clean_text(candidate.get("id")) for candidate in policy_conflict_candidates}
        ranked_candidates = [
            candidate
            for candidate in ranked_candidates
            if _clean_text(candidate.get("id")) not in policy_conflict_ids
        ]
        hidden_weak = [*hidden_weak, *policy_conflict_candidates]
        reranker_debug = {
            **reranker_debug,
            "post_filter_policy_conflict_count": len(policy_conflict_candidates),
            "post_filter_policy_conflict_ids": [
                candidate.get("id")
                for candidate in policy_conflict_candidates
            ],
        }
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
        candidate_pool=candidate_pool,
        location_resolution=location_resolution,
        fallback_used=(
            query_repair_debug.get("status") == "executed"
            or bool(ranking_fallback_candidates)
        ),
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
