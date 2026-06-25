from django.db.models import Count
from django.db.models.functions import TruncDate


TIER_RULES = [
    (22, "challenger", "챌린저"),
    (21, "master", "마스터"),
    (20, "diamond", "다이아"),
    (19, "platinum", "플래티넘"),
    (18, "gold", "골드"),
    (17, "silver", "실버"),
    (16, "bronze", "브론즈"),
    (0, "iron", "아이언"),
]

TIER_COLORS = {
    "iron": "#8b8b8b",
    "bronze": "#b7791f",
    "silver": "#9ca3af",
    "gold": "#f59e0b",
    "platinum": "#14b8a6",
    "diamond": "#3b82f6",
    "master": "#8b5cf6",
    "challenger": "#ef4444",
}

POSTS_PER_CONTRIBUTION_POINT = 1
COMMENTS_PER_CONTRIBUTION_POINT = 1
DAILY_ACTIVITY_CONTRIBUTION_LIMIT = 100
STAFF_DEMO_BASE_CONTRIBUTION = 15
REPORT_CONTRIBUTION_REWARDS = {
    "tag_suggestion": 10,
    "wrong_info": 5,
    "edit_place": 5,
    "new_place": 20,
}


def calculate_daily_activity_contribution(post_count=0, comment_count=0):
    return min(
        DAILY_ACTIVITY_CONTRIBUTION_LIMIT,
        (post_count // POSTS_PER_CONTRIBUTION_POINT)
        + (comment_count // COMMENTS_PER_CONTRIBUTION_POINT),
    )


def calculate_user_contribution(post_count=0, comment_count=0, approved_report_counts=None):
    approved_report_counts = approved_report_counts or {}
    report_contribution = sum(
        REPORT_CONTRIBUTION_REWARDS.get(report_type, 0) * count
        for report_type, count in approved_report_counts.items()
    )

    return calculate_daily_activity_contribution(post_count, comment_count) + report_contribution


def calculate_user_score(post_count, comment_count):
    # 호환용 함수입니다. 새 UI에서는 contribution 값을 우선 사용합니다.
    return calculate_user_contribution(post_count, comment_count)


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


def get_tier_color(tier):
    return TIER_COLORS.get(tier, TIER_COLORS["iron"])


def get_approved_report_counts(user):
    if not user or not getattr(user, "is_authenticated", False):
        return {}

    from django.db.models import Count
    from recommendations.models import PlaceReport

    return {
        row["report_type"]: row["count"]
        for row in (
            PlaceReport.objects
            .filter(user=user, status="approved")
            .values("report_type")
            .annotate(count=Count("id"))
        )
    }


def get_daily_activity_contribution(user):
    post_counts_by_date = {
        row["activity_date"]: row["count"]
        for row in (
            user.posts
            .annotate(activity_date=TruncDate("created_at"))
            .values("activity_date")
            .annotate(count=Count("id"))
        )
    }
    comment_counts_by_date = {
        row["activity_date"]: row["count"]
        for row in (
            user.comments
            .annotate(activity_date=TruncDate("created_at"))
            .values("activity_date")
            .annotate(count=Count("id"))
        )
    }

    activity_dates = set(post_counts_by_date) | set(comment_counts_by_date)

    return sum(
        calculate_daily_activity_contribution(
            post_count=post_counts_by_date.get(activity_date, 0),
            comment_count=comment_counts_by_date.get(activity_date, 0),
        )
        for activity_date in activity_dates
    )


def get_user_contribution(user):
    if not user or not getattr(user, "is_authenticated", False):
        return 0

    activity_contribution = get_daily_activity_contribution(user)
    approved_report_counts = get_approved_report_counts(user)
    report_contribution = calculate_user_contribution(
        approved_report_counts=approved_report_counts,
    )

    staff_demo_contribution = STAFF_DEMO_BASE_CONTRIBUTION if user.is_staff else 0

    return activity_contribution + report_contribution + staff_demo_contribution


def get_user_score(user):
    return get_user_contribution(user)


def get_user_tier_info(user):
    contribution = get_user_contribution(user)
    tier = get_tier_by_score(contribution)

    return {
        "score": contribution,
        "contribution": contribution,
        "tier": tier,
        "tier_label": get_tier_label(tier),
        "tier_color": get_tier_color(tier),
        "nickname_color": get_tier_color(tier),
    }
