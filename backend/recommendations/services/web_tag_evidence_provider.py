"""Paid web search is source discovery only; it never creates Evidence."""

from time import monotonic
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from recommendations.models import ProviderQuotaUsage
from recommendations.services.ai_web_search_provider import (
    _extract_response_texts_and_sources,
    _get_responses_api_config,
    _safe_text,
)


PROVIDER = "openai_web_search"
TOOL_PRICE_USD = 0.01
MODEL_PRICES_PER_MILLION = {
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "cached_input": 0.005, "output": 0.40},
}
FAILURE_REASONS = frozenset({
    "NO_FINAL_OUTPUT", "INCOMPLETE_RESPONSE", "PROVIDER_ERROR", "NO_SOURCE_RESULT",
    "PAGE_NOT_ACCESSIBLE", "IDENTITY_MISMATCH", "NO_TARGET_FEATURE",
    "VERBATIM_VALIDATION_FAILED", "CITATION_VALIDATION_FAILED",
    "DUPLICATE_EVIDENCE", "STALE_ONLY",
})
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "ref", "source"}
BLOCKED_HOST_PARTS = (
    "map.naver.com", "m.place.naver.com", "place.map.kakao.com",
    "map.kakao.com", "google.com/maps", "maps.google.",
)
CATEGORY_TAGS = {
    "cafe": (
        "조용함", "노트북작업", "작업하기좋음", "콘센트있음", "무료와이파이",
        "혼자이용좋음", "분위기좋음", "데이트좋음", "대화하기좋음", "장기체류좋음",
    ),
    "restaurant": (
        "혼밥좋음", "분위기좋음", "데이트좋음", "대화하기좋음", "웨이팅적음", "혼자이용좋음",
    ),
}


def discover_web_sources(place, target_tags, *, request_post=None):
    """Discover cited URLs only. Page verification and tag extraction are separate."""
    allowed = [tag for tag in target_tags if tag in CATEGORY_TAGS.get(place.category, ())]
    if not allowed:
        return _result(error="NO_TARGET_FEATURE")
    if not getattr(settings, "WEB_EVIDENCE_SEARCH_ENABLED", False):
        return _result(executed=False, error="PROVIDER_DISABLED")
    api_key, api_url = _get_responses_api_config("openai")
    if not api_key or not api_url:
        return _result(executed=False, error="PROVIDER_DISABLED")
    if not reserve_web_call():
        return _result(executed=False, error="COST_OR_QUOTA_LIMIT")

    query = "{} {} {}".format(place.name, place.address, " ".join(allowed)).strip()
    model = getattr(settings, "WEB_EVIDENCE_SEARCH_MODEL", "gpt-5-mini")
    payload = {
        "model": model,
        "instructions": (
            "Find public source URLs for the exact Korean place. Return a very short answer "
            "with citations. Do not evaluate identity, infer features, quote evidence, or create tags."
        ),
        "input": query,
        "tools": [{"type": "web_search", "search_context_size": "low"}],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "max_output_tokens": getattr(settings, "WEB_EVIDENCE_SEARCH_MAX_OUTPUT_TOKENS", 800),
    }
    started = monotonic()
    succeeded = False
    data = {}
    try:
        response = (request_post or requests.post)(
            api_url,
            headers={"Authorization": "Bearer {}".format(api_key), "Content-Type": "application/json"},
            json=payload,
            timeout=getattr(settings, "AI_REQUEST_TIMEOUT", 20),
        )
        response.raise_for_status()
        data = response.json()
        succeeded = True
    except (requests.RequestException, ValueError):
        pass
    usage = response_usage(data)
    tool_actions = web_search_action_count(data) if succeeded else 0
    cost = estimate_web_cost_usd(model, usage, tool_actions)
    settle_web_call(
        succeeded=succeeded, usage=usage, model=model,
        tool_actions=tool_actions, cost_usd=cost,
    )
    diagnostics = response_diagnostics(data)
    texts, sources = _extract_response_texts_and_sources(data)
    candidates = []
    seen = set()
    for source in sources:
        url = canonical_url(source.get("url"))
        if not url or url in seen or is_blocked_source(url):
            continue
        seen.add(url)
        candidates.append({
            "url": url,
            "title": _safe_text(source.get("title"), 180),
            "domain": urlsplit(url).netloc.lower(),
        })
    if not succeeded:
        failure = "PROVIDER_ERROR"
    elif diagnostics["status"] == "incomplete":
        failure = "INCOMPLETE_RESPONSE"
    elif not candidates:
        failure = "NO_SOURCE_RESULT"
    elif not texts:
        failure = "NO_FINAL_OUTPUT"
    else:
        failure = ""
    return {
        "executed": True,
        "requests": 1,
        "source_candidates": candidates,
        "evidences": [],
        "error": failure,
        "query": query,
        "latency_ms": round((monotonic() - started) * 1000, 2),
        "usage": usage,
        "cost_usd": cost,
        "diagnostics": diagnostics,
    }


def collect_web_tag_evidence(place, target_tags, *, request_post=None, **_kwargs):
    """Compatibility entrypoint. It intentionally returns candidates, never Evidence."""
    return discover_web_sources(place, target_tags, request_post=request_post)


def classify_legacy_failure(error_code, stats):
    stats = stats or {}
    if error_code == "PAGE_NOT_ACCESSIBLE" and int(stats.get("results_checked") or 0) > 0:
        if not int(stats.get("evidences") or 0) and not (stats.get("failure_reasons") or []):
            return "NO_FINAL_OUTPUT"
    if error_code in FAILURE_REASONS:
        return error_code
    return error_code or "NO_SOURCE_RESULT"


def response_diagnostics(data):
    output = data.get("output") or [] if isinstance(data, dict) else []
    texts, _ = _extract_response_texts_and_sources(data)
    return {
        "response_id": _safe_text(data.get("id"), 120) if isinstance(data, dict) else "",
        "status": _safe_text(data.get("status"), 40) if isinstance(data, dict) else "",
        "incomplete_details": data.get("incomplete_details") if isinstance(data, dict) else None,
        "output_item_types": [
            _safe_text(item.get("type"), 50) for item in output if isinstance(item, dict)
        ],
        "output_text_exists": bool(texts),
        "tool_action_count": web_search_action_count(data),
    }


def reserve_web_call():
    limit = getattr(settings, "WEB_EVIDENCE_SEARCH_DAILY_LIMIT", 500)
    cap = getattr(settings, "WEB_EVIDENCE_SEARCH_MAX_COST_USD", 5.0)
    reserve_cost = getattr(settings, "WEB_EVIDENCE_SEARCH_RESERVE_COST_USD", 0.02)
    with transaction.atomic():
        quota, _ = ProviderQuotaUsage.objects.select_for_update().get_or_create(
            provider=PROVIDER, usage_date=timezone.localdate(), defaults={"daily_limit": limit}
        )
        spent = float((quota.metadata or {}).get("estimated_cost_usd") or 0)
        if (
            limit < 1
            or quota.request_count + quota.reserved_count >= min(limit, quota.daily_limit)
            or spent + (quota.reserved_count + 1) * reserve_cost > cap
        ):
            return False
        quota.reserved_count += 1
        quota.save(update_fields=["reserved_count", "updated_at"])
    return True


def settle_web_call(*, succeeded, usage, model, tool_actions, cost_usd):
    with transaction.atomic():
        quota = ProviderQuotaUsage.objects.select_for_update().get(
            provider=PROVIDER, usage_date=timezone.localdate()
        )
        quota.reserved_count = max(0, quota.reserved_count - 1)
        quota.request_count += 1
        quota.success_count += int(succeeded)
        quota.failed_count += int(not succeeded)
        metadata = dict(quota.metadata or {})
        for key in ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens"):
            metadata[key] = int(metadata.get(key) or 0) + int(usage.get(key) or 0)
        metadata["web_search_calls"] = int(metadata.get("web_search_calls") or 0) + tool_actions
        metadata["estimated_cost_usd"] = round(
            float(metadata.get("estimated_cost_usd") or 0) + cost_usd, 8
        )
        metadata["model"] = model
        quota.metadata = metadata
        quota.save(update_fields=[
            "reserved_count", "request_count", "success_count", "failed_count", "metadata", "updated_at",
        ])


def estimate_web_cost_usd(model, usage, tool_actions):
    prices = MODEL_PRICES_PER_MILLION.get(str(model or ""))
    token_cost = 0.0
    if prices:
        cached = int(usage.get("cached_input_tokens") or 0)
        regular = max(0, int(usage.get("input_tokens") or 0) - cached)
        token_cost = (
            regular * prices["input"] + cached * prices["cached_input"]
            + int(usage.get("output_tokens") or 0) * prices["output"]
        ) / 1_000_000
    return round(tool_actions * TOOL_PRICE_USD + token_cost, 8)


def response_usage(data):
    usage = data.get("usage") or {} if isinstance(data, dict) else {}
    details = usage.get("input_tokens_details") or {}
    return {
        "input_tokens": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "cached_input_tokens": int(details.get("cached_tokens") or 0),
    }


def web_search_action_count(value):
    if isinstance(value, dict):
        return int(value.get("type") == "web_search_call") + sum(
            web_search_action_count(item) for item in value.values()
        )
    if isinstance(value, list):
        return sum(web_search_action_count(item) for item in value)
    return 0


def canonical_url(value):
    value = _safe_text(value, 500)
    if not value.startswith(("http://", "https://")):
        return ""
    parts = urlsplit(value)
    query = urlencode([
        (key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def is_blocked_source(url):
    lowered = str(url or "").lower()
    return any(part in lowered for part in BLOCKED_HOST_PARTS)


def _result(*, executed=True, error=""):
    return {
        "executed": executed, "requests": int(executed), "source_candidates": [],
        "evidences": [], "error": error, "diagnostics": {}, "usage": {}, "cost_usd": 0,
    }
