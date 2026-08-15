from datetime import timedelta

from django.conf import settings
from django.utils import timezone


DEFAULT_TTL_DAYS = {
    "public_toilet_standard": 400,
    "public_parking_standard": 400,
    "citypark_standard": 730,
    "tour_api": 365,
    "heat_shelter_api": 240,
    "library_standard": 400,
    "freewifi": 400,
}


def ttl_days_for(*, place_source="", dataset=""):
    configured = getattr(settings, "STRUCTURED_EVIDENCE_TTL_DAYS", {}) or {}
    key = dataset or place_source
    value = configured.get(key, DEFAULT_TTL_DAYS.get(key))
    try:
        return max(1, int(value)) if value is not None else None
    except (TypeError, ValueError):
        return DEFAULT_TTL_DAYS.get(key)


def structured_expiry(observed_at, *, place_source="", dataset=""):
    days = ttl_days_for(place_source=place_source, dataset=dataset)
    if not observed_at or days is None:
        return None
    return observed_at + timedelta(days=days)


def freshness_state(observed_at, *, place_source="", dataset="", now=None):
    if not observed_at:
        return "unknown"
    expires_at = structured_expiry(
        observed_at,
        place_source=place_source,
        dataset=dataset,
    )
    if expires_at is None:
        return "unknown"
    return "stale" if expires_at <= (now or timezone.now()) else "current"
