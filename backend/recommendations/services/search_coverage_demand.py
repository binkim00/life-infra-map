"""Privacy-conscious search coverage signals for tag collection planning."""

import hashlib
import logging
import uuid
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from recommendations.models import PlaceInteractionEvent
from recommendations.services.tag_enrichment_queue import normalize_subjective_tags


logger = logging.getLogger(__name__)

LOW_RESULT_THRESHOLD = 3
RECENT_DEMAND_DAYS = 30
MAX_RECENT_SIGNALS = 2000


def _values(items):
    values = []
    for item in items or []:
        value = item.get("value") if isinstance(item, dict) else item
        value = str(value or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def _compact(value):
    return "".join(str(value or "").lower().split())


def _category_codes(frame):
    values = frame.get("candidate_category_codes") or frame.get("candidateCategoryCodes") or []
    return _values(values)[:10]


def _quality_gap_tags(response):
    results = response.get("results") or []
    gaps = []
    fallback_count = 0
    for result in results[:5]:
        if not isinstance(result, dict):
            continue
        tier = result.get("result_tier") or result.get("resultTier")
        if tier == "best_available":
            fallback_count += 1
        gaps.extend(
            _values(result.get("missing_conditions") or result.get("missingConditions"))
        )
        gaps.extend(
            _values(result.get("unverified_conditions") or result.get("unverifiedConditions"))
        )
    return normalize_subjective_tags(gaps), fallback_count


def record_search_coverage_demand(response, *, user=None, session_key="", search_id=""):
    """Record normalized demand without retaining the user's raw query."""
    if not isinstance(response, dict):
        return None
    action = response.get("decision_action") or response.get("decisionAction")
    if action != "search":
        return None

    frame = response.get("place_intent_frame") or response.get("placeIntentFrame") or {}
    frame = frame if isinstance(frame, dict) else {}
    result_count = int(response.get("result_count") or response.get("count") or 0)
    quality_gap_tags, top_five_fallback_count = _quality_gap_tags(response)
    sparse = result_count < LOW_RESULT_THRESHOLD
    quality_gap = bool(quality_gap_tags or top_five_fallback_count)
    if not sparse and not quality_gap:
        return None

    constraints = _values(frame.get("constraints"))
    target_objects = _values(frame.get("target_objects") or frame.get("targetObjects"))
    requested_tags = normalize_subjective_tags([
        *constraints,
        *target_objects,
        *quality_gap_tags,
    ])
    location_hint = str(frame.get("anchor_location") or "").strip()[:100]
    categories = _category_codes(frame)
    scenario = str((response.get("search_plan") or {}).get("scenario") or response.get("scenario") or "")[:50]
    normalized_key = "|".join([
        _compact(location_hint),
        ",".join(sorted(categories)),
        ",".join(sorted(requested_tags)),
        str(result_count),
    ])
    safe_search_id = str(search_id or uuid.uuid4().hex)[:64]
    safe_session_key = (
        hashlib.sha256(str(session_key).encode("utf-8")).hexdigest()
        if session_key else ""
    )
    return PlaceInteractionEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        session_key=safe_session_key,
        search_id=safe_search_id,
        event_type="search",
        query="",
        requested_tags=requested_tags,
        context={
            "signal_version": 1,
            "fingerprint": hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()[:24],
            "location_hint": location_hint,
            "category_codes": categories,
            "scenario": scenario,
            "result_count": result_count,
            "top_five_fallback_count": top_five_fallback_count,
            "quality_gap_tags": quality_gap_tags,
            "signal_reason": "sparse_results" if sparse else "top_five_quality_gap",
            "demand_weight": (
                3 if result_count == 0 else
                2 if sparse or top_five_fallback_count >= 3 else
                1
            ),
        },
    )


def coverage_demand_context(places, *, now=None):
    """Return per-place boosts and requested tags from recent sparse searches."""
    now = now or timezone.now()
    signals = list(
        PlaceInteractionEvent.objects.filter(
            event_type="search",
            created_at__gte=now - timedelta(days=RECENT_DEMAND_DAYS),
            context__signal_version=1,
        ).order_by("-created_at").values("requested_tags", "context")[:MAX_RECENT_SIGNALS]
    )
    by_category = defaultdict(list)
    global_signals = []
    for signal in signals:
        context = signal.get("context") or {}
        row = {
            "location": _compact(context.get("location_hint")),
            "weight": max(1, min(3, int(context.get("demand_weight") or 1))),
            "tags": set(_values(signal.get("requested_tags"))),
        }
        categories = _values(context.get("category_codes"))
        if categories:
            for category in categories:
                by_category[category].append(row)
        else:
            global_signals.append(row)

    result = {}
    for place in places:
        haystack = _compact(" ".join([place.name, place.address, place.detail_location]))
        score = 0
        tags = set()
        for signal in [*by_category.get(place.category, []), *global_signals]:
            location = signal["location"]
            if location and location not in haystack:
                continue
            score += signal["weight"]
            tags.update(signal["tags"])
        result[place.id] = {"score": min(30, score), "targeted_tags": tags}
    return result


def safe_record_search_coverage_demand(*args, **kwargs):
    try:
        return record_search_coverage_demand(*args, **kwargs)
    except Exception:
        logger.warning("Failed to record normalized search coverage demand.", exc_info=True)
        return None
