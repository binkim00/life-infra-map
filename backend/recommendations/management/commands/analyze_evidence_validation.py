import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


LABEL_FIELDS = (
    "identity_correct",
    "evidence_about_place",
    "tag_supported",
    "polarity_correct",
)
TRUE_VALUES = {"1", "true", "yes", "y", "o", "맞음", "정확", "정답"}
FALSE_VALUES = {"0", "false", "no", "n", "x", "틀림", "부정확", "오답"}
AMBIGUOUS_VALUES = {"?", "unknown", "ambiguous", "unclear", "애매", "모름", "판단불가"}


class Command(BaseCommand):
    help = "Analyze human-entered identity/evidence/tag/polarity validation labels without modifying the CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--json-output", default="")

    def handle(self, *args, **options):
        path = Path(options["csv_path"]).resolve()
        if not path.exists():
            raise CommandError(f"Validation CSV not found: {path}")
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = [field for field in LABEL_FIELDS if field not in (reader.fieldnames or ())]
            if missing:
                raise CommandError("Missing validation columns: {}".format(", ".join(missing)))
            rows = list(reader)

        report = analyze_rows(rows)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(rendered)
        if options["json_output"]:
            output = Path(options["json_output"]).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")


def analyze_rows(rows):
    parsed_rows = []
    ambiguous_cells = 0
    for row in rows:
        labels = {}
        for field in LABEL_FIELDS:
            value = parse_label(row.get(field))
            labels[field] = value
            ambiguous_cells += value == "ambiguous"
        parsed_rows.append((row, labels))

    reviewed = [(row, labels) for row, labels in parsed_rows if any(v is not None for v in labels.values())]
    false_positive_rows = [
        row for row, labels in reviewed
        if row.get("sample_type") == "accepted_evidence"
        and any(value is False for value in labels.values())
    ]
    false_negative_rows = [
        row for row, labels in reviewed
        if row.get("sample_type") == "rejected_identity" and labels["identity_correct"] is True
    ]
    error_types = Counter()
    for row, labels in reviewed:
        if row.get("sample_type") == "accepted_evidence":
            for field, value in labels.items():
                if value is False:
                    error_types[field] += 1
        elif labels["identity_correct"] is True:
            reason = row.get("diagnostic_reason") or "OTHER"
            error_types[f"false_negative/{reason}"] += 1

    return {
        "rows_in_file": len(rows),
        "reviewed_rows": len(reviewed),
        "metrics": metric_summary(reviewed),
        "by_category": grouped_metrics(reviewed, lambda row: row.get("category") or "(blank)"),
        "by_source": grouped_metrics(reviewed, lambda row: row.get("evidence_source") or "(blank)"),
        "by_confidence": grouped_metrics(reviewed, confidence_bucket),
        "false_positive_cases": len(false_positive_rows),
        "false_negative_cases": len(false_negative_rows),
        "ambiguous_label_cells": ambiguous_cells,
        "major_error_types": dict(error_types.most_common()),
    }


def parse_label(value):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    if normalized in AMBIGUOUS_VALUES:
        return "ambiguous"
    return "ambiguous"


def metric_summary(reviewed):
    names = {
        "identity_correct": "identity_precision",
        "evidence_about_place": "evidence_relevance_precision",
        "tag_supported": "tag_precision",
        "polarity_correct": "polarity_accuracy",
    }
    metrics = {}
    for field, name in names.items():
        values = [labels[field] for _, labels in reviewed if labels[field] in {True, False}]
        correct = sum(value is True for value in values)
        metrics[name] = {
            "reviewed": len(values),
            "correct": correct,
            "rate": round(correct / len(values), 4) if values else None,
        }
    return metrics


def grouped_metrics(reviewed, key):
    groups = defaultdict(list)
    for row, labels in reviewed:
        groups[key(row)].append((row, labels))
    return {name: metric_summary(group) for name, group in sorted(groups.items())}


def confidence_bucket(row):
    raw = row.get("evidence_confidence") or row.get("identity_score")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return "unknown"
    if value < 50:
        return "0-49"
    if value < 65:
        return "50-64"
    if value < 80:
        return "65-79"
    return "80-100"
