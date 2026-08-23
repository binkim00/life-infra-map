import logging
import math
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from accounts.tier_notifications import (
    get_current_user_tier,
    notify_tier_upgrade_if_needed,
)
from .models import ConversationSession, Place, PlaceInteractionEvent, PlaceReport, PlaceTag, Tag, UserPreference, UserSavedPlace, UserSearchLog
from .serializers import (
    PlaceReportAdminReviewSerializer,
    PlaceReportCreateSerializer,
    PlaceReportDetailSerializer,
    PlaceReportListSerializer,
    PlaceInteractionEventSerializer,
    UserPreferenceSerializer,
    UserSavedPlaceSerializer,
    UserSearchLogListSerializer,
    UserSearchLogSerializer,
)
from .services.kakao_local import search_places_by_keyword
from .services.map_search import (
    load_places_by_ids,
    search_saved_places,
)
from .services.operations_dashboard import build_operations_dashboard
from .services.place_mapper import (
    get_saved_tag_data,
    map_kakao_place_to_recommendation,
)
from .services.tag_enrichment_queue import enqueue_tag_enrichment
from .services.ai_situation_parser import parse_situation
from .services.ai_web_search_provider import (
    get_ai_web_search_result,
)
from .services.conversational_search_planner import (
    build_conversational_search_plan,
    sync_frame_location_to_search_plan,
)
from .services.ai_search_orchestrator import run_ai_search, run_ai_search_candidates
from .services.conversation_sessions import (
    build_previous_context,
    can_access_conversation_session,
    create_conversation_session,
    persist_conversation_turn,
)
from .services.db_recommender import search_db_recommendations
from .services.place_urls import get_kakao_place_url
from .services.smoking_area_data import (
    calculate_distance_m,
    search_nearby_smoking_areas,
    map_smoking_area_to_recommendation,
)
from .services.smoking_metadata import derive_smoking_metadata, matches_smoking_filters
from .services.tag_utils import get_category_display_name
from .services.user_preferences import (
    USER_SELECTED_SOURCE,
    create_or_update_user_selected_preference,
    create_or_update_user_selected_tag_preference,
    rebuild_user_preferences,
    unique_valid_labels,
    update_user_preferences_from_search_log,
)
from .management.commands.aggregate_place_tag_interactions import (
    aggregate_place_tag_interactions,
)


logger = logging.getLogger(__name__)


class PlaceInteractionRateThrottle(SimpleRateThrottle):
    scope = 'place_interactions'
    rate = '120/minute'

    def get_cache_key(self, request, view):
        if getattr(request.user, 'is_authenticated', False):
            ident = 'user:{}'.format(request.user.pk)
        else:
            ident = 'ip:{}'.format(self.get_ident(request))
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident,
        }

SCENARIO_KEYWORDS = {
    "work_cafe": "카페",
    "waiting_place": "카페",
    "walk_healing": "공원",
    "smoking_area": "흡연구역",
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
def saved_places(request):
    if request.method == "GET":
        saved_place_queryset = (
            UserSavedPlace.objects
            .filter(user=request.user)
            .select_related("place")
            .order_by("-updated_at", "-created_at")
        )

        keyword = request.GET.get("q", "").strip()
        source = request.GET.get("source", "").strip()

        if keyword:
            saved_place_queryset = saved_place_queryset.filter(
                Q(name__icontains=keyword)
                | Q(category__icontains=keyword)
                | Q(address__icontains=keyword)
                | Q(memo__icontains=keyword)
            )

        if source:
            saved_place_queryset = saved_place_queryset.filter(source=source)

        if "limit" in request.GET and "page" not in request.GET and "page_size" not in request.GET:
            limit = parse_positive_int(request.GET.get("limit"), 20)
            limit = min(limit, 100)
            serializer = UserSavedPlaceSerializer(saved_place_queryset[:limit], many=True)
            return Response({
                "results": serializer.data,
            })

        return paginated_response(
            saved_place_queryset,
            UserSavedPlaceSerializer,
            request,
            default_page_size=10,
            max_page_size=50,
        )

    serializer = UserSavedPlaceSerializer(
        data=request.data,
        context={"request": request},
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    saved_place = serializer.save()
    response_serializer = UserSavedPlaceSerializer(saved_place)
    return Response(
        {
            "message": "saved place created" if getattr(serializer, "created", False) else "saved place updated",
            "saved_place": response_serializer.data,
        },
        status=status.HTTP_201_CREATED if getattr(serializer, "created", False) else status.HTTP_200_OK,
    )


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def saved_place_detail(request, saved_place_id):
    saved_place = get_object_or_404(
        UserSavedPlace,
        id=saved_place_id,
        user=request.user,
    )

    if request.method == "DELETE":
        saved_place.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = UserSavedPlaceSerializer(
        saved_place,
        data=request.data,
        partial=True,
        context={"request": request},
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    saved_place = serializer.save()
    return Response({
        "message": "saved place updated",
        "saved_place": UserSavedPlaceSerializer(saved_place).data,
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
def admin_operations_dashboard(request):
    try:
        days = int(request.GET.get("days", 1))
        payload = build_operations_dashboard(
            days=days,
            region=request.GET.get("region", "").strip(),
            category=request.GET.get("category", "").strip(),
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(payload)


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

    smoking = derive_smoking_metadata(place)
    if smoking:
        data["smoking"] = smoking

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


def search_saved_map_places(*, keyword="", lat=None, lng=None, radius=0, limit=30, queryset=None):
    candidates, total_count, query_info = search_saved_places(
        keyword=keyword,
        lat=lat,
        lng=lng,
        radius=radius,
        limit=limit,
        queryset=queryset,
    )

    places = load_places_by_ids([candidate["id"] for candidate in candidates])
    candidate_by_id = {candidate["id"]: candidate for candidate in candidates}

    results = []

    for place in places:
        candidate = candidate_by_id[place.id]
        result = serialize_place(place, distance=candidate["distance"])
        result["duplicate_count"] = candidate["duplicate_count"]
        results.append(result)

    return results, total_count, query_info


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
    query_info = {}
    kakao_results = []
    kakao_error = ""

    if source in {"all", "db"}:
        db_results, db_total_count, query_info = search_saved_map_places(
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

    # 저장 장소는 관련도 순서를 그대로 유지하고, 카카오 장소만 거리순으로 정렬해 뒤에 붙입니다.
    # 여기서 전체를 거리순으로 다시 정렬하면 검색어와 정확히 맞는 장소가 밀려납니다.
    if lat is not None and lng is not None:
        kakao_results = sorted(kakao_results, key=lambda place: (
            place.get("distance") is None,
            place.get("distance") if place.get("distance") is not None else 999999999,
            str(place.get("name", "")),
        ))

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
        "query_info": query_info,
        "kakao_error": kakao_error,
        "results": combined_results,
    })


@api_view(["GET"])
def place_list(request):
    keyword = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    source = request.GET.get("source", "").strip()
    status = request.GET.get("status", "").strip()
    facility_type = request.GET.get("facility_type", "").strip()
    verification = request.GET.get("verification", "").strip()
    include_stale = request.GET.get("include_stale", "").strip().lower() in {"1", "true", "yes"}
    lat = request.GET.get("lat")
    lng = request.GET.get("lng")
    bounds = {
        key: parse_optional_float(request.GET.get(key))
        for key in ("min_lat", "min_lng", "max_lat", "max_lng")
    }

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

    places = Place.objects.filter(category__in=DB_MARKER_ALLOWED_CATEGORIES)

    if category:
        places = places.filter(category=category)

    if source:
        places = places.filter(source=source)

    if status:
        places = places.filter(data_quality_status=status)

    if all(value is not None for value in bounds.values()):
        places = places.filter(
            lat__gte=bounds["min_lat"], lat__lte=bounds["max_lat"],
            lng__gte=bounds["min_lng"], lng__lte=bounds["max_lng"],
        )

    # Smoking-specific fields are evidence-derived. Fetch extra candidates before
    # applying them so stale/ashtray filters do not truncate the requested limit.
    search_limit = min(limit * 3, 300) if category == "smoking_area" else limit

    if all(value is not None for value in bounds.values()) and not keyword and lat is None and lng is None:
        # Marker-only viewport requests do not need relevance scoring or radius
        # expansion. Keep this path bounded and use the existing coordinate index.
        viewport_places = list(
            places.prefetch_related("place_tags__tag", "tag_evidence")
            .order_by("-data_quality_score", "-updated_at", "-id")[:300]
        )
        results = []
        index_by_key = {}
        for place in viewport_places:
            key = ("".join(place.name.lower().split()), round(place.lat, 3), round(place.lng, 3))
            if key in index_by_key:
                results[index_by_key[key]]["duplicate_count"] += 1
                continue
            index_by_key[key] = len(results)
            results.append({**serialize_place(place), "duplicate_count": 1})
        total_count = places.count()
        query_info = {"matched_categories": [category] if category else [], "bounds_fast_path": True}
    else:
        results, total_count, query_info = search_saved_map_places(
            keyword=keyword,
            lat=lat,
            lng=lng,
            radius=radius,
            limit=search_limit,
            queryset=places,
        )
    if category == "smoking_area":
        results = [
            row for row in results
            if matches_smoking_filters(
                row.get("smoking"), facility_type=facility_type,
                verification=verification, include_stale=include_stale,
            )
        ]
        priority = {"VERIFIED": 0, "VERIFIED_OFFICIAL": 0, "VERIFIED_FACILITY": 1, "PUBLIC_DATA": 2, "WEB_VERIFIED": 3, "UNVERIFIED": 4, "ASHTRAY_ONLY": 5}
        results.sort(key=lambda row: (
            priority.get(row["smoking"]["verification_level"], 9),
            row.get("distance") is None,
            row.get("distance", 999999999),
        ))
        results = results[:limit]
        total_count = len(results)

    viewport_request = all(value is not None for value in bounds.values())
    options = {}
    if not viewport_request:
        options = {
            "categories": list(Place.objects.filter(category__in=DB_MARKER_ALLOWED_CATEGORIES).exclude(category="").order_by("category").values_list("category", flat=True).distinct()),
            "sources": list(Place.objects.exclude(source="").order_by("source").values_list("source", flat=True).distinct()),
            "statuses": list(Place.objects.exclude(data_quality_status="").order_by("data_quality_status").values_list("data_quality_status", flat=True).distinct()),
        }

    return Response({
        "total_count": total_count,
        "count": len(results),
        "limit": limit,
        "options": options,
        "filters": {
            "q": keyword,
            "category": category,
            "source": source,
            "status": status,
            "lat": lat,
            "lng": lng,
            "radius": radius,
            **bounds,
            "facility_type": facility_type,
            "verification": verification,
            "include_stale": include_stale,
        },
        "query_info": query_info,
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


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PlaceInteractionRateThrottle])
def place_interactions(request):
    payload = request.data
    is_batch = isinstance(payload, dict) and isinstance(payload.get('events'), list)
    items = payload.get('events', []) if is_batch else [payload]
    if not items or len(items) > 50:
        return Response(
            {'detail': 'Send between 1 and 50 interaction events.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializers = [
        PlaceInteractionEventSerializer(
            data=item,
            context={'request': request},
        )
        for item in items
    ]
    errors = []
    for index, serializer in enumerate(serializers):
        if not serializer.is_valid():
            errors.append({'index': index, 'errors': serializer.errors})
    if errors:
        return Response(
            {'events': errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        events = [serializer.save() for serializer in serializers]
    feedback_events = [
        event for event in events
        if event.event_type in {'tag_confirm', 'tag_reject'} and event.place_id
    ]
    if feedback_events:
        aggregate_place_tag_interactions(
            place_ids={event.place_id for event in feedback_events},
            tag_names={event.tag_name for event in feedback_events},
        )
    queued_enrichments = enqueue_tag_enrichment(events)
    return Response(
        {
            'count': len(events),
            'event_ids': [event.id for event in events],
            'queued_enrichments': queued_enrichments,
        },
        status=status.HTTP_201_CREATED,
    )


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

EXTERNAL_SEARCH_MAX_KAKAO_QUERIES = 3


def _is_broad_place_term(term):
    compact = _compact_external_text(term)
    if not compact:
        return True
    return compact in {_compact_external_text(item) for item in AI_SEARCH_BROAD_PLACE_TERMS}


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


UNIFIED_EVIDENCE_TIER_RANKS = {
    "verified_direct": 0,
    "target_direct": 1,
    "result_direct": 2,
    "suggested_direct": 3,
    "candidate_direct": 4,
    "category_only": 5,
    "none": 6,
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


@api_view(["POST"])
def ai_recommendation_search(request):
    user = request.user if request.user.is_authenticated else None
    data = run_ai_search(request.data, user=user)
    timings = data.get("debug_pipeline") or {}
    logger.info(
        "AI search latency phase=reranked total_ms=%s planner_ms=%s retrieval_ms=%s reranker_ms=%s results=%s",
        timings.get("total_latency_ms"),
        timings.get("planner_latency_ms"),
        timings.get("retrieval_latency_ms"),
        timings.get("reranker_latency_ms"),
        len(data.get("results") or []),
    )
    return Response(data)


def _conversation_session_payload(session, *, include_turns=False):
    payload = {
        "id": str(session.id),
        "status": session.status,
        "title": session.title,
        "state": session.state,
        "version": session.version,
        "turn_count": session.turn_count,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }
    if include_turns:
        payload["turns"] = [
            {
                "sequence": turn.sequence,
                "user_query": turn.user_query,
                "action": turn.action,
                "assistant_message": turn.assistant_message,
                "result_refs": turn.result_refs,
                "created_at": turn.created_at,
            }
            for turn in session.turns.order_by("sequence")
        ]
    return payload


@api_view(["POST"])
@permission_classes([AllowAny])
def conversation_session_create(request):
    session, token = create_conversation_session(request.user)
    payload = _conversation_session_payload(session)
    if token:
        payload["conversation_token"] = token
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["GET", "DELETE"])
@permission_classes([AllowAny])
def conversation_session_detail(request, session_id):
    session = get_object_or_404(ConversationSession, pk=session_id)
    if not can_access_conversation_session(request, session):
        return Response({"detail": "Conversation session not found."}, status=status.HTTP_404_NOT_FOUND)
    if request.method == "DELETE":
        session.status = "closed"
        session.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response(_conversation_session_payload(session, include_turns=True))


@api_view(["POST"])
@permission_classes([AllowAny])
def conversation_session_turn(request, session_id):
    session = get_object_or_404(ConversationSession, pk=session_id)
    if not can_access_conversation_session(request, session):
        return Response({"detail": "Conversation session not found."}, status=status.HTTP_404_NOT_FOUND)
    if session.status != "active":
        return Response({"detail": "Conversation session is closed."}, status=status.HTTP_409_CONFLICT)
    query = str(request.data.get("query") or "").strip()
    if not query:
        return Response({"query": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)

    payload = dict(request.data)
    payload["query"] = query
    payload["previous_context"] = build_previous_context(session.state)
    expected_version = session.version
    result = run_ai_search(payload, user=request.user if request.user.is_authenticated else None)
    try:
        session = persist_conversation_turn(
            session.id,
            query=query,
            response=result,
            expected_version=expected_version,
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

    result["conversation"] = {
        "session_id": str(session.id),
        "version": session.version,
        "turn_count": session.turn_count,
    }
    return Response(result)


@api_view(["POST"])
def ai_recommendation_candidates(request):
    user = request.user if request.user.is_authenticated else None
    data = run_ai_search_candidates(request.data, user=user)
    timings = data.get("timings") or {}
    logger.info(
        "AI search latency phase=candidates total_ms=%s retrieval_ms=%s results=%s",
        timings.get("total_latency_ms"),
        timings.get("retrieval_latency_ms"),
        len(data.get("results") or []),
    )
    return Response(data)


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
