import math

from recommendations.models import Place
from recommendations.services.recommendation_condition import (
    build_recommendation_condition,
    get_default_radius,
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


DEFAULT_CAUTION = "태그 정보는 후보 정보일 수 있으며 실제 이용 가능 여부는 확인이 필요합니다."

WAITING_PLACE_EXCLUDE_KEYWORDS = [
    "행정복지센터",
    "주민센터",
    "동사무소",
    "구청",
    "시청",
    "군청",
    "읍사무소",
    "면사무소",
    "민원센터",
    "복지센터",
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

    score = (
        20
        + category_score
        + tag_score
        + distance_score
        + quality_score
        + waiting_adjustment["bonus"]
        - warning_penalty
        - avoid_penalty
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
        "avoid_tag_penalty": avoid_penalty,
        "matched_avoid_tags": matched_avoid_tags,
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
):
    required_tags = required_tags or []
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

    if verified_matches and not required_missing_tags and len(missing_tags) <= 1:
        return {
            "source_type": "db_verified",
            "confidence": "high",
            "is_verified": True,
            "fallback_level": 1,
            "missing_tags": missing_tags,
            "required_missing_tags": required_missing_tags,
            "caution_message": "",
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
        }

    return {
        "source_type": "db_category_fallback",
        "confidence": "low",
        "is_verified": False,
        "fallback_level": 5,
        "missing_tags": missing_tags,
        "required_missing_tags": required_missing_tags,
        "caution_message": "입력 조건과의 일치 근거가 부족하여 확인이 필요한 후보입니다.",
    }


def apply_score_cap(score, metadata, matched_tags, missing_tags, score_breakdown):
    cap = 100
    cap_reasons = []

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

    category_only = (
        score_breakdown.get("category", 0) > 0
        and not matched_tags
    )
    if category_only:
        cap = min(cap, 50)
        cap_reasons.append("category_only")

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
        "fallback_label": get_fallback_label(fallback_level),
        "fallback_description": get_fallback_description(fallback_level),
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

    if metadata.get("source_type") == "db_category_fallback":
        parts.append("따라서 검증 추천이 아니라 카테고리 기반 fallback 후보로 제공됩니다.")
    elif not metadata.get("is_verified"):
        parts.append("일부 근거가 후보 태그 기반이므로 방문 전 확인이 필요합니다.")

    if (score_breakdown or {}).get("waiting_place_penalty_reason"):
        parts.append("또한 일반적인 잠깐 휴식 목적과는 맞지 않을 수 있어 후순위로 반영했습니다.")

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
    )
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
    visible_matched_tags = get_visible_tag_names(matched_tags)
    visible_missing_tags = get_visible_tag_names(missing_tags)

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
    radius = min(
        max(_parse_int(radius, context.get("radius") or get_default_radius(context["scenario"])), 300),
        20000,
    )
    context["radius"] = radius

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
            preferred_tags=context["preferred_tags"],
            required_tags=context["required_tags"],
            avoid_tags=context["avoid_tags"],
            distance=distance,
            scenario=context["scenario"],
        )

        if score_breakdown.get("excluded_by_waiting_place"):
            continue

        missing_tags = _missing_tags(
            tag_data,
            required_tags=context["required_tags"],
            preferred_tags=context["preferred_tags"],
        )
        category_matches = place.category in set(context["categories"])
        match_level = get_match_level(matched_tags, category_matches)
        metadata = build_result_metadata(
            tag_data=tag_data,
            matched_tags=matched_tags,
            missing_tags=missing_tags,
            match_level=match_level,
            score_breakdown=score_breakdown,
            required_tags=context["required_tags"],
        )
        score, score_cap, score_cap_reasons = apply_score_cap(
            score,
            metadata,
            matched_tags,
            missing_tags,
            score_breakdown,
        )
        score_breakdown = {
            **score_breakdown,
            "score_cap": score_cap,
            "score_cap_reasons": score_cap_reasons,
        }

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
                condition=context,
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
        },
        "results": results,
    }
