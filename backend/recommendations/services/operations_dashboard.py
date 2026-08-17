from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.db.models import Case, CharField, Count, Max, Q, Value, When
from django.db.models.functions import Cast, Concat, TruncDate
from django.utils import timezone

from recommendations.models import (
    Place,
    PlaceFeatureDocument,
    PlaceTag,
    PlaceTagCollectionJob,
    PlaceTagEvidence,
    OperationsDashboardSnapshot,
    ProviderQuotaUsage,
)
from recommendations.services.place_tag_collection import requested_tags_for_category
from recommendations.services.tag_source_policy import OFFICIAL_EVIDENCE_SOURCES


REGIONS = ("서울", "부산", "인천", "대구", "대전", "광주", "울산")
CATEGORIES = (
    "cafe", "restaurant", "toilet", "parking", "city_park",
    "shelter", "library", "tourism", "freewifi",
)
CAFE_TAGS = (
    "조용함", "작업하기좋음", "노트북작업", "콘센트있음", "무료와이파이",
    "혼자이용좋음", "분위기좋음", "데이트좋음", "대화하기좋음", "장기체류좋음",
)
RESTAURANT_TAGS = ("혼밥좋음", "분위기좋음", "데이트좋음", "대화하기좋음", "웨이팅적음")


def _active_filter(now):
    return Q(expires_at__isnull=True) | Q(expires_at__gt=now)


def _region_filter(region, prefix=""):
    return Q(**{f"{prefix}address__startswith": region}) | Q(
        **{f"{prefix}detail_location__startswith": region}
    )


def _scope(qs, *, region="", category="", place_prefix=""):
    if region:
        qs = qs.filter(_region_filter(region, place_prefix))
    if category:
        qs = qs.filter(**{f"{place_prefix}category": category})
    return qs


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else 0.0


def _int(value):
    return int(value or 0)


def _region_case(prefix=""):
    return Case(
        *[
            When(_region_filter(region, prefix), then=Value(region))
            for region in REGIONS
        ],
        default=Value("기타"),
        output_field=CharField(),
    )


def _job_strategy_rows(start_date, end_date):
    totals = defaultdict(Counter)
    jobs = PlaceTagCollectionJob.objects.filter(
        cycle_date__gte=start_date,
        cycle_date__lte=end_date,
    ).only("place_id", "status", "context", "stats", "error_code")
    for job in jobs.iterator(chunk_size=1000):
        context = job.context or {}
        targeted = context.get("targeted_metrics") or {}
        if targeted:
            for strategy, metrics in targeted.items():
                if context.get("source") == "targeted_evidence_validation":
                    strategy = f"{strategy}_diagnostic"
                row = totals[strategy]
                row["jobs"] += 1
                row["places"] += 1
                row["calls"] += _int(metrics.get("calls"))
                row["evidence"] += _int(metrics.get("evidence"))
                row["active"] += _int(metrics.get("active_evidence"))
                row["failures"] += _int(metrics.get("failures"))
                row["rate_limited"] += _int(metrics.get("rate_limited"))
            continue

        strategy = context.get("budget_bucket") or "unclassified"
        stats = job.stats or {}
        row = totals[strategy]
        row["jobs"] += 1
        row["places"] += 1
        row["calls"] += _int(stats.get("requests"))
        row["evidence"] += _int(stats.get("new_evidences"))
        row["active"] += _int(stats.get("new_active_evidences"))
        if "new_place_tags" in stats:
            row["place_tags"] += _int(stats.get("new_place_tags"))
            row["place_tags_measured"] += 1
        row["failures"] += int(bool(job.error_code and job.error_code != "insufficient_evidence"))
        row["rate_limited"] += int(job.error_code == "rate_limited")

    return [
        {
            "strategy": strategy,
            **dict(row),
            "evidence_per_call": _ratio(row["evidence"], row["calls"]),
            "active_per_call": _ratio(row["active"], row["calls"]),
            "place_tags": row["place_tags"] if row["place_tags_measured"] else None,
            "place_tag_per_call": _ratio(row["place_tags"], row["calls"]) if row["place_tags_measured"] else None,
        }
        for strategy, row in sorted(totals.items())
    ]


def _provider_rows(start_date, end_date):
    rows = []
    for provider in ("naver_search", "openai_evidence"):
        items = list(ProviderQuotaUsage.objects.filter(
            provider=provider,
            usage_date__gte=start_date,
            usage_date__lte=end_date,
        ).order_by("usage_date").values())
        totals = Counter()
        token_totals = Counter()
        cost_micro_usd = 0
        grounded = invalid = stored = active = 0
        for item in items:
            totals["calls"] += item["request_count"]
            totals["success"] += item["success_count"]
            totals["failures"] += item["failed_count"]
            totals["rate_limited"] += item["rate_limited_count"]
            metadata = item.get("metadata") or {}
            usage = metadata.get("usage") or metadata.get("token_usage") or metadata
            token_totals["input"] += _int(usage.get("input_tokens"))
            token_totals["output"] += _int(usage.get("output_tokens"))
            token_totals["total"] += _int(usage.get("total_tokens"))
            if metadata.get("estimated_cost_micro_usd") is not None:
                cost_micro_usd += _int(metadata.get("estimated_cost_micro_usd"))
            elif metadata.get("estimated_cost_usd") is not None:
                cost_micro_usd += round(float(metadata.get("estimated_cost_usd")) * 1_000_000)
            grounded += _int(metadata.get("grounded"))
            invalid += _int(metadata.get("invalid"))
            stored += _int(metadata.get("stored"))
            active += _int(metadata.get("active"))
        today_item = items[-1] if items and items[-1]["usage_date"] == end_date else None
        daily_limit = (today_item or {}).get("daily_limit") or (
            settings.TAG_COLLECTION_DAILY_API_LIMIT if provider == "naver_search" else 0
        )
        safe_limit = daily_limit * getattr(settings, "TAG_COLLECTION_QUOTA_PERCENT", 90) // 100
        if provider == "openai_evidence":
            ai_jobs = PlaceTagCollectionJob.objects.filter(
                cycle_date__gte=start_date, cycle_date__lte=end_date,
                stats__ai_calls__gt=0,
            ).values_list("stats", flat=True)
            for stats in ai_jobs:
                metrics = (stats or {}).get("ai_metrics") or {}
                grounded += _int(metrics.get("grounded"))
                invalid += _int(metrics.get("invalid"))
            ai_evidence = PlaceTagEvidence.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                context__extraction__method="ai",
            )
            stored = ai_evidence.count()
            active = ai_evidence.filter(_active_filter(timezone.now())).count()
        rows.append({
            "provider": provider,
            "calls": totals["calls"],
            "success": totals["success"],
            "failures": totals["failures"],
            "rate_limited": totals["rate_limited"],
            "daily_limit": daily_limit,
            "safe_limit": safe_limit,
            "today_usage_rate": _ratio((today_item or {}).get("request_count", 0), daily_limit),
            "input_tokens": token_totals["input"] or None,
            "output_tokens": token_totals["output"] or None,
            "total_tokens": token_totals["total"] or None,
            "estimated_cost_usd": round(cost_micro_usd / 1_000_000, 8) if cost_micro_usd else None,
            "grounded": grounded,
            "invalid": invalid,
            "stored": stored,
            "active": active,
        })
    return rows


def _growth_rows(start, end, now, evidence, place_tags):
    evidence_rows = {
        row["day"]: row
        for row in evidence.filter(created_at__gte=start, created_at__lt=end)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            evidence=Count("id"),
            active=Count("id", filter=_active_filter(now)),
            evidence_places=Count("place_id", distinct=True),
        )
    }
    tag_rows = {
        row["day"]: row["place_tags"]
        for row in place_tags.filter(created_at__gte=start, created_at__lt=end)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(place_tags=Count("id"))
    }
    day = timezone.localdate(start)
    last = timezone.localdate(end - timedelta(microseconds=1))
    rows = []
    while day <= last:
        evidence_row = evidence_rows.get(day, {})
        rows.append({
            "date": day.isoformat(),
            "new_evidence": _int(evidence_row.get("evidence")),
            "new_active_evidence": _int(evidence_row.get("active")),
            "evidence_places": _int(evidence_row.get("evidence_places")),
            "new_place_tags": _int(tag_rows.get(day)),
        })
        day += timedelta(days=1)
    return rows


def _coverage_rows(*, axis, region="", category="", now):
    if axis == "region":
        place_qs = _scope(Place.objects.all(), category=category).annotate(group=_region_case())
        evidence_qs = _scope(PlaceTagEvidence.objects.all(), category=category, place_prefix="place__").annotate(group=_region_case("place__"))
        tag_qs = _scope(PlaceTag.objects.all(), category=category, place_prefix="place__").annotate(group=_region_case("place__"))
        groups = REGIONS
    else:
        place_qs = _scope(Place.objects.filter(category__in=CATEGORIES), region=region).annotate(group=Value(""))
        evidence_qs = _scope(PlaceTagEvidence.objects.filter(place__category__in=CATEGORIES), region=region, place_prefix="place__").annotate(group=Value(""))
        tag_qs = _scope(PlaceTag.objects.filter(place__category__in=CATEGORIES), region=region, place_prefix="place__").annotate(group=Value(""))
        groups = CATEGORIES

    place_values = ("group",) if axis == "region" else ("category",)
    evidence_values = ("group",) if axis == "region" else ("place__category",)
    tag_values = ("group",) if axis == "region" else ("place__category",)
    totals = {
        (row.get("group") if axis == "region" else row.get("category")): row["count"]
        for row in place_qs.values(*place_values).annotate(count=Count("id"))
    }
    evidence_stats = {
        (row.get("group") if axis == "region" else row.get("place__category")): row
        for row in evidence_qs.values(*evidence_values).annotate(
            evidence=Count("id"),
            evidence_places=Count("place_id", distinct=True),
            active_places=Count("place_id", distinct=True, filter=_active_filter(now)),
            active_evidence=Count("id", filter=_active_filter(now)),
            stale=Count("id", filter=Q(expires_at__lte=now)),
        )
    }
    tag_stats = {
        (row.get("group") if axis == "region" else row.get("place__category")): row
        for row in tag_qs.values(*tag_values).annotate(
            tags=Count("id"),
            high=Count("id", filter=Q(confidence__gte=70)),
            conflicts=Count("id", filter=Q(status="needs_verification")),
        )
    }
    relevant_tags = {
        tag for category in CATEGORIES for tag in requested_tags_for_category(category)
    }
    pair_expression = Concat(
        Cast("place_id", output_field=CharField()),
        Value(":"),
        Cast("tag_id", output_field=CharField()),
    )
    active_pair_stats = {
        (row["region"], row["place__category"]): row["pairs"]
        for row in PlaceTagEvidence.objects.filter(
            _active_filter(now), polarity="positive",
            place__category__in=CATEGORIES, tag__name__in=relevant_tags,
        ).annotate(region=_region_case("place__")).values("region", "place__category").annotate(
            pairs=Count(pair_expression, distinct=True),
        )
    }
    rows = []
    for group in groups:
        total = totals.get(group, 0)
        ev = evidence_stats.get(group, {})
        tags = tag_stats.get(group, {})
        active_places = _int(ev.get("active_places"))
        place_coverage = _ratio(active_places, total)
        rows.append({
            axis: group,
            "places": total,
            "evidence_places": _int(ev.get("evidence_places")),
            "active_evidence_places": active_places,
            "place_coverage": place_coverage,
            "tag_coverage": None,
            "stale_ratio": _ratio(_int(ev.get("stale")), _int(ev.get("evidence"))),
            "high_confidence_ratio": _ratio(_int(tags.get("high")), _int(tags.get("tags"))),
            "conflict": _int(tags.get("conflicts")),
            "active_pairs": _int(active_pair_stats.get((region, category))),
            "possible_pairs": total * len(requested_tags_for_category(category)),
            "readiness": "PARTIAL" if place_coverage >= 0.1 else "NEEDS_ENRICHMENT",
        })
    return rows


def _tag_coverage(regions, category, start, now):
    tags = CAFE_TAGS if category == "cafe" else RESTAURANT_TAGS if category == "restaurant" else requested_tags_for_category(category)
    place_counts = {
        row["region"]: row["count"]
        for row in Place.objects.filter(category=category).annotate(region=_region_case()).values("region").annotate(count=Count("id"))
    }
    active = PlaceTagEvidence.objects.filter(
        _active_filter(now), polarity="positive", place__category=category, tag__name__in=tags,
    ).annotate(region=_region_case("place__"))
    current = {
        (row["region"], row["tag__name"]): row["count"]
        for row in active.values("region", "tag__name").annotate(count=Count("place_id", distinct=True))
    }
    recent = {
        (row["region"], row["tag__name"]): row["count"]
        for row in active.filter(created_at__gte=start).values("region", "tag__name").annotate(count=Count("place_id", distinct=True))
    }
    return {
        region: [
            {
                "tag": tag,
                "active_places": current.get((region, tag), 0),
                "coverage": _ratio(current.get((region, tag), 0), place_counts.get(region, 0)),
                "period_increase": recent.get((region, tag), 0),
            }
            for tag in tags
        ]
        for region in regions
    }


def build_coverage_snapshot(*, now=None):
    now = now or timezone.now()
    snapshot_end = timezone.make_aware(
        timezone.datetime.combine(
            timezone.localdate(now) + timedelta(days=1), timezone.datetime.min.time()
        )
    )
    growth_start = snapshot_end - timedelta(days=30)
    places = Place.objects.filter(category__in=CATEGORIES).annotate(region=_region_case())
    evidence = PlaceTagEvidence.objects.filter(place__category__in=CATEGORIES).annotate(region=_region_case("place__"))
    place_tags = PlaceTag.objects.filter(place__category__in=CATEGORIES).annotate(region=_region_case("place__"))
    keys = [(region, category) for region in REGIONS for category in CATEGORIES]
    totals = {
        (row["region"], row["category"]): row["count"]
        for row in places.values("region", "category").annotate(count=Count("id"))
    }
    evidence_stats = {
        (row["region"], row["place__category"]): row
        for row in evidence.values("region", "place__category").annotate(
            evidence=Count("id"),
            evidence_places=Count("place_id", distinct=True),
            active_places=Count("place_id", distinct=True, filter=_active_filter(now)),
            active_evidence=Count("id", filter=_active_filter(now)),
            stale=Count("id", filter=Q(expires_at__lte=now)),
        )
    }
    tag_stats = {
        (row["region"], row["place__category"]): row
        for row in place_tags.values("region", "place__category").annotate(
            tags=Count("id"),
            high=Count("id", filter=Q(confidence__gte=70)),
            conflicts=Count("id", filter=Q(status="needs_verification")),
        )
    }
    cells = {}
    for region, category in keys:
        total = totals.get((region, category), 0)
        ev = evidence_stats.get((region, category), {})
        tags = tag_stats.get((region, category), {})
        active_places = _int(ev.get("active_places"))
        cells[f"{region}/{category}"] = {
            "region": region,
            "category": category,
            "places": total,
            "evidence_places": _int(ev.get("evidence_places")),
            "active_evidence_places": active_places,
            "evidence": _int(ev.get("evidence")),
            "active_evidence": _int(ev.get("active_evidence")),
            "stale": _int(ev.get("stale")),
            "tags": _int(tags.get("tags")),
            "high": _int(tags.get("high")),
            "conflict": _int(tags.get("conflicts")),
        }

    all_tags = set(CAFE_TAGS) | set(RESTAURANT_TAGS)
    active = PlaceTagEvidence.objects.filter(
        _active_filter(now), polarity="positive",
        place__category__in=("cafe", "restaurant"), tag__name__in=all_tags,
    ).annotate(region=_region_case("place__"))
    tag_counts = {
        (row["region"], row["place__category"], row["tag__name"]): row["count"]
        for row in active.values("region", "place__category", "tag__name").annotate(count=Count("place_id", distinct=True))
    }
    latest_dates = {
        row["category"]: row["latest"]
        for row in Place.objects.filter(category__in=CATEGORIES)
        .values("category").annotate(latest=Max("source_updated_at"))
    }
    official = {
        row["place__category"]: row
        for row in PlaceTagEvidence.objects.filter(
            place__category__in=CATEGORIES,
            source__in=OFFICIAL_EVIDENCE_SOURCES,
        ).values("place__category").annotate(
            current=Count("id", filter=_active_filter(now)),
            stale=Count("id", filter=Q(expires_at__lte=now)),
        )
    }
    source_freshness = []
    for category in ("toilet", "parking", "city_park", "shelter", "library", "tourism", "freewifi"):
        row = official.get(category, {})
        current = _int(row.get("current"))
        stale = _int(row.get("stale"))
        source_freshness.append({
            "source": category,
            "latest_source_date": latest_dates.get(category).isoformat() if latest_dates.get(category) else None,
            "current_evidence": current,
            "stale_evidence": stale,
            "stale_ratio": _ratio(stale, current + stale),
            "refresh_needed": stale > current,
        })
    global_totals = {
        "places": Place.objects.count(),
        "place_tags": PlaceTag.objects.count(),
        "evidence": PlaceTagEvidence.objects.count(),
        "active_evidence": PlaceTagEvidence.objects.filter(_active_filter(now)).count(),
        "stale_evidence": PlaceTagEvidence.objects.filter(expires_at__lte=now).count(),
        "evidence_places": PlaceTagEvidence.objects.values("place_id").distinct().count(),
    }
    growth_30 = _growth_rows(
        growth_start, snapshot_end, now,
        PlaceTagEvidence.objects.all(), PlaceTag.objects.all(),
    )
    active_tag_daily = list(
        PlaceTagEvidence.objects.filter(
            _active_filter(now), polarity="positive", created_at__gte=growth_start,
        ).annotate(day=TruncDate("created_at")).values("day", "tag__name").annotate(count=Count("id"))
    )
    period_summaries = {}
    top_tags_by_days = {}
    for days in (1, 7, 30):
        start_date = timezone.localdate(snapshot_end - timedelta(days=days))
        rows = [row for row in growth_30 if row["date"] >= start_date.isoformat()]
        period_summaries[str(days)] = {
            "new_evidence": sum(row["new_evidence"] for row in rows),
            "new_active_evidence": sum(row["new_active_evidence"] for row in rows),
            "new_place_tags": sum(row["new_place_tags"] for row in rows),
            "evidence_places": PlaceTagEvidence.objects.filter(
                created_at__gte=snapshot_end - timedelta(days=days),
                created_at__lt=snapshot_end,
            ).values("place_id").distinct().count(),
        }
        tag_counter = Counter()
        for row in active_tag_daily:
            if row["day"] >= start_date:
                tag_counter[row["tag__name"]] += row["count"]
        top_tags_by_days[str(days)] = [
            {"tag": tag, "count": count}
            for tag, count in tag_counter.most_common(10)
        ]
    return {
        "generated_at": now.isoformat(),
        "cells": cells,
        "tag_counts": {"|".join(key): count for key, count in tag_counts.items()},
        "source_freshness": source_freshness,
        "global_totals": global_totals,
        "growth_30": growth_30,
        "period_summaries": period_summaries,
        "top_tags_by_days": top_tags_by_days,
    }


def refresh_operations_snapshot(*, now=None):
    now = now or timezone.now()
    payload = build_coverage_snapshot(now=now)
    snapshot, _ = OperationsDashboardSnapshot.objects.update_or_create(
        snapshot_date=timezone.localdate(now),
        defaults={"payload": payload},
    )
    return snapshot


def _summary_from_snapshot(snapshot, *, region="", category=""):
    cells = list((snapshot.get("cells") or {}).values())
    if region:
        cells = [row for row in cells if row["region"] == region]
    if category:
        cells = [row for row in cells if row["category"] == category]

    def aggregate(rows, key):
        grouped = defaultdict(Counter)
        for row in rows:
            target = grouped[row[key]]
            for field in ("places", "evidence_places", "active_evidence_places", "evidence", "active_evidence", "stale", "tags", "high", "conflict", "active_pairs", "possible_pairs"):
                target[field] += _int(row.get(field))
        output = []
        for value, row in grouped.items():
            place_coverage = _ratio(row["active_evidence_places"], row["places"])
            output.append({
                key: value,
                "places": row["places"],
                "evidence_places": row["evidence_places"],
                "active_evidence_places": row["active_evidence_places"],
                "place_coverage": place_coverage,
                "tag_coverage": _ratio(row["active_pairs"], row["possible_pairs"]),
                "stale_ratio": _ratio(row["stale"], row["evidence"]),
                "high_confidence_ratio": _ratio(row["high"], row["tags"]),
                "conflict": row["conflict"],
                "readiness": (
                    "READY" if place_coverage >= 0.2 and _ratio(row["active_pairs"], row["possible_pairs"]) >= 0.1
                    else "PARTIAL" if place_coverage >= 0.1
                    else "NEEDS_ENRICHMENT"
                ),
            })
        return sorted(output, key=lambda row: row[key])

    return aggregate(cells, "region"), aggregate(cells, "category")


def _snapshot_tag_coverage(snapshot, regions, category, start, now):
    # Snapshot counts are current; period increases stay timestamp-driven and inexpensive.
    tags = CAFE_TAGS if category == "cafe" else RESTAURANT_TAGS
    counts = snapshot.get("tag_counts") or {}
    place_counts = {
        region: _int((snapshot.get("cells") or {}).get(f"{region}/{category}", {}).get("places"))
        for region in regions
    }
    recent = PlaceTagEvidence.objects.filter(
        _active_filter(now), polarity="positive", created_at__gte=start,
        place__category=category, tag__name__in=tags,
    ).annotate(region=_region_case("place__"))
    recent_counts = {
        (row["region"], row["tag__name"]): row["count"]
        for row in recent.values("region", "tag__name").annotate(count=Count("place_id", distinct=True))
    }
    return {
        region: [{
            "tag": tag,
            "active_places": _int(counts.get(f"{region}|{category}|{tag}")),
            "coverage": _ratio(_int(counts.get(f"{region}|{category}|{tag}")), place_counts[region]),
            "period_increase": _int(recent_counts.get((region, tag))),
        } for tag in tags]
        for region in regions
    }


def build_operations_dashboard(*, days=1, region="", category="", now=None):
    if days not in {1, 7, 30}:
        raise ValueError("days must be one of 1, 7, or 30")
    if region and region not in REGIONS:
        raise ValueError("unsupported region")
    if category and category not in CATEGORIES:
        raise ValueError("unsupported category")

    now = now or timezone.now()
    end = timezone.make_aware(timezone.datetime.combine(timezone.localdate(now) + timedelta(days=1), timezone.datetime.min.time()))
    start = end - timedelta(days=days)
    start_date = timezone.localdate(start)
    end_date = timezone.localdate(now)

    evidence = _scope(PlaceTagEvidence.objects.all(), region=region, category=category, place_prefix="place__")
    place_tags = _scope(PlaceTag.objects.all(), region=region, category=category, place_prefix="place__")
    places = _scope(Place.objects.all(), region=region, category=category)
    period_evidence = evidence.filter(created_at__gte=start, created_at__lt=end)
    period_tags = place_tags.filter(created_at__gte=start, created_at__lt=end)

    processed_places = PlaceTagCollectionJob.objects.filter(
            cycle_date__gte=start_date, cycle_date__lte=end_date, status="completed",
        ).values("place_id").distinct().count()
    snapshot_row = OperationsDashboardSnapshot.objects.order_by("-snapshot_date").first()
    snapshot = snapshot_row.payload if snapshot_row else build_coverage_snapshot(now=now)
    if not region and not category and snapshot.get("period_summaries"):
        period = {
            "processed_places": processed_places,
            **snapshot["period_summaries"][str(days)],
        }
        growth = [
            row for row in snapshot.get("growth_30", [])
            if row["date"] >= start_date.isoformat()
        ]
        top_tags = snapshot.get("top_tags_by_days", {}).get(str(days), [])
    else:
        period = {
            "processed_places": processed_places,
            "new_evidence": period_evidence.count(),
            "new_active_evidence": period_evidence.filter(_active_filter(now)).count(),
            "new_place_tags": period_tags.count(),
            "evidence_places": period_evidence.values("place_id").distinct().count(),
        }
        growth = _growth_rows(start, end, now, evidence, place_tags)
        top_tags = [
            {"tag": row["tag__name"], "count": row["count"]}
            for row in period_evidence.filter(_active_filter(now), polarity="positive")
            .values("tag__name").annotate(count=Count("id"))
            .order_by("-count", "tag__name")[:10]
        ]
    regions, categories = _summary_from_snapshot(snapshot, region=region, category=category)
    scoped_cells = list((snapshot.get("cells") or {}).values())
    if region:
        scoped_cells = [row for row in scoped_cells if row["region"] == region]
    if category:
        scoped_cells = [row for row in scoped_cells if row["category"] == category]
    cumulative = snapshot.get("global_totals") if not region and not category else {
        "places": sum(_int(row.get("places")) for row in scoped_cells),
        "place_tags": sum(_int(row.get("tags")) for row in scoped_cells),
        "evidence": sum(_int(row.get("evidence")) for row in scoped_cells),
        "active_evidence": sum(_int(row.get("active_evidence")) for row in scoped_cells),
        "stale_evidence": sum(_int(row.get("stale")) for row in scoped_cells),
        "evidence_places": sum(_int(row.get("evidence_places")) for row in scoped_cells),
    }
    tag_category = category if category in {"cafe", "restaurant"} else "cafe"
    tag_regions = (region,) if region else REGIONS
    tag_coverage = _snapshot_tag_coverage(snapshot, tag_regions, tag_category, start, now)

    queue = {
        status: PlaceTagCollectionJob.objects.filter(status=status).count()
        for status in ("queued", "processing", "retry", "failed")
    }
    queue["completed_period"] = PlaceTagCollectionJob.objects.filter(
        status="completed", cycle_date__gte=start_date, cycle_date__lte=end_date,
    ).count()
    latest_success = PlaceTagCollectionJob.objects.filter(status="completed").aggregate(value=Max("updated_at"))["value"]
    latest_created = PlaceTagCollectionJob.objects.aggregate(value=Max("created_at"))["value"]

    return {
        "generated_at": now.isoformat(),
        "filters": {"days": days, "region": region, "category": category},
        "period": period,
        "cumulative": cumulative,
        "growth": growth,
        "top_active_tags": top_tags,
        "providers": _provider_rows(start_date, end_date),
        "strategies": _job_strategy_rows(start_date, end_date),
        "regions": regions,
        "categories": categories,
        "tag_coverage_category": tag_category,
        "tag_coverage": tag_coverage,
        "queue": queue,
        "runtime": {
            "scheduler_last_planned_at": latest_created,
            "worker_last_success_at": latest_success,
            "process_health": "INFERRED_FROM_DATABASE",
        },
        "source_freshness": snapshot.get("source_freshness") or [],
        "search_performance": {"status": "NOT_AVAILABLE", "reason": "search latency is not persisted"},
        "semantic_pilot": {
            "feature_documents": PlaceFeatureDocument.objects.count(),
            "embedded_documents": PlaceFeatureDocument.objects.exclude(embedding=[]).count(),
            "model": getattr(settings, "SEMANTIC_EMBEDDING_MODEL", ""),
            "dimensions": getattr(settings, "SEMANTIC_EMBEDDING_DIMENSIONS", None),
            "retrieval_enabled": bool(getattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", False)),
            "candidate_injection_enabled": bool(
                getattr(settings, "SEMANTIC_CANDIDATE_INJECTION_ENABLED", False)
            ),
        },
    }
