import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from recommendations.models import Place, PlaceTag, PlaceTagEvidence
from recommendations.services.place_evidence_completeness import quality_profiles_for_places


REGIONS = {
    "서울": ("서울특별시", "서울 "),
    "부산": ("부산광역시", "부산 "),
}
CORE_TAGS = {
    "cafe": (
        "조용함", "작업하기좋음", "노트북작업", "콘센트있음", "무료와이파이",
        "혼자이용좋음", "분위기좋음", "데이트좋음", "대화하기좋음", "장기체류좋음",
    ),
    "restaurant": (
        "혼밥좋음", "데이트좋음", "분위기좋음", "대화하기좋음", "웨이팅적음", "혼자이용좋음",
    ),
}


class Command(BaseCommand):
    help = "Report Seoul/Busan cafe and restaurant inventory plus evidence/tag coverage."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="")

    def handle(self, *args, **options):
        report = build_report()
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(rendered)
        if options["output"]:
            path = Path(options["output"]).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")


def build_report(now=None):
    now = now or timezone.now()
    result = {"generated_at": now.isoformat(), "regions": {}}
    for region, prefixes in REGIONS.items():
        location = Q()
        for prefix in prefixes:
            location |= Q(address__startswith=prefix)
            location |= Q(detail_location__startswith=prefix)
        region_result = {}
        for category, tags in CORE_TAGS.items():
            places = Place.objects.filter(location, category=category).distinct()
            total = places.count()
            place_rows = list(places.only("id", "category"))
            quality_profiles = quality_profiles_for_places(place_rows, now=now)
            quality_levels = {
                level: sum(profile["level"] == level for profile in quality_profiles.values())
                for level in ("empty", "thin", "searchable", "rich")
            }
            searchable_places = quality_levels["searchable"] + quality_levels["rich"]
            average_quality_score = (
                round(sum(profile["score"] for profile in quality_profiles.values()) / total, 2)
                if total else 0
            )
            place_ids = places.values_list("id", flat=True)
            evidence = PlaceTagEvidence.objects.filter(place_id__in=place_ids)
            active = evidence.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            stale = evidence.filter(expires_at__lte=now)
            tag_rows = {}
            active_pair_total = 0
            for tag in tags:
                tag_evidence = evidence.filter(tag__name=tag)
                tag_active = tag_evidence.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
                active_places = tag_active.values("place_id").distinct().count()
                active_pair_total += active_places
                statuses = {
                    row["status"]: row["count"]
                    for row in PlaceTag.objects.filter(place_id__in=place_ids, tag__name=tag)
                    .values("status").annotate(count=Count("id"))
                }
                tag_rows[tag] = {
                    "active_places": active_places,
                    "active_coverage_pct": percentage(active_places, total),
                    "active_evidence": tag_active.count(),
                    "stale_evidence": tag_evidence.filter(expires_at__lte=now).count(),
                    "statuses": statuses,
                }
            region_result[category] = {
                "places": total,
                "by_source": {
                    row["source"]: row["count"]
                    for row in places.values("source").annotate(count=Count("id")).order_by("source")
                },
                "external_id_pct": percentage(places.exclude(external_id="").count(), total),
                "coordinate_pct": percentage(places.count(), total),
                "address_pct": percentage(places.exclude(address="").count(), total),
                "evidence_places": evidence.values("place_id").distinct().count(),
                "place_coverage_pct": percentage(evidence.values("place_id").distinct().count(), total),
                "legacy_any_evidence_place_coverage_pct": percentage(
                    evidence.values("place_id").distinct().count(), total
                ),
                "recommendation_searchable_places": searchable_places,
                "recommendation_searchable_coverage_pct": percentage(searchable_places, total),
                "recommendation_rich_places": quality_levels["rich"],
                "recommendation_rich_coverage_pct": percentage(quality_levels["rich"], total),
                "recommendation_quality_levels": quality_levels,
                "average_recommendation_quality_score": average_quality_score,
                "active_evidence_places": active.values("place_id").distinct().count(),
                "stale_evidence_places": stale.values("place_id").distinct().count(),
                "tag_coverage_pct": percentage(active_pair_total, total * len(tags)),
                "tags": tag_rows,
            }
        result["regions"][region] = region_result
    return result


def percentage(numerator, denominator):
    return round(numerator * 100 / denominator, 4) if denominator else 0.0

