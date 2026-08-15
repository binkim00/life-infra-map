from datetime import datetime

from django.utils import timezone


SOURCE_TRUST = {
    "naver_blog_search": 65,
    "web_search": 60,
    "field_rule": 95,
    "external_data": 90,
    "external_api": 85,
    "user_feedback": 85,
    "admin_review": 95,
}


def freshness_score(observed_at, *, now=None):
    now = now or timezone.now()
    if not observed_at:
        return 45
    if timezone.is_naive(observed_at):
        observed_at = timezone.make_aware(observed_at)
    age_days = max(0, (now - observed_at).days)
    if age_days <= 30:
        return 100
    if age_days <= 180:
        return 85
    if age_days <= 365:
        return 70
    if age_days <= 730:
        return 50
    return 30


def parse_observed_date(value):
    text = str(value or "").strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return timezone.make_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None


def evidence_confidence(*, source, identity_score, clarity_score, observed_at):
    """Rule-based score; provider/LLM self-reported confidence is never trusted."""
    source_score = SOURCE_TRUST.get(source, 50)
    freshness = freshness_score(observed_at)
    score = round(
        identity_score * 0.45
        + source_score * 0.20
        + clarity_score * 0.20
        + freshness * 0.15
    )
    return max(25, min(95, score)), {
        "identity": identity_score,
        "source_trust": source_score,
        "clarity": clarity_score,
        "freshness": freshness,
    }

