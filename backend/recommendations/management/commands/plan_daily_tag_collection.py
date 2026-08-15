import math
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from recommendations.models import Place, PlaceTagCollectionJob
from recommendations.services.place_tag_collection import (
    COLLECTION_PROFILES,
    planned_requests_for_category,
    requested_tags_for_category,
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
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        cycle_date = timezone.localdate()
        if options["date"]:
            cycle_date = date.fromisoformat(options["date"])
        stats = plan_daily_jobs(
            cycle_date=cycle_date,
            place_limit=options["limit"] or settings.TAG_COLLECTION_DAILY_PLACE_LIMIT,
            provider=options["provider"],
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


def plan_daily_jobs(*, cycle_date, place_limit, provider="naver_search", dry_run=False):
    place_limit = max(1, int(place_limit))
    budget = math.floor(
        settings.TAG_COLLECTION_DAILY_API_LIMIT
        * settings.TAG_COLLECTION_QUOTA_PERCENT
        / 100
    )
    recent_cutoff = cycle_date - timedelta(days=settings.TAG_COLLECTION_REVISIT_DAYS)
    recent_place_ids = PlaceTagCollectionJob.objects.filter(
        provider=provider,
        cycle_date__gte=recent_cutoff,
        status__in=("queued", "processing", "completed", "retry"),
    ).values_list("place_id", flat=True)
    categories = tuple(COLLECTION_PROFILES)
    per_stratum = max(2, math.ceil(place_limit / (len(REGIONS) * len(categories))) * 2)
    pools = []
    for region, aliases in REGIONS:
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
