import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from recommendations.management.commands.report_city_food_coverage import (
    percentage,
    recommendation_quality_summary,
)
from recommendations.models import Place, PlaceTagEvidence


class Command(BaseCommand):
    help = "Report the lightweight Busan cafe/restaurant evidence quality used by the launch gate."

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
    location = Q(address__startswith="부산광역시") | Q(address__startswith="부산 ")
    location |= Q(detail_location__startswith="부산광역시") | Q(detail_location__startswith="부산 ")
    categories = {}
    for category in ("cafe", "restaurant"):
        places = Place.objects.filter(location, category=category).distinct()
        total = places.count()
        evidence = PlaceTagEvidence.objects.filter(place_id__in=places.values("id"))
        active = evidence.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        levels, average_score = recommendation_quality_summary(
            active,
            category=category,
            total=total,
        )
        searchable = levels["searchable"] + levels["rich"]
        active_places = active.values("place_id").distinct().count()
        categories[category] = {
            "places": total,
            "active_evidence_places": active_places,
            "active_evidence_place_coverage_pct": percentage(active_places, total),
            "recommendation_searchable_places": searchable,
            "recommendation_searchable_coverage_pct": percentage(searchable, total),
            "recommendation_rich_places": levels["rich"],
            "recommendation_rich_coverage_pct": percentage(levels["rich"], total),
            "recommendation_quality_levels": levels,
            "average_recommendation_quality_score": average_score,
        }
    return {
        "generated_at": now.isoformat(),
        "region": "부산",
        "categories": categories,
    }
