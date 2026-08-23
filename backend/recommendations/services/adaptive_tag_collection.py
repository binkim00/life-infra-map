"""Low-cost discovery followed by evidence-driven feature queries."""

from django.conf import settings

from recommendations.services.naver_tag_evidence_provider import (
    SEARCH_KEYWORDS,
    SEARCH_QUERY_VOCABULARY,
)


FEATURE_QUERY_CLUSTERS = (
    ("work_sparse", ("콘센트있음", "무료와이파이", "노트북작업", "작업하기좋음")),
    ("solo", ("혼밥좋음", "혼자이용좋음")),
    # Candidate hints may justify a one-off targeted validation even though this
    # cluster is not part of the adopted daily packs by default.
    ("ambience", ("분위기좋음", "조용함", "데이트좋음", "대화하기좋음")),
    ("long_stay", ("장기체류좋음",)),
    ("talk", ("대화하기좋음",)),
    ("waiting", ("웨이팅적음",)),
    # Candidate-only verification path; it is not adopted for daily discovery.
    ("visit", ("전망좋음",)),
)

FEATURE_QUERY_CLUSTERS = (*FEATURE_QUERY_CLUSTERS, (
    'group_dining',
    (
        '단체석있음', '예약가능', '개별룸있음', '편한좌석',
        '유아의자있음', '유모차접근', '테이크아웃전문', '좌석없음',
    ),
))


CLUSTER_QUERY_STAGES = {
    "work_sparse": (("direct", "노트북"), ("synonym", "카공 공부"), ("supporting_signal", "콘센트 좌석")),
    "solo": (("direct", "혼밥"), ("synonym", "혼자 식사"), ("supporting_signal", "1인석 바 좌석")),
    "ambience": (("direct", "분위기"), ("synonym", "감성 데이트"), ("situational", "한적 이야기")),
    "long_stay": (("direct", "오래 머물"), ("synonym", "장시간"), ("situational", "오래 앉아")),
    "talk": (("direct", "대화"), ("synonym", "이야기 나누기"), ("supporting_signal", "좌석 간격 한적")),
    "waiting": (("direct", "웨이팅 없음"), ("synonym", "대기 없음"), ("situational", "바로 입장")),
    "visit": (("direct", "전망"),),
    'group_dining': (
        ('direct', '단체석 예약'),
        ('synonym', '가족 모임 룸'),
        ('supporting_signal', '유아 의자 편한 좌석'),
    ),
}


def targeted_profiles(targeted_tags, allowed_tags, *, adopted_only=True, max_stages=3):
    target_order = tuple(dict.fromkeys(targeted_tags or ()))
    targets = set(target_order)
    allowed = tuple(allowed_tags or ())
    adopted = set(getattr(
        settings,
        "TAG_COLLECTION_ADOPTED_TARGET_CLUSTERS",
        ("work_sparse",),
    ))
    rows = []
    for cluster_name, cluster_tags in FEATURE_QUERY_CLUSTERS:
        if adopted_only and cluster_name not in adopted:
            continue
        matched = [tag for tag in target_order if tag in cluster_tags and tag in allowed]
        if not matched:
            continue
        primary = matched[0]
        vocabulary = SEARCH_QUERY_VOCABULARY.get(primary) or {}
        stages = []
        for stage in ("direct", "synonym", "supporting_signal", "situational"):
            terms = tuple(vocabulary.get(stage) or ())
            if terms:
                stages.append((stage, terms[0] if stage == "direct" else " ".join(terms[:2])))
        if not stages:
            stages = list(CLUSTER_QUERY_STAGES.get(cluster_name) or (("direct", SEARCH_KEYWORDS[primary]),))
        for stage, keyword in stages:
            rows.append(("target_{}_{}".format(cluster_name, stage), keyword, allowed))
            if len(rows) >= max_stages:
                return rows
    return rows


def adaptive_planned_requests(targeted_tags):
    adopted = set(getattr(
        settings,
        "TAG_COLLECTION_ADOPTED_TARGET_CLUSTERS",
        ("work_sparse",),
    ))
    clusters = sum(
        cluster_name in adopted and bool(set(tags) & set(targeted_tags or ()))
        for cluster_name, tags in FEATURE_QUERY_CLUSTERS
    )
    return 1 + (2 if clusters else 0)
