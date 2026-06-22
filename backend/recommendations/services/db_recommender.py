import math

from recommendations.models import Place
from recommendations.services.smoking_area_data import calculate_distance_m


DEFAULT_CAUTION = "태그 정보는 후보 정보일 수 있으며 실제 이용 가능 여부는 확인이 필요합니다."

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
}

SCENARIO_DEFAULT_RADIUS = {
    "work_cafe": 1500,
    "waiting_place": 1200,
    "walk_healing": 3000,
    "smoking_area": 800,
}

WAITING_PLACE_EXCLUDE_KEYWORDS = [
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
    "요양원",
    "어린이집",
    "유치원",
    "학교",
]

WAITING_PLACE_PENALTY_KEYWORDS = [
    "복지센터",
    "행정복지센터",
    "주민센터",
    "동사무소",
    "구청",
    "시청",
    "민원센터",
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


def get_scenario_config(scenario):
    return SCENARIO_CONFIGS.get(scenario, SCENARIO_CONFIGS["work_cafe"])


def get_default_radius(scenario):
    return SCENARIO_DEFAULT_RADIUS.get(scenario, 1500)


def normalize_recommendation_context(
    scenario="work_cafe",
    categories=None,
    tags=None,
    keyword=None,
    exclude_categories=None,
):
    normalized_scenario = scenario if scenario in SCENARIO_CONFIGS else "custom"
    config = get_scenario_config(scenario)
    normalized_categories = list(dict.fromkeys(categories or config["categories"]))
    normalized_tags = list(dict.fromkeys(tags or config["tags"]))

    return {
        "scenario": normalized_scenario,
        "keyword": keyword or config["keyword"],
        "categories": normalized_categories,
        "tags": normalized_tags,
        "exclude_categories": list(dict.fromkeys(exclude_categories or [])),
    }


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


def _tag_score(tag_data, preferred_tags):
    preferred = set(preferred_tags)
    matched = []
    score = 0

    for tag_name in tag_data["verified_tags"]:
        if tag_name in preferred:
            matched.append(tag_name)
            score += 10

    for tag_name in tag_data["suggested_tags"]:
        if tag_name in preferred:
            matched.append(tag_name)
            score += 7

    return min(score, 35), list(dict.fromkeys(matched))


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
            " ".join(tags),
        ]
    )


def _has_keyword(text, keywords):
    return any(keyword in text for keyword in keywords)


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
        elif place_tag.is_verified or place_tag.status == "confirmed":
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


def score_place(place, tag_data, categories, preferred_tags, distance, scenario=None):
    category_score = _category_score(place, categories)
    tag_score, matched_tags = _tag_score(tag_data, preferred_tags)
    distance_score = _distance_score(distance)
    quality_score = _quality_score(place)
    warning_penalty = _warning_penalty(tag_data)
    waiting_adjustment = (
        get_waiting_place_adjustment(place, tag_data)
        if scenario == "waiting_place"
        else {"exclude": False, "penalty": 0, "bonus": 0, "reason": None}
    )

    score = (
        20
        + category_score
        + tag_score
        + distance_score
        + quality_score
        + waiting_adjustment["bonus"]
        - warning_penalty
        - waiting_adjustment["penalty"]
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
        "waiting_place_bonus": waiting_adjustment["bonus"],
        "unsuitable_place_penalty": waiting_adjustment["penalty"],
        "waiting_place_penalty_reason": waiting_adjustment["reason"],
        "excluded_by_waiting_place": waiting_adjustment["exclude"],
    }


def get_match_level(matched_tags, category_matches):
    if matched_tags:
        return "tag_matched"

    if category_matches:
        return "category_distance_fallback"

    return "low_match"


def get_recommendation_confidence(score, match_level, matched_tags):
    if match_level == "tag_matched" and len(matched_tags) >= 2 and score >= 80:
        return "high"

    if match_level in {"tag_matched", "category_distance_fallback"} and score >= 60:
        return "medium"

    return "low"


def build_db_recommend_reason(place, scenario, distance, matched_tags, match_level, score_breakdown=None):
    parts = []

    if distance is not None:
        parts.append(f"현재 위치에서 약 {distance}m 떨어져 있습니다.")

    if matched_tags:
        parts.append(f"{', '.join(matched_tags[:3])} 태그가 상황 조건과 일치합니다.")
    elif match_level == "category_distance_fallback":
        parts.append(
            "세부 태그 정보가 부족해 카테고리와 현재 위치에서의 거리를 기준으로 추천했습니다."
        )
    elif place.category:
        parts.append(f"{place.category} 카테고리가 입력 조건과 일부 관련됩니다.")

    if scenario == "work_cafe":
        parts.append("조용히 머물거나 작업하기 좋은 후보입니다.")
    elif scenario == "waiting_place":
        if (score_breakdown or {}).get("waiting_place_penalty_reason"):
            parts.append("일반적인 잠깐 휴식 목적과는 맞지 않을 수 있어 후순위로 반영했습니다.")
        else:
            parts.append("잠깐 쉬거나 대기하기 좋은 후보입니다.")
    elif scenario == "walk_healing":    
        parts.append("산책이나 휴식 목적에 맞는 후보입니다.")
    elif scenario == "smoking_area":
        parts.append("가까운 흡연 가능 장소 후보입니다.")
    else:
        parts.append("입력한 상황 조건에 맞는 DB 기반 후보입니다.")

    return " ".join(parts)


def serialize_recommendation(
    place,
    scenario,
    distance=None,
    matched_tags=None,
    score=None,
    score_breakdown=None,
):
    tag_data = get_place_tag_data(place)
    matched_tags = matched_tags or []

    if score is None or score_breakdown is None:
        score, matched_tags, score_breakdown = score_place(
            place=place,
            tag_data=tag_data,
            categories=[place.category],
            preferred_tags=matched_tags,
            distance=distance,
            scenario=scenario,
        )

    category_matches = bool(place.category)
    match_level = get_match_level(matched_tags, category_matches)
    confidence = get_recommendation_confidence(score, match_level, matched_tags)

    reason = build_db_recommend_reason(
        place,
        scenario,
        distance,
        matched_tags,
        match_level,
        score_breakdown,
    )

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
        "runtime_tags": matched_tags,
        "matched_tags": matched_tags,
        "match_level": match_level,
        "recommendation_confidence": confidence,
        "suggested_tags": tag_data["suggested_tags"],
        "verified_tags": tag_data["verified_tags"],
        "warning_tags": tag_data["warning_tags"],
        "tag_details": tag_data["tag_details"],
        "recommend_reason": reason,
        "reason": reason,
        "caution": DEFAULT_CAUTION,
        "source": place.source,
        "external_id": place.external_id,
        "source_name": place.source_name,
        "data_quality_score": place.data_quality_score,
        "data_quality_status": place.data_quality_status,
        "raw_scores": tag_data["raw_scores"],
        "score_breakdown": score_breakdown,
    }


def search_db_recommendations(
    scenario="work_cafe",
    lat=None,
    lng=None,
    categories=None,
    tags=None,
    keyword=None,
    exclude_categories=None,
    limit=10,
    radius=None,
):
    lat = _parse_float(lat)
    lng = _parse_float(lng)
    limit = min(max(_parse_int(limit, 10), 1), 50)

    context = normalize_recommendation_context(
        scenario=scenario,
        categories=categories,
        tags=tags,
        keyword=keyword,
        exclude_categories=exclude_categories,
    )
    radius = min(
        max(_parse_int(radius, get_default_radius(context["scenario"])), 300),
        20000,
    )

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

    for place_id in candidate_ids:
        place = places_by_id.get(place_id)
        if not place:
            continue

        distance = distance_by_place_id.get(place.id)
        tag_data = get_place_tag_data(place)
        score, matched_tags, score_breakdown = score_place(
            place=place,
            tag_data=tag_data,
            categories=context["categories"],
            preferred_tags=context["tags"],
            distance=distance,
            scenario=context["scenario"],
        )

        if score_breakdown.get("excluded_by_waiting_place"):
            continue

        candidates.append((
            score,
            distance if distance is not None else 999999999,
            place,
            matched_tags,
            score_breakdown,
        ))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2].id))

    results = []
    for score, distance, place, matched_tags, score_breakdown in candidates[:limit]:
        normalized_distance = None if distance == 999999999 else distance
        results.append(
            serialize_recommendation(
                place=place,
                scenario=context["scenario"],
                distance=normalized_distance,
                matched_tags=matched_tags,
                score=score,
                score_breakdown=score_breakdown,
            )
        )

    return {
        "scenario": context["scenario"],
        "keyword": context["keyword"],
        "conditions": {
            "categories": context["categories"],
            "exclude_categories": context["exclude_categories"],
            "tags": context["tags"],
            "lat": lat,
            "lng": lng,
            "radius": radius,
            "limit": limit,
        },
        "results": results,
    }
