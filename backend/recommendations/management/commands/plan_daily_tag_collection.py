import math
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from recommendations.models import Place, PlaceTagCollectionJob
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
    budget = math.floor(
        settings.TAG_COLLECTION_DAILY_API_LIMIT
        * settings.TAG_COLLECTION_QUOTA_PERCENT
        / 100
    )
    recent_cutoff = cycle_date - timedelta(days=settings.TAG_COLLECTION_REVISIT_DAYS)
    stale_place_ids = PlaceTagEvidence.objects.filter(
        expires_at__lte=timezone.now(),
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
            rows = list(Place.objects.filter(
                location,
                category=category,
            ).exclude(id__in=recent_place_ids).order_by("id")[:per_stratum])
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
    for _, aliases in regions:
        location = Q()
        for alias in aliases:
            location |= Q(address__startswith=alias)
            location |= Q(detail_location__startswith=alias)
        for category in categories:
            rows = Place.objects.filter(location, category=category).exclude(
                id__in=recent_place_ids
            ).order_by("id")[:per_stratum]
            for place in rows:
                places_by_id[place.id] = place
    places = list(places_by_id.values())
    contexts = priority_context(
        places,
        category_priorities=settings.TAG_COLLECTION_CATEGORY_PRIORITIES,
    )
    selected = weighted_tier_selection(
        [(place, contexts[place.id]) for place in places],
        limit=place_limit,
        tier_weights=parse_tier_weights(settings.TAG_COLLECTION_BOOTSTRAP_TIER_WEIGHTS),
        category_max_share=effective_category_share,
    )
    created = 0
    planned_requests = 0
    covered = set()
    for place, priority in selected:
        requests = planned_requests_for_category(place.category)
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
                        "tier": priority["tier"],
                        "priority": priority,
                        "category": place.category,
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
