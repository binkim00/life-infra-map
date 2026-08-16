from collections import defaultdict
import math

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagCollectionJob, PlaceTagEvidence, TagEnrichmentRequest
from recommendations.services.place_tag_collection import requested_tags_for_category
from recommendations.services.restaurant_collection_quality import restaurant_collection_quality
from recommendations.services.tag_source_policy import OFFICIAL_EVIDENCE_SOURCES, WEB_EVIDENCE_SOURCES


VOLATILE_REFRESH_TAGS = frozenset({
    "웨이팅적음", "24시간운영", "야간운영", "콘센트있음", "무료와이파이",
    "작업하기좋음", "노트북작업", "장기체류좋음",
})


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
            latest_web_observed=Max("observed_at", filter=Q(source__in=WEB_EVIDENCE_SOURCES)),
            expired_count=Count("id", filter=Q(expires_at__lte=now)),
            expired_web_count=Count(
                "id", filter=Q(expires_at__lte=now, source__in=WEB_EVIDENCE_SOURCES),
            ),
            expired_structured_count=Count(
                "id", filter=Q(expires_at__lte=now, source__in=OFFICIAL_EVIDENCE_SOURCES),
            ),
            volatile_expired_tags=Count(
                "tag_id", distinct=True,
                filter=Q(
                    expires_at__lte=now,
                    source__in=WEB_EVIDENCE_SOURCES,
                    tag__name__in=VOLATILE_REFRESH_TAGS,
                ),
            ),
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
    job_quality = {
        row["place_id"]: row
        for row in PlaceTagCollectionJob.objects.filter(place_id__in=place_ids).values("place_id").annotate(
            identity_misses=Count("id", filter=Q(stats__miss_reason="IDENTITY_MISMATCH")),
            successful_jobs=Count("id", filter=Q(stats__evidences__gt=0)),
        )
    }
    category_priorities = category_priorities or {}
    results = {}
    for place in places:
        stats = evidence.get(place.id, {})
        relevant_tag_count = len(requested_tags_for_category(place.category))
        active_tags = int(stats.get("active_tags") or 0)
        coverage_gap = max(0, relevant_tag_count - active_tags)
        evidence_gap = 20 if not stats.get("active_count") else 0
        expired_count = int(stats.get("expired_count") or 0)
        expired_web_count = int(stats.get("expired_web_count") or 0)
        volatile_expired = int(stats.get("volatile_expired_tags") or 0)
        # This planner dispatches a web provider. Structured staleness belongs
        # to source refresh commands and must not spend Naver quota.
        freshness_gap = min(25, expired_web_count * 2 + volatile_expired * 5)
        latest = stats.get("latest_web_observed")
        if not latest:
            freshness_gap = max(freshness_gap, 15)
        elif (now - latest).days >= 90:
            freshness_gap = max(freshness_gap, min(20, 5 + (now - latest).days // 90 * 3))
        conflict_priority = min(20, int(conflicts.get(place.id, 0)) * 8)
        search_demand = min(20, int(demands.get(place.id, 0) or 0))
        data_quality_need = max(0, min(10, round((100 - place.data_quality_score) / 10)))
        job_stats = job_quality.get(place.id, {})
        restaurant_quality = restaurant_collection_quality(
            place,
            identity_misses=int(job_stats.get("identity_misses") or 0),
            successful_jobs=int(job_stats.get("successful_jobs") or 0),
        )
        components = {
            "region": {1: 30, 2: 20, 3: 12, 4: 5}[place_region_tier(place)],
            "category": int(category_priorities.get(place.category, 10)),
            "tag_coverage_gap": min(30, coverage_gap * 3),
            "place_evidence_gap": evidence_gap,
            "freshness_gap": freshness_gap,
            "conflict": conflict_priority,
            "search_demand": search_demand,
            "data_quality_need": data_quality_need,
            "restaurant_collection_quality": restaurant_quality["score"],
        }
        results[place.id] = {
            "score": sum(components.values()),
            "components": components,
            "tier": place_region_tier(place),
            "active_tag_count": active_tags,
            "relevant_tag_count": relevant_tag_count,
            "expired_evidence_count": int(stats.get("expired_count") or 0),
            "expired_web_evidence_count": expired_web_count,
            "expired_structured_evidence_count": int(stats.get("expired_structured_count") or 0),
            "volatile_expired_tag_count": volatile_expired,
            "restaurant_quality_flags": restaurant_quality["flags"],
        }
    return results


def weighted_tier_selection(candidates, *, limit, tier_weights, category_max_share=40):
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
    category_counts = defaultdict(int)
    category_cap = max(1, math.ceil(limit * category_max_share / 100))
    for tier in range(1, 5):
        target = min(quotas[tier], len(pools[tier]))
        kept = []
        for item in pools[tier]:
            if target <= 0:
                kept.append(item)
                continue
            category = item[0].category
            if category_counts[category] >= category_cap:
                kept.append(item)
                continue
            selected.append(item)
            category_counts[category] += 1
            target -= 1
        # Tier allocation is stronger than the category cap. If a tier only has
        # one category, keep its nationwide share instead of silently collapsing
        # the whole batch into Tier 1.
        tier_fill = kept[:target]
        for item in tier_fill:
            category_counts[item[0].category] += 1
        selected.extend(tier_fill)
        pools[tier] = kept[target:]
    remaining = sorted(
        [item for rows in pools.values() for item in rows],
        key=lambda item: (-item[1]["score"], item[0].id),
    )
    for item in remaining:
        if len(selected) >= limit:
            break
        category = item[0].category
        if category_counts[category] >= category_cap:
            continue
        selected.append(item)
        category_counts[category] += 1
    if len(selected) < limit:
        chosen_ids = {item[0].id for item in selected}
        selected.extend(
            item for item in remaining
            if item[0].id not in chosen_ids
        )
    return selected[:limit]
