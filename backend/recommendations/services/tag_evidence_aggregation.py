from django.db.models import Q
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence


WEB_SOURCES = {"ai_suggested", "blog_search", "naver_search"}
OFFICIAL_SOURCES = {"field_rule", "external_data", "external_api"}
AGGREGATION_SUMMARIES = (
    "Independent web evidence:",
    "Confirmed from an official source field",
)


def active_evidence(place, tag, *, now=None):
    now = now or timezone.now()
    return PlaceTagEvidence.objects.filter(place=place, tag=tag).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )


def aggregate_tag_evidence(place, tag, *, now=None, dry_run=False):
    now = now or timezone.now()
    evidence = active_evidence(place, tag, now=now)
    official_positive = evidence.filter(
        source__in=OFFICIAL_SOURCES,
        polarity="positive",
    ).order_by("-confidence", "-observed_at").first()
    official_negative = evidence.filter(
        source__in=OFFICIAL_SOURCES,
        polarity="negative",
    ).order_by("-confidence", "-observed_at").first()

    web = evidence.filter(source__in=WEB_SOURCES)
    web_positive_count = independent_count(web.filter(polarity="positive"))
    web_negative_count = independent_count(web.filter(polarity="negative"))
    web_net = web_positive_count - web_negative_count
    user_positive_count = independent_count(evidence.filter(source="user_feedback", polarity="positive"))
    user_negative_count = independent_count(evidence.filter(source="user_feedback", polarity="negative"))
    admin_positive_count = independent_count(evidence.filter(source="admin_review", polarity="positive"))
    admin_negative_count = independent_count(evidence.filter(source="admin_review", polarity="negative"))

    result = {
        "official_positive": bool(official_positive),
        "official_negative": bool(official_negative),
        "web_positive": web_positive_count,
        "web_negative": web_negative_count,
        "user_positive": user_positive_count,
        "user_negative": user_negative_count,
        "admin_positive": admin_positive_count,
        "admin_negative": admin_negative_count,
        "confirmed_source": "",
        "status": "none",
        "confidence": 0,
    }
    if official_positive and not official_negative:
        result.update(
            confirmed_source=official_positive.source,
            status="confirmed",
            confidence=max(80, official_positive.confidence),
        )
    elif (
        not official_negative
        and admin_positive_count > admin_negative_count
        and web_positive_count >= 1
        and web_net > 0
    ):
        result.update(confirmed_source="checked", status="confirmed", confidence=90)
    elif (
        not official_negative
        and user_positive_count > user_negative_count
        and web_positive_count >= 3
        and web_net > 0
    ):
        result.update(confirmed_source="user_verified", status="confirmed", confidence=85)
    elif web_positive_count:
        result.update(
            status="candidate",
            confidence=max(35, min(75, 40 + web_positive_count * 10 - web_negative_count * 8)),
        )
    elif official_negative or web_negative_count >= 3:
        result.update(status="rejected", confidence=min(75, 40 + web_negative_count * 10))

    if dry_run:
        return result

    materialize_web_candidate(place, tag, web, result, now=now)
    clear_stale_aggregate_confirmations(
        place,
        tag,
        keep_source=result["confirmed_source"] if result["status"] == "confirmed" else "",
    )
    if result["status"] == "confirmed":
        summary = confirmation_summary(result)
        PlaceTag.objects.update_or_create(
            place=place,
            tag=tag,
            source=result["confirmed_source"],
            defaults={
                "status": "confirmed",
                "confidence": result["confidence"],
                "evidence": summary,
                "is_verified": True,
                "verified_at": now,
            },
        )
    elif official_negative:
        PlaceTag.objects.update_or_create(
            place=place,
            tag=tag,
            source=official_negative.source,
            defaults={
                "status": "rejected",
                "confidence": max(70, official_negative.confidence),
                "evidence": official_negative.evidence,
                "is_verified": False,
                "verified_at": None,
            },
        )
    return result


def clear_stale_aggregate_confirmations(place, tag, *, keep_source):
    rows = PlaceTag.objects.filter(place=place, tag=tag, is_verified=True)
    marker = Q()
    for prefix in AGGREGATION_SUMMARIES:
        marker |= Q(evidence__startswith=prefix)
    rows = rows.filter(marker)
    if keep_source:
        rows = rows.exclude(source=keep_source)
    rows.delete()


def independent_count(queryset):
    return queryset.exclude(source_reference="").values("source_reference").distinct().count()


def materialize_web_candidate(place, tag, web, result, *, now):
    if result["web_positive"]:
        summary = web.filter(polarity="positive").order_by("-observed_at").values_list(
            "evidence", flat=True
        ).first() or ""
        PlaceTag.objects.update_or_create(
            place=place,
            tag=tag,
            source="ai_suggested",
            defaults={
                "status": "candidate",
                "confidence": max(35, min(75, 40 + result["web_positive"] * 10 - result["web_negative"] * 8)),
                "evidence": summary,
                "is_verified": False,
                "verified_at": None,
            },
        )
    elif result["web_negative"] >= 3:
        PlaceTag.objects.update_or_create(
            place=place,
            tag=tag,
            source="ai_suggested",
            defaults={
                "status": "rejected",
                "confidence": min(75, 40 + result["web_negative"] * 10),
                "evidence": "Independent negative web evidence",
                "is_verified": False,
                "verified_at": None,
            },
        )
    else:
        PlaceTag.objects.filter(place=place, tag=tag, source="ai_suggested").delete()


def confirmation_summary(result):
    if result["official_positive"]:
        return "Confirmed from an official source field"
    return (
        f"Independent web evidence: +{result['web_positive']}/-{result['web_negative']}; "
        f"user: +{result['user_positive']}/-{result['user_negative']}; "
        f"admin: +{result['admin_positive']}/-{result['admin_negative']}"
    )
