from collections import Counter

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from recommendations.models import (
    Place,
    PlaceTag,
    PlaceTagCollectionJob,
    PlaceTagEvidence,
    SourcePlaceRecord,
)


REGION_NAMES = {
    "부산": "부산광역시",
    "서울": "서울특별시",
    "인천": "인천광역시",
    "대구": "대구광역시",
    "대전": "대전광역시",
    "광주": "광주광역시",
    "울산": "울산광역시",
}
REGION_ORDER = ("부산", "서울", "인천", "대구", "대전", "광주", "울산")
CORE_TAGS = {
    "cafe": (
        "조용함", "노트북작업", "작업하기좋음", "콘센트있음", "혼자이용좋음",
        "분위기좋음", "무료와이파이", "데이트좋음", "대화하기좋음", "장기체류좋음",
    ),
    "restaurant": ("혼밥좋음", "분위기좋음", "데이트좋음", "대화하기좋음", "웨이팅적음"),
}


CORE_TAGS['restaurant'] = tuple(dict.fromkeys([
    *CORE_TAGS['restaurant'],
    '단체석있음', '예약가능', '개별룸있음', '편한좌석', '좌석간격넓음',
    '유아의자있음', '유모차접근', '장기체류좋음', '테이크아웃전문',
    '좌석없음', '시간제한있음', '혼잡함', '소음큼',
]))


def normalize_region(value):
    text = str(value or "").strip()
    for short, full in REGION_NAMES.items():
        if text in {short, full}:
            return short, full
    raise ValueError("unsupported region")


def region_filter(short, prefix=""):
    return Q(**{f"{prefix}address__startswith": short}) | Q(
        **{f"{prefix}detail_location__startswith": short}
    )


def _ratio(value, total):
    return round(value / total, 4) if total else 0.0


def _recent_cycles(jobs, target_calls=500):
    rows = list(jobs.order_by("-created_at").values("place__category", "stats", "error_code")[:5000])
    cycles = []
    current = Counter()
    categories = Counter()
    for row in rows:
        stats = row.get("stats") or {}
        calls = int(stats.get("requests") or 0)
        current["places"] += 1
        current["calls"] += calls
        current["evidence"] += int(stats.get("new_evidences") or 0)
        current["active"] += int(stats.get("new_active_evidences") or 0)
        current["ai_calls"] += int(stats.get("ai_calls") or 0)
        current["mismatch"] += int(stats.get("miss_reason") == "IDENTITY_MISMATCH")
        current["no_result"] += int(stats.get("miss_reason") == "NO_SEARCH_RESULT")
        current["no_tag"] += int(stats.get("miss_reason") == "NO_TAG_EXPRESSION")
        current["failures"] += int(bool(row.get("error_code") and row["error_code"] != "insufficient_evidence"))
        current["rate_limited"] += int(row.get("error_code") == "rate_limited")
        categories[row["place__category"]] += 1
        if current["calls"] >= target_calls:
            cycles.append(_finish_cycle(current, categories))
            current = Counter()
            categories = Counter()
            if len(cycles) == 3:
                break
    if current and len(cycles) < 3:
        cycles.append(_finish_cycle(current, categories))
    return cycles


def _finish_cycle(row, categories):
    result = dict(row)
    result["categories"] = dict(categories)
    result["calls_per_place"] = _ratio(row["calls"], row["places"])
    result["evidence_per_call"] = _ratio(row["evidence"], row["calls"])
    result["active_per_call"] = _ratio(row["active"], row["calls"])
    return result


def build_region_enrichment_report(region, *, now=None):
    now = now or timezone.now()
    short, full = normalize_region(region)
    active_filter = Q(polarity="positive") & (
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )
    categories = {}
    priority_total = 0
    for category, tags in CORE_TAGS.items():
        places = Place.objects.filter(region_filter(short), category=category)
        evidence = PlaceTagEvidence.objects.filter(place__in=places)
        active = evidence.filter(active_filter)
        active_same_pair = PlaceTagEvidence.objects.filter(
            place_id=OuterRef("place_id"), tag_id=OuterRef("tag_id"), polarity="positive",
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        candidates = PlaceTag.objects.filter(
            place__in=places, status__in=("candidate", "needs_verification"), tag__name__in=tags,
        ).annotate(has_active=Exists(active_same_pair)).filter(has_active=False)
        jobs = PlaceTagCollectionJob.objects.filter(place__in=places, status="completed")
        pools = {
            "candidate_hint": candidates.values("place_id").distinct().count(),
            "past_identity_success": jobs.filter(stats__diagnostics__identity_matches__gt=0).values("place_id").distinct().count(),
            "past_evidence_success": jobs.filter(stats__evidences__gt=0).values("place_id").distinct().count(),
            "no_tag_expression": jobs.filter(stats__miss_reason="NO_TAG_EXPRESSION").values("place_id").distinct().count(),
            "coverage_gap": places.exclude(id__in=active.values("place_id")).count(),
        }
        priority_total += pools["candidate_hint"] + pools["past_identity_success"] + pools["no_tag_expression"]
        tag_counts = {
            row["tag__name"]: row["count"]
            for row in active.filter(tag__name__in=tags).values("tag__name").annotate(
                count=__import__("django.db.models", fromlist=["Count"]).Count("place_id", distinct=True)
            )
        }
        total = places.count()
        categories[category] = {
            "places": total,
            "evidence_places": evidence.values("place_id").distinct().count(),
            "active_evidence_places": active.values("place_id").distinct().count(),
            "place_tags": PlaceTag.objects.filter(place__in=places).count(),
            "priority_pool": pools,
            "tags": [
                {"tag": tag, "active_places": tag_counts.get(tag, 0), "coverage": _ratio(tag_counts.get(tag, 0), total)}
                for tag in tags
            ],
        }
    completed = PlaceTagCollectionJob.objects.filter(
        region_filter(short, "place__"), place__category__in=CORE_TAGS, status="completed",
    )
    cycles = _recent_cycles(completed)
    if priority_total == 0:
        state = "READY_TO_MOVE"
    elif len(cycles) >= 3 and sum(row["active"] for row in cycles[:3]) == 0:
        state = "SOURCE_LIMITED"
    else:
        state = "KEEP_ENRICHING"
    next_region = REGION_ORDER[min(REGION_ORDER.index(short) + 1, len(REGION_ORDER) - 1)]
    source_rows = []
    for category in CORE_TAGS:
        source_rows.append({
            "category": category,
            "records": SourcePlaceRecord.objects.filter(sido_name__startswith=short, category=category).count(),
            "materialized": SourcePlaceRecord.objects.filter(
                sido_name__startswith=short, category=category, normalized_place__isnull=False,
            ).count(),
        })
    return {
        "region": short,
        "region_full": full,
        "state": state,
        "recommended_next_region": next_region,
        "categories": categories,
        "recent_cycles": cycles,
        "source_registry": source_rows,
    }
