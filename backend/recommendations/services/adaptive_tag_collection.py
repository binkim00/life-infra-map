"""Low-cost discovery followed by evidence-driven feature queries."""

from django.conf import settings

from recommendations.services.naver_tag_evidence_provider import SEARCH_KEYWORDS


FEATURE_QUERY_CLUSTERS = (
    ("work_sparse", ("콘센트있음", "무료와이파이", "노트북작업", "작업하기좋음")),
    # Candidate hints may justify a one-off targeted validation even though this
    # cluster is not part of the adopted daily packs by default.
    ("ambience", ("분위기좋음", "조용함", "데이트좋음", "대화하기좋음")),
    ("solo", ("혼자이용좋음", "혼밥좋음")),
    ("long_stay", ("장기체류좋음",)),
    ("talk", ("대화하기좋음",)),
    ("waiting", ("웨이팅적음",)),
)


def targeted_profiles(targeted_tags, allowed_tags, *, adopted_only=True):
    targets = set(targeted_tags or ())
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
        matched = [tag for tag in cluster_tags if tag in targets and tag in allowed]
        if not matched:
            continue
        primary = matched[0]
        rows.append(("target_{}".format(cluster_name), SEARCH_KEYWORDS[primary], allowed))
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
    return 1 + min(2, clusters)
