from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Place
from .services.kakao_local import search_places_by_keyword
from .services.place_mapper import (
    get_saved_tag_data,
    map_kakao_place_to_recommendation,
)
from .services.ai_situation_parser import parse_situation
from .services.ai_web_search_provider import (
    get_ai_web_search_result,
    get_ai_web_search_status,
)
from .services.db_recommender import search_db_recommendations
from .services.place_urls import get_kakao_place_url
from .services.smoking_area_data import (
    calculate_distance_m,
    search_nearby_smoking_areas,
    map_smoking_area_to_recommendation,
)

SCENARIO_KEYWORDS = {
    "work_cafe": "카페",
    "waiting_place": "카페",
    "walk_healing": "공원",
    "smoking_area": "흡연구역",
}

PLACE_CATEGORY_ALIASES = {
    "toilet": ["toilet", "화장실", "공중화장실", "공용화장실"],
    "freewifi": ["freewifi", "wifi", "wi-fi", "와이파이", "무료와이파이", "무선인터넷"],
    "smoking_area": ["smoking", "smoking_area", "흡연", "흡연구역", "흡연실"],
    "beach": ["beach", "해수욕장", "해변", "바다"],
    "parking": ["parking", "주차", "주차장"],
    "city_park": ["city_park", "citypark", "공원", "도시공원"],
    "tourism": ["tourism", "관광", "관광지", "여행", "명소"],
}

DB_MARKER_ALLOWED_CATEGORIES = [
    "toilet",
    "freewifi",
    "smoking_area",
    "beach",
    "parking",
    "city_park",
    "tourism",
]

@api_view(["GET"])
def health_check(request):
    return Response({
        "message": "recommendations API is working"
    })


def get_matching_categories(keyword):
    normalized_keyword = keyword.lower().replace(" ", "")
    matched_categories = []

    for category, aliases in PLACE_CATEGORY_ALIASES.items():
        if any(alias.lower().replace(" ", "") in normalized_keyword for alias in aliases):
            matched_categories.append(category)

    return matched_categories


def serialize_place(place, distance=None):
    kakao_place_url = get_kakao_place_url(place)
    data = {
        "id": place.id,
        "name": place.name,
        "category": place.category,
        "address": place.address,
        "detail_location": place.detail_location,
        "lat": place.lat,
        "lng": place.lng,
        "source": place.source,
        "external_id": place.external_id,
        "source_name": place.source_name,
        "kakao_place_url": kakao_place_url,
        "place_url": kakao_place_url,
        "source_updated_at": (
            place.source_updated_at.isoformat()
            if place.source_updated_at
            else None
        ),
        "data_quality_status": place.data_quality_status,
        "data_quality_score": place.data_quality_score,
        "raw": place.raw,
        "tags": [
            {
                "id": place_tag.tag.id,
                "name": place_tag.tag.name,
                "tag_type": place_tag.tag.tag_type,
                "source": place_tag.source,
                "status": place_tag.status,
                "confidence": place_tag.confidence,
                "evidence": place_tag.evidence,
                "is_verified": place_tag.is_verified,
            }
            for place_tag in place.place_tags.all()
        ],
        "created_at": place.created_at.isoformat(),
        "updated_at": place.updated_at.isoformat(),
    }

    if distance is not None:
        data["distance"] = distance

    return data


@api_view(["GET"])
def place_list(request):
    keyword = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    source = request.GET.get("source", "").strip()
    status = request.GET.get("status", "").strip()
    lat = request.GET.get("lat")
    lng = request.GET.get("lng")

    try:
        limit = int(request.GET.get("limit", 100))
    except ValueError:
        limit = 100

    try:
        radius = int(request.GET.get("radius", 0))
    except ValueError:
        radius = 0

    try:
        lat = float(lat) if lat else None
        lng = float(lng) if lng else None
    except ValueError:
        lat = None
        lng = None

    limit = min(max(limit, 1), 300)

    places = (
        Place.objects
        .filter(category__in=DB_MARKER_ALLOWED_CATEGORIES)
        .order_by("-updated_at", "-id")
    )

    if keyword:
        matched_categories = get_matching_categories(keyword)
        places = places.filter(
            Q(name__icontains=keyword)
            | Q(address__icontains=keyword)
            | Q(detail_location__icontains=keyword)
            | Q(category__icontains=keyword)
            | Q(source__icontains=keyword)
            | Q(source_name__icontains=keyword)
            | Q(external_id__icontains=keyword)
            | Q(place_tags__tag__name__icontains=keyword)
            | Q(category__in=matched_categories)
        ).distinct()

    if category:
        places = places.filter(category=category)

    if source:
        places = places.filter(source=source)

    if status:
        places = places.filter(data_quality_status=status)

    distance_by_place_id = {}

    if lat is not None and lng is not None:
        nearby_place_ids = []

        for place in places.only("id", "lat", "lng").iterator(chunk_size=1000):
            distance = calculate_distance_m(lat, lng, place.lat, place.lng)

            if radius and distance > radius:
                continue

            distance_by_place_id[place.id] = distance
            nearby_place_ids.append(place.id)

        nearby_place_ids.sort(key=lambda place_id: distance_by_place_id[place_id])
        total_count = len(nearby_place_ids)
        limited_place_ids = nearby_place_ids[:limit]

        places_by_id = {
            place.id: place
            for place in (
                Place.objects
                .filter(id__in=limited_place_ids)
                .prefetch_related("place_tags__tag")
            )
        }

        results = [
            serialize_place(
                places_by_id[place_id],
                distance=distance_by_place_id[place_id],
            )
            for place_id in limited_place_ids
            if place_id in places_by_id
        ]
    else:
        total_count = places.count()
        results = [
            serialize_place(place)
            for place in places.prefetch_related("place_tags__tag")[:limit]
        ]

    return Response({
        "total_count": total_count,
        "count": len(results),
        "limit": limit,
        "options": {
            "categories": list(
                Place.objects
                .filter(category__in=DB_MARKER_ALLOWED_CATEGORIES)
                .exclude(category="")
                .order_by("category")
                .values_list("category", flat=True)
                .distinct()
            ),
            "sources": list(
                Place.objects
                .exclude(source="")
                .order_by("source")
                .values_list("source", flat=True)
                .distinct()
            ),
            "statuses": list(
                Place.objects
                .exclude(data_quality_status="")
                .order_by("data_quality_status")
                .values_list("data_quality_status", flat=True)
                .distinct()
            ),
        },
        "filters": {
            "q": keyword,
            "category": category,
            "source": source,
            "status": status,
            "lat": lat,
            "lng": lng,
            "radius": radius,
        },
        "results": results,
    })


@api_view(["GET"])
def kakao_place_tag_lookup(request):
    external_ids = [
        external_id.strip()
        for external_id in request.GET.get("external_ids", "").split(",")
        if external_id.strip()
    ]
    external_ids = list(dict.fromkeys(external_ids))[:100]

    places = (
        Place.objects
        .filter(source="kakao_local", external_id__in=external_ids)
        .prefetch_related("place_tags__tag")
    )

    results = {}

    for place in places:
        tag_data = get_saved_tag_data(place)

        results[place.external_id] = {
            "saved_place_id": place.id,
            "name": place.name,
            "category": place.category,
            "source_name": place.source_name,
            "data_quality_status": place.data_quality_status,
            "data_quality_score": place.data_quality_score,
            "suggested_tags": tag_data["suggested_tags"],
            "verified_tags": tag_data["verified_tags"],
            "warning_tags": tag_data["warning_tags"],
            "tag_details": tag_data["tag_details"],
            "raw_scores": tag_data["raw_scores"],
        }

    return Response({
        "count": len(results),
        "results": results,
    })


@api_view(["GET"])
def recommendation_search(request):
    scenario = request.GET.get("scenario", "work_cafe")
    lat = request.GET.get("lat")
    lng = request.GET.get("lng")
    limit = request.GET.get("limit", 10)
    radius = request.GET.get("radius")

    data = search_db_recommendations(
        scenario=scenario,
        lat=lat,
        lng=lng,
        limit=limit,
        radius=radius,
    )

    return Response(data)


@api_view(["POST"])
def ai_recommendation_search(request):
    query = request.data.get("query", "")
    lat = request.data.get("lat")
    lng = request.data.get("lng")
    limit = request.data.get("limit", 10)
    radius = request.data.get("radius")

    parsed = parse_situation(query)
    data = search_db_recommendations(
        scenario=parsed["scenario"],
        condition=parsed,
        lat=lat,
        lng=lng,
        keyword=parsed["situation_summary"],
        exclude_categories=parsed.get("exclude_categories"),
        limit=limit,
        radius=radius,
    )
    data["ai_parse"] = parsed
    data["ai_web_search"] = get_ai_web_search_status()

    return Response(data)


@api_view(["POST"])
def ai_web_search(request):
    query = request.data.get("query", "")
    lat = request.data.get("lat")
    lng = request.data.get("lng")
    condition = request.data.get("condition") or {}
    existing_results_summary = request.data.get("existing_results_summary") or {}

    data = get_ai_web_search_result(
        query=query,
        lat=lat,
        lng=lng,
        condition=condition,
        existing_results_summary=existing_results_summary,
        manual=True,
    )

    return Response({
        "ai_web_search": data,
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
