SCENARIO_CONFIGS = {
    "work_cafe": {
        "keyword": "조용히 작업할 곳",
        "categories": ["cafe"],
        "tags": ["조용한", "와이파이", "콘센트있음", "노트북작업", "혼자이용좋음"],
    },
    "waiting_place": {
        "keyword": "잠깐 머물 곳",
        "categories": ["cafe", "shelter", "city_park"],
        "tags": ["잠깐쉬기좋음", "실내쉼터", "편의시설", "조용한", "혼자이용좋음"],
    },
    "walk_healing": {
        "keyword": "산책하고 힐링할 곳",
        "categories": ["city_park", "beach", "tourism"],
        "tags": ["산책좋음", "힐링", "전망좋음", "야경", "사진찍기좋음", "호수", "벚꽃"],
    },
    "smoking_area": {
        "keyword": "가까운 흡연구역",
        "categories": ["smoking_area"],
        "tags": ["개방형흡연구역", "부스형흡연구역", "실내흡연실", "실외흡연구역"],
    },
    "restaurant": {
        "keyword": "혼자 식사하기 좋은 식당",
        "categories": ["restaurant"],
        "tags": ["혼자이용좋음", "조용한"],
    },
}

SCENARIO_DEFAULT_RADIUS = {
    "work_cafe": 1500,
    "waiting_place": 1200,
    "walk_healing": 3000,
    "smoking_area": 800,
    "restaurant": 1500,
}

SCENARIO_INTENTS = {
    "work_cafe": "노트북 작업하기 좋은 장소 추천",
    "waiting_place": "잠깐 쉬거나 머물기 좋은 장소 추천",
    "walk_healing": "산책하거나 힐링하기 좋은 장소 추천",
    "smoking_area": "가까운 흡연 가능 장소 추천",
    "restaurant": "혼자 식사하기 좋은 조용한 식당 추천",
}

SCENARIO_KEYWORDS = {
    "work_cafe": ["노트북", "작업", "카페", "콘센트", "와이파이"],
    "waiting_place": ["잠깐", "쉴 곳", "실내", "쉼터", "카페"],
    "walk_healing": ["산책", "힐링", "공원", "전망", "야경"],
    "smoking_area": ["흡연구역", "흡연실", "담배"],
    "restaurant": ["혼밥", "1인 식사", "조용한 식당", "밥집", "음식점"],
}

LIST_FIELDS = {
    "categories",
    "required_tags",
    "preferred_tags",
    "avoid_tags",
    "keywords",
    "exclude_categories",
}


def _unique_list(values):
    if not values:
        return []

    if isinstance(values, str):
        values = [values]

    cleaned = []
    for value in values:
        if value in (None, ""):
            continue

        text = str(value).strip()
        if text:
            cleaned.append(text)

    return list(dict.fromkeys(cleaned))


def _parse_bool(value, default=True):
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "n"}

    return bool(value)


def _parse_radius(value, default):
    if value in (None, ""):
        return default

    try:
        radius = int(value)
    except (TypeError, ValueError):
        return default

    return min(max(radius, 300), 20000)


def get_scenario_config(scenario):
    return SCENARIO_CONFIGS.get(scenario, SCENARIO_CONFIGS["work_cafe"])


def get_default_radius(scenario):
    return SCENARIO_DEFAULT_RADIUS.get(scenario, 1500)


def scenario_to_condition(scenario="work_cafe"):
    config = get_scenario_config(scenario)
    normalized_scenario = scenario if scenario in SCENARIO_CONFIGS else "custom"

    preferred_tags = _unique_list(config["tags"])

    condition = {
        "intent": SCENARIO_INTENTS.get(normalized_scenario, config["keyword"]),
        "scenario": normalized_scenario,
        "categories": _unique_list(config["categories"]),
        "required_tags": [],
        "preferred_tags": preferred_tags,
        "avoid_tags": [],
        "keywords": _unique_list(
            SCENARIO_KEYWORDS.get(normalized_scenario, [config["keyword"]])
        ),
        "radius": get_default_radius(normalized_scenario),
        "fallback_enabled": True,
        "exclude_categories": [],
    }
    condition["tags"] = list(condition["preferred_tags"])
    condition["keyword"] = config["keyword"]
    return condition


def build_recommendation_condition(
    scenario="work_cafe",
    condition=None,
    categories=None,
    tags=None,
    keyword=None,
    exclude_categories=None,
    radius=None,
):
    source_condition = condition or {}
    base_scenario = source_condition.get("scenario") or scenario
    normalized = scenario_to_condition(base_scenario)

    for key, value in source_condition.items():
        if value in (None, ""):
            continue

        if key in LIST_FIELDS:
            normalized[key] = _unique_list(value)
        elif key == "tags":
            normalized["preferred_tags"] = _unique_list(value)
        elif key == "radius":
            normalized["radius"] = _parse_radius(value, normalized["radius"])
        elif key == "fallback_enabled":
            normalized["fallback_enabled"] = _parse_bool(value, True)
        elif key in {"intent", "scenario", "keyword"}:
            normalized[key] = str(value).strip()

    if categories is not None:
        normalized["categories"] = _unique_list(categories)

    if tags is not None:
        normalized["preferred_tags"] = _unique_list(tags)

    if keyword:
        normalized["keyword"] = str(keyword).strip()
        normalized["intent"] = normalized["intent"] or normalized["keyword"]
        if normalized["keyword"] not in normalized["keywords"]:
            normalized["keywords"] = _unique_list([normalized["keyword"], *normalized["keywords"]])

    if exclude_categories is not None:
        normalized["exclude_categories"] = _unique_list(exclude_categories)

    if radius is not None:
        normalized["radius"] = _parse_radius(radius, normalized["radius"])

    normalized["required_tags"] = _unique_list(normalized.get("required_tags"))
    normalized["preferred_tags"] = _unique_list(normalized.get("preferred_tags"))
    normalized["avoid_tags"] = _unique_list(normalized.get("avoid_tags"))
    normalized["categories"] = _unique_list(normalized.get("categories"))
    normalized["keywords"] = _unique_list(normalized.get("keywords"))
    normalized["exclude_categories"] = _unique_list(normalized.get("exclude_categories"))
    normalized["tags"] = list(normalized["preferred_tags"])
    normalized["fallback_enabled"] = _parse_bool(normalized.get("fallback_enabled"), True)
    normalized["radius"] = _parse_radius(
        normalized.get("radius"),
        get_default_radius(normalized.get("scenario")),
    )
    return normalized
