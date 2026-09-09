from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import EvidenceReview, PlaceTagEvidence, TagEnrichmentRequest
from .services.tag_evidence_aggregation import aggregate_tag_evidence
from .services.tag_source_policy import WEB_EVIDENCE_SOURCES, ADMIN_EVIDENCE_SOURCE


@api_view(["GET"])
@permission_classes([IsAdminUser])
def research_audits(request):
    from .models import ResearchAudit
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        return Response({"detail": "페이지를 확인해 주세요."}, status=400)
    rows = ResearchAudit.objects.order_by("-created_at", "-id")
    count = rows.count()
    return Response({"count": count, "has_next": count > page * 5,
                     "results": [{"id": r.id, "run_key": r.run_key, "payload": r.payload}
                                 for r in rows[(page-1)*5:page*5]]})


def serialize(row):
    review = getattr(row, "review", None)
    return {
        "id": row.id, "place_id": row.place_id, "place_name": row.place.name,
        "address": row.place.address, "tag": row.tag.name, "source": row.source,
        "source_url": row.source_reference, "quote": row.evidence,
        "polarity": row.polarity, "confidence": row.confidence,
        "created_at": row.created_at, "observed_at": row.observed_at,
        "expires_at": row.expires_at, "status": review.status if review else "pending",
        "note": review.note if review else "", "history": review.history if review else [],
        "source_title": row.context.get("source_title", ""),
    }


@api_view(["GET"])
@permission_classes([IsAdminUser])
def evidence_queue(request):
    rows = PlaceTagEvidence.objects.filter(source__in=WEB_EVIDENCE_SOURCES)
    status = request.GET.get("status", "pending")
    if status == "pending":
        rows = rows.filter(Q(review__isnull=True) | Q(review__status="pending"))
    elif status in {"approved", "rejected", "research"}:
        rows = rows.filter(review__status=status)
    elif status != "all":
        return Response({"detail": "검토 상태를 확인해 주세요."}, status=400)
    source = request.GET.get("source", "")
    if source:
        rows = rows.filter(source=source)
    query = request.GET.get("q", "").strip()
    if query:
        rows = rows.filter(Q(place__name__icontains=query) | Q(tag__name__icontains=query))
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        return Response({"detail": "페이지를 확인해 주세요."}, status=400)
    count = rows.count()
    # Bound the sort before joining wide Place rows (raw source JSON can be huge).
    ids = list(rows.order_by("-created_at", "-id").values_list("id", flat=True)[(page-1)*20:page*20])
    selected = {
        row.id: row for row in PlaceTagEvidence.objects.filter(id__in=ids)
        .select_related("place", "tag", "review").defer("place__raw")
    }
    return Response({"count": count, "page": page, "has_next": count > page * 20,
                     "results": [serialize(selected[pk]) for pk in ids]})


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def evidence_review(request, evidence_id):
    if request.method == "GET":
        return Response(serialize(get_object_or_404(PlaceTagEvidence.objects.select_related("place", "tag", "review"), pk=evidence_id, source__in=WEB_EVIDENCE_SOURCES)))
    decision = request.data.get("status")
    note = str(request.data.get("note") or "").strip()
    if decision not in {"approved", "rejected", "research"} or not note:
        return Response({"detail": "검토 결과와 근거 메모를 입력해 주세요."}, status=400)
    with transaction.atomic():
        row = get_object_or_404(PlaceTagEvidence.objects.select_for_update(), pk=evidence_id, source__in=WEB_EVIDENCE_SOURCES)
        if decision == "approved" and row.expires_at and row.expires_at <= timezone.now():
            return Response({"detail": "만료된 근거입니다. 재조사가 필요합니다."}, status=400)
        review, _ = EvidenceReview.objects.get_or_create(evidence=row)
        review.status, review.note, review.reviewer = decision, note[:4000], request.user
        review.history = [*review.history, {"status": decision, "note": note[:4000], "reviewer_id": request.user.id, "at": timezone.now().isoformat()}]
        review.save()
        # Keep the original quote/source intact. A separate admin attestation
        # records human verification, with the original evidence's expiry.
        key = f"admin-review:{row.id}"
        if decision == "approved":
            PlaceTagEvidence.objects.update_or_create(evidence_key=key, defaults={
                "place": row.place, "tag": row.tag, "source": ADMIN_EVIDENCE_SOURCE,
                "source_reference": row.source_reference, "polarity": row.polarity,
                "confidence": row.confidence, "evidence": note[:4000], "user": request.user,
                "context": {"reviewed_evidence_id": row.id}, "observed_at": timezone.now(),
                "expires_at": row.expires_at,
            })
        else:
            PlaceTagEvidence.objects.filter(evidence_key=key).update(expires_at=timezone.now())
        if decision == "research":
            pending, _ = TagEnrichmentRequest.objects.get_or_create(place=row.place, tag_name=row.tag.name)
            # Do not replace a worker's active lease.
            if pending.status != "processing":
                pending.status = "queued"
                pending.next_attempt_at = None
                pending.save(update_fields=["status", "next_attempt_at", "updated_at"])
        aggregate_tag_evidence(row.place, row.tag)
    return Response({"status": decision, "message": "검토 결과를 저장했습니다."})
