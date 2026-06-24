import logging
import math

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

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
    build_conversational_search_plan,
    sync_frame_location_to_search_plan,
)
from .services.db_recommender import search_db_recommendations
from .services.place_urls import get_kakao_place_url
from .services.smoking_area_data import (
    calculate_distance_m,
    search_nearby_smoking_areas,
    map_smoking_area_to_recommendation,
)
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


def apply_place_report_approval(report):
    if report.report_type != "tag_suggestion" or not report.place or not report.suggested_tags:
        return {
            "created_place_tags": 0,
            "skipped_tags": [],
        }

    created_count = 0
    skipped_tags = []

    for tag_label in unique_valid_labels(report.suggested_tags):
        tag = Tag.objects.filter(name=tag_label).first()
        if not tag:
            skipped_tags.append(tag_label)
            continue

        if PlaceTag.objects.filter(place=report.place, tag=tag).exists():
            continue

        PlaceTag.objects.create(
            place=report.place,
            tag=tag,
            source="user_verified",
            status="confirmed",
            confidence=80,
            evidence=f"사용자 제보 #{report.id} 관리자 승인",
            is_verified=True,
            verified_at=timezone.now(),
        )
        created_count += 1

    return {
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
        if review_status == "approved":
            approval_result = apply_place_report_approval(report)

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
                "updated_at",
            ],
        )

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
            "original_query": request.data.get("original_query", ""),
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
        data["clarification_options"] = _as_request_list(
            data.get("clarification_options") or data.get("clarificationOptions") or []
        )
    elif action in {"blocked", "out_of_scope"}:
        data["type"] = action
        data["can_search_now"] = False
        data["results"] = []
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


def _empty_decision_gate_response(action, search_plan, frame):
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
    return Response({
        "scenario": action,
        "type": response_type,
        "decision_action": action,
        "decisionAction": action,
        "can_search_now": False,
        "results": [],
        "markers": [],
        "count": 0,
        "result_count": 0,
        "relevant_result_count": 0,
        "execution_policy": {
            "run_search": False,
            "preserve_explicit_location": False,
            "allow_kakao_fallback": False,
            "allow_ai_web_search_auto": False,
            "merge_ai_web_results": False,
        },
        "clarification_question": question,
        "clarification_options": options,
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
        "ai_web_search": get_ai_web_search_status(),
    })


@api_view(["POST"])
def ai_recommendation_search(request):
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

    if decision_action in {"ask_clarification", "out_of_scope", "blocked"}:
        return _empty_decision_gate_response(decision_action, search_plan, place_intent_frame)

    safety_parse = parse_situation(original_query or query)

    if safety_parse.get("blocked") or safety_parse.get("is_searchable") is False:
        return Response({
            "scenario": safety_parse.get("scenario", "blocked"),
            "results": [],
            "count": 0,
            "blocked": True,
            "reason": safety_parse.get("block_reason", "inappropriate_place_use"),
            "message": safety_parse.get(
                "user_message",
                "요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.",
            ),
            "ai_parse": safety_parse,
            "ai_web_search": get_ai_web_search_status(),
        })

    if has_valid_frame:
        parsed = {
            "scenario": search_plan.get("scenario") or place_intent_frame.get("situation") or "custom",
            "situation_summary": place_intent_frame.get("display_label") or query,
            "is_searchable": True,
            "parser_provider": search_plan.get("parser_provider") or "frame",
            "parser_fallback": False,
            "plan_source": search_plan.get("plan_source") or search_plan.get("planSource") or "ai",
            "execution_mode": "frame",
            "search_plan": search_plan,
            "place_intent_frame": place_intent_frame,
        }
    else:
        parsed = parse_situation(query)

    user = request.user if request.user.is_authenticated else None
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
        place_intent_frame=place_intent_frame,
    )
    data["ai_parse"] = parsed
    data["ai_web_search"] = get_ai_web_search_status()
    data["execution_mode"] = data.get("execution_mode") or parsed.get("execution_mode") or "legacy"
    data["plan_source"] = data.get("plan_source") or parsed.get("plan_source") or "legacy_fallback"

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
