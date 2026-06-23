TIER_RULES = [
    (16, "challenger", "챌린저"),
    (14, "master", "마스터"),
    (12, "diamond", "다이아"),
    (10, "platinum", "플래티넘"),
    (8, "gold", "골드"),
    (6, "silver", "실버"),
    (4, "bronze", "브론즈"),
    (0, "iron", "아이언"),
]


def calculate_user_score(post_count, comment_count):
    # 현재 기준: 게시글 1개 = 2점, 댓글 1개 = 1점
    # 추후 점수 정책이 바뀌면 여기만 수정하면 됩니다.
    return (post_count * 2) + comment_count


def get_tier_by_score(score):
    for minimum_score, tier, label in TIER_RULES:
        if score >= minimum_score:
            return tier
    return "iron"


def get_tier_label(tier):
    for minimum_score, tier_value, label in TIER_RULES:
        if tier_value == tier:
            return label
    return "아이언"


def get_user_score(user):
    if not user or not getattr(user, "is_authenticated", False):
        return 0

    post_count = user.posts.count()
    comment_count = user.comments.count()
    return calculate_user_score(post_count, comment_count)


def get_user_tier_info(user):
    score = get_user_score(user)
    tier = get_tier_by_score(score)

    return {
        "score": score,
        "tier": tier,
        "tier_label": get_tier_label(tier),
    }
