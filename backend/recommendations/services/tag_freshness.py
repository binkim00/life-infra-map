from datetime import timedelta

from django.utils import timezone


TAG_TTL_DAYS = {
    "웨이팅적음": 45,
    "조용함": 120,
    "분위기좋음": 120,
    "혼밥좋음": 120,
    "데이트좋음": 120,
    "대화하기좋음": 120,
    "작업하기좋음": 180,
    "노트북작업": 180,
    "콘센트있음": 180,
    "무료와이파이": 180,
    "전망좋음": 365,
}


def evidence_ttl(tag_name, source):
    if source in {"field_rule", "external_data", "external_api"}:
        return None
    return timedelta(days=TAG_TTL_DAYS.get(tag_name, 120))


def evidence_is_expired(tag_name, source, observed_at, *, now=None):
    """Use the storage TTL before collecting an already expired candidate."""
    ttl = evidence_ttl(tag_name, source)
    if observed_at is None or ttl is None:
        return False
    return observed_at + ttl <= (now or timezone.now())

