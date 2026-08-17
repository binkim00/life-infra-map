from collections import defaultdict


DEFAULT_WEIGHTS = {
    "candidate_hint": 45,
    "cafe_discovery": 25,
    "no_tag_targeted": 15,
    "high_quality_restaurant": 5,
    "stale_refresh": 1,
    "exploration": 9,
}

BUCKET_FALLBACK_ORDER = (
    "candidate_hint",
    "cafe_discovery",
    "no_tag_targeted",
    "high_quality_restaurant",
    "exploration",
    "stale_refresh",
)


def collection_bucket(place, context):
    reason = context.get("adaptive_reason")
    if reason == "candidate_hint":
        return "candidate_hint"
    if reason == "no_tag_expression":
        return "no_tag_targeted"
    if reason == "stale_refresh":
        return "stale_refresh"
    if place.category == "restaurant":
        return "high_quality_restaurant"
    if place.category == "cafe":
        return "cafe_discovery"
    return "exploration"


def yield_adjusted_weights(base_weights, history, *, minimum_calls=200):
    """Adjust only after a bucket has enough calls; sparse history stays neutral."""
    weights = dict(base_weights or DEFAULT_WEIGHTS)
    measured = {
        key: values.get("active_evidence", values["evidence"]) / values["calls"]
        for key, values in history.items()
        if values.get("calls", 0) >= minimum_calls
    }
    if not measured:
        return weights
    baseline = sum(measured.values()) / len(measured)
    if baseline <= 0:
        return weights
    for key, evidence_yield in measured.items():
        multiplier = max(0.5, min(1.5, evidence_yield / baseline))
        weights[key] = max(1, round(weights.get(key, 1) * multiplier))
    return weights


def allocate_by_request_budget(candidates, *, budget, weights, request_count):
    total_weight = max(1, sum(weights.values()))
    caps = {key: budget * value / total_weight for key, value in weights.items()}
    used = defaultdict(int)
    selected = []
    deferred = []
    for item in candidates:
        place, context = item
        bucket = context["budget_bucket"]
        calls = request_count(context)
        if used[bucket] + calls <= caps.get(bucket, 0):
            selected.append(item)
            used[bucket] += calls
        else:
            deferred.append(item)
    total = sum(used.values())
    fallback_rank = {key: index for index, key in enumerate(BUCKET_FALLBACK_ORDER)}
    deferred.sort(key=lambda item: (
        fallback_rank.get(item[1]["budget_bucket"], len(fallback_rank)),
        -int(item[1].get("score") or 0),
        getattr(item[0], "id", 0),
    ))
    for item in deferred:
        calls = request_count(item[1])
        if total + calls > budget:
            continue
        selected.append(item)
        used[item[1]["budget_bucket"]] += calls
        total += calls
    return selected, dict(used)


def recommend_scaled_budget(cycles, *, current_budget, minimum_yield=0.05):
    """Recommend a conservative next-cycle request budget from three real cycles."""
    rows = list(cycles or [])[:3]
    if len(rows) < 3:
        return {"recommended_budget": current_budget, "action": "hold", "reason": "insufficient_history"}
    calls = sum(max(0, int(row.get("calls") or 0)) for row in rows)
    active = sum(max(0, int(row.get("active_evidence") or 0)) for row in rows)
    failures = sum(max(0, int(row.get("failures") or 0)) for row in rows)
    rate_limited = sum(max(0, int(row.get("rate_limited") or 0)) for row in rows)
    active_yield = active / calls if calls else 0
    failure_rate = failures / calls if calls else 0
    if rate_limited or failure_rate > 0.02 or active_yield < minimum_yield:
        return {
            "recommended_budget": max(100, round(current_budget * 0.75)),
            "action": "decrease",
            "reason": "rate_limit_or_low_yield",
            "active_per_call": round(active_yield, 4),
        }
    return {
        "recommended_budget": round(current_budget * 1.2),
        "action": "increase",
        "reason": "three_stable_cycles",
        "active_per_call": round(active_yield, 4),
    }
