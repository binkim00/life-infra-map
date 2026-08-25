"""Turn launch-search quality gaps into idempotent place/tag research demand."""

import hashlib
import json
from collections import Counter, defaultdict

from django.db import transaction

from recommendations.models import Place, TagEnrichmentRequest
from recommendations.services.tag_enrichment_queue import normalize_subjective_tags
from recommendations.services.web_tag_evidence_provider import CATEGORY_TAGS


TOP_N = 5
RECENT_FINGERPRINT_LIMIT = 14


def evaluation_fingerprint(payload):
    stable = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]


def _values(items):
    if not isinstance(items, list):
        items = [items] if items else []
    values = []
    for item in items:
        value = item.get("value") if isinstance(item, dict) else item
        value = str(value or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def _numeric_result_id(result):
    value = str(result.get("id") or "").strip()
    return int(value) if value.isdigit() else None


def _resolve_place(result, *, places_by_id, exact_places, unique_name_places):
    if str(result.get("source") or "").lower() != "db":
        return None
    numeric_id = _numeric_result_id(result)
    if numeric_id is not None:
        place = places_by_id.get(numeric_id)
        if place:
            return place
    name = str(result.get("name") or "").strip()
    category = str(result.get("category") or "").strip()
    address = str(result.get("address") or "").strip()
    if not name or category not in CATEGORY_TAGS:
        return None
    if address:
        exact = exact_places.get((name, category, address))
        if exact:
            return exact
    return unique_name_places.get((name, category))


def _place_lookup(scanned_rows):
    numeric_ids = {
        _numeric_result_id(result)
        for _case_id, _constraints, _rank, result in scanned_rows
        if str(result.get("source") or "").lower() == "db"
        and _numeric_result_id(result) is not None
    }
    places_by_id = Place.objects.in_bulk(numeric_ids)
    fallback_rows = [
        result for _case_id, _constraints, _rank, result in scanned_rows
        if str(result.get("source") or "").lower() == "db"
        and _numeric_result_id(result) not in places_by_id
    ]
    names = {str(result.get("name") or "").strip() for result in fallback_rows}
    categories = {str(result.get("category") or "").strip() for result in fallback_rows}
    candidates = list(Place.objects.filter(name__in=names, category__in=categories)) if names else []
    exact_places = {}
    by_name = defaultdict(list)
    for place in candidates:
        exact_places[(place.name, place.category, str(place.address or "").strip())] = place
        by_name[(place.name, place.category)].append(place)
    unique_name_places = {
        key: rows[0] for key, rows in by_name.items() if len(rows) == 1
    }
    return places_by_id, exact_places, unique_name_places


def extract_launch_demands(payload, *, top_n=TOP_N):
    """Aggregate missing canonical tags for DB places exposed by launch cases."""
    demands = defaultdict(lambda: {
        "place": None, "tags": defaultdict(lambda: {"rank_score": 0, "signals": 0, "cases": set()}),
    })
    scanned_rows = []
    for case in payload.get("results") or []:
        case_id = str(case.get("case_id") or case.get("id") or "")[:100]
        frame_constraints = _values((case.get("frame") or {}).get("constraints"))
        for rank, result in enumerate((case.get("top_results") or [])[:top_n], start=1):
            scanned_rows.append((case_id, frame_constraints, rank, result))
    places_by_id, exact_places, unique_name_places = _place_lookup(scanned_rows)
    unresolved = 0
    for case_id, frame_constraints, rank, result in scanned_rows:
        place = _resolve_place(
            result,
            places_by_id=places_by_id,
            exact_places=exact_places,
            unique_name_places=unique_name_places,
        )
        if not place:
            unresolved += 1
            continue
        raw_gaps = [
            *_values(result.get("missing_conditions")),
            *_values(result.get("unverified_conditions")),
        ]
        if not raw_gaps and result.get("result_tier") == "best_available":
            raw_gaps = frame_constraints
        tags = [
            tag for tag in normalize_subjective_tags(raw_gaps)
            if tag in CATEGORY_TAGS.get(place.category, ())
        ]
        for tag in dict.fromkeys(tags):
            item = demands[place.id]
            item["place"] = place
            signal = item["tags"][tag]
            signal["rank_score"] += max(1, top_n + 1 - rank)
            signal["signals"] += 1
            if case_id:
                signal["cases"].add(case_id)
    return demands, {"scanned_results": len(scanned_rows), "unresolved_results": unresolved}


def prioritize_launch_evidence(payload, *, dry_run=False):
    fingerprint = evaluation_fingerprint(payload)
    demands, stats = extract_launch_demands(payload)
    created = updated = idempotent = 0
    tag_counts = Counter()
    place_scores = Counter()
    place_ids = set(demands)
    tag_names = {
        tag_name for item in demands.values() for tag_name in item["tags"]
    }
    existing_requests = {
        (request.place_id, request.tag_name): request
        for request in TagEnrichmentRequest.objects.filter(
            place_id__in=place_ids, tag_name__in=tag_names,
        )
    }

    with transaction.atomic():
        for place_id, item in demands.items():
            place = item["place"]
            for tag_name, signal in item["tags"].items():
                tag_counts[tag_name] += signal["signals"]
                place_scores[place.name] += signal["rank_score"]
                existing = existing_requests.get((place_id, tag_name))
                context = dict(existing.context or {}) if existing else {}
                launch = dict(context.get("launch_quality") or {})
                fingerprints = list(launch.get("evaluation_fingerprints") or [])
                if fingerprint in fingerprints:
                    idempotent += 1
                    continue
                fingerprints = [*fingerprints, fingerprint][-RECENT_FINGERPRINT_LIMIT:]
                launch.update({
                    "evaluation_fingerprints": fingerprints,
                    "last_evaluation_created_at": str(payload.get("created_at") or ""),
                    "case_ids": sorted(signal["cases"]),
                    "rank_score": signal["rank_score"],
                    "signal_count": signal["signals"],
                    "source": "busan_launch_quality",
                })
                context["launch_quality"] = launch
                priority_boost = min(100, 30 + signal["rank_score"])
                if dry_run:
                    created += int(existing is None)
                    updated += int(existing is not None)
                    continue
                if existing is None:
                    TagEnrichmentRequest.objects.create(
                        place=place,
                        tag_name=tag_name,
                        status="queued",
                        priority=priority_boost,
                        demand_count=signal["signals"],
                        context=context,
                    )
                    created += 1
                else:
                    existing.status = "queued"
                    existing.priority = min(100000, max(existing.priority, priority_boost) + signal["rank_score"])
                    existing.demand_count = min(100000, existing.demand_count + signal["signals"])
                    existing.next_attempt_at = None
                    existing.error_message = ""
                    existing.context = context
                    existing.save(update_fields=[
                        "status", "priority", "demand_count", "next_attempt_at",
                        "error_message", "context", "last_requested_at", "updated_at",
                    ])
                    updated += 1
        if dry_run:
            transaction.set_rollback(True)

    return {
        "evaluation_fingerprint": fingerprint,
        **stats,
        "demand_places": len(demands),
        "demand_tags": sum(len(item["tags"]) for item in demands.values()),
        "requests_created": created,
        "requests_updated": updated,
        "requests_idempotent": idempotent,
        "top_missing_tags": [
            {"tag": tag, "signals": count} for tag, count in tag_counts.most_common(10)
        ],
        "top_priority_places": [
            {"place": place, "rank_score": score} for place, score in place_scores.most_common(10)
        ],
        "dry_run": dry_run,
    }
