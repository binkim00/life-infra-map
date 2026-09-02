import json
import logging
import math
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.db.models.fields.json import KeyTextTransform

from recommendations.models import Place
from recommendations.services.ai_candidate_reranker import _hybrid_score, semantic_rerank_candidates
from recommendations.services.ai_intent_planner import (
    build_ai_intent_plan,
    repair_search_queries,
    to_search_plan,
)
from recommendations.services.ai_web_search_provider import (
    get_ai_web_search_result,
    get_ai_web_search_status,
)
from recommendations.services.area_gazetteer import (
    resolve_area_coordinates,
    resolve_area_coordinates_by_token,
)
from recommendations.services.kakao_local import search_places_by_keyword
from recommendations.services.map_search import get_matching_categories, supports_postgis
from recommendations.services.place_urls import get_kakao_place_url
from recommendations.services.smoking_area_data import calculate_distance_m
from recommendations.services.tag_utils import get_category_display_name
from recommendations.services.semantic_retrieval import attach_semantic_scores, retrieve_semantic_places
from recommendations.services.canonical_tag_policy import canonical_tag_name
from recommendations.services.commercial_place_registry import normalize_address, normalize_name
from recommendations.services.conversation_sessions import resolve_previous_result_action
from recommendations.services.search_hard_gate import apply_common_hard_gate


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
RESTAURANT_PRIMARY_DATASETS = frozenset({"general_restaurant"})
RESTAURANT_SECONDARY_DATASETS = frozenset({"commercial_store"})
CONVENIENCE_STORE_NAME_PREFIXES = (
    "씨유", "지에스25", "세븐일레븐", "이마트24", "미니스톱", "스토리웨이",
)
NON_MEAL_RESTAURANT_NAME_TERMS = (
    "카페", "커피", "COFFEE", "CAFE", "베이커리", "제과", "도넛", "던킨",
    "파스쿠찌", "스타벅스", "투썸", "이디야", "메가MGC", "컴포즈", "빽다방",
    "할리스", "엔제리너스",
)
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


# 상호명에 지명이 우연히 들어간 가게를 기준 위치로 삼지 않기 위한 카테고리입니다.
# `서면` -> `서면손칼국수`(음식점)처럼 이름 일부만 겹치는 상업 시설을 걸러냅니다.
COMMERCIAL_ANCHOR_CATEGORY_HINTS = (
    "음식점",
    "카페",
    "술집",
    "숙박",
    "소매",
    "마트",
    "편의점",
    "의료",
    "병원",
    "약국",
    "미용",
    "부동산",
    "학원",
    "서비스,산업",
    "학교",
    "전자제품",
    "문구",
    "드럭스토어",
)
# 이 점수에 못 미치는 후보는 기준 위치로 쓰지 않습니다.
# 엉뚱한 곳을 기준으로 검색하느니 위치를 못 찾았다고 알리는 편이 낫습니다.
MIN_ANCHOR_RESOLUTION_SCORE = 25
# 카카오가 찾아준 기준점이 지명 사전 좌표에서 이만큼 떨어지면 다른 지역으로 봅니다.
# 같은 지명이 전국에 여러 개 있어서 생기는 오해석을 걸러내는 용도라 넉넉하게 둡니다.
# (`해운대 그랜드호텔`처럼 지명 안의 특정 장소는 이 안에 들어오므로 그대로 쓰입니다.)
MAX_ANCHOR_GAP_FROM_KNOWN_AREA_M = 20_000

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

    # `서면`, `광안리` 같은 통칭 지명은 카카오 검색으로 풀리지 않으므로 사전에서 먼저 해결한다.
    area = resolve_area_coordinates(anchor_location)
    if area:
        area_lat, area_lng, area_label = area
        return {
            "status": "resolved",
            "reason": "",
            "lat": area_lat,
            "lng": area_lng,
            "label": area_label,
            "source": "area_gazetteer",
            "external_id": "",
            "address": "",
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
            # 이름이 정확히 일치하지 않는데 상업 시설이면 지명이 아니라 상호명 우연 일치로 본다.
            if (
                category_key
                and name_key != anchor_key
                and not transit_match
                and not alias_match
                and any(hint in category_key for hint in COMMERCIAL_ANCHOR_CATEGORY_HINTS)
            ):
                score -= 70
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
        best = resolved_candidates[0]
        if best["score"] < MIN_ANCHOR_RESOLUTION_SCORE:
            # 점수가 낮으면 쓰지 않고 아래 지명 사전 폴백으로 내려간다.
            last_error_reason = "anchor_match_too_weak"
        else:
            selected = dict(best)
            selected.pop("score", None)
            selected.pop("name_length", None)

            # 카카오가 찾아준 곳이 지명 사전의 위치에서 너무 멀면 다른 지역을 잡은 것으로 본다.
            # `서면 맛집`이 전남 순천시 서면의 졸음쉼터로 풀리던 경우가 여기에 해당한다.
            # 사전에 없는 지명은 이 검사를 건너뛰므로 기존 동작에 영향이 없다.
            token_area = resolve_area_coordinates_by_token(anchor_location)
            if token_area:
                area_lat, area_lng, area_label = token_area
                gap = calculate_distance_m(area_lat, area_lng, selected["lat"], selected["lng"])
                if gap is not None and gap > MAX_ANCHOR_GAP_FROM_KNOWN_AREA_M:
                    return {
                        "status": "resolved",
                        "reason": "",
                        "lat": area_lat,
                        "lng": area_lng,
                        "label": area_label,
                        "source": "area_gazetteer_far_match",
                        "external_id": "",
                        "address": "",
                    }
            return selected

    # 카카오로도 못 풀었으면 지명이 다른 말과 붙어 있는지 낱말 단위로 마지막 확인을 한다.
    token_area = resolve_area_coordinates_by_token(anchor_location)
    if token_area:
        token_lat, token_lng, token_label = token_area
        return {
            "status": "resolved",
            "reason": "",
            "lat": token_lat,
            "lng": token_lng,
            "label": token_label,
            "source": "area_gazetteer_token",
            "external_id": "",
            "address": "",
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






def _semantic_feature_from_text(value):
    text = _clean_text(value, 80)
    if not text:
        return ''
    compact_text = _compact(text)
    canonical = canonical_tag_name(text) or canonical_tag_name(compact_text)
    if canonical:
        return canonical
    if "\ucf54\uc13c\ud2b8" in compact_text:
        return "\ucf54\uc13c\ud2b8\uc788\uc74c"
    return ''


def _extract_semantic_intent_markers(frame):
    compact_condition_text = _compact(" ".join(
        [
            _clean_text(item.get('label') or item.get('value') or '', 80)
            for item in (
                frame.get('structured_conditions', [])
                or frame.get('structuredConditions', [])
            )
            if isinstance(item, dict)
        ]
    ))
    matched = []
    for item in frame.get('structured_conditions', []) or frame.get('structuredConditions', []):
        if not isinstance(item, dict):
            continue
        condition_type = _clean_text(item.get('type'), 40).lower()
        condition_label = _clean_text(item.get('label') or item.get('value'), 120)
        semantic_feature = _semantic_feature_from_text(condition_label)
        if semantic_feature:
            matched.append(semantic_feature)
            continue
        if condition_type in {'situation', 'experience'}:
            matched.append(condition_type)
        elif condition_type == 'environment' and any(
            word in compact_condition_text
            for word in ('walk', 'outdoor', 'park')
        ):
            matched.append('walk')
    return list(dict.fromkeys(matched))


def _extract_semantic_features(frame):
    raw_values = [
        *_frame_terms(frame, 'target_objects', 'targetObjects'),
        *_frame_terms(frame, 'result_match_terms', 'resultMatchTerms'),
        *_frame_terms(frame, 'constraints'),
        *_frame_terms(frame, 'primary_search_queries', 'search_queries', 'searchQueries'),
    ]
    condition_values = []
    for item in frame.get('structured_conditions') or frame.get('structuredConditions') or []:
        if isinstance(item, dict) and item.get('label'):
            condition_values.append(item.get('label'))
    raw_values.extend(condition_values)

    features = []
    seen = set()
    for raw_value in raw_values:
        text = _clean_text(raw_value)
        if not text:
            continue
        compact_text = _compact(text)
        if not compact_text:
            continue
        canonical = _semantic_feature_from_text(compact_text)
        if canonical and canonical not in seen:
            features.append(canonical)
            seen.add(canonical)
            continue
        for alias in _split_specific_evidence_terms(text, frame=frame):
            alias_canonical = _semantic_feature_from_text(alias)
            if alias_canonical and alias_canonical not in seen:
                features.append(alias_canonical)
                seen.add(alias_canonical)
    return features

def _semantic_hard_conditions(frame):
    requirements = _frame_policy_requirements(frame) or {"desired": [], "excluded": []}
    return list(dict.fromkeys([*requirements.get("desired", []), *requirements.get("excluded", [])]))


def _semantic_activation_context(frame, raw_query):
    frame_text = _frame_semantic_text(frame)
    compact_query = _compact(raw_query)
    compact_frame = _compact(frame_text)
    if compact_query and compact_query not in compact_frame:
        compact_frame = f"{compact_frame} {compact_query}".strip()

    parsed_features = _extract_semantic_features(frame)
    raw_feature = _semantic_feature_from_text(raw_query)
    if raw_feature and raw_feature not in parsed_features:
        parsed_features.append(raw_feature)
    intent_markers = _extract_semantic_intent_markers(frame)
    has_multiple_semantic_signals = len(set([*parsed_features, *intent_markers])) >= 2
    category_codes = list(dict.fromkeys([
        *_direct_db_category_codes(frame),
        *_frame_category_codes(frame),
    ]))
    hard_conditions = _semantic_hard_conditions(frame)

    anchor_location = _clean_text(frame.get("anchor_location"), 100)
    location_mode = _clean_text(frame.get("location_mode") or frame.get("locationMode"))
    region = anchor_location if location_mode == "explicit" else (
        _clean_text(frame.get("location_query") or frame.get("base_location_query"), 100)
    )

    needs_semantic = bool(parsed_features or intent_markers or has_multiple_semantic_signals)
    top_up_requires_semantic_support = (
        bool(frame.get('required_features'))
        if 'required_features' in frame
        else needs_semantic
    )
    if not needs_semantic and (
        category_codes or anchor_location
        or _frame_terms(frame, "target_objects", "result_match_terms", "candidate_place_types")
    ):
        return {
            "semantic_required": False,
            "top_up_requires_semantic_support": False,
            "activation_reason": "category_or_place_reference_only",
            "parsed_features": parsed_features,
            "hard_conditions": hard_conditions,
            "category": category_codes,
            "region": region,
            "semantic_reason_flags": intent_markers,
            "query_compact": compact_query,
        }

    if parsed_features:
        if has_multiple_semantic_signals:
            reason = "composite_feature_query"
        else:
            reason = f"semantic_feature: {parsed_features[0]}"
    elif intent_markers:
        reason = f"semantic_intent: {', '.join(sorted(intent_markers))}"
    elif has_multiple_semantic_signals:
        reason = "composite_feature_query"
    else:
        reason = "no_explicit_semantic_signal"

    return {
        "semantic_required": needs_semantic,
        "top_up_requires_semantic_support": top_up_requires_semantic_support,
        "activation_reason": reason,
        "parsed_features": parsed_features,
        "hard_conditions": hard_conditions,
        "category": category_codes,
        "region": region,
        "semantic_reason_flags": intent_markers,
        "query_compact": compact_query,
    }


def _frame_category_codes(frame):
    return _frame_terms(frame, "candidate_category_codes")


def _target_consensus_category_codes(frame):
    target_terms = _frame_terms(frame, "target_objects", "targetObjects")
    matched_sets = []
    for term in target_terms:
        matched = set(get_matching_categories(term)) if term else set()
        if matched:
            matched_sets.append(matched)
    inferred_codes = set.intersection(*matched_sets) if matched_sets else set()
    return sorted(inferred_codes)


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


def _collector_direct_db_category_codes(frame):
    direct_codes = _direct_db_category_codes(frame)
    direct_text = _compact(" ".join([
        *_frame_terms(frame, "target_objects", "targetObjects"),
        *_frame_terms(frame, "result_match_terms", "resultMatchTerms"),
    ]))
    for code in _target_consensus_category_codes(frame):
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
    if group_dining_request and restaurant_request:
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
        tag_name = canonical_tag_name(tag_name) or tag_name
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
    loaded_raw = place.__dict__.get("raw")
    if isinstance(loaded_raw, dict):
        raw_text = _clean_text(json.dumps(loaded_raw, ensure_ascii=False), 500)
    else:
        raw_text = " ".join(filter(None, [
            _clean_text(getattr(place, "collect_business_type", "")),
            _clean_text(getattr(place, "collect_source_dataset", "")),
        ]))
    text_fields = {
        "name": _clean_text(place.name),
        "category": _clean_text(place.category),
        "address": _clean_text(place.address),
        "detail_location": _clean_text(place.detail_location),
        "source_name": _clean_text(place.source_name),
        "raw": raw_text,
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


def _restaurant_business_profile(place):
    """Use source business metadata to keep non-dining permits out of meal search."""
    if place.category != "restaurant":
        return {"excluded": False, "score": 0, "reason": "not_restaurant"}

    business_type = _clean_text(getattr(place, "collect_business_type", ""))
    dataset = _clean_text(getattr(place, "collect_source_dataset", "")).lower()
    name = _clean_text(place.name)
    upper_name = name.upper()
    compact_name = re.sub(r"[\s_-]+", "", upper_name)
    is_convenience_name = compact_name.startswith(("GS25", "CU")) or name.startswith(
        CONVENIENCE_STORE_NAME_PREFIXES
    )
    if "편의점" in business_type or is_convenience_name:
        return {"excluded": True, "score": -100, "reason": "convenience_store"}
    if any(term.upper() in upper_name for term in NON_MEAL_RESTAURANT_NAME_TERMS):
        return {"excluded": True, "score": -80, "reason": "non_meal_cafe_or_bakery"}

    score = 0
    reason = "generic_restaurant"
    if dataset in RESTAURANT_PRIMARY_DATASETS:
        score = 30
        reason = "general_restaurant_registry"
    elif dataset in RESTAURANT_SECONDARY_DATASETS:
        score = 20
        reason = "commercial_food_registry"
    elif "휴게음식점" in business_type:
        score = -5
        reason = "rest_food_service"
    return {"excluded": False, "score": score, "reason": reason}


def _order_by_distance(queryset, lat, lng, *, use_knn=True):
    """
    후보를 가까운 순으로 정렬한다.

    좌표가 있으면 GiST 인덱스를 타는 `ST_Distance` 로 DB 에서 정렬한다.
    좌표가 없으면 거리 정렬 자체가 불가능하므로 품질순을 쓴다.
    """
    if lat is None or lng is None or not supports_postgis():
        return queryset.order_by("-data_quality_score", "-updated_at")

    distance_sql = (
        "geog <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography"
        if use_knn
        else "ST_Distance(geog, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)"
    )
    return queryset.annotate(
        collect_distance=RawSQL(
            distance_sql,
            (lng, lat),
        ),
    ).order_by("collect_distance")


SHOPPING_VENUE_MARKERS = (
    ("롯데백화점부산본점", "롯데백화점 부산본점"),
    ("롯데백화점광복점", "롯데백화점 광복점"),
    ("롯데백화점동래점", "롯데백화점 동래점"),
    ("롯데백화점센텀시티점", "롯데백화점 센텀시티점"),
    ("신세계백화점센텀시티점", "신세계백화점 센텀시티점"),
    ("현대백화점부산점", "현대백화점 부산점"),
    ("롯데프리미엄아울렛동부산점", "롯데프리미엄아울렛 동부산점"),
    ("신세계사이먼프리미엄아울렛부산점", "신세계사이먼 프리미엄 아울렛 부산점"),
    ("애플아울렛부산점", "애플아울렛 부산점"),
    ("서면삼정타워", "서면 삼정타워"),
    ("삼정타워", "서면 삼정타워"),
    ("서면지하상가", "서면지하상가"),
    ("중부지하도상가서면몰", "서면몰"),
    ("서면몰", "서면몰"),
)


def _shopping_venue_name(raw_name):
    name_key = _compact(raw_name)
    for marker, label in SHOPPING_VENUE_MARKERS:
        if marker in name_key:
            return label
    return ""


def _collect_derived_shopping_candidates(*, lat=None, lng=None, limit=50, radius=None):
    query = Q()
    for term in [
        "백화점", "프리미엄아울렛", "애플아울렛", "삼정타워",
        "서면지하상가", "서면몰",
    ]:
        query |= Q(name__icontains=term)
    queryset = Place.objects.filter(query)
    bounds = _nearby_bounds(lat, lng, radius)
    if bounds:
        queryset = queryset.filter(
            lat__gte=bounds["lat_min"],
            lat__lte=bounds["lat_max"],
            lng__gte=bounds["lng_min"],
            lng__lte=bounds["lng_max"],
        )

    venues = {}
    scan_limit = max(_as_int(limit, 50) * 100, 1000)
    for row in queryset.values(
        "id", "name", "address", "detail_location", "lat", "lng",
    )[:scan_limit]:
        venue_name = _shopping_venue_name(row.get("name"))
        if not venue_name:
            continue
        venue_key = _compact(venue_name)
        if venue_key not in venues:
            venues[venue_key] = {
                "name": venue_name,
                "address": row.get("address") or row.get("detail_location") or "",
                "lat": row.get("lat"),
                "lng": row.get("lng"),
                "evidence_count": 0,
            }
        venues[venue_key]["evidence_count"] += 1

    candidates = []
    for venue_key, venue in venues.items():
        distance = _distance(lat, lng, venue["lat"], venue["lng"])
        candidate_id = f"shopping:{venue_key}"
        evidence_count = venue["evidence_count"]
        candidates.append({
            **_candidate_base(
                candidate_id,
                "db",
                venue["name"],
                "shopping",
                venue["address"],
                lat=venue["lat"],
                lng=venue["lng"],
                distance=distance,
            ),
            "source_name": "derived_shopping_venue",
            "derived_from_tenant_records": True,
            "venue_evidence_count": evidence_count,
            "verified_tags": ["쇼핑시설"],
            "verified_tag_labels": ["쇼핑시설"],
            "suggested_tags": [],
            "candidate_tags": [],
            "warning_tags": [],
            "matched_evidence": [{
                "type": "target_direct",
                "field": "tenant_venue_name",
                "value": "쇼핑시설",
                "source_strength": "verified",
                "evidence_count": evidence_count,
            }],
            "matched_tags": ["쇼핑시설"],
            "matched_tag_labels": ["쇼핑시설"],
            "policy_matched_constraints": [],
            "pre_ai_unmet_constraints": [],
            "policy_verification_needed": [],
            "pre_ai_evidence_level": "strong" if evidence_count >= 3 else "medium",
            "evidence_level": "strong" if evidence_count >= 3 else "medium",
            "frame_match_strength": "strong" if evidence_count >= 3 else "medium",
            "recommendation_confidence": "medium",
            "confidence": "medium",
            "confidence_label": "입점 데이터로 확인된 쇼핑시설",
            "score": min(92, 65 + evidence_count),
            "data_quality_score": min(100, 60 + evidence_count),
        })
    candidates.sort(key=lambda candidate: (
        candidate.get("distance") if candidate.get("distance") is not None else float("inf"),
        -_as_int(candidate.get("venue_evidence_count"), 0),
        _clean_text(candidate.get("name")),
    ))
    return candidates[:max(_as_int(limit, 50), 1)]


SPARSE_BEST_AVAILABLE_CATEGORY_CODES = frozenset({"shopping", "smoking_area"})
SPARSE_BEST_AVAILABLE_RADIUS = 20_000


def _merge_expanded_candidates(nearby, expanded, *, original_radius, limit):
    merged = list(nearby or [])
    seen = {_clean_text(candidate.get("id")) for candidate in merged}
    for candidate in expanded or []:
        candidate_id = _clean_text(candidate.get("id"))
        if not candidate_id or candidate_id in seen:
            continue
        merged.append({
            **candidate,
            "expanded_search": True,
            "expanded_from_radius_m": original_radius,
            "best_available_reason": "가까운 범위에 후보가 부족해 더 넓은 범위에서 찾은 차선 후보예요.",
        })
        seen.add(candidate_id)
        if len(merged) >= max(_as_int(limit, 50), 1):
            break
    return merged


def collect_db_candidates(
    frame,
    *,
    lat=None,
    lng=None,
    limit=50,
    radius=None,
    _allow_sparse_expansion=True,
):
    terms = _db_evidence_terms(frame)
    search_terms = terms["search"]
    db_first_category_codes = _db_first_category_codes(frame)
    direct_category_codes = _collector_direct_db_category_codes(frame)
    restaurant_search = "restaurant" in direct_category_codes
    if "shopping" in direct_category_codes:
        resolved_radius = _radius(radius)
        derived = _collect_derived_shopping_candidates(
            lat=lat,
            lng=lng,
            limit=limit,
            radius=resolved_radius,
        )
        minimum = min(5, max(_as_int(limit, 50), 1))
        if (
            _allow_sparse_expansion
            and len(derived) < minimum
            and resolved_radius < SPARSE_BEST_AVAILABLE_RADIUS
        ):
            expanded = _collect_derived_shopping_candidates(
                lat=lat,
                lng=lng,
                limit=limit,
                radius=SPARSE_BEST_AVAILABLE_RADIUS,
            )
            derived = _merge_expanded_candidates(
                derived,
                expanded,
                original_radius=resolved_radius,
                limit=limit,
            )
        if derived:
            return derived
    if not search_terms and not db_first_category_codes and not direct_category_codes:
        return []

    if direct_category_codes:
        # The requested category is already a deterministic constraint. An OR
        # against PlaceTag evidence here forces a wide DISTINCT join before the
        # spatial/category cut, while tag suitability is evaluated below from
        # the prefetched PlaceTags. Keep the candidate universe category-safe.
        query = Q(category__in=direct_category_codes)
        # 일부 공공 원천은 실제 약국을 tourism/freewifi 등으로 잘못 분류한다.
        # 상호에 '약국'이 명시된 경우만 신뢰해 실체 카테고리를 복구한다.
        if "pharmacy" in direct_category_codes:
            query |= Q(name__icontains="약국")
    else:
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

    radius = _radius(radius)
    bounds = _nearby_bounds(lat, lng, radius)
    queryset = Place.objects.filter(query)
    # Direct category lookup has no multiplying join, so DISTINCT only forces a
    # wide sort of Place.raw. Lexical lookup still joins PlaceTag and needs it.
    if not direct_category_codes:
        queryset = queryset.distinct()
    if bounds:
        queryset = queryset.filter(
            lat__gte=bounds["lat_min"],
            lat__lte=bounds["lat_max"],
            lng__gte=bounds["lng_min"],
            lng__lte=bounds["lng_max"],
        )

    candidate_limit = max(limit * 3, 100)
    # Exact category searches do not need a five-times-wide hydrated Place
    # window: non-restaurant rows are neither business-profile filtered nor
    # evidence-sorted before the final slice. Keep a small margin for the
    # rectangular bounds versus the exact radius, while avoiding decoding the
    # large raw JSON field and prefetching tags for rows that can never surface.
    if direct_category_codes and not restaurant_search and "pharmacy" not in direct_category_codes:
        candidate_limit = max(math.ceil(limit * 4 / 3), 60)
        if _result_diversity_enabled(frame):
            # Dense department-store tenant records can otherwise consume the
            # entire nearest window before other buildings are hydrated.
            candidate_limit = max(limit * 4, 180)

    def detail_queryset(queryset):
        return queryset.annotate(
            collect_business_type=KeyTextTransform("business_type", "raw"),
            collect_source_dataset=KeyTextTransform("dataset", "raw"),
            collect_kakao_place_url=KeyTextTransform("kakao_place_url", "raw"),
            collect_kakao_url=KeyTextTransform("kakao_url", "raw"),
            collect_place_url=KeyTextTransform("place_url", "raw"),
            collect_detail_url=KeyTextTransform("detail_url", "raw"),
        ).defer("raw")

    if direct_category_codes and bounds and lat is not None and lng is not None:
        if supports_postgis():
            # The production table contains more than a million rows. Exact
            # COUNT probes and category-filtered geography KNN both become
            # multi-second scans as the dataset grows. The rectangular bounds
            # are already covered by the (category, lat, lng) index, so sort
            # only that bounded set with an equirectangular approximation and
            # hydrate the small result window. Exact haversine distance and
            # radius filtering are still applied below.
            lng_scale = math.cos(math.radians(float(lat)))
            candidate_places = detail_queryset(queryset).annotate(
                collect_bounded_distance=RawSQL(
                    "POWER(lat - %s, 2) + POWER((lng - %s) * %s, 2)",
                    (lat, lng, lng_scale),
                ),
            ).order_by("collect_bounded_distance").prefetch_related(
                "place_tags__tag",
            )[:candidate_limit]
        else:
            # SQLite/local tests have no PostGIS expressions. Read only the
            # coordinates and preserve exact nearest-N selection in Python.
            coordinate_rows = list(queryset.values_list("id", "lat", "lng"))
            coordinate_rows.sort(
                key=lambda row: _distance(lat, lng, row[1], row[2])
                if row[1] is not None and row[2] is not None else float("inf")
            )
            candidate_coordinate_rows = coordinate_rows[:candidate_limit]
            candidate_ids = [row[0] for row in candidate_coordinate_rows]
            slim_rows_by_id = {
                row[0]: row
                for row in Place.objects.filter(id__in=candidate_ids).values_list(
                    "id", "address", "detail_location", "name", "data_quality_score",
                )
            }
            candidate_rows = [
                (
                    row[0], row[1], row[2],
                    slim_rows_by_id[row[0]][1], slim_rows_by_id[row[0]][2],
                    slim_rows_by_id[row[0]][3], slim_rows_by_id[row[0]][4],
                )
                for row in candidate_coordinate_rows
                if row[0] in slim_rows_by_id
            ]
            hydration_rows = candidate_rows
            if _result_diversity_enabled(frame) and len(candidate_rows) > max(limit * 2, 90):
                nearest_count = min(len(candidate_rows), max(limit, 60))
                quality_count = min(len(candidate_rows), max(math.ceil(limit / 2), 20))
                quality_rows = sorted(
                    candidate_rows,
                    key=lambda row: -_as_int(row[6], 0),
                )[:quality_count]
                slim_candidates = [{
                    "id": f"db:{row[0]}",
                    "name": row[5],
                    "address": row[3] or row[4] or "",
                    "category": direct_category_codes[0] if len(direct_category_codes) == 1 else "",
                } for row in candidate_rows]
                diverse_ids = {
                    _as_int(_clean_text(candidate.get("id")).split(":")[-1], 0)
                    for candidate in _balance_candidate_pool_for_diversity(
                        slim_candidates,
                        frame,
                        limit=limit,
                    )
                }
                hydration_ids = {
                    *(row[0] for row in candidate_rows[:nearest_count]),
                    *(row[0] for row in quality_rows),
                    *diverse_ids,
                }
                hydration_rows = [
                    row for row in candidate_rows if row[0] in hydration_ids
                ]
            ordered_ids = [row[0] for row in hydration_rows]
            places_by_id = {
                place.id: place
                for place in detail_queryset(
                    Place.objects.filter(id__in=ordered_ids)
                ).prefetch_related("place_tags__tag")
            }
            candidate_places = [places_by_id[place_id] for place_id in ordered_ids if place_id in places_by_id]
    else:
        queryset = _order_by_distance(
            detail_queryset(queryset), lat, lng
        ).prefetch_related("place_tags__tag")
        candidate_places = queryset[:candidate_limit]

    from recommendations.services.place_evidence_completeness import quality_profiles_for_places

    candidate_places = list(candidate_places)
    evidence_quality_profiles = quality_profiles_for_places(candidate_places)
    candidates = []
    for place in candidate_places:
        distance = _distance(lat, lng, place.lat, place.lng)
        if distance is not None and distance > radius:
            continue
        business_profile = _restaurant_business_profile(place)
        if restaurant_search and business_profile["excluded"]:
            continue
        tag_lists = _db_tag_lists(place)
        evidence_quality = evidence_quality_profiles[place.id]
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
            "business_type": _clean_text(getattr(place, "collect_business_type", "")),
            "source_dataset": _clean_text(getattr(place, "collect_source_dataset", "")),
            "db_business_fit_score": business_profile["score"],
            "db_business_fit_reason": business_profile["reason"],
            "data_quality_score": place.data_quality_score,
            "place_evidence_quality": evidence_quality,
            "evidence_quality_score": evidence_quality["score"],
            "evidence_quality_level": evidence_quality["level"],
            "evidence_gaps": evidence_quality["missing_dimension_labels"],
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
    if restaurant_search:
        candidates.sort(key=lambda candidate: (
            -_as_int(candidate.get("db_business_fit_score"), 0),
            -_as_int(candidate.get("score"), 0),
            -_as_int(candidate.get("data_quality_score"), 0),
            candidate.get("distance") if candidate.get("distance") is not None else float("inf"),
            _clean_text(candidate.get("name")),
        ))
    balanced = _balance_candidate_pool_for_diversity(candidates, frame, limit=limit)
    minimum = min(5, max(_as_int(limit, 50), 1))
    if (
        _allow_sparse_expansion
        and len(balanced) < minimum
        and set(direct_category_codes).intersection(SPARSE_BEST_AVAILABLE_CATEGORY_CODES)
        and radius < SPARSE_BEST_AVAILABLE_RADIUS
    ):
        expanded = collect_db_candidates(
            frame,
            lat=lat,
            lng=lng,
            limit=limit,
            radius=SPARSE_BEST_AVAILABLE_RADIUS,
            _allow_sparse_expansion=False,
        )
        return _merge_expanded_candidates(
            balanced,
            expanded,
            original_radius=radius,
            limit=limit,
        )
    return balanced


def collect_semantic_candidates(
    query,
    frame,
    *,
    semantic_required=False,
    lat=None,
    lng=None,
    radius=None,
):
    """Build ordinary DB candidates from existing, fact-only semantic documents."""
    if not semantic_required:
        return [], {"status": "skipped", "reason": "semantic_not_required", "results": []}
    if not getattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", False):
        return [], {"status": "disabled", "results": []}
    if not getattr(settings, "SEMANTIC_CANDIDATE_INJECTION_ENABLED", False):
        return [], {"status": "injection_disabled", "results": []}
    try:
        retrieval = retrieve_semantic_places(
            query, top_k=getattr(settings, "SEMANTIC_TOP_K", 10),
        )
    except Exception as exc:  # Keep the established search path available if the optional pilot fails.
        logger.warning("semantic retrieval unavailable: %s", exc.__class__.__name__)
        return [], {
            "status": "unavailable",
            "reason": f"semantic_retrieval_failed:{exc.__class__.__name__}",
            "results": [],
        }
    radius = _radius(radius)
    # Explicit category words in the user's query are stronger than a broad or
    # mistaken local intent frame. They gate semantic-only candidates rather
    # than expanding the frame's categories.
    explicit_category_codes = _explicit_semantic_query_categories(query)
    direct_category_codes = explicit_category_codes or _direct_db_category_codes(frame)
    candidates = []
    required_feature_groups = _semantic_required_feature_groups(frame)
    for row in retrieval["results"]:
        place = row["place"]
        inferred_category = place.category
        if "pharmacy" in direct_category_codes and "약국" in _compact(place.name):
            inferred_category = "pharmacy"
        if direct_category_codes and inferred_category not in direct_category_codes:
            continue
        distance = _distance(lat, lng, place.lat, place.lng)
        if distance is not None and distance > radius:
            continue
        tag_lists = _db_tag_lists(place)
        level, matched, policy_unmet, policy_verification_needed = _db_evidence(place, tag_lists, frame)
        # Semantic similarity cannot satisfy a required structured policy.
        # UNKNOWN is safe for soft ranking, but a semantic-only candidate with
        # an unverified hard facility/time condition must not be injected.
        if policy_unmet or policy_verification_needed:
            continue
        actual_features = list(row.get("features") or [])
        if any(not (choices & set(actual_features)) for choices in required_feature_groups):
            continue
        matched = [*matched, {
            "type": "semantic_feature_document", "field": "active_features",
            "value": actual_features, "source_strength": "suggested",
            "document_id": row.get("document_id"),
        }]
        level = "medium" if level == "weak" else level
        candidate = {
            **_candidate_base(
                f"db:{place.id}", "db", place.name, inferred_category,
                place.address or place.detail_location, lat=place.lat, lng=place.lng, distance=distance,
            ),
            "place_id": place.id, "external_id": place.external_id,
            "source_name": place.source_name, "kakao_place_url": get_kakao_place_url(place),
            "place_url": get_kakao_place_url(place), "verified_tags": tag_lists["verified"],
            "verified_tag_labels": tag_lists["verified"], "suggested_tags": tag_lists["suggested"],
            "suggested_tag_labels": tag_lists["suggested"], "candidate_tags": tag_lists["candidate"],
            "candidate_tag_labels": tag_lists["candidate"], "warning_tags": tag_lists["warning"],
            "matched_evidence": matched, "matched_tags": actual_features,
            "matched_tag_labels": actual_features, "policy_matched_constraints": [
                item["value"] for item in matched if item.get("type") == "policy_constraint"
            ],
            "pre_ai_unmet_constraints": [],
            "policy_verification_needed": policy_verification_needed,
            "pre_ai_evidence_level": level, "evidence_level": level, "frame_match_strength": level,
            "recommendation_confidence": "high" if level == "strong" else "medium",
            "confidence": "high" if level == "strong" else "medium",
            "score": 80 if level == "strong" else 55,
            "retrieval_semantic_score": row["semantic_score"],
            "retrieval_semantic_features": actual_features,
            "retrieval_semantic_document_id": row.get("document_id"),
            "semantic_document": row["document"],
            "score_breakdown": {"collector": "semantic", "semantic_similarity": row["semantic_similarity"]},
        }
        if inferred_category != place.category:
            candidate["source_category"] = place.category
            candidate["category_identity_inferred"] = True
        candidates.append(candidate)
        if len(candidates) >= int(getattr(settings, "SEMANTIC_CANDIDATE_LIMIT", 5)):
            break
    retrieval["status"] = "executed"
    retrieval["injected_count"] = len(candidates)
    return candidates, retrieval



def _semantic_required_feature_groups(frame):
    """Map explicit required conditions to existing canonical facts only."""
    values = [*_frame_terms(frame, 'constraints')]
    for condition in frame.get('structured_conditions', []) or frame.get('structuredConditions', []) or []:
        if isinstance(condition, dict) and condition.get('required'):
            condition_value = condition.get('label') or condition.get('value')
            if condition_value:
                values.append(condition_value)
    groups = []
    seen = set()
    for value in values:
        compact = _compact(value)
        if not compact:
            continue
        canonical = canonical_tag_name(compact)
        if canonical and canonical not in seen:
            groups.append({canonical})
            seen.add(canonical)
            continue
        for alias in _split_specific_evidence_terms(value, frame=frame):
            canonical = canonical_tag_name(_compact(alias))
            if canonical and canonical not in seen:
                groups.append({canonical})
                seen.add(canonical)
    return groups





def _explicit_semantic_query_categories(query):
    """Conservative lexical category gates for semantic-only candidates."""
    text = _compact(query)
    if any(
        term in text
        for term in (
            "cafe",
            "coffee",
            "카페",
            "커피",
        )
    ):
        return ['cafe']
    if any(
        term in text
        for term in (
            "restaurant",
            "food",
            "식당",
            "음식점",
            "밥",
            "혼밥",
        )
    ):
        return ['restaurant']
    if any(term in text for term in ('tourism', 'tour', 'sight', '관광', '관광지')):
        return ['tourism']
    if 'park' in text or '공원' in text:
        return ['city_park']
    if 'library' in text or '도서관' in text:
        return ['library']
    if 'parking' in text or '주차' in text:
        return ['parking']
    if 'toilet' in text or '화장실' in text:
        return ['toilet']
    if 'shelter' in text or '대피소' in text or '쉼터' in text:
        return ['shelter']
    return []

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


def _same_place_identity(left, right):
    left_name = normalize_name(left.get('name'))
    right_name = normalize_name(right.get('name'))
    if not left_name or left_name != right_name:
        return False

    left_address = normalize_address(left.get('address') or left.get('detail_location'))
    right_address = normalize_address(right.get('address') or right.get('detail_location'))
    if left_address and left_address == right_address:
        return True

    left_lat = _as_float(left.get('lat'))
    left_lng = _as_float(left.get('lng'))
    right_lat = _as_float(right.get('lat'))
    right_lng = _as_float(right.get('lng'))
    if None in {left_lat, left_lng, right_lat, right_lng}:
        return False
    return calculate_distance_m(left_lat, left_lng, right_lat, right_lng) <= 30


def _merge_duplicate_candidate(primary, duplicate):
    merged = {**primary}
    list_fields = {
        'verified_tags', 'verified_tag_labels', 'suggested_tags',
        'suggested_tag_labels', 'candidate_tags', 'candidate_tag_labels',
        'warning_tags', 'matched_tags', 'matched_tag_labels',
        'policy_matched_constraints', 'pre_ai_unmet_constraints',
        'policy_verification_needed',
    }
    for field in list_fields:
        merged[field] = list(dict.fromkeys([
            *_as_list(primary.get(field), max_items=100),
            *_as_list(duplicate.get(field), max_items=100),
        ]))

    matched_evidence = []
    seen_evidence = set()
    for item in [
        *(primary.get('matched_evidence') or []),
        *(duplicate.get('matched_evidence') or []),
    ]:
        if not isinstance(item, dict):
            continue
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen_evidence:
            continue
        seen_evidence.add(key)
        matched_evidence.append(item)
    merged['matched_evidence'] = matched_evidence

    for field in ('kakao_place_url', 'place_url', 'external_url'):
        if not _clean_text(merged.get(field)) and _clean_text(duplicate.get(field)):
            merged[field] = duplicate[field]
    merged['duplicate_count'] = int(primary.get('duplicate_count') or 1) + int(
        duplicate.get('duplicate_count') or 1
    )
    merged['duplicate_candidate_ids'] = list(dict.fromkeys([
        *_as_list(primary.get('duplicate_candidate_ids'), max_items=100),
        _clean_text(duplicate.get('id')),
        *_as_list(duplicate.get('duplicate_candidate_ids'), max_items=100),
    ]))
    return merged


def _dedupe_candidates(candidates):
    seen_external_ids = set()
    deduped = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        external_id = _clean_text(candidate.get("external_id"))
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(deduped)
                if _same_place_identity(existing, candidate)
            ),
            None,
        )
        if duplicate_index is not None:
            deduped[duplicate_index] = _merge_duplicate_candidate(
                deduped[duplicate_index], candidate,
            )
            continue
        if external_id and external_id in seen_external_ids:
            continue
        if external_id:
            seen_external_ids.add(external_id)
        deduped.append({**candidate, 'duplicate_count': int(candidate.get('duplicate_count') or 1)})
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


DIRECT_TARGET_GENERIC_TERMS = {
    "장소",
    "곳",
    "카페",
    "커피",
    "식당",
    "음식점",
    "맛집",
    "레스토랑",
    "분위기",
    "분위기좋음",
    "조용",
    "조용함",
    "좋은",
    "가까운",
}


def _prioritize_direct_specific_targets(candidates, frame):
    anchor_key = _compact(frame.get("anchor_location"))
    specific_terms = []
    for term in _frame_terms(frame, "target_objects", "result_match_terms"):
        term_key = _compact(term)
        if (
            len(term_key) < 2
            or term_key in DIRECT_TARGET_GENERIC_TERMS
            or (anchor_key and term_key == anchor_key)
        ):
            continue
        # "브런치 카페"처럼 대상과 업종이 붙은 표현에서도 핵심 직접 근거를 살린다.
        stripped_key = term_key
        for generic_term in ["카페", "식당", "음식점", "맛집", "레스토랑"]:
            stripped_key = stripped_key.replace(generic_term, "")
        if len(stripped_key) >= 2 and stripped_key not in DIRECT_TARGET_GENERIC_TERMS:
            specific_terms.append(stripped_key)
        elif term_key not in DIRECT_TARGET_GENERIC_TERMS:
            specific_terms.append(term_key)
    specific_terms = list(dict.fromkeys(specific_terms))
    if not specific_terms:
        return list(candidates or [])

    prioritized = sorted(
        candidates or [],
        key=lambda candidate: (
            0
            if any(
                term in _compact(" ".join([
                    _clean_text(candidate.get("name")),
                    _clean_text(candidate.get("category")),
                ]))
                for term in specific_terms
            )
            else 1,
            _as_int(candidate.get("backend_rank") or candidate.get("unified_rank"), 999),
        ),
    )
    return [
        {
            **candidate,
            "backend_rank": index + 1,
            "unified_rank": index + 1,
        }
        for index, candidate in enumerate(prioritized)
    ]


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
    unmet.extend(
        violation.get("label") or violation.get("required") or violation.get("type")
        for violation in candidate.get("hard_gate_violations") or []
        if isinstance(violation, dict)
    )
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


def _grounded_semantic_reason(candidate):
    current_features = set(candidate.get("hard_gate_active_tags") or [])
    features = [
        _clean_text(value, 50)
        for value in candidate.get("retrieval_semantic_features") or []
        if _clean_text(value, 50) and value in current_features
    ]
    if features:
        return f"{', '.join(features[:2])} 근거가 있는 후보예요."
    category = get_category_display_name(candidate.get("category")) or "장소"
    return f"요청한 지역과 {category} 분류에 맞는 후보예요."


def _semantic_hybrid_pilot_rank(candidates, *, limit=15):
    """Rank existing candidates with the configured hybrid components, without an LLM call."""
    ranked = []
    for candidate in candidates:
        if _blocking_unmet_constraints(candidate):
            continue
        decision = {
            "semantic_score": candidate.get("retrieval_semantic_score") or 0,
            "evidence_level": candidate.get("pre_ai_evidence_level") or "weak",
        }
        final_score, breakdown = _hybrid_score(candidate, decision)
        grounded_reason = _grounded_semantic_reason(candidate)
        ranked.append({
            **candidate, "score": final_score, "score_breakdown": breakdown,
            "semantic_score": breakdown["semantic_score"],
            "semantic_reason": grounded_reason,
            "recommendation_reason": grounded_reason,
            "recommend_reason": grounded_reason,
            "unified_ranker_applied": True,
        })
    ranked.sort(key=lambda row: (-row["score"], _candidate_sort_key(row)))
    return [
        {**row, "backend_rank": index + 1, "unified_rank": index + 1}
        for index, row in enumerate(ranked[:max(1, int(limit))])
    ]


SEMANTIC_SUPPORT_EVIDENCE_TYPES = {
    'verified_tag_direct',
    'suggested_tag_direct',
    'candidate_tag_direct',
    'semantic_feature_document',
    'policy_constraint',
}


def _has_semantic_support(candidate):
    return any(
        isinstance(item, dict) and item.get('type') in SEMANTIC_SUPPORT_EVIDENCE_TYPES
        for item in candidate.get('matched_evidence') or []
    )


def _cap_verification_confidence(candidates):
    capped = []
    for candidate in candidates or []:
        needs_verification = bool(candidate.get('verification_required')) or (
            candidate.get('compatibility_gate') == 'needs_verification'
        )
        if not needs_verification:
            capped.append(candidate)
            continue
        capped.append({
            **candidate,
            'confidence': 'low',
            'recommendation_confidence': 'low',
            'confidence_label': '조건 확인 필요',
        })
    return capped


def _top_up_ranked_candidates(
    ranked_candidates,
    candidate_pool,
    excluded_candidates,
    *,
    limit=15,
    semantic_required=False,
):
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
        if semantic_required and not _has_semantic_support(candidate):
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
            'confidence': 'low',
            'recommendation_confidence': 'low',
            'confidence_label': '조건 확인 필요',
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


def _feature_unknown_violations(candidate):
    return [
        violation
        for violation in candidate.get("hard_gate_violations") or []
        if isinstance(violation, dict)
        and violation.get("type") == "feature"
        and violation.get("evidence_status") == "unknown"
    ]


def _relaxable_best_available_gap(value):
    text = _clean_text(value, 160)
    if not text:
        return False
    non_relaxable_terms = [
        "제외 조건",
        "다른 정보",
        "비카페",
        "온라인 쇼핑",
        "차량 충전소",
        "주차장 후보",
        "입점 식음료",
        "일반 방문 추천 맥락과 맞지 않는",
        "술집/바 요청과 맞지 않는",
    ]
    if any(term in text for term in non_relaxable_terms):
        return False
    return "근거가 부족" in text or text.endswith("요청과 맞지 않는 후보")


def _display_gap_label(value):
    text = _clean_text(value, 120)
    text = text.replace(" 요청과 맞지 않는 후보", " 근거 확인 필요")
    text = text.replace("에 적합하다는 근거가 부족한 후보", " 적합성 확인 필요")
    return text


def _can_use_as_best_available(candidate, frame):
    """Allow only category/region-safe candidates whose missing data is unknown."""
    if not isinstance(candidate, dict) or not _clean_text(candidate.get("id")):
        return False
    violations = [
        item for item in candidate.get("hard_gate_violations") or []
        if isinstance(item, dict)
    ]
    if any(
        item.get("type") != "feature" or item.get("evidence_status") != "unknown"
        for item in violations
    ):
        return False
    pre_ai_unmet = _as_list(candidate.get("pre_ai_unmet_constraints"))
    if pre_ai_unmet and not all(
        _relaxable_best_available_gap(item) for item in pre_ai_unmet
    ):
        return False
    semantic = candidate.get("semantic_reranker") if isinstance(
        candidate.get("semantic_reranker"), dict
    ) else {}
    semantic_unmet = [
        item for item in _as_list(semantic.get("unmet_constraints"))
        if _clean_text(item) != "details_need_verification"
    ]
    if semantic_unmet and not all(
        _relaxable_best_available_gap(item) for item in semantic_unmet
    ):
        return False

    expected_categories = set(_frame_category_codes(frame))
    if expected_categories:
        actual_categories = set(get_matching_categories(candidate.get("category")))
        raw_category = _clean_text(candidate.get("category"))
        if raw_category:
            actual_categories.add(raw_category)
        if not expected_categories.intersection(actual_categories):
            return False
    return True


def _requested_result_conditions(frame):
    conditions = []
    for value in _frame_terms(frame, "constraints"):
        value = _clean_text(value, 80)
        if not value or _compact(value) in NON_DISCRIMINATING_CONSTRAINTS:
            continue
        conditions.append(value)
    return list(dict.fromkeys(conditions))[:12]


def _condition_supported(condition, values):
    condition_key = _compact(condition)
    if not condition_key:
        return False
    for value in values:
        value_key = _compact(value)
        if not value_key:
            continue
        if condition_key in value_key or value_key in condition_key:
            return True
    return False


def _candidate_result_quality(candidate, frame, *, best_available=False):
    requested = _requested_result_conditions(frame)
    hard_gate_requirements = candidate.get("hard_gate_requirements") or {}
    feature_requirements = [
        requirement
        for requirement in hard_gate_requirements.get("features") or []
        if isinstance(requirement, dict) and _clean_text(requirement.get("label"), 80)
    ]
    requested = list(dict.fromkeys([
        *requested,
        *(_clean_text(requirement.get("label"), 80) for requirement in feature_requirements),
    ]))[:12]
    raw_category = _clean_text(candidate.get("category"))
    matching_category_codes = get_matching_categories(raw_category)
    implicit_category_capabilities = set()
    if "restaurant" in matching_category_codes:
        implicit_category_capabilities.update({"식사가능", "식당", "음식점"})
    if "cafe" in matching_category_codes:
        implicit_category_capabilities.update({"음료마실수있음", "카페"})
    requested = [
        condition for condition in requested
        if _compact(condition) not in implicit_category_capabilities
    ]
    verified_values = [
        *_as_list(candidate.get("hard_gate_active_tags"), max_items=50),
        *_as_list(candidate.get("verified_tags"), max_items=50),
        *_as_list(candidate.get("policy_matched_constraints"), max_items=30),
    ]
    violated_feature_codes = {
        _clean_text(violation.get("required"), 80)
        for violation in candidate.get("hard_gate_violations") or []
        if isinstance(violation, dict) and violation.get("type") == "feature"
    }
    verified_values.extend(
        _clean_text(requirement.get("label"), 80)
        for requirement in feature_requirements
        if _clean_text(requirement.get("code"), 80) not in violated_feature_codes
    )
    provisional_values = [
        *_as_list(candidate.get("suggested_tags"), max_items=50),
        *_as_list(candidate.get("candidate_tags"), max_items=50),
    ]
    for evidence in candidate.get("matched_evidence") or []:
        if not isinstance(evidence, dict):
            continue
        value = evidence.get("value") or evidence.get("label")
        if not value:
            continue
        if evidence.get("source_strength") == "verified":
            verified_values.append(value)
        elif evidence.get("source_strength") in {"suggested", "candidate"}:
            provisional_values.append(value)

    matched = [
        condition for condition in requested
        if _condition_supported(condition, verified_values)
    ]
    unverified = [
        condition for condition in requested
        if condition not in matched and _condition_supported(condition, provisional_values)
    ]
    missing = [
        condition for condition in requested
        if condition not in matched
    ]
    missing.extend(
        _clean_text(item, 100)
        for item in _as_list(candidate.get("policy_verification_needed"), max_items=20)
        if _clean_text(item, 100)
    )
    missing.extend(
        _clean_text(item.get("label") or item.get("required"), 100)
        for item in _feature_unknown_violations(candidate)
        if _clean_text(item.get("label") or item.get("required"), 100)
    )
    missing.extend(
        _display_gap_label(item)
        for item in _as_list(candidate.get("pre_ai_unmet_constraints"), max_items=20)
        if _display_gap_label(item)
    )
    if candidate.get("expanded_search"):
        missing.append("가까운 범위 내 후보")
    missing = list(dict.fromkeys(missing))
    if best_available and not missing:
        missing = ["세부 적합성 근거"]

    if not missing and not best_available:
        tier = "all_conditions_met"
        tier_label = "모든 조건 충족"
        tier_rank = 0
    elif matched:
        tier = "partial_match"
        tier_label = "일부 조건 충족"
        tier_rank = 1
    else:
        tier = "best_available"
        tier_label = "가장 가까운 대안"
        tier_rank = 2

    category = (
        get_category_display_name(matching_category_codes[0])
        if matching_category_codes
        else get_category_display_name(raw_category)
    ) or raw_category or "장소"
    distance = candidate.get("distance")
    if distance is None:
        distance = candidate.get("distance_m")
    base_reason = f"요청한 지역의 {category} 후보예요."
    if distance is not None:
        base_reason = f"요청한 지역에서 약 {int(round(float(distance)))}m 거리의 {category} 후보예요."
    if candidate.get("derived_from_tenant_records"):
        evidence_count = _as_int(candidate.get("venue_evidence_count"), 0)
        base_reason = (
            f"입점 시설 데이터 {evidence_count}건으로 확인된 {category}이며, "
            + (
                f"요청한 지역에서 약 {int(round(float(distance)))}m 거리예요."
                if distance is not None
                else "요청한 지역의 후보예요."
            )
        )
    reason_parts = [base_reason]
    if matched:
        reason_parts.append(f"확인된 조건은 {', '.join(matched[:3])}입니다.")
    if missing:
        reason_parts.append(f"부족하거나 확인이 필요한 조건은 {', '.join(missing[:3])}입니다.")
    evidence_gaps = _as_list(candidate.get("evidence_gaps"), max_items=10)
    if evidence_gaps and candidate.get("evidence_quality_level") in {"empty", "thin"}:
        reason_parts.append(f"장소 정보가 아직 부족한 영역은 {', '.join(evidence_gaps[:3])}입니다.")
    reason = " ".join(reason_parts)

    return {
        **candidate,
        "result_tier": tier,
        "result_tier_label": tier_label,
        "condition_match_count": len(matched),
        "condition_request_count": len(requested),
        "matched_conditions": matched,
        "unverified_conditions": unverified,
        "missing_conditions": missing,
        "relaxation_applied": bool(best_available or missing),
        "best_available_fallback": bool(best_available or tier == "best_available"),
        "relaxed_conditions": missing,
        "verification_required": bool(
            candidate.get("verification_required") or missing or unverified
        ),
        "recommendation_reason": reason,
        "recommend_reason": reason,
        "semantic_reason": reason,
        "result_quality_sort_key": tier_rank,
    }


RESULT_DIVERSITY_CATEGORY_CODES = frozenset({
    "cafe",
    "restaurant",
    "shopping",
    "tourism",
})
RESULT_DIVERSITY_NEAREST_MARKERS = frozenset({
    "가장가까운",
    "제일가까운",
    "최단거리",
    "거리순",
    "긴급",
    "급함",
    "급해",
    "바로앞",
})
RESULT_DIVERSITY_FRANCHISES = (
    "스타벅스",
    "투썸플레이스",
    "메가mgc커피",
    "메가커피",
    "컴포즈커피",
    "이디야커피",
    "이디야",
    "빽다방",
    "파스쿠찌",
    "할리스",
    "엔제리너스",
    "커피빈",
    "카페베네",
    "더벤티",
    "매머드커피",
    "폴바셋",
    "탐앤탐스",
    "공차",
    "블루샥",
    "롯데리아",
    "맥도날드",
    "버거킹",
    "맘스터치",
    "서브웨이",
    "kfc",
)


def _result_building_key(candidate):
    raw_address = _clean_text(
        candidate.get("road_address")
        or candidate.get("road_address_name")
        or candidate.get("address")
        or candidate.get("detail_location"),
        300,
    )
    if not raw_address:
        return ""
    normalized = unicodedata.normalize("NFKC", raw_address).lower()
    normalized = re.sub(r"\(.*?\)", " ", normalized)
    road_match = re.search(
        r"([0-9a-z가-힣]+(?:대로|로|길))\s*(\d+(?:-\d+)?)",
        normalized,
    )
    if road_match:
        return _compact(" ".join(road_match.groups()))
    lot_match = re.search(r"([0-9a-z가-힣]+동)\s*(\d+(?:-\d+)?)", normalized)
    if lot_match:
        return _compact(" ".join(lot_match.groups()))
    return normalize_address(normalized)


def _result_franchise_key(candidate):
    name_key = normalize_name(candidate.get("name"))
    if not name_key:
        return ""
    for franchise in RESULT_DIVERSITY_FRANCHISES:
        franchise_key = normalize_name(franchise)
        if franchise_key and franchise_key in name_key:
            return franchise_key
    return ""


def _result_diversity_enabled(frame):
    category_codes = set([
        *_frame_category_codes(frame),
        *_target_consensus_category_codes(frame),
    ])
    if not category_codes.intersection(RESULT_DIVERSITY_CATEGORY_CODES):
        return False
    request_text = _compact(" ".join([
        *_frame_terms(frame, "constraints"),
        *_frame_terms(frame, "result_match_terms", "resultMatchTerms"),
    ]))
    return not any(marker in request_text for marker in RESULT_DIVERSITY_NEAREST_MARKERS)


def _balance_candidate_pool_for_diversity(candidates, frame, *, limit):
    """Keep dense tenant datasets from crowding all other buildings out."""
    ordered = list(candidates or [])
    limit = max(_as_int(limit, 50), 1)
    if not _result_diversity_enabled(frame):
        return ordered[:limit]

    selected = []
    selected_object_ids = set()
    building_counts = {}
    franchise_counts = {}
    requested_conditions = _requested_result_conditions(frame)

    def has_verified_requested_support(candidate):
        if not requested_conditions:
            return False
        verified_values = [
            *_as_list(candidate.get("verified_tags"), max_items=50),
            *_as_list(candidate.get("verified_tag_labels"), max_items=50),
        ]
        verified_values.extend(
            evidence.get("value") or evidence.get("label")
            for evidence in candidate.get("matched_evidence") or []
            if isinstance(evidence, dict)
            and evidence.get("source_strength") == "verified"
        )
        return any(
            _condition_supported(condition, verified_values)
            for condition in requested_conditions
        )

    # Evidence that directly answers the user's request is stronger than the
    # diversity preference and must remain available to the hard gate/ranker.
    for candidate in ordered:
        if not has_verified_requested_support(candidate):
            continue
        selected.append(candidate)
        selected_object_ids.add(id(candidate))
        building_key = _result_building_key(candidate)
        franchise_key = _result_franchise_key(candidate)
        if building_key:
            building_counts[building_key] = building_counts.get(building_key, 0) + 1
        if franchise_key:
            franchise_counts[franchise_key] = franchise_counts.get(franchise_key, 0) + 1
        if len(selected) >= limit:
            return selected

    for building_cap, franchise_cap in ((2, 4), (5, 8), (None, None)):
        for candidate in ordered:
            if id(candidate) in selected_object_ids:
                continue
            building_key = _result_building_key(candidate)
            franchise_key = _result_franchise_key(candidate)
            if (
                building_cap is not None
                and building_key
                and building_counts.get(building_key, 0) >= building_cap
            ):
                continue
            if (
                franchise_cap is not None
                and franchise_key
                and franchise_counts.get(franchise_key, 0) >= franchise_cap
            ):
                continue
            selected.append(candidate)
            selected_object_ids.add(id(candidate))
            if building_key:
                building_counts[building_key] = building_counts.get(building_key, 0) + 1
            if franchise_key:
                franchise_counts[franchise_key] = franchise_counts.get(franchise_key, 0) + 1
            if len(selected) >= limit:
                return selected
    return selected


def _diversify_ordered_results(candidates, frame, *, limit):
    """Promote distinct buildings and brands without crossing quality strata."""
    ordered = list(candidates or [])
    top_window = min(max(_as_int(limit, 15), 1), 5, len(ordered))
    if top_window < 3 or not _result_diversity_enabled(frame):
        return ordered

    strata = []
    for candidate in ordered:
        key = (
            _as_int(candidate.get("result_quality_sort_key"), 9),
            _as_int(candidate.get("condition_match_count"), 0),
        )
        if not strata or strata[-1][0] != key:
            strata.append((key, []))
        strata[-1][1].append(candidate)

    selected = []
    building_counts = {}
    franchise_counts = {}
    for _, stratum in strata:
        remaining = list(stratum)
        while remaining and len(selected) < top_window:
            chosen_index = next((
                index
                for index, candidate in enumerate(remaining)
                if (
                    not _result_building_key(candidate)
                    or building_counts.get(_result_building_key(candidate), 0) < 1
                )
                and (
                    not _result_franchise_key(candidate)
                    or franchise_counts.get(_result_franchise_key(candidate), 0) < 2
                )
            ), None)
            if chosen_index is None:
                chosen_index = next((
                    index
                    for index, candidate in enumerate(remaining)
                    if (
                        not _result_building_key(candidate)
                        or building_counts.get(_result_building_key(candidate), 0) < 2
                    )
                    and (
                        not _result_franchise_key(candidate)
                        or franchise_counts.get(_result_franchise_key(candidate), 0) < 3
                    )
                ), 0)
            candidate = remaining.pop(chosen_index)
            selected.append(candidate)
            building_key = _result_building_key(candidate)
            franchise_key = _result_franchise_key(candidate)
            if building_key:
                building_counts[building_key] = building_counts.get(building_key, 0) + 1
            if franchise_key:
                franchise_counts[franchise_key] = franchise_counts.get(franchise_key, 0) + 1
            if len(selected) >= top_window:
                selected_object_ids = {id(item) for item in selected}
                return [
                    *selected,
                    *(item for item in ordered if id(item) not in selected_object_ids),
                ]
    selected_object_ids = {id(item) for item in selected}
    return [*selected, *(item for item in ordered if id(item) not in selected_object_ids)]


def _result_diversity_summary(candidates, frame):
    top_results = list(candidates or [])[:5]
    building_counts = {}
    franchise_counts = {}
    for candidate in top_results:
        building_key = _result_building_key(candidate)
        franchise_key = _result_franchise_key(candidate)
        if building_key:
            building_counts[building_key] = building_counts.get(building_key, 0) + 1
        if franchise_key:
            franchise_counts[franchise_key] = franchise_counts.get(franchise_key, 0) + 1
    return {
        "enabled": _result_diversity_enabled(frame),
        "window_count": len(top_results),
        "unique_building_count": len(building_counts),
        "same_building_max_count": max(building_counts.values(), default=0),
        "unique_franchise_count": len(franchise_counts),
        "same_franchise_max_count": max(franchise_counts.values(), default=0),
    }


def _complete_and_order_results(
    ranked_candidates,
    candidate_pool,
    feature_removed_candidates,
    excluded_candidates,
    frame,
    *,
    limit,
):
    """Keep strict matches first, then fill the requested window with honest alternatives."""
    limit = max(_as_int(limit, 15), 1)
    strict = list(ranked_candidates or [])
    strict_ids = {
        _clean_text(candidate.get("id"))
        for candidate in strict
        if _clean_text(candidate.get("id"))
    }
    excluded_ids = {
        _clean_text(candidate.get("id"))
        for candidate in excluded_candidates or []
        if _clean_text(candidate.get("id"))
    }
    additions = []
    seen_ids = set(strict_ids)
    pools = [
        list(candidate_pool or []),
        list(feature_removed_candidates or []),
    ]
    for pool in pools:
        for candidate in sorted(pool, key=_candidate_sort_key):
            candidate_id = _clean_text(candidate.get("id"))
            if not candidate_id or candidate_id in seen_ids:
                continue
            if candidate_id in excluded_ids and not _can_top_up_excluded_candidate(candidate):
                continue
            if not _can_use_as_best_available(candidate, frame):
                continue
            additions.append({
                **candidate,
                "confidence": "low",
                "recommendation_confidence": "low",
                "confidence_label": "조건 확인 필요",
                "compatibility_gate": "needs_verification",
                "compatibility_gate_reason": "best_available_missing_evidence",
                "best_available_fallback": True,
            })
            seen_ids.add(candidate_id)
            if len(strict) + len(additions) >= limit:
                break
        if len(strict) + len(additions) >= limit:
            break

    decorated = [
        _candidate_result_quality(candidate, frame, best_available=False)
        for candidate in strict
    ]
    decorated.extend(
        _candidate_result_quality(candidate, frame, best_available=True)
        for candidate in additions
    )
    decorated.sort(key=lambda candidate: (
        _as_int(candidate.get("result_quality_sort_key"), 9),
        -_as_int(candidate.get("condition_match_count"), 0),
        -_as_int(candidate.get("evidence_quality_score"), 0),
        candidate.get("distance") if candidate.get("distance") is not None else 999999999,
        {"strong": 0, "medium": 1, "weak": 2}.get(
            _clean_text(candidate.get("pre_ai_evidence_level") or candidate.get("evidence_level")),
            9,
        ),
        -_as_int(candidate.get("db_business_fit_score"), 0),
        -_as_int(candidate.get("data_quality_score"), 0),
        -float(candidate.get("score") or 0),
        _clean_text(candidate.get("name")),
    ))
    decorated = _diversify_ordered_results(decorated, frame, limit=limit)
    ordered = [
        {
            **candidate,
            "backend_rank": index + 1,
            "unified_rank": index + 1,
        }
        for index, candidate in enumerate(decorated[:limit])
    ]
    return ordered, additions


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
        semantic_activation=None,
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
            "semantic": _as_int(candidate_counts.get("semantic"), 0),
            "top_results": _as_int(candidate_counts.get("top_results"), len(top_results)),
            "hidden_weak": _as_int(candidate_counts.get("hidden_weak"), len(hidden_weak)),
            "removed_incompatible": _as_int(candidate_counts.get("removed_incompatible"), len(hidden_weak)),
            "unresolved": _as_int(candidate_counts.get("unresolved"), 0),
        },
        "semantic_activation": {
            "semantic_required": bool((semantic_activation or {}).get("semantic_required")),
            "activation_reason": (semantic_activation or {}).get("activation_reason") or "",
            "parsed_features": (semantic_activation or {}).get("parsed_features") or [],
            "hard_conditions": (semantic_activation or {}).get("hard_conditions") or [],
            "category": (semantic_activation or {}).get("category") or [],
            "region": (semantic_activation or {}).get("region") or "",
            "semantic_reason_flags": (semantic_activation or {}).get("semantic_reason_flags") or [],
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
        "intent_parsing_latency_ms": (timings or {}).get("intent_parsing_latency_ms"),
        "location_resolution_latency_ms": (timings or {}).get("location_resolution_latency_ms"),
        "db_candidate_retrieval_latency_ms": (timings or {}).get("db_candidate_retrieval_latency_ms"),
        "kakao_search_latency_ms": (timings or {}).get("kakao_search_latency_ms"),
        "evidence_tag_loading_latency_ms": (timings or {}).get("evidence_tag_loading_latency_ms"),
        "filtering_latency_ms": (timings or {}).get("filtering_latency_ms"),
        "ranking_latency_ms": (timings or {}).get("ranking_latency_ms"),
        "serialization_latency_ms": (timings or {}).get("serialization_latency_ms"),
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


def _previous_result_action_response(action_data, previous_context, timings):
    action = action_data["action"]
    results = action_data.get("results") or []
    search_plan = previous_context.get("search_plan") or {}
    frame = (
        previous_context.get("place_intent_frame")
        or search_plan.get("place_intent_frame")
        or search_plan.get("placeIntentFrame")
        or {}
    )
    if action == "reset_conversation":
        search_plan = {}
        frame = {}
    return {
        "scenario": action,
        "type": action,
        "decision_action": action,
        "decisionAction": action,
        "blocked": False,
        "can_search_now": False,
        "results": results,
        "markers": results,
        "count": len(results),
        "result_count": len(results),
        "relevant_result_count": len(results),
        "message": action_data.get("message") or "",
        "result_indexes": action_data.get("result_indexes") or [],
        "search_plan": search_plan,
        "place_intent_frame": frame,
        "execution_policy": {"run_search": False},
        "debug_pipeline": {"total_latency_ms": timings.get("total_latency_ms")},
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


def _candidate_preview_frame(request_data):
    """Build a retrieval frame from the client-side plan without calling an AI provider."""
    search_plan = request_data.get("search_plan") or request_data.get("searchPlan") or {}
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    frame = (
        request_data.get("place_intent_frame")
        or request_data.get("placeIntentFrame")
        or search_plan.get("place_intent_frame")
        or search_plan.get("placeIntentFrame")
        or {}
    )
    frame = dict(frame) if isinstance(frame, dict) else {}

    aliases = {
        "target_objects": "targetObjects",
        "candidate_place_types": "candidatePlaceTypes",
        "candidate_category_codes": "candidateCategoryCodes",
        "result_match_terms": "resultMatchTerms",
        "constraints": "constraints",
        "exclusions": "exclusions",
        "ranking_policy": "rankingPolicy",
        "primary_search_queries": "primarySearchQueries",
    }
    for snake_name, camel_name in aliases.items():
        value = frame.get(snake_name) or frame.get(camel_name)
        if value in (None, "", []):
            value = (
                request_data.get(snake_name)
                or request_data.get(camel_name)
                or search_plan.get(snake_name)
                or search_plan.get(camel_name)
            )
        if value not in (None, "", []):
            frame[snake_name] = value

    queries = _normalize_search_queries(frame.get("primary_search_queries"))
    specific_target_queries = []
    for target_term in _frame_terms(frame, "target_objects"):
        parts = _split_specific_evidence_terms(target_term, frame)
        qualifiers = [
            part
            for part in parts
            if _compact(part) not in DIRECT_TARGET_GENERIC_TERMS
        ]
        category_parts = [
            part
            for part in parts
            if get_matching_categories(part)
        ]
        for qualifier in qualifiers:
            specific_target_queries.append(
                " ".join([qualifier, *category_parts[:1]])
            )
    if specific_target_queries:
        queries = _normalize_search_queries([
            *specific_target_queries,
            *queries,
        ])
    if not queries:
        queries = _normalize_search_queries(
            search_plan.get("kakaoKeywordCandidates")
            or search_plan.get("kakao_keywords")
            or search_plan.get("kakaoKeywords")
        )
    if not queries:
        queries = _normalize_search_queries([
            *_frame_terms(frame, "target_objects"),
            *_frame_terms(frame, "candidate_place_types"),
            request_data.get("query"),
        ])
    frame["primary_search_queries"] = queries[:5]

    # React has already resolved any explicit location to these coordinates.
    frame.update({
        "location_mode": "current_context",
        "locationMode": "current_context",
        "anchor_location": "",
        "anchorLocation": "",
    })
    return frame, search_plan


def run_ai_search_candidates(request_data, *, user=None):
    """Return deterministic candidates quickly while the full AI search is running."""
    del user  # Reserved for future personalization.
    total_started = time.perf_counter()
    query = _clean_text(request_data.get("query"), 500)
    lat, lng = _context_coordinates(
        lat=request_data.get("lat"),
        lng=request_data.get("lng"),
        map_center=request_data.get("map_center") or request_data.get("mapCenter"),
    )
    limit = _limit(request_data.get("limit"), default=15)
    frame, search_plan = _candidate_preview_frame(request_data)
    radius = _search_radius_for_frame(request_data.get("radius"), frame, query)
    primary_queries = _normalize_search_queries(frame.get("primary_search_queries"))[:5]

    retrieval_started = time.perf_counter()
    if getattr(settings, "IS_TESTING", False):
        db_candidates = collect_db_candidates(
            frame, lat=lat, lng=lng, limit=max(limit * 3, 30), radius=radius,
        )
        kakao_candidates, query_counts = collect_kakao_candidates(
            frame, primary_queries, lat=lat, lng=lng, radius=radius,
        )
    else:
        with ThreadPoolExecutor(max_workers=2) as executor:
            db_future = executor.submit(
                collect_db_candidates,
                frame,
                lat=lat,
                lng=lng,
                limit=max(limit * 3, 30),
                radius=radius,
            )
            kakao_future = executor.submit(
                collect_kakao_candidates,
                frame,
                primary_queries,
                lat=lat,
                lng=lng,
                radius=radius,
            )
            db_candidates = db_future.result()
            kakao_candidates, query_counts = kakao_future.result()
    retrieval_latency_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)

    candidate_pool = [
        candidate
        for candidate in _dedupe_candidates([*db_candidates, *kakao_candidates])
        if not _candidate_has_invalid_display(candidate)
        and not _has_only_retrieval_query_evidence(candidate)
        and not _blocking_unmet_constraints(candidate)
        and candidate.get("pre_ai_evidence_level") in {"strong", "medium", "weak"}
    ]
    ranked = _prioritize_direct_specific_targets(
        sorted(candidate_pool, key=_candidate_sort_key),
        frame,
    )[:limit]
    results = []
    for index, candidate in enumerate(ranked):
        reason = candidate.get("recommendation_reason") or "요청 조건과 가까운 후보예요. AI가 적합도 순서를 확인하고 있습니다."
        results.append({
            **candidate,
            "recommendation_reason": reason,
            "recommend_reason": reason,
            "backend_rank": index + 1,
            "unified_rank": index + 1,
            "preview_rank": index + 1,
        })

    total_latency_ms = round((time.perf_counter() - total_started) * 1000, 2)
    timings = {
        "planner_latency_ms": 0.0,
        "retrieval_latency_ms": retrieval_latency_ms,
        "query_repair_latency_ms": None,
        "web_latency_ms": None,
        "semantic_query_embedding_latency_ms": 0.0,
        "semantic_vector_search_latency_ms": 0.0,
        "semantic_merge_latency_ms": 0.0,
        "reranker_latency_ms": None,
        "total_latency_ms": total_latency_ms,
    }
    return {
        "scenario": "ai_place_search",
        "type": "search",
        "decision_action": "search",
        "decisionAction": "search",
        "blocked": False,
        "can_search_now": True,
        "search_phase": "candidates",
        "provisional": True,
        "candidate_pipeline": "fast_candidate_preview",
        "unified_candidate_pipeline": True,
        "frontend_should_preserve_order": True,
        "frontend_should_skip_kakao_fallback": True,
        "candidate_source_counts": {
            "db": len(db_candidates),
            "kakao": len(kakao_candidates),
            "web": 0,
        },
        "external_search_triggered": bool(kakao_candidates),
        "external_query_count": len(primary_queries),
        "external_queries": primary_queries,
        "external_query_result_counts": query_counts,
        "results": results,
        "markers": _markers(results),
        "count": len(results),
        "result_count": len(results),
        "relevant_result_count": len(results),
        "search_plan": search_plan,
        "place_intent_frame": frame,
        "execution_mode": "candidate_preview",
        "plan_source": "client_frame",
        "timings": timings,
        "debug_pipeline": {
            "used_path": "candidate_preview",
            "candidate_counts": {
                "db": len(db_candidates),
                "kakao": len(kakao_candidates),
                "web": 0,
                "top_results": len(results),
            },
            **timings,
            "ai_call_count": 0,
        },
    }


def run_ai_search(request_data, *, user=None):
    total_started = time.perf_counter()
    timings = {
        "planner_latency_ms": None,
        "intent_parsing_latency_ms": None,
        "location_resolution_latency_ms": 0.0,
        "db_candidate_retrieval_latency_ms": None,
        "kakao_search_latency_ms": None,
        "evidence_tag_loading_latency_ms": None,
        "filtering_latency_ms": None,
        "ranking_latency_ms": None,
        "serialization_latency_ms": None,
        "retrieval_latency_ms": None,
        "query_repair_latency_ms": None,
        "web_latency_ms": None,
        "reranker_latency_ms": None,
        "semantic_query_embedding_latency_ms": 0.0,
        "semantic_query_embedding_cache_hit": None,
        "semantic_query_embedding_api_calls": 0,
        "semantic_vector_search_latency_ms": 0.0,
        "semantic_merge_latency_ms": 0.0,
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

    previous_result_action = resolve_previous_result_action(query, previous_context)
    if previous_result_action:
        return _previous_result_action_response(
            previous_result_action,
            previous_context,
            finish_timings(),
        )

    planner_started = time.perf_counter()
    intent_plan = build_ai_intent_plan(
        query,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )
    timings["planner_latency_ms"] = round((time.perf_counter() - planner_started) * 1000, 2)
    timings["intent_parsing_latency_ms"] = timings["planner_latency_ms"]
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
    semantic_activation = _semantic_activation_context(frame, original_query or query)

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
        location_started = time.perf_counter()
        location_resolution = _resolve_anchor_location(
            frame.get("anchor_location"),
            lat=context_lat,
            lng=context_lng,
        )
        timings["location_resolution_latency_ms"] = round(
            (time.perf_counter() - location_started) * 1000,
            2,
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

    def timed_collect(collector, *args, **kwargs):
        started = time.perf_counter()
        value = collector(*args, **kwargs)
        return value, round((time.perf_counter() - started) * 1000, 2)

    if getattr(settings, "IS_TESTING", False):
        db_candidates, db_latency_ms = timed_collect(
            collect_db_candidates,
            frame,
            lat=search_lat,
            lng=search_lng,
            limit=max(limit * 3, 30),
            radius=radius,
        )
        kakao_result, kakao_latency_ms = timed_collect(
            collect_kakao_candidates,
            frame,
            primary_queries,
            lat=search_lat,
            lng=search_lng,
            radius=radius,
        )
        kakao_candidates, query_counts = kakao_result
    else:
        with ThreadPoolExecutor(max_workers=2) as executor:
            db_future = executor.submit(
                timed_collect,
                collect_db_candidates,
                frame,
                lat=search_lat,
                lng=search_lng,
                limit=max(limit * 3, 30),
                radius=radius,
            )
            kakao_future = executor.submit(
                timed_collect,
                collect_kakao_candidates,
                frame,
                primary_queries,
                lat=search_lat,
                lng=search_lng,
                radius=radius,
            )
            db_candidates, db_latency_ms = db_future.result()
            kakao_result, kakao_latency_ms = kakao_future.result()
            kakao_candidates, query_counts = kakao_result
    timings["db_candidate_retrieval_latency_ms"] = db_latency_ms
    timings["evidence_tag_loading_latency_ms"] = db_latency_ms
    timings["kakao_search_latency_ms"] = kakao_latency_ms
    timings["retrieval_latency_ms"] = round((time.perf_counter() - retrieval_started) * 1000, 2)

    initial_candidates = _dedupe_candidates([*db_candidates, *kakao_candidates])
    candidate_counts = {
        "db": len(db_candidates),
        "kakao": len(kakao_candidates),
        "web": 0,
        "semantic": 0,
    }

    min_strong_medium_candidates = _as_int(
        getattr(settings, "AI_SEARCH_MIN_STRONG_MEDIUM_CANDIDATES", 3),
        3,
    )
    strong_medium_count = sum(
        1
        for candidate in initial_candidates
        if candidate.get("pre_ai_evidence_level") in {"strong", "medium"}
        and not _blocking_unmet_constraints(candidate)
    )
    deterministic_fallback_queries = []
    if min_strong_medium_candidates > 0 and strong_medium_count < min_strong_medium_candidates:
        fallback_targets = frame.get("fallback_targets") or frame.get("fallbackTargets") or []
        fallback_query_values = []
        for fallback_target in fallback_targets:
            if not isinstance(fallback_target, dict):
                continue
            fallback_query_values.extend(_as_list(fallback_target.get("queries"), max_items=4))
        deterministic_fallback_queries = [
            item
            for item in _normalize_search_queries(fallback_query_values)
            if item not in primary_queries
        ][:3]
        if deterministic_fallback_queries:
            fallback_retrieval_started = time.perf_counter()
            fallback_kakao, fallback_counts = collect_kakao_candidates(
                frame,
                deterministic_fallback_queries,
                lat=search_lat,
                lng=search_lng,
                radius=radius,
            )
            fallback_latency_ms = round((time.perf_counter() - fallback_retrieval_started) * 1000, 2)
            timings["retrieval_latency_ms"] = round(
                (timings["retrieval_latency_ms"] or 0) + fallback_latency_ms, 2
            )
            timings["kakao_search_latency_ms"] = round(
                (timings["kakao_search_latency_ms"] or 0) + fallback_latency_ms, 2
            )
            query_generation["fallback_queries"] = deterministic_fallback_queries
            query_counts.extend(fallback_counts)
            kakao_candidates.extend(fallback_kakao)
            candidate_counts["kakao"] = len(kakao_candidates)
            initial_candidates = _dedupe_candidates([*db_candidates, *kakao_candidates])
            strong_medium_count = sum(
                1
                for candidate in initial_candidates
                if candidate.get("pre_ai_evidence_level") in {"strong", "medium"}
                and not _blocking_unmet_constraints(candidate)
            )

    query_repair_debug = {"status": "skipped"}
    should_repair_queries = (
        min_strong_medium_candidates > 0
        and (
            strong_medium_count < min_strong_medium_candidates
            and (
                not initial_candidates
                or _query_needs_repair(primary_queries)
            )
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
            if item not in [*primary_queries, *deterministic_fallback_queries]
        ]
        if repaired_queries:
            repaired_kakao_started = time.perf_counter()
            repaired_kakao, repaired_counts = collect_kakao_candidates(
                frame,
                repaired_queries,
                lat=search_lat,
                lng=search_lng,
                radius=radius,
            )
            repaired_kakao_latency_ms = round(
                (time.perf_counter() - repaired_kakao_started) * 1000,
                2,
            )
            timings["kakao_search_latency_ms"] = round(
                (timings["kakao_search_latency_ms"] or 0) + repaired_kakao_latency_ms,
                2,
            )
            timings["retrieval_latency_ms"] = round(
                (timings["retrieval_latency_ms"] or 0) + repaired_kakao_latency_ms,
                2,
            )
            query_generation["fallback_queries"] = [
                *deterministic_fallback_queries,
                *repaired_queries,
            ]
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

    semantic_candidates = []
    semantic_debug = {"status": "disabled", "results": []}
    if (
        getattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", False)
        and getattr(settings, "SEMANTIC_CANDIDATE_INJECTION_ENABLED", False)
        and semantic_activation.get("semantic_required")
    ):
        semantic_started = time.perf_counter()
        semantic_candidates, semantic_debug = collect_semantic_candidates(
            original_query or query,
            frame,
            semantic_required=semantic_activation.get("semantic_required"),
            lat=search_lat,
            lng=search_lng,
            radius=radius,
        )
        timings["semantic_query_embedding_latency_ms"] = semantic_debug.get("query_embedding_latency_ms", 0.0)
        timings["semantic_query_embedding_cache_hit"] = semantic_debug.get("query_embedding_cache_hit")
        timings["semantic_query_embedding_api_calls"] = semantic_debug.get("query_embedding_api_calls", 0)
        timings["semantic_vector_search_latency_ms"] = semantic_debug.get("vector_search_latency_ms", 0.0)
        attach_semantic_scores(
            db_candidates,
            semantic_debug.get("results") or [],
        )
        timings["semantic_merge_latency_ms"] = round(
            (time.perf_counter() - semantic_started) * 1000
            - float(timings["semantic_query_embedding_latency_ms"] or 0)
            - float(timings["semantic_vector_search_latency_ms"] or 0),
            2,
        )
        candidate_counts["semantic"] = len(semantic_candidates)
    elif not semantic_activation.get("semantic_required"):
        semantic_debug = {
            "status": "skipped",
            "reason": "semantic_not_required",
            "results": [],
        }

    filtering_started = time.perf_counter()
    candidate_pool = _dedupe_candidates([
        *db_candidates, *kakao_candidates, *web_candidates, *semantic_candidates,
    ])
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
    candidate_pool, common_hard_gate_removed, common_hard_gate_debug = apply_common_hard_gate(
        candidate_pool,
        original_query or query,
        frame,
    )
    candidate_counts["removed_common_hard_gate"] = len(common_hard_gate_removed)
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
    semantic_hybrid_results = (
        _semantic_hybrid_pilot_rank(evidence_candidates, limit=limit)
        if semantic_debug.get("status") == "executed" and semantic_candidates
        else []
    )
    deterministic_results = (
        _deterministic_ranked_candidates(evidence_candidates, deterministic_codes, limit=limit)
        if deterministic_codes and not semantic_hybrid_results
        else []
    )
    timings["filtering_latency_ms"] = round(
        (time.perf_counter() - filtering_started) * 1000,
        2,
    )
    ranking_started = time.perf_counter()

    if semantic_hybrid_results:
        ranked_candidates = semantic_hybrid_results
        reranker_debug = {
            "status": "skipped", "reason": "semantic_hybrid_pilot",
            "input_count": len(candidate_pool), "included_count": len(ranked_candidates),
            "excluded_count": len(candidate_pool) - len(ranked_candidates),
            "excluded_candidates": [], "call_count": 0,
        }
        timings["reranker_latency_ms"] = 0.0
    elif deterministic_results:
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
            semantic_required=semantic_activation.get(
                'top_up_requires_semantic_support',
                semantic_activation.get('semantic_required', False),
            ),
        )

    planner_status = str(
        ((intent_plan.get("ai_debug") or {}).get("planner") or {}).get("status") or ""
    )
    if (
        not reranker_available
        and not ranking_fallback_candidates
        and planner_status.startswith("local_")
    ):
        # A deterministic intent was understood successfully. An empty result
        # set is a data coverage outcome, not an AI availability failure.
        ranked_candidates = []
        reranker_debug = {
            **reranker_debug,
            "status": "degraded_success",
            "reason": "local_intent_no_supported_candidates",
        }
        reranker_available = True

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
        semantic_required=semantic_activation.get(
            'top_up_requires_semantic_support',
            semantic_activation.get('semantic_required', False),
        ),
    )
    if top_up_candidates:
        reranker_debug = {
            **reranker_debug,
            "top_up_count": len(top_up_candidates),
            "top_up_candidate_ids": [candidate.get("id") for candidate in top_up_candidates],
        }
    ranked_candidates = _cap_verification_confidence(ranked_candidates)
    ranked_candidates = _prioritize_direct_specific_targets(ranked_candidates, frame)
    ranked_candidates, best_available_candidates = _complete_and_order_results(
        ranked_candidates,
        candidate_pool,
        common_hard_gate_removed,
        hidden_weak,
        frame,
        limit=limit,
    )
    results = ranked_candidates[:limit]
    timings["ranking_latency_ms"] = round(
        max(0.0, (time.perf_counter() - ranking_started) * 1000 - (timings["reranker_latency_ms"] or 0)),
        2,
    )
    candidate_counts.update({
        "top_results": len(results),
        "hidden_weak": len(hidden_weak),
        "removed_incompatible": len(hidden_weak),
        "unresolved": len(unresolved_candidates),
        "best_available": len(best_available_candidates),
    })
    result_quality_summary = {
        "requested_limit": limit,
        "returned_count": len(results),
        "top_five_count": min(len(results), 5),
        "all_conditions_met": sum(
            candidate.get("result_tier") == "all_conditions_met"
            for candidate in results
        ),
        "partial_match": sum(
            candidate.get("result_tier") == "partial_match"
            for candidate in results
        ),
        "best_available": sum(
            candidate.get("result_tier") == "best_available"
            for candidate in results
        ),
        "fallback_applied": bool(best_available_candidates),
        "diversity": _result_diversity_summary(results, frame),
    }

    serialization_started = time.perf_counter()
    debug_pipeline = _debug_pipeline(
        intent_plan=intent_plan,
        search_plan=search_plan,
        frame=frame,
        query_generation=query_generation,
        semantic_activation=semantic_activation,
        candidate_counts=candidate_counts,
        reranker_debug={
            **reranker_debug,
            "semantic_retrieval": {
                key: value for key, value in semantic_debug.items() if key != "results"
            },
            "common_hard_gate": common_hard_gate_debug,
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
            or bool(best_available_candidates)
        ),
        fallback_created_candidates=False,
        timings=finish_timings(),
        ai_call_count=ai_call_count,
    )
    timings["serialization_latency_ms"] = round(
        (time.perf_counter() - serialization_started) * 1000,
        2,
    )
    debug_pipeline["serialization_latency_ms"] = timings["serialization_latency_ms"]

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
        "collector_names": ["db", "kakao", "web", "semantic"],
        "candidate_source_counts": {
            "db": len(db_candidates),
            "kakao": len(kakao_candidates),
            "web": len(web_candidates),
            "semantic": len(semantic_candidates),
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
        "result_quality": result_quality_summary,
        "search_plan": search_plan,
        "place_intent_frame": search_plan.get("place_intent_frame") or frame,
        "ai_parse": parsed,
        "ai_web_search": get_ai_web_search_status(),
        "execution_mode": "ai_first_orchestrator",
        "plan_source": "ai",
        "timings": timings,
        "debug_pipeline": debug_pipeline,
        "ai_debug": {
            **(intent_plan.get("ai_debug") or {}),
            "reranker": reranker_debug,
            "query_repair": query_repair_debug,
        },
    }
