from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max, Min

from recommendations.models import PlaceTag, SourcePlaceRecord, TagEnrichmentRequest


SIDO_ALIASES = {
    "서울특별시": ("서울특별시", "서울"),
    "부산광역시": ("부산광역시", "부산"),
    "대구광역시": ("대구광역시", "대구"),
    "인천광역시": ("인천광역시", "인천"),
    "광주광역시": ("광주광역시", "광주"),
    "대전광역시": ("대전광역시", "대전"),
    "울산광역시": ("울산광역시", "울산"),
    "세종특별자치시": ("세종특별자치시", "세종시", "세종"),
    "경기도": ("경기도", "경기"),
    "강원특별자치도": ("강원특별자치도", "강원도", "강원"),
    "충청북도": ("충청북도", "충북"),
    "충청남도": ("충청남도", "충남"),
    "전북특별자치도": ("전북특별자치도", "전라북도", "전북"),
    "전라남도": ("전라남도", "전남"),
    "경상북도": ("경상북도", "경북"),
    "경상남도": ("경상남도", "경남"),
    "제주특별자치도": ("제주특별자치도", "제주도", "제주"),
}

CATEGORY_SOURCE_VALUES = {
    "cafe": ("cafe", "bakery"),
    "restaurant": ("restaurant", "food_service"),
    "tourism": ("tourism",),
    "city_park": ("city_park",),
}

CATEGORY_TAGS = {
    "cafe": (
        "조용함", "작업하기좋음", "노트북작업", "콘센트있음", "무료와이파이",
        "분위기좋음", "데이트좋음", "대화하기좋음", "전망좋음", "웨이팅적음",
    ),
    "restaurant": (
        "조용함", "무료와이파이", "분위기좋음", "혼밥좋음", "데이트좋음",
        "대화하기좋음", "전망좋음", "웨이팅적음",
    ),
    "tourism": (
        "조용함", "분위기좋음", "데이트좋음", "대화하기좋음", "전망좋음", "웨이팅적음",
    ),
    "city_park": (
        "조용함", "분위기좋음", "데이트좋음", "대화하기좋음", "전망좋음",
    ),
}


class Command(BaseCommand):
    help = "Build a balanced 17-sido subjective-tag queue from confirmed Kakao matches only."

    def add_arguments(self, parser):
        parser.add_argument("--per-stratum", type=int, default=5)
        parser.add_argument(
            "--categories",
            default=",".join(CATEGORY_SOURCE_VALUES),
            help="Comma-separated canonical categories.",
        )
        parser.add_argument("--tags", default="", help="Override tags for every category.")
        parser.add_argument("--priority", type=int, default=10)
        parser.add_argument("--refresh-existing", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        per_stratum = options["per_stratum"]
        if per_stratum < 1:
            raise CommandError("--per-stratum must be at least 1.")
        categories = [value.strip() for value in options["categories"].split(",") if value.strip()]
        unknown = set(categories) - set(CATEGORY_SOURCE_VALUES)
        if unknown:
            raise CommandError("Unknown categories: " + ", ".join(sorted(unknown)))
        override_tags = tuple(
            value.strip() for value in options["tags"].split(",") if value.strip()
        )

        stats = {
            "strata": 0,
            "covered_strata": 0,
            "selected_places": 0,
            "created": 0,
            "existing": 0,
            "verified_skipped": 0,
        }
        selected_place_ids = set()
        rows = []
        for sido, aliases in SIDO_ALIASES.items():
            for category in categories:
                stats["strata"] += 1
                queryset = SourcePlaceRecord.objects.filter(
                    is_active=True,
                    sido_name__in=aliases,
                    category__in=CATEGORY_SOURCE_VALUES[category],
                    kakao_match__status="confirmed",
                    normalized_place__isnull=False,
                    normalized_place__source="kakao_local",
                ).select_related("normalized_place")
                selected = evenly_spread_records(
                    queryset,
                    per_stratum,
                    excluded_place_ids=selected_place_ids,
                )
                if selected:
                    stats["covered_strata"] += 1
                for record in selected:
                    selected_place_ids.add(record.normalized_place_id)
                    rows.append((sido, category, record.normalized_place, override_tags or CATEGORY_TAGS[category]))

        stats["selected_places"] = len(rows)
        if not options["dry_run"]:
            with transaction.atomic():
                for sido, category, place, tags in rows:
                    verified = set(PlaceTag.objects.filter(
                        place=place,
                        tag__name__in=tags,
                        status="confirmed",
                        is_verified=True,
                    ).values_list("tag__name", flat=True))
                    stats["verified_skipped"] += len(verified)
                    for tag_name in set(tags) - verified:
                        request, created = TagEnrichmentRequest.objects.get_or_create(
                            place=place,
                            tag_name=tag_name,
                            defaults={
                                "priority": max(1, options["priority"]),
                                "source_query": f"nationwide sample {sido} {category}",
                                "context": {
                                    "source": "nationwide_stratified_sample",
                                    "sido": sido,
                                    "category": category,
                                },
                            },
                        )
                        if created:
                            stats["created"] += 1
                        else:
                            stats["existing"] += 1
                            if options["refresh_existing"]:
                                request.status = "queued"
                                request.priority = max(request.priority, max(1, options["priority"]))
                                request.next_attempt_at = None
                                request.error_message = ""
                                request.save(update_fields=[
                                    "status", "priority", "next_attempt_at", "error_message",
                                    "last_requested_at", "updated_at",
                                ])

        prefix = "[dry-run] " if options["dry_run"] else ""
        missing = stats["strata"] - stats["covered_strata"]
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Nationwide sample queue complete: strata={stats['strata']} "
            f"covered={stats['covered_strata']} missing={missing} "
            f"places={stats['selected_places']} created={stats['created']} "
            f"existing={stats['existing']} verified_skipped={stats['verified_skipped']}"
        ))


def evenly_spread_records(queryset, limit, *, excluded_place_ids=None):
    excluded_place_ids = set(excluded_place_ids or ())
    bounds = queryset.aggregate(min_id=Min("id"), max_id=Max("id"))
    min_id = bounds["min_id"]
    max_id = bounds["max_id"]
    if min_id is None or max_id is None:
        return []
    if limit == 1 or min_id == max_id:
        anchors = [min_id]
    else:
        span = max_id - min_id
        anchors = [round(min_id + span * index / (limit - 1)) for index in range(limit)]

    selected = []
    seen_records = set()
    for anchor in anchors:
        candidates = queryset.filter(id__gte=anchor).order_by("id")[: max(5, limit * 2)]
        for record in candidates:
            if record.id in seen_records or record.normalized_place_id in excluded_place_ids:
                continue
            selected.append(record)
            seen_records.add(record.id)
            excluded_place_ids.add(record.normalized_place_id)
            break
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for record in queryset.order_by("id")[: max(20, limit * 4)]:
            if record.id in seen_records or record.normalized_place_id in excluded_place_ids:
                continue
            selected.append(record)
            seen_records.add(record.id)
            excluded_place_ids.add(record.normalized_place_id)
            if len(selected) >= limit:
                break
    return selected
