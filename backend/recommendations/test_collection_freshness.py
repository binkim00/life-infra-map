from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from recommendations.services.tag_freshness import evidence_is_expired
from recommendations.services.tag_source_policy import NAVER_BLOG_SEARCH
from recommendations.services.place_tag_collection import collect_naver_place_evidence
from recommendations.services.naver_tag_evidence_provider import collect_naver_tag_evidence


class CollectionFreshnessTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 10, 14, 12))
        self.place = SimpleNamespace(
            id=1, name="테스트 카페", address="부산광역시 부산진구 부전동",
            category="cafe", raw={},
        )

    def item(self, days):
        return {
            "title": "테스트 카페 후기",
            "description": "부산진구 부전동의 조용한 카페로 전망 좋은 좌석에서 노트북 작업을 할 수 있다.",
            "link": "https://blog.example.test/review",
            "postdate": (self.now - timedelta(days=days)).strftime("%Y%m%d"),
        }

    def test_expiry_boundary_and_tag_specific_ttl(self):
        self.assertTrue(evidence_is_expired("조용함", NAVER_BLOG_SEARCH,
                                           self.now - timedelta(days=120), now=self.now))
        self.assertFalse(evidence_is_expired("조용함", NAVER_BLOG_SEARCH,
                                            self.now - timedelta(days=120) + timedelta(seconds=1), now=self.now))
        self.assertFalse(evidence_is_expired("전망좋음", NAVER_BLOG_SEARCH,
                                            self.now - timedelta(days=200), now=self.now))

    def test_unknown_date_and_nonexpiring_source_keep_existing_behavior(self):
        self.assertFalse(evidence_is_expired("조용함", NAVER_BLOG_SEARCH, None, now=self.now))
        self.assertFalse(evidence_is_expired("조용함", "external_data",
                                            self.now - timedelta(days=999), now=self.now))

    def collect(self, items, tags, allow_ai=False):
        with patch("recommendations.services.place_tag_collection._request_channel", return_value={"items": items}) as request, \
             patch("recommendations.services.place_tag_collection.acquire_provider_slot"), \
             patch("recommendations.services.place_tag_collection.identity_assessment", return_value={"matched": True, "score": 90}), \
             patch("recommendations.services.tag_freshness.timezone.now", return_value=self.now):
            result = collect_naver_place_evidence(self.place, requested_tags=tags, allow_ai=allow_ai)
        return result, request.call_count

    def test_expired_results_are_excluded_without_ai_or_extra_requests(self):
        with patch("recommendations.services.canonical_ai_evidence_extractor.extract_canonical_tags_from_evidence_detailed") as ai:
            result, requests = self.collect([self.item(200)], ["조용함"], allow_ai=True)
        self.assertEqual(result["evidences"], [])
        self.assertEqual(requests, 1)
        self.assertEqual(result["diagnostics"]["expired_results"], 1)
        self.assertEqual(result["search_attempts"][0]["results"][0]["rejection_reason"], "EXPIRED_SOURCE")
        ai.assert_not_called()

    def test_same_article_keeps_longer_lived_tag_only(self):
        result, _ = self.collect([self.item(200)], ["조용함", "전망좋음"])
        self.assertEqual([e["tag_name"] for e in result["evidences"]], ["전망좋음"])
        self.assertEqual(result["evidences"][0]["observed_date"], self.item(200)["postdate"])

    def test_current_positive_and_negative_evidence_are_preserved(self):
        positive = self.item(20)
        negative = dict(positive, link="https://blog.example.test/negative", description="부산진구 테스트 카페는 소음이 심하고 시끄럽다.")
        result, _ = self.collect([positive, negative], ["조용함"])
        self.assertEqual([e["polarity"] for e in result["evidences"]], ["positive", "negative"])

    def test_single_tag_provider_excludes_expired_and_handles_invalid_date(self):
        for postdate, expected in ((self.item(200)["postdate"], False), ("20260230", True)):
            with self.subTest(postdate=postdate), \
                 patch("recommendations.services.naver_tag_evidence_provider._request_channel", return_value={"items": [dict(self.item(20), postdate=postdate)]}), \
                 patch("recommendations.services.naver_tag_evidence_provider.identity_assessment", return_value={"matched": True, "score": 90}), \
                 patch("recommendations.services.tag_freshness.timezone.now", return_value=self.now):
                result = collect_naver_tag_evidence(self.place, "조용함")
            self.assertEqual(bool(result.get("evidences")), expected)
