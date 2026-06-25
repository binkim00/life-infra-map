import logging
import math

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from accounts.tier_notifications import (
    get_current_user_tier,
    notify_tier_upgrade_if_needed,
)
from .models import Place, PlaceReport, PlaceTag, Tag, UserPreference, UserSearchLog
from .serializers import (
    PlaceReportAdminReviewSerializer,
    PlaceReportCreateSerializer,
    PlaceReportDetailSerializer,
    PlaceReportListSerializer,
    UserPreferenceSerializer,
    UserSearchLogListSerializer,
    UserSearchLogSerializer,
)
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
from .services.conversational_search_planner import (
    BROAD_FRAME_CLARIFICATION_MESSAGE,
    BROAD_FRAME_CLARIFICATION_OPTIONS,
    build_conversational_search_plan,
    get_ai_frame_post_validation_reasons,
    sync_frame_location_to_search_plan,
)
from .services.ai_search_orchestrator import run_ai_search
from .services.db_recommender import search_db_recommendations
from .services.place_urls import get_kakao_place_url
from .services.smoking_area_data import (
    calculate_distance_m,
    search_nearby_smoking_areas,
    map_smoking_area_to_recommendation,
)
from .services.tag_utils import get_category_display_name
from .services.user_preferences import (
    USER_SELECTED_SOURCE,
    create_or_update_user_selected_preference,
    create_or_update_user_selected_tag_preference,
    rebuild_user_preferences,
    unique_valid_labels,
    update_user_preferences_from_search_log,
)


logger = logging.getLogger(__name__)

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

TAG_TYPE_GROUP_LABELS = {
    "category": "카테고리",
    "recommendation": "추천 태그",
    "warning": "주의/확인 필요",
}


def parse_positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return parsed if parsed > 0 else default


def paginated_response(queryset, serializer_class, request, default_page_size=5, max_page_size=20):
    page = parse_positive_int(request.GET.get("page"), 1)
    page_size = parse_positive_int(request.GET.get("page_size"), default_page_size)
    page_size = min(page_size, max_page_size)
    count = queryset.count()
    total_pages = max(math.ceil(count / page_size), 1)
    offset = (page - 1) * page_size
    serializer = serializer_class(queryset[offset:offset + page_size], many=True)

    return Response({
        "count": count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "results": serializer.data,
    })

@api_view(["GET"])
def health_check(request):
    return Response({
        "message": "recommendations API is working"
    })


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def search_logs(request):
    if request.method == "GET":
        search_log_queryset = UserSearchLog.objects.filter(
            user=request.user,
        ).order_by("-created_at")

        if "limit" in request.GET and "page" not in request.GET and "page_size" not in request.GET:
            limit = parse_positive_int(request.GET.get("limit"), 20)
            limit = min(limit, 50)
            serializer = UserSearchLogListSerializer(search_log_queryset[:limit], many=True)
            return Response({
                "results": serializer.data,
            })

        return paginated_response(
            search_log_queryset,
            UserSearchLogListSerializer,
            request,
            default_page_size=5,
            max_page_size=20,
        )

    serializer = UserSearchLogSerializer(
        data=request.data,
        context={"request": request},
    )

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    search_log = serializer.save()
    try:
        update_user_preferences_from_search_log(search_log)
    except Exception:
        logger.debug("Failed to update user preferences from search log.", exc_info=True)

    return Response(
        {
            "id": search_log.id,
            "message": "search log saved",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def search_log_detail(request, search_log_id):
    search_log = get_object_or_404(
        UserSearchLog,
        id=search_log_id,
        user=request.user,
    )
    search_log.delete()

    try:
        rebuild_user_preferences(request.user)
    except Exception:
        logger.debug("Failed to rebuild user preferences after search log delete.", exc_info=True)

    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def user_preferences(request):
    if request.method == "POST":
        try:
            tag_id = request.data.get("tag_id")
            if tag_id is not None and str(tag_id).strip():
                try:
                    normalized_tag_id = int(tag_id)
                except (TypeError, ValueError):
                    return Response(
                        {
                            "detail": "태그를 다시 확인해 주세요.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                tag = get_object_or_404(Tag, id=normalized_tag_id)
                preference, created = create_or_update_user_selected_tag_preference(
                    user=request.user,
                    tag=tag,
                )
            else:
                preference, created = create_or_update_user_selected_preference(
                    user=request.user,
                    preference_type=request.data.get("preference_type", "tag"),
                    label=request.data.get("label", ""),
                )
        except ValueError as error:
            return Response(
                {
                    "detail": str(error),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = UserPreferenceSerializer(preference)
        return Response(
            {
                "message": "preference created" if created else "preference updated",
                "preference": serializer.data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    preference_type = request.GET.get("type", "").strip()
    source = request.GET.get("source", "").strip()
    preferences = (
        UserPreference.objects
        .filter(user=request.user)
        .exclude(key__iexact="[object object]")
        .exclude(label__iexact="[object object]")
    )

    if preference_type:
        preferences = preferences.filter(preference_type=preference_type)

    if source:
        preferences = preferences.filter(source=source)

    preferences = preferences.order_by("-score", "-last_seen_at", "label")

    if "limit" in request.GET and "page" not in request.GET and "page_size" not in request.GET:
        limit = parse_positive_int(request.GET.get("limit"), 20)
        limit = min(limit, 50)
        serializer = UserPreferenceSerializer(preferences[:limit], many=True)
        return Response({
            "results": serializer.data,
        })

    return paginated_response(
        preferences,
        UserPreferenceSerializer,
        request,
        default_page_size=5,
        max_page_size=50,
    )


@api_view(["GET"])
def preference_tags(request):
    tags = Tag.objects.exclude(name="").order_by("tag_type", "name")
    return Response({
        "results": [
            {
                "id": tag.id,
                "name": tag.name,
                "display_name": tag.name,
                "group": TAG_TYPE_GROUP_LABELS.get(tag.tag_type, "기타"),
                "tag_type": tag.tag_type,
                "description": tag.description,
            }
            for tag in tags
        ],
    })


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def user_preference_detail(request, preference_id):
    preference = get_object_or_404(
        UserPreference,
        id=preference_id,
        user=request.user,
    )

    if preference.source != USER_SELECTED_SOURCE:
        return Response(
            {
                "detail": "자동으로 추정된 선호는 삭제할 수 없습니다.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    preference.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rebuild_preferences(request):
    rebuilt_count = rebuild_user_preferences(request.user)
    return Response({
        "message": "preferences rebuilt",
        "count": rebuilt_count,
    })


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def place_reports(request):
    if request.method == "GET":
        reports = (
            PlaceReport.objects
            .filter(user=request.user)
            .select_related("place", "reviewed_by")
            .prefetch_related("images")
            .order_by("-created_at")
        )
        return paginated_response(
            reports,
            PlaceReportListSerializer,
            request,
            default_page_size=5,
            max_page_size=20,
        )

    serializer = PlaceReportCreateSerializer(
        data=request.data,
        context={"request": request},
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    report = serializer.save()
    detail_serializer = PlaceReportDetailSerializer(
        report,
        context={"request": request},
    )
    return Response(
        {
            "message": "place report created",
            "report": detail_serializer.data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_place_reports(request):
    reports = (
        PlaceReport.objects
        .select_related("user", "place", "reviewed_by")
        .prefetch_related("images")
        .order_by("-created_at")
    )

    report_status = request.GET.get("status", "").strip()
    report_type = request.GET.get("report_type", "").strip()

    if report_status:
        reports = reports.filter(status=report_status)
    if report_type:
        reports = reports.filter(report_type=report_type)

    return paginated_response(
        reports,
        PlaceReportListSerializer,
        request,
        default_page_size=10,
        max_page_size=50,
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_place_report_detail(request, report_id):
    report = get_object_or_404(
        PlaceReport.objects
        .select_related("user", "place", "reviewed_by")
        .prefetch_related("images"),
        id=report_id,
    )
    serializer = PlaceReportDetailSerializer(report, context={"request": request})
    return Response(serializer.data)


def attach_report_tags_to_place(report, place, *, create_missing_tags=False):
    created_count = 0
    skipped_tags = []

    for tag_label in unique_valid_labels(report.suggested_tags):
        tag = Tag.objects.filter(name=tag_label).first()
        if not tag and create_missing_tags:
            tag = Tag.objects.create(name=tag_label, tag_type="recommendation")
        if not tag:
            skipped_tags.append(tag_label)
            continue
        if PlaceTag.objects.filter(place=place, tag=tag).exists():
            continue

        _, created = PlaceTag.objects.get_or_create(
            place=place,
            tag=tag,
            source="user_verified",
            defaults={
                "status": "confirmed",
                "confidence": 80,
                "evidence": f"사용자 제보 #{report.id} 관리자 승인",
                "is_verified": True,
                "verified_at": timezone.now(),
            },
        )
        if created:
            created_count += 1

    return created_count, skipped_tags


def create_place_from_report(report):
    if not report.suggested_name:
        raise ValueError("새 장소 제보 승인에는 장소명이 필요합니다.")
    if not report.suggested_category:
        raise ValueError("새 장소 제보 승인에는 카테고리가 필요합니다.")
    if report.suggested_lat is None or report.suggested_lng is None:
        raise ValueError("새 장소 제보 승인에는 좌표가 필요합니다.")

    place, created = Place.objects.update_or_create(
        source="user_report",
        external_id=f"place-report-{report.id}",
        defaults={
            "name": report.suggested_name,
            "category": report.suggested_category,
            "address": report.suggested_address,
            "lat": float(report.suggested_lat),
            "lng": float(report.suggested_lng),
            "source_name": "사용자 장소 제보",
            "detail_location": "",
            "data_quality_status": "candidate",
            "data_quality_score": 60,
            "raw": {
                "place_report_id": report.id,
                "report_type": report.report_type,
                "description": report.description,
            },
        },
    )

    return place, created


def update_place_from_report(report):
    if not report.place:
        raise ValueError("장소 수정 제보 승인에는 연결된 장소가 필요합니다.")

    place = report.place
    update_fields = []
    field_map = [
        ("suggested_name", "name"),
        ("suggested_category", "category"),
        ("suggested_address", "address"),
        ("suggested_lat", "lat"),
        ("suggested_lng", "lng"),
    ]

    for report_field, place_field in field_map:
        value = getattr(report, report_field)
        if value in (None, ""):
            continue
        if place_field in {"lat", "lng"}:
            value = float(value)
        setattr(place, place_field, value)
        update_fields.append(place_field)

    if update_fields:
        place.data_quality_status = "candidate"
        place.raw = {
            **(place.raw or {}),
            "last_edit_report_id": report.id,
            "last_edit_report_description": report.description,
        }
        update_fields.extend(["data_quality_status", "raw", "updated_at"])
        place.save(update_fields=list(dict.fromkeys(update_fields)))

    return place, bool(update_fields)


def apply_place_report_approval(report):
    if report.report_type == "new_place":
        place, created = create_place_from_report(report)
        report.place = place
        created_tag_count, skipped_tags = attach_report_tags_to_place(
            report,
            place,
            create_missing_tags=True,
        )
        return {
            "created_places": 1 if created else 0,
            "updated_places": 0 if created else 1,
            "created_place_tags": created_tag_count,
            "skipped_tags": skipped_tags,
        }

    if report.report_type == "edit_place":
        place, updated = update_place_from_report(report)
        created_tag_count, skipped_tags = attach_report_tags_to_place(report, place)
        return {
            "created_places": 0,
            "updated_places": 1 if updated else 0,
            "created_place_tags": created_tag_count,
            "skipped_tags": skipped_tags,
        }

    if report.report_type != "tag_suggestion" or not report.place or not report.suggested_tags:
        return {
            "created_places": 0,
            "updated_places": 0,
            "created_place_tags": 0,
            "skipped_tags": [],
        }

    created_count, skipped_tags = attach_report_tags_to_place(report, report.place)

    return {
        "created_places": 0,
        "updated_places": 0,
        "created_place_tags": created_count,
        "skipped_tags": skipped_tags,
    }


def review_place_report(request, report_id, review_status):
    report = get_object_or_404(PlaceReport, id=report_id)
    serializer = PlaceReportAdminReviewSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        approval_result = {}
        previous_tier = get_current_user_tier(report.user)
        if review_status == "approved":
            try:
                approval_result = apply_place_report_approval(report)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        report.status = review_status
        report.admin_note = serializer.validated_data.get("admin_note", "")
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.save(
            update_fields=[
                "status",
                "admin_note",
                "reviewed_by",
                "reviewed_at",
                "place",
                "updated_at",
            ],
        )
        if review_status == "approved":
            notify_tier_upgrade_if_needed(report.user, previous_tier)

    detail_serializer = PlaceReportDetailSerializer(report, context={"request": request})
    return Response({
        "message": f"place report {review_status}",
        "report": detail_serializer.data,
        **approval_result,
    })


@api_view(["POST"])
@permission_classes([IsAdminUser])
def admin_place_report_approve(request, report_id):
    return review_place_report(request, report_id, "approved")


@api_view(["POST"])
@permission_classes([IsAdminUser])
def admin_place_report_reject(request, report_id):
    return review_place_report(request, report_id, "rejected")


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
        "category_label": get_category_display_name(place.category),
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


def parse_optional_float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_limited_int(value, *, default=30, minimum=1, maximum=100):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def build_place_keyword_filter(keyword):
    matched_categories = get_matching_categories(keyword)
    return (
        Q(name__icontains=keyword)
        | Q(address__icontains=keyword)
        | Q(detail_location__icontains=keyword)
        | Q(category__icontains=keyword)
        | Q(source__icontains=keyword)
        | Q(source_name__icontains=keyword)
        | Q(external_id__icontains=keyword)
        | Q(place_tags__tag__name__icontains=keyword)
        | Q(category__in=matched_categories)
    )


def search_saved_map_places(*, keyword="", lat=None, lng=None, radius=0, limit=30):
    places = Place.objects.all().order_by("-updated_at", "-id")

    if keyword:
        places = places.filter(build_place_keyword_filter(keyword)).distinct()

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
        limited_place_ids = nearby_place_ids[:limit]
        places_by_id = {
            place.id: place
            for place in (
                Place.objects
                .filter(id__in=limited_place_ids)
                .prefetch_related("place_tags__tag")
            )
        }

        return [
            serialize_place(
                places_by_id[place_id],
                distance=distance_by_place_id[place_id],
            )
            for place_id in limited_place_ids
            if place_id in places_by_id
        ], len(nearby_place_ids)

    total_count = places.count()
    return [
        serialize_place(place)
        for place in places.prefetch_related("place_tags__tag")[:limit]
    ], total_count


def serialize_kakao_map_place(place, *, lat=None, lng=None):
    place_lat = parse_optional_float(place.get("y"))
    place_lng = parse_optional_float(place.get("x"))
    distance = None
    if place.get("distance") not in (None, ""):
        distance = parse_optional_float(place.get("distance"))
    elif lat is not None and lng is not None and place_lat is not None and place_lng is not None:
        distance = calculate_distance_m(lat, lng, place_lat, place_lng)

    return {
        "id": place.get("id"),
        "name": place.get("place_name", ""),
        "category": place.get("category_name", ""),
        "category_label": place.get("category_name", ""),
        "address": place.get("road_address_name") or place.get("address_name", ""),
        "detail_location": "",
        "lat": place_lat,
        "lng": place_lng,
        "source": "kakao",
        "external_id": place.get("id", ""),
        "source_name": "카카오 지도",
        "kakao_place_url": place.get("place_url", ""),
        "place_url": place.get("place_url", ""),
        "phone": place.get("phone", ""),
        "distance": distance,
        "tags": [],
        "raw": place,
    }


@api_view(["GET"])
def map_place_search(request):
    keyword = request.GET.get("q", "").strip()
    source = request.GET.get("source", "all").strip() or "all"
    lat = parse_optional_float(request.GET.get("lat"))
    lng = parse_optional_float(request.GET.get("lng"))
    radius = parse_limited_int(request.GET.get("radius"), default=0, minimum=0, maximum=20000)
    limit = parse_limited_int(request.GET.get("limit"), default=30, minimum=1, maximum=100)

    db_results = []
    db_total_count = 0
    kakao_results = []
    kakao_error = ""

    if source in {"all", "db"}:
        db_results, db_total_count = search_saved_map_places(
            keyword=keyword,
            lat=lat,
            lng=lng,
            radius=radius,
            limit=limit,
        )

    if keyword and source in {"all", "kakao"}:
        try:
            kakao_data = search_places_by_keyword(
                keyword=keyword,
                lat=lat,
                lng=lng,
                radius=radius or None,
                size=min(limit, 15),
            )
            db_external_ids = {
                str(place.get("external_id"))
                for place in db_results
                if place.get("source") == "kakao_local" and place.get("external_id")
            }
            kakao_results = [
                serialize_kakao_map_place(place, lat=lat, lng=lng)
                for place in kakao_data.get("documents", [])
                if str(place.get("id")) not in db_external_ids
            ]
        except Exception as exc:
            logger.info("Kakao map search failed.", exc_info=True)
            kakao_error = str(exc)

    combined_results = [
        *[
            {
                **place,
                "result_source": "db",
                "source_label": "저장 장소",
            }
            for place in db_results
        ],
        *[
            {
                **place,
                "result_source": "kakao",
                "source_label": "카카오 장소",
            }
            for place in kakao_results
        ],
    ]

    if lat is not None and lng is not None:
        combined_results.sort(key=lambda place: (
            place.get("distance") is None,
            place.get("distance") if place.get("distance") is not None else 999999999,
            0 if place.get("result_source") == "db" else 1,
            str(place.get("name", "")),
        ))

    return Response({
        "query": keyword,
        "count": len(combined_results),
        "candidate_counts": {
            "db": len(db_results),
            "kakao": len(kakao_results),
            "db_total": db_total_count,
        },
        "filters": {
            "q": keyword,
            "source": source,
            "lat": lat,
            "lng": lng,
            "radius": radius,
            "limit": limit,
        },
        "kakao_error": kakao_error,
        "results": combined_results,
    })


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

    user = request.user if request.user.is_authenticated else None
    data = search_db_recommendations(
        scenario=scenario,
        lat=lat,
        lng=lng,
        limit=limit,
        radius=radius,
        user=user,
    )

    return Response(data)


@api_view(["POST"])
def search_safety_check(request):
    query = request.data.get("query", "")
    parsed = parse_situation(query)
    blocked = parsed.get("blocked") or parsed.get("is_searchable") is False

    return Response({
        "blocked": bool(blocked),
        "is_searchable": not blocked,
        "reason": parsed.get("block_reason", "") if blocked else "",
        "message": parsed.get(
            "user_message",
            "요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.",
        ) if blocked else "",
        "ai_parse": parsed,
    })


@api_view(["POST"])
def conversational_search_plan(request):
    query = request.data.get("query", "")
    previous_context = (
        request.data.get("previous_search_context")
        or request.data.get("previous_context")
    )
    previous_search_plan = request.data.get("previous_search_plan")
    pending_clarification_frame = request.data.get("pending_clarification_frame")
    if isinstance(previous_search_plan, dict) or isinstance(pending_clarification_frame, dict):
        if not isinstance(previous_context, dict):
            previous_context = {}
        previous_context = {
            **previous_context,
            "search_plan": previous_search_plan or previous_context.get("search_plan") or {},
            "pending_clarification_frame": (
                pending_clarification_frame
                or previous_context.get("pending_clarification_frame")
                or {}
            ),
            "is_clarification_followup": bool(request.data.get("is_clarification_followup")),
            "clarification_answer": request.data.get("clarification_answer", ""),
            "previous_user_query": request.data.get("previous_user_query", ""),
            "original_query": request.data.get("original_query", ""),
            "last_resolved_location_context": request.data.get("last_resolved_location_context") or {},
        }

    user = request.user if request.user.is_authenticated else None
    data = build_conversational_search_plan(
        query=query,
        user=user,
        lat=request.data.get("lat"),
        lng=request.data.get("lng"),
        map_center=request.data.get("map_center"),
        previous_context=previous_context,
    )
    _sync_conversational_search_plan_response(data)
    return Response(data)


def _sync_conversational_search_plan_response(data):
    if not isinstance(data, dict):
        return data

    action = data.get("decision_action") or data.get("action") or ""
    if action:
        data["decision_action"] = action
        data["decisionAction"] = action
    if action == "ask_clarification":
        data["type"] = "clarification"
        data["can_search_now"] = False
        data["results"] = []
        data["markers"] = []
        data["clarification_options"] = _as_request_list(
            data.get("clarification_options") or data.get("clarificationOptions") or []
        )
    elif action in {"blocked", "out_of_scope"}:
        data["type"] = action
        data["can_search_now"] = False
        data["results"] = []
        data["markers"] = []
    elif action:
        data["type"] = "search" if action == "search" else action
        data["can_search_now"] = action == "search"

    search_plan = data.get("search_plan")
    if not isinstance(search_plan, dict):
        return data
    if action in {"blocked", "out_of_scope"} and not search_plan:
        return data

    search_plan["decision_action"] = action
    search_plan["decisionAction"] = action
    search_plan["can_search_now"] = action == "search"
    if action == "ask_clarification":
        search_plan["clarification_question"] = data.get("clarification_question", "")
        search_plan["clarification_options"] = data.get("clarification_options", [])

    ai_debug = data.get("ai_debug")
    if not isinstance(ai_debug, dict):
        ai_debug = {}

    frame = search_plan.get("place_intent_frame") or search_plan.get("placeIntentFrame")
    if not isinstance(frame, dict):
        frame = {}
    elif action:
        frame["decision_action"] = action
        frame["decisionAction"] = action
        frame["can_search_now"] = action == "search"
        frame["canSearchNow"] = action == "search"
        frame["normalized_user_intent"] = (
            frame.get("normalized_user_intent")
            or frame.get("normalizedUserIntent")
            or data.get("user_intent_summary")
            or frame.get("user_goal")
            or ""
        )
        frame["normalizedUserIntent"] = frame["normalized_user_intent"]
        if action == "ask_clarification":
            frame["clarification_question"] = (
                frame.get("clarification_question")
                or frame.get("clarificationQuestion")
                or data.get("clarification_question")
                or ""
            )
            frame["clarificationQuestion"] = frame["clarification_question"]
            frame["clarification_options"] = _as_request_list(
                frame.get("clarification_options")
                or frame.get("clarificationOptions")
                or data.get("clarification_options")
                or []
            )
            frame["clarificationOptions"] = frame["clarification_options"]
        search_plan["place_intent_frame"] = frame

    location_repair = ai_debug.get("location_repair")
    if isinstance(location_repair, dict):
        repair_anchor = (
            location_repair.get("frame_anchor_location")
            or location_repair.get("explicit_anchor_location")
            or ""
        )
        repair_location_mode = (
            location_repair.get("frame_location_mode")
            or location_repair.get("checked_location_mode")
            or ""
        )
        repair_status = location_repair.get("status") or ""
        frame_anchor = frame.get("anchor_location") or frame.get("anchorLocation") or ""
        if (
            repair_anchor
            and (repair_location_mode == "explicit" or repair_status == "repaired")
            and not frame_anchor
        ):
            frame["anchor_location"] = repair_anchor
            frame["anchorLocation"] = repair_anchor
            frame["location_mode"] = "explicit"
            frame["locationMode"] = "explicit"
            search_plan["place_intent_frame"] = frame

    synced_anchor = sync_frame_location_to_search_plan(search_plan)
    if synced_anchor:
        data["location"] = {
            "text": synced_anchor,
            "is_explicit": True,
            "fallback": "",
        }
        execution_policy = data.get("execution_policy")
        if not isinstance(execution_policy, dict):
            execution_policy = {}
        execution_policy["preserve_explicit_location"] = True
        data["execution_policy"] = execution_policy

    final_frame = search_plan.get("place_intent_frame") or search_plan.get("placeIntentFrame") or {}
    if not isinstance(final_frame, dict):
        final_frame = {}
    ai_debug["final_search_plan"] = {
        "final_search_plan_anchor_location": (
            search_plan.get("anchorLocation")
            or search_plan.get("anchor_location")
            or ""
        ),
        "final_search_plan_locationQuery": (
            search_plan.get("locationQuery")
            or search_plan.get("location_query")
            or ""
        ),
        "final_frame_anchor_location": (
            final_frame.get("anchor_location")
            or final_frame.get("anchorLocation")
            or ""
        ),
        "final_frame_location_mode": (
            final_frame.get("location_mode")
            or final_frame.get("locationMode")
            or ""
        ),
    }
    data["ai_debug"] = ai_debug
    data["search_plan"] = search_plan
    return data


def _as_request_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return [value]


def _get_request_search_plan(data):
    search_plan = data.get("search_plan") or data.get("searchPlan") or {}
    return search_plan if isinstance(search_plan, dict) else {}


def _get_request_place_intent_frame(data, search_plan):
    frame = (
        data.get("place_intent_frame")
        or data.get("placeIntentFrame")
        or search_plan.get("place_intent_frame")
        or search_plan.get("placeIntentFrame")
        or {}
    )
    return frame if isinstance(frame, dict) else {}


def _is_valid_request_frame(frame):
    location_mode = str(frame.get("location_mode") or frame.get("locationMode") or "").strip()
    if location_mode not in {"explicit", "current_context", "clarification_required"}:
        return False
    if location_mode == "explicit" and not str(frame.get("anchor_location") or frame.get("anchorLocation") or "").strip():
        return False
    return bool(
        str(frame.get("user_goal") or frame.get("userGoal") or "").strip()
        and str(frame.get("display_label") or frame.get("displayLabel") or "").strip()
        and (
            _as_request_list(frame.get("candidate_place_types") or frame.get("candidatePlaceTypes"))
            or _as_request_list(frame.get("search_queries") or frame.get("searchQueries"))
        )
    )


def _get_request_decision_action(data, search_plan, frame):
    action = (
        data.get("decision_action")
        or data.get("decisionAction")
        or search_plan.get("decision_action")
        or search_plan.get("decisionAction")
        or frame.get("decision_action")
        or frame.get("decisionAction")
        or ""
    )
    return str(action or "").strip()


def _get_request_previous_context(data):
    context = (
        data.get("previousContext")
        or data.get("previous_context")
        or data.get("previous_search_context")
        or {}
    )
    return context if isinstance(context, dict) else {}


def _get_request_map_center(data):
    map_center = data.get("mapCenter") or data.get("map_center") or {}
    return map_center if isinstance(map_center, dict) else None


def _sync_decision_to_plan(search_plan, frame, action, reason="", message=""):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    frame = frame if isinstance(frame, dict) else {}
    search_plan.update({
        "decision_action": action,
        "decisionAction": action,
        "can_search_now": False,
        "canSearchNow": False,
        "execution_mode": search_plan.get("execution_mode") or "decision_gate",
        "plan_source": search_plan.get("plan_source") or search_plan.get("planSource") or "ai_search_gate",
    })
    if reason:
        search_plan["blocked_reason" if action == "blocked" else "out_of_scope_reason"] = reason
    if message:
        search_plan["message"] = message
    if frame:
        frame.update({
            "decision_action": action,
            "decisionAction": action,
            "can_search_now": False,
            "canSearchNow": False,
        })
        if reason:
            frame["blocked_reason" if action == "blocked" else "out_of_scope_reason"] = reason
    return search_plan, frame


def _is_safety_out_of_scope(safety_parse):
    scenario = str(safety_parse.get("scenario") or "").strip()
    reason = str(safety_parse.get("block_reason") or safety_parse.get("reason") or "").strip()
    return scenario == "out_of_scope" or reason in {
        "not_place_recommendation",
        "out_of_scope",
    }


def _decision_response_from_safety_parse(safety_parse, search_plan, frame):
    action = "out_of_scope" if _is_safety_out_of_scope(safety_parse) else "blocked"
    reason = safety_parse.get("block_reason") or safety_parse.get("reason") or action
    message = safety_parse.get("user_message") or safety_parse.get("message") or (
        "생활 장소 추천 범위 밖의 요청입니다."
        if action == "out_of_scope"
        else "요청하신 목적은 장소 추천으로 도와드리기 어렵습니다."
    )
    search_plan, frame = _sync_decision_to_plan(
        search_plan,
        frame,
        action,
        reason=reason,
        message=message,
    )
    response = _empty_decision_gate_response(
        action,
        search_plan,
        frame,
        ai_debug={
            "safety_parse": safety_parse,
            "ai_search_execution_gate": {
                "status": f"blocked_by_{action}",
                "reason": reason,
            },
        },
    )
    response.data["reason"] = reason
    response.data["message"] = message
    response.data["ai_parse"] = {
        **safety_parse,
        "decision_action": action,
        "decisionAction": action,
        "can_search_now": False,
    }
    return response


def _ai_unavailable_response(search_plan, frame, reason="ai_call_failed"):
    message = "AI가 장소 의도를 안전하게 확인하지 못해 검색을 실행하지 않았습니다. 지역과 목적을 조금 더 구체적으로 입력해 주세요."
    search_plan, frame = _sync_decision_to_plan(
        search_plan,
        frame,
        "ai_unavailable",
        reason=reason,
        message=message,
    )
    return _empty_decision_gate_response(
        "ai_unavailable",
        search_plan,
        frame,
        ai_debug={
            "debug_pipeline": _build_debug_pipeline(
                search_plan,
                frame,
                query_generation=_query_generation_from_frame(search_plan, frame),
                has_actionable_place_target=False,
                ai_call_failed=True,
                ai_fallback_reason=reason,
            ),
            "ai_search_execution_gate": {
                "status": "blocked_by_ai_unavailable",
                "reason": reason,
            },
        },
    )


AI_SEARCH_BROAD_PLACE_TERMS = {
    "장소",
    "추천장소",
    "추천 장소",
    "공간",
    "곳",
    "갈만한곳",
    "갈만한 곳",
    "어디갈만한데",
    "어디 갈만한 데",
    "어디",
    "근처",
    "주변",
    "찾기",
    "추천",
    "place",
    "places",
    "search",
}


def _is_broad_place_term(term):
    compact = _compact_external_text(term)
    if not compact:
        return True
    return compact in {_compact_external_text(item) for item in AI_SEARCH_BROAD_PLACE_TERMS}


def _frame_non_broad_terms(frame, *field_names):
    return [
        term
        for term in _external_frame_terms(frame, *field_names)
        if not _is_broad_place_term(term)
    ]


def _has_place_seeking_frame_evidence(frame):
    if not isinstance(frame, dict) or not frame:
        return False

    target_terms = _frame_non_broad_terms(
        frame,
        "target_objects",
        "targetObjects",
        "result_match_terms",
        "resultMatchTerms",
    )
    evidence_terms = [
        term
        for term in _external_frame_evidence_terms(frame)
        if not _is_broad_place_term(term)
    ]
    candidate_terms = _frame_non_broad_terms(
        frame,
        "candidate_place_types",
        "candidatePlaceTypes",
        "search_queries",
        "searchQueries",
        "candidate_category_codes",
        "candidateCategoryCodes",
    )
    display_terms = [
        term
        for term in [
            frame.get("display_label"),
            frame.get("displayLabel"),
            frame.get("user_goal"),
            frame.get("userGoal"),
        ]
        if not _is_broad_place_term(term)
    ]
    direct_terms = [*target_terms, *evidence_terms]
    if not candidate_terms:
        return False

    if direct_terms:
        compact_candidates = [_compact_external_text(term) for term in candidate_terms]
        for direct_term in direct_terms:
            compact_direct = _compact_external_text(direct_term)
            if not compact_direct:
                continue
            if any(
                compact_direct in candidate
                or candidate in compact_direct
                for candidate in compact_candidates
                if candidate
            ):
                return True
        return False

    return bool(display_terms and candidate_terms)


def _has_actionable_place_target(search_plan, frame):
    if not isinstance(frame, dict) or not frame:
        return False

    partitions = _frame_evidence_partitions(search_plan, frame)
    trusted_by_field = partitions["trusted_by_field"]
    direct_terms = [
        *trusted_by_field.get("target_objects", []),
        *trusted_by_field.get("targetObjects", []),
        *trusted_by_field.get("result_match_terms", []),
        *trusted_by_field.get("resultMatchTerms", []),
        *[item.get("value") for item in partitions.get("trusted_evidence", []) if isinstance(item, dict)],
    ]
    direct_terms = [
        term for term in direct_terms
        if term and not _is_broad_place_term(term)
    ]
    candidate_terms = [
        *trusted_by_field.get("candidate_place_types", []),
        *trusted_by_field.get("candidatePlaceTypes", []),
        *trusted_by_field.get("candidate_category_codes", []),
        *trusted_by_field.get("candidateCategoryCodes", []),
    ]
    candidate_terms = [
        term for term in candidate_terms
        if term and not _is_broad_place_term(term)
    ]
    search_terms = [
        *trusted_by_field.get("search_queries", []),
        *trusted_by_field.get("searchQueries", []),
    ]
    search_terms = [
        term for term in search_terms
        if term and not _is_broad_place_term(term)
    ]
    display_terms = [
        term
        for term in [
            frame.get("display_label"),
            frame.get("displayLabel"),
            frame.get("user_goal"),
            frame.get("userGoal"),
        ]
        if term and not _is_broad_place_term(term)
    ]

    if direct_terms and (candidate_terms or search_terms):
        compact_candidates = [
            _compact_external_text(term)
            for term in [*candidate_terms, *search_terms]
            if _compact_external_text(term)
        ]
        return any(
            compact_direct
            and any(
                compact_direct in compact_candidate
                or compact_candidate in compact_direct
                for compact_candidate in compact_candidates
            )
            for compact_direct in (_compact_external_text(term) for term in direct_terms)
        )
    if candidate_terms and search_terms and display_terms:
        return True
    return False


def _is_ai_failure_fallback(search_plan):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    fallback_reason = _clean_external_text(
        search_plan.get("ai_fallback_reason")
        or search_plan.get("aiFallbackReason")
    )
    plan_source = _clean_external_text(
        search_plan.get("plan_source")
        or search_plan.get("planSource")
    )
    execution_mode = _clean_external_text(
        search_plan.get("execution_mode")
        or search_plan.get("executionMode")
    )
    if plan_source == "clarification_follow_up" or "clarification" in execution_mode:
        return fallback_reason.startswith("ai_call_failed")
    return (
        bool(search_plan.get("parser_fallback") or search_plan.get("parserFallback"))
        or plan_source == "legacy_fallback"
        or fallback_reason.startswith("ai_call_failed")
    )


def _ai_search_execution_plan_rejection_reason(search_plan):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    plan_source = _clean_external_text(
        search_plan.get("plan_source")
        or search_plan.get("planSource")
    )
    execution_mode = _clean_external_text(
        search_plan.get("execution_mode")
        or search_plan.get("executionMode")
    )
    parser_provider = _clean_external_text(
        search_plan.get("parser_provider")
        or search_plan.get("parserProvider")
    )
    parser_fallback = bool(search_plan.get("parser_fallback") or search_plan.get("parserFallback"))
    fallback_reason = _clean_external_text(
        search_plan.get("ai_fallback_reason")
        or search_plan.get("aiFallbackReason")
    )

    if plan_source == "clarification_follow_up" or "clarification" in execution_mode:
        return ""
    if fallback_reason.startswith("ai_call_failed"):
        return "ai_call_failed"
    if plan_source == "legacy_fallback":
        return "legacy_fallback"
    if parser_fallback:
        return "parser_fallback"
    if parser_provider in {"frontend", "rule"} and plan_source != "ai":
        return f"untrusted_parser_provider:{parser_provider}"
    return ""


def _debug_blocked_terms(search_plan, frame):
    partitions = _frame_evidence_partitions(search_plan, frame)
    return [
        {
            "value": item.get("value"),
            "source": item.get("source"),
            "field": item.get("field"),
        }
        for item in partitions.get("blocked_terms", [])
    ]


def _debug_evidence_terms_by_source(search_plan, frame):
    partitions = _frame_evidence_partitions(search_plan, frame)
    grouped = {
        "trusted": partitions.get("trusted_terms", []),
        "fallback_placeholder": [],
        "legacy_inferred": [],
        "raw_query_repeat": [],
        "broad_default": [],
    }
    for item in partitions.get("blocked_terms", []):
        source = item.get("source")
        if source in grouped:
            grouped[source].append(item.get("value"))
    return {
        key: _dedupe_texts(values)
        for key, values in grouped.items()
    }


def _top_result_evidence_debug(results):
    debug_items = []
    for result in (results or [])[:15]:
        if not isinstance(result, dict):
            continue
        debug_items.append({
            "id": result.get("id"),
            "name": result.get("name"),
            "source_type": result.get("source_type"),
            "frame_evidence_tier": _candidate_evidence_tier(result),
            "frame_match_strength": result.get("frame_match_strength"),
            "matched_evidence": result.get("matched_evidence") or [],
            "compatibility_gate": result.get("compatibility_gate"),
        })
    return debug_items


def _build_debug_pipeline(
    search_plan,
    frame,
    *,
    query_generation=None,
    candidate_counts=None,
    top_results=None,
    hidden_weak_candidates=None,
    has_actionable_place_target=None,
    ai_call_failed=None,
    ai_fallback_reason=None,
):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    frame = frame if isinstance(frame, dict) else {}
    if has_actionable_place_target is None:
        has_actionable_place_target = _has_actionable_place_target(search_plan, frame)
    if ai_call_failed is None:
        ai_call_failed = _is_ai_failure_fallback(search_plan)
    if ai_fallback_reason is None:
        ai_fallback_reason = (
            search_plan.get("ai_fallback_reason")
            or search_plan.get("aiFallbackReason")
            or ""
        )
    rejection_reason = _ai_search_execution_plan_rejection_reason(search_plan)
    fallback_used = bool(rejection_reason)
    ai_retry_count = search_plan.get("ai_retry_count") or search_plan.get("aiRetryCount") or 0
    try:
        ai_retry_count = int(ai_retry_count)
    except (TypeError, ValueError):
        ai_retry_count = 0
    candidate_counts = candidate_counts if isinstance(candidate_counts, dict) else {}
    top_results = top_results if isinstance(top_results, list) else []
    hidden_weak_candidates = hidden_weak_candidates if isinstance(hidden_weak_candidates, list) else []
    return {
        "used_path": "unified_candidate_pipeline",
        "legacy_path_used": False,
        "ai_call_failed": bool(ai_call_failed),
        "ai_retry_count": ai_retry_count,
        "ai_fallback_reason": ai_fallback_reason or "",
        "fallback_used": fallback_used,
        "fallback_reason": rejection_reason,
        "fallback_created_candidates": False,
        "plan_source": search_plan.get("plan_source") or search_plan.get("planSource") or "",
        "parser_fallback": bool(search_plan.get("parser_fallback") or search_plan.get("parserFallback")),
        "has_actionable_place_target": bool(has_actionable_place_target),
        "evidence_terms": _debug_evidence_terms_by_source(search_plan, frame),
        "blocked_terms": _debug_blocked_terms(search_plan, frame),
        "query_generation": query_generation or {
            "primary_queries": [],
            "blocked_queries": [],
            "fallback_queries": [],
        },
        "candidate_counts": {
            "db": int(candidate_counts.get("db") or 0),
            "kakao": int(candidate_counts.get("kakao") or 0),
            "web": int(candidate_counts.get("web") or 0),
            "top_results": int(candidate_counts.get("top_results") or len(top_results)),
            "hidden_weak": int(candidate_counts.get("hidden_weak") or len(hidden_weak_candidates)),
            "removed_incompatible": int(candidate_counts.get("removed_incompatible") or len(hidden_weak_candidates)),
        },
        "top_result_evidence": _top_result_evidence_debug(top_results),
    }


def _is_generic_clarification_text(value):
    compact = _compact_external_text(value)
    if not compact:
        return True
    generic_patterns = {
        _compact_external_text(BROAD_FRAME_CLARIFICATION_MESSAGE),
        _compact_external_text("어떤 장소를 원하시나요?"),
        _compact_external_text("좀 더 자세히 알려주세요."),
        _compact_external_text("어떤 목적의 장소를 찾으시나요?"),
    }
    return compact in generic_patterns


def _contextual_clarification_question(query, frame):
    frame = frame if isinstance(frame, dict) else {}
    existing = _clean_external_text(
        frame.get("clarification_question")
        or frame.get("clarificationQuestion")
    )
    if existing and not _is_generic_clarification_text(existing):
        return existing

    intent_text = _clean_external_text(
        frame.get("normalized_user_intent")
        or frame.get("normalizedUserIntent")
        or frame.get("user_goal")
        or frame.get("userGoal")
        or frame.get("display_label")
        or frame.get("displayLabel")
        or query
    )
    if intent_text:
        return f'"{intent_text}" 상황에서 어떤 장소를 찾아야 할지 아직 확정하기 어렵습니다. 찾고 싶은 장소 방향을 조금 더 구체적으로 알려주세요.'
    return "현재 문장만으로는 검색할 장소 방향을 확정하기 어렵습니다. 찾고 싶은 장소 방향을 조금 더 구체적으로 알려주세요."


def _contextual_clarification_options(frame):
    frame = frame if isinstance(frame, dict) else {}
    options = _as_request_list(
        frame.get("clarification_options")
        or frame.get("clarificationOptions")
        or []
    )
    broad_options = {_compact_external_text(option) for option in BROAD_FRAME_CLARIFICATION_OPTIONS}
    return [
        option
        for option in options
        if _compact_external_text(option) and _compact_external_text(option) not in broad_options
    ]


def _request_frame_post_validation_response(query, search_plan, frame):
    if not isinstance(frame, dict) or not frame:
        return None

    reasons = get_ai_frame_post_validation_reasons(frame, query)
    if not reasons:
        return None

    question = _contextual_clarification_question(query, frame)
    options = _contextual_clarification_options(frame)
    frame.update({
        "decision_action": "ask_clarification",
        "decisionAction": "ask_clarification",
        "can_search_now": False,
        "canSearchNow": False,
        "location_mode": "clarification_required"
        if not str(frame.get("anchor_location") or frame.get("anchorLocation") or "").strip()
        else (frame.get("location_mode") or frame.get("locationMode") or "current_context"),
        "clarification_question": question,
        "clarificationQuestion": question,
        "clarification_options": options,
        "clarificationOptions": options,
    })
    frame["locationMode"] = frame["location_mode"]
    search_plan.update({
        "decision_action": "ask_clarification",
        "decisionAction": "ask_clarification",
        "can_search_now": False,
        "clarification_question": question,
        "clarification_options": options,
        "place_intent_frame": frame,
        "placeIntentFrame": frame,
        "execution_mode": search_plan.get("execution_mode") or "decision_gate",
        "plan_source": search_plan.get("plan_source") or search_plan.get("planSource") or "ai",
    })
    return _empty_decision_gate_response(
        "ask_clarification",
        search_plan,
        frame,
        ai_debug={
            "post_validation": {
                "status": "forced_clarification",
                "reasons": reasons,
            },
        },
    )


def _empty_decision_gate_response(action, search_plan, frame, ai_debug=None):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    frame = frame if isinstance(frame, dict) else {}
    ai_debug = ai_debug or {}
    response_type = "clarification" if action == "ask_clarification" else action
    question = (
        search_plan.get("clarification_question")
        or frame.get("clarification_question")
        or frame.get("clarificationQuestion")
        or ""
    )
    options = _as_request_list(
        search_plan.get("clarification_options")
        or frame.get("clarification_options")
        or frame.get("clarificationOptions")
        or []
    )
    if action == "ask_clarification":
        question = question if not _is_generic_clarification_text(question) else ""
        question = question or _contextual_clarification_question(
            search_plan.get("originalQuery") or search_plan.get("original_query") or "",
            frame,
        )
        options = _contextual_clarification_options(frame) or [
            option
            for option in options
            if _compact_external_text(option)
            and _compact_external_text(option)
            not in {_compact_external_text(item) for item in BROAD_FRAME_CLARIFICATION_OPTIONS}
        ]
    debug_pipeline = ai_debug.get("debug_pipeline") or _build_debug_pipeline(
        search_plan,
        frame,
        has_actionable_place_target=False,
    )
    message = (
        search_plan.get("message")
        or frame.get("message")
        or frame.get("user_message")
        or ""
    )
    return Response({
        "scenario": action,
        "type": response_type,
        "decision_action": action,
        "decisionAction": action,
        "blocked": action == "blocked",
        "can_search_now": False,
        "results": [],
        "markers": [],
        "count": 0,
        "result_count": 0,
        "relevant_result_count": 0,
        "unified_candidate_pipeline": True,
        "frontend_should_preserve_order": True,
        "frontend_should_skip_kakao_fallback": True,
        "execution_policy": {
            "run_search": False,
            "preserve_explicit_location": False,
            "allow_kakao_fallback": False,
            "allow_ai_web_search_auto": False,
            "merge_ai_web_results": False,
        },
        "clarification_question": question,
        "clarification_options": options,
        "message": message,
        "ai_parse": {
            "scenario": action,
            "is_searchable": False,
            "decision_action": action,
            "can_search_now": False,
            "parser_provider": search_plan.get("parser_provider") or "frame",
            "parser_fallback": search_plan.get("parser_fallback") if "parser_fallback" in search_plan else False,
            "execution_mode": search_plan.get("execution_mode") or "decision_gate",
            "plan_source": search_plan.get("plan_source") or "ai",
            "search_plan": search_plan,
            "place_intent_frame": frame,
        },
        "execution_mode": search_plan.get("execution_mode") or "decision_gate",
        "plan_source": search_plan.get("plan_source") or "ai",
        "place_intent_frame": frame,
        "debug_pipeline": debug_pipeline,
        "ai_debug": ai_debug,
        "ai_web_search": get_ai_web_search_status(),
    })


EXTERNAL_SEARCH_STRONG_MEDIUM_MIN_RESULTS = 3
EXTERNAL_SEARCH_MAX_KAKAO_QUERIES = 3
EXTERNAL_SEARCH_KAKAO_SIZE = 5
EXTERNAL_SEARCH_KAKAO_RADIUS = 5000
EXTERNAL_SEARCH_MAX_MERGED_CANDIDATES = 8
EXTERNAL_SEARCH_MAX_WEB_QUERIES = 1

UNIFIED_EVIDENCE_TIER_RANKS = {
    "target_direct": 0,
    "result_direct": 1,
    "verified_direct": 2,
    "suggested_direct": 3,
    "candidate_direct": 4,
    "category_only": 5,
    "none": 9,
}


def _clean_external_text(value):
    return str(value or "").strip()


def _compact_external_text(value):
    return _clean_external_text(value).lower().replace(" ", "")


TRUSTED_AI_SEARCH_EVIDENCE_SOURCES = {
    "user_explicit",
    "ai_extracted",
    "clarification_patch",
    "verified_db_evidence",
    "external_evidence",
}

BLOCKED_AI_SEARCH_EVIDENCE_SOURCES = {
    "fallback_placeholder",
    "legacy_inferred",
    "raw_query_repeat",
    "broad_default",
}

BROAD_DEFAULT_AI_SEARCH_TERMS = {
    "카페",
    "쉼터",
    "cafe",
    "shelter",
    "restaurant",
    "식당",
    "음식점",
    "장소",
    "추천장소",
    "추천 장소",
    "갈만한곳",
    "갈만한 곳",
    "쉴곳",
    "쉴 곳",
}

AI_SEARCH_FRAME_EVIDENCE_FIELDS = {
    "target_objects",
    "targetObjects",
    "result_match_terms",
    "resultMatchTerms",
    "candidate_place_types",
    "candidatePlaceTypes",
    "candidate_category_codes",
    "candidateCategoryCodes",
    "search_queries",
    "searchQueries",
    "constraints",
    "preferred_place_natures",
    "preferredPlaceNatures",
}


def _term_value_from_item(item):
    if isinstance(item, dict):
        for key in ("value", "text", "term", "label", "query", "name"):
            value = _clean_external_text(item.get(key))
            if value:
                return value
        return ""
    return _clean_external_text(item)


def _request_list(value):
    return [
        _term_value_from_item(item)
        for item in _as_request_list(value)
        if _term_value_from_item(item)
    ]


def _external_frame_terms(frame, *field_names):
    terms = []
    for field_name in field_names:
        terms.extend(_request_list(frame.get(field_name)))
    return list(dict.fromkeys(terms))


def _frame_default_evidence_source(search_plan):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    plan_source = _clean_external_text(
        search_plan.get("plan_source")
        or search_plan.get("planSource")
    )
    execution_mode = _clean_external_text(
        search_plan.get("execution_mode")
        or search_plan.get("executionMode")
    )
    parser_fallback = bool(search_plan.get("parser_fallback") or search_plan.get("parserFallback"))

    if plan_source == "clarification_follow_up" or "clarification" in execution_mode:
        return "clarification_patch"
    if parser_fallback or plan_source == "legacy_fallback":
        return "legacy_inferred"
    return "ai_extracted"


def _is_broad_default_ai_search_term(value):
    compact = _compact_external_text(value)
    if not compact:
        return False
    return compact in {_compact_external_text(term) for term in BROAD_DEFAULT_AI_SEARCH_TERMS}


def _remove_anchor_from_query_value(value, search_plan, frame):
    text = _clean_external_text(value)
    anchor = _external_location_anchor(search_plan, frame)
    if not text or not anchor:
        return text
    compact_text = _compact_external_text(text)
    compact_anchor = _compact_external_text(anchor)
    if compact_anchor and compact_text.startswith(compact_anchor):
        return text[len(anchor):].strip()
    return text


def _broad_default_support_terms(frame):
    terms = [
        *_request_list(frame.get("target_objects") or frame.get("targetObjects")),
        *_request_list(frame.get("constraints")),
        frame.get("display_label"),
        frame.get("displayLabel"),
    ]
    for evidence in _as_request_list(frame.get("evidence") or frame.get("evidences")):
        terms.append(_term_value_from_item(evidence))
    return _dedupe_texts(terms)


def _has_broad_default_support(value, search_plan, frame):
    compact = _compact_external_text(value)
    if not compact:
        return False
    original_query = _clean_external_text(
        search_plan.get("originalQuery")
        or search_plan.get("original_query")
        or frame.get("originalQuery")
        or frame.get("original_query")
    )
    if original_query and compact in _compact_external_text(original_query):
        return True
    for support_term in _broad_default_support_terms(frame):
        support_compact = _compact_external_text(support_term)
        if support_compact and (compact == support_compact or compact in support_compact):
            return True
    return False


def _normalize_entry_source(search_plan, frame, field_name, value, source):
    if not _is_trusted_ai_search_source(source):
        return source
    core_value = _remove_anchor_from_query_value(value, search_plan, frame)
    if (
        _is_broad_default_ai_search_term(core_value)
        and not _has_broad_default_support(core_value, search_plan, frame)
    ):
        return "broad_default"
    return source


def _source_from_frame_item(item, default_source):
    if isinstance(item, dict):
        for key in (
            "evidence_source",
            "evidenceSource",
            "source_provenance",
            "sourceProvenance",
            "provenance",
            "source",
        ):
            source = _clean_external_text(item.get(key))
            if source:
                return source
    return default_source


def _frame_source_entries(search_plan, frame, *field_names, default_source=None):
    frame = frame if isinstance(frame, dict) else {}
    default_source = default_source or _frame_default_evidence_source(search_plan)
    entries = []
    seen = set()
    for field_name in field_names:
        for item in _as_request_list(frame.get(field_name)):
            value = _term_value_from_item(item)
            if not value:
                continue
            source = _source_from_frame_item(item, default_source)
            source = _normalize_entry_source(search_plan, frame, field_name, value, source)
            key = (_compact_external_text(value), source, field_name)
            if key in seen:
                continue
            seen.add(key)
            entries.append({
                "value": value,
                "source": source,
                "field": field_name,
            })
    return entries


def _frame_evidence_source_entries(search_plan, frame):
    raw_evidence = frame.get("evidence") or frame.get("evidences") or []
    if not isinstance(raw_evidence, list):
        raw_evidence = [raw_evidence]

    default_source = _frame_default_evidence_source(search_plan)
    entries = []
    seen = set()
    for item in raw_evidence:
        value = _term_value_from_item(item)
        if not value:
            continue
        source = _source_from_frame_item(item, default_source)
        key = (_compact_external_text(value), source, "evidence")
        if key in seen:
            continue
        seen.add(key)
        entries.append({
            "value": value,
            "source": source,
            "field": "evidence",
            "raw": item if isinstance(item, dict) else {"value": value},
        })
    return entries


def _is_trusted_ai_search_source(source):
    return _clean_external_text(source) in TRUSTED_AI_SEARCH_EVIDENCE_SOURCES


def _is_blocked_ai_search_source(source):
    return _clean_external_text(source) in BLOCKED_AI_SEARCH_EVIDENCE_SOURCES


def _dedupe_texts(values):
    return list(dict.fromkeys(
        _clean_external_text(value)
        for value in values
        if _clean_external_text(value)
    ))


def _frame_evidence_partitions(search_plan, frame):
    trusted_by_field = {field_name: [] for field_name in AI_SEARCH_FRAME_EVIDENCE_FIELDS}
    blocked_terms = []
    blocked_queries = []
    trusted_terms = []

    for field_name in AI_SEARCH_FRAME_EVIDENCE_FIELDS:
        for entry in _frame_source_entries(search_plan, frame, field_name):
            value = entry["value"]
            if _is_trusted_ai_search_source(entry["source"]):
                trusted_by_field[field_name].append(value)
                trusted_terms.append(value)
            else:
                blocked_terms.append({
                    "value": value,
                    "source": entry["source"],
                    "field": field_name,
                })
                if field_name in {"search_queries", "searchQueries"}:
                    blocked_queries.append({
                        "query": value,
                        "source": entry["source"],
                        "field": field_name,
                    })

    trusted_evidence = []
    for entry in _frame_evidence_source_entries(search_plan, frame):
        if _is_trusted_ai_search_source(entry["source"]):
            raw = entry.get("raw") if isinstance(entry.get("raw"), dict) else {}
            trusted_evidence.append({
                **raw,
                "value": entry["value"],
                "evidence_source": entry["source"],
            })
            trusted_terms.append(entry["value"])
        else:
            blocked_terms.append({
                "value": entry["value"],
                "source": entry["source"],
                "field": "evidence",
            })

    return {
        "trusted_by_field": {
            field_name: _dedupe_texts(values)
            for field_name, values in trusted_by_field.items()
        },
        "trusted_evidence": trusted_evidence,
        "trusted_terms": _dedupe_texts(trusted_terms),
        "blocked_terms": blocked_terms,
        "blocked_queries": blocked_queries,
    }


def _sanitize_frame_for_ai_search(search_plan, frame):
    frame = frame.copy() if isinstance(frame, dict) else {}
    search_plan = search_plan.copy() if isinstance(search_plan, dict) else {}
    collector_category_codes = []
    if not _is_ai_failure_fallback(search_plan):
        collector_category_codes = _dedupe_texts([
            *_request_list(search_plan.get("collector_category_codes")),
            *_request_list(search_plan.get("collectorCategoryCodes")),
            *_request_list(frame.get("candidate_category_codes")),
            *_request_list(frame.get("candidateCategoryCodes")),
            *_request_list(search_plan.get("candidate_category_codes")),
            *_request_list(search_plan.get("candidateCategoryCodes")),
        ])
    partitions = _frame_evidence_partitions(search_plan, frame)
    trusted_by_field = partitions["trusted_by_field"]

    for field_name in AI_SEARCH_FRAME_EVIDENCE_FIELDS:
        if field_name in frame:
            frame[field_name] = trusted_by_field.get(field_name, [])

    if "evidence" in frame or "evidences" in frame:
        frame["evidence"] = partitions["trusted_evidence"]
        frame["evidences"] = partitions["trusted_evidence"]

    search_plan["place_intent_frame"] = frame
    search_plan["placeIntentFrame"] = frame
    search_plan["collector_category_codes"] = collector_category_codes
    search_plan["collectorCategoryCodes"] = collector_category_codes
    for field_name in (
        "target_objects",
        "candidate_category_codes",
        "candidate_place_types",
        "search_queries",
        "result_match_terms",
        "constraints",
        "ranking_policy",
    ):
        if field_name in frame:
            search_plan[field_name] = frame.get(field_name)

    return search_plan, frame, partitions


def _external_frame_evidence_terms(frame):
    raw_evidence = frame.get("evidence") or frame.get("evidences") or []
    if not isinstance(raw_evidence, list):
        raw_evidence = [raw_evidence]

    terms = []
    for item in raw_evidence:
        if isinstance(item, dict):
            terms.extend([
                item.get("value"),
                item.get("text"),
                item.get("term"),
                item.get("label"),
            ])
        else:
            terms.append(item)

    return _request_list(terms)


def _is_external_candidate(result):
    return bool(result.get("is_external")) or result.get("source_type") in {
        "kakao_candidate",
        "web_evidence_candidate",
        "web_reference",
    }


def _candidate_evidence_tier(result):
    explicit_tier = _clean_external_text(
        result.get("frame_evidence_tier")
        or result.get("frameEvidenceTier")
        or result.get("evidence_tier")
        or result.get("evidenceTier")
    )
    if explicit_tier in UNIFIED_EVIDENCE_TIER_RANKS:
        return explicit_tier

    matched_evidence = result.get("matched_evidence") or result.get("matchedEvidence") or []
    if not isinstance(matched_evidence, list):
        matched_evidence = []

    best_tier = "none"
    best_rank = UNIFIED_EVIDENCE_TIER_RANKS[best_tier]
    for item in matched_evidence:
        if not isinstance(item, dict):
            continue
        evidence_type = _clean_external_text(item.get("type"))
        source_strength = _clean_external_text(item.get("source_strength") or item.get("sourceStrength"))
        if source_strength == "verified":
            tier = "verified_direct"
        elif source_strength == "suggested":
            tier = "suggested_direct"
        elif source_strength == "candidate":
            tier = "candidate_direct"
        elif evidence_type in {"target_term", "target_place_text", "target_category_label"}:
            tier = "target_direct"
        elif evidence_type in {"result_term", "result_place_text", "result_category_label"}:
            tier = "result_direct"
        elif evidence_type in {"candidate_place_type", "candidate_tag", "candidate_place_text", "place_nature"}:
            tier = "candidate_direct"
        elif evidence_type in {"category_code", "category_label"}:
            tier = "category_only"
        else:
            tier = "none"

        rank = UNIFIED_EVIDENCE_TIER_RANKS.get(tier, UNIFIED_EVIDENCE_TIER_RANKS["none"])
        if rank < best_rank:
            best_tier = tier
            best_rank = rank
    return best_tier


def _candidate_evidence_rank(result):
    return UNIFIED_EVIDENCE_TIER_RANKS.get(
        _candidate_evidence_tier(result),
        UNIFIED_EVIDENCE_TIER_RANKS["none"],
    )


def _result_evidence_strength(result):
    strength = _clean_external_text(
        result.get("frame_match_strength")
        or result.get("frameMatchStrength")
    ).lower()
    if strength in {"strong", "medium", "weak"}:
        return strength

    tier = _candidate_evidence_tier(result)
    if tier in {"target_direct", "result_direct", "verified_direct"}:
        return "strong"
    if tier in {"suggested_direct", "candidate_direct"}:
        return "medium"

    source_type = _clean_external_text(result.get("source_type")).lower()
    confidence = _clean_external_text(result.get("confidence")).lower()
    try:
        fallback_level = int(result.get("fallback_level"))
    except (TypeError, ValueError):
        fallback_level = 0
    score_breakdown = result.get("score_breakdown")
    score_breakdown = score_breakdown if isinstance(score_breakdown, dict) else {}
    score_cap_reasons = score_breakdown.get("score_cap_reasons", [])
    score_cap_reasons = score_cap_reasons if isinstance(score_cap_reasons, list) else []
    if (
        source_type == "db_category_fallback"
        or fallback_level >= 3
        or "frame_weak_category_fallback" in score_cap_reasons
        or "category_fallback" in score_cap_reasons
    ):
        return "weak"
    if source_type == "db_verified":
        return "strong" if confidence == "high" else "medium"
    if source_type == "db_candidate":
        return "medium"
    return "weak"


def _result_sort_rank(result):
    return {"strong": 0, "medium": 2, "weak": 4}.get(
        _result_evidence_strength(result),
        4,
    )


def _result_source_tie_rank(result):
    return 1 if _is_external_candidate(result) else 0


def _has_enough_db_evidence(results):
    strong_medium_count = sum(
        1
        for result in results
        if not _is_external_candidate(result)
        and _result_evidence_strength(result) in {"strong", "medium"}
    )
    return strong_medium_count >= EXTERNAL_SEARCH_STRONG_MEDIUM_MIN_RESULTS


def _should_run_external_search(data, search_plan, frame):
    if not isinstance(data, dict):
        return False, "invalid_data"
    decision_action = (
        data.get("decision_action")
        or data.get("decisionAction")
        or search_plan.get("decision_action")
        or search_plan.get("decisionAction")
        or frame.get("decision_action")
        or frame.get("decisionAction")
        or "search"
    )
    execution_policy = data.get("execution_policy") if isinstance(data.get("execution_policy"), dict) else {}
    if decision_action in {"ask_clarification", "out_of_scope", "blocked"}:
        return False, f"decision_{decision_action}"
    if execution_policy.get("run_search") is False:
        return False, "run_search_false"

    target_terms = _external_frame_terms(frame, "target_objects", "targetObjects", "result_match_terms", "resultMatchTerms")
    candidate_terms = _external_frame_terms(frame, "candidate_place_types", "candidatePlaceTypes", "search_queries", "searchQueries")
    if not target_terms and not candidate_terms:
        return False, "missing_frame_terms"

    results = data.get("results") if isinstance(data.get("results"), list) else []
    if _has_enough_db_evidence(results):
        return False, "db_strong_medium_sufficient"

    if not results:
        return True, "db_empty"

    weak_count = sum(
        1
        for result in results
        if _result_evidence_strength(result) == "weak"
        or result.get("source_type") == "db_category_fallback"
    )
    if weak_count >= max(1, len(results) // 2):
        return True, "db_weak_majority"

    return True, "db_strong_medium_insufficient"


def _external_location_anchor(search_plan, frame):
    return _clean_external_text(
        frame.get("anchor_location")
        or frame.get("anchorLocation")
        or search_plan.get("locationQuery")
        or search_plan.get("location_query")
        or search_plan.get("baseLocationQuery")
        or search_plan.get("base_location_query")
    )


def _query_contains_any_term(query, terms):
    compact_query = _compact_external_text(query)
    return any(
        compact_term and compact_term in compact_query
        for compact_term in (_compact_external_text(term) for term in terms)
    )


def _append_query_candidate(target, query, source, field, direct_terms):
    query = " ".join(_clean_external_text(query).split())
    if not query:
        return
    compact = _compact_external_text(query)
    broad_terms = {
        "장소",
        "추천장소",
        "추천 장소",
        "공간",
        "갈만한곳",
        "갈만한 곳",
        "어디갈만한데",
        "어디 갈만한 데",
    }
    if compact in {_compact_external_text(term) for term in broad_terms}:
        target["blocked_queries"].append({
            "query": query,
            "source": source,
            "field": field,
            "reason": "broad_placeholder_query",
        })
        return
    if direct_terms and not _query_contains_any_term(query, direct_terms):
        target["fallback_queries"].append({
            "query": query,
            "source": source,
            "field": field,
            "reason": "query_without_direct_target_evidence",
        })
        return
    target["primary_queries"].append({
        "query": query,
        "source": source,
        "field": field,
    })


def _query_generation_from_frame(search_plan, frame, fallback_query=""):
    anchor = _external_location_anchor(search_plan, frame)
    partitions = _frame_evidence_partitions(search_plan, frame)
    direct_terms = [
        term
        for term in [
            *partitions["trusted_by_field"].get("target_objects", []),
            *partitions["trusted_by_field"].get("targetObjects", []),
            *partitions["trusted_by_field"].get("result_match_terms", []),
            *partitions["trusted_by_field"].get("resultMatchTerms", []),
            *[item.get("value") for item in partitions.get("trusted_evidence", []) if isinstance(item, dict)],
        ]
        if not _is_broad_place_term(term)
    ]
    target = {
        "primary_queries": [],
        "blocked_queries": list(partitions["blocked_queries"]),
        "fallback_queries": [],
    }

    ordered_entries = [
        *_frame_source_entries(search_plan, frame, "search_queries", "searchQueries"),
        *[
            {
                **entry,
                "value": f"{anchor} {entry['value']}".strip(),
                "field": f"anchored_{entry['field']}",
            }
            for entry in _frame_source_entries(search_plan, frame, "result_match_terms", "resultMatchTerms")
            if anchor
        ],
        *[
            {
                **entry,
                "value": f"{anchor} {entry['value']}".strip(),
                "field": f"anchored_{entry['field']}",
            }
            for entry in _frame_source_entries(search_plan, frame, "target_objects", "targetObjects")
            if anchor
        ],
        *[
            {
                **entry,
                "value": f"{anchor} {entry['value']}".strip(),
                "field": f"anchored_{entry['field']}",
            }
            for entry in _frame_source_entries(search_plan, frame, "candidate_place_types", "candidatePlaceTypes")
            if anchor and not direct_terms
        ],
        *_frame_source_entries(search_plan, frame, "result_match_terms", "resultMatchTerms"),
        *_frame_source_entries(search_plan, frame, "target_objects", "targetObjects"),
        *(
            _frame_source_entries(search_plan, frame, "candidate_place_types", "candidatePlaceTypes")
            if not direct_terms else []
        ),
    ]

    seen_entries = set()
    for entry in ordered_entries:
        value = entry["value"]
        compact = _compact_external_text(value)
        if not value or (anchor and compact == _compact_external_text(anchor)):
            continue
        entry_key = (compact, entry["source"], entry["field"])
        if entry_key in seen_entries:
            continue
        seen_entries.add(entry_key)
        if not _is_trusted_ai_search_source(entry["source"]):
            target["blocked_queries"].append({
                "query": value,
                "source": entry["source"],
                "field": entry["field"],
                "reason": "blocked_evidence_source",
            })
            continue
        _append_query_candidate(target, value, entry["source"], entry["field"], direct_terms)

    if fallback_query:
        target["blocked_queries"].append({
            "query": fallback_query,
            "source": "raw_query_repeat",
            "field": "fallback_query",
            "reason": "raw_query_repeat_not_allowed",
        })

    primary_queries = []
    seen_queries = set()
    for item in target["primary_queries"]:
        query = item["query"]
        compact = _compact_external_text(query)
        if compact in seen_queries or any(compact in seen_query for seen_query in seen_queries):
            continue
        seen_queries.add(compact)
        primary_queries.append(query)

    fallback_queries = []
    seen_fallback_queries = set()
    for item in target["fallback_queries"]:
        query = item["query"]
        compact = _compact_external_text(query)
        if compact in seen_queries or compact in seen_fallback_queries:
            continue
        seen_fallback_queries.add(compact)
        fallback_queries.append(query)

    blocked_queries = []
    seen_blocked_queries = set()
    for item in target["blocked_queries"]:
        query = item.get("query") or item.get("value")
        compact = _compact_external_text(query)
        key = (compact, item.get("source"), item.get("field"), item.get("reason"))
        if not compact or key in seen_blocked_queries:
            continue
        seen_blocked_queries.add(key)
        blocked_queries.append({**item, "query": query})

    return {
        "primary_queries": primary_queries[:EXTERNAL_SEARCH_MAX_KAKAO_QUERIES],
        "blocked_queries": blocked_queries,
        "fallback_queries": fallback_queries[:EXTERNAL_SEARCH_MAX_KAKAO_QUERIES],
    }


def _external_queries_from_frame(search_plan, frame, fallback_query=""):
    return _query_generation_from_frame(
        search_plan,
        frame,
        fallback_query=fallback_query,
    )["primary_queries"]


def _external_match_terms(frame):
    return list(dict.fromkeys([
        *_external_frame_terms(frame, "target_objects", "targetObjects"),
        *_external_frame_terms(frame, "result_match_terms", "resultMatchTerms"),
        *_external_frame_terms(frame, "candidate_place_types", "candidatePlaceTypes"),
    ]))


def _evaluate_external_candidate_evidence(candidate_text, frame):
    compact_candidate = _compact_external_text(candidate_text)
    target_terms = _external_frame_terms(frame, "target_objects", "targetObjects")
    result_terms = _external_frame_terms(frame, "result_match_terms", "resultMatchTerms")
    evidence_terms = _external_frame_evidence_terms(frame)
    candidate_terms = _external_frame_terms(
        frame,
        "candidate_place_types",
        "candidatePlaceTypes",
        "search_queries",
        "searchQueries",
    )
    matched = []

    for term in [*target_terms, *evidence_terms]:
        compact_term = _compact_external_text(term)
        if compact_term and compact_term in compact_candidate:
            matched.append({"type": "target_term", "value": term})

    for term in result_terms:
        compact_term = _compact_external_text(term)
        if compact_term and compact_term in compact_candidate:
            matched.append({"type": "result_term", "value": term})

    if matched:
        return "strong", matched

    for term in candidate_terms:
        compact_term = _compact_external_text(term)
        if compact_term and compact_term in compact_candidate:
            matched.append({"type": "candidate_place_type", "value": term})

    if matched:
        return "medium", matched

    return "weak", []


def _external_score(strength, distance=None):
    base = {"strong": 78, "medium": 58, "weak": 38}.get(strength, 38)
    try:
        distance_value = int(distance)
    except (TypeError, ValueError):
        distance_value = None
    if distance_value is not None:
        if distance_value <= 500:
            base += 6
        elif distance_value <= 1500:
            base += 3
    return min(base, 85)


def _normalize_kakao_external_candidate(place, frame, query):
    place_id = _clean_external_text(place.get("id"))
    name = _clean_external_text(place.get("place_name"))
    category = _clean_external_text(place.get("category_name"))
    address = _clean_external_text(place.get("address_name"))
    road_address = _clean_external_text(place.get("road_address_name"))
    lat = place.get("y")
    lng = place.get("x")
    candidate_text = " ".join([name, category, address, road_address])
    strength, matched_evidence = _evaluate_external_candidate_evidence(candidate_text, frame)
    frame_evidence_tier = _candidate_evidence_tier({"matched_evidence": matched_evidence})
    score = _external_score(strength, place.get("distance"))
    confidence = {"strong": "medium", "medium": "medium", "weak": "low"}.get(strength, "low")
    confidence_label = {"strong": "보통", "medium": "보통", "weak": "확인 필요"}.get(strength, "확인 필요")
    external_url = _clean_external_text(place.get("place_url")) or (
        f"https://place.map.kakao.com/{place_id}" if place_id else ""
    )
    reason = (
        f"{query} 카카오 장소 검색 결과와 장소 카테고리를 기준으로 추천한 후보입니다. "
        "세부 메뉴와 영업 여부는 방문 전 확인이 필요합니다."
    )
    caution = "카카오 검색 후보입니다. 방문 전 세부 정보 확인이 필요합니다."

    return {
        "id": f"external:kakao:{place_id or name}",
        "source": "kakao_candidate",
        "source_type": "kakao_candidate",
        "source_label": "카카오 후보",
        "name": name,
        "category": category,
        "address": address,
        "road_address": road_address,
        "detail_location": road_address or address,
        "lat": float(lat) if lat not in (None, "") else None,
        "lng": float(lng) if lng not in (None, "") else None,
        "distance": int(place["distance"]) if _clean_external_text(place.get("distance")).isdigit() else None,
        "distance_m": int(place["distance"]) if _clean_external_text(place.get("distance")).isdigit() else None,
        "external_url": external_url,
        "kakao_place_url": external_url,
        "place_url": external_url,
        "external_id": place_id,
        "source_name": "kakao_local",
        "evidence_text": candidate_text,
        "matched_evidence": matched_evidence,
        "matched_tags": [item["value"] for item in matched_evidence],
        "matched_tag_labels": [item["value"] for item in matched_evidence],
        "missing_tags": ["세부 메뉴/영업 여부 확인 필요"],
        "missing_tag_labels": ["세부 메뉴/영업 여부 확인 필요"],
        "frame_match_strength": strength,
        "frame_evidence_tier": frame_evidence_tier,
        "evidence_sort_rank": _candidate_evidence_rank({"frame_evidence_tier": frame_evidence_tier}),
        "confidence": confidence,
        "recommendation_confidence": confidence,
        "confidence_label": confidence_label,
        "fallback_level": 4 if strength in {"strong", "medium"} else 5,
        "fallback_label": "카카오/웹 검색 근거 후보, 세부 정보 확인 필요",
        "fallback_description": "카카오 장소 검색 근거를 가진 응답 단위 후보입니다.",
        "score": score,
        "recommendation_reason": reason,
        "recommend_reason": reason,
        "reason": reason,
        "caution_message": caution,
        "caution": caution,
        "is_external": True,
        "can_show_on_map": bool(lat and lng),
        "raw_scores": {},
        "score_breakdown": {
            "external_source": "kakao",
            "external_query": query,
            "frame_match_strength": strength,
            "frame_evidence_tier": frame_evidence_tier,
        },
    }


def _dedupe_external_candidates(candidates, existing_results):
    seen = set()
    for result in existing_results:
        external_id = _clean_external_text(result.get("external_id") or result.get("externalId"))
        if external_id:
            seen.add(("external_id", external_id))
        name_address_key = (
            _compact_external_text(result.get("name")),
            _compact_external_text(result.get("address") or result.get("road_address")),
        )
        if any(name_address_key):
            seen.add(("name_address", name_address_key))

    deduped = []
    for candidate in candidates:
        external_id = _clean_external_text(candidate.get("external_id"))
        name_address_key = (
            _compact_external_text(candidate.get("name")),
            _compact_external_text(candidate.get("address") or candidate.get("road_address")),
        )
        keys = [
            ("external_id", external_id) if external_id else None,
            ("name_address", name_address_key) if any(name_address_key) else None,
        ]
        if any(key in seen for key in keys if key):
            continue
        for key in keys:
            if key:
                seen.add(key)
        deduped.append(candidate)
    return deduped


def _merge_and_sort_recommendation_results(db_results, external_candidates, ranking_policy=""):
    merged = [*db_results, *external_candidates]
    if ranking_policy == "urgent_nearest":
        merged.sort(key=lambda result: (
            _result_sort_rank(result),
            result.get("distance") if result.get("distance") is not None else 999999999,
            -float(result.get("score") or 0),
            _result_source_tie_rank(result),
            str(result.get("id")),
        ))
    else:
        merged.sort(key=lambda result: (
            _result_sort_rank(result),
            -float(result.get("score") or 0),
            result.get("distance") if result.get("distance") is not None else 999999999,
            _result_source_tie_rank(result),
            str(result.get("id")),
        ))
    return merged


def _collect_kakao_external_candidates(queries, frame, lat=None, lng=None):
    candidates = []
    query_result_counts = []
    for query in queries[:EXTERNAL_SEARCH_MAX_KAKAO_QUERIES]:
        try:
            result = search_places_by_keyword(
                keyword=query,
                lat=lat,
                lng=lng,
                radius=EXTERNAL_SEARCH_KAKAO_RADIUS,
                size=EXTERNAL_SEARCH_KAKAO_SIZE,
            )
        except Exception as error:
            logger.info(
                "[EXTERNAL_SEARCH_KAKAO_FAILED] query=%s error=%s",
                query,
                str(error)[:160],
            )
            continue

        documents = result.get("documents") if isinstance(result, dict) else []
        documents = documents if isinstance(documents, list) else []
        query_result_counts.append({"query": query, "count": len(documents)})
        for place in documents:
            if not isinstance(place, dict):
                continue
            candidates.append(_normalize_kakao_external_candidate(place, frame, query))

    return candidates, query_result_counts


def _normalize_web_external_candidate(candidate, frame):
    name = _clean_external_text(candidate.get("name") or candidate.get("title"))
    source_url = _clean_external_text(candidate.get("source_url"))
    summary = _clean_external_text(candidate.get("summary") or candidate.get("evidence_text"))
    text = " ".join([name, summary, _clean_external_text(candidate.get("address_hint"))])
    strength, matched_evidence = _evaluate_external_candidate_evidence(text, frame)
    frame_evidence_tier = _candidate_evidence_tier({"matched_evidence": matched_evidence})
    confidence = {"strong": "medium", "medium": "medium", "weak": "low"}.get(strength, "low")
    return {
        "id": f"external:web:{source_url or name}",
        "source": "web_evidence_candidate",
        "source_type": "web_evidence_candidate",
        "source_label": "웹 근거 후보",
        "name": name,
        "category": _clean_external_text(candidate.get("category")),
        "address": _clean_external_text(candidate.get("address_hint")),
        "lat": None,
        "lng": None,
        "external_url": source_url,
        "place_url": source_url,
        "evidence_text": summary,
        "matched_evidence": matched_evidence,
        "frame_match_strength": strength,
        "frame_evidence_tier": frame_evidence_tier,
        "evidence_sort_rank": _candidate_evidence_rank({"frame_evidence_tier": frame_evidence_tier}),
        "confidence": confidence,
        "recommendation_confidence": confidence,
        "confidence_label": "확인 필요",
        "fallback_level": 5,
        "fallback_label": "카카오/웹 검색 근거 후보, 세부 정보 확인 필요",
        "fallback_description": "웹 검색 결과 기반 후보이며 지도 표시는 좌표 확보 전까지 제한됩니다.",
        "score": _external_score(strength),
        "recommendation_reason": "웹 검색 결과의 장소명과 요약 문구를 기준으로 추천한 후보입니다. 방문 전 위치와 세부 정보를 확인해 주세요.",
        "recommend_reason": "웹 검색 결과의 장소명과 요약 문구를 기준으로 추천한 후보입니다. 방문 전 위치와 세부 정보를 확인해 주세요.",
        "caution_message": "웹 검색 근거 후보입니다. 지도 표시는 실제 좌표 확인 전까지 제한됩니다.",
        "caution": "웹 검색 근거 후보입니다. 지도 표시는 실제 좌표 확인 전까지 제한됩니다.",
        "is_external": True,
        "can_show_on_map": False,
    }


def _collect_web_external_candidates(queries, frame, data, condition, lat=None, lng=None):
    if not getattr(settings, "AI_WEB_SEARCH_AUTO_MERGE_ENABLED", False):
        return []
    web_candidates = []
    for query in queries[:EXTERNAL_SEARCH_MAX_WEB_QUERIES]:
        result = get_ai_web_search_result(
            query=query,
            lat=lat,
            lng=lng,
            location_hint=_external_location_anchor(data.get("search_plan") or {}, frame),
            search_plan=data.get("search_plan") or {},
            condition=condition,
            existing_results_summary={
                "db_count": len(data.get("results") or []),
                "relevant_result_count": data.get("relevant_result_count") or 0,
            },
            manual=True,
        )
        for candidate in result.get("candidates") or []:
            if isinstance(candidate, dict):
                web_candidates.append(_normalize_web_external_candidate(candidate, frame))
    return web_candidates


def _merge_external_candidates_if_needed(data, query, lat=None, lng=None, search_plan=None, frame=None, condition=None):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    frame = frame if isinstance(frame, dict) else {}
    db_results = data.get("results") if isinstance(data.get("results"), list) else []
    should_run, reason = _should_run_external_search(data, search_plan, frame)
    external_debug = {
        "external_search_triggered": False,
        "external_search_reason": reason,
        "external_query_count": 0,
        "external_candidate_count": 0,
        "merged_candidate_count": len(db_results),
    }
    if not should_run:
        data.update(external_debug)
        return data

    queries = _external_queries_from_frame(search_plan, frame, fallback_query=query)
    external_debug["external_query_count"] = len(queries)
    if not queries:
        external_debug["external_search_reason"] = "no_external_queries"
        data.update(external_debug)
        return data

    kakao_candidates, query_result_counts = _collect_kakao_external_candidates(queries, frame, lat=lat, lng=lng)
    web_candidates = _collect_web_external_candidates(
        queries,
        frame,
        data,
        condition or {},
        lat=lat,
        lng=lng,
    )
    external_candidates = _dedupe_external_candidates(
        [*kakao_candidates, *web_candidates],
        db_results,
    )[:EXTERNAL_SEARCH_MAX_MERGED_CANDIDATES]
    merged_results = _merge_and_sort_recommendation_results(
        db_results,
        external_candidates,
        ranking_policy=_clean_external_text(frame.get("ranking_policy") or frame.get("rankingPolicy")),
    )

    external_debug.update({
        "external_search_triggered": True,
        "external_search_reason": reason,
        "external_candidate_count": len(kakao_candidates) + len(web_candidates),
        "merged_candidate_count": len(merged_results),
        "external_queries": queries,
        "external_query_result_counts": query_result_counts,
    })
    logger.info(
        "[EXTERNAL_SEARCH_MERGE] triggered=%s reason=%s query_count=%s candidate_count=%s merged_count=%s",
        external_debug["external_search_triggered"],
        external_debug["external_search_reason"],
        external_debug["external_query_count"],
        external_debug["external_candidate_count"],
        external_debug["merged_candidate_count"],
    )
    data.update(external_debug)
    data["results"] = merged_results[:50]
    data["count"] = len(data["results"])
    data["relevant_result_count"] = len(data["results"])
    data["external_candidates"] = external_candidates
    return data


def _parse_unified_limit(value, default=50):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, 1), 50)


def collect_db_candidates(parsed, lat=None, lng=None, limit=50, radius=None, user=None, search_plan=None, frame=None):
    data = search_db_recommendations(
        scenario=parsed["scenario"],
        condition=parsed,
        lat=lat,
        lng=lng,
        keyword=parsed["situation_summary"],
        exclude_categories=parsed.get("exclude_categories"),
        limit=limit,
        radius=radius,
        user=user,
        search_plan=search_plan,
        place_intent_frame=frame,
    )
    candidates = []
    for index, candidate in enumerate(data.get("results") or []):
        if not isinstance(candidate, dict):
            continue
        candidates.append({
            **candidate,
            "candidate_source": "db",
            "unified_candidate_source": "db",
            "is_external": False,
            "can_show_on_map": candidate.get("can_show_on_map", True),
            "collector_rank": index,
        })
    return data, candidates


def collect_kakao_candidates(queries, frame, lat=None, lng=None):
    candidates, query_result_counts = _collect_kakao_external_candidates(
        queries,
        frame,
        lat=lat,
        lng=lng,
    )
    normalized = [
        {
            **candidate,
            "candidate_source": "kakao",
            "unified_candidate_source": "kakao",
            "collector_rank": index,
        }
        for index, candidate in enumerate(candidates)
        if isinstance(candidate, dict)
    ]
    return normalized, query_result_counts


def collect_web_candidates(queries, frame, db_data, parsed, lat=None, lng=None):
    candidates = _collect_web_external_candidates(
        queries,
        frame,
        db_data,
        parsed or {},
        lat=lat,
        lng=lng,
    )
    return [
        {
            **candidate,
            "candidate_source": "web",
            "unified_candidate_source": "web",
            "collector_rank": index,
        }
        for index, candidate in enumerate(candidates)
        if isinstance(candidate, dict)
    ]


def _candidate_identity_keys(candidate):
    external_id = _clean_external_text(candidate.get("external_id") or candidate.get("externalId"))
    name = _compact_external_text(candidate.get("name"))
    address = _compact_external_text(
        candidate.get("address")
        or candidate.get("road_address")
        or candidate.get("detail_location")
        or candidate.get("detailLocation")
    )
    keys = []
    if external_id:
        keys.append(("external_id", external_id))
    if name and address:
        keys.append(("name_address", name, address))
    elif name:
        keys.append(("name", name))
    return keys


def _reinforce_db_candidates_with_external_evidence(db_candidates, external_candidates):
    external_by_key = {}
    for external in external_candidates:
        tier = _candidate_evidence_tier(external)
        if tier not in {"target_direct", "result_direct"}:
            continue
        for key in _candidate_identity_keys(external):
            external_by_key[key] = external

    reinforced = []
    for candidate in db_candidates:
        matched_external = None
        for key in _candidate_identity_keys(candidate):
            matched_external = external_by_key.get(key)
            if matched_external:
                break
        if not matched_external:
            reinforced.append(candidate)
            continue

        current_tier = _candidate_evidence_tier(candidate)
        external_tier = _candidate_evidence_tier(matched_external)
        if _candidate_evidence_rank({"frame_evidence_tier": external_tier}) >= _candidate_evidence_rank(candidate):
            reinforced.append(candidate)
            continue

        matched_evidence = candidate.get("matched_evidence") or []
        if not isinstance(matched_evidence, list):
            matched_evidence = []
        reinforced_candidate = {
            **candidate,
            "frame_evidence_tier": external_tier,
            "frame_match_strength": "strong",
            "evidence_sort_rank": _candidate_evidence_rank({"frame_evidence_tier": external_tier}),
            "fallback_label": "추천 근거 높음",
            "fallback_description": "DB 후보와 외부 검색 근거가 같은 의도를 서로 보강한 후보입니다.",
            "caution_message": candidate.get("caution_message") or "외부 검색 근거로 보강된 후보입니다. 세부 정보는 방문 전 확인해 주세요.",
            "matched_evidence": [
                *matched_evidence,
                {
                    "type": "external_reinforcement",
                    "value": matched_external.get("name") or matched_external.get("source_label") or "external",
                    "source_strength": "verified",
                },
            ],
        }
        score_breakdown = reinforced_candidate.get("score_breakdown")
        score_breakdown = score_breakdown if isinstance(score_breakdown, dict) else {}
        reinforced_candidate["score_breakdown"] = {
            **score_breakdown,
            "external_reinforced": True,
            "external_reinforcement_source": matched_external.get("source_type"),
            "frame_evidence_tier": external_tier,
        }
        reinforced.append(reinforced_candidate)
    return reinforced


def _candidate_distance_for_rank(candidate):
    for key in ("distance", "distance_m", "distanceM"):
        try:
            value = float(candidate.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return 999999999


def _candidate_score_for_rank(candidate):
    try:
        return float(candidate.get("score") or 0)
    except (TypeError, ValueError):
        return 0


def _candidate_text_for_compatibility(candidate):
    text_parts = [
        candidate.get("name"),
        candidate.get("category"),
        candidate.get("address"),
        candidate.get("road_address"),
        candidate.get("detail_location"),
        candidate.get("source_name"),
        candidate.get("evidence_text"),
        candidate.get("fallback_description"),
        candidate.get("recommendation_reason"),
    ]
    for key in (
        "matched_tags",
        "matched_tag_labels",
        "verified_tags",
        "verified_tag_labels",
        "suggested_tags",
        "suggested_tag_labels",
        "place_natures",
    ):
        value = candidate.get(key)
        if isinstance(value, list):
            text_parts.extend(value)
        else:
            text_parts.append(value)

    matched_evidence = candidate.get("matched_evidence") or []
    if isinstance(matched_evidence, list):
        for item in matched_evidence:
            if isinstance(item, dict):
                text_parts.extend([item.get("value"), item.get("label"), item.get("text")])

    return " ".join(_clean_external_text(part) for part in text_parts if _clean_external_text(part))


def _candidate_matches_any_term(candidate, terms):
    candidate_text = _compact_external_text(_candidate_text_for_compatibility(candidate))
    if not candidate_text:
        return False
    for term in terms:
        compact_term = _compact_external_text(term)
        if compact_term and compact_term in candidate_text:
            return True
    return False


def _frame_direct_compatibility_terms(frame):
    return list(dict.fromkeys([
        *_frame_non_broad_terms(frame, "target_objects", "targetObjects"),
        *_frame_non_broad_terms(frame, "result_match_terms", "resultMatchTerms"),
        *[
            term
            for term in _external_frame_evidence_terms(frame)
            if not _is_broad_place_term(term)
        ],
    ]))


def _frame_candidate_compatibility_terms(frame):
    return list(dict.fromkeys([
        *_frame_non_broad_terms(frame, "candidate_place_types", "candidatePlaceTypes"),
        *_frame_non_broad_terms(frame, "candidate_category_codes", "candidateCategoryCodes"),
    ]))


def _candidate_has_direct_frame_evidence(candidate):
    return _candidate_evidence_tier(candidate) in {
        "target_direct",
        "result_direct",
        "verified_direct",
        "suggested_direct",
        "candidate_direct",
    }


def _compatibility_label_for_candidate(candidate):
    tier = _candidate_evidence_tier(candidate)
    if tier in {"target_direct", "result_direct", "verified_direct"}:
        return candidate.get("fallback_label") or "추천 근거 높음"
    if tier in {"suggested_direct", "candidate_direct"}:
        return candidate.get("fallback_label") or "추천 후보, 확인 필요"
    return "관련 근거 부족 후보"


def _apply_candidate_compatibility(candidate, frame):
    score_breakdown = candidate.get("score_breakdown")
    score_breakdown = score_breakdown if isinstance(score_breakdown, dict) else {}
    direct_terms = _frame_direct_compatibility_terms(frame)
    candidate_terms = _frame_candidate_compatibility_terms(frame)
    has_specific_target = bool(direct_terms)
    evidence_tier = _candidate_evidence_tier(candidate)

    compatible = (
        _candidate_has_direct_frame_evidence(candidate)
        or _candidate_matches_any_term(candidate, direct_terms)
        or (
            not has_specific_target
            and _candidate_matches_any_term(candidate, candidate_terms)
        )
    )

    if compatible:
        return True, {
            **candidate,
            "compatibility_gate": "passed",
            "fallback_label": _compatibility_label_for_candidate(candidate),
            "score_breakdown": {
                **score_breakdown,
                "compatibility_gate": "passed",
            },
        }

    source_type = _clean_external_text(candidate.get("source_type"))
    category_only = evidence_tier in {"category_only", "none"} or source_type == "db_category_fallback"
    if has_specific_target and category_only:
        capped_score = min(_candidate_score_for_rank(candidate), 30)
        return False, {
            **candidate,
            "compatibility_gate": "excluded",
            "compatibility_gate_reason": "specific_frame_target_without_candidate_evidence",
            "frame_match_strength": "weak",
            "frame_evidence_tier": evidence_tier if evidence_tier != "none" else "category_only",
            "fallback_label": "관련 근거 부족 후보",
            "fallback_description": "현재 사용자 의도와 직접 맞는 근거가 부족한 후보입니다.",
            "score": capped_score,
            "score_breakdown": {
                **score_breakdown,
                "compatibility_gate": "excluded",
                "compatibility_gate_reason": "specific_frame_target_without_candidate_evidence",
                "score_cap": min(score_breakdown.get("score_cap", capped_score) or capped_score, capped_score),
                "score_cap_reasons": list(dict.fromkeys([
                    *(score_breakdown.get("score_cap_reasons", []) if isinstance(score_breakdown.get("score_cap_reasons"), list) else []),
                    "compatibility_gate_excluded_from_top_results",
                ])),
            },
        }

    capped_score = min(_candidate_score_for_rank(candidate), 30)
    return False, {
        **candidate,
        "compatibility_gate": "excluded",
        "compatibility_gate_reason": "weak_candidate_type_match",
        "frame_match_strength": "weak",
        "frame_evidence_tier": evidence_tier if evidence_tier != "none" else "category_only",
        "fallback_label": "관련 근거 부족 후보",
        "fallback_description": "현재 사용자 의도와 직접 맞는 근거가 부족한 후보입니다.",
        "score": capped_score,
        "score_breakdown": {
            **score_breakdown,
            "compatibility_gate": "excluded",
            "compatibility_gate_reason": "weak_candidate_type_match",
            "score_cap": min(score_breakdown.get("score_cap", capped_score) or capped_score, capped_score),
            "score_cap_reasons": list(dict.fromkeys([
                *(score_breakdown.get("score_cap_reasons", []) if isinstance(score_breakdown.get("score_cap_reasons"), list) else []),
                "compatibility_gate_excluded_from_top_results",
            ])),
        },
    }


def compatibility_filter_or_cap(candidates, frame):
    kept = []
    removed = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        keep, updated_candidate = _apply_candidate_compatibility(candidate, frame)
        if keep:
            kept.append(updated_candidate)
        else:
            removed.append(updated_candidate)

    return kept, {
        "compatibility_gate_applied": True,
        "compatibility_removed_count": len(removed),
        "compatibility_demoted_count": 0,
        "hidden_weak_count": len(removed),
        "hidden_weak_candidates": removed[:50],
        "compatibility_removed_candidates": [
            {
                "id": candidate.get("id"),
                "name": candidate.get("name"),
                "source_type": candidate.get("source_type"),
                "reason": candidate.get("compatibility_gate_reason"),
            }
            for candidate in removed[:20]
        ],
    }


def unified_evidence_rank_candidates(candidates):
    ranked = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        tier = _candidate_evidence_tier(candidate)
        score_breakdown = candidate.get("score_breakdown")
        score_breakdown = score_breakdown if isinstance(score_breakdown, dict) else {}
        ranked.append({
            **candidate,
            "frame_evidence_tier": tier,
            "evidence_sort_rank": _candidate_evidence_rank({"frame_evidence_tier": tier}),
            "unified_ranker_applied": True,
            "score_breakdown": {
                **score_breakdown,
                "unified_evidence_tier": tier,
                "unified_evidence_rank": _candidate_evidence_rank({"frame_evidence_tier": tier}),
            },
        })

    ranked.sort(key=lambda candidate: (
        _candidate_evidence_rank(candidate),
        _candidate_distance_for_rank(candidate),
        -_candidate_score_for_rank(candidate),
        _result_source_tie_rank(candidate),
        str(candidate.get("id")),
    ))
    return [
        {
            **candidate,
            "backend_rank": index + 1,
            "unified_rank": index + 1,
        }
        for index, candidate in enumerate(ranked)
    ]


def run_unified_candidate_search(parsed, query, original_query, lat=None, lng=None, limit=50, radius=None, user=None, search_plan=None, frame=None):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    frame = frame if isinstance(frame, dict) else {}
    raw_search_plan = search_plan.get("_raw_ai_search_plan")
    raw_frame = search_plan.get("_raw_place_intent_frame")
    raw_search_plan = raw_search_plan if isinstance(raw_search_plan, dict) else search_plan
    raw_frame = raw_frame if isinstance(raw_frame, dict) else frame
    search_plan = {
        **search_plan,
        "originalQuery": search_plan.get("originalQuery") or original_query or query,
        "original_query": search_plan.get("original_query") or original_query or query,
    }
    original_search_plan = {
        **raw_search_plan,
        "originalQuery": raw_search_plan.get("originalQuery") or original_query or query,
        "original_query": raw_search_plan.get("original_query") or original_query or query,
    }
    original_frame = raw_frame
    query_generation = _query_generation_from_frame(
        original_search_plan,
        original_frame,
        fallback_query=original_query or query,
    )
    search_plan, frame, evidence_partitions = _sanitize_frame_for_ai_search(search_plan, frame)
    final_limit = _parse_unified_limit(limit, default=50)
    collector_limit = max(final_limit, 50)
    rejection_reason = _ai_search_execution_plan_rejection_reason(search_plan)

    if rejection_reason or not _has_actionable_place_target(search_plan, frame):
        has_actionable_target = False if rejection_reason else _has_actionable_place_target(search_plan, frame)
        data = {
            "candidate_pipeline": "unified_evidence",
            "unified_candidate_pipeline": True,
            "frontend_should_preserve_order": True,
            "frontend_should_skip_kakao_fallback": True,
            "collector_names": ["db", "kakao", "web"],
            "candidate_source_counts": {
                "db": 0,
                "kakao": 0,
                "web": 0,
            },
            "decision_action": "ai_unavailable" if rejection_reason in {"ai_call_failed", "parser_fallback", "legacy_fallback"} else "ask_clarification",
            "can_search_now": False,
            "external_search_triggered": False,
            "external_search_reason": (
                f"blocked_by_{rejection_reason}"
                if rejection_reason
                else "blocked_by_missing_actionable_place_target"
            ),
            "external_query_count": 0,
            "external_candidate_count": 0,
            "merged_candidate_count": 0,
            "external_queries": [],
            "external_query_result_counts": [],
            "external_candidates": [],
            "hidden_weak_candidates": [],
            "hidden_weak_count": 0,
            "results": [],
            "count": 0,
            "relevant_result_count": 0,
            "debug_pipeline": _build_debug_pipeline(
                original_search_plan,
                original_frame,
                query_generation=query_generation,
                candidate_counts={"db": 0, "kakao": 0, "web": 0, "top_results": 0, "hidden_weak": 0, "removed_incompatible": 0},
                has_actionable_place_target=has_actionable_target,
                ai_call_failed=bool(rejection_reason),
                ai_fallback_reason=rejection_reason,
            ),
        }
        return data

    db_data, db_candidates = collect_db_candidates(
        parsed,
        lat=lat,
        lng=lng,
        limit=collector_limit,
        radius=radius,
        user=user,
        search_plan=search_plan,
        frame=frame,
    )
    queries = query_generation["primary_queries"]
    kakao_candidates, query_result_counts = collect_kakao_candidates(queries, frame, lat=lat, lng=lng)
    web_candidates = collect_web_candidates(queries, frame, db_data, parsed, lat=lat, lng=lng)
    external_candidates = [*kakao_candidates, *web_candidates]
    reinforced_db_candidates = _reinforce_db_candidates_with_external_evidence(
        db_candidates,
        external_candidates,
    )
    deduped_external_candidates = _dedupe_external_candidates(
        external_candidates,
        reinforced_db_candidates,
    )
    compatible_candidates, compatibility_debug = compatibility_filter_or_cap([
        *reinforced_db_candidates,
        *deduped_external_candidates,
    ], frame)
    unified_candidates = unified_evidence_rank_candidates(compatible_candidates)
    results = unified_candidates[:final_limit]
    hidden_weak_candidates = compatibility_debug.get("hidden_weak_candidates") or []
    candidate_counts = {
        "db": len(db_candidates),
        "kakao": len(kakao_candidates),
        "web": len(web_candidates),
        "top_results": len(results),
        "hidden_weak": len(hidden_weak_candidates),
        "removed_incompatible": compatibility_debug.get("compatibility_removed_count") or 0,
    }

    data = {
        **db_data,
        "candidate_pipeline": "unified_evidence",
        "unified_candidate_pipeline": True,
        "frontend_should_preserve_order": True,
        "frontend_should_skip_kakao_fallback": True,
        "collector_names": ["db", "kakao", "web"],
        "candidate_source_counts": {
            "db": len(db_candidates),
            "kakao": len(kakao_candidates),
            "web": len(web_candidates),
        },
        "external_search_triggered": bool(kakao_candidates or web_candidates),
        "external_search_reason": "unified_candidate_collectors" if (kakao_candidates or web_candidates) else "no_external_candidates",
        "external_query_count": len(queries),
        "external_candidate_count": len(external_candidates),
        "merged_candidate_count": len(unified_candidates),
        "external_queries": queries,
        "query_generation": query_generation,
        "external_query_result_counts": query_result_counts,
        "external_candidates": deduped_external_candidates,
        **compatibility_debug,
        "results": results,
        "count": len(results),
        "relevant_result_count": len(results),
        "debug_pipeline": _build_debug_pipeline(
            original_search_plan,
            original_frame,
            query_generation=query_generation,
            candidate_counts=candidate_counts,
            top_results=results,
            hidden_weak_candidates=hidden_weak_candidates,
            has_actionable_place_target=True,
        ),
        "evidence_source_summary": {
            "trusted_terms": evidence_partitions.get("trusted_terms", []),
            "blocked_terms": evidence_partitions.get("blocked_terms", []),
        },
    }
    return data


@api_view(["POST"])
def legacy_ai_recommendation_search(request):
    query = request.data.get("query", "")
    original_query = request.data.get("originalQuery") or request.data.get("original_query") or query
    lat = request.data.get("lat")
    lng = request.data.get("lng")
    limit = request.data.get("limit", 10)
    radius = request.data.get("radius")
    search_plan = _get_request_search_plan(request.data)
    place_intent_frame = _get_request_place_intent_frame(request.data, search_plan)
    has_valid_frame = _is_valid_request_frame(place_intent_frame)
    decision_action = _get_request_decision_action(request.data, search_plan, place_intent_frame)
    user = request.user if request.user.is_authenticated else None
    if isinstance(search_plan, dict):
        search_plan = {
            **search_plan,
            "originalQuery": search_plan.get("originalQuery") or original_query or query,
            "original_query": search_plan.get("original_query") or original_query or query,
        }

    if decision_action in {"ask_clarification", "out_of_scope", "blocked", "ai_unavailable"}:
        return _empty_decision_gate_response(decision_action, search_plan, place_intent_frame)

    sanitized_search_plan, sanitized_frame, _ = _sanitize_frame_for_ai_search(search_plan, place_intent_frame)
    initial_rejection_reason = _ai_search_execution_plan_rejection_reason(sanitized_search_plan)
    if has_valid_frame and initial_rejection_reason:
        search_plan = {
            **search_plan,
            "_rejected_ai_search_plan_reason": initial_rejection_reason,
        }
        place_intent_frame = {}
        has_valid_frame = False

    if has_valid_frame and _is_ai_failure_fallback(search_plan):
        return _ai_unavailable_response(search_plan, place_intent_frame, search_plan.get("ai_fallback_reason") or "ai_fallback_without_actionable_target")

    if has_valid_frame and _frame_direct_compatibility_terms(sanitized_frame) and not _has_actionable_place_target(sanitized_search_plan, sanitized_frame):
        search_plan, place_intent_frame = _sync_decision_to_plan(
            search_plan,
            place_intent_frame,
            "out_of_scope",
            reason="missing_place_seeking_frame_evidence",
            message="생활 장소 추천으로 이어질 대상 근거가 부족해 검색을 실행하지 않았습니다.",
        )
        return _empty_decision_gate_response(
            "out_of_scope",
            search_plan,
            place_intent_frame,
            ai_debug={
                "ai_search_execution_gate": {
                    "status": "blocked_by_missing_place_target_evidence",
                    "reason": "missing_place_seeking_frame_evidence",
                },
            },
        )

    if has_valid_frame and decision_action in {"", "search"}:
        gated_response = _request_frame_post_validation_response(
            original_query or query,
            search_plan,
            place_intent_frame,
        )
        if gated_response:
            return gated_response

    safety_parse = parse_situation(original_query or query)

    safety_blocked = safety_parse.get("blocked") or safety_parse.get("is_searchable") is False
    safety_unavailable = safety_parse.get("block_reason") == "safety_check_unavailable"
    if safety_blocked and not (has_valid_frame and safety_unavailable):
        return _decision_response_from_safety_parse(safety_parse, search_plan, place_intent_frame)

    if not has_valid_frame:
        generated_plan = build_conversational_search_plan(
            original_query or query,
            user=user,
            lat=lat,
            lng=lng,
            map_center=_get_request_map_center(request.data),
            previous_context=_get_request_previous_context(request.data),
        )
        generated_plan = generated_plan if isinstance(generated_plan, dict) else {}
        generated_search_plan = generated_plan.get("search_plan")
        generated_search_plan = generated_search_plan if isinstance(generated_search_plan, dict) else {}
        for passthrough_key in ("parser_fallback", "parserFallback", "plan_source", "planSource", "ai_fallback_reason", "aiFallbackReason"):
            if passthrough_key in generated_plan and passthrough_key not in generated_search_plan:
                generated_search_plan[passthrough_key] = generated_plan.get(passthrough_key)
        generated_search_plan["originalQuery"] = generated_search_plan.get("originalQuery") or original_query or query
        generated_search_plan["original_query"] = generated_search_plan.get("original_query") or original_query or query
        generated_frame = _get_request_place_intent_frame({}, generated_search_plan)
        generated_action = (
            generated_plan.get("action")
            or generated_plan.get("decision_action")
            or generated_search_plan.get("decision_action")
            or generated_frame.get("decision_action")
            or ""
        )
        generated_action = str(generated_action or "").strip()
        generated_sanitized_plan, generated_sanitized_frame, _ = _sanitize_frame_for_ai_search(
            generated_search_plan,
            generated_frame,
        )
        generated_rejection_reason = _ai_search_execution_plan_rejection_reason(generated_sanitized_plan)

        if generated_rejection_reason:
            return _ai_unavailable_response(
                generated_search_plan,
                generated_frame,
                generated_sanitized_plan.get("ai_fallback_reason") or generated_rejection_reason,
            )

        if generated_action in {"ask_clarification", "out_of_scope", "blocked"}:
            if generated_plan.get("clarification_question"):
                generated_search_plan["clarification_question"] = generated_plan.get("clarification_question")
            if generated_plan.get("clarification_options"):
                generated_search_plan["clarification_options"] = generated_plan.get("clarification_options")
            return _empty_decision_gate_response(
                generated_action,
                generated_search_plan,
                generated_frame,
                ai_debug={
                    "ai_search_execution_gate": {
                        "status": f"planner_returned_{generated_action}",
                        "source": "ai_search_no_frame_router",
                    },
                },
            )

        if generated_action == "search" and _is_valid_request_frame(generated_frame):
            generated_sanitized_plan["_raw_ai_search_plan"] = generated_search_plan
            generated_sanitized_plan["_raw_place_intent_frame"] = generated_frame
            search_plan = generated_sanitized_plan
            place_intent_frame = generated_sanitized_frame
            has_valid_frame = True
            gated_response = _request_frame_post_validation_response(
                original_query or query,
                search_plan,
                place_intent_frame,
            )
            if gated_response:
                return gated_response
        else:
            fallback_question = (
                generated_plan.get("clarification_question")
                or "어떤 상황의 장소를 찾으시는지 지역과 목적을 함께 입력해 주세요."
            )
            generated_search_plan.update({
                "clarification_question": fallback_question,
                "decision_action": "ask_clarification",
                "decisionAction": "ask_clarification",
                "execution_mode": "decision_gate",
                "plan_source": generated_plan.get("plan_source") or "ai_search_no_frame_gate",
            })
            return _empty_decision_gate_response(
                "ask_clarification",
                generated_search_plan,
                generated_frame,
                ai_debug={
                    "ai_search_execution_gate": {
                        "status": "missing_valid_frame",
                        "source": "ai_search_no_frame_router",
                    },
                },
            )

    raw_execution_search_plan = search_plan.copy() if isinstance(search_plan, dict) else {}
    raw_execution_frame = place_intent_frame.copy() if isinstance(place_intent_frame, dict) else {}
    search_plan, place_intent_frame, evidence_partitions = _sanitize_frame_for_ai_search(search_plan, place_intent_frame)
    search_plan["_raw_ai_search_plan"] = raw_execution_search_plan
    search_plan["_raw_place_intent_frame"] = raw_execution_frame
    final_rejection_reason = _ai_search_execution_plan_rejection_reason(search_plan)
    if final_rejection_reason:
        return _ai_unavailable_response(
            search_plan,
            place_intent_frame,
            search_plan.get("ai_fallback_reason") or final_rejection_reason,
        )

    if not _has_actionable_place_target(search_plan, place_intent_frame):
        search_plan, place_intent_frame = _sync_decision_to_plan(
            search_plan,
            place_intent_frame,
            "out_of_scope",
            reason="missing_place_seeking_frame_evidence",
            message="생활 장소 추천으로 이어질 대상 근거가 부족해 검색을 실행하지 않았습니다.",
        )
        return _empty_decision_gate_response(
            "out_of_scope",
            search_plan,
            place_intent_frame,
            ai_debug={
                "ai_search_execution_gate": {
                    "status": "blocked_by_missing_place_target_evidence",
                    "reason": "missing_place_seeking_frame_evidence",
                },
            },
        )

    parsed = {
        "scenario": place_intent_frame.get("situation") or search_plan.get("scenario") or "custom",
        "situation_summary": place_intent_frame.get("display_label") or query,
        "is_searchable": True,
        "parser_provider": search_plan.get("parser_provider") or "frame",
        "parser_fallback": bool(search_plan.get("parser_fallback") or search_plan.get("parserFallback")),
        "plan_source": search_plan.get("plan_source") or search_plan.get("planSource") or "ai",
        "execution_mode": "frame",
        "search_plan": search_plan,
        "place_intent_frame": place_intent_frame,
    }
    data = run_unified_candidate_search(
        parsed,
        query=query,
        original_query=original_query or query,
        lat=lat,
        lng=lng,
        limit=limit,
        radius=radius,
        user=user,
        search_plan=search_plan,
        frame=place_intent_frame,
    )
    data["ai_parse"] = parsed
    data["ai_web_search"] = get_ai_web_search_status()
    data["execution_mode"] = data.get("execution_mode") or parsed.get("execution_mode") or "frame"
    data["plan_source"] = data.get("plan_source") or parsed.get("plan_source") or "ai"
    return Response(data)


@api_view(["POST"])
def ai_recommendation_search(request):
    user = request.user if request.user.is_authenticated else None
    return Response(run_ai_search(request.data, user=user))


@api_view(["POST"])
def ai_web_search(request):
    query = request.data.get("query", "")
    lat = request.data.get("lat")
    lng = request.data.get("lng")
    location_hint = request.data.get("location_hint", "")
    search_plan = request.data.get("search_plan") or {}
    condition = request.data.get("condition") or {}
    existing_results_summary = request.data.get("existing_results_summary") or {}

    data = get_ai_web_search_result(
        query=query,
        lat=lat,
        lng=lng,
        location_hint=location_hint,
        search_plan=search_plan,
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
