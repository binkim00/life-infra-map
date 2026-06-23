SCENARIO_CONFIGS = {
    "work_cafe": {
        "keyword": "조용히 작업할 곳",
        "categories": ["cafe"],
        "tags": ["노트북작업", "조용한", "와이파이", "콘센트있음"],
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

SCENARIO_MIN_RADIUS = {
    "walk_healing": 3000,
}

WORK_CAFE_ALLOWED_CATEGORIES = {
    "cafe",
    "library",
    "public_library",
    "study_cafe",
}
WORK_CAFE_CORE_TAGS = [
    "노트북작업",
    "조용한",
    "와이파이",
    "콘센트있음",
]
WORK_CAFE_REMOVED_TAGS = {
    "실내쉼터",
    "편의시설",
    "개방형흡연구역",
    "부스형흡연구역",
    "실내흡연실",
    "실외흡연구역",
}

WAITING_PLACE_ALLOWED_CATEGORIES = {
    "cafe",
    "city_park",
    "shelter",
    "library",
    "public_library",
}
WAITING_PLACE_DEFAULT_TAGS = [
    "잠깐쉬기좋음",
    "실내쉼터",
    "조용한",
    "혼자이용좋음",
    "편의시설",
]
WAITING_PLACE_OPTIONAL_TAG_KEYWORDS = {
    "노트북작업": ["노트북", "작업", "공부", "일할"],
    "와이파이": ["와이파이", "wifi", "wi-fi", "무선인터넷"],
    "콘센트있음": ["콘센트", "전원", "충전"],
    "개방형흡연구역": ["흡연", "담배"],
    "부스형흡연구역": ["흡연", "담배"],
    "실내흡연실": ["흡연", "담배"],
    "실외흡연구역": ["흡연", "담배"],
    "식사가능": ["식사", "밥", "먹", "음식", "맛집"],
    "야경": ["야경"],
    "벚꽃": ["벚꽃"],
    "호수": ["호수"],
    "힐링": ["힐링"],
    "사진찍기좋음": ["사진"],
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
    "menu_keywords",
    "place_type_keywords",
    "purpose_keywords",
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


def _compact_text(value):
    return str(value or "").lower().replace(" ", "")


def _condition_policy_text(condition):
    values = [
        condition.get("intent"),
        condition.get("keyword"),
        *condition.get("keywords", []),
        *condition.get("purpose_keywords", []),
        *condition.get("place_type_keywords", []),
    ]
    return _compact_text(" ".join(str(value or "") for value in values))


def _has_explicit_tag_signal(condition_text, tag_name):
    keywords = WAITING_PLACE_OPTIONAL_TAG_KEYWORDS.get(tag_name, [])
    return any(_compact_text(keyword) in condition_text for keyword in keywords)


def _filter_categories(categories, allowed_categories, fallback_categories):
    filtered = [
        category
        for category in _unique_list(categories)
        if category in allowed_categories
    ]
    return filtered or list(fallback_categories)


def _apply_work_cafe_policy(condition):
    condition["categories"] = _filter_categories(
        condition.get("categories"),
        WORK_CAFE_ALLOWED_CATEGORIES,
        ["cafe"],
    )

    preferred_tags = [
        tag
        for tag in _unique_list(condition.get("preferred_tags"))
        if tag in WORK_CAFE_CORE_TAGS and tag not in WORK_CAFE_REMOVED_TAGS
    ]
    for tag in WORK_CAFE_CORE_TAGS:
        if tag not in preferred_tags:
            preferred_tags.append(tag)

    condition["preferred_tags"] = preferred_tags
    condition["required_tags"] = [
        tag
        for tag in _unique_list(condition.get("required_tags"))
        if tag in WORK_CAFE_CORE_TAGS
    ]
    condition["avoid_tags"] = [
        tag
        for tag in _unique_list(condition.get("avoid_tags"))
        if tag not in WORK_CAFE_REMOVED_TAGS
    ]
    condition["exclude_categories"] = _unique_list([
        *condition.get("exclude_categories", []),
        "shelter",
        "city_park",
        "beach",
        "smoking_area",
        "tourism",
        "restaurant",
    ])
    return condition


def _apply_waiting_place_policy(condition):
    condition["categories"] = _filter_categories(
        condition.get("categories"),
        WAITING_PLACE_ALLOWED_CATEGORIES,
        ["cafe", "city_park", "shelter"],
    )

    condition_text = _condition_policy_text(condition)
    preferred_tags = []
    for tag in _unique_list(condition.get("preferred_tags")):
        if tag in WAITING_PLACE_DEFAULT_TAGS or _has_explicit_tag_signal(condition_text, tag):
            preferred_tags.append(tag)

    for tag in WAITING_PLACE_DEFAULT_TAGS:
        if tag not in preferred_tags:
            preferred_tags.append(tag)

    condition["preferred_tags"] = preferred_tags
    condition["required_tags"] = [
        tag
        for tag in _unique_list(condition.get("required_tags"))
        if tag in WAITING_PLACE_DEFAULT_TAGS or _has_explicit_tag_signal(condition_text, tag)
    ]
    return condition


def _apply_scenario_policy(condition):
    scenario = condition.get("scenario")
    if scenario == "work_cafe":
        return _apply_work_cafe_policy(condition)
    if scenario == "waiting_place":
        return _apply_waiting_place_policy(condition)
    return condition


def get_min_radius(scenario):
    return SCENARIO_MIN_RADIUS.get(scenario, 300)


def _parse_radius(value, default, min_radius=300):
    if value in (None, ""):
        return default

    try:
        radius = int(value)
    except (TypeError, ValueError):
        return default

    return min(max(radius, min_radius), 20000)


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
        "menu_keywords": [],
        "place_type_keywords": [],
        "purpose_keywords": [],
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
            normalized["radius"] = _parse_radius(
                value,
                normalized["radius"],
                get_min_radius(normalized.get("scenario")),
            )
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
        normalized["radius"] = _parse_radius(
            radius,
            normalized["radius"],
            get_min_radius(normalized.get("scenario")),
        )

    normalized["required_tags"] = _unique_list(normalized.get("required_tags"))
    normalized["preferred_tags"] = _unique_list(normalized.get("preferred_tags"))
    normalized["avoid_tags"] = _unique_list(normalized.get("avoid_tags"))
    normalized["categories"] = _unique_list(normalized.get("categories"))
    normalized["keywords"] = _unique_list(normalized.get("keywords"))
    normalized["menu_keywords"] = _unique_list(normalized.get("menu_keywords"))
    normalized["place_type_keywords"] = _unique_list(normalized.get("place_type_keywords"))
    normalized["purpose_keywords"] = _unique_list(normalized.get("purpose_keywords"))
    normalized["exclude_categories"] = _unique_list(normalized.get("exclude_categories"))
    normalized["tags"] = list(normalized["preferred_tags"])
    normalized["fallback_enabled"] = _parse_bool(normalized.get("fallback_enabled"), True)
    normalized["radius"] = _parse_radius(
        normalized.get("radius"),
        get_default_radius(normalized.get("scenario")),
        get_min_radius(normalized.get("scenario")),
    )
    normalized = _apply_scenario_policy(normalized)
    normalized["tags"] = list(normalized["preferred_tags"])
    return normalized
