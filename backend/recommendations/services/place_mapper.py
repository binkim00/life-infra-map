from recommendations.models import Place
from recommendations.services.tag_utils import (
    get_confidence_label,
    get_fallback_description,
    get_fallback_label,
    get_source_label,
    get_tag_display_names,
    get_visible_tag_names,
)


def build_runtime_tags(place, scenario):
    category_name = place.get("category_name", "")
    place_name = place.get("place_name", "")

    tags = []

    if "카페" in category_name or "카페" in place_name:
        tags.extend(["카페", "실내후보"])

        if scenario == "work_cafe":
            tags.append("작업가능후보")

        if scenario == "waiting_place":
            tags.append("대기하기좋음후보")

    if "공원" in category_name or "공원" in place_name:
        tags.extend(["공원", "야외", "산책후보", "휴식후보"])

    if "도서관" in category_name or "도서관" in place_name:
        tags.extend(["도서관", "실내후보", "작업가능후보", "조용함후보"])

    if "전망" in place_name:
        tags.extend(["경관후보", "야경후보"])

    if "흡연" in place_name or "흡연" in category_name:
        tags.extend(["흡연구역후보"])

    return list(dict.fromkeys(tags))


def get_saved_place_by_kakao_id(place):
    """
    카카오 검색 결과의 id와 DB에 저장된 Place.external_id를 매칭합니다.
    카페 태그 수집 데이터의 external_id는 카카오 장소 ID입니다.
    """
    kakao_id = str(place.get("id", "")).strip()

    if not kakao_id:
        return None

    return (
        Place.objects
        .filter(source="kakao_local", external_id=kakao_id)
        .prefetch_related("place_tags__tag")
        .first()
    )


def get_saved_tag_data(saved_place):
    """
    DB에 저장된 PlaceTag를 화면 표시용 태그로 나눕니다.

    runtime_tags:
    - 검색 시점에 즉시 붙이는 태그

    suggested_tags:
    - 블로그 기반으로 수집한 추천 태그 후보

    verified_tags:
    - confirmed 또는 is_verified=True인 태그

    warning_tags:
    - 웨이팅주의 같은 주의 태그
    """
    if not saved_place:
        return {
            "suggested_tags": [],
            "verified_tags": [],
            "warning_tags": [],
            "tag_details": [],
            "raw_scores": {},
            "saved_place": None,
        }

    suggested_tags = []
    verified_tags = []
    warning_tags = []
    tag_details = []

    raw = saved_place.raw or {}
    raw_warning_tags = raw.get("warning_tags", [])
    raw_scores = raw.get("scores", {})

    for place_tag in saved_place.place_tags.select_related("tag").all():
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
        "saved_place": saved_place,
    }


def calculate_recommendation_score(place, runtime_tags, saved_tag_data=None):
    score = 50

    distance = place.get("distance")
    if distance:
        try:
            distance_value = int(distance)
            if distance_value <= 300:
                score += 25
            elif distance_value <= 700:
                score += 15
            elif distance_value <= 1000:
                score += 8
        except ValueError:
            pass

    # 기존 runtime 태그 점수
    score += min(len(runtime_tags) * 5, 20)

    # DB에 저장된 후보 태그 점수
    if saved_tag_data:
        suggested_tags = saved_tag_data.get("suggested_tags", [])
        verified_tags = saved_tag_data.get("verified_tags", [])
        warning_tags = saved_tag_data.get("warning_tags", [])
        saved_place = saved_tag_data.get("saved_place")
        raw_scores = saved_tag_data.get("raw_scores", {})

        score += min(len(suggested_tags) * 3, 18)
        score += min(len(verified_tags) * 5, 20)

        if saved_place:
            score += int(saved_place.data_quality_score * 0.1)

        ready_score = raw_scores.get("recommendation_ready_score")
        if ready_score is not None:
            try:
                score += int(float(ready_score) * 0.1)
            except (ValueError, TypeError):
                pass

        if warning_tags:
            score -= min(len(warning_tags) * 4, 12)

    return min(max(score, 0), 100)


def build_recommend_reason(place, scenario, runtime_tags, saved_tag_data=None):
    distance = place.get("distance")

    if saved_tag_data and saved_tag_data.get("suggested_tags"):
        tag_text = ", ".join(get_tag_display_names(saved_tag_data["suggested_tags"][:3]))

        if scenario == "work_cafe":
            return (
                f"사용자의 요청은 '노트북 작업하기 좋은 장소 추천'으로 해석되었습니다. "
                f"이 장소는 외부 검색 후보에 {tag_text} 후보 태그가 보강되어 작업 장소 후보로 분류되었습니다. "
                "후보 태그 기반 정보이므로 방문 전 실제 이용 가능 여부 확인이 필요합니다."
            )

        if scenario == "waiting_place":
            return (
                f"사용자의 요청은 '잠깐 쉬거나 머물기 좋은 장소 추천'으로 해석되었습니다. "
                f"이 장소는 외부 검색 후보에 {tag_text} 후보 태그가 보강되어 대기 장소 후보로 분류되었습니다. "
                "후보 태그 기반 정보이므로 방문 전 실제 이용 가능 여부 확인이 필요합니다."
            )

        return (
            f"이 장소는 외부 검색 후보에 {tag_text} 후보 태그가 보강된 후보입니다. "
            "후보 태그 기반 정보이므로 방문 전 실제 이용 가능 여부 확인이 필요합니다."
        )

    if scenario == "work_cafe":
        return (
            "사용자의 요청은 '노트북 작업하기 좋은 장소 추천'으로 해석되었습니다. "
            "이 장소는 외부 검색 결과의 카테고리와 위치 정보를 기준으로 제공되는 후보입니다. "
            "세부 태그 정보는 아직 부족해 낮은 신뢰도의 후보로 표시됩니다."
        )

    if scenario == "waiting_place":
        return (
            "사용자의 요청은 '잠깐 쉬거나 머물기 좋은 장소 추천'으로 해석되었습니다. "
            "이 장소는 외부 검색 결과의 카테고리와 위치 정보를 기준으로 제공되는 후보입니다. "
            "세부 태그 정보는 아직 부족해 낮은 신뢰도의 후보로 표시됩니다."
        )

    if scenario == "walk_healing":
        return "산책이나 휴식 목적에 맞는 장소 후보입니다. 거리와 장소 유형을 기준으로 추천했습니다."

    if scenario == "smoking_area":
        return "현재 위치 주변의 흡연 가능 장소 후보입니다. 실제 이용 가능 여부는 확인이 필요합니다."

    return "현재 위치와 장소 정보를 기준으로 추천한 후보입니다."


def build_kakao_result_metadata(saved_tag_data):
    verified_tags = saved_tag_data.get("verified_tags", [])
    suggested_tags = saved_tag_data.get("suggested_tags", [])

    if verified_tags:
        return {
            "source_type": "kakao_with_db_tags",
            "confidence": "medium",
            "is_verified": True,
            "fallback_level": 4,
            "caution_message": "외부 검색 결과에 DB 태그를 보강한 후보입니다. 방문 전 최신 정보 확인이 필요합니다.",
        }

    if suggested_tags:
        return {
            "source_type": "kakao_with_db_tags",
            "confidence": "medium",
            "is_verified": False,
            "fallback_level": 4,
            "caution_message": (
                "수집 태그는 후보 정보이며 실제 이용 가능 여부는 방문 전 확인이 필요합니다."
            ),
        }

    return {
        "source_type": "kakao_candidate",
        "confidence": "low",
        "is_verified": False,
        "fallback_level": 5,
        "caution_message": "세부 태그 데이터가 부족한 외부 검색 후보입니다.",
    }


def apply_kakao_score_cap(score, metadata):
    cap = 100

    if not metadata["is_verified"]:
        cap = min(cap, 75)

    if metadata["fallback_level"] == 4:
        cap = min(cap, 60)
    elif metadata["fallback_level"] == 5:
        cap = min(cap, 50)

    if metadata["source_type"] == "kakao_candidate":
        cap = min(cap, 50)

    return min(score, cap), cap


def map_kakao_place_to_recommendation(place, scenario):
    runtime_tags = build_runtime_tags(place, scenario)

    saved_place = get_saved_place_by_kakao_id(place)
    saved_tag_data = get_saved_tag_data(saved_place)

    score = calculate_recommendation_score(
        place,
        runtime_tags,
        saved_tag_data=saved_tag_data,
    )
    metadata = build_kakao_result_metadata(saved_tag_data)
    score, score_cap = apply_kakao_score_cap(score, metadata)
    matched_tags = saved_tag_data["verified_tags"] + saved_tag_data["suggested_tags"]
    visible_matched_tags = get_visible_tag_names(matched_tags)
    reason = build_recommend_reason(
        place,
        scenario,
        runtime_tags,
        saved_tag_data=saved_tag_data,
    )
    kakao_place_url = place.get("place_url") or (
        f"https://place.map.kakao.com/{place.get('id')}"
        if place.get("id")
        else ""
    )

    return {
        "id": place.get("id"),
        "saved_place_id": saved_place.id if saved_place else None,
        "name": place.get("place_name"),
        "category": place.get("category_name"),
        "address": place.get("road_address_name") or place.get("address_name"),
        "distance": int(place["distance"]) if place.get("distance") else None,

        # 태그 구분
        "runtime_tags": runtime_tags,
        "suggested_tags": saved_tag_data["suggested_tags"],
        "verified_tags": saved_tag_data["verified_tags"],
        "warning_tags": saved_tag_data["warning_tags"],
        "tag_details": saved_tag_data["tag_details"],

        # 점수/근거
        "score": score,
        "matched_tags": visible_matched_tags,
        "missing_tags": [],
        "matched_tag_labels": get_tag_display_names(visible_matched_tags),
        "missing_tag_labels": [],
        "source_type": metadata["source_type"],
        "confidence": metadata["confidence"],
        "is_verified": metadata["is_verified"],
        "fallback_level": metadata["fallback_level"],
        "source_label": get_source_label(metadata["source_type"]),
        "confidence_label": get_confidence_label(metadata["confidence"]),
        "fallback_label": get_fallback_label(metadata["fallback_level"]),
        "fallback_description": get_fallback_description(metadata["fallback_level"]),
        "score_cap": score_cap,
        "recommendation_reason": reason,
        "recommend_reason": reason,
        "caution_message": metadata["caution_message"],
        "caution": metadata["caution_message"],

        # 위치/출처
        "lat": float(place.get("y")),
        "lng": float(place.get("x")),
        "source": "kakao_local",
        "external_id": place.get("id"),
        "source_name": saved_place.source_name if saved_place else "kakao_local",
        "data_quality_score": saved_place.data_quality_score if saved_place else None,
        "raw_scores": saved_tag_data["raw_scores"],
        "kakao_place_url": kakao_place_url,
        "place_url": kakao_place_url,
        "navigation_url": place.get("place_url"),
    }
