import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from recommendations.models import ProviderQuotaUsage


def provider_rps(provider):
    if provider == "naver_search":
        return max(0.1, float(getattr(settings, "TAG_COLLECTION_NAVER_RPS", 10)))
    return max(0.1, float(getattr(settings, "TAG_COLLECTION_DEFAULT_RPS", 2)))


def acquire_provider_slot(provider):
    """Cross-worker fixed-interval limiter persisted in the provider quota row."""
    if not getattr(settings, "TAG_COLLECTION_RATE_LIMIT_ENABLED", True):
        return 0.0
    interval = 1.0 / provider_rps(provider)
    total_wait = 0.0
    while True:
        now = timezone.now()
        wait_seconds = 0.0
        with transaction.atomic():
            quota, _ = ProviderQuotaUsage.objects.select_for_update().get_or_create(
                provider=provider,
                usage_date=timezone.localdate(),
                defaults={"daily_limit": settings.TAG_COLLECTION_DAILY_API_LIMIT},
            )
            metadata = dict(quota.metadata or {})
            next_at_text = metadata.get("next_request_at")
            next_at = None
            if next_at_text:
                try:
                    next_at = timezone.datetime.fromisoformat(next_at_text)
                except (TypeError, ValueError):
                    next_at = None
            if next_at and timezone.is_naive(next_at):
                next_at = timezone.make_aware(next_at)
            if next_at and next_at > now:
                wait_seconds = min(1.0, (next_at - now).total_seconds())
            else:
                metadata["next_request_at"] = (now + timedelta(seconds=interval)).isoformat()
                metadata["configured_rps"] = provider_rps(provider)
                quota.metadata = metadata
                quota.save(update_fields=["metadata", "updated_at"])
                return total_wait
        if wait_seconds:
            time.sleep(wait_seconds)
            total_wait += wait_seconds

