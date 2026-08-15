from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from recommendations.services.ai_json_client import call_ai_json
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


def extract_canonical_tags_from_evidence(text, allowed_tags, *, request_call=None):
    allowed = [tag for tag in allowed_tags if tag in CANONICAL_TAGS]
    if not text.strip() or not allowed:
        return []
    request_call = request_call or call_ai_json
    if not reserve_ai_call():
        return []
    succeeded = False
    try:
        payload = request_call(
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
        succeeded = True
    except Exception:
        payload = {}
    finally:
        settle_ai_call(succeeded=succeeded)
    results = []
    compact_text = compact(text)
    seen = set()
    for row in payload.get("matches") or []:
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
    return results


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


def settle_ai_call(*, succeeded):
    ProviderQuotaUsage.objects.filter(
        provider="openai_evidence",
        usage_date=timezone.localdate(),
    ).update(
        reserved_count=F("reserved_count") - 1,
        request_count=F("request_count") + 1,
        success_count=F("success_count") + int(succeeded),
        failed_count=F("failed_count") + int(not succeeded),
    )
