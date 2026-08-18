from collections import Counter, defaultdict, deque

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence


REGION_PREFIXES = {
    "서울": ("서울특별시", "서울 "), "부산": ("부산광역시", "부산 "),
    "인천": ("인천광역시", "인천 "), "대구": ("대구광역시", "대구 "),
    "대전": ("대전광역시", "대전 "), "광주": ("광주광역시", "광주 "),
    "울산": ("울산광역시", "울산 "),
}
PILOT_CATEGORIES = (
    "cafe", "restaurant", "city_park", "tourism", "shelter",
    "library", "parking", "toilet",
)
FEATURE_CLUSTERS = {
    "work": {"조용함", "작업하기좋음", "노트북작업", "콘센트있음", "무료와이파이", "장기체류좋음"},
    "solo_social": {"혼자이용좋음", "혼밥좋음", "대화하기좋음", "데이트좋음", "분위기좋음"},
    "outdoor": {"산책", "전망좋음", "운동시설", "놀이시설", "편의시설"},
    "facility": {"무료이용", "24시간", "24시간운영", "장애인시설", "카드결제가능", "주차가능", "냉방시설", "야간운영"},
}
CLUSTER_ORDER = {"work": 0, "solo_social": 1, "outdoor": 2, "facility": 3, "other": 4}


def _region_filter(regions):
    query = Q()
    for region in regions:
        for prefix in REGION_PREFIXES[region]:
            query |= Q(place__address__startswith=prefix)
            query |= Q(place__detail_location__startswith=prefix)
    return query


def _region_for(row):
    text = f"{row['address']} {row['detail_location']}"
    for region, prefixes in REGION_PREFIXES.items():
        if any(text.startswith(prefix) for prefix in prefixes):
            return region
    return ""


def _cluster_for(tag_name):
    for cluster, names in FEATURE_CLUSTERS.items():
        if tag_name in names:
            return cluster
    return "other"


def eligible_feature_rows(*, regions=None, categories=None, now=None):
    regions = tuple(regions or REGION_PREFIXES)
    categories = tuple(categories) if categories else ()
    now = now or timezone.now()
    positive = PlaceTagEvidence.objects.filter(
        place_id=OuterRef("place_id"), tag_id=OuterRef("tag_id"), polarity="positive",
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    negative = PlaceTagEvidence.objects.filter(
        place_id=OuterRef("place_id"), tag_id=OuterRef("tag_id"), polarity="negative",
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    queryset = PlaceTag.objects.filter(_region_filter(regions))
    if categories:
        queryset = queryset.filter(place__category__in=categories)
    return (
        queryset
        .filter(Q(status="confirmed") | Q(status="candidate", confidence__gte=50))
        .annotate(has_positive=Exists(positive), has_negative=Exists(negative))
        .filter(has_positive=True, has_negative=False)
        .values("place_id", "place__name", "place__category", "place__address",
                "place__detail_location", "tag__name")
        .order_by("place_id", "tag__name")
    )


def stratified_feature_sample(*, limit=1000, regions=None, categories=None, now=None, hard_limit=1000):
    by_place = {}
    for row in eligible_feature_rows(regions=regions, categories=categories, now=now).iterator():
        item = by_place.setdefault(row["place_id"], {
            "place_id": row["place_id"], "name": row["place__name"],
            "category": row["place__category"], "address": row["place__address"],
            "detail_location": row["place__detail_location"], "features": [],
        })
        item["features"].append(row["tag__name"])
    tag_frequency = Counter(tag for item in by_place.values() for tag in item["features"])
    strata = defaultdict(list)
    for item in by_place.values():
        item["region"] = _region_for(item)
        if not item["region"]:
            continue
        item["features"] = sorted(set(item["features"]))
        for cluster in sorted({_cluster_for(name) for name in item["features"]}):
            strata[(item["region"], item["category"], cluster)].append(item)
    for rows in strata.values():
        rows.sort(key=lambda row: (min(tag_frequency[tag] for tag in row["features"]), -len(row["features"]), row["place_id"]))
    # Put the historically sparse semantic clusters first. A place may belong
    # to more than one stratum, and facility-heavy rows must not consume it
    # before its rarer work/solo meaning can contribute to the pilot balance.
    ordered_strata = sorted(strata.items(), key=lambda item: (item[0][0], item[0][1]))
    cluster_queues = defaultdict(list)
    for key, rows in ordered_strata:
        cluster_queues[key[2]].append((key, deque(rows)))
    selected, selected_ids = [], set()
    maximum = max(1, min(int(limit), int(hard_limit)))
    region_cap = max(1, int(maximum * 0.25))
    region_counts = Counter()
    cluster_cursor = Counter()
    while cluster_queues and len(selected) < maximum:
        progressed = False
        for cluster in sorted(cluster_queues, key=lambda value: CLUSTER_ORDER[value]):
            options = cluster_queues[cluster]
            if not options:
                continue
            row = None
            key = None
            for _ in range(len(options)):
                index = cluster_cursor[cluster] % len(options)
                cluster_cursor[cluster] += 1
                key, queue = options[index]
                if region_counts[key[0]] >= region_cap:
                    continue
                while queue and queue[0]["place_id"] in selected_ids:
                    queue.popleft()
                if queue:
                    row = dict(queue.popleft())
                    break
            cluster_queues[cluster] = [(item_key, queue) for item_key, queue in options if queue]
            if not cluster_queues[cluster]:
                cluster_queues.pop(cluster, None)
            if row is None:
                continue
            row["selection_stratum"] = {"region": key[0], "category": key[1], "cluster": key[2]}
            selected.append(row)
            selected_ids.add(row["place_id"])
            region_counts[row["region"]] += 1
            progressed = True
            if len(selected) >= maximum:
                break
        if not progressed:
            break
    return selected


def sample_distribution(rows):
    feature_counts = Counter(len(row["features"]) for row in rows)
    return {
        "selected": len(rows),
        "regions": dict(sorted(Counter(row["region"] for row in rows).items())),
        "categories": dict(sorted(Counter(row["category"] for row in rows).items())),
        "tags": dict(Counter(tag for row in rows for tag in row["features"]).most_common()),
        "feature_count_distribution": {str(key): value for key, value in sorted(feature_counts.items())},
        "selection_clusters": dict(sorted(Counter(row["selection_stratum"]["cluster"] for row in rows).items())),
    }
