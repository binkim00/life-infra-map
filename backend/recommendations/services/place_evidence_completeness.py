"""Measure whether a place is understood well enough for recommendation search.

Basic place facts remain useful filters, but they must not make a place look
"researched".  This module measures coverage across experience dimensions and
keeps collection focused on the dimensions that are still unknown.
"""

from collections import defaultdict

from django.db.models import Q
from django.utils import timezone

from recommendations.models import PlaceTagEvidence


BASIC_FACT_TAGS = frozenset({
    "카페", "베이커리", "패스트푸드", "전통찻집", "디저트", "브런치", "북카페",
    "냉방시설있음", "무료와이파이", "와이파이있음", "24시간운영", "24시간", "무료이용", "야간운영",
    "주말휴일운영", "토요일운영", "공휴일운영", "카드결제가능", "주차가능",
    "장애인시설", "장애인전용주차", "휠체어접근", "기저귀교환대",
    "운동시설", "놀이시설", "숙박가능", "편의시설", "열람좌석많음",
    "예약가능", "유아의자있음",
})


CATEGORY_EVIDENCE_DIMENSIONS = {
    "cafe": {
        "atmosphere": (
            "조용함", "분위기좋음", "소음큼", "혼잡함",
        ),
        "work_stay": (
            "노트북작업", "작업하기좋음", "콘센트있음", "와이파이있음",
            "무료와이파이", "장기체류좋음", "시간제한있음",
        ),
        "space_seating": (
            "넓은테이블", "좌석간격넓음", "편한좌석", "개별룸있음",
            "단체석있음", "좌석없음",
        ),
        "visit_purpose": (
            "혼자이용좋음", "데이트좋음", "대화하기좋음",
        ),
        "distinctiveness": (
            "전망좋음", "자연채광좋음", "야외좌석", "반려동물동반",
            "디저트특화", "커피맛좋음", "사진찍기좋음", "테이크아웃전문",
        ),
        "friction": (
            "웨이팅적음", "웨이팅많음", "주차어려움", "계단접근만가능",
        ),
    },
    "restaurant": {
        "atmosphere": (
            "조용함", "분위기좋음", "소음큼", "혼잡함", "전망좋음",
        ),
        "solo_visit": (
            "혼밥좋음", "혼자이용좋음", "테이크아웃전문", "좌석없음",
        ),
        "group_family": (
            "데이트좋음", "대화하기좋음", "가족동반좋음", "단체석있음",
            "개별룸있음", "유아의자있음", "유모차접근", "아이메뉴있음",
        ),
        "space_seating": (
            "넓은테이블", "좌석간격넓음", "편한좌석", "무단차접근",
            "엘리베이터있음",
        ),
        "reservation_wait": (
            "예약가능", "예약필수", "웨이팅적음", "웨이팅많음",
            "시간제한있음",
        ),
        "food_value": (
            "대표메뉴뚜렷함", "메뉴선택폭넓음", "여럿이먹기좋은메뉴", "가성비좋음",
        ),
        "friction": (
            "주차어려움", "계단접근만가능", "소음큼", "혼잡함",
        ),
    },
}

DIMENSION_LABELS = {
    "atmosphere": "분위기·소음",
    "work_stay": "작업·체류",
    "space_seating": "공간·좌석",
    "visit_purpose": "이용 목적",
    "distinctiveness": "차별점",
    "friction": "불편 요소",
    "solo_visit": "혼자 이용",
    "group_family": "모임·가족 이용",
    "reservation_wait": "예약·대기",
    "food_value": "메뉴·가치",
}

CATEGORY_ALIASES = {"bakery": "cafe", "food_service": "restaurant"}


def canonical_category(category):
    value = str(category or "").strip().lower()
    return CATEGORY_ALIASES.get(value, value)


def evidence_dimensions(category):
    return CATEGORY_EVIDENCE_DIMENSIONS.get(canonical_category(category), {})


def meaningful_tags_for_category(category):
    return tuple(dict.fromkeys(
        tag
        for tags in evidence_dimensions(category).values()
        for tag in tags
        if tag not in BASIC_FACT_TAGS
    ))


def assess_evidence_quality(category, observations):
    """Return recommendation-oriented coverage from active evidence observations."""
    dimensions = evidence_dimensions(category)
    allowed = set(meaningful_tags_for_category(category))
    by_dimension = defaultdict(set)
    positive_tags = set()
    negative_tags = set()
    sources = set()

    tag_to_dimensions = defaultdict(set)
    for dimension, tags in dimensions.items():
        for tag in tags:
            if tag in allowed:
                tag_to_dimensions[tag].add(dimension)

    for row in observations or ():
        tag = str(row.get("tag_name") or row.get("tag__name") or "").strip()
        if tag not in allowed:
            continue
        polarity = str(row.get("polarity") or "positive").strip().lower()
        if polarity == "positive":
            positive_tags.add(tag)
        elif polarity == "negative":
            negative_tags.add(tag)
        else:
            continue
        for dimension in tag_to_dimensions[tag]:
            by_dimension[dimension].add(tag)
        source = str(row.get("source") or "").strip()
        reference = str(row.get("source_reference") or "").strip()
        if source or reference:
            sources.add((source, reference or source))

    observed_tags = positive_tags | negative_tags
    covered_dimensions = [name for name in dimensions if by_dimension[name]]
    missing_dimensions = [name for name in dimensions if not by_dimension[name]]
    tag_count = len(observed_tags)
    domain_count = len(covered_dimensions)
    source_count = len(sources)
    tradeoff_tags = {
        "소음큼", "혼잡함", "시간제한있음", "웨이팅많음", "주차어려움",
        "계단접근만가능", "좌석없음", "예약필수",
    }
    has_tradeoff = bool((observed_tags & tradeoff_tags) or negative_tags)

    if domain_count >= 4 and tag_count >= 6 and source_count >= 2 and has_tradeoff:
        level = "rich"
        level_label = "추천 정보 충분"
    elif domain_count >= 2 and tag_count >= 3 and source_count >= 2:
        level = "searchable"
        level_label = "검색 가능"
    elif tag_count:
        level = "thin"
        level_label = "조사 부족"
    else:
        level = "empty"
        level_label = "추천 정보 없음"

    total_dimensions = len(dimensions)
    score = round(min(100, (
        (domain_count / total_dimensions * 55 if total_dimensions else 0)
        + min(tag_count, 8) / 8 * 20
        + min(source_count, 3) / 3 * 15
        + (10 if has_tradeoff else 0)
    )))
    return {
        "level": level,
        "level_label": level_label,
        "score": score,
        "meaningful_tag_count": tag_count,
        "positive_tag_count": len(positive_tags),
        "negative_tag_count": len(negative_tags),
        "source_count": source_count,
        "dimension_count": domain_count,
        "dimension_total": total_dimensions,
        "covered_dimensions": covered_dimensions,
        "covered_dimension_labels": [DIMENSION_LABELS.get(name, name) for name in covered_dimensions],
        "missing_dimensions": missing_dimensions,
        "missing_dimension_labels": [DIMENSION_LABELS.get(name, name) for name in missing_dimensions],
        "observed_tags": sorted(observed_tags),
        "has_tradeoff_evidence": has_tradeoff,
    }


def target_tags_for_gaps(category, observations, *, limit=8):
    profile = assess_evidence_quality(category, observations)
    dimensions = evidence_dimensions(category)
    observed = set(profile["observed_tags"])
    targets = []
    # First get one signal from every unknown dimension. Then deepen dimensions
    # that only have a single observation instead of declaring the place done.
    for dimension in profile["missing_dimensions"]:
        first_missing = next((tag for tag in dimensions[dimension] if tag not in observed), None)
        if first_missing:
            targets.append(first_missing)
    for dimension in profile["missing_dimensions"]:
        targets.extend(tag for tag in dimensions[dimension] if tag not in observed)
    for dimension in profile["covered_dimensions"]:
        dimension_tags = [tag for tag in dimensions[dimension] if tag in observed]
        if len(dimension_tags) < 2:
            targets.extend(tag for tag in dimensions[dimension] if tag not in observed)
    return list(dict.fromkeys(targets))[:max(0, int(limit))]


def quality_profiles_for_places(places, *, now=None):
    places = list(places)
    now = now or timezone.now()
    place_ids = [place.id for place in places]
    all_tags = set()
    for place in places:
        all_tags.update(meaningful_tags_for_category(place.category))
    observations = defaultdict(list)
    if place_ids and all_tags:
        rows = PlaceTagEvidence.objects.filter(
            place_id__in=place_ids,
            tag__name__in=all_tags,
            polarity__in=("positive", "negative"),
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).values(
            "place_id", "tag__name", "polarity", "source", "source_reference",
        )
        for row in rows:
            observations[row["place_id"]].append({**row, "tag_name": row["tag__name"]})
    return {
        place.id: assess_evidence_quality(place.category, observations[place.id])
        for place in places
    }
