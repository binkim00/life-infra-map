import json
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.management.commands.generate_meaningful_place_tags import generate_meaningful_tags
from recommendations.models import Place, PlaceTag, PlaceTagEvidence
from recommendations.services.meaningful_tag_rules import extract_meaningful_tags


SOURCE_CONFIG = {
    "toilet": {
        "source": "public_toilet_standard",
        "path": "ExData/Cleaned/toilet_places.json",
        "container": None,
    },
    "parking": {
        "source": "public_parking_standard",
        "path": "ExData/ImportPlan/final/parking_db_ready.json",
        "container": "place_candidates",
    },
    "city_park": {
        "source": "citypark_standard",
        "path": "ExData/ImportPlan/final/citypark_db_ready.json",
        "container": "place_candidates",
    },
}


class Command(BaseCommand):
    help = "Backfill missing official public-facility fields into Place.raw without replacing existing data."

    def add_arguments(self, parser):
        parser.add_argument("--category", choices=SOURCE_CONFIG, action="append")
        parser.add_argument("--region", default="")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--skip-evidence", action="store_true")

    def handle(self, *args, **options):
        categories = options["category"] or list(SOURCE_CONFIG)
        total = {
            "source_rows": 0, "matched_places": 0, "raw_updates": 0,
            "source_date_updates": 0, "missing_places": 0, "region_skipped": 0,
            "official_fields_added": 0,
            "tag_matches_after_merge": 0, "field_rule_before": PlaceTagEvidence.objects.filter(source="field_rule").count(),
        }
        processed_ids = []
        for category in categories:
            stats, ids = backfill_category(
                category,
                region=options["region"],
                limit=options["limit"],
                batch_size=max(1, options["batch_size"]),
                dry_run=options["dry_run"],
            )
            processed_ids.extend(ids)
            for key, value in stats.items():
                total[key] += value

        evidence_stats = None
        invalidated = neutralize_unsupported_all_day_evidence(processed_ids, dry_run=options["dry_run"])
        if not options["dry_run"] and not options["skip_evidence"] and processed_ids:
            evidence_stats = generate_meaningful_tags(
                Place.objects.filter(id__in=processed_ids).order_by("id"),
                batch_size=max(1, options["batch_size"]),
            )
        total["field_rule_after"] = PlaceTagEvidence.objects.filter(source="field_rule").count()
        total["field_rule_created"] = total["field_rule_after"] - total["field_rule_before"]
        total["evidence_generation"] = evidence_stats
        total["neutralized_unsupported_all_day"] = invalidated
        total["mode"] = "dry-run" if options["dry_run"] else "commit"
        self.stdout.write(json.dumps(total, ensure_ascii=False, indent=2))


def backfill_category(category, *, region="", limit=None, batch_size=500, dry_run=False):
    config = SOURCE_CONFIG[category]
    path = Path(settings.BASE_DIR).parent / config["path"]
    if not path.exists():
        raise CommandError(f"Source file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if config["container"] is None else payload.get(config["container"], [])
    queryset = Place.objects.filter(category=category, source=config["source"])
    places = {place.external_id: place for place in queryset}
    stats = {
        "source_rows": 0, "matched_places": 0, "raw_updates": 0,
        "source_date_updates": 0, "missing_places": 0, "region_skipped": 0,
        "official_fields_added": 0,
        "tag_matches_after_merge": 0,
    }
    updates = []
    processed_ids = []
    for row in rows:
        if limit is not None and stats["matched_places"] >= limit:
            break
        external_id = str(row.get("external_id") or row.get("source_id") or "")
        if not external_id:
            continue
        stats["source_rows"] += 1
        place = places.get(external_id)
        if place is None:
            stats["missing_places"] += 1
            continue
        if region and not (place.address or "").startswith(region):
            stats["region_skipped"] += 1
            continue
        stats["matched_places"] += 1
        processed_ids.append(place.id)
        official = official_fields(row)
        merged, added = merge_missing_official_fields(place.raw, official)
        observed_date = parse_source_date(row.get("source_updated_at") or official.get("데이터기준일자"))
        date_changed = observed_date is not None and (
            place.source_updated_at is None or observed_date > place.source_updated_at
        )
        stats["tag_matches_after_merge"] += len(extract_meaningful_tags(merged))
        if not added and not date_changed:
            continue
        if added:
            stats["raw_updates"] += 1
            stats["official_fields_added"] += len(added)
        if date_changed:
            stats["source_date_updates"] += 1
        if dry_run:
            continue
        place.raw = merged
        if date_changed:
            place.source_updated_at = observed_date
        updates.append(place)
        if len(updates) >= batch_size:
            with transaction.atomic():
                Place.objects.bulk_update(updates, ["raw", "source_updated_at", "updated_at"], batch_size=batch_size)
            updates = []
    if updates and not dry_run:
        with transaction.atomic():
            Place.objects.bulk_update(updates, ["raw", "source_updated_at", "updated_at"], batch_size=batch_size)
    return stats, processed_ids


def official_fields(row):
    raw = row.get("raw") or {}
    nested = raw.get("raw") if isinstance(raw, dict) else None
    return nested if isinstance(nested, dict) else raw if isinstance(raw, dict) else {}


def merge_missing_official_fields(current_raw, official):
    merged = dict(current_raw or {})
    existing_names = mapping_key_names(merged)
    missing = {key: value for key, value in official.items() if key not in existing_names}
    if not missing:
        return merged, {}
    namespace = dict(merged.get("official_backfill") or {})
    namespace.update(missing)
    merged["official_backfill"] = namespace
    return merged, missing


def mapping_key_names(value):
    names = set()
    if isinstance(value, dict):
        for key, child in value.items():
            names.add(str(key))
            names.update(mapping_key_names(child))
    elif isinstance(value, list):
        for child in value:
            names.update(mapping_key_names(child))
    return names


def parse_source_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def neutralize_unsupported_all_day_evidence(place_ids, *, dry_run=False):
    rows = list(PlaceTagEvidence.objects.filter(
        place_id__in=place_ids,
        place__category="toilet",
        source="field_rule",
        tag__name="24시간운영",
        polarity="positive",
    ))
    invalid = []
    for evidence in rows:
        value = str((evidence.raw or {}).get("value", ""))
        compact = "".join(value.lower().split())
        explicit = (
            any(marker in compact for marker in ("24시간", "24시개방", "상시개방"))
            or compact == "상시"
        )
        if "연중무휴" in compact and not explicit:
            invalid.append(evidence)
    if dry_run or not invalid:
        return len(invalid)
    for evidence in invalid:
        evidence.polarity = "neutral"
        evidence.confidence = 0
        context = dict(evidence.context or {})
        context["invalidated_reason"] = "연중무휴는 24시간 운영의 직접 근거가 아님"
        evidence.context = context
    PlaceTagEvidence.objects.bulk_update(invalid, ["polarity", "confidence", "context", "updated_at"])
    PlaceTag.objects.filter(
        place_id__in=[evidence.place_id for evidence in invalid],
        tag__name="24시간운영",
        source="field_rule",
    ).update(
        status="needs_verification",
        confidence=0,
        evidence="기존 공식 field_rule이 24시간 운영을 직접 입증하지 못해 무효화됨",
        is_verified=False,
        verified_at=None,
    )
    return len(invalid)
