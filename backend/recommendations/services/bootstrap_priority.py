from collections import defaultdict

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence, TagEnrichmentRequest
from recommendations.services.place_tag_collection import requested_tags_for_category


TIER_1_PREFIXES = ("서울", "부산")
TIER_2_PREFIXES = ("인천", "대구", "대전", "광주", "울산")
TIER_3_CITIES = ("수원", "용인", "고양", "성남", "창원")


def place_region_tier(place):
    location = "{} {}".format(place.address or "", place.detail_location or "").strip()
    if location.startswith(TIER_1_PREFIXES):
        return 1
    if location.startswith(TIER_2_PREFIXES):
        return 2
    if any(city in location for city in TIER_3_CITIES):
        return 3
    return 4


def parse_tier_weights(value):
    try:
        weights = [max(0, int(item.strip())) for item in str(value).split(",")]
    except (TypeError, ValueError):
        weights = []
    if len(weights) != 4 or not sum(weights):
        return (70, 15, 10, 5)
    return tuple(weights)


def priority_context(places, *, category_priorities=None, now=None):
    now = now or timezone.now()
    place_ids = [place.id for place in places]
    evidence = {
        row["place_id"]: row
        for row in PlaceTagEvidence.objects.filter(place_id__in=place_ids).values("place_id").annotate(
            active_count=Count("id", filter=Q(expires_at__isnull=True) | Q(expires_at__gt=now)),
            active_tags=Count(
                "tag_id",
                distinct=True,
                filter=Q(expires_at__isnull=True) | Q(expires_at__gt=now),
            ),
            latest_observed=Max("observed_at"),
            expired_count=Count("id", filter=Q(expires_at__lte=now)),
        )
    }
    conflicts = dict(
        PlaceTag.objects.filter(
            place_id__in=place_ids,
            status="needs_verification",
        ).values_list("place_id").annotate(n=Count("id"))
    )
    demands = dict(
        TagEnrichmentRequest.objects.filter(place_id__in=place_ids).values_list("place_id").annotate(
            n=Sum("demand_count")
        )
    )
    category_priorities = category_priorities or {}
    results = {}
    for place in places:
        stats = evidence.get(place.id, {})
        relevant_tag_count = len(requested_tags_for_category(place.category))
        active_tags = int(stats.get("active_tags") or 0)
        coverage_gap = max(0, relevant_tag_count - active_tags)
        evidence_gap = 20 if not stats.get("active_count") else 0
        freshness_gap = 0
        latest = stats.get("latest_observed")
        if not latest:
            freshness_gap = 15
        elif (now - latest).days >= 90:
            freshness_gap = min(15, 5 + (now - latest).days // 90 * 3)
        conflict_priority = min(20, int(conflicts.get(place.id, 0)) * 8)
        search_demand = min(20, int(demands.get(place.id, 0) or 0))
        data_quality_need = max(0, min(10, round((100 - place.data_quality_score) / 10)))
        components = {
            "region": {1: 30, 2: 20, 3: 12, 4: 5}[place_region_tier(place)],
            "category": int(category_priorities.get(place.category, 10)),
            "tag_coverage_gap": min(30, coverage_gap * 3),
            "place_evidence_gap": evidence_gap,
            "freshness_gap": freshness_gap,
            "conflict": conflict_priority,
            "search_demand": search_demand,
            "data_quality_need": data_quality_need,
        }
        results[place.id] = {
            "score": sum(components.values()),
            "components": components,
            "tier": place_region_tier(place),
            "active_tag_count": active_tags,
            "relevant_tag_count": relevant_tag_count,
            "expired_evidence_count": int(stats.get("expired_count") or 0),
        }
    return results


def weighted_tier_selection(candidates, *, limit, tier_weights):
    pools = defaultdict(list)
    for place, context in candidates:
        pools[context["tier"]].append((place, context))
    for rows in pools.values():
        rows.sort(key=lambda item: (-item[1]["score"], item[0].id))

    total_weight = sum(tier_weights)
    quotas = {
        tier: max(0, round(limit * tier_weights[tier - 1] / total_weight))
        for tier in range(1, 5)
    }
    while sum(quotas.values()) < limit:
        quotas[max(quotas, key=lambda tier: tier_weights[tier - 1])] += 1
    selected = []
    for tier in range(1, 5):
        take = min(quotas[tier], len(pools[tier]))
        selected.extend(pools[tier][:take])
        pools[tier] = pools[tier][take:]
    remaining = sorted(
        [item for rows in pools.values() for item in rows],
        key=lambda item: (-item[1]["score"], item[0].id),
    )
    selected.extend(remaining[: max(0, limit - len(selected))])
    return selected[:limit]

