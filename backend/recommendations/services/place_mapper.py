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


def calculate_recommendation_score(place, tags):
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

    score += min(len(tags) * 5, 20)

    return min(score, 100)


def build_recommend_reason(place, scenario, tags):
    distance = place.get("distance")

    if scenario == "work_cafe":
        return f"현재 위치에서 {distance}m 떨어진 작업 장소 후보입니다. 카테고리와 장소 정보를 기준으로 추천했습니다."

    if scenario == "waiting_place":
        return f"현재 위치에서 {distance}m 떨어져 있어 약속 전 잠깐 머물 장소 후보로 추천합니다."

    if scenario == "walk_healing":
        return f"산책이나 휴식 목적에 맞는 장소 후보입니다. 거리와 장소 유형을 기준으로 추천했습니다."

    if scenario == "smoking_area":
        return f"현재 위치 주변의 흡연 가능 장소 후보입니다. 실제 이용 가능 여부는 확인이 필요합니다."

    return "현재 위치와 장소 정보를 기준으로 추천한 후보입니다."


def map_kakao_place_to_recommendation(place, scenario):
    tags = build_runtime_tags(place, scenario)
    score = calculate_recommendation_score(place, tags)

    return {
        "name": place.get("place_name"),
        "category": place.get("category_name"),
        "address": place.get("road_address_name") or place.get("address_name"),
        "distance": int(place["distance"]) if place.get("distance") else None,
        "runtime_tags": tags,
        "verified_tags": [],
        "score": score,
        "recommend_reason": build_recommend_reason(place, scenario, tags),
        "caution": "지도 API 검색 결과를 기반으로 한 후보 정보이며, 세부 시설 여부는 확인이 필요합니다.",
        "lat": float(place.get("y")),
        "lng": float(place.get("x")),
        "source": "kakao_local",
        "navigation_url": place.get("place_url"),
    }