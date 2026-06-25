from accounts.utils import get_user_tier_info
from boards.models import Notification


TIER_ORDER = [
    "iron",
    "bronze",
    "silver",
    "gold",
    "platinum",
    "diamond",
    "master",
    "challenger",
]
TIER_UP_NOTIFICATION_TITLE = "등급 승급 안내"


def get_current_user_tier(user):
    if not user or not user.is_authenticated:
        return None

    return get_user_tier_info(user)["tier"]


def get_tier_rank(tier):
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return -1


def notify_tier_upgrade_if_needed(user, previous_tier):
    if not user or not user.is_authenticated or not previous_tier:
        return None

    current_tier_info = get_user_tier_info(user)
    current_tier = current_tier_info["tier"]

    if get_tier_rank(current_tier) <= get_tier_rank(previous_tier):
        return None

    return Notification.objects.create(
        recipient=user,
        notification_type="system",
        title=TIER_UP_NOTIFICATION_TITLE,
        message=f"축하합니다! {current_tier_info['tier_label']}등급으로 승급하셨습니다!",
    )
