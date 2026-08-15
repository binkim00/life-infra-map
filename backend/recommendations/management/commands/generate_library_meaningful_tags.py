import hashlib
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_date

from recommendations.models import PlaceTag, PlaceTagEvidence, SourcePlaceRecord, Tag


CATALOG_URL = "https://www.data.go.kr/data/15013109/standard.do"


class Command(BaseCommand):
    help = "Generate confirmed library attributes from official standard fields."

    def add_arguments(self, parser):
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--large-seat-threshold", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        queryset = SourcePlaceRecord.objects.filter(
            source="data_go_kr",
            dataset="library_standard",
            is_active=True,
            normalized_place__isnull=False,
            id__gt=max(0, options["after_id"]),
        ).select_related("normalized_place").order_by("id")
        if options["limit"] is not None:
            queryset = queryset[: options["limit"]]
        stats = {"read": 0, "tags": 0, "last_id": options["after_id"]}
        for record in queryset.iterator(chunk_size=max(1, options["batch_size"])):
            stats["read"] += 1
            stats["last_id"] = record.id
            attributes = library_attributes(
                record.raw,
                large_seat_threshold=max(1, options["large_seat_threshold"]),
            )
            stats["tags"] += len(attributes)
            if not options["dry_run"]:
                for tag_name, field_name, value in attributes:
                    save_library_tag(record, tag_name, field_name, value)
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Library tags complete: read={stats['read']} tags={stats['tags']} "
            f"last_id={stats['last_id']}"
        ))


def library_attributes(raw, *, large_seat_threshold=100):
    raw = raw if isinstance(raw, dict) else {}
    attributes = []
    weekday_close = parse_clock(raw.get("weekday_close"))
    if weekday_close and weekday_close >= time(21, 0):
        attributes.append(("야간운영", "weekday_close", raw.get("weekday_close")))
    if valid_opening_range(raw.get("saturday_open"), raw.get("saturday_close")):
        attributes.append(("토요일운영", "saturday_hours", f"{raw.get('saturday_open')}-{raw.get('saturday_close')}"))
    if valid_opening_range(raw.get("holiday_open"), raw.get("holiday_close")):
        attributes.append(("공휴일운영", "holiday_hours", f"{raw.get('holiday_open')}-{raw.get('holiday_close')}"))
    try:
        seats = int(raw.get("seat_count") or 0)
    except (TypeError, ValueError):
        seats = 0
    if seats >= large_seat_threshold:
        attributes.append(("열람좌석많음", "seat_count", seats))
    return attributes


def parse_clock(value):
    text = str(value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def valid_opening_range(open_value, close_value):
    opens = parse_clock(open_value)
    closes = parse_clock(close_value)
    if not opens or not closes:
        return False
    return not (opens == time.min and closes == time.min) and opens != closes


def evidence_times(record):
    raw = record.raw if isinstance(record.raw, dict) else {}
    reference_date = parse_date(str(raw.get("reference_date") or ""))
    if reference_date:
        observed = timezone.make_aware(datetime.combine(reference_date, time.min))
    else:
        observed = record.source_updated_at or timezone.now()
    return observed, observed + timedelta(days=400)


def save_library_tag(record, tag_name, field_name, value):
    tag, _ = Tag.objects.get_or_create(
        name=tag_name,
        defaults={"tag_type": "recommendation", "description": "전국도서관표준데이터 공식 필드"},
    )
    evidence = f"전국도서관표준데이터 {field_name}={value}"
    observed_at, expires_at = evidence_times(record)
    PlaceTag.objects.update_or_create(
        place=record.normalized_place,
        tag=tag,
        source="external_data",
        defaults={
            "status": "confirmed",
            "confidence": 90,
            "evidence": evidence,
            "is_verified": True,
            "verified_at": timezone.now(),
        },
    )
    reference = f"{CATALOG_URL}#{record.source_record_id}:{field_name}"
    key = hashlib.sha256(reference.encode("utf-8")).hexdigest()
    PlaceTagEvidence.objects.update_or_create(
        evidence_key=key,
        defaults={
            "place": record.normalized_place,
            "tag": tag,
            "source": "external_data",
            "source_reference": reference,
            "polarity": "positive",
            "confidence": 90,
            "evidence": evidence,
            "context": {
                "dataset": "library_standard",
                "source_record_id": record.source_record_id,
                "field": field_name,
            },
            "raw": {"value": value},
            "observed_at": observed_at,
            "expires_at": expires_at,
        },
    )
