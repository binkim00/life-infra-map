from django.conf import settings
from django.db import transaction
from django.utils import timezone

from recommendations.services.ai_json_client import call_ai_json_with_usage
from recommendations.services.canonical_tag_policy import CANONICAL_TAGS
from recommendations.services.naver_tag_evidence_provider import compact
from recommendations.models import ProviderQuotaUsage


AI_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string"},
                    "polarity": {"type": "string", "enum": ["positive", "negative", "unknown"]},
                    "evidence_span": {"type": "string"},
                },
                "required": ["tag", "polarity", "evidence_span"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["matches"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """
Classify only the supplied evidence text. Never use general knowledge about the place.
Choose only from allowed canonical tags. Do not create a new tag.
Every positive or negative result must include an exact evidence_span copied from the text.
If the text does not explicitly support a tag, omit it or use unknown.
""".strip()


MODEL_PRICES_PER_MILLION = {
    "gpt-5-nano": {"input": 0.05, "cached_input": 0.005, "output": 0.40},
}


def extract_canonical_tags_from_evidence(text, allowed_tags, *, request_call=None):
    return extract_canonical_tags_from_evidence_detailed(
        text, allowed_tags, request_call=request_call,
    )["matches"]


def extract_canonical_tags_from_evidence_detailed(text, allowed_tags, *, request_call=None):
    configured = set(getattr(settings, "TAG_COLLECTION_AI_ALLOWED_TAGS", CANONICAL_TAGS))
    allowed = [tag for tag in allowed_tags if tag in CANONICAL_TAGS and tag in configured]
    if not text.strip() or not allowed:
        return {"matches": [], "metrics": {"attempted": 0}}
    request_call = request_call or call_ai_json_with_usage
    if not reserve_ai_call():
        return {"matches": [], "metrics": {"attempted": 0, "quota_exhausted": 1}}
    succeeded = False
    envelope = {}
    try:
        response = request_call(
            "allowed_tags: {}\nevidence_text: {}".format(", ".join(allowed), text),
            SYSTEM_PROMPT,
            500,
            provider="openai",
            model=getattr(settings, "TAG_COLLECTION_AI_MODEL", "gpt-5-nano"),
            timeout=getattr(settings, "AI_REQUEST_TIMEOUT", 20),
            response_schema=AI_EXTRACTION_SCHEMA,
            schema_name="canonical_tag_evidence",
            reasoning_effort="low",
        ) or {}
        if "data" in response and isinstance(response.get("data"), dict):
            envelope = response
            payload = response["data"]
        else:
            payload = response
        succeeded = True
    except Exception:
        payload = {}
    finally:
        settle_ai_call(succeeded=succeeded, metadata=envelope)
    results = []
    compact_text = compact(text)
    seen = set()
    raw_matches = payload.get("matches") or []
    for row in raw_matches:
        tag = str(row.get("tag") or "").strip()
        polarity = str(row.get("polarity") or "").strip().lower()
        span = str(row.get("evidence_span") or "").strip()
        key = (tag, polarity, span)
        if (
            tag not in allowed
            or polarity not in {"positive", "negative"}
            or len(compact(span)) < 3
            or compact(span) not in compact_text
            or key in seen
        ):
            continue
        seen.add(key)
        results.append({"tag_name": tag, "polarity": polarity, "evidence_span": span})
    usage = envelope.get("usage") or {}
    model = str(envelope.get("model") or getattr(settings, "TAG_COLLECTION_AI_MODEL", ""))
    return {
        "matches": results,
        "metrics": {
            "attempted": 1,
            "succeeded": int(succeeded),
            "grounded": len(results),
            "invalid": max(0, len(raw_matches) - len(results)),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "cached_input_tokens": int(usage.get("cached_input_tokens") or 0),
            "estimated_cost_usd": estimate_cost_usd(model, usage),
            "model": model,
        },
    }


def reserve_ai_call():
    limit = getattr(settings, "TAG_COLLECTION_AI_DAILY_LIMIT", 100)
    if limit < 1:
        return False
    with transaction.atomic():
        quota, _ = ProviderQuotaUsage.objects.select_for_update().get_or_create(
            provider="openai_evidence",
            usage_date=timezone.localdate(),
            defaults={"daily_limit": limit},
        )
        if quota.request_count + quota.reserved_count >= quota.daily_limit:
            return False
        quota.reserved_count += 1
        quota.save(update_fields=["reserved_count", "updated_at"])
    return True


def settle_ai_call(*, succeeded, metadata=None):
    with transaction.atomic():
        quota = ProviderQuotaUsage.objects.select_for_update().get(
            provider="openai_evidence", usage_date=timezone.localdate(),
        )
        quota.reserved_count = max(0, quota.reserved_count - 1)
        quota.request_count += 1
        quota.success_count += int(succeeded)
        quota.failed_count += int(not succeeded)
        stored = dict(quota.metadata or {})
        usage = (metadata or {}).get("usage") or {}
        for key in ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens"):
            stored[key] = int(stored.get(key) or 0) + int(usage.get(key) or 0)
        model = str((metadata or {}).get("model") or "")
        if model:
            stored["model"] = model
        stored["estimated_cost_usd"] = round(
            float(stored.get("estimated_cost_usd") or 0) + estimate_cost_usd(model, usage), 8,
        )
        quota.metadata = stored
        quota.save(update_fields=[
            "reserved_count", "request_count", "success_count", "failed_count",
            "metadata", "updated_at",
        ])


def estimate_cost_usd(model, usage):
    model_name = str(model or "")
    prices = MODEL_PRICES_PER_MILLION.get(model_name)
    if not prices:
        prices = next(
            (value for prefix, value in MODEL_PRICES_PER_MILLION.items() if model_name.startswith(prefix)),
            None,
        )
    if not prices:
        return 0
    cached = int((usage or {}).get("cached_input_tokens") or 0)
    input_tokens = max(0, int((usage or {}).get("input_tokens") or 0) - cached)
    output_tokens = int((usage or {}).get("output_tokens") or 0)
    return round(
        (input_tokens * prices["input"] + cached * prices["cached_input"] + output_tokens * prices["output"])
        / 1_000_000,
        8,
    )
