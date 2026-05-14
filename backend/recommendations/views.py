from rest_framework.decorators import api_view
from rest_framework.response import Response

from .services.kakao_local import search_places_by_keyword
from .services.place_mapper import map_kakao_place_to_recommendation

SCENARIO_KEYWORDS = {
    "work_cafe": "카페",
    "waiting_place": "카페",
    "walk_healing": "공원",
    "smoking_area": "흡연구역",
}

MOCK_RESULTS = {
    "work_cafe": [
        {
            "name": "샘플 작업 카페",
            "category": "카페",
            "address": "서울시 중구 샘플로 1",
            "distance": 320,
            "runtime_tags": ["카페", "실내후보", "작업가능후보"],
            "verified_tags": ["콘센트확인"],
            "score": 82,
            "recommend_reason": "현재 위치에서 가깝고, 실내에서 머물 수 있는 카페 후보입니다.",
            "caution": "조용함 여부는 확인되지 않은 후보 정보입니다.",
            "lat": 37.5665,
            "lng": 126.9780,
            "navigation_url": "https://map.kakao.com/link/to/샘플 작업 카페,37.5665,126.9780",
        }
    ],
    "waiting_place": [
        {
            "name": "샘플 대기 장소",
            "category": "공공시설",
            "address": "서울시 중구 대기로 2",
            "distance": 180,
            "runtime_tags": ["실내후보", "잠깐쉬기", "대기하기좋음후보"],
            "verified_tags": [],
            "score": 78,
            "recommend_reason": "현재 위치에서 가깝고, 잠깐 머물기 좋은 후보 장소입니다.",
            "caution": "실제 좌석 여부는 확인되지 않았습니다.",
            "lat": 37.5651,
            "lng": 126.9775,
            "navigation_url": "https://map.kakao.com/link/to/샘플 대기 장소,37.5651,126.9775",
        }
    ],
    "walk_healing": [
        {
            "name": "샘플 근린공원",
            "category": "공원",
            "address": "서울시 중구 산책로 3",
            "distance": 540,
            "runtime_tags": ["공원", "야외", "산책후보", "휴식후보"],
            "verified_tags": ["화장실"],
            "score": 75,
            "recommend_reason": "산책과 휴식 목적에 맞는 야외 장소 후보입니다.",
            "caution": "혼잡도와 실제 산책로 상태는 확인되지 않았습니다.",
            "lat": 37.5640,
            "lng": 126.9761,
            "navigation_url": "https://map.kakao.com/link/to/샘플 근린공원,37.5640,126.9761",
        }
    ],
    "smoking_area": [
        {
            "name": "샘플 흡연구역",
            "category": "흡연구역",
            "address": "서울시 중구 흡연로 4",
            "distance": 210,
            "runtime_tags": ["흡연", "흡연구역", "실외후보"],
            "verified_tags": ["좌표확인"],
            "score": 86,
            "recommend_reason": "현재 위치에서 가까운 흡연구역 후보입니다.",
            "caution": "현재 이용 가능 여부는 확인이 필요합니다.",
            "lat": 37.5632,
            "lng": 126.9754,
            "navigation_url": "https://map.kakao.com/link/to/샘플 흡연구역,37.5632,126.9754",
        }
    ],
}


@api_view(["GET"])
def health_check(request):
    return Response({
        "message": "recommendations API is working"
    })


@api_view(["GET"])
def recommendation_search(request):
    scenario = request.GET.get("scenario", "work_cafe")
    lat = float(request.GET.get("lat", 37.5665))
    lng = float(request.GET.get("lng", 126.9780))

    keyword = SCENARIO_KEYWORDS.get(scenario, "카페")

    kakao_data = search_places_by_keyword(
        keyword=keyword,
        lat=lat,
        lng=lng,
        radius=1000,
        size=5,
    )

    results = [
        map_kakao_place_to_recommendation(place, scenario)
        for place in kakao_data.get("documents", [])
    ]

    return Response({
        "scenario": scenario,
        "keyword": keyword,
        "results": results,
    })

@api_view(["GET"])
def kakao_search_test(request):
    keyword = request.GET.get("keyword", "카페")
    lat = request.GET.get("lat")
    lng = request.GET.get("lng")

    lat = float(lat) if lat else None
    lng = float(lng) if lng else None

    data = search_places_by_keyword(
        keyword=keyword,
        lat=lat,
        lng=lng,
        radius=1000,
        size=5,
    )

    return Response(data)