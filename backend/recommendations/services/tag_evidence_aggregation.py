from django.db.models import Q
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence
from recommendations.services.tag_source_policy import (
    ADMIN_EVIDENCE_SOURCE,
    OFFICIAL_EVIDENCE_SOURCES,
    USER_EVIDENCE_SOURCE,
    WEB_AGGREGATE_SOURCE,
    WEB_EVIDENCE_SOURCES,
)

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
        source__in=OFFICIAL_EVIDENCE_SOURCES,
        polarity="positive",
    ).order_by("-confidence", "-observed_at").first()
    official_negative = evidence.filter(
        source__in=OFFICIAL_EVIDENCE_SOURCES,
        polarity="negative",
    ).order_by("-confidence", "-observed_at").first()

    web = evidence.filter(source__in=WEB_EVIDENCE_SOURCES)
    web_positive_count = independent_count(web.filter(polarity="positive"))
    web_negative_count = independent_count(web.filter(polarity="negative"))
    web_net = web_positive_count - web_negative_count
    web_quality = evidence_metrics(web, now=now)
    user_positive_count = independent_count(evidence.filter(source=USER_EVIDENCE_SOURCE, polarity="positive"))
    user_negative_count = independent_count(evidence.filter(source=USER_EVIDENCE_SOURCE, polarity="negative"))
    admin_positive_count = independent_count(evidence.filter(source=ADMIN_EVIDENCE_SOURCE, polarity="positive"))
    admin_negative_count = independent_count(evidence.filter(source=ADMIN_EVIDENCE_SOURCE, polarity="negative"))

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
        "evidence_state": "NO_EVIDENCE",
        "quality": web_quality,
        "status": "none",
        "confidence": 0,
    }
    if official_positive and not official_negative:
        result.update(
            confirmed_source=official_positive.source,
            evidence_state="POSITIVE_DOMINANT",
            status="confirmed",
            confidence=max(80, official_positive.confidence),
        )
    elif (
        not official_negative
        and admin_positive_count > admin_negative_count
        and web_positive_count >= 1
        and web_net > 0
    ):
        result.update(confirmed_source="checked", evidence_state="POSITIVE_DOMINANT", status="confirmed", confidence=90)
    elif (
        not official_negative
        and user_positive_count > user_negative_count
        and web_positive_count >= 3
        and web_net > 0
    ):
        result.update(confirmed_source="user_verified", evidence_state="POSITIVE_DOMINANT", status="confirmed", confidence=85)
    elif web_positive_count >= 2 and web_net >= 2:
        result.update(
            evidence_state="POSITIVE_DOMINANT",
            status="candidate",
            confidence=aggregate_confidence(
                "candidate", web_positive_count, web_negative_count, web_quality
            ),
        )
    elif official_negative:
        result.update(evidence_state="NEGATIVE_DOMINANT", status="rejected", confidence=max(70, official_negative.confidence))
    elif web_negative_count >= 3 and web_net <= -2:
        result.update(
            evidence_state="NEGATIVE_DOMINANT",
            status="rejected",
            confidence=aggregate_confidence(
                "rejected", web_positive_count, web_negative_count, web_quality
            ),
        )
    elif web_positive_count or web_negative_count:
        result.update(
            evidence_state=(
                "CONFLICT"
                if web_positive_count and web_negative_count
                else "POSITIVE_DOMINANT" if web_positive_count else "NEGATIVE_DOMINANT"
            ),
            status="needs_verification",
            confidence=aggregate_confidence(
                "needs_verification", web_positive_count, web_negative_count, web_quality
            ),
        )

    if dry_run:
        return result

    materialize_web_aggregate(place, tag, web, result, now=now)
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


def evidence_metrics(queryset, *, now):
    rows = list(queryset.exclude(source_reference="").order_by("-confidence", "-observed_at"))
    independent = {}
    for row in rows:
        independent.setdefault(row.source_reference, row)
    rows = list(independent.values())
    if not rows:
        return {
            "independent_urls": 0,
            "source_diversity": 0,
            "average_confidence": 0,
            "freshness": 0,
        }
    average_confidence = round(sum(row.confidence for row in rows) / len(rows), 2)
    freshness_values = []
    for row in rows:
        if not row.observed_at:
            freshness_values.append(45)
            continue
        age_days = max(0, (now - row.observed_at).days)
        freshness_values.append(100 if age_days <= 30 else 85 if age_days <= 180 else 70 if age_days <= 365 else 50)
    return {
        "independent_urls": len(rows),
        "source_diversity": len({row.source for row in rows}),
        "average_confidence": average_confidence,
        "freshness": round(sum(freshness_values) / len(freshness_values), 2),
    }


def aggregate_confidence(status, positive_count, negative_count, quality):
    average = quality["average_confidence"]
    diversity = quality["source_diversity"]
    freshness = quality["freshness"]
    if status == "candidate":
        score = (
            25 + positive_count * 8 - negative_count * 7
            + average * 0.25 + diversity * 2 + freshness * 0.08
        )
        return max(35, min(75, round(score)))
    if status == "rejected":
        score = (
            30 + negative_count * 8 - positive_count * 6
            + average * 0.20 + diversity * 2 + freshness * 0.05
        )
        return max(40, min(75, round(score)))
    conflict_penalty = 8 if positive_count and negative_count else 0
    score = (
        20 + max(positive_count, negative_count) * 6
        + average * 0.20 + diversity * 2 + freshness * 0.05 - conflict_penalty
    )
    return max(25, min(65, round(score)))


def materialize_web_aggregate(place, tag, web, result, *, now):
    if result["status"] in {"candidate", "needs_verification", "rejected"} and (
        result["web_positive"] or result["web_negative"]
    ):
        preferred_polarity = "positive" if result["web_positive"] >= result["web_negative"] else "negative"
        summary = web.filter(polarity=preferred_polarity).order_by("-observed_at").values_list(
            "evidence", flat=True
        ).first() or ""
        PlaceTag.objects.update_or_create(
            place=place,
            tag=tag,
            source=WEB_AGGREGATE_SOURCE,
            defaults={
                "status": result["status"],
                "confidence": result["confidence"],
                "evidence": summary,
                "is_verified": False,
                "verified_at": None,
            },
        )
    else:
        PlaceTag.objects.filter(place=place, tag=tag, source=WEB_AGGREGATE_SOURCE).delete()


def confirmation_summary(result):
    if result["official_positive"]:
        return "Confirmed from an official source field"
    return (
        f"Independent web evidence: +{result['web_positive']}/-{result['web_negative']}; "
        f"user: +{result['user_positive']}/-{result['user_negative']}; "
        f"admin: +{result['admin_positive']}/-{result['admin_negative']}"
    )
