from collections import defaultdict


DEFAULT_WEIGHTS = {
    "seoul_cafe": 45,
    "busan_cafe": 15,
    "high_quality_restaurant": 10,
    "targeted_sparse": 15,
    "stale_refresh": 10,
    "exploration": 5,
}


def collection_bucket(place, context):
    if context.get("stale_refresh_tags"):
        return "stale_refresh"
    if context.get("targeted_tags"):
        return "targeted_sparse"
    if place.category == "restaurant":
        return "high_quality_restaurant"
    if place.category == "cafe" and str(place.address or "").startswith("서울"):
        return "seoul_cafe"
    if place.category == "cafe" and str(place.address or "").startswith("부산"):
        return "busan_cafe"
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
    for item in deferred:
        calls = request_count(item[1])
        if total + calls > budget:
            continue
        selected.append(item)
        used[item[1]["budget_bucket"]] += calls
        total += calls
    return selected, dict(used)
