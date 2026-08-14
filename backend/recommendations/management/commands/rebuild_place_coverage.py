from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Q

from recommendations.models import PlaceCoverage, SourcePlaceRecord


class Command(BaseCommand):
    help = "Rebuild nationwide place and tag coverage cells from staged source records."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="")
        parser.add_argument("--dataset", default="")
        parser.add_argument("--prune", action="store_true")

    def handle(self, *args, **options):
        queryset = SourcePlaceRecord.objects.all()
        if options["source"]:
            queryset = queryset.filter(source=options["source"])
        if options["dataset"]:
            queryset = queryset.filter(dataset=options["dataset"])

        groups = queryset.values(
            "administrative_code",
            "category",
            "source",
        ).annotate(
            sido_name=Max("sido_name"),
            sigungu_name=Max("sigungu_name"),
            source_record_count=Count("id"),
            active_record_count=Count("id", filter=Q(is_active=True)),
            normalized_place_count=Count("normalized_place", distinct=True),
            tagged_place_count=Count(
                "normalized_place",
                filter=Q(normalized_place__place_tags__isnull=False),
                distinct=True,
            ),
            evidence_place_count=Count(
                "normalized_place",
                filter=Q(normalized_place__tag_evidence__isnull=False),
                distinct=True,
            ),
        )

        touched_ids = []
        for group in groups.iterator():
            coverage, _ = PlaceCoverage.objects.update_or_create(
                administrative_code=group["administrative_code"],
                category=group["category"],
                source=group["source"],
                defaults={
                    "sido_name": group["sido_name"],
                    "sigungu_name": group["sigungu_name"],
                    "source_record_count": group["source_record_count"],
                    "active_record_count": group["active_record_count"],
                    "normalized_place_count": group["normalized_place_count"],
                    "tagged_place_count": group["tagged_place_count"],
                    "evidence_place_count": group["evidence_place_count"],
                    "coverage_score": calculate_coverage_score(group),
                },
            )
            touched_ids.append(coverage.id)

        pruned = 0
        if options["prune"]:
            stale = PlaceCoverage.objects.all()
            if options["source"]:
                stale = stale.filter(source=options["source"])
            if touched_ids:
                stale = stale.exclude(id__in=touched_ids)
            pruned, _ = stale.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Coverage rebuild complete: cells={len(touched_ids)} pruned={pruned}"
            )
        )


def calculate_coverage_score(group):
    active = group["active_record_count"]
    if active <= 0:
        return 0.0

    normalized_ratio = min(group["normalized_place_count"] / active, 1)
    tagged_ratio = min(group["tagged_place_count"] / active, 1)
    evidence_ratio = min(group["evidence_place_count"] / active, 1)
    score = 20 + 30 * normalized_ratio + 20 * tagged_ratio + 30 * evidence_ratio
    return round(min(score, 100), 2)
