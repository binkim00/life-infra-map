import json
import logging
import re

from django.conf import settings

from recommendations.services.ai_situation_parser import (
    ALLOWED_CATEGORIES,
    ALLOWED_SCENARIOS,
    ALLOWED_TAGS,
    _call_gms_chat_json,
)


logger = logging.getLogger(__name__)

CLARIFICATION_MESSAGE = "어느 지역이나 기준 위치에서 찾을지 알려주시면 더 정확히 찾아드릴게요."
PURPOSE_CLARIFICATION_MESSAGE = (
    "어떤 상황의 장소를 찾으시나요? 지역과 목적을 함께 입력해 주세요. "
    "예: 서면역 조용한 카페, 하단역 산책할 곳, 광안리 잠깐 쉴 곳"
)
REFINEMENT_CLARIFICATION_MESSAGE = (
    "이전 검색 결과가 없어서 어떤 장소를 다시 찾으려는지 알 수 없습니다. "
    "지역과 원하는 장소 종류를 함께 입력해 주세요. 예: 서면역 조용한 카페, 하단역 산책할 곳"
)
OUT_OF_SCOPE_MESSAGE = "이 서비스는 생활 장소 추천을 위한 서비스라 해당 질문은 도와드리기 어렵습니다."
BLOCKED_MESSAGE = "해당 요청은 안전상 안내하기 어렵습니다."

ROUTER_ACTIONS = {
    "search",
    "ask_clarification",
    "out_of_scope",
    "blocked",
    "refine_previous_search",
}

AI_SCENARIO_ALIASES = {
    "study_room": "work_cafe",
    "study_cafe": "work_cafe",
    "workspace": "work_cafe",
    "work_space": "work_cafe",
    "cafe_work": "work_cafe",
    "rest": "waiting_place",
    "rest_place": "waiting_place",
    "walking": "walk_healing",
    "walk": "walk_healing",
    "smoking": "smoking_area",
    "smoking_zone": "smoking_area",
}

LOCATION_SUFFIXES = (
    "특별자치시",
    "특별자치도",
    "광역시",
    "특별시",
    "해수욕장",
    "대학교",
    "공항",
    "터미널",
    "시장",
    "역",
    "구",
    "군",
    "시",
    "읍",
    "면",
    "동",
    "리",
    "대",
)

COMMAND_PATTERNS = [
    r"추천\s*해\s*줘",
    r"추천해줘",
    r"추천",
    r"찾아\s*줘",
    r"찾아줘",
    r"찾아",
    r"알려\s*줘",
    r"알려줘",
    r"좀",
]

MENU_KEYWORDS = [
    "소금빵",
    "브런치",
    "디저트",
    "쌀국수",
    "파스타",
    "돈까스",
    "돈가스",
    "커피",
    "빵",
]

PLACE_TYPE_KEYWORDS = {
    "소금빵": ["베이커리", "빵집", "카페"],
    "브런치": ["카페"],
    "디저트": ["카페", "베이커리", "빵집"],
    "쌀국수": ["식당", "음식점"],
    "파스타": ["식당", "음식점"],
    "돈까스": ["식당", "음식점"],
    "돈가스": ["식당", "음식점"],
    "커피": ["카페"],
    "빵": ["베이커리", "빵집", "카페"],
}

SCENARIO_RULES = [
    (
        "smoking_area",
        ["흡연구역", "흡연장", "흡연", "담배필", "담배 필", "담배피", "담배 피", "담배", "피울 수 있는 곳", "피울수있는곳"],
        ["smoking_area"],
        ["흡연구역"],
        ["실외흡연구역"],
    ),
    (
        "walk_healing",
        ["산책", "힐링", "걷", "야경", "전망", "공원", "바다", "해변"],
        ["city_park", "tourism", "beach"],
        ["공원", "산책로", "전망대"],
        ["산책좋음", "힐링"],
    ),
    (
        "work_cafe",
        ["작업", "노트북", "공부", "조용", "콘센트", "와이파이", "카페", "카공"],
        ["cafe"],
        ["카페", "작업 카페", "스터디카페"],
        ["조용한", "노트북작업", "콘센트있음", "와이파이"],
    ),
    (
        "waiting_place",
        ["잠깐", "잠시", "쉬", "쉴", "앉", "대기", "기다", "실내", "쉼터"],
        ["cafe", "shelter"],
        ["카페", "쉼터", "실내 쉼터"],
        ["잠깐쉬기좋음", "실내쉼터"],
    ),
    (
        "restaurant",
        ["맛집", "먹", "밥", "식사", "식당", "음식점", "브런치", "소금빵", "쌀국수", "디저트", "빵"],
        ["restaurant", "cafe"],
        ["식당", "카페"],
        ["식사가능"],
    ),
]

CONDITION_RULES = [
    ("혼자", "혼자 이용하기 좋음", "혼자이용좋음"),
    ("혼밥", "혼자 이용하기 좋음", "혼자이용좋음"),
    ("눈치", "혼자 이용하기 좋음", "혼자이용좋음"),
    ("조용", "조용함", "조용한"),
    ("노트북", "노트북 작업 가능", "노트북작업"),
    ("작업", "노트북 작업 가능", "노트북작업"),
    ("사람", "붐비지 않음", "조용한"),
    ("붐비", "붐비지 않음", "조용한"),
    ("콘센트", "콘센트 있음", "콘센트있음"),
    ("와이파이", "와이파이 있음", "와이파이"),
    ("wifi", "와이파이 있음", "와이파이"),
    ("비", "비 피하기 좋음", "실내쉼터"),
    ("밖 말고", "실내", "실내쉼터"),
    ("실외 말고", "실내", "실내쉼터"),
    ("앉", "앉을 수 있음", "잠깐쉬기좋음"),
    ("쉬", "잠깐 쉬기 좋음", "잠깐쉬기좋음"),
    ("실내", "실내 이용 가능", "실내쉼터"),
    ("산책", "산책하기 좋음", "산책좋음"),
    ("걷", "걷기 좋음", "산책좋음"),
    ("바람", "바람 쐬기 좋음", "힐링"),
    ("힐링", "힐링하기 좋음", "힐링"),
    ("카페 말고", "카페 제외", ""),
    ("카페 느낌", "카페 느낌 아님", ""),
    ("야경", "야경 보기 좋음", "야경"),
    ("흡연", "흡연 가능", "실외흡연구역"),
]

AMBIGUOUS_REFERENCE_KEYWORDS = [
    "거기",
    "그곳",
    "아까",
    "방금",
    "그중",
    "저기",
]

REFINEMENT_KEYWORDS = [
    "대신",
    "더",
    "다른",
    "가까운",
    "가까이",
    "만",
    "빼",
    "제외",
    "보여줘",
]

REFINEMENT_CONTEXT_PHRASES = [
    "거기 말고",
    "아까 거 말고",
    "아까거 말고",
    "이전 결과 말고",
    "그중에서",
    "다른 데",
    "다른데",
    "다른 곳",
    "다른곳",
    "좀 더 가까운 데",
    "더 가까운 데",
    "더 조용한 데",
    "카페만",
    "공원은 빼",
    "와이파이 되는 곳만",
]

NEGATIVE_PREFERENCE_PHRASES = [
    "밖 말고",
    "실외 말고",
    "사람 많은 데 말고",
    "사람 너무 많은 데 말고",
    "붐비는 데 말고",
    "붐비지 않는",
    "카페 말고",
    "카페 느낌은 아니",
    "카페 같지 않은",
    "카페느낌은아니",
    "카페는 싫",
    "카페 싫",
    "카페 빼고",
]

CATEGORY_LIKE_CONDITION_VALUES = {
    "카페",
    "공원",
    "맛집",
    "쉴 곳",
    "쉴곳",
    "산책할 곳",
    "산책할곳",
    "흡연구역",
    "식당",
    "음식점",
    "쉼터",
}

OUT_OF_SCOPE_KEYWORDS = [
    "비트코인",
    "주식",
    "코인",
    "투자",
    "매수",
    "매도",
    "숙제",
    "과제",
    "파이썬",
    "정치",
    "뉴스",
    "연애",
    "의료",
    "감기약",
    "법률",
    "법적",
    "계약서",
    "소송",
    "진단",
]

BLOCKED_KEYWORDS = [
    "불법",
    "위험한 요청",
    "위험한 행동",
    "마약",
    "도박",
    "폭탄",
    "무기",
    "해킹",
    "몰래",
    "스토킹",
    "침입",
    "방화",
    "범죄",
]

PLACE_RECOMMENDATION_HINTS = [
    "장소",
    "곳",
    "데",
    "근처",
    "주변",
    "카페",
    "맛집",
    "산책",
    "쉴",
    "쉬",
    "작업",
    "공부",
    "노트북",
    "공원",
    "화장실",
    "주차장",
    "와이파이",
    "흡연",
    "쉼터",
    "식당",
    "밥",
    "먹",
    "역",
]

AI_INTENT_FALLBACK_HINTS = [
    "눈치",
    "바람쐬",
    "바람 쐬",
    "펴도",
    "많은 데 말고",
    "많은데 말고",
    "카페 느낌",
    "밖 말고",
    "앉아있",
    "있고 싶은데",
    "카페 말고",
    "실외 말고",
    "붐비지",
]

SEARCH_COMMAND_HINTS = [
    "추천",
    "찾아",
    "알려",
    "어디",
]


def build_conversational_search_plan(
    query,
    user=None,
    lat=None,
    lng=None,
    map_center=None,
    previous_context=None,
):
    normalized_query = _clean_text(query)
    if not normalized_query:
        return _finalize_router_plan(_empty_plan(query))

    rule_plan = _build_rule_plan(
        normalized_query,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )
    if not _should_use_ai_intent_fallback(
        normalized_query,
        rule_plan,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    ):
        return _finalize_router_plan(rule_plan)

    ai_plan = _build_ai_plan(normalized_query, rule_plan)

    if not ai_plan:
        return _finalize_router_plan(rule_plan)

    normalized_ai_plan = _normalize_ai_plan(
        ai_plan,
        query=normalized_query,
        fallback_plan=rule_plan,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )
    return _finalize_router_plan(normalized_ai_plan or rule_plan)


def _empty_plan(query):
    return {
        "action": "ask_clarification",
        "user_intent_summary": "검색어를 입력해 주세요.",
        "location": _location_payload("", False, "current_location"),
        "targets": [],
        "conditions": [],
        "preferences": [],
        "avoid": [],
        "search_plan": _search_plan_payload(
            original_query=query or "",
            location_query="",
            target_query="",
            scenario="waiting_place",
            categories=["cafe", "shelter"],
            menu_keywords=[],
            place_type_keywords=[],
            required_tags=[],
            preferred_tags=[],
            requested_conditions=[],
        ),
        "execution_policy": _execution_policy(False, False),
        "needs_clarification": True,
        "clarification_question": "어떤 장소를 찾고 싶은지 알려주세요.",
        "confidence": 0,
        "fallback_reason": "empty_query",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _build_rule_plan(query, lat=None, lng=None, map_center=None, previous_context=None):
    if _is_blocked_query(query):
        return _blocked_plan(query)

    if _is_out_of_scope_query(query):
        return _out_of_scope_plan(query)

    location_query, target_query = _extract_location_and_target(query)
    has_explicit_location = bool(location_query)
    fallback_location = "" if has_explicit_location else "current_location"
    has_previous_context = bool(previous_context)
    has_ambiguous_reference = _has_any(query, AMBIGUOUS_REFERENCE_KEYWORDS)
    has_refinement = _is_refinement_request(query)
    has_location_context = has_explicit_location or _has_coordinate_context(lat, lng, map_center)

    if has_refinement and not has_previous_context and not has_explicit_location:
        return _clarification_plan(
            query,
            question=REFINEMENT_CLARIFICATION_MESSAGE,
            reason="refinement_without_context",
            target_query=target_query,
            fallback_location=fallback_location,
        )

    if has_ambiguous_reference and not has_previous_context and not has_explicit_location:
        return _clarification_plan(
            query,
            question=CLARIFICATION_MESSAGE,
            reason="ambiguous_reference_without_context",
            target_query=target_query,
            fallback_location=fallback_location,
        )

    scenario, categories, kakao_keywords, preferred_tags = _pick_scenario(query, target_query)
    scenario, categories, kakao_keywords, preferred_tags = _apply_query_intent_overrides(
        query,
        scenario,
        categories,
        kakao_keywords,
        preferred_tags,
    )
    if _is_vague_place_request(query, scenario, target_query):
        return _clarification_plan(
            query,
            question=PURPOSE_CLARIFICATION_MESSAGE,
            reason="missing_purpose",
            target_query=target_query,
            fallback_location=fallback_location,
        )

    if not has_location_context and _requires_location_before_search(query, scenario, target_query):
        return _clarification_plan(
            query,
            question=_missing_location_question(query, scenario),
            reason="missing_location_context",
            target_query=_target_query_for_scenario(scenario),
            fallback_location=fallback_location,
        )

    if has_previous_context and has_refinement:
        return _refine_previous_search_plan(query, previous_context)

    conditions = [] if scenario == "smoking_area" else _extract_conditions(query)
    menu_keywords = _extract_menu_keywords(query)
    place_type_keywords = _extract_place_type_keywords(query, menu_keywords, scenario)
    if _has_cafe_negative_preference(query):
        place_type_keywords = [
            keyword
            for keyword in place_type_keywords
            if "카페" not in keyword
        ]
    target_query = _clean_target_query(target_query or _derive_target_query(query, scenario, menu_keywords))
    target_query = _fallback_target_query(target_query, scenario, menu_keywords)
    if scenario == "smoking_area":
        target_query = "흡연구역"
    elif scenario == "walk_healing" and _has_any(query, ["바람", "걷", "산책", "힐링"]):
        target_query = "산책할 곳"
    elif scenario == "waiting_place" and _has_waiting_place_natural_intent(query):
        target_query = "쉴 곳"
    elif scenario == "work_cafe" and _has_any(
        query,
        ["작업", "노트북", "공부", "카공", "콘센트", "와이파이", "조용"],
    ):
        target_query = "카페"

    preferred_tags = _unique([
        *preferred_tags,
        *[tag for _, _, tag in _matched_condition_rules(query) if tag],
    ])
    preferred_tags = [tag for tag in preferred_tags if tag in ALLOWED_TAGS or tag]
    conditions = _sanitize_requested_conditions(conditions)

    return {
        "action": "search",
        "user_intent_summary": _build_intent_summary(location_query, target_query, scenario, conditions),
        "location": _location_payload(location_query, has_explicit_location, fallback_location),
        "targets": _unique([target_query, *menu_keywords, *place_type_keywords]),
        "conditions": conditions,
        "preferences": preferred_tags,
        "avoid": _extract_avoid_terms(query),
        "search_plan": {
            **_search_plan_payload(
            original_query=query,
            location_query=location_query,
            target_query=target_query,
            scenario=scenario,
            categories=categories,
            menu_keywords=menu_keywords,
            place_type_keywords=place_type_keywords,
            required_tags=[],
            preferred_tags=preferred_tags,
            requested_conditions=conditions,
            kakao_keyword_candidates=_unique([*kakao_keywords, target_query, *place_type_keywords]),
            ),
            "excluded_categories": _extract_excluded_categories(query),
        },
        "execution_policy": _execution_policy(True, has_explicit_location),
        "needs_clarification": False,
        "clarification_question": "",
        "confidence": 82 if has_explicit_location else 72,
        "fallback_reason": "rule_based_planner",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _clarification_plan(
    query,
    question,
    reason,
    target_query="",
    fallback_location="current_location",
):
    conditions = _extract_conditions(query)
    return {
        "action": "ask_clarification",
        "user_intent_summary": question,
        "message": question,
        "location": _location_payload("", False, fallback_location),
        "targets": [],
        "conditions": _sanitize_requested_conditions(conditions),
        "preferences": [],
        "avoid": [],
        "search_plan": _search_plan_payload(
            original_query=query,
            location_query="",
            target_query=_clean_target_query(target_query or query),
            scenario="waiting_place",
            categories=["cafe", "shelter"],
            menu_keywords=[],
            place_type_keywords=[],
            required_tags=[],
            preferred_tags=[],
            requested_conditions=_sanitize_requested_conditions(conditions),
        ),
        "execution_policy": _execution_policy(False, False),
        "needs_clarification": True,
        "clarification_question": question,
        "confidence": 45,
        "fallback_reason": reason,
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _out_of_scope_plan(query):
    return {
        "action": "out_of_scope",
        "intent_type": "out_of_scope",
        "user_intent_summary": "장소 추천 범위 밖 요청입니다.",
        "message": OUT_OF_SCOPE_MESSAGE,
        "location": _location_payload("", False, ""),
        "targets": [],
        "conditions": [],
        "preferences": [],
        "avoid": [],
        "search_plan": {},
        "execution_policy": _execution_policy(False, False),
        "needs_clarification": False,
        "clarification_question": "",
        "blocked_reason": "",
        "out_of_scope_reason": "not_place_recommendation",
        "confidence": 90,
        "fallback_reason": "out_of_scope_rule",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _blocked_plan(query):
    return {
        "action": "blocked",
        "intent_type": "unsafe_request",
        "user_intent_summary": "안전상 처리할 수 없는 요청입니다.",
        "message": BLOCKED_MESSAGE,
        "location": _location_payload("", False, ""),
        "targets": [],
        "conditions": [],
        "preferences": [],
        "avoid": [],
        "search_plan": {},
        "execution_policy": _execution_policy(False, False),
        "needs_clarification": False,
        "clarification_question": "",
        "blocked_reason": "unsafe_request",
        "out_of_scope_reason": "",
        "confidence": 95,
        "fallback_reason": "blocked_rule",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _refine_previous_search_plan(query, previous_context):
    previous_context = previous_context or {}
    previous_search_plan = previous_context.get("search_plan") or {}
    if not isinstance(previous_search_plan, dict):
        previous_search_plan = {}

    additional_conditions = _sanitize_requested_conditions(_extract_conditions(query))
    location_query = _clean_text(
        previous_search_plan.get("locationQuery")
        or previous_search_plan.get("location_query")
        or previous_search_plan.get("baseLocationQuery")
        or previous_search_plan.get("base_location_query")
    )
    target_query = _clean_target_query(
        previous_search_plan.get("targetQuery")
        or previous_search_plan.get("target_query")
        or previous_search_plan.get("targetKeyword")
        or previous_search_plan.get("target_keyword")
        or _derive_target_query(query, "waiting_place", [])
    )
    scenario = _normalize_scenario(previous_search_plan.get("scenario"))
    categories = _normalize_categories(previous_search_plan.get("categories") or [])
    if not categories:
        categories = ["cafe", "shelter"] if scenario == "waiting_place" else ["cafe"]

    search_plan = _search_plan_payload(
        original_query=query,
        location_query=location_query,
        target_query=target_query,
        scenario=scenario,
        categories=categories,
        menu_keywords=_normalize_text_list(previous_search_plan.get("menu_keywords") or []),
        place_type_keywords=_normalize_text_list(previous_search_plan.get("place_type_keywords") or []),
        required_tags=_normalize_tags(previous_search_plan.get("required_tags") or []),
        preferred_tags=_unique([
            *_normalize_tags(previous_search_plan.get("preferred_tags") or []),
            *[tag for _, _, tag in _matched_condition_rules(query) if tag],
        ]),
        requested_conditions=_unique([
            *_normalize_text_list(
                previous_search_plan.get("requestedConditions")
                or previous_search_plan.get("requested_conditions")
                or []
            ),
            *additional_conditions,
        ]),
        kakao_keyword_candidates=_normalize_text_list(
            previous_search_plan.get("kakaoKeywordCandidates")
            or previous_search_plan.get("kakao_keyword_candidates")
            or [target_query]
        ),
    )
    search_plan["additional_conditions"] = additional_conditions
    search_plan["sort_hint"] = "distance" if _has_any(query, ["가까운", "가까이"]) else ""
    search_plan["category_filter"] = _extract_category_filter(query)
    search_plan["exclude_terms"] = _extract_avoid_terms(query)

    return {
        "action": "refine_previous_search",
        "intent_type": "place_recommendation",
        "user_intent_summary": "이전 검색 결과를 더 좁히는 요청입니다.",
        "message": "",
        "location": _location_payload(location_query, bool(location_query), "current_location"),
        "targets": _normalize_text_list([target_query]),
        "conditions": additional_conditions,
        "preferences": search_plan["preferred_tags"],
        "avoid": search_plan["exclude_terms"],
        "search_plan": search_plan,
        "execution_policy": _execution_policy(False, bool(location_query)),
        "needs_clarification": False,
        "clarification_question": "",
        "confidence": 78,
        "fallback_reason": "refine_previous_search_rule",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _finalize_router_plan(plan):
    plan = plan or _empty_plan("")
    action = plan.get("action")
    if action not in ROUTER_ACTIONS:
        action = "ask_clarification"
    plan["action"] = action

    if "intent_type" not in plan:
        if action == "blocked":
            plan["intent_type"] = "unsafe_request"
        elif action == "out_of_scope":
            plan["intent_type"] = "out_of_scope"
        else:
            plan["intent_type"] = "place_recommendation"

    plan.setdefault("user_intent_summary", "")
    plan.setdefault("message", "")
    plan.setdefault("search_plan", {} if action in {"blocked", "out_of_scope"} else _empty_plan("")["search_plan"])
    plan.setdefault("blocked_reason", "unsafe_request" if action == "blocked" else "")
    plan.setdefault("out_of_scope_reason", "not_place_recommendation" if action == "out_of_scope" else "")
    plan.setdefault("confidence", 0.0)
    plan.setdefault("clarification_question", "")

    if action == "ask_clarification":
        plan["needs_clarification"] = True
        plan["clarification_question"] = plan.get("clarification_question") or plan.get("message") or CLARIFICATION_MESSAGE
        plan["message"] = plan.get("message") or plan["clarification_question"]
        plan["execution_policy"] = _execution_policy(False, False)
    elif action in {"blocked", "out_of_scope"}:
        plan["needs_clarification"] = False
        plan["message"] = plan.get("message") or (BLOCKED_MESSAGE if action == "blocked" else OUT_OF_SCOPE_MESSAGE)
        plan["search_plan"] = {}
        plan["execution_policy"] = _execution_policy(False, False)
    else:
        plan["needs_clarification"] = False
        plan.setdefault("execution_policy", _execution_policy(action == "search", False))

    return plan


def _should_use_ai_intent_fallback(query, rule_plan, lat=None, lng=None, map_center=None, previous_context=None):
    if getattr(settings, "CONVERSATIONAL_SEARCH_AI_ENABLED", False) is not True:
        return False

    if getattr(settings, "AI_PROVIDER", "gms").lower() != "gms":
        return False

    action = rule_plan.get("action")
    search_plan = rule_plan.get("search_plan") if isinstance(rule_plan.get("search_plan"), dict) else {}
    scenario = search_plan.get("scenario")

    if action in {"blocked", "out_of_scope", "refine_previous_search"}:
        return False

    if action == "ask_clarification" and rule_plan.get("fallback_reason") in {
        "missing_purpose",
        "refinement_without_context",
        "ambiguous_reference_without_context",
    }:
        return False

    if scenario == "smoking_area":
        return False

    if _has_any(query, AI_INTENT_FALLBACK_HINTS):
        return True

    if action == "search" and not _has_any(query, SEARCH_COMMAND_HINTS):
        return True

    return False


def _categories_for_scenario(scenario):
    for rule_scenario, _, categories, _, _ in SCENARIO_RULES:
        if rule_scenario == scenario:
            return list(categories)
    return ["cafe", "shelter"] if scenario == "waiting_place" else ["cafe"]


def _normalize_ai_scenario(value, target_query="", fallback="waiting_place"):
    scenario = _clean_text(value)
    if scenario in ALLOWED_SCENARIOS:
        return scenario

    scenario = AI_SCENARIO_ALIASES.get(scenario, scenario)
    if scenario in ALLOWED_SCENARIOS:
        return scenario

    target_text = _compact(target_query)
    if any(keyword in target_text for keyword in ["스터디", "작업", "노트북", "카페"]):
        return "work_cafe"
    if any(keyword in target_text for keyword in ["산책", "걷", "바람", "공원"]):
        return "walk_healing"
    if any(keyword in target_text for keyword in ["흡연", "담배"]):
        return "smoking_area"

    return fallback if fallback in ALLOWED_SCENARIOS else "waiting_place"


def _looks_like_ai_generated_address_or_coordinate(value):
    text = _clean_text(value)
    if not text:
        return False
    if re.search(r"\d+\.\d+\s*,\s*\d+\.\d+", text):
        return True
    if re.search(r"\d{2,}\s*(?:번길|길|로|번지)", text):
        return True
    return any(keyword in text for keyword in ["위도", "경도", "주소:", "도로명"])


def _sanitize_ai_location_query(value):
    text = _clean_location_text(value)
    if not text or _looks_like_ai_generated_address_or_coordinate(text):
        return ""
    if len(text) > 30:
        return ""
    return text


def _sanitize_ai_target_query(value, scenario, fallback_target=""):
    text = _clean_target_query(value)
    if _looks_like_ai_generated_address_or_coordinate(text):
        text = ""

    if scenario == "work_cafe":
        if not text or any(keyword in _compact(text) for keyword in ["스터디", "작업", "노트북", "카페"]):
            return "카페"
    if scenario == "walk_healing":
        if not text or any(keyword in _compact(text) for keyword in ["산책", "걷", "바람", "공원"]):
            return "산책할 곳"
    if scenario == "waiting_place":
        if not text or any(keyword in _compact(text) for keyword in ["쉬", "쉴", "앉", "쉼"]):
            return "쉴 곳"
    if scenario == "smoking_area":
        return "흡연구역"

    return text or fallback_target or _derive_target_query("", scenario, [])


def _build_ai_plan(query, fallback_plan):
    if getattr(settings, "CONVERSATIONAL_SEARCH_AI_ENABLED", False) is not True:
        return None

    provider = getattr(settings, "AI_PROVIDER", "gms").lower()
    if provider != "gms":
        return None

    try:
        return _call_gms_chat_json(
            query=json.dumps(
                {
                    "query": query,
                    "fallback_plan": fallback_plan,
                },
                ensure_ascii=False,
            ),
            system_prompt=CONVERSATIONAL_SEARCH_SYSTEM_PROMPT,
            max_completion_tokens=900,
        )
    except Exception:
        logger.debug("Conversational search planner AI call failed.", exc_info=True)
        return None


CONVERSATIONAL_SEARCH_SYSTEM_PROMPT = """
너는 장소 추천 서비스의 자연어 검색 해석기다. 실제 장소 추천 결과를 만들지 말고 검색 계획만 JSON으로 반환한다.

반드시 지킬 규칙:
- JSON object만 반환한다.
- 장소명, 주소, 좌표, 영업 여부, 시설 여부, 메뉴 제공 여부를 새로 만들거나 단정하지 않는다.
- 사용자가 명시한 지역/역/장소명은 현재 위치나 지도 중심으로 덮어쓰지 않는다.
- 위치가 명시되지 않으면 location.fallback에 current_location 또는 map_center를 넣고 location.text는 비워둔다.
- "거기", "아까", "그곳"처럼 이전 맥락이 필요한 표현인데 previous_context가 없으면 action은 ask_clarification으로 둔다.
- "밖 말고", "실외 말고", "사람 많은 데 말고", "붐비는 데 말고"는 이전 결과 refine이 아니라 신규 검색의 부정/선호 조건으로 본다.
- "카페 말고", "카페 느낌은 아니었으면", "카페 같지 않은"은 카페 검색이 아니라 waiting_place의 카페 제외 의도로 본다.
- "쪽에서", "쪽", "근처", "주변", "앞" 같은 위치 접미사는 locationQuery에서 제거한다.
- walk_healing은 targetQuery를 "공원"으로 좁히지 말고 "산책할 곳"처럼 넓게 유지한다.
- 장소 추천과 무관한 일반 질문은 out_of_scope로 둔다.
- 불법적이거나 위험한 장소 이용 요청은 blocked로 둔다.
- SearchPlan 전체 구조를 새로 설계하지 말고 아래 스키마에 맞춘다.

반환 스키마:
{
  "action": "search | ask_clarification | out_of_scope | blocked | refine_previous_search",
  "intent_type": "place_recommendation | out_of_scope | unsafe_request",
  "user_intent_summary": "짧은 한국어 요약",
  "message": "",
  "location": {"text": "", "is_explicit": false, "fallback": "current_location"},
  "targets": [],
  "conditions": [],
  "preferences": [],
  "avoid": [],
  "search_plan": {
    "locationQuery": "",
    "baseLocationQuery": "",
    "targetQuery": "",
    "targetType": "",
    "scenario": "",
    "categories": [],
    "categoryHint": "",
    "menu_keywords": [],
    "place_type_keywords": [],
    "required_tags": [],
    "preferred_tags": [],
    "requestedConditions": []
  },
  "execution_policy": {
    "run_search": true,
    "preserve_explicit_location": false,
    "allow_kakao_fallback": true,
    "allow_ai_web_search_auto": false,
    "merge_ai_web_results": false
  },
  "needs_clarification": false,
  "clarification_question": "",
  "blocked_reason": "",
  "out_of_scope_reason": "",
  "confidence": 0,
  "fallback_reason": ""
}
""".strip()


def _normalize_ai_plan(raw_plan, query, fallback_plan, lat=None, lng=None, map_center=None, previous_context=None):
    if not isinstance(raw_plan, dict):
        return None

    action = raw_plan.get("action")
    if action not in ROUTER_ACTIONS:
        return _clarification_plan(
            query,
            question=PURPOSE_CLARIFICATION_MESSAGE,
            reason="invalid_ai_action",
            target_query="",
            fallback_location="current_location",
        )

    if action == "blocked":
        plan = _blocked_plan(query)
        plan["message"] = _clean_text(raw_plan.get("message")) or plan["message"]
        plan["blocked_reason"] = _clean_text(raw_plan.get("blocked_reason")) or plan["blocked_reason"]
        plan["confidence"] = _normalize_confidence(raw_plan.get("confidence"), plan["confidence"])
        plan["parser_provider"] = "gms"
        plan["parser_fallback"] = False
        return plan

    if action == "out_of_scope":
        plan = _out_of_scope_plan(query)
        plan["message"] = _clean_text(raw_plan.get("message")) or plan["message"]
        plan["out_of_scope_reason"] = _clean_text(raw_plan.get("out_of_scope_reason")) or plan["out_of_scope_reason"]
        plan["confidence"] = _normalize_confidence(raw_plan.get("confidence"), plan["confidence"])
        plan["parser_provider"] = "gms"
        plan["parser_fallback"] = False
        return plan

    search_plan = raw_plan.get("search_plan") or {}
    if not isinstance(search_plan, dict):
        search_plan = {}

    top_level_plan_keys = {
        "scenario": "scenario",
        "locationQuery": "locationQuery",
        "location_query": "locationQuery",
        "targetQuery": "targetQuery",
        "target_query": "targetQuery",
        "conditions": "requestedConditions",
    }
    search_plan = {
        **search_plan,
        **{
            target_key: raw_plan.get(source_key)
            for source_key, target_key in top_level_plan_keys.items()
            if raw_plan.get(source_key) not in (None, "", [])
        },
    }

    fallback_search_plan = fallback_plan["search_plan"]
    location_text = _sanitize_ai_location_query(
        _first_text(
            search_plan.get("locationQuery"),
            search_plan.get("location_query"),
            raw_plan.get("location", {}).get("text") if isinstance(raw_plan.get("location"), dict) else "",
            fallback_search_plan.get("locationQuery"),
        )
    )
    raw_target_query = _clean_target_query(
        _first_text(
            search_plan.get("targetQuery"),
            search_plan.get("target_query"),
            fallback_search_plan.get("targetQuery"),
        )
    )
    fallback_scenario = _normalize_scenario(fallback_search_plan.get("scenario"))
    scenario = _normalize_ai_scenario(
        _first_text(search_plan.get("scenario"), raw_plan.get("scenario")),
        target_query=raw_target_query,
        fallback=fallback_scenario,
    )
    force_query_policy = _should_force_query_intent_policy(query)
    scenario, policy_categories, policy_kakao_keywords, policy_preferred_tags = _apply_query_intent_overrides(
        query,
        scenario,
        _categories_for_scenario(scenario),
        [],
        [],
    )
    target_query = _sanitize_ai_target_query(
        raw_target_query,
        scenario,
        fallback_target=fallback_search_plan.get("targetQuery"),
    )
    if scenario == "waiting_place" and _has_waiting_place_natural_intent(query):
        target_query = "쉴 곳"
    elif scenario == "walk_healing" and _has_walk_healing_natural_intent(query):
        target_query = "산책할 곳"
    elif scenario == "work_cafe" and not _has_cafe_negative_preference(query):
        target_query = "카페"

    categories = _normalize_categories(search_plan.get("categories") or [])
    if force_query_policy or not categories or any(category not in ALLOWED_CATEGORIES for category in categories):
        categories = policy_categories or _categories_for_scenario(scenario)
    menu_keywords = _normalize_text_list(search_plan.get("menu_keywords") or fallback_search_plan.get("menu_keywords") or [])
    place_type_keywords = _normalize_text_list(search_plan.get("place_type_keywords") or fallback_search_plan.get("place_type_keywords") or [])
    conditions = _normalize_text_list(
        raw_plan.get("conditions")
        or search_plan.get("conditions")
        or search_plan.get("requestedConditions")
        or search_plan.get("requested_conditions")
        or []
    )
    conditions = _sanitize_requested_conditions([*conditions, *_extract_conditions(query)])
    preferred_tags = _normalize_tags(search_plan.get("preferred_tags") or raw_plan.get("preferences") or fallback_search_plan.get("preferred_tags") or [])
    preferred_tags = _unique([
        *preferred_tags,
        *policy_preferred_tags,
        *[tag for _, _, tag in _matched_condition_rules(query) if tag],
    ])
    required_tags = _normalize_tags(search_plan.get("required_tags") or fallback_search_plan.get("required_tags") or [])

    if action == "search" and not target_query:
        return _clarification_plan(
            query,
            question=PURPOSE_CLARIFICATION_MESSAGE,
            reason="ai_missing_target",
            target_query="",
            fallback_location="current_location",
        )

    if (
        action == "search"
        and not location_text
        and not _has_coordinate_context(lat, lng, map_center)
        and _requires_location_before_search(query, scenario, target_query)
    ):
        return _clarification_plan(
            query,
            question=_missing_location_question(query, scenario),
            reason="ai_missing_location_context",
            target_query=target_query,
            fallback_location="current_location",
        )

    normalized_search_plan = _search_plan_payload(
        original_query=query,
        location_query=location_text,
        target_query=target_query,
        scenario=scenario,
        categories=categories,
        menu_keywords=menu_keywords,
        place_type_keywords=place_type_keywords,
        required_tags=required_tags,
        preferred_tags=preferred_tags,
        requested_conditions=conditions,
        kakao_keyword_candidates=_normalize_text_list(
            (
                [*policy_kakao_keywords, target_query]
                if force_query_policy
                else search_plan.get("kakaoKeywordCandidates")
            )
            or search_plan.get("kakao_keyword_candidates")
            or fallback_search_plan.get("kakaoKeywordCandidates")
            or []
        ),
    )
    excluded_categories = _extract_excluded_categories(query)
    if excluded_categories:
        normalized_search_plan["excluded_categories"] = excluded_categories

    needs_clarification = bool(raw_plan.get("needs_clarification")) or action == "ask_clarification"
    return {
        "action": action,
        "intent_type": "place_recommendation",
        "user_intent_summary": _clean_text(raw_plan.get("user_intent_summary")) or fallback_plan["user_intent_summary"],
        "message": _clean_text(raw_plan.get("message")),
        "location": _location_payload(
            location_text,
            bool(location_text),
            "" if location_text else fallback_plan["location"].get("fallback", "current_location"),
        ),
        "targets": _normalize_text_list(raw_plan.get("targets") or fallback_plan.get("targets") or []),
        "conditions": conditions,
        "preferences": preferred_tags,
        "avoid": _normalize_text_list(raw_plan.get("avoid") or fallback_plan.get("avoid") or []),
        "search_plan": normalized_search_plan,
        "execution_policy": _execution_policy(action == "search" and not needs_clarification, bool(location_text)),
        "needs_clarification": needs_clarification,
        "clarification_question": _clean_text(raw_plan.get("clarification_question")) if needs_clarification else "",
        "blocked_reason": "",
        "out_of_scope_reason": "",
        "confidence": _normalize_confidence(raw_plan.get("confidence"), fallback_plan["confidence"]),
        "fallback_reason": "ai_planner",
        "parser_provider": "gms",
        "parser_fallback": False,
    }


def _extract_location_and_target(query):
    text = _clean_text(query)
    explicit_patterns = [
        rf"^(.+?({'|'.join(LOCATION_SUFFIXES)}))\s*(?:근처에서|주변에서|인근에서|앞에서|쪽에서|근처|주변|인근|에서|쪽|앞|일대|지역)?\s+(.+)$",
        rf"^(.+?)\s*(?:근처에서|주변에서|인근에서|앞에서|근처|주변|인근|앞)(?:에서|의)?\s+(.+)$",
        rf"^(.+?)에서\s+(.+)$",
    ]

    for pattern in explicit_patterns:
        match = re.match(pattern, text)
        if not match:
            continue

        location_query = _clean_location_text(match.group(1))
        target_query = _clean_target_query(match.group(3) if len(match.groups()) >= 3 else match.group(2))
        if location_query and target_query and not _looks_like_non_location(location_query):
            return location_query, target_query

    return "", _clean_target_query(text)


def _clean_location_text(value):
    return _normalize_location_query(value)


def _normalize_location_query(value):
    text = _clean_text(value)
    text = re.sub(r"\s+", " ", text).strip(" ,.?!")
    if not text:
        return ""

    suffix_pattern = (
        r"(?:근처에서|주변에서|인근에서|앞에서|쪽에서|"
        r"근처|주변|인근|앞|쪽|에서|일대|지역)$"
    )
    previous_text = None
    while text and previous_text != text:
        previous_text = text
        text = re.sub(suffix_pattern, "", text).strip(" ,.?!")

    if _looks_like_non_location(text):
        return ""

    return text


def _clean_target_query(value):
    text = _clean_text(value)
    for pattern in COMMAND_PATTERNS:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.?!")
    return text


def _clean_text(value):
    return str(value or "").replace("\u200b", "").strip()


def _compact(value):
    return _clean_text(value).lower().replace(" ", "")


def _has_any(query, keywords):
    compact = _compact(query)
    return any(_compact(keyword) in compact for keyword in keywords)


def _has_coordinate_context(lat=None, lng=None, map_center=None):
    if lat not in (None, "") and lng not in (None, ""):
        return True

    if isinstance(map_center, dict):
        return map_center.get("lat") not in (None, "") and map_center.get("lng") not in (None, "")

    return False


def _is_blocked_query(query):
    return _has_any(query, BLOCKED_KEYWORDS)


def _has_place_recommendation_hint(query):
    return _has_any(query, PLACE_RECOMMENDATION_HINTS)


def _is_out_of_scope_query(query):
    if not _has_any(query, OUT_OF_SCOPE_KEYWORDS):
        return False

    if _has_any(query, [
        "숙제",
        "과제",
        "비트코인",
        "주식",
        "코인",
        "투자",
        "정치",
        "뉴스",
        "의료",
        "감기약",
        "법률",
        "법적",
        "계약서",
        "연애",
    ]):
        return True

    return not _has_place_recommendation_hint(query)


def _is_refinement_request(query):
    if _is_negative_preference(query):
        return False
    return _has_any(query, REFINEMENT_CONTEXT_PHRASES)


def _scenario_keyword_score(query):
    combined = _compact(query)
    return max(
        sum(1 for keyword in keywords if _compact(keyword) in combined)
        for _, keywords, _, _, _ in SCENARIO_RULES
    )


def _is_vague_place_request(query, scenario, target_query):
    compact = _compact(query)
    has_vague_phrase = any(
        phrase in compact
        for phrase in [
            "좋은곳",
            "좋은데",
            "괜찮은곳",
            "괜찮은데",
            "어디좋",
            "어디갈까",
            "어디가",
        ]
    )
    return has_vague_phrase and _scenario_keyword_score(query) <= 0 and not _extract_menu_keywords(query)


def _requires_location_before_search(query, scenario, target_query):
    if scenario == "waiting_place" and _has_waiting_place_natural_intent(query):
        return True
    return _has_any(query, ["근처", "주변", "가까운", "가까이", "인근"])


def _extract_category_filter(query):
    if _has_any(query, ["카페만"]):
        return "cafe"
    if _has_any(query, ["공원만"]):
        return "city_park"
    if _has_any(query, ["식당만", "맛집만"]):
        return "restaurant"
    return ""


def _looks_like_non_location(text):
    compact = _compact(text)
    if compact in {"비", "비와서", "쉴곳", "쉴데", "산책할곳"}:
        return True
    return any(keyword in compact for keyword in [
        "조용",
        "혼자",
        "잠깐",
        "추천",
        "산책",
        "먹고",
        "맛집",
        "흡연",
        "담배",
        "카페",
        "공원",
        "쉴곳",
        "쉴데",
        "산책할곳",
        "밖말고",
    ])


def _scenario_rule_payload(scenario):
    for rule_scenario, _, categories, kakao_keywords, preferred_tags in SCENARIO_RULES:
        if rule_scenario == scenario:
            return (
                rule_scenario,
                list(categories),
                list(kakao_keywords),
                list(preferred_tags),
            )
    return (
        scenario,
        _categories_for_scenario(scenario),
        [_derive_target_query("", scenario, [])],
        [],
    )


def _apply_query_intent_overrides(query, scenario, categories, kakao_keywords, preferred_tags):
    if _has_cafe_negative_preference(query):
        rule_scenario, rule_categories, rule_kakao_keywords, rule_preferred_tags = _scenario_rule_payload("waiting_place")
        return (
            rule_scenario,
            rule_categories,
            [keyword for keyword in rule_kakao_keywords if "카페" not in keyword],
            rule_preferred_tags,
        )

    if _has_rain_indoor_intent(query) or _has_crowd_solo_waiting_intent(query):
        return _scenario_rule_payload("waiting_place")

    if _has_walk_healing_natural_intent(query):
        return _scenario_rule_payload("walk_healing")

    return (
        scenario,
        list(categories or []),
        list(kakao_keywords or []),
        list(preferred_tags or []),
    )


def _should_force_query_intent_policy(query):
    return (
        _has_cafe_negative_preference(query)
        or _has_rain_indoor_intent(query)
        or _has_crowd_solo_waiting_intent(query)
        or _has_walk_healing_natural_intent(query)
    )


def _is_negative_preference(query):
    return _has_any(query, NEGATIVE_PREFERENCE_PHRASES)


def _has_rain_indoor_intent(query):
    return (
        _has_any(query, ["밖 말고", "실외 말고", "비 피", "비피", "비 와서", "비와서"])
        or (_has_any(query, ["비"]) and _has_any(query, ["앉", "쉬", "쉴", "있을 데", "있을 곳"]))
    )


def _has_crowd_solo_waiting_intent(query):
    if _has_any(query, ["혼밥", "밥", "먹", "식사", "맛집"]):
        return False

    has_crowd_negative = _has_any(query, [
        "사람 많은 데 말고",
        "사람 너무 많은 데 말고",
        "사람많은데말고",
        "붐비는 데 말고",
        "붐비지",
    ])
    has_solo_rest = _has_any(query, ["혼자"]) and _has_any(query, ["쉬", "쉴", "있고 싶", "있을 곳", "있을 데"])
    return has_crowd_negative or has_solo_rest


def _has_cafe_negative_preference(query):
    return _has_any(query, [
        "카페 말고",
        "카페 느낌은 아니",
        "카페 느낌 아니",
        "카페느낌은아니",
        "카페 같지 않은",
        "카페는 아니",
        "카페는 싫",
        "카페 싫",
        "카페 빼고",
    ])


def _has_walk_healing_natural_intent(query):
    return _has_any(query, [
        "바람 쐬",
        "바람쐬",
        "걷기 좋은",
        "걷기좋은",
        "산책하면서",
        "산책할 곳",
        "힐링할 곳",
    ])


def _has_waiting_place_natural_intent(query):
    return (
        _has_rain_indoor_intent(query)
        or _has_crowd_solo_waiting_intent(query)
        or _has_cafe_negative_preference(query)
        or _has_any(query, ["잠깐", "잠시", "앉", "쉴 곳", "쉴곳", "쉬고 싶", "있고 싶"])
    )


def _missing_location_question(query, scenario):
    if scenario == "waiting_place":
        if _has_rain_indoor_intent(query):
            return "어느 지역에서 비를 피하면서 앉아 있을 곳을 찾아드릴까요? 예: 서면, 하단역, 광안리"
        if _has_crowd_solo_waiting_intent(query):
            return "어느 지역에서 혼자 조용히 쉴 곳을 찾아드릴까요? 예: 서면, 하단역, 광안리"
        if _has_cafe_negative_preference(query):
            return "어느 지역에서 조용히 쉴 곳을 찾아드릴까요? 예: 서면, 하단역, 광안리"
    return CLARIFICATION_MESSAGE


def _target_query_for_scenario(scenario):
    return _derive_target_query("", scenario, [])


def _extract_excluded_categories(query):
    if _has_cafe_negative_preference(query):
        return ["카페"]
    return []


def _pick_scenario(query, target_query):
    combined = _compact(f"{query} {target_query}")
    scores = []
    for scenario, keywords, categories, kakao_keywords, preferred_tags in SCENARIO_RULES:
        score = sum(1 for keyword in keywords if _compact(keyword) in combined)
        scores.append((score, scenario, categories, kakao_keywords, preferred_tags))

    best_score, scenario, categories, kakao_keywords, preferred_tags = max(scores, key=lambda item: item[0])
    if best_score <= 0:
        return "waiting_place", ["cafe", "shelter"], ["카페", "쉼터"], ["잠깐쉬기좋음"]

    return scenario, categories, kakao_keywords, preferred_tags


def _matched_condition_rules(query):
    compact = _compact(query)
    return [
        (keyword, label, tag)
        for keyword, label, tag in CONDITION_RULES
        if _compact(keyword) in compact
    ]


def _extract_conditions(query):
    return _sanitize_requested_conditions([
        *[label for _, label, _ in _matched_condition_rules(query)],
        *_inferred_natural_conditions(query),
    ])


def _sanitize_requested_conditions(items):
    sanitized = []
    for item in _normalize_text_list(items):
        compact = _compact(item)
        if not compact:
            continue
        if compact in {_compact(value) for value in CATEGORY_LIKE_CONDITION_VALUES}:
            continue
        sanitized.append(item)
    return _unique(sanitized)


def _inferred_natural_conditions(query):
    conditions = []

    if _has_rain_indoor_intent(query):
        conditions.extend(["실내", "앉을 수 있음", "비 피하기 좋음", "잠깐 쉬기 좋음"])

    if _has_crowd_solo_waiting_intent(query):
        conditions.extend(["혼자 이용하기 좋음", "조용함", "붐비지 않음", "잠깐 쉬기 좋음"])

    if _has_cafe_negative_preference(query):
        if _has_any(query, ["조용"]):
            conditions.append("조용함")
        if _has_any(query, ["앉", "쉬", "쉴", "있고 싶"]):
            conditions.append("잠깐 쉬기 좋음")
        conditions.append("카페 제외")

    if _has_walk_healing_natural_intent(query):
        conditions.append("산책하기 좋음")
        if _has_any(query, ["걷"]):
            conditions.append("걷기 좋음")
        if _has_any(query, ["바람"]):
            conditions.append("바람 쐬기 좋음")
        if _has_any(query, ["힐링"]):
            conditions.append("힐링하기 좋음")

    return conditions


def _extract_menu_keywords(query):
    compact = _compact(query)
    return _unique([keyword for keyword in MENU_KEYWORDS if _compact(keyword) in compact])


def _extract_place_type_keywords(query, menu_keywords, scenario):
    keywords = []
    compact = _compact(query)
    for menu_keyword in menu_keywords:
        keywords.extend(PLACE_TYPE_KEYWORDS.get(menu_keyword, []))

    if "카페" in compact:
        keywords.append("카페")
    if any(keyword in compact for keyword in ["맛집", "식당", "음식점", "먹"]):
        keywords.extend(["식당", "음식점"])
    if scenario == "walk_healing":
        keywords.extend(["공원", "산책로"])
    if scenario == "waiting_place":
        keywords.extend(["카페", "쉼터"])

    return _unique(keywords)


def _derive_target_query(query, scenario, menu_keywords):
    if menu_keywords:
        if "브런치" in menu_keywords and "카페" in query:
            return "브런치 카페"
        if any(keyword in query for keyword in ["맛집", "빵집", "카페"]):
            suffix = "맛집" if "맛집" in query else ("카페" if "카페" in query else "빵집")
            return f"{menu_keywords[0]} {suffix}"
        return menu_keywords[0]

    fallback_by_scenario = {
        "restaurant": "식당",
        "walk_healing": "산책할 곳",
        "work_cafe": "카페",
        "waiting_place": "쉴 곳",
        "smoking_area": "흡연구역",
    }
    return fallback_by_scenario.get(scenario, query)


def _fallback_target_query(target_query, scenario, menu_keywords):
    if target_query:
        return target_query
    return _derive_target_query("", scenario, menu_keywords)


def _extract_avoid_terms(query):
    text = _clean_text(query)
    if "말고" not in text and "제외" not in text:
        if "빼" not in text:
            return []

    avoid_terms = []
    for keyword in ["공원", "카페", "식당", "쉼터", "흡연구역", "관광지"]:
        if keyword in text:
            avoid_terms.append(keyword)
    return _unique(avoid_terms)


def _build_intent_summary(location_query, target_query, scenario, conditions):
    location_label = location_query or "현재 위치 기준"
    condition_label = f" · 조건: {', '.join(conditions[:2])}" if conditions else ""
    target_label = target_query or {
        "restaurant": "식당/맛집",
        "walk_healing": "산책/힐링 장소",
        "work_cafe": "작업하기 좋은 카페",
        "waiting_place": "잠깐 쉴 곳",
        "smoking_area": "흡연구역",
    }.get(scenario, "장소")
    return f"{location_label}에서 {target_label}을 찾는 요청으로 이해했어요{condition_label}."


def _location_payload(text, is_explicit, fallback):
    return {
        "text": text or "",
        "is_explicit": bool(is_explicit),
        "fallback": fallback or "",
    }


def _search_plan_payload(
    original_query,
    location_query,
    target_query,
    scenario,
    categories,
    menu_keywords,
    place_type_keywords,
    required_tags,
    preferred_tags,
    requested_conditions,
    kakao_keyword_candidates=None,
):
    category_hint = categories[0] if categories else ""
    return {
        "originalQuery": original_query,
        "locationQuery": location_query or "",
        "baseLocationQuery": location_query or "",
        "has_explicit_location": bool(location_query),
        "location_resolution_required": bool(location_query),
        "targetQuery": target_query or "",
        "targetType": "category" if category_hint else "",
        "scenario": scenario,
        "categories": categories,
        "categoryHint": category_hint,
        "menu_keywords": menu_keywords,
        "place_type_keywords": place_type_keywords,
        "required_tags": required_tags,
        "preferred_tags": preferred_tags,
        "requestedConditions": requested_conditions,
        "kakaoKeywordCandidates": _unique(kakao_keyword_candidates or [target_query]),
    }


def _execution_policy(run_search, preserve_explicit_location):
    return {
        "run_search": bool(run_search),
        "preserve_explicit_location": bool(preserve_explicit_location),
        "allow_kakao_fallback": True,
        "allow_ai_web_search_auto": False,
        "merge_ai_web_results": False,
    }


def _normalize_text_list(items):
    if not isinstance(items, list):
        items = [items] if items else []
    return _unique([
        _clean_text(item)
        for item in items
        if _clean_text(item) and _clean_text(item) != "[object Object]"
    ])


def _normalize_tags(items):
    return [
        item
        for item in _normalize_text_list(items)
        if item in ALLOWED_TAGS or item
    ]


def _normalize_categories(items):
    categories = []
    for item in _normalize_text_list(items):
        if item == "park":
            item = "city_park"
        if item == "tourist_spot":
            item = "tourism"
        if item in ALLOWED_CATEGORIES:
            categories.append(item)
    return _unique(categories)


def _normalize_scenario(value):
    scenario = _clean_text(value)
    return scenario if scenario in ALLOWED_SCENARIOS else "waiting_place"


def _normalize_confidence(value, fallback):
    try:
        confidence = int(float(value))
    except (TypeError, ValueError):
        confidence = fallback
    return min(max(confidence, 0), 100)


def _first_text(*values):
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _unique(items):
    seen = set()
    result = []
    for item in items:
        text = _clean_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
