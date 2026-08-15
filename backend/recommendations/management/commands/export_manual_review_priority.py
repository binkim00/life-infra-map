import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q
from django.utils import timezone

from recommendations.models import PlaceTag
from recommendations.services.tag_source_policy import WEB_AGGREGATE_SOURCE


HARD_CONSTRAINT_TAGS = {
    "콘센트있음", "무료와이파이", "휠체어접근", "장애인시설",
    "장애인전용주차", "24시간운영", "무료이용",
}
HIGH_VALUE_TAGS = HARD_CONSTRAINT_TAGS | {
    "조용함", "노트북작업", "작업하기좋음", "혼밥좋음", "웨이팅적음",
}


class Command(BaseCommand):
    help = "Export a bounded, impact-prioritized manual review queue."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tmp/manual_review_priority.csv")
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        now = timezone.now()
        rows = PlaceTag.objects.filter(
            source=WEB_AGGREGATE_SOURCE,
            status__in=("candidate", "needs_verification", "rejected"),
        ).select_related("place", "tag").annotate(
            positive_count=Count(
                "place__tag_evidence__source_reference",
                distinct=True,
                filter=Q(
                    place__tag_evidence__tag_id=F("tag_id"),
                    place__tag_evidence__polarity="positive",
                ) & (Q(place__tag_evidence__expires_at__isnull=True) | Q(place__tag_evidence__expires_at__gt=now)),
            ),
            negative_count=Count(
                "place__tag_evidence__source_reference",
                distinct=True,
                filter=Q(
                    place__tag_evidence__tag_id=F("tag_id"),
                    place__tag_evidence__polarity="negative",
                ) & (Q(place__tag_evidence__expires_at__isnull=True) | Q(place__tag_evidence__expires_at__gt=now)),
            ),
        )
        ranked = []
        for row in rows.iterator(chunk_size=1000):
            conflict = bool(row.positive_count and row.negative_count)
            score = (
                (50 if conflict else 0)
                + (25 if row.tag.name in HARD_CONSTRAINT_TAGS else 15 if row.tag.name in HIGH_VALUE_TAGS else 0)
                + (20 if row.status == "needs_verification" else 0)
                + (15 if 40 <= row.confidence <= 69 else 0)
                + (10 if row.positive_count + row.negative_count == 1 else 0)
            )
            ranked.append((score, row, conflict))
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        ranked = ranked[: max(1, options["limit"])]
        path = Path(options["output"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "priority", "place_id", "place_name", "address", "category", "tag",
                "status", "confidence", "positive_count", "negative_count", "conflict",
                "manual_decision", "manual_note",
            ])
            for score, row, conflict in ranked:
                writer.writerow([
                    score, row.place_id, row.place.name, row.place.address, row.place.category,
                    row.tag.name, row.status, row.confidence, row.positive_count,
                    row.negative_count, conflict, "", "",
                ])
        self.stdout.write(self.style.SUCCESS(
            f"Manual review queue: rows={len(ranked)} output={path}"
        ))
