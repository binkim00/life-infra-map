import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence
from recommendations.services.structured_evidence_freshness import (
    freshness_state,
    structured_expiry,
    ttl_days_for,
)


STRUCTURED_SOURCES = ("field_rule", "external_data")


class Command(BaseCommand):
    help = "Apply source-specific TTL to official Evidence without deleting old rows."

    def add_arguments(self, parser):
        parser.add_argument("--category", action="append")
        parser.add_argument("--place-source", action="append")
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--output", default="")

    def handle(self, *args, **options):
        queryset = PlaceTagEvidence.objects.filter(source__in=STRUCTURED_SOURCES).select_related("place")
        if options["category"]:
            queryset = queryset.filter(place__category__in=options["category"])
        if options["place_source"]:
            queryset = queryset.filter(place__source__in=options["place_source"])
        report = apply_freshness(
            queryset,
            dry_run=options["dry_run"],
            batch_size=max(1, options["batch_size"]),
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(rendered)
        if options["output"]:
            output = Path(options["output"]).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")


def apply_freshness(queryset, *, dry_run=False, batch_size=1000, now=None):
    now = now or timezone.now()
    counts = Counter()
    by_source = Counter()
    by_category = Counter()
    updates = []
    stale_pairs = set()
    for evidence in queryset.iterator(chunk_size=batch_size):
        context = evidence.context or {}
        dataset = context.get("dataset", "")
        place_source = evidence.place.source
        state = freshness_state(
            evidence.observed_at,
            place_source=place_source,
            dataset=dataset,
            now=now,
        )
        counts[state] += 1
        by_source[(place_source, state)] += 1
        by_category[(evidence.place.category, state)] += 1
        expected_expiry = structured_expiry(
            evidence.observed_at,
            place_source=place_source,
            dataset=dataset,
        )
        if state == "stale":
            stale_pairs.add((evidence.place_id, evidence.tag_id, evidence.source))
        if evidence.expires_at != expected_expiry:
            counts["expiry_updates"] += 1
            evidence.expires_at = expected_expiry
            new_context = dict(context)
            new_context["freshness_policy"] = {
                "key": dataset or place_source,
                "ttl_days": ttl_days_for(place_source=place_source, dataset=dataset),
                "state": state,
            }
            evidence.context = new_context
            updates.append(evidence)
            if len(updates) >= batch_size and not dry_run:
                PlaceTagEvidence.objects.bulk_update(updates, ["expires_at", "context", "updated_at"], batch_size=batch_size)
                updates = []
    if updates and not dry_run:
        PlaceTagEvidence.objects.bulk_update(updates, ["expires_at", "context", "updated_at"], batch_size=batch_size)

    aggregate_updates = 0
    if not dry_run and stale_pairs:
        with transaction.atomic():
            for evidence_source, aggregate_source in (("field_rule", "field_rule"), ("external_data", "external_data")):
                pair_subset = [(place_id, tag_id) for place_id, tag_id, source in stale_pairs if source == evidence_source]
                for place_id, tag_id in pair_subset:
                    aggregate_updates += PlaceTag.objects.filter(
                        place_id=place_id,
                        tag_id=tag_id,
                        source=aggregate_source,
                        status="confirmed",
                    ).update(status="needs_verification", is_verified=False, verified_at=None)
    return {
        "evidence": sum(counts[state] for state in ("current", "stale", "unknown")),
        "current": counts["current"],
        "stale": counts["stale"],
        "unknown": counts["unknown"],
        "expiry_updates": counts["expiry_updates"],
        "aggregate_updates": aggregate_updates,
        "by_source": nested_counts(by_source),
        "by_category": nested_counts(by_category),
        "mode": "dry-run" if dry_run else "commit",
    }


def nested_counts(counter):
    result = {}
    for (name, state), count in sorted(counter.items()):
        result.setdefault(name, {})[state] = count
    return result
