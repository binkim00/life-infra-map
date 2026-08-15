import json
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence
from recommendations.services.coverage_reporting import build_coverage_report


CATEGORY_TAGS = {
    "toilet": ("장애인시설", "24시간운영", "기저귀교환대"),
    "parking": ("무료이용", "장애인전용주차", "24시간운영", "카드결제가능"),
    "city_park": ("놀이시설", "운동시설", "편의시설"),
}


class Command(BaseCommand):
    help = "Report structured Evidence coverage for toilet, parking, and city park plus Seoul/Busan readiness."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tmp/structured_evidence_coverage.json")

    def handle(self, *args, **options):
        report = build_structured_report()
        output = Path(options["output"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps({"output": str(output), **report["overall"]}, ensure_ascii=False))


def build_structured_report(now=None):
    now = now or timezone.now()
    categories = tuple(CATEGORY_TAGS)
    total_evidence = PlaceTagEvidence.objects.count()
    field_rule = PlaceTagEvidence.objects.filter(source="field_rule")
    report = {
        "generated_at": now.isoformat(),
        "overall": {
            "evidence": total_evidence,
            "field_rule_evidence": field_rule.count(),
            "places_with_evidence": PlaceTagEvidence.objects.values("place_id").distinct().count(),
        },
        "field_rule_by_tag": list(field_rule.values("tag__name").annotate(count=Count("id")).order_by("tag__name")),
        "categories": {},
    }
    for category, tags in CATEGORY_TAGS.items():
        places = Place.objects.filter(category=category)
        total_places = places.count()
        evidence = PlaceTagEvidence.objects.filter(place__category=category, tag__name__in=tags)
        active = evidence.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now),
            polarity__in=("positive", "negative"),
        )
        evidence_places = active.values("place_id").distinct().count()
        pairs = active.values("place_id", "tag_id").distinct().count()
        high = active.filter(confidence__gte=90).count()
        stale = evidence.filter(expires_at__lte=now).count()
        conflict = active.values("place_id", "tag_id").annotate(
            positive=Count("id", filter=Q(polarity="positive")),
            negative=Count("id", filter=Q(polarity="negative")),
        ).filter(positive__gt=0, negative__gt=0).count()
        report["categories"][category] = {
            "total_places": total_places,
            "evidence_places": evidence_places,
            "place_coverage": ratio(evidence_places, total_places),
            "tag_pairs": pairs,
            "tag_coverage": ratio(pairs, total_places * len(tags)),
            "high_confidence_ratio": ratio(high, active.count()),
            "stale_ratio": ratio(stale, evidence.count()),
            "conflict_ratio": ratio(conflict, pairs),
            "tags": list(active.values("tag__name").annotate(
                evidence=Count("id"), places=Count("place_id", distinct=True)
            ).order_by("tag__name")),
        }
    standard = build_coverage_report(now=now)
    report["regions"] = {
        region: standard["regions"].get(region, {})
        for region in ("서울특별시", "부산광역시")
    }
    return report


def ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else 0.0
