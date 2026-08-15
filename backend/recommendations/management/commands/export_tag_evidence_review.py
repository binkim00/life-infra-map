import csv
import json
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence, TagEnrichmentRequest


CSV_FIELDS = (
    "evidence_id",
    "place_id",
    "place_name",
    "address",
    "tag",
    "polarity",
    "source_url",
    "evidence",
    "confidence",
    "observed_at",
    "expires_at",
    "is_expired",
    "manual_correct",
    "manual_note",
)
TRUE_LABELS = {"1", "true", "yes", "y", "correct", "accept", "accepted", "맞음", "채택"}
FALSE_LABELS = {"0", "false", "no", "n", "incorrect", "reject", "rejected", "틀림", "거절"}


class Command(BaseCommand):
    help = "Export subjective evidence for review and calculate per-tag quality metrics."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tmp/tag_evidence_review.csv")
        parser.add_argument("--report", default="tmp/tag_evidence_review_report.json")
        parser.add_argument("--labels", default="", help="Reviewed CSV containing evidence_id and manual_correct.")
        parser.add_argument("--source", default="ai_suggested")
        parser.add_argument("--tag", action="append", default=[])
        parser.add_argument("--include-expired", action="store_true")
        parser.add_argument("--limit", type=int)

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 1:
            raise CommandError("--limit must be at least 1.")
        labels = load_manual_labels(options["labels"]) if options["labels"] else {}
        now = timezone.now()
        queryset = PlaceTagEvidence.objects.filter(source=options["source"]).select_related(
            "place", "tag"
        ).order_by("tag__name", "place_id", "-observed_at", "id")
        if options["tag"]:
            queryset = queryset.filter(tag__name__in=options["tag"])
        if not options["include_expired"]:
            queryset = queryset.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        if options["limit"] is not None:
            queryset = queryset[: options["limit"]]
        evidences = list(queryset)

        output_path = resolve_output_path(options["output"])
        report_path = resolve_output_path(options["report"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for evidence in evidences:
                label = labels.get(str(evidence.id), {})
                writer.writerow({
                    "evidence_id": evidence.id,
                    "place_id": evidence.place_id,
                    "place_name": evidence.place.name,
                    "address": evidence.place.address,
                    "tag": evidence.tag.name,
                    "polarity": evidence.polarity,
                    "source_url": evidence.source_reference,
                    "evidence": evidence.evidence,
                    "confidence": evidence.confidence,
                    "observed_at": evidence.observed_at.isoformat() if evidence.observed_at else "",
                    "expires_at": evidence.expires_at.isoformat() if evidence.expires_at else "",
                    "is_expired": bool(evidence.expires_at and evidence.expires_at <= now),
                    "manual_correct": label.get("raw", ""),
                    "manual_note": label.get("note", ""),
                })

        report = build_report(evidences, labels=labels, source=options["source"])
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(
            f"Evidence review exported: rows={len(evidences)} output={output_path} "
            f"report={report_path} precision={report['overall']['manual_precision']}"
        ))


def resolve_output_path(value):
    return Path(value).expanduser().resolve()


def parse_manual_correct(value):
    normalized = str(value or "").strip().lower()
    if normalized in TRUE_LABELS:
        return True
    if normalized in FALSE_LABELS:
        return False
    return None


def load_manual_labels(path_value):
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise CommandError(f"Labels CSV does not exist: {path}")
    labels = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"evidence_id", "manual_correct"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise CommandError("Labels CSV requires evidence_id and manual_correct columns.")
        for row in reader:
            evidence_id = str(row.get("evidence_id") or "").strip()
            parsed = parse_manual_correct(row.get("manual_correct"))
            if evidence_id and parsed is not None:
                labels[evidence_id] = {
                    "correct": parsed,
                    "raw": row.get("manual_correct") or "",
                    "note": row.get("manual_note") or "",
                }
    return labels


def build_report(evidences, *, labels, source):
    now = timezone.now()
    by_tag = defaultdict(list)
    for evidence in evidences:
        by_tag[evidence.tag.name].append(evidence)

    insufficient = TagEnrichmentRequest.objects.filter(
        status="completed",
        error_message__icontains="insufficient",
    )
    completed = TagEnrichmentRequest.objects.filter(status="completed")
    tag_reports = {}
    total_pairs = set()
    total_conflicts = set()
    total_reviewed = 0
    total_correct = 0
    for tag_name, rows in sorted(by_tag.items()):
        pairs = {(row.place_id, row.tag_id) for row in rows}
        positive_pairs = {(row.place_id, row.tag_id) for row in rows if row.polarity == "positive"}
        negative_pairs = {(row.place_id, row.tag_id) for row in rows if row.polarity == "negative"}
        conflicts = positive_pairs & negative_pairs
        adopted_pairs = set(PlaceTag.objects.filter(
            place_id__in={pair[0] for pair in positive_pairs},
            tag__name=tag_name,
            source=source,
        ).values_list("place_id", "tag_id"))
        reviewed = [
            labels[str(row.id)]["correct"]
            for row in rows
            if str(row.id) in labels
        ]
        correct = sum(1 for value in reviewed if value)
        tag_completed = completed.filter(tag_name=tag_name).count()
        tag_insufficient = insufficient.filter(tag_name=tag_name).count()
        tag_reports[tag_name] = {
            "evidence_count": len(rows),
            "place_tag_pairs": len(pairs),
            "positive_count": sum(1 for row in rows if row.polarity == "positive"),
            "negative_count": sum(1 for row in rows if row.polarity == "negative"),
            "adoption_rate": ratio(len(adopted_pairs & positive_pairs), len(positive_pairs)),
            "conflict_rate": ratio(len(conflicts), len(pairs)),
            "no_evidence_rate": ratio(tag_insufficient, tag_completed),
            "manual_reviewed": len(reviewed),
            "manual_precision": ratio(correct, len(reviewed)),
            "expired_count": sum(1 for row in rows if row.expires_at and row.expires_at <= now),
        }
        total_pairs |= pairs
        total_conflicts |= conflicts
        total_reviewed += len(reviewed)
        total_correct += correct

    completed_count = completed.count()
    insufficient_count = insufficient.count()
    return {
        "generated_at": now.isoformat(),
        "source": source,
        "overall": {
            "evidence_count": len(evidences),
            "place_tag_pairs": len(total_pairs),
            "conflict_rate": ratio(len(total_conflicts), len(total_pairs)),
            "no_evidence_count": insufficient_count,
            "completed_request_count": completed_count,
            "no_evidence_rate": ratio(insufficient_count, completed_count),
            "manual_reviewed": total_reviewed,
            "manual_precision": ratio(total_correct, total_reviewed),
        },
        "tags": tag_reports,
    }


def ratio(numerator, denominator):
    if not denominator:
        return None
    return round(numerator / denominator, 4)
