import hashlib

from django.core.management.base import BaseCommand
from pyproj import Transformer

from recommendations.models import Place, SourcePlaceRecord


KOREA_LNG_RANGE = (123.0, 132.0)
KOREA_LAT_RANGE = (32.0, 39.5)
TRANSFORMERS = {}


class Command(BaseCommand):
    help = "Promote valid staged source rows into canonical searchable Place rows."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="localdata")
        parser.add_argument("--dataset", default="")
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--refresh", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        queryset = SourcePlaceRecord.objects.filter(
            source=options["source"],
            is_active=True,
        ).exclude(source_x="").exclude(source_y="")
        if options["dataset"]:
            queryset = queryset.filter(dataset=options["dataset"])
        if not options["refresh"]:
            queryset = queryset.filter(normalized_place__isnull=True)
        queryset = queryset.order_by("id")
        if options["limit"] is not None:
            queryset = queryset[:options["limit"]]

        stats = promote_records(
            queryset,
            batch_size=max(1, options["batch_size"]),
            dry_run=options["dry_run"],
        )
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Place promotion complete: read={stats['read']} "
                f"valid={stats['valid']} created={stats['created']} "
                f"updated={stats['updated']} invalid_coordinates={stats['invalid_coordinates']}"
            )
        )


def promote_records(records, *, batch_size=1000, dry_run=False):
    stats = {
        "read": 0,
        "valid": 0,
        "created": 0,
        "updated": 0,
        "invalid_coordinates": 0,
    }
    batch = []
    for record in records.iterator(chunk_size=batch_size):
        stats["read"] += 1
        coordinates = normalize_coordinates(
            record.source_x,
            record.source_y,
            record.coordinate_reference_system,
        )
        if coordinates is None:
            stats["invalid_coordinates"] += 1
            continue
        stats["valid"] += 1
        batch.append((record, coordinates))
        if len(batch) >= batch_size:
            save_promotion_batch(batch, stats, dry_run=dry_run)
            batch = []
    if batch:
        save_promotion_batch(batch, stats, dry_run=dry_run)
    return stats


def save_promotion_batch(batch, stats, *, dry_run=False):
    external_ids = [canonical_external_id(record) for record, _ in batch]
    existing_ids = set(
        Place.objects.filter(
            source=batch[0][0].source,
            external_id__in=external_ids,
        ).values_list("external_id", flat=True)
    )
    stats["updated"] += len(existing_ids)
    stats["created"] += len(batch) - len(existing_ids)
    if dry_run:
        return

    places = []
    for record, (lat, lng) in batch:
        places.append(
            Place(
                name=record.name,
                category=search_category(record.category),
                address=record.road_address or record.address,
                lat=lat,
                lng=lng,
                source=record.source,
                external_id=canonical_external_id(record),
                source_name=record.dataset,
                source_updated_at=(
                    record.source_updated_at.date()
                    if record.source_updated_at is not None
                    else None
                ),
                detail_location=record.road_address or record.address,
                data_quality_status="official_source",
                data_quality_score=80,
                raw={
                    "dataset": record.dataset,
                    "source_record_id": record.source_record_id,
                    "business_type": record.business_type,
                    "business_status": record.business_status,
                    "administrative_code": record.administrative_code,
                    "source_crs": record.coordinate_reference_system,
                },
            )
        )
    Place.objects.bulk_create(
        places,
        batch_size=len(places),
        update_conflicts=True,
        unique_fields=["source", "external_id"],
        update_fields=[
            "name",
            "category",
            "address",
            "lat",
            "lng",
            "source_name",
            "source_updated_at",
            "detail_location",
            "data_quality_status",
            "data_quality_score",
            "raw",
            "updated_at",
        ],
    )

    place_map = {
        place.external_id: place.id
        for place in Place.objects.filter(
            source=batch[0][0].source,
            external_id__in=external_ids,
        ).only("id", "external_id")
    }
    records_to_link = []
    for record, _ in batch:
        record.normalized_place_id = place_map[canonical_external_id(record)]
        records_to_link.append(record)
    SourcePlaceRecord.objects.bulk_update(
        records_to_link,
        ["normalized_place"],
        batch_size=len(records_to_link),
    )


def normalize_coordinates(source_x, source_y, source_crs):
    try:
        x = float(str(source_x).replace(",", "").strip())
        y = float(str(source_y).replace(",", "").strip())
    except (TypeError, ValueError):
        return None

    if is_korea_wgs84(y, x):
        return round(y, 7), round(x, 7)

    crs = source_crs or "EPSG:5174"
    transformer = TRANSFORMERS.get(crs)
    if transformer is None:
        try:
            transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        except Exception:
            return None
        TRANSFORMERS[crs] = transformer
    try:
        lng, lat = transformer.transform(x, y)
    except Exception:
        return None
    if not is_korea_wgs84(lat, lng):
        return None
    return round(lat, 7), round(lng, 7)


def is_korea_wgs84(lat, lng):
    return (
        KOREA_LAT_RANGE[0] <= lat <= KOREA_LAT_RANGE[1]
        and KOREA_LNG_RANGE[0] <= lng <= KOREA_LNG_RANGE[1]
    )


def canonical_external_id(record):
    value = f"{record.dataset}:{record.source_record_id}"
    if len(value) <= 100:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{record.dataset[:30]}:{digest}"[:100]


def search_category(category):
    if category == "food_service":
        return "restaurant"
    return category
