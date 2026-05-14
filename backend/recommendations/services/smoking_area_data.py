import json
import math
from pathlib import Path
from django.conf import settings


SMOKING_DATA_PATH = (
    settings.BASE_DIR.parent
    / "ExData"
    / "JsonData"
    / "smoking_places_normalized.json"
)


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


def load_smoking_areas():
    if not SMOKING_DATA_PATH.exists():
        return []

    with open(SMOKING_DATA_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def get_value(item, candidates):
    for key in candidates:
        if key in item and item[key] not in [None, ""]:
            return item[key]
    return None


def normalize_name(value):
    if isinstance(value, dict):
        return value.get("ko") or value.get("en") or "흡연구역"

    return value or "흡연구역"


def normalize_smoking_area(item):
    """
    흡연구역 JSON의 컬럼명이 다를 수 있으므로 후보 키를 여러 개 둔다.
    실제 파일 구조에 맞춰 키 이름은 조정해야 한다.
    """
    raw_name = get_value(item, ["name", "place_name", "시설명", "장소명", "설치위치"])
    name = normalize_name(raw_name)

    address = get_value(item, ["address", "주소", "도로명주소", "지번주소"])
    lat = get_value(item, ["lat", "latitude", "위도", "y"])
    lng = get_value(item, ["lng", "longitude", "경도", "x"])

    if lat is None or lng is None:
        return None

    try:
        lat = float(lat)
        lng = float(lng)
    except ValueError:
        return None

    return {
        "name": name,
        "category": "흡연구역",
        "address": address or "",
        "lat": lat,
        "lng": lng,
        "raw": item,
    }


def search_nearby_smoking_areas(lat, lng, radius=1000, size=5):
    raw_items = load_smoking_areas()

    results = []

    for item in raw_items:
        place = normalize_smoking_area(item)

        if place is None:
            continue

        distance = calculate_distance_m(
            lat,
            lng,
            place["lat"],
            place["lng"],
        )

        if distance > radius:
            continue

        place["distance"] = distance
        results.append(place)

    results.sort(key=lambda place: place["distance"])

    return results[:size]


def map_smoking_area_to_recommendation(place):
    return {
        "name": place["name"],
        "category": "흡연구역",
        "address": place["address"],
        "distance": place["distance"],
        "runtime_tags": ["흡연", "흡연구역"],
        "verified_tags": ["자체수집데이터"],
        "score": calculate_smoking_score(place["distance"]),
        "recommend_reason": f"현재 위치에서 {place['distance']}m 떨어진 흡연구역 후보입니다. 자체 수집 데이터를 기준으로 추천했습니다.",
        "caution": "현재 운영 여부와 현장 상태는 확인이 필요합니다.",
        "lat": place["lat"],
        "lng": place["lng"],
        "source": "local_smoking_data",
        "navigation_url": f"https://map.kakao.com/link/to/{place['name']},{place['lat']},{place['lng']}",
    }


def calculate_smoking_score(distance):
    score = 50

    if distance <= 100:
        score += 35
    elif distance <= 300:
        score += 25
    elif distance <= 700:
        score += 15
    elif distance <= 1000:
        score += 8

    return min(score, 100)