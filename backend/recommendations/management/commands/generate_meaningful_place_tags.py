import hashlib

from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.meaningful_tag_rules import extract_meaningful_tags


class Command(BaseCommand):
    help = "Generate evidence-backed non-category tags from official raw fields."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="")
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        queryset = Place.objects.filter(id__gt=options["after_id"]).order_by("id")
        if options["source"]:
            queryset = queryset.filter(source=options["source"])
        if options["limit"] is not None:
            queryset = queryset[:options["limit"]]
        stats = generate_meaningful_tags(
            queryset,
            batch_size=max(1, options["batch_size"]),
            dry_run=options["dry_run"],
        )
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Meaningful tag generation complete: "
            f"places={stats['places']} matches={stats['matches']} "
            f"tags={stats['tags']} evidence={stats['evidence']}"
        ))


def generate_meaningful_tags(places, *, batch_size=1000, dry_run=False):
    stats = {"places": 0, "matches": 0, "tags": 0, "evidence": 0}
    pending = []
    for place in places.iterator(chunk_size=batch_size):
        stats["places"] += 1
        for match in extract_meaningful_tags(place.raw):
            pending.append((place, match))
        if len(pending) >= batch_size:
            save_matches(pending, stats, dry_run=dry_run)
            pending = []
    if pending:
        save_matches(pending, stats, dry_run=dry_run)
    return stats


def save_matches(matches, stats, *, dry_run=False):
    unique = {}
    for place, match in matches:
        unique[(place.id, match["tag"])] = (place, match)
    matches = list(unique.values())
    stats["matches"] += len(matches)
    if dry_run:
        return

    tag_names = {match["tag"] for _, match in matches}
    existing = {tag.name: tag for tag in Tag.objects.filter(name__in=tag_names)}
    for name in tag_names - existing.keys():
        existing[name] = Tag.objects.create(
            name=name,
            tag_type="recommendation",
            description="공식 원문 필드로 검증된 의미 태그",
        )

    now = timezone.now()
    aggregates = []
    evidence_rows = []
    for place, match in matches:
        tag = existing[match["tag"]]
        reference = f"{place.source}:{place.external_id}:{match['field']}"
        evidence_text = f"{match['description']} ({match['field']}={match['value']})"
        aggregates.append(PlaceTag(
            place=place,
            tag=tag,
            source="field_rule",
            status="confirmed",
            confidence=match["confidence"],
            evidence=evidence_text,
            is_verified=True,
            verified_at=now,
        ))
        key_value = f"{place.id}|{tag.id}|field_rule|{reference}|positive"
        evidence_rows.append(PlaceTagEvidence(
            place=place,
            tag=tag,
            evidence_key=hashlib.sha256(key_value.encode("utf-8")).hexdigest(),
            source="field_rule",
            source_reference=reference,
            polarity="positive",
            confidence=match["confidence"],
            evidence=evidence_text,
            context={"field": match["field"], "objective": True},
            raw={"field": match["field"], "value": match["value"]},
            observed_at=place.source_updated_at or now,
        ))

    PlaceTag.objects.bulk_create(
        aggregates,
        batch_size=max(1, len(aggregates)),
        update_conflicts=True,
        unique_fields=["place", "tag", "source"],
        update_fields=[
            "status", "confidence", "evidence", "is_verified",
            "verified_at", "updated_at",
        ],
    )
    PlaceTagEvidence.objects.bulk_create(
        evidence_rows,
        batch_size=max(1, len(evidence_rows)),
        update_conflicts=True,
        unique_fields=["evidence_key"],
        update_fields=[
            "confidence", "evidence", "context", "raw", "observed_at",
            "updated_at",
        ],
    )
    stats["tags"] += len(aggregates)
    stats["evidence"] += len(evidence_rows)
