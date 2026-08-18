import json
from types import SimpleNamespace

from django.test import TestCase, override_settings

from recommendations.models import ProviderQuotaUsage
from recommendations.services.web_tag_evidence_provider import (
    classify_legacy_failure,
    discover_web_sources,
    estimate_web_cost_usd,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@override_settings(
    OPENAI_API_KEY="test-key", WEB_EVIDENCE_SEARCH_ENABLED=True,
    WEB_EVIDENCE_SEARCH_DAILY_LIMIT=10, WEB_EVIDENCE_SEARCH_MAX_COST_USD=5,
    WEB_EVIDENCE_SEARCH_MODEL="gpt-5-mini",
)
class WebSourceDiscoveryTests(TestCase):
    place = SimpleNamespace(name="서면 테스트카페", address="부산광역시 부산진구", category="cafe")

    def test_discovers_source_without_creating_evidence(self):
        payload = {
            "id": "resp_1", "status": "completed",
            "output": [
                {"type": "web_search_call", "action": {"sources": [{"url": "https://example.com/cafe", "title": "공식"}]}},
                {"type": "message", "content": [{"type": "output_text", "text": "source found"}]},
            ],
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        }
        result = discover_web_sources(
            self.place, ["콘센트있음"], request_post=lambda *args, **kwargs: FakeResponse(payload)
        )
        self.assertEqual(len(result["source_candidates"]), 1)
        self.assertEqual(result["evidences"], [])
        self.assertEqual(result["diagnostics"]["response_id"], "resp_1")

    def test_no_final_output_is_distinct_from_page_failure(self):
        payload = {
            "status": "completed",
            "output": [{"type": "web_search_call", "action": {"sources": [{"url": "https://example.com", "title": "source"}]}}],
            "usage": {},
        }
        result = discover_web_sources(
            self.place, ["콘센트있음"], request_post=lambda *args, **kwargs: FakeResponse(payload)
        )
        self.assertEqual(result["error"], "NO_FINAL_OUTPUT")

    def test_legacy_page_error_is_reported_as_no_final_output(self):
        self.assertEqual(
            classify_legacy_failure("PAGE_NOT_ACCESSIBLE", {"results_checked": 1, "evidences": 0, "failure_reasons": []}),
            "NO_FINAL_OUTPUT",
        )

    def test_gpt5_mini_cost_includes_tokens_and_tool_actions(self):
        cost = estimate_web_cost_usd(
            "gpt-5-mini",
            {"input_tokens": 1000, "cached_input_tokens": 200, "output_tokens": 100},
            2,
        )
        self.assertGreater(cost, 0.02)

    @override_settings(WEB_EVIDENCE_SEARCH_ENABLED=False)
    def test_disabled_provider_never_calls_api(self):
        calls = []
        result = discover_web_sources(
            self.place, ["콘센트있음"], request_post=lambda *args, **kwargs: calls.append(1)
        )
        self.assertFalse(result["executed"])
        self.assertEqual(calls, [])
