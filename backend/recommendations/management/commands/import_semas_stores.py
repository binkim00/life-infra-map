import csv
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
)
from recommendations.models import DataSourceSyncRun, SourcePlaceRecord


CATALOG_URL = "https://www.data.go.kr/data/15083033/fileData.do"
SUPPORTED_CATEGORIES = {"cafe", "restaurant", "bookstore"}
ALIASES = {
    "id": ("상가업소번호", "상가업소ID", "store_id", "bizesId"),
    "name": ("상호명", "store_name", "bizesNm"),
    "branch": ("지점명", "branch_name", "brchNm"),
    "major_code": ("상권업종대분류코드", "indsLclsCd"),
    "major_name": ("상권업종대분류명", "indsLclsNm"),
    "middle_code": ("상권업종중분류코드", "indsMclsCd"),
    "middle_name": ("상권업종중분류명", "indsMclsNm"),
    "minor_code": ("상권업종소분류코드", "indsSclsCd"),
    "minor_name": ("상권업종소분류명", "indsSclsNm"),
    "ksic_code": ("표준산업분류코드", "ksicCd"),
    "ksic_name": ("표준산업분류명", "ksicNm"),
    "sido_code": ("시도코드", "ctprvnCd"),
    "sido_name": ("시도명", "ctprvnNm"),
    "sigungu_code": ("시군구코드", "signguCd"),
    "sigungu_name": ("시군구명", "signguNm"),
    "administrative_code": ("행정동코드", "adongCd"),
    "lot_address": ("지번주소", "lnoAdr"),
    "road_address": ("도로명주소", "rdnmAdr"),
    "lng": ("경도", "lon"),
    "lat": ("위도", "lat"),
}


class Command(BaseCommand):
    help = "Import nationwide SEMAS store CSV rows for selected place categories."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--categories", default="cafe,restaurant,bookstore")
        parser.add_argument("--snapshot-date", default="")
        parser.add_argument("--encoding", default="auto")
        parser.add_argument("--delimiter", default="")
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument("--start-row", type=int, default=0)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--sync-type", choices=("full", "delta"), default="full")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"]).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise CommandError(f"File does not exist: {path}")
        categories = {value.strip() for value in options["categories"].split(",") if value.strip()}
        unknown = categories - SUPPORTED_CATEGORIES
        if unknown:
            raise CommandError("Unknown categories: " + ", ".join(sorted(unknown)))
        snapshot_date = parse_date(options["snapshot_date"]) if options["snapshot_date"] else None
        if options["snapshot_date"] and not snapshot_date:
            raise CommandError("--snapshot-date must use YYYY-MM-DD.")
        stats = import_semas_csv(
            path,
            categories=categories,
            snapshot_date=snapshot_date,
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
            f"{prefix}SEMAS import complete: read={stats['read']} selected={stats['valid']} "
            f"created={stats['created']} updated={stats['updated']} "
            f"skipped={stats['skipped']} duplicates={stats['duplicates']}"
        ))


def import_semas_csv(
    path,
    *,
    categories,
    snapshot_date=None,
    encoding="auto",
    delimiter="",
    batch_size=2000,
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
            source="semas",
            dataset="commercial_store",
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
                record = build_semas_record(row, categories=categories, snapshot_date=snapshot_date)
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


def build_semas_record(row, *, categories, snapshot_date=None):
    cleaned = {str(key or "").lstrip("\ufeff").strip(): str(value or "").strip() for key, value in row.items()}
    values = {field: pick(cleaned, aliases) for field, aliases in ALIASES.items()}
    category = infer_store_category(values)
    if not values["id"] or not values["name"] or category not in categories:
        return None
    if not (values["road_address"] or values["lot_address"]):
        return None
    name = values["name"]
    if values["branch"] and compact(values["branch"]) not in compact(name):
        name = f"{name} {values['branch']}"
    source_updated_at = None
    if snapshot_date:
        source_updated_at = timezone.make_aware(datetime.combine(snapshot_date, time.min))
    return {
        "source": "semas",
        "dataset": "commercial_store",
        "source_record_id": values["id"][:160],
        "name": name[:255],
        "category": category,
        "business_type": values["minor_name"][:100],
        "business_status": "영업",
        "is_active": True,
        "address": values["lot_address"][:500],
        "road_address": values["road_address"][:500],
        "sido_name": values["sido_name"][:50],
        "sigungu_name": values["sigungu_name"][:80],
        "administrative_code": (values["administrative_code"] or values["sigungu_code"])[:30],
        "source_x": values["lng"][:50],
        "source_y": values["lat"][:50],
        "coordinate_reference_system": "EPSG:4326",
        "source_updated_at": source_updated_at,
        "raw": {
            "catalog_url": CATALOG_URL,
            "branch_name": values["branch"],
            "industry_major_code": values["major_code"],
            "industry_major_name": values["major_name"],
            "industry_middle_code": values["middle_code"],
            "industry_middle_name": values["middle_name"],
            "industry_minor_code": values["minor_code"],
            "industry_minor_name": values["minor_name"],
            "ksic_code": values["ksic_code"],
            "ksic_name": values["ksic_name"],
            "sido_code": values["sido_code"],
            "sigungu_code": values["sigungu_code"],
        },
    }


def infer_store_category(values):
    text = " ".join(
        values.get(field, "")
        for field in ("major_name", "middle_name", "minor_name", "ksic_name")
    ).lower()
    if any(term in text for term in ("서점", "서적 소매", "중고 서적", "책방")):
        return "bookstore"
    if any(term in text for term in ("카페", "커피", "다방", "차류")):
        return "cafe"
    if "음식" in text or "식당" in text:
        return "restaurant"
    return ""


def pick(row, aliases):
    for alias in aliases:
        value = row.get(alias, "")
        if value:
            return value
    return ""


def compact(value):
    return "".join(character.lower() for character in str(value or "") if character.isalnum())
