import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Case, CharField, Count, Q, Value, When
from django.utils import timezone

from recommendations.management.commands.build_nationwide_tag_enrichment_sample import SIDO_ALIASES
from recommendations.models import (
    KakaoPlaceMatch,
    Place,
    PlaceTag,
    PlaceTagEvidence,
    SourcePlaceRecord,
    TagEnrichmentRequest,
)


class Command(BaseCommand):
    help = "Report nationwide place, source registry, Kakao match, and tag inventory."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Optional JSON output path.")

    def handle(self, *args, **options):
        report = build_inventory_report()
        payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        output = options.get("output")
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(f"Inventory written: {path}")
        else:
            self.stdout.write(payload)


def build_inventory_report():
    confirmed = KakaoPlaceMatch.objects.filter(status="confirmed")
    return {
        "generated_at": timezone.now(),
        "database_vendor": connection.vendor,
        "places": {
            "total": Place.objects.count(),
            "with_external_id": Place.objects.exclude(external_id="").count(),
            "kakao_canonical": Place.objects.filter(source="kakao_local")
            .exclude(external_id="")
            .count(),
            "categories": _group_counts(Place.objects.all(), "category"),
            "sources": _group_counts(Place.objects.all(), "source"),
            "regions": _place_region_counts(),
        },
        "source_records": {
            "total": SourcePlaceRecord.objects.count(),
            "active": SourcePlaceRecord.objects.filter(is_active=True).count(),
            "normalized": SourcePlaceRecord.objects.filter(normalized_place__isnull=False).count(),
            "datasets": _group_counts(SourcePlaceRecord.objects.all(), "source", "dataset"),
            "regions": _group_counts(SourcePlaceRecord.objects.all(), "sido_name"),
        },
        "kakao_matches": {
            "total": KakaoPlaceMatch.objects.count(),
            "statuses": _group_counts(KakaoPlaceMatch.objects.all(), "status"),
            "integrity": {
                "confirmed_without_canonical_place": confirmed.filter(canonical_place__isnull=True).count(),
                "confirmed_without_kakao_id": confirmed.filter(kakao_place_id="").count(),
                "confirmed_non_kakao_canonical": confirmed.exclude(canonical_place__source="kakao_local").count(),
                "normalized_without_confirmed_match": SourcePlaceRecord.objects.filter(
                    normalized_place__isnull=False
                ).exclude(kakao_match__status="confirmed").count(),
            },
        },
        "tags": {
            "place_tags": PlaceTag.objects.count(),
            "place_tag_statuses": _group_counts(PlaceTag.objects.all(), "status"),
            "evidence": PlaceTagEvidence.objects.count(),
            "enrichment_requests": TagEnrichmentRequest.objects.count(),
        },
    }


def _group_counts(queryset, *fields):
    rows = queryset.values(*fields).annotate(count=Count("id")).order_by(*fields)
    return [dict(row) for row in rows]


def _place_region_counts():
    whens = []
    for canonical, aliases in SIDO_ALIASES.items():
        condition = Q()
        for alias in aliases:
            condition |= Q(address__startswith=alias)
        whens.append(When(condition, then=Value(canonical)))
    rows = (
        Place.objects.annotate(
            sido=Case(*whens, default=Value("unknown"), output_field=CharField())
        )
        .values("sido")
        .annotate(count=Count("id"))
        .order_by("sido")
    )
    return [dict(row) for row in rows]
