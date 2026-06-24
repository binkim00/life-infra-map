import math

from recommendations.models import Place
from recommendations.services.recommendation_condition import (
    build_recommendation_condition,
    get_default_radius,
    get_min_radius,
)
from recommendations.services.place_urls import get_kakao_place_url
from recommendations.services.smoking_area_data import calculate_distance_m
from recommendations.services.tag_utils import (
    get_category_display_name,
    get_confidence_label,
    get_fallback_description,
    get_fallback_label,
    get_source_label,
    get_tag_display_name,
    get_tag_display_names,
    get_visible_tag_names,
)
from recommendations.services.user_preferences import (
    calculate_personalization_boost,
    get_user_preference_lookup,
)


DEFAULT_CAUTION = "태그 정보는 후보 정보일 수 있으며 실제 이용 가능 여부는 확인이 필요합니다."

WAITING_PLACE_EXCLUDE_KEYWORDS = [
    "행정복지센터",
    "주민센터",
    "동사무소",
    "마을행복센터",
    "구청",
    "시청",
    "군청",
    "읍사무소",
    "면사무소",
    "민원센터",
    "복지센터",
    "복지시설쉼터",
    "복지시설",
    "경로당",
    "노인정",
    "노인회관",
    "마을회관",
    "사랑방",
    "사랑터",
    "할머니",
    "할아버지",
    "복지관",
    "노인복지",
    "노인복지관",
    "장애인복지관",
    "지원센터",
    "건강가정지원센터",
    "가족센터",
    "청소년센터",
    "자원봉사센터",
    "문화센터",
    "평생학습관",
    "요양원",
    "어린이집",
    "유치원",
    "학교",
    "새마을금고",
    "은행",
    "호텔",
    "브랜드 매장",
    "브랜드매장",
    "흡연구역",
    "흡연실",
]

WAITING_PLACE_PENALTY_KEYWORDS = [
    "파출소",
    "경찰서",
    "소방서",
    "병원",
    "교회",
    "성당",
    "사찰",
]

WAITING_PLACE_PREFERRED_KEYWORDS = [
    "카페",
    "쉼터",
    "실내쉼터",
    "도서관",
    "대합실",
    "터미널",
    "역사",
    "쇼핑몰",
    "복합상가",
    "휴게공간",
    "관광안내소",
]

WORK_CAFE_EXCLUDE_KEYWORDS = [
    "경로당",
    "노인정",
    "주민센터",
    "행정복지센터",
    "마을행복센터",
    "마을회관",
    "복지관",
    "복지시설",
    "무더위쉼터",
    "쉼터",
    "새마을금고",
    "은행",
    "흡연구역",
    "흡연실",
    "공원",
    "해변",
    "관광지",
]

WORK_CAFE_EXCLUDE_CATEGORIES = {
    "shelter",
    "city_park",
    "beach",
    "smoking_area",
    "tourism",
    "restaurant",
}

WORK_CAFE_CORE_TAGS = {
    "노트북작업",
    "조용한",
    "와이파이",
    "콘센트있음",
}

WORK_CAFE_EVIDENCE_KEYWORDS = [
    "노트북",
    "작업",
    "공부",
    "조용",
    "와이파이",
    "wifi",
    "wi-fi",
    "콘센트",
    "전원",
    "충전",
]

WORK_CAFE_LOW_CONFIDENCE_CATEGORIES = {
    "cafe",
    "library",
    "public_library",
    "study_cafe",
}

TAKEOUT_FOCUSED_TERMS = [
    "테이크아웃",
    "takeout",
    "포장전문",
    "포장 중심",
    "좌석 부족",
    "좌석없음",
    "매장 이용 제한",
]

WALK_HEALING_EXCLUDE_KEYWORDS = [
    *WAITING_PLACE_EXCLUDE_KEYWORDS,
    "음식점",
    "식당",
    "마트",
    "홈플러스",
    "시장",
    "브랜드 매장",
    "브랜드매장",
    "뉴발란스",
    "주차장",
    "술집",
    "주점",
    "편의점",
    "카페",
    "병원",
    "약국",
    "부동산",
    "숙박",
    "모텔",
    "호텔",
    "노래방",
    "PC방",
    "피시방",
    "상가",
]

WALK_HEALING_PREFERRED_KEYWORDS = [
    "공원",
    "산책",
    "산책로",
    "강변",
    "하천",
    "수변",
    "둘레길",
    "해변",
    "해수욕장",
    "전망",
    "전망대",
    "명소",
    "생태",
    "숲",
    "길",
    "호수",
    "갈맷길",
    "낙동강",
    "하구",
]

WALK_HEALING_STRONG_TAGS = {
    "산책좋음",
    "힐링",
    "숲",
    "강변",
    "공원산책",
    "산책로",
    "둘레길",
    "갈맷길",
    "전망좋음",
}

WALK_HEALING_SMALL_PARK_KEYWORDS = [
    "어린이공원",
    "소공원",
    "작은공원",
]

def normalize_recommendation_context(
    scenario="work_cafe",
    condition=None,
    categories=None,
    tags=None,
    keyword=None,
    exclude_categories=None,
    radius=None,
):
    return build_recommendation_condition(
        scenario=scenario,
        condition=condition,
        categories=categories,
        tags=tags,
        keyword=keyword,
        exclude_categories=exclude_categories,
        radius=radius,
    )


def _parse_float(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value, default):
    if value in (None, ""):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_coordinate_bounds(lat, lng, radius_m):
    lat_delta = radius_m / 111_320
    lng_scale = max(math.cos(math.radians(lat)), 0.01)
    lng_delta = radius_m / (111_320 * lng_scale)

    return {
        "lat_min": lat - lat_delta,
        "lat_max": lat + lat_delta,
        "lng_min": lng - lng_delta,
        "lng_max": lng + lng_delta,
    }


def _distance_score(distance):
    if distance is None:
        return 0

    if distance <= 300:
        return 25
    if distance <= 700:
        return 18
    if distance <= 1500:
        return 10
    if distance <= 3000:
        return 5
    return 0


def _category_score(place, categories):
    return 25 if place.category in categories else 0


def _tag_score(tag_data, preferred_tags, required_tags=None):
    required = set(required_tags or [])
    preferred = set(preferred_tags or [])
    requested = required | preferred
    matched = []
    score = 0

    for tag_name in tag_data["verified_tags"]:
        if tag_name in required:
            matched.append(tag_name)
            score += 12
        elif tag_name in requested:
            matched.append(tag_name)
            score += 10

    for tag_name in tag_data["suggested_tags"]:
        if tag_name in required:
            matched.append(tag_name)
            score += 8
        elif tag_name in requested:
            matched.append(tag_name)
            score += 7

    return min(score, 35), list(dict.fromkeys(matched))


def _all_tag_names(tag_data):
    return set(
        tag_data["verified_tags"]
        + tag_data["suggested_tags"]
        + tag_data["warning_tags"]
    )


def _missing_tags(tag_data, required_tags=None, preferred_tags=None):
    requested = list(dict.fromkeys((required_tags or []) + (preferred_tags or [])))
    if not requested:
        return []

    available = _all_tag_names(tag_data)
    return [tag for tag in requested if tag not in available]


def _avoid_tag_penalty(tag_data, avoid_tags=None):
    avoid = set(avoid_tags or [])
    if not avoid:
        return 0, []

    matched_avoid_tags = sorted(_all_tag_names(tag_data) & avoid)
    return min(len(matched_avoid_tags) * 10, 25), matched_avoid_tags


def _quality_score(place):
    return min(max(int(place.data_quality_score or 0), 0), 100) * 0.15


def _warning_penalty(tag_data):
    return min(len(tag_data["warning_tags"]) * 6, 18)


def _place_search_text(place, tag_data=None):
    tags = []
    if tag_data:
        tags = (
            tag_data.get("suggested_tags", [])
            + tag_data.get("verified_tags", [])
            + tag_data.get("warning_tags", [])
        )

    return " ".join(
        str(value or "")
        for value in [
            place.name,
            place.category,
            place.address,
            place.detail_location,
            place.source_name,
            _raw_search_text(place.raw),
            " ".join(tags),
        ]
    )


def _raw_search_text(value):
    if value in (None, ""):
        return ""

    if isinstance(value, dict):
        return " ".join(_raw_search_text(item) for item in value.values())

    if isinstance(value, (list, tuple, set)):
        return " ".join(_raw_search_text(item) for item in value)

    if isinstance(value, (str, int, float, bool)):
        return str(value)

    return ""


def _as_text_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = [value]

    result = []
    for item in values:
        if isinstance(item, dict):
            item = (
                item.get("label")
                or item.get("name")
                or item.get("display_name")
                or item.get("displayName")
                or item.get("value")
                or item.get("text")
            )
        text = str(item or "").strip()
        if text and text != "[object Object]" and text not in result:
            result.append(text)
    return result


def _compact_text(value):
    return str(value or "").lower().replace(" ", "")


def _frame_from_inputs(search_plan=None, place_intent_frame=None):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    frame = place_intent_frame if isinstance(place_intent_frame, dict) else {}
    if not frame:
        candidate = (
            search_plan.get("place_intent_frame")
            or search_plan.get("placeIntentFrame")
            or {}
        )
        frame = candidate if isinstance(candidate, dict) else {}
    return frame


def _normalize_frame_for_recommendation(search_plan=None, place_intent_frame=None):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    frame = _frame_from_inputs(search_plan, place_intent_frame)
    location_mode = str(
        frame.get("location_mode")
        or frame.get("locationMode")
        or search_plan.get("location_mode")
        or search_plan.get("locationMode")
        or ""
    ).strip()
    collector_categories = _as_text_list(
        search_plan.get("collector_category_codes")
        or search_plan.get("collectorCategoryCodes")
    )
    candidate_categories = _as_text_list(
        frame.get("candidate_category_codes")
        or frame.get("candidateCategoryCodes")
        or search_plan.get("candidate_category_codes")
        or search_plan.get("candidateCategoryCodes")
        or collector_categories
    )
    candidate_place_types = _as_text_list(
        frame.get("candidate_place_types")
        or frame.get("candidatePlaceTypes")
        or search_plan.get("candidate_place_types")
        or search_plan.get("candidatePlaceTypes")
    )
    search_queries = _as_text_list(
        frame.get("search_queries")
        or frame.get("searchQueries")
        or search_plan.get("search_queries")
        or search_plan.get("searchQueries")
    )
    result_match_terms = _as_text_list(
        frame.get("result_match_terms")
        or frame.get("resultMatchTerms")
        or search_plan.get("result_match_terms")
        or search_plan.get("resultMatchTerms")
    )
    target_objects = _as_text_list(
        frame.get("target_objects")
        or frame.get("targetObjects")
        or search_plan.get("target_objects")
        or search_plan.get("targetObjects")
    )
    ranking_policy = str(
        frame.get("ranking_policy")
        or frame.get("rankingPolicy")
        or search_plan.get("ranking_policy")
        or search_plan.get("rankingPolicy")
        or ""
    ).strip()

    normalized = {
        **frame,
        "user_goal": str(frame.get("user_goal") or frame.get("userGoal") or "").strip(),
        "anchor_location": str(frame.get("anchor_location") or frame.get("anchorLocation") or "").strip(),
        "location_mode": location_mode,
        "display_label": str(frame.get("display_label") or frame.get("displayLabel") or "").strip(),
        "target_objects": target_objects,
        "candidate_category_codes": candidate_categories,
        "candidate_place_types": candidate_place_types,
        "search_queries": search_queries,
        "result_match_terms": result_match_terms,
        "constraints": _as_text_list(frame.get("constraints") or search_plan.get("constraints")),
        "exclusions": _as_text_list(frame.get("exclusions") or search_plan.get("exclusions")),
        "preferred_place_natures": _as_text_list(
            frame.get("preferred_place_natures")
            or frame.get("preferredPlaceNatures")
            or search_plan.get("preferred_place_natures")
            or search_plan.get("preferredPlaceNatures")
        ),
        "excluded_place_natures": _as_text_list(
            frame.get("excluded_place_natures")
            or frame.get("excludedPlaceNatures")
            or search_plan.get("excluded_place_natures")
            or search_plan.get("excludedPlaceNatures")
        ),
        "ranking_policy": ranking_policy,
    }
    if normalized["target_objects"]:
        normalized["result_match_terms"] = list(dict.fromkeys([
            *normalized["target_objects"],
            *normalized["result_match_terms"],
        ]))
    return normalized


def _is_valid_recommendation_frame(frame):
    if not isinstance(frame, dict):
        return False
    if frame.get("location_mode") not in {"explicit", "current_context", "clarification_required"}:
        return False
    if frame.get("location_mode") == "explicit" and not frame.get("anchor_location"):
        return False
    return bool(
        frame.get("user_goal")
        and frame.get("display_label")
        and (frame.get("candidate_place_types") or frame.get("search_queries"))
    )


PLACE_NATURES_BY_CATEGORY = {
    "library": ["ordinary_public_access", "library_like"],
    "public_library": ["ordinary_public_access", "library_like"],
    "city_park": ["ordinary_public_access", "park_like"],
    "citypark": ["ordinary_public_access", "park_like"],
    "beach": ["ordinary_public_access", "park_like"],
    "tourism": ["ordinary_public_access"],
    "cafe": ["ordinary_public_access", "commercial_rest_place"],
    "restaurant": ["ordinary_public_access", "commercial_rest_place"],
    "shelter": ["ordinary_public_access"],
    "parking": ["ordinary_public_access", "transit_facility"],
    "toilet": ["ordinary_public_access"],
    "smoking_area": ["ordinary_public_access"],
    "pharmacy": ["ordinary_public_access", "medical_facility"],
    "hospital": ["medical_facility"],
}


GENERAL_REST_FRAME_TERMS = [
    "쉴",
    "쉼",
    "휴식",
    "휴게",
    "조용",
    "도서관",
    "쉼터",
]

SENIOR_FACILITY_TERMS = [
    "경로당",
    "노인정",
    "노인회관",
    "노인복지",
    "노인복지관",
    "요양원",
]

PUBLIC_INSTITUTION_TERMS = [
    "행정복지센터",
    "주민센터",
    "동사무소",
    "마을행복센터",
    "구청",
    "시청",
    "군청",
    "읍사무소",
    "면사무소",
    "민원센터",
    "지원센터",
    "새마을금고",
    "은행",
]

RESTRICTED_PROGRAM_FACILITY_TERMS = [
    "복지센터",
    "복지시설쉼터",
    "복지시설",
    "복지관",
    "장애인복지관",
    "건강가정지원센터",
    "가족센터",
    "청소년센터",
    "자원봉사센터",
    "문화센터",
    "평생학습관",
    "어린이집",
    "유치원",
    "학교",
]

LIMITED_ACCESS_PLACE_NATURES = {
    "conditional_shelter",
    "senior_facility_like",
    "public_institution_like",
    "restricted_program_facility",
    "limited_access_facility",
}

GENERAL_REST_LIMITED_ACCESS_PENALTIES = {
    "senior_facility_like": 55,
    "restricted_program_facility": 45,
    "public_institution_like": 42,
    "limited_access_facility": 38,
    "conditional_shelter": 35,
}


def _infer_place_natures(place, tag_data=None):
    natures = list(PLACE_NATURES_BY_CATEGORY.get(place.category, []))
    search_text = _place_search_text(place, tag_data)
    tag_text = _compact_text(" ".join(_all_tag_names(tag_data or {
        "verified_tags": [],
        "suggested_tags": [],
        "warning_tags": [],
    })))
    raw_text = _compact_text(
        " ".join([
            place.source,
            place.source_name,
            _raw_search_text(place.raw),
        ])
    )
    if "도서관" in tag_text or "library" in tag_text:
        natures.append("library_like")
    if "공원" in tag_text or "산책" in tag_text:
        natures.append("park_like")
    if place.category == "shelter" and (
        place.source == "heat_shelter_api"
        or "무더위쉼터" in raw_text
    ):
        natures.append("conditional_shelter")
    if _has_keyword(search_text, SENIOR_FACILITY_TERMS):
        natures.extend(["senior_facility_like", "limited_access_facility"])
    if _has_keyword(search_text, PUBLIC_INSTITUTION_TERMS):
        natures.extend(["public_institution_like", "limited_access_facility"])
    if _has_keyword(search_text, RESTRICTED_PROGRAM_FACILITY_TERMS):
        natures.extend(["restricted_program_facility", "limited_access_facility"])
    if _has_keyword(search_text, TAKEOUT_FOCUSED_TERMS):
        natures.append("takeout_focused")
    return list(dict.fromkeys(natures or ["unknown"]))


def _term_matches_text(text, terms):
    compact = _compact_text(text)
    if not compact:
        return False
    return any(
        term and (_compact_text(term) in compact or compact in _compact_text(term))
        for term in terms
    )


FRAME_EVIDENCE_TIER_RANKS = {
    "target_direct": 0,
    "result_direct": 1,
    "verified_direct": 2,
    "suggested_direct": 3,
    "candidate_direct": 4,
    "category_only": 5,
    "none": 9,
}

TRUSTED_DIRECT_TAG_SOURCES = {"checked", "user_verified"}
SUGGESTED_DIRECT_TAG_SOURCES = {"ai_suggested", "blog_search"}


def _frame_evidence_sort_rank(frame_relevance):
    frame_relevance = frame_relevance if isinstance(frame_relevance, dict) else {}
    return FRAME_EVIDENCE_TIER_RANKS.get(
        frame_relevance.get("evidence_tier") or "none",
        FRAME_EVIDENCE_TIER_RANKS["none"],
    )


def _frame_result_terms(frame):
    return _as_text_list(frame.get("result_match_terms")) + _as_text_list(frame.get("resultMatchTerms"))


def _is_trusted_tag_detail(detail):
    if not isinstance(detail, dict):
        return False
    if detail.get("is_verified"):
        return True
    return (
        detail.get("source") in TRUSTED_DIRECT_TAG_SOURCES
        and detail.get("status") == "confirmed"
    )


def _is_suggested_tag_detail(detail):
    if not isinstance(detail, dict):
        return False
    if _is_trusted_tag_detail(detail):
        return False
    return detail.get("source") in SUGGESTED_DIRECT_TAG_SOURCES or detail.get("status") != "confirmed"


def _tag_names_for_evidence(tag_data, *, trusted):
    names = []
    for detail in tag_data.get("tag_details", []):
        if not isinstance(detail, dict):
            continue
        if _is_trusted_tag_detail(detail) == trusted:
            names.append(detail.get("name"))
    return list(dict.fromkeys(name for name in names if name))


def _append_frame_evidence(evidence, evidence_type, value, *, label="", source_strength=""):
    item = {
        "type": evidence_type,
        "value": value,
    }
    if label:
        item["label"] = label
    if source_strength:
        item["source_strength"] = source_strength
    evidence.append(item)


def _evidence_tier(evidence):
    best_tier = "none"
    best_rank = FRAME_EVIDENCE_TIER_RANKS[best_tier]
    for item in evidence:
        evidence_type = str(item.get("type") or "")
        source_strength = str(item.get("source_strength") or "")
        if source_strength == "verified":
            tier = "verified_direct"
        elif source_strength == "suggested":
            tier = "suggested_direct"
        elif source_strength == "candidate":
            tier = "candidate_direct"
        elif evidence_type.startswith("target_"):
            tier = "target_direct"
        elif evidence_type.startswith("result_"):
            tier = "result_direct"
        elif evidence_type in {"category_code", "category_label"}:
            tier = "category_only"
        else:
            tier = "none"

        rank = FRAME_EVIDENCE_TIER_RANKS.get(tier, FRAME_EVIDENCE_TIER_RANKS["none"])
        if rank < best_rank:
            best_rank = rank
            best_tier = tier
    return best_tier


def _match_strength_from_evidence_tier(tier):
    if tier in {"target_direct", "result_direct", "verified_direct"}:
        return "strong"
    if tier in {"suggested_direct", "candidate_direct"}:
        return "medium"
    if tier == "category_only":
        return "weak"
    return "none"


def _frame_relevance_terms(frame):
    return list(dict.fromkeys(
        _as_text_list(frame.get("target_objects"))
        + _as_text_list(frame.get("targetObjects"))
        + _as_text_list(frame.get("result_match_terms"))
        + _as_text_list(frame.get("constraints"))
        + _as_text_list(frame.get("candidate_place_types"))
    ))


def _frame_target_terms(frame):
    return list(dict.fromkeys(
        _as_text_list(frame.get("target_objects"))
        + _as_text_list(frame.get("targetObjects"))
        + _as_text_list(frame.get("result_match_terms"))
        + _as_text_list(frame.get("constraints"))
    ))


def _frame_candidate_terms(frame):
    return _as_text_list(frame.get("candidate_place_types"))


def _frame_ranking_policy(frame):
    return str(frame.get("ranking_policy") or frame.get("rankingPolicy") or "").strip()


def _place_evidence_text(place, tag_data, include_raw=True):
    values = [
        place.name,
        place.category,
        get_category_display_name(place.category),
        place.address,
        place.detail_location,
        place.source_name,
        " ".join(tag_data["verified_tags"]),
        " ".join(tag_data["suggested_tags"]),
        " ".join(tag_data["warning_tags"]),
    ]
    if include_raw:
        values.append(_raw_search_text(place.raw))
    return " ".join(str(value or "") for value in values)


def _frame_requests_general_rest(frame):
    frame_text = _compact_text(" ".join(
        _as_text_list(frame.get("candidate_place_types"))
        + _as_text_list(frame.get("result_match_terms"))
        + _as_text_list(frame.get("constraints"))
        + _as_text_list(frame.get("preferred_place_natures"))
        + [
            frame.get("user_goal", ""),
            frame.get("display_label", ""),
            frame.get("situation", ""),
        ]
    ))
    if not frame_text:
        return False
    if any(keyword in frame_text for keyword in ["화장실", "약국", "병원", "흡연", "주차"]):
        return False
    return any(_compact_text(term) in frame_text for term in GENERAL_REST_FRAME_TERMS)


def _frame_requests_low_cost_public_space(frame):
    frame_text = _compact_text(" ".join(
        _as_text_list(frame.get("target_objects"))
        + _as_text_list(frame.get("constraints"))
        + _as_text_list(frame.get("preferred_place_natures"))
        + [
            frame.get("user_goal", ""),
            frame.get("display_label", ""),
            frame.get("ranking_policy", ""),
        ]
    ))
    if not frame_text:
        return False
    return any(term in frame_text for term in ["무료", "돈안", "돈안쓰", "저비용", "공공", "cost_sensitive"])


def _frame_policy_scenario(frame):
    frame_text = _compact_text(" ".join(
        _as_text_list(frame.get("candidate_category_codes"))
        + _as_text_list(frame.get("candidate_place_types"))
        + _as_text_list(frame.get("result_match_terms"))
        + _as_text_list(frame.get("constraints"))
        + _as_text_list(frame.get("preferred_place_natures"))
        + [
            frame.get("situation", ""),
            frame.get("display_label", ""),
            frame.get("user_goal", ""),
        ]
    ))
    if not frame_text:
        return ""

    work_signals = ["work_cafe", "workplace", "작업", "노트북", "콘센트", "와이파이", "wifi", "공부", "스터디"]
    if (
        ("cafe" in frame_text or "카페" in frame_text)
        and any(_compact_text(signal) in frame_text for signal in work_signals)
    ):
        return "work_cafe"

    walk_signals = ["walk_healing", "산책", "힐링", "걷기"]
    if any(_compact_text(signal) in frame_text for signal in walk_signals):
        return "walk_healing"

    return ""


def _evaluate_frame_relevance(place, tag_data, frame):
    evidence = []
    matched_categories = []
    category_codes = set(_as_text_list(frame.get("candidate_category_codes")))
    target_object_terms = list(dict.fromkeys(
        _as_text_list(frame.get("target_objects"))
        + _as_text_list(frame.get("targetObjects"))
    ))
    result_terms = _frame_result_terms(frame)
    target_terms = _frame_target_terms(frame)
    candidate_terms = _frame_candidate_terms(frame)
    category_label = get_category_display_name(place.category)
    place_identity_text = " ".join([
        place.name,
        place.address,
        place.detail_location,
        place.source_name,
        _raw_search_text(place.raw),
        " ".join(tag_data["warning_tags"]),
    ])
    category_text = " ".join([place.category, category_label])
    trusted_tag_names = _tag_names_for_evidence(tag_data, trusted=True)
    suggested_tag_names = [
        detail.get("name")
        for detail in tag_data.get("tag_details", [])
        if _is_suggested_tag_detail(detail) and detail.get("name")
    ]
    candidate_tag_names = [
        detail.get("name")
        for detail in tag_data.get("tag_details", [])
        if (
            isinstance(detail, dict)
            and detail.get("name")
            and not _is_trusted_tag_detail(detail)
            and not _is_suggested_tag_detail(detail)
        )
    ]
    trusted_tag_text = " ".join(trusted_tag_names)
    suggested_tag_text = " ".join(suggested_tag_names)
    candidate_tag_text = " ".join(candidate_tag_names)

    if category_codes and place.category in category_codes:
        matched_categories.append(place.category)
        _append_frame_evidence(
            evidence,
            "category_code",
            place.category,
            label=category_label,
        )

    if target_object_terms and _term_matches_text(category_text, target_object_terms):
        _append_frame_evidence(evidence, "target_category_label", category_label)

    if target_object_terms and _term_matches_text(place_identity_text, target_object_terms):
        _append_frame_evidence(evidence, "target_place_text", place.name)

    if result_terms and _term_matches_text(category_text, result_terms):
        _append_frame_evidence(evidence, "result_category_label", category_label)

    if result_terms and _term_matches_text(place_identity_text, result_terms):
        _append_frame_evidence(evidence, "result_place_text", place.name)

    if candidate_terms and _term_matches_text(category_text, candidate_terms):
        _append_frame_evidence(evidence, "category_label", category_label)

    if candidate_terms and _term_matches_text(place_identity_text, candidate_terms):
        _append_frame_evidence(
            evidence,
            "candidate_place_text",
            place.name,
            source_strength="candidate" if not target_object_terms else "",
        )

    for tag_name in trusted_tag_names:
        if _term_matches_text(tag_name, target_terms):
            _append_frame_evidence(
                evidence,
                "tag_direct",
                tag_name,
                source_strength="verified",
            )
        elif _term_matches_text(tag_name, candidate_terms):
            _append_frame_evidence(
                evidence,
                "candidate_tag",
                tag_name,
                source_strength="candidate" if not target_object_terms else "",
            )

    for tag_name in suggested_tag_names:
        if _term_matches_text(tag_name, target_terms):
            _append_frame_evidence(
                evidence,
                "tag_direct",
                tag_name,
                source_strength="suggested",
            )
        elif _term_matches_text(tag_name, candidate_terms):
            _append_frame_evidence(
                evidence,
                "candidate_tag",
                tag_name,
                source_strength="candidate" if not target_object_terms else "",
            )

    for tag_name in candidate_tag_names:
        if _term_matches_text(tag_name, target_terms):
            _append_frame_evidence(
                evidence,
                "tag_direct",
                tag_name,
                source_strength="candidate",
            )
        elif _term_matches_text(tag_name, candidate_terms):
            _append_frame_evidence(
                evidence,
                "candidate_tag",
                tag_name,
                source_strength="candidate" if not target_object_terms else "",
            )

    if (
        suggested_tag_text
        and target_terms
        and _term_matches_text(suggested_tag_text, target_terms)
        and (
            _term_matches_text(place_identity_text, target_terms)
            or _term_matches_text(category_text, target_terms)
            or _term_matches_text(candidate_tag_text, target_terms)
        )
    ):
        _append_frame_evidence(
            evidence,
            "reinforced_suggested_tag",
            suggested_tag_names[0],
            source_strength="verified",
        )

    place_natures = _infer_place_natures(place, tag_data)
    preferred_natures = set(_as_text_list(frame.get("preferred_place_natures")))
    if preferred_natures and preferred_natures.intersection(place_natures):
        _append_frame_evidence(
            evidence,
            "place_nature",
            sorted(preferred_natures.intersection(place_natures))[0],
        )

    score_penalty = 0
    score_penalty_reason = ""
    evidence_tier = _evidence_tier(evidence)
    match_strength = _match_strength_from_evidence_tier(evidence_tier)
    has_place_nature_evidence = any(item["type"] == "place_nature" for item in evidence)
    place_nature_can_be_medium = (
        not target_object_terms
        or _frame_requests_general_rest(frame)
        or _frame_requests_low_cost_public_space(frame)
    )
    if (
        match_strength == "weak"
        and (
            (has_place_nature_evidence and place_nature_can_be_medium)
            or (
                not target_object_terms
                and candidate_terms
                and (
                    _term_matches_text(place_identity_text, candidate_terms)
                    or _term_matches_text(trusted_tag_text, candidate_terms)
                    or _term_matches_text(suggested_tag_text, candidate_terms)
                    or _term_matches_text(candidate_tag_text, candidate_terms)
                )
            )
        )
    ):
        match_strength = "medium"
        evidence_tier = "candidate_direct"

    if _frame_requests_general_rest(frame):
        limited_natures = [
            nature for nature in place_natures
            if nature in LIMITED_ACCESS_PLACE_NATURES and nature not in preferred_natures
        ]
        if limited_natures:
            score_penalty = max(
                GENERAL_REST_LIMITED_ACCESS_PENALTIES.get(nature, 35)
                for nature in limited_natures
            )
            score_penalty_reason = f"{limited_natures[0]}_for_general_rest"

    if (
        _frame_requests_low_cost_public_space(frame)
        and "commercial_rest_place" in place_natures
        and "commercial_rest_place" not in preferred_natures
        and not score_penalty
    ):
            score_penalty = 34
            score_penalty_reason = "commercial_rest_place_for_low_cost_public_space"

    if match_strength == "weak" and target_terms and not score_penalty:
        score_penalty = 28
        score_penalty_reason = "frame_category_fallback_without_target_evidence"

    if category_codes:
        is_relevant = bool(matched_categories)
    else:
        is_relevant = bool(evidence)

    score = 0
    if matched_categories:
        if match_strength == "strong":
            score += 70
        elif match_strength == "medium":
            score += 55
        else:
            score += 35
    score += min(30, len(evidence) * 10)

    return {
        "is_relevant": is_relevant,
        "matched_evidence": evidence,
        "matched_category_codes": matched_categories,
        "relevance_score": min(score, 100),
        "relevance_source": "frame_category_or_tag" if evidence else "",
        "place_natures": place_natures,
        "match_strength": match_strength,
        "evidence_tier": evidence_tier,
        "evidence_sort_rank": FRAME_EVIDENCE_TIER_RANKS.get(
            evidence_tier,
            FRAME_EVIDENCE_TIER_RANKS["none"],
        ),
        "has_target_evidence": evidence_tier in {"target_direct", "result_direct", "verified_direct"},
        "score_penalty": score_penalty,
        "score_penalty_reason": score_penalty_reason,
    }


def _frame_exclusion_terms(frame):
    return _as_text_list(frame.get("exclusions")) + _as_text_list(frame.get("excluded_place_natures"))


def _get_frame_excluded_reason(place, tag_data, frame):
    terms = _frame_exclusion_terms(frame)
    if not terms:
        return ""

    category_text = " ".join([
        place.category,
        get_category_display_name(place.category),
        " ".join(tag_data["verified_tags"]),
        " ".join(tag_data["suggested_tags"]),
        " ".join(_infer_place_natures(place, tag_data)),
    ])
    for term in terms:
        cleaned = (
            str(term)
            .replace("제외", " ")
            .replace("말고", " ")
            .replace("빼고", " ")
            .strip()
        )
        if cleaned and _term_matches_text(category_text, [cleaned]):
            return term
    return ""


def _has_keyword(text, keywords):
    return any(keyword in text for keyword in keywords)


def _has_walk_healing_tag_evidence(tag_data):
    return bool(_all_tag_names(tag_data) & WALK_HEALING_STRONG_TAGS)


def get_waiting_place_adjustment(place, tag_data):
    text = _place_search_text(place, tag_data)

    if _has_keyword(text, WAITING_PLACE_EXCLUDE_KEYWORDS):
        return {
            "exclude": True,
            "penalty": 140,
            "bonus": 0,
            "reason": "limited_access_shelter",
        }

    penalty = 0
    reason = None
    if _has_keyword(text, WAITING_PLACE_PENALTY_KEYWORDS):
        penalty = 65
        reason = "public_admin_penalty"

    bonus = 0
    if _has_keyword(text, WAITING_PLACE_PREFERRED_KEYWORDS):
        bonus = 12

    return {
        "exclude": False,
        "penalty": penalty,
        "bonus": bonus,
        "reason": reason,
    }


def get_work_cafe_adjustment(place, tag_data):
    text = _place_search_text(place, tag_data)
    tag_names = _all_tag_names(tag_data)
    has_core_evidence = bool(tag_names & WORK_CAFE_CORE_TAGS) or _has_keyword(
        text,
        WORK_CAFE_EVIDENCE_KEYWORDS,
    )
    place_natures = _infer_place_natures(place, tag_data)
    is_shelter_without_work_evidence = place.category == "shelter" and not has_core_evidence
    is_takeout_without_work_evidence = "takeout_focused" in place_natures and not has_core_evidence

    if (
        place.category in WORK_CAFE_EXCLUDE_CATEGORIES
        or _has_keyword(text, WORK_CAFE_EXCLUDE_KEYWORDS)
        or is_shelter_without_work_evidence
    ):
        return {
            "exclude": True,
            "penalty": 140,
            "bonus": 0,
            "reason": "work_cafe_unsuitable_place",
            "has_core_evidence": has_core_evidence,
            "category_only_without_core": False,
            "takeout_without_core": is_takeout_without_work_evidence,
        }

    category_only_without_core = (
        place.category in WORK_CAFE_LOW_CONFIDENCE_CATEGORIES
        and not has_core_evidence
    )
    penalty = 0
    reason = None
    if is_takeout_without_work_evidence:
        penalty = 55
        reason = "work_cafe_takeout_without_core"
    elif category_only_without_core:
        penalty = 35
        reason = "work_cafe_category_only_without_core"

    return {
        "exclude": False,
        "penalty": penalty,
        "bonus": 12 if has_core_evidence else 0,
        "reason": reason,
        "has_core_evidence": has_core_evidence,
        "category_only_without_core": category_only_without_core,
        "takeout_without_core": is_takeout_without_work_evidence,
    }


def get_walk_healing_adjustment(place, tag_data):
    text = _place_search_text(place, tag_data)
    has_walk_keyword_evidence = _has_keyword(text, WALK_HEALING_PREFERRED_KEYWORDS)
    has_walk_tag_evidence = _has_walk_healing_tag_evidence(tag_data)
    has_walk_evidence = has_walk_keyword_evidence or has_walk_tag_evidence
    is_small_park = _has_keyword(text, WALK_HEALING_SMALL_PARK_KEYWORDS)

    if _has_keyword(text, WALK_HEALING_EXCLUDE_KEYWORDS):
        return {
            "exclude": True,
            "penalty": 120,
            "bonus": 0,
            "reason": "non_walk_healing_place",
            "has_walk_evidence": has_walk_evidence,
            "is_small_park_without_walk_tag": False,
            "tourism_without_walk_evidence": False,
        }

    if place.category == "tourism" and not has_walk_evidence:
        return {
            "exclude": True,
            "penalty": 120,
            "bonus": 0,
            "reason": "tourism_without_walk_evidence",
            "has_walk_evidence": False,
            "is_small_park_without_walk_tag": False,
            "tourism_without_walk_evidence": True,
        }

    bonus = 0
    if has_walk_evidence:
        bonus = 14

    penalty = 0
    reason = None
    is_small_park_without_walk_tag = is_small_park and not has_walk_tag_evidence
    if is_small_park_without_walk_tag:
        penalty = 45
        bonus = 0
        reason = "small_park_without_walk_tag"

    return {
        "exclude": False,
        "penalty": penalty,
        "bonus": bonus,
        "reason": reason,
        "has_walk_evidence": has_walk_evidence,
        "is_small_park_without_walk_tag": is_small_park_without_walk_tag,
        "tourism_without_walk_evidence": False,
    }


def get_place_tag_data(place):
    suggested_tags = []
    verified_tags = []
    warning_tags = []
    tag_details = []
    raw = place.raw or {}
    raw_warning_tags = raw.get("warning_tags", [])
    raw_scores = raw.get("scores", {})

    for place_tag in place.place_tags.all():
        tag = place_tag.tag
        detail = {
            "name": tag.name,
            "tag_type": tag.tag_type,
            "source": place_tag.source,
            "status": place_tag.status,
            "confidence": place_tag.confidence,
            "evidence": place_tag.evidence,
            "is_verified": place_tag.is_verified,
        }
        tag_details.append(detail)

        if tag.tag_type == "warning" or tag.name in raw_warning_tags:
            warning_tags.append(tag.name)
        elif _is_trusted_tag_detail(detail):
            verified_tags.append(tag.name)
        else:
            suggested_tags.append(tag.name)

    return {
        "suggested_tags": list(dict.fromkeys(suggested_tags)),
        "verified_tags": list(dict.fromkeys(verified_tags)),
        "warning_tags": list(dict.fromkeys(warning_tags)),
        "tag_details": tag_details,
        "raw_scores": raw_scores,
        "saved_place": place,
    }


def score_place(
    place,
    tag_data,
    categories,
    preferred_tags,
    distance,
    scenario=None,
    required_tags=None,
    avoid_tags=None,
):
    category_score = _category_score(place, categories)
    tag_score, matched_tags = _tag_score(
        tag_data,
        preferred_tags,
        required_tags=required_tags,
    )
    distance_score = _distance_score(distance)
    quality_score = _quality_score(place)
    warning_penalty = _warning_penalty(tag_data)
    avoid_penalty, matched_avoid_tags = _avoid_tag_penalty(tag_data, avoid_tags)
    waiting_adjustment = (
        get_waiting_place_adjustment(place, tag_data)
        if scenario == "waiting_place"
        else {"exclude": False, "penalty": 0, "bonus": 0, "reason": None}
    )
    work_cafe_adjustment = (
        get_work_cafe_adjustment(place, tag_data)
        if scenario == "work_cafe"
        else {"exclude": False, "penalty": 0, "bonus": 0, "reason": None}
    )
    walk_healing_adjustment = (
        get_walk_healing_adjustment(place, tag_data)
        if scenario == "walk_healing"
        else {"exclude": False, "penalty": 0, "bonus": 0, "reason": None}
    )

    score = (
        20
        + category_score
        + tag_score
        + distance_score
        + quality_score
        + waiting_adjustment["bonus"]
        + work_cafe_adjustment["bonus"]
        + walk_healing_adjustment["bonus"]
        - warning_penalty
        - avoid_penalty
        - waiting_adjustment["penalty"]
        - work_cafe_adjustment["penalty"]
        - walk_healing_adjustment["penalty"]
    )

    if category_score == 0 and not matched_tags:
        score -= 20

    score = min(max(round(score), 0), 100)
    return score, matched_tags, {
        "category": category_score,
        "tags": tag_score,
        "distance": distance_score,
        "data_quality": round(quality_score, 1),
        "warning_penalty": warning_penalty,
        "avoid_tag_penalty": avoid_penalty,
        "matched_avoid_tags": matched_avoid_tags,
        "waiting_place_bonus": waiting_adjustment["bonus"],
        "unsuitable_place_penalty": waiting_adjustment["penalty"],
        "waiting_place_penalty_reason": waiting_adjustment["reason"],
        "excluded_by_waiting_place": waiting_adjustment["exclude"],
        "work_cafe_bonus": work_cafe_adjustment["bonus"],
        "work_cafe_penalty": work_cafe_adjustment["penalty"],
        "work_cafe_penalty_reason": work_cafe_adjustment["reason"],
        "excluded_by_work_cafe": work_cafe_adjustment["exclude"],
        "work_cafe_policy_applied": scenario == "work_cafe",
        "work_cafe_has_core_evidence": work_cafe_adjustment.get("has_core_evidence", False),
        "work_cafe_category_only_without_core": work_cafe_adjustment.get(
            "category_only_without_core",
            False,
        ),
        "work_cafe_takeout_without_core": work_cafe_adjustment.get(
            "takeout_without_core",
            False,
        ),
        "walk_healing_bonus": walk_healing_adjustment["bonus"],
        "walk_healing_penalty": walk_healing_adjustment["penalty"],
        "walk_healing_penalty_reason": walk_healing_adjustment["reason"],
        "excluded_by_walk_healing": walk_healing_adjustment["exclude"],
        "walk_healing_policy_applied": scenario == "walk_healing",
        "walk_healing_has_evidence": walk_healing_adjustment.get("has_walk_evidence", False),
        "walk_healing_small_park_without_walk_tag": walk_healing_adjustment.get(
            "is_small_park_without_walk_tag",
            False,
        ),
        "walk_healing_tourism_without_evidence": walk_healing_adjustment.get(
            "tourism_without_walk_evidence",
            False,
        ),
    }


def get_match_level(matched_tags, category_matches):
    if matched_tags:
        return "tag_matched"

    if category_matches:
        return "category_distance_fallback"

    return "low_match"


def get_recommendation_confidence(score, metadata):
    if metadata["required_missing_tags"]:
        return "low"

    if (
        metadata["is_verified"]
        and metadata["fallback_level"] == 1
        and not metadata["required_missing_tags"]
        and len(metadata["missing_tags"]) <= 1
        and score >= 75
    ):
        return "high"

    if metadata["fallback_level"] <= 3 and score >= 55:
        return "medium"

    return "low"


def build_result_metadata(
    tag_data,
    matched_tags,
    missing_tags,
    match_level,
    score_breakdown,
    required_tags=None,
    frame_relevance=None,
):
    required_tags = required_tags or []
    frame_relevance = frame_relevance if isinstance(frame_relevance, dict) else {}
    required_missing_tags = [
        tag for tag in required_tags
        if tag in missing_tags
    ]
    verified_matches = [
        tag for tag in matched_tags
        if tag in tag_data["verified_tags"]
    ]
    candidate_matches = [
        tag for tag in matched_tags
        if tag in tag_data["suggested_tags"]
    ]
    has_any_tag_data = bool(
        tag_data["verified_tags"]
        or tag_data["suggested_tags"]
        or tag_data["warning_tags"]
    )
    evidence_tier = frame_relevance.get("evidence_tier") or ""

    if evidence_tier in {"target_direct", "result_direct", "verified_direct"}:
        source_type = "db_verified" if evidence_tier == "verified_direct" else "db_direct_evidence"
        is_verified = evidence_tier == "verified_direct"
        confidence = "high" if is_verified and not required_missing_tags else "medium"
        caution = "" if is_verified else "장소명/카테고리/설명에서 요청 의도와 직접 맞는 근거가 확인됐습니다. 세부 정보는 방문 전 확인해 주세요."
        if required_missing_tags:
            caution = "직접 근거는 있지만 요청의 핵심 조건 일부는 아직 확인되지 않았습니다."
        return {
            "source_type": source_type,
            "confidence": confidence,
            "is_verified": is_verified,
            "fallback_level": 1,
            "missing_tags": missing_tags,
            "required_missing_tags": required_missing_tags,
            "caution_message": caution,
            "evidence_label": "추천 근거 높음",
            "evidence_description": "현재 사용자 의도와 직접 맞는 근거가 확인된 후보입니다.",
        }

    if evidence_tier in {"suggested_direct", "candidate_direct"}:
        caution = "추천 후보이지만 검증된 직접 근거는 아니므로 방문 전 확인이 필요합니다."
        if required_missing_tags:
            caution = "요청의 핵심 조건 일부가 확인되지 않아 방문 전 확인이 필요합니다."
        return {
            "source_type": "db_candidate",
            "confidence": "medium" if not required_missing_tags else "low",
            "is_verified": False,
            "fallback_level": 2,
            "missing_tags": missing_tags,
            "required_missing_tags": required_missing_tags,
            "caution_message": caution,
            "evidence_label": "추천 후보, 확인 필요",
            "evidence_description": "후보/자동 생성 근거가 사용자 의도와 일부 맞지만 검증은 필요합니다.",
        }

    if evidence_tier == "category_only":
        caution = "DB 카테고리만 맞고 요청 대상과 직접 맞는 근거는 부족합니다."
        if missing_tags:
            missing_labels = get_tag_display_names(
                missing_tags[:3],
                hidden_label="확인되지 않은 세부 조건",
            )
            caution = f"{caution} 확인되지 않은 조건: {', '.join(missing_labels)}."
        return {
            "source_type": "db_category_fallback",
            "confidence": "low",
            "is_verified": False,
            "fallback_level": 5,
            "missing_tags": missing_tags,
            "required_missing_tags": required_missing_tags,
            "caution_message": caution,
            "evidence_label": "관련 근거 부족 후보",
            "evidence_description": "카테고리/거리 기반 후보이며 현재 의도와 직접 맞는 근거는 부족합니다.",
        }

    if verified_matches and not required_missing_tags and len(missing_tags) <= 1:
        return {
            "source_type": "db_verified",
            "confidence": "high",
            "is_verified": True,
            "fallback_level": 1,
            "missing_tags": missing_tags,
            "required_missing_tags": required_missing_tags,
            "caution_message": "",
            "evidence_label": "추천 근거 높음",
            "evidence_description": "검증된 DB 태그가 사용자 조건과 일치한 후보입니다.",
        }

    if verified_matches:
        caution = "검증 태그 일부는 일치하지만 요청의 핵심 조건 일부는 아직 확인되지 않았습니다."
        return {
            "source_type": "db_verified",
            "confidence": "medium",
            "is_verified": True,
            "fallback_level": 2,
            "missing_tags": missing_tags,
            "required_missing_tags": required_missing_tags,
            "caution_message": caution,
            "evidence_label": "추천 근거 높음",
            "evidence_description": "검증된 DB 태그 일부가 사용자 조건과 일치한 후보입니다.",
        }

    if candidate_matches or matched_tags:
        if required_missing_tags:
            caution = "요청의 핵심 조건 일부가 확인되지 않아 낮은 신뢰도의 후보로 표시됩니다."
        elif missing_tags and len(missing_tags) > len(matched_tags):
            caution = (
                "일부 태그는 후보 정보이고 확인되지 않은 조건이 더 많아 "
                "방문 전 실제 이용 가능 여부 확인이 필요합니다."
            )
        else:
            caution = "일부 태그는 후보 정보이므로 실제 이용 가능 여부는 방문 전 확인이 필요합니다."

        return {
            "source_type": "db_candidate",
            "confidence": "medium" if not required_missing_tags else "low",
            "is_verified": False,
            "fallback_level": 2,
            "missing_tags": missing_tags,
            "required_missing_tags": required_missing_tags,
            "caution_message": caution,
            "evidence_label": "추천 후보, 확인 필요",
            "evidence_description": "후보 태그가 일부 일치하지만 검증은 필요합니다.",
        }

    if match_level == "category_distance_fallback":
        if has_any_tag_data:
            caution = (
                "요청한 세부 조건과 직접 일치하는 태그는 부족하지만, "
                "DB 카테고리와 거리 기준으로 추천된 후보입니다."
            )
            fallback_level = 3
        else:
            caution = "세부 태그 데이터가 부족하여 카테고리와 거리 기준으로 추천된 후보입니다."
            fallback_level = 5

        if missing_tags:
            missing_labels = get_tag_display_names(
                missing_tags[:3],
                hidden_label="확인되지 않은 세부 조건",
            )
            caution = f"{caution} 확인되지 않은 조건: {', '.join(missing_labels)}."

        return {
            "source_type": "db_category_fallback",
            "confidence": "low",
            "is_verified": False,
            "fallback_level": fallback_level,
            "missing_tags": missing_tags,
            "required_missing_tags": required_missing_tags,
            "caution_message": caution,
            "evidence_label": "관련 근거 부족 후보",
            "evidence_description": "카테고리/거리 기반 후보이며 직접 근거는 부족합니다.",
        }

    return {
        "source_type": "db_category_fallback",
        "confidence": "low",
        "is_verified": False,
        "fallback_level": 5,
        "missing_tags": missing_tags,
        "required_missing_tags": required_missing_tags,
        "caution_message": "입력 조건과의 일치 근거가 부족하여 확인이 필요한 후보입니다.",
        "evidence_label": "관련 근거 부족 후보",
        "evidence_description": "현재 의도와 직접 맞는 근거가 부족한 후보입니다.",
    }


def apply_score_cap(score, metadata, matched_tags, missing_tags, score_breakdown):
    cap = 100
    cap_reasons = []
    frame_evidence_tier = score_breakdown.get("frame_evidence_tier") or ""

    if not metadata["is_verified"]:
        cap = min(cap, 75)
        cap_reasons.append("unverified")

    if metadata["source_type"] == "db_candidate":
        cap = min(cap, 75)
        cap_reasons.append("candidate_tags")
    elif metadata["source_type"] == "db_category_fallback":
        cap = min(cap, 60)
        cap_reasons.append("category_fallback")

    fallback_caps = {
        3: 65,
        4: 60,
        5: 50,
    }
    fallback_level = metadata.get("fallback_level")
    if fallback_level in fallback_caps:
        cap = min(cap, fallback_caps[fallback_level])
        cap_reasons.append(f"fallback_level_{fallback_level}")

    if metadata["required_missing_tags"]:
        cap = min(cap, 60)
        cap_reasons.append("required_tags_missing")

    if frame_evidence_tier in {"suggested_direct", "candidate_direct"}:
        cap = min(cap, 72)
        cap_reasons.append(f"frame_{frame_evidence_tier}_needs_verification")
    elif frame_evidence_tier == "category_only":
        cap = min(cap, 42)
        cap_reasons.append("frame_category_only_without_direct_evidence")

    category_only = (
        score_breakdown.get("category", 0) > 0
        and not matched_tags
        and not score_breakdown.get("work_cafe_has_core_evidence")
    )
    if category_only:
        cap = min(cap, 50)
        cap_reasons.append("category_only")

        if score_breakdown.get("walk_healing_policy_applied"):
            cap = min(cap, 40)
            cap_reasons.append("walk_healing_category_only_without_walk_tag")

        if score_breakdown.get("work_cafe_policy_applied"):
            cap = min(cap, 40)
            cap_reasons.append("work_cafe_category_only_without_core")

    if score_breakdown.get("walk_healing_tourism_without_evidence"):
        cap = min(cap, 30)
        cap_reasons.append("walk_healing_tourism_without_evidence")

    if score_breakdown.get("walk_healing_small_park_without_walk_tag"):
        cap = min(cap, 35)
        cap_reasons.append("walk_healing_small_park_without_walk_tag")

    if score_breakdown.get("work_cafe_category_only_without_core"):
        cap = min(cap, 40)
        cap_reasons.append("work_cafe_category_only_without_core")

    if score_breakdown.get("work_cafe_takeout_without_core"):
        cap = min(cap, 35)
        cap_reasons.append("work_cafe_takeout_without_core")

    if score_breakdown.get("frame_match_strength") == "weak":
        cap = min(cap, 42)
        cap_reasons.append("frame_weak_category_fallback")
    elif score_breakdown.get("frame_match_strength") == "medium":
        cap = min(cap, 72)
        cap_reasons.append("frame_medium_without_target_evidence")

    if missing_tags and len(missing_tags) > len(matched_tags):
        cap = min(cap, 65)
        cap_reasons.append("more_missing_than_matched")

    capped_score = min(score, cap)
    return capped_score, cap, cap_reasons


def build_result_labels(metadata):
    fallback_level = metadata.get("fallback_level")
    return {
        "source_label": get_source_label(metadata.get("source_type")),
        "confidence_label": get_confidence_label(metadata.get("confidence")),
        "fallback_label": metadata.get("evidence_label") or get_fallback_label(fallback_level),
        "fallback_description": metadata.get("evidence_description") or get_fallback_description(fallback_level),
    }


def build_response_condition(context):
    return {
        **context,
        "required_tags": get_visible_tag_names(context.get("required_tags")),
        "preferred_tags": get_visible_tag_names(context.get("preferred_tags")),
        "avoid_tags": get_visible_tag_names(context.get("avoid_tags")),
        "tags": get_visible_tag_names(context.get("tags")),
    }


def build_db_recommend_reason(
    place,
    scenario,
    distance,
    matched_tags,
    match_level,
    score_breakdown=None,
    condition=None,
    metadata=None,
):
    condition = condition or build_recommendation_condition(scenario=scenario)
    metadata = metadata or {}
    intent = condition.get("intent") or condition.get("keyword") or "입력한 상황"
    confidence_text = {
        "high": "높은 편",
        "medium": "중간 수준",
        "low": "낮은 수준",
    }.get(metadata.get("confidence"), "확인 필요")
    missing_tags = metadata.get("missing_tags", [])
    required_missing_tags = metadata.get("required_missing_tags", [])
    matched_tag_labels = get_tag_display_names(matched_tags)
    missing_tag_labels = get_tag_display_names(
        missing_tags,
        hidden_label="확인되지 않은 세부 조건",
    )
    required_missing_tag_labels = get_tag_display_names(
        required_missing_tags,
        hidden_label="요청한 핵심 조건",
    )
    category_label = get_category_display_name(place.category)
    source_label = get_source_label(metadata.get("source_type"))

    parts = [f"사용자의 요청은 '{intent}'로 해석되었습니다."]

    if matched_tag_labels:
        parts.append(
            f"이 장소는 {', '.join(matched_tag_labels[:3])} 태그가 조건과 일부 일치해 {source_label} 후보로 분류되었습니다."
        )
    elif match_level == "category_distance_fallback":
        if scenario == "walk_healing":
            parts.append(
                f"이 장소는 {category_label} 카테고리와 위치 조건에는 부합하지만, "
                "산책 조건과 직접 일치하는 근거가 부족합니다."
            )
        else:
            parts.append(
                f"이 장소는 {category_label} 카테고리와 위치 조건에는 부합하지만, "
                "세부 태그 정보가 부족해 요청한 조건과 직접 일치하는 근거는 아직 부족합니다."
            )
    elif place.category:
        parts.append(f"이 장소는 {category_label} 카테고리가 입력 조건과 일부 관련됩니다.")

    if distance is not None:
        parts.append(f"현재 위치에서 약 {distance}m 떨어져 있습니다.")

    if required_missing_tag_labels:
        parts.append(
            f"다만 핵심 조건인 {', '.join(required_missing_tag_labels[:3])} 정보는 확인되지 않았습니다."
        )
    elif missing_tag_labels:
        parts.append(
            f"다만 {', '.join(missing_tag_labels[:3])} 조건은 아직 확인되지 않았습니다."
        )

    if metadata.get("source_type") == "db_category_fallback" and scenario == "walk_healing":
        parts.append("따라서 기본 산책 추천이 아니라 카테고리 기반 fallback 후보로만 보아야 합니다.")
    elif metadata.get("source_type") == "db_category_fallback":
        parts.append("따라서 검증 추천이 아니라 카테고리 기반 fallback 후보로 제공됩니다.")
    elif not metadata.get("is_verified"):
        parts.append("일부 근거가 후보 태그 기반이므로 방문 전 확인이 필요합니다.")

    if (score_breakdown or {}).get("waiting_place_penalty_reason"):
        parts.append("또한 일반적인 잠깐 휴식 목적과는 맞지 않을 수 있어 후순위로 반영했습니다.")

    if (score_breakdown or {}).get("work_cafe_penalty_reason"):
        parts.append("작업 장소로 보기에는 노트북 작업/조용함/와이파이/콘센트 같은 핵심 조건 근거가 부족합니다.")

    if (score_breakdown or {}).get("walk_healing_penalty_reason"):
        parts.append("또한 산책/힐링 목적과 직접 맞지 않을 수 있어 후순위로 반영했습니다.")

    if (score_breakdown or {}).get("frame_match_strength") == "weak":
        parts.append("사용자가 찾은 대상과 직접 일치하는 근거가 부족해 낮은 신뢰도 후보로 반영했습니다.")
    elif (score_breakdown or {}).get("frame_match_strength") == "medium":
        parts.append("장소 유형은 맞지만 사용자가 찾은 대상의 직접 근거는 방문 전 확인이 필요합니다.")

    parts.append(f"추천 신뢰도는 {confidence_text}으로 표시됩니다.")
    return " ".join(parts)


def serialize_recommendation(
    place,
    scenario,
    distance=None,
    matched_tags=None,
    score=None,
    score_breakdown=None,
    condition=None,
    frame_relevance=None,
):
    tag_data = get_place_tag_data(place)
    matched_tags = matched_tags or []
    condition = condition or build_recommendation_condition(scenario=scenario)
    required_tags = condition.get("required_tags", [])
    preferred_tags = condition.get("preferred_tags", condition.get("tags", []))

    if score is None or score_breakdown is None:
        score, matched_tags, score_breakdown = score_place(
            place=place,
            tag_data=tag_data,
            categories=condition.get("categories") or [place.category],
            preferred_tags=preferred_tags,
            required_tags=required_tags,
            avoid_tags=condition.get("avoid_tags", []),
            distance=distance,
            scenario=scenario,
        )

    category_matches = place.category in set(condition.get("categories") or [place.category])
    match_level = get_match_level(matched_tags, category_matches)
    missing_tags = _missing_tags(
        tag_data,
        required_tags=required_tags,
        preferred_tags=preferred_tags,
    )
    metadata = build_result_metadata(
        tag_data=tag_data,
        matched_tags=matched_tags,
        missing_tags=missing_tags,
        match_level=match_level,
        score_breakdown=score_breakdown,
        required_tags=required_tags,
        frame_relevance=frame_relevance,
    )
    if "score_cap" in score_breakdown:
        score_cap = score_breakdown.get("score_cap")
        score_cap_reasons = score_breakdown.get("score_cap_reasons", [])
    else:
        score, score_cap, score_cap_reasons = apply_score_cap(
            score,
            metadata,
            matched_tags,
            missing_tags,
            score_breakdown,
        )
    metadata["confidence"] = get_recommendation_confidence(score, metadata)
    labels = build_result_labels(metadata)
    score_breakdown = {
        **score_breakdown,
        "score_cap": score_cap,
        "score_cap_reasons": score_cap_reasons,
    }
    personalization_boost = round(float(score_breakdown.get("personalization_boost", 0) or 0), 2)
    personalization_reasons = score_breakdown.get("personalization_reasons", [])
    visible_matched_tags = get_visible_tag_names(matched_tags)
    visible_missing_tags = get_visible_tag_names(missing_tags)
    frame_relevance = frame_relevance or {}

    reason = build_db_recommend_reason(
        place,
        scenario,
        distance,
        matched_tags,
        match_level,
        score_breakdown,
        condition=condition,
        metadata=metadata,
    )
    kakao_place_url = get_kakao_place_url(place)

    return {
        "id": place.id,
        "name": place.name,
        "category": place.category,
        "address": place.address,
        "detail_location": place.detail_location,
        "lat": place.lat,
        "lng": place.lng,
        "distance": distance,
        "distance_m": distance,
        "score": score,
        "personalization_boost": personalization_boost,
        "personalization_reasons": personalization_reasons,
        "runtime_tags": visible_matched_tags,
        "matched_tags": visible_matched_tags,
        "missing_tags": visible_missing_tags,
        "matched_tag_labels": get_tag_display_names(visible_matched_tags),
        "missing_tag_labels": get_tag_display_names(
            missing_tags,
            hidden_label="확인되지 않은 세부 조건",
        ),
        "match_level": match_level,
        "recommendation_confidence": metadata["confidence"],
        "source_type": metadata["source_type"],
        "confidence": metadata["confidence"],
        "is_verified": metadata["is_verified"],
        "fallback_level": metadata["fallback_level"],
        "source_label": labels["source_label"],
        "confidence_label": labels["confidence_label"],
        "fallback_label": labels["fallback_label"],
        "fallback_description": labels["fallback_description"],
        "suggested_tags": tag_data["suggested_tags"],
        "verified_tags": tag_data["verified_tags"],
        "warning_tags": tag_data["warning_tags"],
        "suggested_tag_labels": get_tag_display_names(tag_data["suggested_tags"]),
        "verified_tag_labels": get_tag_display_names(tag_data["verified_tags"]),
        "warning_tag_labels": get_tag_display_names(tag_data["warning_tags"]),
        "tag_details": [
            {
                **detail,
                "display_name": get_tag_display_name(detail["name"]),
            }
            for detail in tag_data["tag_details"]
        ],
        "recommendation_reason": reason,
        "recommend_reason": reason,
        "reason": reason,
        "caution_message": metadata["caution_message"],
        "caution": metadata["caution_message"],
        "source": place.source,
        "external_id": place.external_id,
        "source_name": place.source_name,
        "kakao_place_url": kakao_place_url,
        "place_url": kakao_place_url,
        "data_quality_score": place.data_quality_score,
        "data_quality_status": place.data_quality_status,
        "raw_scores": tag_data["raw_scores"],
        "score_breakdown": score_breakdown,
        "matched_evidence": frame_relevance.get("matched_evidence", []),
        "matched_category_codes": frame_relevance.get("matched_category_codes", []),
        "relevance_score": frame_relevance.get("relevance_score", 0),
        "relevance_source": frame_relevance.get("relevance_source", ""),
        "frame_match_strength": frame_relevance.get("match_strength", ""),
        "frame_evidence_tier": frame_relevance.get("evidence_tier", ""),
        "evidence_sort_rank": frame_relevance.get("evidence_sort_rank"),
        "excluded_reason": frame_relevance.get("excluded_reason", ""),
        "place_natures": frame_relevance.get("place_natures", []),
        "plan_source": condition.get("plan_source", ""),
        "execution_mode": condition.get("execution_mode", ""),
    }


def search_db_recommendations(
    scenario="work_cafe",
    condition=None,
    lat=None,
    lng=None,
    categories=None,
    tags=None,
    keyword=None,
    exclude_categories=None,
    limit=10,
    radius=None,
    user=None,
    search_plan=None,
    place_intent_frame=None,
):
    lat = _parse_float(lat)
    lng = _parse_float(lng)
    limit = min(max(_parse_int(limit, 10), 1), 50)

    context = normalize_recommendation_context(
        scenario=scenario,
        condition=condition,
        categories=categories,
        tags=tags,
        keyword=keyword,
        exclude_categories=exclude_categories,
        radius=radius,
    )
    frame = _normalize_frame_for_recommendation(search_plan, place_intent_frame)
    frame_mode = _is_valid_recommendation_frame(frame)
    if frame_mode:
        context["execution_mode"] = "frame"
        context["plan_source"] = (
            (search_plan or {}).get("plan_source")
            or (search_plan or {}).get("planSource")
            or "ai"
        )
        context["place_intent_frame"] = frame
        context["categories"] = frame["candidate_category_codes"]
        context["required_tags"] = []
        context["preferred_tags"] = []
        context["avoid_tags"] = []
        context["tags"] = []
        context["keywords"] = frame["search_queries"] or frame["candidate_place_types"]
        context["fallback_enabled"] = False
    else:
        context["execution_mode"] = "legacy"
        context["plan_source"] = "legacy_fallback"
    min_radius = get_min_radius(context["scenario"])
    radius = min(
        max(
            _parse_int(radius, context.get("radius") or get_default_radius(context["scenario"])),
            min_radius,
        ),
        20000,
    )
    context["radius"] = radius
    preference_lookup = get_user_preference_lookup(user)

    if frame_mode and not context["categories"]:
        response_condition = build_response_condition(context)
        return {
            "scenario": context["scenario"],
            "keyword": context["keyword"],
            "condition": response_condition,
            "recommendation_condition": response_condition,
            "conditions": {
                "categories": context["categories"],
                "exclude_categories": context["exclude_categories"],
                "required_tags": response_condition["required_tags"],
                "preferred_tags": response_condition["preferred_tags"],
                "avoid_tags": response_condition["avoid_tags"],
                "tags": response_condition["tags"],
                "required_tag_labels": [],
                "preferred_tag_labels": [],
                "avoid_tag_labels": [],
                "keywords": context["keywords"],
                "fallback_enabled": context["fallback_enabled"],
                "lat": lat,
                "lng": lng,
                "radius": radius,
                "limit": limit,
                "execution_mode": context["execution_mode"],
                "plan_source": context["plan_source"],
                "place_intent_frame": frame,
            },
            "results": [],
            "count": 0,
            "relevant_result_count": 0,
            "execution_mode": context["execution_mode"],
            "plan_source": context["plan_source"],
            "place_intent_frame": frame,
        }

    base_places = Place.objects.filter(category__in=context["categories"])

    if context["exclude_categories"]:
        base_places = base_places.exclude(category__in=context["exclude_categories"])

    distance_by_place_id = {}
    candidate_ids = []

    if lat is not None and lng is not None:
        nearby = []
        bounds = _get_coordinate_bounds(lat, lng, radius)
        bounded_places = base_places.filter(
            lat__gte=bounds["lat_min"],
            lat__lte=bounds["lat_max"],
            lng__gte=bounds["lng_min"],
            lng__lte=bounds["lng_max"],
        )

        for place in bounded_places.only("id", "lat", "lng").iterator(chunk_size=2000):
            distance = calculate_distance_m(lat, lng, place.lat, place.lng)
            if distance > radius:
                continue

            distance_by_place_id[place.id] = distance
            nearby.append((distance, place.id))

        nearby.sort(key=lambda item: item[0])
        candidate_ids = [place_id for _, place_id in nearby[: max(limit * 300, 500)]]
    else:
        candidate_ids = list(
            base_places
            .order_by("-data_quality_score", "-updated_at")
            .values_list("id", flat=True)[: max(limit * 300, 500)]
        )

    places = (
        Place.objects
        .filter(id__in=candidate_ids)
        .prefetch_related("place_tags__tag")
    )
    places_by_id = {place.id: place for place in places}

    candidates = []
    frame_policy_scenario = _frame_policy_scenario(frame) if frame_mode else ""
    ranking_policy = _frame_ranking_policy(frame) if frame_mode else ""

    for place_id in candidate_ids:
        place = places_by_id.get(place_id)
        if not place:
            continue

        distance = distance_by_place_id.get(place.id)
        tag_data = get_place_tag_data(place)
        frame_relevance = {}
        if frame_mode:
            excluded_reason = _get_frame_excluded_reason(place, tag_data, frame)
            if excluded_reason:
                continue
            frame_relevance = _evaluate_frame_relevance(place, tag_data, frame)
            if not frame_relevance["is_relevant"]:
                continue

        score, matched_tags, score_breakdown = score_place(
            place=place,
            tag_data=tag_data,
            categories=context["categories"],
            preferred_tags=context["preferred_tags"],
            required_tags=context["required_tags"],
            avoid_tags=context["avoid_tags"],
            distance=distance,
            scenario=frame_policy_scenario if frame_mode else context["scenario"],
        )

        if score_breakdown.get("excluded_by_waiting_place"):
            continue
        if score_breakdown.get("excluded_by_work_cafe"):
            continue
        if score_breakdown.get("excluded_by_walk_healing"):
            continue

        if frame_mode:
            score_breakdown["frame_match_strength"] = frame_relevance.get("match_strength", "")
            score_breakdown["frame_has_target_evidence"] = frame_relevance.get("has_target_evidence", False)
            score_breakdown["frame_evidence_tier"] = frame_relevance.get("evidence_tier", "")
            score_breakdown["frame_evidence_sort_rank"] = frame_relevance.get("evidence_sort_rank")

        missing_tags = _missing_tags(
            tag_data,
            required_tags=context["required_tags"],
            preferred_tags=context["preferred_tags"],
        )
        category_matches = place.category in set(context["categories"])
        match_level = get_match_level(matched_tags, category_matches)
        if (
            not context["fallback_enabled"]
            and match_level == "category_distance_fallback"
            and context["required_tags"]
            and not set(matched_tags).intersection(context["required_tags"])
        ):
            continue

        metadata = build_result_metadata(
            tag_data=tag_data,
            matched_tags=matched_tags,
            missing_tags=missing_tags,
            match_level=match_level,
            score_breakdown=score_breakdown,
            required_tags=context["required_tags"],
            frame_relevance=frame_relevance,
        )
        score, score_cap, score_cap_reasons = apply_score_cap(
            score,
            metadata,
            matched_tags,
            missing_tags,
            score_breakdown,
        )
        frame_score_penalty = frame_relevance.get("score_penalty", 0) if frame_mode else 0
        if frame_score_penalty:
            score = max(0, score - frame_score_penalty)
            score_breakdown["frame_relevance_penalty"] = frame_score_penalty
            score_breakdown["frame_relevance_penalty_reason"] = frame_relevance.get(
                "score_penalty_reason",
                "",
            )
        base_score = score
        personalization_boost, personalization_reasons = calculate_personalization_boost(
            place=place,
            tag_data=tag_data,
            scenario=frame_policy_scenario if frame_mode else context["scenario"],
            preference_lookup=preference_lookup,
        )
        score = min(round(base_score + personalization_boost, 2), 100)
        score_breakdown = {
            **score_breakdown,
            "base_score": base_score,
            "personalization_boost": round(score - base_score, 2),
            "personalization_reasons": personalization_reasons,
            "score_cap": score_cap,
            "score_cap_reasons": score_cap_reasons,
        }

        candidates.append((
            score,
            distance if distance is not None else 999999999,
            place,
            matched_tags,
            score_breakdown,
            frame_relevance,
        ))

    if frame_mode:
        candidates.sort(key=lambda item: (
            _frame_evidence_sort_rank(item[5]),
            item[1],
            -item[0],
            item[2].id,
        ))
    elif ranking_policy == "urgent_nearest":
        candidates.sort(key=lambda item: (item[1], -item[0], item[2].id))
    else:
        candidates.sort(key=lambda item: (-item[0], item[1], item[2].id))

    results = []
    for score, distance, place, matched_tags, score_breakdown, frame_relevance in candidates[:limit]:
        normalized_distance = None if distance == 999999999 else distance
        results.append(
            serialize_recommendation(
                place=place,
                scenario=context["scenario"],
                distance=normalized_distance,
                matched_tags=matched_tags,
                score=score,
                score_breakdown=score_breakdown,
                condition=context,
                frame_relevance=frame_relevance,
            )
        )

    response_condition = build_response_condition(context)

    return {
        "scenario": context["scenario"],
        "keyword": context["keyword"],
        "condition": response_condition,
        "recommendation_condition": response_condition,
        "conditions": {
            "categories": context["categories"],
            "exclude_categories": context["exclude_categories"],
            "required_tags": response_condition["required_tags"],
            "preferred_tags": response_condition["preferred_tags"],
            "avoid_tags": response_condition["avoid_tags"],
            "tags": response_condition["tags"],
            "required_tag_labels": get_tag_display_names(
                context["required_tags"],
                hidden_label="요청한 핵심 조건",
            ),
            "preferred_tag_labels": get_tag_display_names(
                context["preferred_tags"],
                hidden_label="요청한 세부 조건",
            ),
            "avoid_tag_labels": get_tag_display_names(
                context["avoid_tags"],
                hidden_label="피해야 할 조건",
            ),
            "keywords": context["keywords"],
            "fallback_enabled": context["fallback_enabled"],
            "lat": lat,
            "lng": lng,
            "radius": radius,
            "limit": limit,
            "execution_mode": context["execution_mode"],
            "plan_source": context["plan_source"],
            "place_intent_frame": frame if frame_mode else {},
        },
        "results": results,
        "count": len(results),
        "relevant_result_count": len(results),
        "execution_mode": context["execution_mode"],
        "plan_source": context["plan_source"],
        "place_intent_frame": frame if frame_mode else {},
    }
