"""Numeric collection events only; never include queries, quotes, or identities."""
import json
import logging
import time
from collections import Counter
from functools import wraps

from django.utils import timezone

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)
logger.propagate = False


def elapsed_ms(start):
    return round(max(0, time.monotonic() - start) * 1000, 3)


def emit_event(component, metrics):
    # Callers supply only the explicitly constructed numeric/schema payload.
    logger.info("collection_metrics %s", json.dumps({
        "version": 1, "component": component,
        "recorded_at": timezone.now().isoformat(), **metrics,
    }, sort_keys=True))


def observed_sleep(seconds, *, component, reason):
    started = time.monotonic()
    start_date = timezone.localdate().isoformat()
    time.sleep(seconds)
    emit_event(component, {
        "reason": reason, "start_date": start_date,
        "end_date": timezone.localdate().isoformat(),
        "requested_sleep_ms": seconds * 1000, "actual_sleep_ms": elapsed_ms(started),
    })


def extraction_counts(attempts):
    counts = Counter()
    for attempt in attempts:
        for result in attempt.get("results") or []:
            counts["search_results"] += 1
            counts["identity_matches"] += int(bool(result.get("identity_matched")))
            reason = result.get("rejection_reason")
            if reason in {"IDENTITY_MISMATCH", "SOURCE_REJECT", "NO_FEATURE", "WEAK_FEATURE"}:
                counts[reason] += 1
            for extraction in result.get("extractions") or []:
                polarity, strength = extraction.get("polarity"), extraction.get("strength")
                if polarity in {"positive", "negative", "unknown"}:
                    counts["polarity_" + polarity] += 1
                if strength in {"DIRECT", "SUPPORTING", "WEAK", "UNKNOWN", "CONTRADICTING"}:
                    counts["strength_" + strength] += 1
    return dict(counts)


def instrument_planner(function):
    @wraps(function)
    def measured(*args, **kwargs):
        started = time.monotonic()
        result = function(*args, **kwargs)
        metrics = result.setdefault("telemetry", {})
        if metrics.get("planner_path") == "bounded" and function.__name__ != "plan_bounded_jobs":
            # The bounded inner planner already emitted this event.
            return result
        metrics.update(elapsed_ms=elapsed_ms(started), version=1)
        emit_event("planner", {"cycle_date": kwargs["cycle_date"].isoformat(),
                              "places": result["places"], **metrics})
        return result
    return measured
