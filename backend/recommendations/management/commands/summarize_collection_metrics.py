"""Aggregate a selected local event stream without copying raw log content."""
import json
import math
import sys
from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

COMPONENTS = {"planner", "worker", "worker_attempt", "worker_checkpoint", "scheduler_queue"}
NUMERIC_FIELDS = {
    "places", "scanned", "unique_candidates", "candidates", "elapsed_ms", "claim_ms",
    "queue_depth", "queue_backpressure", "daily_cap", "evidences", "new_evidences", "requests",
    "actual_sleep_ms", "requested_sleep_ms", "budget_blocked", "budget_selection_dropped",
    "candidate_shortfall", "selected_before_budget", "selected_after_budget",
    "resumed_checkpoint", "settled_now",
}
NESTED_FIELDS = {
    "timings_ms": {"claim_ms", "structured_ms", "collector_ms", "settle_ms", "save_and_finalize_ms", "processing_ms"},
    "quality_at_save": {"expired", "reused", "active_positive", "active_accepted", "active_positive_accepted"},
    "reasons": {"considered", "recent", "category_mismatch", "category_cap", "region_cap", "region_mismatch",
                "candidate_visits", "requested_cap", "cooldown", "quota_budget", "daily_cap",
                "budget_selection_dropped", "final_selection_cap", "request_budget", "lock_busy", "deadline_or_sql_timeout"},
}


def summarize(lines):
    groups = {}
    ignored = 0
    for line in lines:
        try:
            event = json.loads(line.split("collection_metrics ", 1)[-1])
            if not isinstance(event, dict) or event.get("component") not in COMPONENTS:
                raise ValueError()
            at = parse_datetime(event["recorded_at"])
            if at is None or timezone.is_naive(at):
                raise ValueError()
            key = (timezone.localdate(at).isoformat(), event["component"])
        except (ValueError, TypeError, KeyError, AttributeError):
            ignored += 1
            continue
        totals = groups.setdefault(key, Counter())
        totals["events"] += 1
        for field in NUMERIC_FIELDS:
            value = event.get(field)
            if type(value) in {int, float} and math.isfinite(value) and value >= 0:
                totals[field] += value
        for field, allowed in NESTED_FIELDS.items():
            values = event.get(field)
            if isinstance(values, dict):
                for name in allowed:
                    value = values.get(name)
                    if type(value) in {int, float} and math.isfinite(value) and value >= 0:
                        totals[field + "." + name] += value
    return {"basis": "event recorded_at local date; whole durations assigned to event end date",
            "ignored_lines": ignored, "groups": [
                {"date": day, "component": component, "totals": dict(totals)}
                for (day, component), totals in sorted(groups.items())
            ]}


class Command(BaseCommand):
    help = "Sum numeric collection_metrics events from stdin; never echo other logs."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(summarize(sys.stdin), sort_keys=True))
