import csv
import hashlib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from recommendations.models import DataSourceSyncRun, SourcePlaceRecord


DATASET_DEFAULT_CATEGORIES = {
    "general_restaurant": "restaurant",
    "rest_restaurant": "food_service",
    "bakery": "bakery",
    "tourist_restaurant": "restaurant",
}

HEADER_ALIASES = {
    "source_record_id": [
        "관리번호", "개방서비스아이디", "영업신고증관리번호", "번호",
        "mgtNo", "opnSvcId",
    ],
    "name": ["사업장명", "업소명", "업체명", "시설명", "bplcNm"],
    "business_type": [
        "업태구분명", "업태명", "위생업태명", "업종명", "개방서비스명",
        "uptaeNm", "opnSvcNm",
    ],
    "business_status": [
        "상세영업상태명", "영업상태명", "영업상태구분코드",
        "dtlStateNm", "trdStateNm",
    ],
    "business_status_code": [
        "영업상태구분코드", "상세영업상태코드", "trdStateGbn", "dtlStateGbn",
    ],
    "address": ["소재지전체주소", "소재지주소", "지번주소", "siteWhlAddr"],
    "road_address": ["도로명전체주소", "도로명주소", "rdnWhlAddr"],
    "administrative_code": [
        "개방자치단체코드", "관리기관코드", "시군구코드", "opnSfTeamCode",
    ],
    "source_x": ["좌표정보(x)", "좌표정보X", "x", "X"],
    "source_y": ["좌표정보(y)", "좌표정보Y", "y", "Y"],
    "license_date": ["인허가일자", "영업신고일자", "허가일자", "apvPermYmd"],
    "closed_date": ["폐업일자", "인허가취소일자", "dcbYmd"],
    "source_updated_at": [
        "최종수정시점", "데이터갱신일자", "수정일자", "updateDt", "dataUpdateDate",
    ],
}

API_HEADER_ALIASES = {
    "source_record_id": ["MNG_NO"],
    "name": ["BPLC_NM"],
    "business_type": ["BZSTAT_SE_NM"],
    "business_status": ["DTL_SALS_STTS_NM", "SALS_STTS_NM"],
    "business_status_code": ["SALS_STTS_CD", "DTL_SALS_STTS_CD"],
    "address": ["LOTNO_ADDR"],
    "road_address": ["ROAD_NM_ADDR"],
    "administrative_code": ["OPN_ATMY_GRP_CD"],
    "source_x": ["CRD_INFO_X", "\uc88c\ud45c\uc815\ubcf4(X)"],
    "source_y": ["CRD_INFO_Y", "\uc88c\ud45c\uc815\ubcf4(Y)"],
    "license_date": ["LCPMT_YMD"],
    "closed_date": ["CLSBIZ_YMD"],
    "source_updated_at": ["LAST_MDFCN_PNT", "DAT_UPDT_PNT"],
}
for field, aliases in API_HEADER_ALIASES.items():
    HEADER_ALIASES[field].extend(aliases)


INACTIVE_STATUS_CODES = {"02", "03", "04"}
INACTIVE_STATUS_TERMS = ("폐업", "휴업", "취소", "말소", "만료", "정지", "중지")
CAFE_TERMS = ("커피", "카페", "까페", "다방", "전통찻집")
BAKERY_TERMS = ("제과", "베이커리", "빵")


class Command(BaseCommand):
    help = "Import a nationwide LOCALDATA CSV snapshot or delta into source staging records."

    def add_arguments(self, parser):
        parser.add_argument("path", help="LOCALDATA CSV file path")
        parser.add_argument("--dataset", required=True, help="Stable dataset key")
        parser.add_argument("--category", default="", help="Fallback normalized category")
        parser.add_argument("--source", default="localdata")
        parser.add_argument("--sync-type", choices=["full", "delta"], default="full")
        parser.add_argument("--encoding", default="auto")
        parser.add_argument("--delimiter", default="")
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--start-row", type=int, default=0)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"]).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise CommandError(f"File does not exist: {path}")
        if path.suffix.lower() != ".csv":
            raise CommandError("Only CSV is supported. Export LOCALDATA XLSX files to CSV first.")

        category = (
            options["category"].strip()
            or DATASET_DEFAULT_CATEGORIES.get(options["dataset"], "place")
        )
        stats = import_localdata_csv(
            path=path,
            source=options["source"],
            dataset=options["dataset"],
            default_category=category,
            sync_type=options["sync_type"],
            encoding=options["encoding"],
            delimiter=options["delimiter"],
            batch_size=max(1, options["batch_size"]),
            start_row=max(0, options["start_row"]),
            limit=options["limit"],
            dry_run=options["dry_run"],
        )
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}LOCALDATA import complete: "
                f"read={stats['read']} valid={stats['valid']} "
                f"created={stats['created']} updated={stats['updated']} "
                f"skipped={stats['skipped']} duplicates={stats['duplicates']}"
            )
        )


def import_localdata_csv(
    *,
    path,
    source,
    dataset,
    default_category,
    sync_type="full",
    encoding="auto",
    delimiter="",
    batch_size=1000,
    start_row=0,
    limit=None,
    dry_run=False,
):
    path = Path(path)
    resolved_encoding = detect_encoding(path) if encoding == "auto" else encoding
    resolved_delimiter = delimiter or detect_delimiter(path, resolved_encoding)
    checksum = calculate_sha256(path)
    stats = {
        "start_row": start_row,
        "read": 0,
        "valid": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "duplicates": 0,
    }
    sync_run = None

    if not dry_run:
        sync_run = DataSourceSyncRun.objects.create(
            source=source,
            dataset=dataset,
            sync_type=sync_type,
            source_uri=str(path),
            source_checksum=checksum,
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
                record_data = build_source_record(
                    row,
                    source=source,
                    dataset=dataset,
                    default_category=default_category,
                )
                if record_data is None:
                    stats["skipped"] += 1
                    continue
                stats["valid"] += 1
                if dry_run:
                    continue
                batch.append(SourcePlaceRecord(**record_data))
                if len(batch) >= batch_size:
                    save_batch(batch, stats)
                    batch = []

        if batch:
            save_batch(batch, stats)

        if sync_run is not None:
            sync_run.status = "succeeded"
            sync_run.stats = stats
            sync_run.completed_at = timezone.now()
            sync_run.save(update_fields=["status", "stats", "completed_at"])
        return stats
    except Exception as exc:
        if sync_run is not None:
            sync_run.status = "failed"
            sync_run.stats = stats
            sync_run.error_message = str(exc)[:4000]
            sync_run.completed_at = timezone.now()
            sync_run.save(
                update_fields=["status", "stats", "error_message", "completed_at"]
            )
        raise


def save_batch(records, stats):
    unique_records = {}
    for record in records:
        unique_records[record.source_record_id] = record
    stats["duplicates"] += len(records) - len(unique_records)
    records = list(unique_records.values())

    keys = [record.source_record_id for record in records]
    existing = set(
        SourcePlaceRecord.objects.filter(
            source=records[0].source,
            dataset=records[0].dataset,
            source_record_id__in=keys,
        ).values_list("source_record_id", flat=True)
    )
    SourcePlaceRecord.objects.bulk_create(
        records,
        batch_size=len(records),
        update_conflicts=True,
        unique_fields=["source", "dataset", "source_record_id"],
        update_fields=[
            "name",
            "category",
            "business_type",
            "business_status",
            "is_active",
            "address",
            "road_address",
            "sido_name",
            "sigungu_name",
            "administrative_code",
            "source_x",
            "source_y",
            "coordinate_reference_system",
            "license_date",
            "closed_date",
            "source_updated_at",
            "raw",
            "updated_at",
            "last_seen_at",
        ],
    )
    stats["updated"] += len(existing)
    stats["created"] += len(records) - len(existing)


def build_source_record(row, *, source, dataset, default_category):
    normalized_row = {
        clean_text(key).lstrip("\ufeff"): clean_text(value)
        for key, value in row.items()
        if key is not None
    }
    name = pick_value(normalized_row, "name")
    address = pick_value(normalized_row, "address")
    road_address = pick_value(normalized_row, "road_address")
    if not name or not (address or road_address):
        return None

    business_type = pick_value(normalized_row, "business_type")
    business_status = pick_value(normalized_row, "business_status")
    business_status_code = pick_value(normalized_row, "business_status_code")
    source_record_id = pick_value(normalized_row, "source_record_id")
    if not source_record_id:
        source_record_id = stable_record_id(name, road_address or address)

    sido_name, sigungu_name = parse_administrative_names(road_address or address)
    administrative_code = pick_value(normalized_row, "administrative_code")
    if not administrative_code:
        administrative_code = stable_region_code(sido_name, sigungu_name)

    return {
        "source": source[:50],
        "dataset": dataset[:100],
        "source_record_id": source_record_id[:160],
        "name": name[:255],
        "category": infer_category(default_category, business_type)[:100],
        "business_type": business_type[:100],
        "business_status": business_status[:50],
        "is_active": is_active_business(business_status_code, business_status),
        "address": address[:500],
        "road_address": road_address[:500],
        "sido_name": sido_name[:50],
        "sigungu_name": sigungu_name[:80],
        "administrative_code": administrative_code[:30],
        "source_x": pick_value(normalized_row, "source_x")[:50],
        "source_y": pick_value(normalized_row, "source_y")[:50],
        "coordinate_reference_system": "EPSG:5174",
        "license_date": parse_source_date(pick_value(normalized_row, "license_date")),
        "closed_date": parse_source_date(pick_value(normalized_row, "closed_date")),
        "source_updated_at": parse_source_datetime(
            pick_value(normalized_row, "source_updated_at")
        ),
        "raw": normalized_row,
    }


def pick_value(row, field):
    for key in HEADER_ALIASES[field]:
        value = row.get(key)
        if value:
            return value
    return ""


def infer_category(default_category, business_type):
    compact_type = clean_text(business_type).replace(" ", "")
    if any(term in compact_type for term in CAFE_TERMS):
        return "cafe"
    if any(term in compact_type for term in BAKERY_TERMS):
        return "bakery"
    return default_category


def is_active_business(status_code, status_name):
    if clean_text(status_code) in INACTIVE_STATUS_CODES:
        return False
    return not any(term in clean_text(status_name) for term in INACTIVE_STATUS_TERMS)


def parse_administrative_names(address):
    parts = clean_text(address).split()
    if not parts:
        return "", ""
    sido_name = parts[0]
    sigungu_name = ""
    if len(parts) > 1 and parts[1].endswith(("시", "군", "구")):
        sigungu_name = parts[1]
    if sido_name == "세종특별자치시":
        sigungu_name = sido_name
    return sido_name, sigungu_name


def parse_source_date(value):
    text = clean_text(value)
    if not text:
        return None
    digits = "".join(character for character in text if character.isdigit())
    try:
        if len(digits) >= 8:
            return parse_date(f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}")
        return parse_date(text)
    except (TypeError, ValueError):
        return None


def parse_source_datetime(value):
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = parse_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        digits = "".join(character for character in text if character.isdigit())
        if len(digits) >= 14:
            parsed = parse_datetime(
                f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
                f"T{digits[8:10]}:{digits[10:12]}:{digits[12:14]}"
            )
        elif len(digits) >= 8:
            parsed_date = parse_source_date(text)
            if parsed_date is not None:
                parsed = timezone.datetime.combine(parsed_date, timezone.datetime.min.time())
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def stable_record_id(name, address):
    value = f"{clean_text(name)}|{clean_text(address)}"
    return f"generated:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:32]}"


def stable_region_code(sido_name, sigungu_name):
    value = f"{sido_name}|{sigungu_name}"
    return f"name:{hashlib.sha1(value.encode('utf-8')).hexdigest()[:20]}"


def calculate_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_encoding(path):
    sample = Path(path).read_bytes()[:65536]
    for encoding in ("utf-8-sig", "cp949"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    raise CommandError("CSV encoding must be UTF-8 or CP949.")


def detect_delimiter(path, encoding):
    with Path(path).open("r", encoding=encoding, newline="") as handle:
        sample = handle.read(65536)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t|").delimiter
    except csv.Error:
        return ","


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()
