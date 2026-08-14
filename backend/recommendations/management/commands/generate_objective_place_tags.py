import hashlib

from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence, SourcePlaceRecord, Tag


FIELD_RULES = [
    {
        "tag": "카페",
        "tag_type": "category",
        "categories": {"cafe"},
        "terms": (),
        "confidence": 95,
    },
    {
        "tag": "베이커리",
        "tag_type": "category",
        "categories": {"bakery"},
        "terms": ("제과", "베이커리"),
        "confidence": 95,
    },
    {
        "tag": "전통찻집",
        "tag_type": "recommendation",
        "categories": set(),
        "terms": ("전통찻집",),
        "confidence": 90,
    },
    {
        "tag": "패스트푸드",
        "tag_type": "category",
        "categories": set(),
        "terms": ("패스트푸드",),
        "confidence": 90,
    },
    {
        "tag": "디저트",
        "tag_type": "recommendation",
        "categories": set(),
        "terms": ("아이스크림", "떡카페"),
        "confidence": 85,
    },
]

NAME_RULES = [
    {"tag": "브런치", "terms": ("브런치",), "confidence": 60},
    {"tag": "북카페", "terms": ("북카페", "책카페"), "confidence": 60},
    {"tag": "24시간", "terms": ("24시간", "24시"), "confidence": 50},
]


class Command(BaseCommand):
    help = "Generate evidence-backed objective tag candidates from official source fields."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="localdata")
        parser.add_argument("--dataset", default="")
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        queryset = SourcePlaceRecord.objects.filter(
            source=options["source"],
            is_active=True,
            normalized_place__isnull=False,
        ).select_related("normalized_place")
        if options["dataset"]:
            queryset = queryset.filter(dataset=options["dataset"])
        queryset = queryset.order_by("id")
        if options["limit"] is not None:
            queryset = queryset[:options["limit"]]

        stats = generate_tags(
            queryset,
            batch_size=max(1, options["batch_size"]),
            dry_run=options["dry_run"],
        )
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Objective tag generation complete: "
                f"records={stats['records']} matches={stats['matches']} "
                f"aggregates={stats['aggregates']} evidence={stats['evidence']}"
            )
        )


def generate_tags(records, *, batch_size=1000, dry_run=False):
    tags = ensure_tags(dry_run=dry_run)
    stats = {"records": 0, "matches": 0, "aggregates": 0, "evidence": 0}
    batch = []
    for record in records.iterator(chunk_size=batch_size):
        stats["records"] += 1
        batch.extend(extract_tag_matches(record))
        if len(batch) >= batch_size:
            save_tag_batch(batch, tags, stats, dry_run=dry_run)
            batch = []
    if batch:
        save_tag_batch(batch, tags, stats, dry_run=dry_run)
    return stats


def ensure_tags(*, dry_run=False):
    definitions = {
        rule["tag"]: rule.get("tag_type", "recommendation")
        for rule in [*FIELD_RULES, *NAME_RULES]
    }
    if dry_run:
        return {}
    result = {}
    for name, tag_type in definitions.items():
        tag, _ = Tag.objects.get_or_create(
            name=name,
            defaults={
                "tag_type": tag_type,
                "description": "Nationwide official-field tag pipeline",
            },
        )
        result[name] = tag
    return result


def extract_tag_matches(record):
    matches = []
    business_type = compact(record.business_type)
    for rule in FIELD_RULES:
        category_match = record.category in rule["categories"]
        term_match = any(compact(term) in business_type for term in rule["terms"])
        if not category_match and not term_match:
            continue
        matches.append(
            {
                "record": record,
                "tag": rule["tag"],
                "source": "external_data",
                "status": "confirmed",
                "confidence": rule["confidence"],
                "is_verified": True,
                "evidence": (
                    f"LOCALDATA official field: category={record.category}, "
                    f"business_type={record.business_type}"
                ),
                "context": {"field": "business_type", "objective": True},
            }
        )

    name = compact(record.name)
    for rule in NAME_RULES:
        matched_term = next(
            (term for term in rule["terms"] if compact(term) in name),
            None,
        )
        if matched_term is None:
            continue
        matches.append(
            {
                "record": record,
                "tag": rule["tag"],
                "source": "keyword_rule",
                "status": "candidate",
                "confidence": rule["confidence"],
                "is_verified": False,
                "evidence": f"Place name contains '{matched_term}': {record.name}",
                "context": {"field": "name", "objective": False},
            }
        )
    return matches


def save_tag_batch(matches, tags, stats, *, dry_run=False):
    unique_matches = {}
    for match in matches:
        key = (
            match["record"].normalized_place_id,
            match["tag"],
            match["source"],
        )
        unique_matches[key] = match
    matches = list(unique_matches.values())
    stats["matches"] += len(matches)
    if dry_run:
        return

    now = timezone.now()
    aggregates = []
    evidence_rows = []
    for match in matches:
        record = match["record"]
        tag = tags[match["tag"]]
        reference = f"localdata:{record.dataset}:{record.source_record_id}"
        aggregates.append(
            PlaceTag(
                place_id=record.normalized_place_id,
                tag=tag,
                source=match["source"],
                status=match["status"],
                confidence=match["confidence"],
                evidence=match["evidence"],
                is_verified=match["is_verified"],
                verified_at=now if match["is_verified"] else None,
            )
        )
        evidence_rows.append(
            PlaceTagEvidence(
                place_id=record.normalized_place_id,
                tag=tag,
                evidence_key=make_evidence_key(
                    record.normalized_place_id,
                    tag.id,
                    match["source"],
                    reference,
                ),
                source=match["source"],
                source_reference=reference,
                polarity="positive",
                confidence=match["confidence"],
                evidence=match["evidence"],
                context=match["context"],
                observed_at=record.source_updated_at or now,
                raw={
                    "dataset": record.dataset,
                    "source_record_id": record.source_record_id,
                },
            )
        )

    PlaceTag.objects.bulk_create(
        aggregates,
        batch_size=len(aggregates),
        update_conflicts=True,
        unique_fields=["place", "tag", "source"],
        update_fields=[
            "status",
            "confidence",
            "evidence",
            "is_verified",
            "verified_at",
            "updated_at",
        ],
    )
    PlaceTagEvidence.objects.bulk_create(
        evidence_rows,
        batch_size=len(evidence_rows),
        update_conflicts=True,
        unique_fields=["evidence_key"],
        update_fields=[
            "confidence",
            "evidence",
            "context",
            "observed_at",
            "raw",
            "updated_at",
        ],
    )
    stats["aggregates"] += len(aggregates)
    stats["evidence"] += len(evidence_rows)


def make_evidence_key(place_id, tag_id, source, source_reference):
    value = f"{place_id}|{tag_id}|{source}|{source_reference}|positive"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def compact(value):
    return str(value or "").strip().lower().replace(" ", "")
