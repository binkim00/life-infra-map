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


def _resolve_place(result):
    if str(result.get("source") or "").lower() != "db":
        return None
    raw_id = str(result.get("id") or "").strip()
    if raw_id.isdigit():
        place = Place.objects.filter(id=int(raw_id)).first()
        if place:
            return place
    name = str(result.get("name") or "").strip()
    category = str(result.get("category") or "").strip()
    address = str(result.get("address") or "").strip()
    if not name or category not in CATEGORY_TAGS:
        return None
    matches = Place.objects.filter(name=name, category=category)
    if address:
        exact = matches.filter(address=address).first()
        if exact:
            return exact
    rows = list(matches[:2])
    return rows[0] if len(rows) == 1 else None


def extract_launch_demands(payload, *, top_n=TOP_N):
    """Aggregate missing canonical tags for DB places exposed by launch cases."""
    demands = defaultdict(lambda: {
        "place": None, "tags": defaultdict(lambda: {"rank_score": 0, "signals": 0, "cases": set()}),
    })
    unresolved = 0
    scanned = 0
    for case in payload.get("results") or []:
        case_id = str(case.get("case_id") or case.get("id") or "")[:100]
        frame_constraints = _values((case.get("frame") or {}).get("constraints"))
        for rank, result in enumerate((case.get("top_results") or [])[:top_n], start=1):
            scanned += 1
            place = _resolve_place(result)
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
    return demands, {"scanned_results": scanned, "unresolved_results": unresolved}


def prioritize_launch_evidence(payload, *, dry_run=False):
    fingerprint = evaluation_fingerprint(payload)
    demands, stats = extract_launch_demands(payload)
    created = updated = idempotent = 0
    tag_counts = Counter()
    place_scores = Counter()

    with transaction.atomic():
        for place_id, item in demands.items():
            place = item["place"]
            for tag_name, signal in item["tags"].items():
                tag_counts[tag_name] += signal["signals"]
                place_scores[place.name] += signal["rank_score"]
                existing = TagEnrichmentRequest.objects.filter(
                    place_id=place_id, tag_name=tag_name,
                ).first()
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
