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
        ["흡연", "담배"],
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
        ["작업", "노트북", "공부", "조용", "콘센트", "와이파이", "카페"],
        ["cafe"],
        ["카페", "작업 카페", "스터디카페"],
        ["조용한", "노트북작업", "콘센트있음", "와이파이"],
    ),
    (
        "waiting_place",
        ["잠깐", "쉬", "쉴", "대기", "기다", "실내", "쉼터"],
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
    "좀",
    "다른",
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
        return _empty_plan(query)

    rule_plan = _build_rule_plan(
        normalized_query,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )
    ai_plan = _build_ai_plan(normalized_query, rule_plan)

    if not ai_plan:
        return rule_plan

    normalized_ai_plan = _normalize_ai_plan(
        ai_plan,
        query=normalized_query,
        fallback_plan=rule_plan,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )
    return normalized_ai_plan or rule_plan


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
    location_query, target_query = _extract_location_and_target(query)
    has_explicit_location = bool(location_query)
    fallback_location = "" if has_explicit_location else "current_location"
    has_previous_context = bool(previous_context)
    has_ambiguous_reference = _has_any(query, AMBIGUOUS_REFERENCE_KEYWORDS)
    has_refinement = _has_any(query, REFINEMENT_KEYWORDS)

    if has_ambiguous_reference and not has_previous_context and not has_explicit_location:
        return {
            "action": "ask_clarification",
            "user_intent_summary": "이전 장소를 가리키는 표현이 있지만 기준이 분명하지 않습니다.",
            "location": _location_payload("", False, fallback_location),
            "targets": [],
            "conditions": _extract_conditions(query),
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
                requested_conditions=_extract_conditions(query),
            ),
            "execution_policy": _execution_policy(False, False),
            "needs_clarification": True,
            "clarification_question": CLARIFICATION_MESSAGE,
            "confidence": 40,
            "fallback_reason": "ambiguous_reference_without_context",
            "parser_provider": "rule",
            "parser_fallback": True,
        }

    scenario, categories, kakao_keywords, preferred_tags = _pick_scenario(query, target_query)
    conditions = _extract_conditions(query)
    menu_keywords = _extract_menu_keywords(query)
    place_type_keywords = _extract_place_type_keywords(query, menu_keywords, scenario)
    target_query = _clean_target_query(target_query or _derive_target_query(query, scenario, menu_keywords))
    target_query = _fallback_target_query(target_query, scenario, menu_keywords)

    preferred_tags = _unique([
        *preferred_tags,
        *[tag for _, _, tag in _matched_condition_rules(query) if tag],
    ])
    preferred_tags = [tag for tag in preferred_tags if tag in ALLOWED_TAGS or tag]

    action = "refine_previous_search" if has_previous_context and has_refinement else "search"

    return {
        "action": action,
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
- SearchPlan 전체 구조를 새로 설계하지 말고 아래 스키마에 맞춘다.

반환 스키마:
{
  "action": "search | ask_clarification | refine_previous_search",
  "user_intent_summary": "짧은 한국어 요약",
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
  "confidence": 0,
  "fallback_reason": ""
}
""".strip()


def _normalize_ai_plan(raw_plan, query, fallback_plan, lat=None, lng=None, map_center=None, previous_context=None):
    if not isinstance(raw_plan, dict):
        return None

    action = raw_plan.get("action")
    if action not in {"search", "ask_clarification", "refine_previous_search"}:
        action = fallback_plan["action"]

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
        "user_intent_summary": _clean_text(raw_plan.get("user_intent_summary")) or fallback_plan["user_intent_summary"],
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
        "execution_policy": _execution_policy(not needs_clarification, bool(location_text)),
        "needs_clarification": needs_clarification,
        "clarification_question": _clean_text(raw_plan.get("clarification_question")) if needs_clarification else "",
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


def _looks_like_non_location(text):
    compact = _compact(text)
    return any(keyword in compact for keyword in ["조용", "혼자", "잠깐", "추천", "산책", "먹고", "맛집"])


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
        return []
    return []


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
