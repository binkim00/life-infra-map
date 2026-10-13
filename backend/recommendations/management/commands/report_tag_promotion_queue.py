"""Read-only shortlist for human review of well-supported web tag candidates."""

import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.models import PlaceTag
from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence
from recommendations.services.tag_source_policy import WEB_AGGREGATE_SOURCE


class Command(BaseCommand):
    help = "Summarize web tag promotion candidates without exposing evidence text or place names."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--output", default="")

    def handle(self, *args, **options):
        limit = max(1, min(options["limit"], 5000))
        pairs = PlaceTag.objects.filter(
            source=WEB_AGGREGATE_SOURCE, status="candidate",
        ).select_related("place", "tag").order_by("id")[:limit]
        queue = []
        summary = Counter()
        for pair in pairs:
            state = aggregate_tag_evidence(pair.place, pair.tag, dry_run=True)
            quality = state["quality"]
            if state["official_negative"] or state["web_negative"]:
                reason = "conflict_review"
            elif (
                state["web_positive"] >= 3
                and quality["average_confidence"] >= 75
                and quality["freshness"] >= 70
                and quality["source_diversity"] >= 2
            ):
                reason = "identity_and_independence_review"
            else:
                reason = "more_independent_evidence_needed"
            summary[reason] += 1
            if reason != "more_independent_evidence_needed":
                queue.append({
                    "place_tag_id": pair.id,
                    "place_id": pair.place_id,
                    "tag_id": pair.tag_id,
                    "reason": reason,
                    "independent_positive": state["web_positive"],
                    "independent_negative": state["web_negative"],
                    "average_confidence": quality["average_confidence"],
                    "freshness": quality["freshness"],
                    "source_diversity": quality["source_diversity"],
                })
        if options["output"]:
            path = Path(options["output"]).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps({
            "inspected": sum(summary.values()),
            "review_queue": len(queue),
            "reasons": dict(summary),
        }, ensure_ascii=False))
