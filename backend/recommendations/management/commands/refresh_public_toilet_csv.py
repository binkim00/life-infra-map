import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date, parse_datetime

from recommendations.management.commands.import_localdata_records import detect_delimiter, detect_encoding
from recommendations.models import Place


MANAGEMENT_ID = "관리번호"
NAME = "화장실명"
ROAD_ADDRESS = "소재지도로명주소"
LOT_ADDRESS = "소재지지번주소"
REFERENCE_DATE = "데이터기준일자"
FINAL_MODIFIED_AT = "최종수정시점"
DATA_UPDATED_AT = "데이터갱신시점"


class Command(BaseCommand):
    help = "Refresh existing public-toilet Places from an official CSV without deleting Evidence or creating coordinate-less Places."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--encoding", default="auto")
        parser.add_argument("--delimiter", default="")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--report", default="")

    def handle(self, *args, **options):
        path = Path(options["path"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"File does not exist: {path}")
        report = refresh_toilets(
            path,
            encoding=options["encoding"],
            delimiter=options["delimiter"],
            limit=options["limit"],
            batch_size=max(1, options["batch_size"]),
            dry_run=options["dry_run"],
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(rendered)
        if options["report"]:
            output = Path(options["report"]).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")


def refresh_toilets(path, *, encoding="auto", delimiter="", limit=None, batch_size=1000, dry_run=False):
    path = Path(path)
    resolved_encoding = detect_encoding(path) if encoding == "auto" else encoding
    resolved_delimiter = delimiter or detect_delimiter(path, resolved_encoding)
    place_map = {
        place.external_id: place
        for place in Place.objects.filter(source="public_toilet_standard").only(
            "id", "external_id", "name", "address", "detail_location", "source_name", "source_updated_at", "raw"
        )
    }
    stats = Counter()
    examples = {"matched": [], "unmatched": [], "duplicate_source_id": []}
    updates = []
    seen = set()

    def flush():
        nonlocal updates
        if updates and not dry_run:
            Place.objects.bulk_update(
                updates,
                ["name", "address", "detail_location", "source_name", "source_updated_at", "raw", "updated_at"],
                batch_size=batch_size,
            )
        updates = []

    with path.open("r", encoding=resolved_encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=resolved_delimiter)
        required = {MANAGEMENT_ID, NAME}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise CommandError("Official toilet CSV headers are missing.")
        for row in reader:
            if limit is not None and stats["read"] >= limit:
                break
            stats["read"] += 1
            cleaned = {str(key or "").lstrip("\ufeff").strip(): str(value or "").strip() for key, value in row.items()}
            source_id = cleaned.get(MANAGEMENT_ID, "")
            if not source_id:
                stats["rejected_missing_id"] += 1
                continue
            external_id = f"toilet_{source_id}"
            if external_id in seen:
                stats["duplicate_source_id"] += 1
                if len(examples["duplicate_source_id"]) < 5:
                    examples["duplicate_source_id"].append(source_id)
                continue
            seen.add(external_id)
            place = place_map.get(external_id)
            if place is None:
                stats["unmatched"] += 1
                if len(examples["unmatched"]) < 10:
                    examples["unmatched"].append({"management_id": source_id, "name": cleaned.get(NAME), "address": cleaned.get(ROAD_ADDRESS) or cleaned.get(LOT_ADDRESS)})
                continue
            stats["matched"] += 1
            observed_date = source_observed_date(cleaned)
            old_date = place.source_updated_at
            if observed_date and (old_date is None or observed_date > old_date):
                stats["date_advanced"] += 1
            raw = dict(place.raw) if isinstance(place.raw, dict) else {}
            raw.update(cleaned)
            raw["source_file"] = path.name
            raw["source_identity"] = {"management_id": source_id}
            name = cleaned.get(NAME) or place.name
            address = cleaned.get(ROAD_ADDRESS) or cleaned.get(LOT_ADDRESS) or place.address
            place.name = name[:200]
            place.address = address[:255]
            place.detail_location = address[:255]
            place.source_name = "공중화장실정보"
            place.source_updated_at = observed_date or old_date
            place.raw = raw
            updates.append(place)
            if len(examples["matched"]) < 10:
                examples["matched"].append({"place_id": place.id, "management_id": source_id, "name": name, "observed_date": str(observed_date or "")})
            if len(updates) >= batch_size:
                flush()
    flush()
    stats["existing_places"] = len(place_map)
    stats["source_ids"] = len(seen)
    stats["mode"] = "dry-run" if dry_run else "commit"
    return {"stats": dict(stats), "examples": examples, "encoding": resolved_encoding, "delimiter": resolved_delimiter}


def source_observed_date(row):
    values = []
    reference = parse_date(str(row.get(REFERENCE_DATE) or "").strip())
    if reference:
        values.append(reference)
    for key in (FINAL_MODIFIED_AT, DATA_UPDATED_AT):
        text = str(row.get(key) or "").strip().replace(" ", "T", 1)
        parsed = parse_datetime(text)
        if parsed:
            values.append(parsed.date())
    return max(values) if values else None

