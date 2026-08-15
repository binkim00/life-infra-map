from django.test import TestCase, override_settings

from recommendations.models import ProviderQuotaUsage
from recommendations.services.canonical_ai_evidence_extractor import (
    extract_canonical_tags_from_evidence,
)


@override_settings(TAG_COLLECTION_AI_DAILY_LIMIT=10)
class CanonicalAiEvidenceExtractorTests(TestCase):
    def test_accepts_only_allowed_tag_with_verbatim_evidence_span(self):
        result = extract_canonical_tags_from_evidence(
            "이 카페는 오래 머물기 좋고 좌석이 편하다.",
            ["장기체류좋음"],
            request_call=lambda *args, **kwargs: {
                "matches": [
                    {"tag": "장기체류좋음", "polarity": "positive", "evidence_span": "오래 머물기 좋고"},
                    {"tag": "새로운자유태그", "polarity": "positive", "evidence_span": "좌석이 편하다"},
                    {"tag": "장기체류좋음", "polarity": "positive", "evidence_span": "원문에 없는 문장"},
                ]
            },
        )
        self.assertEqual(result, [{
            "tag_name": "장기체류좋음",
            "polarity": "positive",
            "evidence_span": "오래 머물기 좋고",
        }])
        quota = ProviderQuotaUsage.objects.get(provider="openai_evidence")
        self.assertEqual(quota.request_count, 1)
        self.assertEqual(quota.success_count, 1)

    @override_settings(TAG_COLLECTION_AI_DAILY_LIMIT=0)
    def test_does_not_call_ai_after_quota_is_exhausted(self):
        calls = []
        result = extract_canonical_tags_from_evidence(
            "조용한 공간",
            ["조용함"],
            request_call=lambda *args, **kwargs: calls.append(1),
        )
        self.assertEqual(result, [])
        self.assertEqual(calls, [])

