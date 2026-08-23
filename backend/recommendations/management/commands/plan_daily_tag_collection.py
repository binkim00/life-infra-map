import math
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.utils import timezone

from recommendations.models import Place, PlaceTag, PlaceTagCollectionJob, ProviderQuotaUsage
from recommendations.models import PlaceTagEvidence
from recommendations.services.place_tag_collection import (
    COLLECTION_PROFILES,
    planned_requests_for_category,
    requested_tags_for_category,
)
from recommendations.services.bootstrap_priority import (
    parse_tier_weights,
    priority_context,
    weighted_tier_selection,
)
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES
from recommendations.services.adaptive_tag_collection import adaptive_planned_requests
from recommendations.services.restaurant_collection_quality import restaurant_collection_quality
from recommendations.services.place_evidence_completeness import meaningful_tags_for_category
from recommendations.services.adaptive_budget import (
    allocate_by_request_budget,
    yield_adjusted_weights,
)


REGIONS = (
    ("서울특별시", ("서울특별시", "서울 ")),
    ("부산광역시", ("부산광역시", "부산 ")),
    ("대구광역시", ("대구광역시", "대구 ")),
    ("인천광역시", ("인천광역시", "인천 ")),
    ("광주광역시", ("광주광역시", "광주 ")),
    ("대전광역시", ("대전광역시", "대전 ")),
    ("울산광역시", ("울산광역시", "울산 ")),
    ("세종특별자치시", ("세종특별자치시", "세종 ")),
    ("경기도", ("경기도",)),
    ("강원특별자치도", ("강원특별자치도", "강원도")),
    ("충청북도", ("충청북도",)),
    ("충청남도", ("충청남도",)),
    ("전북특별자치도", ("전북특별자치도", "전라북도")),
    ("전라남도", ("전라남도",)),
    ("경상북도", ("경상북도",)),
    ("경상남도", ("경상남도",)),
    ("제주특별자치도", ("제주특별자치도", "제주도")),
)


class Command(BaseCommand):
    help = "Plan a balanced nationwide day of place-level meaningful-tag collection."

    def add_arguments(self, parser):
        parser.add_argument("--date")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--provider", default="naver_search")
        parser.add_argument("--mode", choices=("balanced", "bootstrap"), default=None)
        parser.add_argument(
            "--categories",
            default="",
            help="Optional comma-separated subset of configured collection profiles.",
        )
        parser.add_argument(
            "--regions",
            default="",
            help="Optional comma-separated subset of the configured nationwide regions.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        cycle_date = timezone.localdate()
        if options["date"]:
            cycle_date = date.fromisoformat(options["date"])
        stats = plan_daily_jobs(
            cycle_date=cycle_date,
            place_limit=options["limit"] or settings.TAG_COLLECTION_DAILY_PLACE_LIMIT,
            provider=options["provider"],
            mode=options["mode"] or settings.TAG_COLLECTION_MODE,
            categories=tuple(
                value.strip() for value in options["categories"].split(",") if value.strip()
            ) or None,
            regions=tuple(
                value.strip() for value in options["regions"].split(",") if value.strip()
            ) or None,
            dry_run=options["dry_run"],
        )
        self.stdout.write(self.style.SUCCESS(
            "{}Daily tag plan: date={} places={} requests={} strata={}".format(
                "[dry-run] " if options["dry_run"] else "",
                cycle_date,
                stats["places"],
                stats["planned_requests"],
                stats["covered_strata"],
            )
        ))


def plan_daily_jobs(
    *, cycle_date, place_limit, provider="naver_search", mode="balanced",
    categories=None, regions=None, dry_run=False,
):
    place_limit = max(1, int(place_limit))
    safe_limit = math.floor(
        settings.TAG_COLLECTION_DAILY_API_LIMIT
        * settings.TAG_COLLECTION_QUOTA_PERCENT
        / 100
    )
    usage = ProviderQuotaUsage.objects.filter(
        provider=provider, usage_date=cycle_date,
    ).values("request_count", "reserved_count").first() or {}
    queued_requests = PlaceTagCollectionJob.objects.filter(
        provider=provider,
        status__in=("queued", "retry"),
    ).aggregate(total=Sum("planned_requests"))["total"] or 0
    budget = max(
        0,
        safe_limit
        - int(usage.get("request_count") or 0)
        - int(usage.get("reserved_count") or 0)
        - int(queued_requests),
    )
    recent_cutoff = cycle_date - timedelta(days=settings.TAG_COLLECTION_REVISIT_DAYS)
    stale_place_ids = PlaceTagEvidence.objects.filter(
        expires_at__lte=timezone.now(),
        source__in=WEB_EVIDENCE_SOURCES,
    ).values_list("place_id", flat=True)
    recent_place_ids = PlaceTagCollectionJob.objects.filter(
        provider=provider,
        cycle_date__gte=recent_cutoff,
        status__in=("queued", "processing", "completed", "retry"),
    ).filter(
        Q(cycle_date=cycle_date) | ~Q(place_id__in=stale_place_ids)
    ).values_list("place_id", flat=True)
    categories = tuple(categories or COLLECTION_PROFILES)
    unknown_categories = set(categories) - set(COLLECTION_PROFILES)
    if unknown_categories:
        raise ValueError("Unknown collection categories: " + ", ".join(sorted(unknown_categories)))
    configured_regions = {name for name, _ in REGIONS}
    regions = tuple(regions or configured_regions)
    unknown_regions = set(regions) - configured_regions
    if unknown_regions:
        raise ValueError("Unknown collection regions: " + ", ".join(sorted(unknown_regions)))
    selected_regions = tuple(row for row in REGIONS if row[0] in regions)
    if mode == "bootstrap":
        return plan_bootstrap_jobs(
            cycle_date=cycle_date,
            place_limit=place_limit,
            provider=provider,
            budget=budget,
            recent_place_ids=recent_place_ids,
            categories=categories,
            regions=selected_regions,
            dry_run=dry_run,
        )
    per_stratum = max(2, math.ceil(place_limit / (len(REGIONS) * len(categories))) * 2)
    pools = []
    for region, aliases in selected_regions:
        location = Q()
        for alias in aliases:
            location |= Q(address__startswith=alias)
            location |= Q(detail_location__startswith=alias)
        for category in categories:
            candidate_limit = per_stratum * 3 if category == "restaurant" else per_stratum
            rows = list(Place.objects.filter(
                location,
                category=category,
            ).exclude(id__in=recent_place_ids).order_by("id")[:candidate_limit])
            if category == "restaurant":
                rows.sort(key=lambda place: (
                    -restaurant_collection_quality(place)["score"],
                    place.id,
                ))
                rows = rows[:per_stratum]
            if rows:
                pools.append((region, category, rows))

    created = 0
    planned_requests = 0
    covered = set()
    while pools and created < place_limit:
        remaining = []
        for region, category, rows in pools:
            if not rows or created >= place_limit:
                continue
            place = rows.pop(0)
            requests = planned_requests_for_category(category)
            if planned_requests + requests > budget:
                pools = []
                break
            if not dry_run:
                _, was_created = PlaceTagCollectionJob.objects.get_or_create(
                    place=place,
                    provider=provider,
                    cycle_date=cycle_date,
                    defaults={
                        "priority": 10,
                        "requested_tags": requested_tags_for_category(category),
                        "planned_requests": requests,
                        "context": {"region": region, "category": category, "source": "daily_nationwide_plan"},
                    },
                )
                if not was_created:
                    if rows:
                        remaining.append((region, category, rows))
                    continue
            created += 1
            planned_requests += requests
            covered.add((region, category))
            if rows:
                remaining.append((region, category, rows))
        pools = remaining
    return {"places": created, "planned_requests": planned_requests, "covered_strata": len(covered)}


def plan_bootstrap_jobs(
    *, cycle_date, place_limit, provider, budget, recent_place_ids,
    categories, regions=REGIONS, dry_run,
):
    # A nationally even pool can starve a high-value category when its records
    # are concentrated in one city (the current cafe registry is mostly Busan).
    # Fetch enough rows from one stratum to reach the configured category share,
    # while bounding the candidate pool used by priority scoring.
    effective_category_share = max(
        settings.TAG_COLLECTION_BOOTSTRAP_CATEGORY_MAX_SHARE,
        math.ceil(100 / max(1, len(categories))),
    )
    category_share = effective_category_share / 100
    # A deliberate one-region/one-category bootstrap is a bounded operational
    # batch, so its single stratum must be allowed to fill the requested limit.
    # Nationwide plans keep the 500-row cap to bound priority scoring work.
    stratum_cap = place_limit if len(regions) == 1 and len(categories) == 1 else 500
    per_stratum = max(100, min(stratum_cap, math.ceil(place_limit * category_share)))
    places_by_id = {}
    region_by_place_id = {}
    region_weights = {}
    for region_name, aliases in regions:
        location = Q()
        for alias in aliases:
            location |= Q(address__startswith=alias)
            location |= Q(detail_location__startswith=alias)
        for category in categories:
            base = Place.objects.filter(location, category=category).exclude(
                id__in=recent_place_ids
            )
            total_places = Place.objects.filter(location, category=category).count()
            meaningful_tags = meaningful_tags_for_category(category)
            active_places = PlaceTagEvidence.objects.filter(
                place__in=Place.objects.filter(location, category=category),
                tag__name__in=meaningful_tags,
                polarity__in=("positive", "negative"),
            ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).values(
                "place_id"
            ).annotate(
                meaningful_tag_count=Count("tag_id", distinct=True),
                evidence_source_count=Count("source_reference", distinct=True),
            ).filter(
                meaningful_tag_count__gte=3,
                evidence_source_count__gte=2,
            ).count()
            coverage_gap = 1 - (active_places / total_places if total_places else 0)
            region_weights[region_name] = region_weights.get(region_name, 0) + total_places * coverage_gap
            active_same_tag = PlaceTagEvidence.objects.filter(
                place_id=OuterRef("place_id"), tag_id=OuterRef("tag_id"),
            ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
            candidate_place_ids = PlaceTag.objects.filter(
                place__in=base,
                status__in=("candidate", "needs_verification"),
                tag__name__in=requested_tags_for_category(category),
            ).annotate(has_active=Exists(active_same_tag)).filter(
                has_active=False,
            ).order_by("-confidence", "place_id").values_list("place_id", flat=True)[:per_stratum]
            candidate_rows = Place.objects.filter(id__in=candidate_place_ids)
            discovery_rows = base.order_by("id")[:per_stratum]
            for place in list(candidate_rows) + list(discovery_rows):
                places_by_id[place.id] = place
                region_by_place_id[place.id] = region_name
    places = list(places_by_id.values())
    contexts = priority_context(
        places,
        category_priorities=settings.TAG_COLLECTION_CATEGORY_PRIORITIES,
    )
    for place in places:
        contexts[place.id]["region"] = region_by_place_id.get(place.id, "")
    candidates = [(place, contexts[place.id]) for place in places]
    if len(regions) > 1 and len({contexts[place.id]["tier"] for place in places}) == 1:
        selected = weighted_region_selection(candidates, limit=place_limit, region_weights=region_weights)
    else:
        selected = weighted_tier_selection(
            candidates, limit=place_limit,
            tier_weights=parse_tier_weights(settings.TAG_COLLECTION_BOOTSTRAP_TIER_WEIGHTS),
            category_max_share=effective_category_share,
        )
    history = {}
    for context, stats in PlaceTagCollectionJob.objects.filter(
        context__budget_bucket__isnull=False,
        status="completed",
    ).order_by("-id").values_list("context", "stats")[:5000]:
        bucket = (context or {}).get("budget_bucket")
        if "active_evidences" not in (stats or {}):
            continue
        row = history.setdefault(bucket, {"calls": 0, "evidence": 0, "active_evidence": 0})
        row["calls"] += int((stats or {}).get("requests") or 0)
        row["evidence"] += int((stats or {}).get("evidences") or 0)
        row["active_evidence"] += int((stats or {}).get("active_evidences") or 0)
    for context in PlaceTagCollectionJob.objects.filter(
        context__targeted_metrics__isnull=False,
    ).order_by("-id").values_list("context", flat=True)[:5000]:
        for bucket, metrics in ((context or {}).get("targeted_metrics") or {}).items():
            row = history.setdefault(bucket, {"calls": 0, "evidence": 0, "active_evidence": 0})
            row["calls"] += int((metrics or {}).get("calls") or 0)
            row["evidence"] += int((metrics or {}).get("evidence") or 0)
            row["active_evidence"] += int((metrics or {}).get("active_evidence") or 0)
    weights = yield_adjusted_weights(settings.TAG_COLLECTION_BUDGET_WEIGHTS, history)
    cycle_request_budget = min(
        budget,
        sum(adaptive_planned_requests(context["targeted_tags"]) for _, context in selected),
    )
    selected, bucket_requests = allocate_by_request_budget(
        selected,
        budget=cycle_request_budget,
        weights=weights,
        request_count=lambda context: adaptive_planned_requests(context["targeted_tags"]),
    )
    created = 0
    planned_requests = 0
    covered = set()
    for place, priority in selected:
        requests = adaptive_planned_requests(priority["targeted_tags"])
        if planned_requests + requests > budget:
            break
        if not dry_run:
            _, was_created = PlaceTagCollectionJob.objects.get_or_create(
                place=place,
                provider=provider,
                cycle_date=cycle_date,
                defaults={
                    "priority": max(1, priority["score"]),
                    "requested_tags": requested_tags_for_category(place.category),
                    "planned_requests": requests,
                    "context": {
                        "mode": "bootstrap",
                        "region": priority.get("region", ""),
                        "tier": priority["tier"],
                        "priority": priority,
                        "category": place.category,
                        "adaptive": True,
                        "targeted_tags": priority["targeted_tags"],
                        "adaptive_reason": priority["adaptive_reason"],
                        "budget_bucket": priority["budget_bucket"],
                        "budget_weights": weights,
                        "source": "daily_bootstrap_plan",
                    },
                },
            )
            if not was_created:
                continue
        created += 1
        planned_requests += requests
        covered.add((priority["tier"], place.category))
    return {"places": created, "planned_requests": planned_requests, "covered_strata": len(covered)}


def weighted_region_selection(candidates, *, limit, region_weights):
    """Allocate an explicit same-tier batch by coverage gap and registry size."""
    pools = {}
    for place, context in candidates:
        pools.setdefault(context.get("region") or "unknown", []).append((place, context))
    for rows in pools.values():
        rows.sort(key=lambda item: (-item[1]["score"], item[0].id))
    weights = {region: max(0.0, float(region_weights.get(region, 0))) for region in pools}
    total_weight = sum(weights.values()) or float(len(weights) or 1)
    quotas = {region: int(limit * (weight or 1) / total_weight) for region, weight in weights.items()}
    while sum(quotas.values()) < limit:
        region = max(
            quotas,
            key=lambda key: (weights[key] / max(1, quotas[key] + 1), len(pools[key])),
        )
        quotas[region] += 1
    selected = []
    leftovers = []
    for region, rows in pools.items():
        take = min(quotas[region], len(rows))
        selected.extend(rows[:take])
        leftovers.extend(rows[take:])
    leftovers.sort(key=lambda item: (-item[1]["score"], item[0].id))
    selected.extend(leftovers[:max(0, limit - len(selected))])
    return selected[:limit]
