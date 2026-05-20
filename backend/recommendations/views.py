from rest_framework.decorators import api_view
from rest_framework.response import Response

from .services.kakao_local import search_places_by_keyword
from .services.place_mapper import map_kakao_place_to_recommendation
from .services.smoking_area_data import (
    search_nearby_smoking_areas,
    map_smoking_area_to_recommendation,
)

SCENARIO_KEYWORDS = {
    "work_cafe": "카페",
    "waiting_place": "카페",
    "walk_healing": "공원",
    "smoking_area": "흡연구역",
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

    if scenario == "smoking_area":
        smoking_places = search_nearby_smoking_areas(
            lat=lat,
            lng=lng,
            radius=1000,
            size=5,
        )

        results = [
            map_smoking_area_to_recommendation(place)
            for place in smoking_places
        ]

        return Response({
            "scenario": scenario,
            "keyword": "흡연구역",
            "source": "local_smoking_data",
            "results": results,
        })

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
        "source": "kakao_local",
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