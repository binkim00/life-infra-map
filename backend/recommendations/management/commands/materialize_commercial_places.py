import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.management.commands.promote_source_places import canonical_external_id
from recommendations.models import Place, SourcePlaceRecord
from recommendations.services.commercial_place_registry import (
    exact_identity_key,
    is_service_category,
    normalize_address,
    normalize_name,
    possible_duplicate,
    valid_coordinates,
)


class Command(BaseCommand):
    help = "Materialize official SEMAS cafe/restaurant records with conservative cross-source deduplication."

    def add_arguments(self, parser):
        parser.add_argument("--regions", default="서울특별시,부산광역시")
        parser.add_argument("--categories", default="cafe,restaurant")
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--report", default="")

    def handle(self, *args, **options):
        regions = tuple(value.strip() for value in options["regions"].split(",") if value.strip())
        categories = tuple(value.strip() for value in options["categories"].split(",") if value.strip())
        unknown = set(categories) - {"cafe", "restaurant"}
        if unknown:
            raise CommandError("Unknown categories: " + ", ".join(sorted(unknown)))
        queryset = SourcePlaceRecord.objects.filter(
            source="semas",
            dataset="commercial_store",
            sido_name__in=regions,
            category__in=categories,
            is_active=True,
            normalized_place__isnull=True,
            id__gt=max(0, options["after_id"]),
        ).order_by("id")
        if options["limit"] is not None:
            queryset = queryset[:max(1, options["limit"])]
        stats, examples = materialize_records(
            queryset,
            regions=regions,
            categories=categories,
            dry_run=options["dry_run"],
            batch_size=max(1, options["batch_size"]),
        )
        report = {"stats": stats, "examples": examples}
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(rendered)
        if options["report"]:
            path = Path(options["report"]).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")


def materialize_records(records, *, regions, categories, dry_run=False, batch_size=1000):
    stats = Counter()
    stats_by_stratum = Counter()
    examples = defaultdict(list)
    existing = list(
        Place.objects.filter(category__in=categories).only(
            "id", "name", "category", "address", "detail_location", "lat", "lng", "source", "external_id"
        )
    )
    grid = defaultdict(list)
    exact = defaultdict(list)
    for place in existing:
        grid[(place.category, round(place.lat, 3), round(place.lng, 3))].append(place)
        for address in (place.address, place.detail_location):
            key = exact_identity_key(place.name, address)
            if key:
                exact[(place.category, *key)].append(place)

    pending = []
    pending_records = []
    pending_keys = {}

    def remember(kind, record, detail=""):
        stats[kind] += 1
        stats_by_stratum[(record.sido_name, record.category, kind)] += 1
        if len(examples[kind]) < 10:
            examples[kind].append({
                "record_id": record.id,
                "source_record_id": record.source_record_id,
                "name": record.name,
                "category": record.category,
                "address": record.road_address or record.address,
                "detail": detail,
            })

    def flush():
        nonlocal pending, pending_records, pending_keys
        if not pending:
            return
        if dry_run:
            pending = []
            pending_records = []
            pending_keys = {}
            return
        with transaction.atomic():
            Place.objects.bulk_create(pending, batch_size=batch_size)
            created = {
                place.external_id: place
                for place in Place.objects.filter(
                    source="semas", external_id__in=[place.external_id for place in pending]
                )
            }
            for record, external_id in pending_records:
                record.normalized_place = created[external_id]
            SourcePlaceRecord.objects.bulk_update(pending_records_to_unique(pending_records), ["normalized_place"], batch_size=batch_size)
        for place in created.values():
            grid[(place.category, round(place.lat, 3), round(place.lng, 3))].append(place)
            for address in (place.address, place.detail_location):
                key = exact_identity_key(place.name, address)
                if key:
                    exact[(place.category, *key)].append(place)
        pending = []
        pending_records = []
        pending_keys = {}

    for record in records.iterator(chunk_size=batch_size):
        stats["read"] += 1
        stats["last_id"] = record.id
        if record.sido_name not in regions or record.category not in categories or not is_service_category(record):
            remember("rejected_category", record, record.business_type)
            continue
        coordinates = valid_coordinates(record)
        if coordinates is None:
            remember("rejected_coordinates", record)
            continue
        address = record.road_address or record.address
        if not address or not any(address.startswith(region[:2]) for region in regions):
            remember("rejected_region", record)
            continue

        keys = [
            exact_identity_key(record.name, record.road_address),
            exact_identity_key(record.name, record.address),
        ]
        exact_candidates = []
        for key in {key for key in keys if key}:
            exact_candidates.extend(exact.get((record.category, *key), []))
        exact_candidates = {place.id: place for place in exact_candidates}.values()
        if len(exact_candidates) == 1:
            place = next(iter(exact_candidates))
            remember("existing_match", record, f"place_id={place.id}; exact_name_address")
            if not dry_run:
                record.normalized_place = place
                record.save(update_fields=["normalized_place", "updated_at"])
            continue
        if len(exact_candidates) > 1:
            remember("ambiguous", record, "multiple exact name/address candidates")
            continue

        nearby = []
        lat, lng = coordinates
        for lat_key in (round(lat, 3) - 0.001, round(lat, 3), round(lat, 3) + 0.001):
            for lng_key in (round(lng, 3) - 0.001, round(lng, 3), round(lng, 3) + 0.001):
                nearby.extend(grid.get((record.category, round(lat_key, 3), round(lng_key, 3)), []))
        classifications = [(place, possible_duplicate(record, place, source_coordinates=coordinates)) for place in nearby]
        confirmed = [place for place, status in classifications if status == "confirmed"]
        ambiguous = [place for place, status in classifications if status == "ambiguous"]
        if len(confirmed) == 1:
            place = confirmed[0]
            remember("existing_match", record, f"place_id={place.id}; exact_name_nearby")
            if not dry_run:
                record.normalized_place = place
                record.save(update_fields=["normalized_place", "updated_at"])
            continue
        if len(confirmed) > 1 or ambiguous:
            candidate_ids = [place.id for place in confirmed + ambiguous]
            remember("ambiguous", record, f"place_ids={candidate_ids[:10]}")
            continue

        source_key = (record.category, normalize_name(record.name), normalize_address(address))
        if source_key in pending_keys:
            external_id = pending_keys[source_key]
            pending_records.append((record, external_id))
            remember("existing_match", record, "same SEMAS name/address in current batch")
            continue
        external_id = canonical_external_id(record)
        place = Place(
            name=record.name[:200],
            category=record.category,
            address=address[:255],
            lat=lat,
            lng=lng,
            source="semas",
            external_id=external_id,
            source_name="commercial_store",
            source_updated_at=record.source_updated_at.date() if record.source_updated_at else None,
            detail_location=address[:255],
            data_quality_status="official_source",
            data_quality_score=80,
            raw={
                **(record.raw if isinstance(record.raw, dict) else {}),
                "dataset": record.dataset,
                "source_record_id": record.source_record_id,
                "business_type": record.business_type,
                "source_address": record.address,
                "source_road_address": record.road_address,
            },
        )
        pending.append(place)
        pending_records.append((record, external_id))
        pending_keys[source_key] = external_id
        remember("new_place", record)
        if len(pending) >= batch_size:
            flush()
    flush()
    stats["strata"] = {
        f"{region}|{category}|{kind}": count
        for (region, category, kind), count in sorted(stats_by_stratum.items())
    }
    return dict(stats), dict(examples)


def pending_records_to_unique(pending_records):
    return list({record.id: record for record, _ in pending_records}.values())

