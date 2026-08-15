import csv
import hashlib
from datetime import datetime, time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from recommendations.management.commands.import_localdata_records import (
    calculate_sha256,
    detect_delimiter,
    detect_encoding,
    save_batch,
    stable_region_code,
)
from recommendations.models import DataSourceSyncRun, SourcePlaceRecord


CATALOG_URL = "https://www.data.go.kr/data/15013109/standard.do"
FIELD_ALIASES = {
    "name": ("도서관명", "library_name"),
    "sido": ("시도명", "sido_name"),
    "sigungu": ("시군구명", "sigungu_name"),
    "library_type": ("도서관유형", "library_type"),
    "closed_days": ("휴관일", "closed_days"),
    "weekday_open": ("평일운영시작시각", "weekday_open"),
    "weekday_close": ("평일운영종료시각", "weekday_close"),
    "saturday_open": ("토요일운영시작시각", "saturday_open"),
    "saturday_close": ("토요일운영종료시각", "saturday_close"),
    "holiday_open": ("공휴일운영시작시각", "holiday_open"),
    "holiday_close": ("공휴일운영종료시각", "holiday_close"),
    "seat_count": ("열람좌석수", "seat_count"),
    "address": ("소재지도로명주소", "road_address"),
    "operator": ("운영기관명", "operator"),
    "phone": ("도서관전화번호", "phone"),
    "homepage": ("홈페이지주소", "homepage"),
    "lat": ("위도", "latitude", "lat"),
    "lng": ("경도", "longitude", "lng"),
    "reference_date": ("데이터기준일자", "reference_date"),
}


class Command(BaseCommand):
    help = "Import the nationwide library standard CSV into SourcePlaceRecord."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--encoding", default="auto")
        parser.add_argument("--delimiter", default="")
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--start-row", type=int, default=0)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--sync-type", choices=("full", "delta"), default="full")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"]).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise CommandError(f"File does not exist: {path}")
        stats = import_library_csv(
            path,
            encoding=options["encoding"],
            delimiter=options["delimiter"],
            batch_size=max(1, options["batch_size"]),
            start_row=max(0, options["start_row"]),
            limit=options["limit"],
            sync_type=options["sync_type"],
            dry_run=options["dry_run"],
        )
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Library import complete: read={stats['read']} valid={stats['valid']} "
            f"created={stats['created']} updated={stats['updated']} "
            f"skipped={stats['skipped']} duplicates={stats['duplicates']}"
        ))


def import_library_csv(
    path,
    *,
    encoding="auto",
    delimiter="",
    batch_size=1000,
    start_row=0,
    limit=None,
    sync_type="full",
    dry_run=False,
):
    path = Path(path)
    resolved_encoding = detect_encoding(path) if encoding == "auto" else encoding
    resolved_delimiter = delimiter or detect_delimiter(path, resolved_encoding)
    stats = {"read": 0, "valid": 0, "created": 0, "updated": 0, "skipped": 0, "duplicates": 0}
    sync_run = None
    if not dry_run:
        sync_run = DataSourceSyncRun.objects.create(
            source="data_go_kr",
            dataset="library_standard",
            sync_type=sync_type,
            source_uri=CATALOG_URL,
            source_checksum=calculate_sha256(path),
        )
    try:
        batch = []
        with path.open("r", encoding=resolved_encoding, newline="") as handle:
            reader = csv.DictReader(handle, delimiter=resolved_delimiter)
            if not reader.fieldnames:
                raise CommandError("CSV header is missing.")
            for row_index, row in enumerate(reader):
                if row_index < start_row:
                    continue
                if limit is not None and stats["read"] >= limit:
                    break
                stats["read"] += 1
                record = build_library_record(row)
                if record is None:
                    stats["skipped"] += 1
                    continue
                stats["valid"] += 1
                if not dry_run:
                    batch.append(SourcePlaceRecord(**record))
                    if len(batch) >= batch_size:
                        save_batch(batch, stats)
                        batch = []
        if batch:
            save_batch(batch, stats)
        if sync_run:
            sync_run.status = "succeeded"
            sync_run.stats = stats
            sync_run.completed_at = timezone.now()
            sync_run.save(update_fields=["status", "stats", "completed_at"])
        return stats
    except Exception as exc:
        if sync_run:
            sync_run.status = "failed"
            sync_run.stats = stats
            sync_run.error_message = str(exc)[:4000]
            sync_run.completed_at = timezone.now()
            sync_run.save(update_fields=["status", "stats", "error_message", "completed_at"])
        raise


def build_library_record(row):
    cleaned = {str(key or "").lstrip("\ufeff").strip(): str(value or "").strip() for key, value in row.items()}
    values = {field: pick(cleaned, aliases) for field, aliases in FIELD_ALIASES.items()}
    if not values["name"] or not values["address"]:
        return None
    identity = "|".join((values["name"], values["address"], values["operator"]))
    source_record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    reference_date = parse_date(values["reference_date"])
    source_updated_at = None
    if reference_date:
        source_updated_at = timezone.make_aware(datetime.combine(reference_date, time.min))
    raw = {
        "catalog_url": CATALOG_URL,
        "library_type": values["library_type"],
        "closed_days": values["closed_days"],
        "weekday_open": values["weekday_open"],
        "weekday_close": values["weekday_close"],
        "saturday_open": values["saturday_open"],
        "saturday_close": values["saturday_close"],
        "holiday_open": values["holiday_open"],
        "holiday_close": values["holiday_close"],
        "seat_count": parse_nonnegative_int(values["seat_count"]),
        "operator": values["operator"],
        "phone": values["phone"],
        "homepage": values["homepage"],
        "reference_date": values["reference_date"],
    }
    return {
        "source": "data_go_kr",
        "dataset": "library_standard",
        "source_record_id": source_record_id,
        "name": values["name"][:255],
        "category": "library",
        "business_type": values["library_type"][:100],
        "business_status": "",
        "is_active": True,
        "address": values["address"][:500],
        "road_address": values["address"][:500],
        "sido_name": values["sido"][:50],
        "sigungu_name": values["sigungu"][:80],
        "administrative_code": stable_region_code(values["sido"], values["sigungu"]),
        "source_x": values["lng"][:50],
        "source_y": values["lat"][:50],
        "coordinate_reference_system": "EPSG:4326",
        "source_updated_at": source_updated_at,
        "raw": raw,
    }


def pick(row, aliases):
    for alias in aliases:
        value = row.get(alias, "")
        if value:
            return value
    return ""


def parse_nonnegative_int(value):
    try:
        return max(0, int(str(value or "0").replace(",", "")))
    except ValueError:
        return 0
