import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence


REGIONS = {
    "인천": ("인천광역시", "인천 "), "대구": ("대구광역시", "대구 "),
    "대전": ("대전광역시", "대전 "), "광주": ("광주광역시", "광주 "),
    "울산": ("울산광역시", "울산 "),
}
TAGS = (
    "조용함", "작업하기좋음", "노트북작업", "콘센트있음", "무료와이파이",
    "혼자이용좋음", "분위기좋음", "데이트좋음", "대화하기좋음", "장기체류좋음",
)


class Command(BaseCommand):
    help = "Report Tier 2 cafe evidence and active canonical-tag coverage."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="")

    def handle(self, *args, **options):
        now = timezone.now()
        report = {"generated_at": now.isoformat(), "regions": {}}
        for region, prefixes in REGIONS.items():
            location = Q()
            for prefix in prefixes:
                location |= Q(address__startswith=prefix) | Q(detail_location__startswith=prefix)
            places = Place.objects.filter(location, category="cafe").distinct()
            place_ids = places.values_list("id", flat=True)
            evidence = PlaceTagEvidence.objects.filter(place_id__in=place_ids)
            active = evidence.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            total = places.count()
            active_places = active.values("place_id").distinct().count()
            report["regions"][region] = {
                "places": total,
                "evidence_places": evidence.values("place_id").distinct().count(),
                "active_evidence_places": active_places,
                "active_place_coverage_pct": round(active_places * 100 / total, 4) if total else 0.0,
                "tags": {
                    tag: {
                        "active_places": active.filter(tag__name=tag, polarity="positive").values("place_id").distinct().count(),
                    }
                    for tag in TAGS
                },
            }
            for row in report["regions"][region]["tags"].values():
                row["coverage_pct"] = round(row["active_places"] * 100 / total, 4) if total else 0.0
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(rendered)
        if options["output"]:
            path = Path(options["output"]).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
