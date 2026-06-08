from recommendations.models import Place


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
        tag_text = ", ".join(saved_tag_data["suggested_tags"][:3])

        if scenario == "work_cafe":
            return (
                f"현재 위치에서 {distance}m 떨어져 있고, "
                f"수집된 태그 후보에 {tag_text} 정보가 있어 작업 장소 후보로 추천합니다."
            )

        if scenario == "waiting_place":
            return (
                f"현재 위치에서 {distance}m 떨어져 있고, "
                f"수집된 태그 후보에 {tag_text} 정보가 있어 잠깐 머물 장소 후보로 추천합니다."
            )

        return (
            f"현재 위치에서 {distance}m 떨어져 있고, "
            f"수집된 태그 후보에 {tag_text} 정보가 있어 추천합니다."
        )

    if scenario == "work_cafe":
        return (
            f"현재 위치에서 {distance}m 떨어진 작업 장소 후보입니다. "
            "카테고리와 장소 정보를 기준으로 추천했습니다."
        )

    if scenario == "waiting_place":
        return (
            f"현재 위치에서 {distance}m 떨어져 있어 "
            "약속 전 잠깐 머물 장소 후보로 추천합니다."
        )

    if scenario == "walk_healing":
        return "산책이나 휴식 목적에 맞는 장소 후보입니다. 거리와 장소 유형을 기준으로 추천했습니다."

    if scenario == "smoking_area":
        return "현재 위치 주변의 흡연 가능 장소 후보입니다. 실제 이용 가능 여부는 확인이 필요합니다."

    return "현재 위치와 장소 정보를 기준으로 추천한 후보입니다."


def map_kakao_place_to_recommendation(place, scenario):
    runtime_tags = build_runtime_tags(place, scenario)

    saved_place = get_saved_place_by_kakao_id(place)
    saved_tag_data = get_saved_tag_data(saved_place)

    score = calculate_recommendation_score(
        place,
        runtime_tags,
        saved_tag_data=saved_tag_data,
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
        "recommend_reason": build_recommend_reason(
            place,
            scenario,
            runtime_tags,
            saved_tag_data=saved_tag_data,
        ),
        "caution": (
            "수집 태그는 블로그 검색 결과 기반의 후보 정보이며, "
            "실제 시설 여부는 확인이 필요합니다."
        ),

        # 위치/출처
        "lat": float(place.get("y")),
        "lng": float(place.get("x")),
        "source": "kakao_local",
        "source_name": saved_place.source_name if saved_place else "kakao_local",
        "data_quality_score": saved_place.data_quality_score if saved_place else None,
        "raw_scores": saved_tag_data["raw_scores"],
        "navigation_url": place.get("place_url"),
    }