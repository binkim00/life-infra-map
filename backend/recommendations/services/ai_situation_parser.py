import json
import logging

import requests
from django.conf import settings

from recommendations.services.db_recommender import SCENARIO_CONFIGS

logger = logging.getLogger(__name__)

ALLOWED_SCENARIOS = set(SCENARIO_CONFIGS.keys())
ALLOWED_CATEGORIES = {
    "cafe",
    "shelter",
    "city_park",
    "beach",
    "tourism",
    "smoking_area",
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
}
CATEGORY_ALIASES = {
    "park": "city_park",
    "tourist_spot": "tourism",
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
}


def _pick_scenario(query):
    normalized = query.lower()
    scores = {}

    for scenario, keywords in SCENARIO_KEYWORDS.items():
        scores[scenario] = sum(
            1 for keyword in keywords if keyword.lower() in normalized
        )

    best_scenario, best_score = max(scores.items(), key=lambda item: item[1])
    return best_scenario if best_score > 0 else "waiting_place"


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


def _apply_context_constraints(parse, query):
    if parse["scenario"] != "waiting_place" or not _has_indoor_weather_context(query):
        parse["exclude_categories"] = []
        return parse

    parse["categories"] = [
        category
        for category in parse["categories"]
        if category in INDOOR_WAITING_CATEGORIES
    ] or list(INDOOR_WAITING_CATEGORIES)
    parse["exclude_categories"] = list(INDOOR_EXCLUDED_CATEGORIES)

    if "실내쉼터" not in parse["tags"]:
        parse["tags"].append("실내쉼터")

    parse["reason_hint"] = (
        f"{parse['reason_hint']} 날씨/실내 맥락이 있어 실외 장소는 제외했습니다."
    )
    return parse


def _rule_based_parse(query):
    cleaned_query = (query or "").strip()
    scenario = _pick_scenario(cleaned_query)
    config = SCENARIO_CONFIGS[scenario]
    tags = _extract_tags(cleaned_query, scenario)

    return _apply_context_constraints({
        "scenario": scenario,
        "categories": list(config["categories"]),
        "tags": tags,
        "situation_summary": cleaned_query or config["keyword"],
        "reason_hint": "입력 문장에서 장소 유형과 태그 조건을 추출했습니다.",
    }, cleaned_query)


def _build_parser_system_prompt():
    return (
        "You convert a Korean user situation into recommendation filters. "
        "Return only a JSON object with these keys: scenario, categories, "
        "tags, situation_summary, reason_hint. Never create places, addresses, "
        "coordinates, opening hours, facilities, or new tags. Use only "
        f"scenarios={sorted(ALLOWED_SCENARIOS)}, "
        f"categories={sorted(ALLOWED_CATEGORIES)}, "
        f"tags={sorted(ALLOWED_TAGS)}."
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


def _call_gms_parser(query):
    api_key = getattr(settings, "GMS_API_KEY", "")
    api_url = getattr(settings, "GMS_API_URL", "")
    model = getattr(settings, "GMS_MODEL", "gpt-5-mini")

    if not api_key or not api_url:
        return None

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": _build_parser_system_prompt(),
            },
            {
                "role": "user",
                "content": query,
            },
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 500,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=getattr(settings, "AI_REQUEST_TIMEOUT", 4),
    )
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content:
            return _extract_json_object(content)

    return (
        data.get("parsed")
        or data.get("result")
        or data.get("output")
        or data
    )


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
    scenario = raw.get("scenario")

    if scenario not in ALLOWED_SCENARIOS:
        scenario = fallback_parse["scenario"]

    config = SCENARIO_CONFIGS[scenario]
    categories = _normalize_categories(raw.get("categories"), config["categories"])
    tags = _normalize_tags(raw.get("tags"), fallback_parse["tags"])
    summary = raw.get("situation_summary") or fallback_parse["situation_summary"]
    reason_hint = raw.get("reason_hint") or fallback_parse["reason_hint"]

    return _apply_context_constraints({
        "scenario": scenario,
        "categories": categories,
        "tags": tags,
        "situation_summary": str(summary)[:200],
        "reason_hint": str(reason_hint)[:240],
    }, fallback_parse["situation_summary"])


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
