"""Low-cost discovery followed by evidence-driven feature queries."""

from recommendations.services.naver_tag_evidence_provider import SEARCH_KEYWORDS


FEATURE_QUERY_CLUSTERS = (
    ("work_sparse", ("콘센트있음", "무료와이파이", "노트북작업", "작업하기좋음")),
    ("solo", ("혼자이용좋음", "혼밥좋음")),
    ("long_stay", ("장기체류좋음",)),
    ("talk", ("대화하기좋음",)),
    ("waiting", ("웨이팅적음",)),
)


def targeted_profiles(targeted_tags, allowed_tags):
    targets = set(targeted_tags or ())
    allowed = tuple(allowed_tags or ())
    rows = []
    for cluster_name, cluster_tags in FEATURE_QUERY_CLUSTERS:
        matched = [tag for tag in cluster_tags if tag in targets and tag in allowed]
        if not matched:
            continue
        primary = matched[0]
        rows.append(("target_{}".format(cluster_name), SEARCH_KEYWORDS[primary], allowed))
    return rows


def adaptive_planned_requests(targeted_tags):
    clusters = sum(
        bool(set(tags) & set(targeted_tags or ()))
        for _, tags in FEATURE_QUERY_CLUSTERS
    )
    return 1 + min(2, clusters)
