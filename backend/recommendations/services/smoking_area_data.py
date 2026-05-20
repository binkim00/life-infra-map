import math

from recommendations.models import Place


def calculate_distance_m(lat1, lng1, lat2, lng2):
    """
    두 좌표 사이의 거리를 미터 단위로 계산한다.
    """
    radius = 6371000

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lng / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return int(radius * c)


def search_nearby_smoking_areas(lat, lng, radius=1000, size=5):
    places = Place.objects.filter(
        category="smoking_area",
        data_quality_status="usable",
    )

    results = []

    for place in places:
        distance = calculate_distance_m(
            lat,
            lng,
            place.lat,
            place.lng,
        )

        if distance > radius:
            continue

        results.append({
            "id": place.id,
            "name": place.name,
            "category": place.category,
            "address": place.address,
            "detail_location": place.detail_location,
            "lat": place.lat,
            "lng": place.lng,
            "distance": distance,
            "source": place.source,
            "source_name": place.source_name,
            "data_quality_status": place.data_quality_status,
            "data_quality_score": place.data_quality_score,
            "tags": [
                place_tag.tag.name
                for place_tag in place.place_tags.select_related("tag").all()
            ],
        })

    results.sort(key=lambda place: place["distance"])

    return results[:size]


def map_smoking_area_to_recommendation(place):
    tags = place.get("tags", [])

    verified_tags = []
    runtime_tags = ["흡연", "흡연구역"]

    for tag in tags:
        if tag not in runtime_tags:
            verified_tags.append(tag)

    return {
        "id": place["id"],
        "name": place["name"],
        "category": "흡연구역",
        "address": place["address"],
        "detail_location": place["detail_location"],
        "distance": place["distance"],
        "runtime_tags": runtime_tags,
        "verified_tags": verified_tags,
        "score": calculate_smoking_score(
            place["distance"],
            place.get("data_quality_score", 50),
        ),
        "recommend_reason": f"현재 위치에서 {place['distance']}m 떨어진 흡연구역입니다. DB에 저장된 정제 데이터를 기준으로 추천했습니다.",
        "caution": "현재 운영 여부와 현장 상태는 확인이 필요합니다.",
        "lat": place["lat"],
        "lng": place["lng"],
        "source": "local_db",
        "source_name": place["source_name"],
        "navigation_url": f"https://map.kakao.com/link/to/{place['name']},{place['lat']},{place['lng']}",
    }


def calculate_smoking_score(distance, data_quality_score=50):
    score = 50

    if distance <= 100:
        score += 35
    elif distance <= 300:
        score += 25
    elif distance <= 700:
        score += 15
    elif distance <= 1000:
        score += 8

    score += int(data_quality_score * 0.1)

    return min(score, 100)