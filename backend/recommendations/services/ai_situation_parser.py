import json
import logging
import re

import requests
from django.conf import settings

from recommendations.services.recommendation_condition import (
    SCENARIO_CONFIGS,
    build_recommendation_condition,
)

logger = logging.getLogger(__name__)

ALLOWED_SCENARIOS = set(SCENARIO_CONFIGS.keys())
ALLOWED_CATEGORIES = {
    "cafe",
    "shelter",
    "toilet",
    "parking",
    "freewifi",
    "pharmacy",
    "hospital",
    "city_park",
    "beach",
    "tourism",
    "smoking_area",
    "restaurant",
    "library",
    "public_library",
    "study_cafe",
}
ALLOWED_TAGS = {
    "조용한",
    "와이파이",
    "콘센트있음",
    "노트북작업",
    "혼자이용좋음",
    "잠깐쉬기좋음",
    "실내쉼터",
    "편의시설",
    "산책좋음",
    "힐링",
    "전망좋음",
    "야경",
    "사진찍기좋음",
    "호수",
    "벚꽃",
    "개방형흡연구역",
    "부스형흡연구역",
    "실내흡연실",
    "실외흡연구역",
    "식사가능",
}
SAFETY_BLOCK_MESSAGE = (
    "요청하신 목적은 장소 추천으로 도와드리기 어렵습니다. "
    "공공장소와 영업장을 정상적으로 이용하는 범위에서 다시 검색해 주세요."
)
SAFETY_CHECK_UNAVAILABLE_MESSAGE = (
    "요청을 안전하게 확인하지 못해 검색을 진행하지 않았습니다. "
    "잠시 후 다시 시도해 주세요."
)
CATEGORY_ALIASES = {
    "park": "city_park",
    "tourist_spot": "tourism",
    "bathroom": "toilet",
    "restroom": "toilet",
    "public_toilet": "toilet",
    "wifi": "freewifi",
    "public_wifi": "freewifi",
    "medical": "hospital",
}
TAG_ALIASES = {
    "조용함": "조용한",
    "실내": "실내쉼터",
    "잠깐쉬기": "잠깐쉬기좋음",
    "산책": "산책좋음",
    "전망": "전망좋음",
    "흡연구역": "실외흡연구역",
}

INDOOR_WEATHER_KEYWORDS = [
    "비",
    "비오",
    "비 오",
    "눈",
    "눈오",
    "눈 오",
    "더위",
    "더운",
    "덥",
    "폭염",
    "추위",
    "추운",
    "춥",
    "한파",
    "실내",
]
INDOOR_WAITING_CATEGORIES = ["cafe", "shelter"]
INDOOR_EXCLUDED_CATEGORIES = ["city_park", "beach"]
WALK_HEALING_BASE_CATEGORIES = ["city_park", "beach", "tourism"]
WALK_HEALING_CAFE_KEYWORDS = ["카페", "커피", "cafe"]
WALK_HEALING_RESTAURANT_KEYWORDS = [
    "식당",
    "맛집",
    "음식점",
    "밥집",
    "식사",
    "밥",
    "먹",
]
WALK_HEALING_WIFI_KEYWORDS = ["와이파이", "wifi", "wi-fi", "무선인터넷"]
WALK_HEALING_HEALING_KEYWORDS = [
    "힐링",
    "쉬고 싶",
    "쉬고싶",
    "쉬고",
    "조용히 걷",
    "조용하게 걷",
    "조용한 산책",
]
WALK_HEALING_REQUIRED_KEYWORDS = ["산책", "걷", "둘레길", "갈맷길"]

FOOD_INTENT_KEYWORDS = [
    "맛집",
    "먹고",
    "먹고싶",
    "먹을",
    "식사",
    "밥",
    "혼밥",
    "식당",
    "밥집",
    "음식점",
    "레스토랑",
    "디저트",
    "브런치",
    "빵",
    "빵집",
    "베이커리",
    "소금빵",
    "파스타",
    "쌀국수",
    "돈까스",
    "돈가스",
]
BAKERY_MENU_KEYWORDS = ["빵", "소금빵", "디저트", "베이커리", "빵집"]
CAFE_MENU_KEYWORDS = ["카페", "커피", "디저트", "브런치", "소금빵", "빵"]
RESTAURANT_MENU_KEYWORDS = ["밥", "식사", "혼밥", "파스타", "쌀국수", "돈까스", "돈가스"]
KNOWN_MENU_KEYWORDS = [
    "소금빵",
    "디저트",
    "브런치",
    "커피",
    "파스타",
    "쌀국수",
    "돈까스",
    "돈가스",
    "밥",
    "식사",
    "빵",
]
MENU_PATTERN_SUFFIXES = [
    "맛집",
    "먹고 싶",
    "먹고싶",
    "파는 곳",
    "파는곳",
    "먹을 수 있는 곳",
    "먹을수있는곳",
    "카페",
    "빵집",
    "디저트",
]

SCENARIO_KEYWORDS = {
    "work_cafe": [
        "작업",
        "공부",
        "노트북",
        "조용",
        "콘센트",
        "와이파이",
        "카페",
        "일할",
    ],
    "waiting_place": [
        "대기",
        "기다",
        "잠깐",
        "쉬",
        "머물",
        "실내",
        "쉼터",
        "비",
        "더위",
        "추위",
    ],
    "walk_healing": [
        "산책",
        "힐링",
        "경치",
        "전망",
        "야경",
        "바다",
        "공원",
        "걷",
        "사진",
    ],
    "smoking_area": [
        "흡연",
        "담배",
        "smoking",
        "smoke",
    ],
    "restaurant": [
        "혼밥",
        "혼자",
        "밥",
        "먹",
        "식당",
        "밥집",
        "음식점",
        "점심",
        "저녁",
        "브런치",
        "식사",
    ],
}

EXTRA_TAG_KEYWORDS = {
    "조용": "조용한",
    "와이파이": "와이파이",
    "wifi": "와이파이",
    "콘센트": "콘센트있음",
    "노트북": "노트북작업",
    "혼자": "혼자이용좋음",
    "실내": "실내쉼터",
    "잠깐": "잠깐쉬기좋음",
    "편의": "편의시설",
    "산책": "산책좋음",
    "힐링": "힐링",
    "전망": "전망좋음",
    "야경": "야경",
    "사진": "사진찍기좋음",
    "흡연": "실외흡연구역",
    "혼밥": "혼자이용좋음",
    "혼자": "혼자이용좋음",
    "밥": "식사가능",
    "먹": "식사가능",
    "식당": "식사가능",
    "밥집": "식사가능",
    "음식점": "식사가능",
}


def _pick_scenario(query):
    if _has_food_intent(query):
        return "restaurant"

    normalized = query.lower()
    scores = {}

    for scenario, keywords in SCENARIO_KEYWORDS.items():
        scores[scenario] = sum(
            1 for keyword in keywords if keyword.lower() in normalized
        )

    best_scenario, best_score = max(scores.items(), key=lambda item: item[1])
    return best_scenario if best_score > 0 else "waiting_place"


def _compact_text(value):
    return (value or "").lower().replace(" ", "")


def _has_food_intent(query):
    compact = _compact_text(query)
    return any(keyword.replace(" ", "") in compact for keyword in FOOD_INTENT_KEYWORDS)


def _clean_menu_keyword(value):
    text = (value or "").strip()
    text = re.sub(r"^(근처에|근처|주변에|주변|가까운|가까이|여기서|지금)\s*", "", text)
    text = re.sub(r"(추천|찾아줘|찾아|좋은|괜찮은|먹고\s*싶어|먹고싶어)$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.?!")
    return text[:40]


def _extract_menu_keywords(query):
    text = (query or "").strip()
    menu_keywords = []

    for suffix in MENU_PATTERN_SUFFIXES:
        pattern = rf"(.+?)\s*{re.escape(suffix)}"
        match = re.search(pattern, text)
        if match:
            menu = _clean_menu_keyword(match.group(1))
            if menu:
                menu_keywords.append(menu)

    compact = _compact_text(text)
    for keyword in KNOWN_MENU_KEYWORDS:
        if keyword.replace(" ", "") in compact:
            menu_keywords.append(keyword)

    return list(dict.fromkeys(menu_keywords))[:3]


def _get_food_place_type_keywords(menu_keywords, query):
    compact = _compact_text(" ".join([query or "", *menu_keywords]))

    if any(keyword in compact for keyword in BAKERY_MENU_KEYWORDS):
        return ["베이커리", "빵집", "카페"]

    if any(keyword in compact for keyword in CAFE_MENU_KEYWORDS):
        return ["카페"]

    return ["식당", "음식점"]


def _build_food_keywords(query, menu_keywords, place_type_keywords, purpose_keywords):
    keywords = []
    has_matjip = "맛집" in (query or "")

    for menu in menu_keywords:
        if has_matjip:
            keywords.append(f"{menu} 맛집")
        keywords.append(menu)

        if any(place_type in {"베이커리", "빵집", "카페"} for place_type in place_type_keywords):
            keywords.append(f"{menu} 카페")
        else:
            keywords.append(f"{menu} 식당")

    if not menu_keywords and any(keyword in _compact_text(query) for keyword in ["혼밥", "혼자밥", "혼자식사"]):
        keywords.extend(["혼밥", "식당", "밥집", "음식점"])

    keywords.extend(place_type_keywords)
    keywords.extend(purpose_keywords)
    return list(dict.fromkeys(keyword for keyword in keywords if keyword))[:10]


def _build_food_intent_condition(query):
    if not _has_food_intent(query):
        return None

    menu_keywords = _extract_menu_keywords(query)
    place_type_keywords = _get_food_place_type_keywords(menu_keywords, query)
    purpose_keywords = ["맛집"] if "맛집" in (query or "") else []
    compact = _compact_text(query)

    if "혼밥" in compact or "혼자" in compact:
        purpose_keywords.append("혼밥")

    categories = ["restaurant"]
    if any(place_type in {"베이커리", "빵집", "카페"} for place_type in place_type_keywords):
        categories = ["cafe", "restaurant"]

    preferred_tags = ["식사가능"]
    if "혼밥" in purpose_keywords:
        preferred_tags.append("혼자이용좋음")
    if "조용" in compact:
        preferred_tags.append("조용한")

    keywords = _build_food_keywords(query, menu_keywords, place_type_keywords, purpose_keywords)
    intent_subject = menu_keywords[0] if menu_keywords else "음식/메뉴"
    condition = build_recommendation_condition(
        scenario="restaurant",
        condition={
            "intent": f"{intent_subject} 맛집 검색",
            "scenario": "restaurant",
            "categories": categories,
            "required_tags": [],
            "preferred_tags": preferred_tags,
            "keywords": keywords,
            "menu_keywords": menu_keywords,
            "place_type_keywords": place_type_keywords,
            "purpose_keywords": purpose_keywords,
            "fallback_enabled": True,
        },
        keyword=query or f"{intent_subject} 맛집 검색",
    )
    condition.update({
        "situation_summary": query or f"{intent_subject} 맛집 검색",
        "reason_hint": "음식/메뉴/맛집 의도로 해석해 카페, 베이커리, 식당 계열 후보를 우선합니다.",
    })
    return condition


def _extract_tags(query, scenario):
    normalized = query.lower()
    config = SCENARIO_CONFIGS[scenario]
    tags = list(config["tags"])

    for keyword, tag in EXTRA_TAG_KEYWORDS.items():
        if keyword.lower() in normalized:
            tags.append(tag)

    return list(dict.fromkeys(tag for tag in tags if tag in ALLOWED_TAGS))


def _has_indoor_weather_context(query):
    normalized = (query or "").lower().replace(" ", "")
    return any(
        keyword.replace(" ", "").lower() in normalized
        for keyword in INDOOR_WEATHER_KEYWORDS
    )


def _has_any_compact_keyword(query, keywords):
    normalized = _compact_text(query)
    return any(keyword.replace(" ", "").lower() in normalized for keyword in keywords)


def _apply_walk_healing_constraints(parse, query):
    if parse["scenario"] != "walk_healing":
        return parse

    mentions_cafe = _has_any_compact_keyword(query, WALK_HEALING_CAFE_KEYWORDS)
    mentions_restaurant = _has_any_compact_keyword(query, WALK_HEALING_RESTAURANT_KEYWORDS)
    mentions_wifi = _has_any_compact_keyword(query, WALK_HEALING_WIFI_KEYWORDS)
    mentions_healing = _has_any_compact_keyword(query, WALK_HEALING_HEALING_KEYWORDS)
    mentions_walk = _has_any_compact_keyword(query, WALK_HEALING_REQUIRED_KEYWORDS)

    allowed_categories = set(WALK_HEALING_BASE_CATEGORIES)
    if mentions_cafe:
        allowed_categories.add("cafe")
    if mentions_restaurant:
        allowed_categories.add("restaurant")

    parse["categories"] = [
        category
        for category in parse.get("categories", [])
        if category in allowed_categories
    ] or list(WALK_HEALING_BASE_CATEGORIES)

    parse["preferred_tags"] = [
        tag
        for tag in parse.get("preferred_tags") or parse.get("tags") or []
        if (
            tag != "와이파이" or mentions_wifi
        ) and (
            tag != "힐링" or mentions_healing
        )
    ]
    parse["required_tags"] = [
        tag
        for tag in parse.get("required_tags", [])
        if (
            tag != "와이파이" or mentions_wifi
        ) and (
            tag != "힐링" or mentions_healing
        )
    ]

    if mentions_walk and "산책좋음" not in parse["required_tags"]:
        parse["required_tags"].insert(0, "산책좋음")

    if mentions_healing and "힐링" not in parse["preferred_tags"]:
        parse["preferred_tags"].append("힐링")

    if mentions_wifi and "와이파이" not in parse["preferred_tags"]:
        parse["preferred_tags"].append("와이파이")

    parse["tags"] = list(parse["preferred_tags"])
    return parse


def _sync_condition_aliases(parse):
    preferred_tags = list(dict.fromkeys(
        parse.get("preferred_tags")
        or parse.get("tags")
        or []
    ))
    parse["preferred_tags"] = preferred_tags
    parse["tags"] = list(preferred_tags)
    parse["required_tags"] = list(dict.fromkeys(parse.get("required_tags") or []))
    parse["avoid_tags"] = list(dict.fromkeys(parse.get("avoid_tags") or []))
    parse["keywords"] = list(dict.fromkeys(parse.get("keywords") or []))
    parse["fallback_enabled"] = bool(parse.get("fallback_enabled", True))
    return parse


def _apply_context_constraints(parse, query):
    parse = _apply_walk_healing_constraints(parse, query)

    if parse["scenario"] != "waiting_place" or not _has_indoor_weather_context(query):
        parse["exclude_categories"] = []
        return _sync_condition_aliases(parse)

    parse["categories"] = [
        category
        for category in parse["categories"]
        if category in INDOOR_WAITING_CATEGORIES
    ] or list(INDOOR_WAITING_CATEGORIES)
    parse["exclude_categories"] = list(INDOOR_EXCLUDED_CATEGORIES)

    if "실내쉼터" not in parse["tags"]:
        parse["tags"].append("실내쉼터")
    if "실내쉼터" not in parse.get("preferred_tags", []):
        parse.setdefault("preferred_tags", []).append("실내쉼터")

    parse["reason_hint"] = (
        f"{parse['reason_hint']} 날씨/실내 맥락이 있어 실외 장소는 제외했습니다."
    )
    return _sync_condition_aliases(parse)


def _apply_default_safety(parse):
    parse.setdefault("is_searchable", True)
    parse.setdefault("blocked", False)
    parse.setdefault("block_reason", "")
    parse.setdefault("safety_reason", "")
    parse.setdefault("user_message", "")
    return parse


def _is_false_value(value):
    if isinstance(value, bool):
        return value is False

    if isinstance(value, str):
        return value.strip().lower() in {"false", "no", "not_allowed", "blocked", "0"}

    return value == 0


def _build_blocked_parse(fallback_parse, raw_parse=None):
    raw_parse = raw_parse or {}
    blocked_parse = {
        **fallback_parse,
        "is_searchable": False,
        "blocked": True,
        "block_reason": raw_parse.get("block_reason") or "inappropriate_place_use",
        "safety_reason": str(raw_parse.get("safety_reason") or "")[:240],
        "user_message": str(raw_parse.get("user_message") or SAFETY_BLOCK_MESSAGE)[:240],
        "fallback_enabled": False,
        "keywords": [],
    }
    return _sync_condition_aliases(blocked_parse)


def _rule_based_parse(query):
    cleaned_query = (query or "").strip()
    food_condition = _build_food_intent_condition(cleaned_query)
    if food_condition:
        return _apply_default_safety(_apply_context_constraints(food_condition, cleaned_query))

    scenario = _pick_scenario(cleaned_query)
    config = SCENARIO_CONFIGS[scenario]
    tags = _extract_tags(cleaned_query, scenario)
    condition = build_recommendation_condition(
        scenario=scenario,
        categories=config["categories"],
        tags=tags,
        keyword=cleaned_query or config["keyword"],
    )
    condition.update({
        "situation_summary": cleaned_query or config["keyword"],
        "reason_hint": "입력 문장에서 장소 유형과 태그 조건을 추출했습니다.",
    })

    return _apply_default_safety(_apply_context_constraints(condition, cleaned_query))


def _build_parser_system_prompt():
    return (
        "You convert a Korean user situation into recommendation filters. "
        "A separate safety classifier has already allowed the request, so set "
        "is_searchable=true. Return only a JSON object with these "
        "keys: is_searchable, safety_reason, user_message, scenario, categories, "
        "tags, required_tags, preferred_tags, avoid_tags, keywords, radius, "
        "fallback_enabled, situation_summary, reason_hint. Never create places, "
        "addresses, coordinates, opening hours, facilities, menus, or new tags. "
        "If the query includes menu, food, cafe, bakery, dessert, brunch, meal, "
        "or matjip intent, do not use waiting_place; use restaurant with food keywords. "
        "Use waiting_place only for explicit rest, waiting, sitting, shelter, or short-stay intent. "
        "Use only "
        f"scenarios={sorted(ALLOWED_SCENARIOS)}, "
        f"categories={sorted(ALLOWED_CATEGORIES)}, "
        f"tags={sorted(ALLOWED_TAGS)}."
    )


def _build_safety_system_prompt():
    return (
        "You are a safety classifier for a Korean public-place recommendation "
        "service. Decide only whether the user's requested use of a place is "
        "appropriate for search. Block requests asking for places to damage, "
        "contaminate, harass, threaten, sexually misuse, illegally use, or "
        "clearly abuse a business, public facility, or shared space. Do not "
        "convert blocked requests into restaurant, cafe, restroom, facility, "
        "or nearby-place searches. Allow normal food, cafe, rest, tourism, "
        "parking, smoking-area, restroom, accessibility, or facility searches "
        "when the requested use is ordinary. Return only JSON with keys "
        "is_searchable, safety_reason, user_message. Use Korean for "
        "user_message."
    )


def _extract_json_object(value):
    if isinstance(value, dict):
        return value

    if not isinstance(value, str):
        return {}

    stripped = value.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.replace("json\n", "", 1).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or start >= end:
            return {}

        try:
            return json.loads(stripped[start:end + 1])
        except json.JSONDecodeError:
            return {}


def _has_gms_config():
    return bool(getattr(settings, "GMS_API_KEY", "") and getattr(settings, "GMS_API_URL", ""))


def _call_gms_chat_json(query, system_prompt, max_completion_tokens, *, model=None, timeout=None):
    api_key = getattr(settings, "GMS_API_KEY", "")
    api_url = getattr(settings, "GMS_API_URL", "")
    model = model or getattr(settings, "AI_INTENT_MODEL", getattr(settings, "GMS_MODEL", "gpt-5-nano"))

    if not _has_gms_config():
        return None

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": query,
            },
        ],
        "response_format": {"type": "json_object"},
        "reasoning_effort": "minimal",
        "max_completion_tokens": max_completion_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=timeout or getattr(settings, "AI_REQUEST_TIMEOUT", 4),
    )
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content:
            return _extract_json_object(content)

    structured = (
        data.get("parsed")
        or data.get("result")
        or data.get("output")
    )
    if structured:
        return structured

    if any(key in data for key in ("is_searchable", "searchable", "scenario")):
        return data

    return None


def _normalize_safety_decision(raw_decision):
    raw = _extract_json_object(raw_decision)
    if not raw:
        return None

    searchable_value = raw.get("is_searchable", raw.get("searchable"))
    if searchable_value is None:
        return {
            "is_searchable": False,
            "block_reason": "safety_check_incomplete",
            "safety_reason": "AI safety classifier did not return a searchable decision.",
            "user_message": SAFETY_CHECK_UNAVAILABLE_MESSAGE,
        }

    is_searchable = not _is_false_value(searchable_value)
    block_reason = str(raw.get("block_reason") or "inappropriate_place_use")[:80]
    user_message = "" if is_searchable else SAFETY_BLOCK_MESSAGE

    return {
        "is_searchable": is_searchable,
        "block_reason": block_reason,
        "safety_reason": str(raw.get("safety_reason") or "")[:240],
        "user_message": user_message,
    }


def _call_gms_safety_classifier(query):
    raw_decision = _call_gms_chat_json(
        query,
        _build_safety_system_prompt(),
        max_completion_tokens=500,
    )
    decision = _normalize_safety_decision(raw_decision)
    if decision is None:
        return {
            "is_searchable": False,
            "block_reason": "safety_check_incomplete",
            "safety_reason": "AI safety classifier returned no usable decision.",
            "user_message": SAFETY_CHECK_UNAVAILABLE_MESSAGE,
        }
    return decision


def _call_gms_parser(query):
    if not _has_gms_config():
        return None

    try:
        safety_decision = _call_gms_safety_classifier(query)
    except Exception as exc:
        logger.info("GMS safety classifier failed; blocking search: %s", exc)
        return {
            "is_searchable": False,
            "block_reason": "safety_check_unavailable",
            "safety_reason": "AI safety classifier request failed.",
            "user_message": SAFETY_CHECK_UNAVAILABLE_MESSAGE,
        }

    if safety_decision and safety_decision.get("is_searchable") is False:
        return safety_decision

    raw_parse = _call_gms_chat_json(
        query,
        _build_parser_system_prompt(),
        max_completion_tokens=500,
    )
    if isinstance(raw_parse, dict):
        raw_parse.setdefault("is_searchable", True)
    return raw_parse


def _call_openai_parser(query):
    # TODO: OPENAI_API_KEY is loaded in settings for a future provider.
    # This project currently prefers provider="gms", and OpenAI calls are not
    # enabled in this task so tests never hit an external OpenAI API.
    return None


def _normalize_categories(categories, fallback_categories):
    normalized = []

    for category in categories or []:
        category = CATEGORY_ALIASES.get(category, category)
        if category in ALLOWED_CATEGORIES:
            normalized.append(category)

    return list(dict.fromkeys(normalized)) or list(fallback_categories)


def _normalize_tags(tags, fallback_tags):
    normalized = []

    for tag in tags or []:
        tag = TAG_ALIASES.get(tag, tag)
        if tag in ALLOWED_TAGS:
            normalized.append(tag)

    return list(dict.fromkeys(normalized)) or list(fallback_tags)


def _normalize_ai_parse(raw_parse, fallback_parse):
    raw = _extract_json_object(raw_parse)
    if _is_false_value(raw.get("is_searchable", raw.get("searchable", True))):
        return _build_blocked_parse(fallback_parse, raw)

    scenario = raw.get("scenario")
    food_condition = _build_food_intent_condition(fallback_parse.get("situation_summary", ""))

    if scenario not in ALLOWED_SCENARIOS:
        scenario = fallback_parse["scenario"]

    if food_condition and scenario == "waiting_place":
        return _apply_default_safety(_apply_context_constraints(food_condition, fallback_parse["situation_summary"]))

    config = SCENARIO_CONFIGS[scenario]
    categories = _normalize_categories(raw.get("categories"), config["categories"])
    preferred_tags = _normalize_tags(
        raw.get("preferred_tags") or raw.get("tags"),
        fallback_parse["preferred_tags"],
    )
    required_tags = _normalize_tags(raw.get("required_tags"), [])
    avoid_tags = _normalize_tags(raw.get("avoid_tags"), [])
    keywords = raw.get("keywords") or fallback_parse.get("keywords", [])
    summary = raw.get("situation_summary") or fallback_parse["situation_summary"]
    reason_hint = raw.get("reason_hint") or fallback_parse["reason_hint"]
    intent = raw.get("intent") or summary

    condition = build_recommendation_condition(
        scenario=scenario,
        condition={
            "intent": intent,
            "categories": categories,
            "required_tags": required_tags,
            "preferred_tags": preferred_tags,
            "avoid_tags": avoid_tags,
            "keywords": keywords,
            "radius": raw.get("radius") or fallback_parse.get("radius"),
            "fallback_enabled": raw.get(
                "fallback_enabled",
                fallback_parse.get("fallback_enabled", True),
            ),
        },
        keyword=summary,
    )
    condition.update({
        "situation_summary": str(summary)[:200],
        "reason_hint": str(reason_hint)[:240],
    })
    if food_condition:
        condition["keywords"] = list(dict.fromkeys([
            *food_condition.get("keywords", []),
            *condition.get("keywords", []),
        ]))
        condition["menu_keywords"] = food_condition.get("menu_keywords", [])
        condition["place_type_keywords"] = food_condition.get("place_type_keywords", [])
        condition["purpose_keywords"] = food_condition.get("purpose_keywords", [])
        if condition.get("scenario") == "restaurant":
            condition["categories"] = food_condition.get("categories", condition.get("categories", []))

    return _apply_default_safety(_apply_context_constraints(condition, fallback_parse["situation_summary"]))


def _call_ai_parser(query):
    provider = getattr(settings, "AI_PROVIDER", "gms").lower()

    if provider == "gms":
        return "gms", _call_gms_parser(query)

    if provider == "openai":
        return "openai", _call_openai_parser(query)

    return "rule", None


def parse_situation(query):
    """
    Convert a natural-language situation into recommendation conditions.

    AI is allowed to parse the user's intent only. It must not create places,
    coordinates, operation facts, or tags that are not in the allowlist. If an
    AI provider is unavailable or fails, the function falls back to the local
    rule-based parser with the same return interface.
    """
    cleaned_query = (query or "").strip()
    fallback_parse = _rule_based_parse(cleaned_query)

    try:
        provider, raw_parse = _call_ai_parser(cleaned_query)
        if raw_parse:
            parsed = _normalize_ai_parse(raw_parse, fallback_parse)
            parsed["parser_provider"] = provider
            parsed["parser_fallback"] = False
            return parsed
    except Exception as exc:
        logger.info("AI situation parser failed; using rule fallback: %s", exc)

    fallback_parse["parser_provider"] = "rule"
    fallback_parse["parser_fallback"] = True
    return fallback_parse
