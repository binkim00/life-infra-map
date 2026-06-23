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
    ("조용", "조용함", "조용한"),
    ("콘센트", "콘센트 있음", "콘센트있음"),
    ("와이파이", "와이파이 있음", "와이파이"),
    ("wifi", "와이파이 있음", "와이파이"),
    ("실내", "실내 이용 가능", "실내쉼터"),
    ("산책", "산책하기 좋음", "산책좋음"),
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
    "말고",
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
            question=CLARIFICATION_MESSAGE,
            reason="missing_location_context",
            target_query=target_query,
            fallback_location=fallback_location,
        )

    if has_previous_context and has_refinement:
        return _refine_previous_search_plan(query, previous_context)

    conditions = [] if scenario == "smoking_area" else _extract_conditions(query)
    menu_keywords = _extract_menu_keywords(query)
    place_type_keywords = _extract_place_type_keywords(query, menu_keywords, scenario)
    target_query = _clean_target_query(target_query or _derive_target_query(query, scenario, menu_keywords))
    target_query = _fallback_target_query(target_query, scenario, menu_keywords)
    if scenario == "smoking_area":
        target_query = "흡연구역"
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

    return {
        "action": "search",
        "user_intent_summary": _build_intent_summary(location_query, target_query, scenario, conditions),
        "location": _location_payload(location_query, has_explicit_location, fallback_location),
        "targets": _unique([target_query, *menu_keywords, *place_type_keywords]),
        "conditions": conditions,
        "preferences": preferred_tags,
        "avoid": _extract_avoid_terms(query),
        "search_plan": _search_plan_payload(
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
        "conditions": conditions,
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
            requested_conditions=conditions,
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

    additional_conditions = _extract_conditions(query)
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
        action = fallback_plan["action"]

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

    fallback_search_plan = fallback_plan["search_plan"]
    location_text = _clean_text(
        _first_text(
            search_plan.get("locationQuery"),
            search_plan.get("location_query"),
            raw_plan.get("location", {}).get("text") if isinstance(raw_plan.get("location"), dict) else "",
            fallback_search_plan.get("locationQuery"),
        )
    )
    target_query = _clean_target_query(
        _first_text(
            search_plan.get("targetQuery"),
            search_plan.get("target_query"),
            fallback_search_plan.get("targetQuery"),
        )
    )
    scenario = _normalize_scenario(_first_text(search_plan.get("scenario"), fallback_search_plan.get("scenario")))
    categories = _normalize_categories(search_plan.get("categories") or fallback_search_plan.get("categories") or [])
    menu_keywords = _normalize_text_list(search_plan.get("menu_keywords") or fallback_search_plan.get("menu_keywords") or [])
    place_type_keywords = _normalize_text_list(search_plan.get("place_type_keywords") or fallback_search_plan.get("place_type_keywords") or [])
    conditions = _normalize_text_list(raw_plan.get("conditions") or search_plan.get("requestedConditions") or fallback_plan.get("conditions") or [])
    preferred_tags = _normalize_tags(search_plan.get("preferred_tags") or raw_plan.get("preferences") or fallback_search_plan.get("preferred_tags") or [])
    required_tags = _normalize_tags(search_plan.get("required_tags") or fallback_search_plan.get("required_tags") or [])

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
            search_plan.get("kakaoKeywordCandidates")
            or search_plan.get("kakao_keyword_candidates")
            or fallback_search_plan.get("kakaoKeywordCandidates")
            or []
        ),
    )

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
        rf"^(.+?({'|'.join(LOCATION_SUFFIXES)}))\s*(?:근처|주변|인근|에서|쪽|일대|지역)?\s+(.+)$",
        rf"^(.+?)\s*(?:근처|주변|인근)(?:에서|의)?\s+(.+)$",
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
    return _clean_text(value).strip(" ,.?!")


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
    return _has_any(query, REFINEMENT_KEYWORDS)


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
    return any(keyword in compact for keyword in ["조용", "혼자", "잠깐", "추천", "산책", "먹고", "맛집", "흡연", "담배"])


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
    return _unique([label for _, label, _ in _matched_condition_rules(query)])


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
