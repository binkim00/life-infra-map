from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from recommendations.services.naver_tag_evidence_provider import (
    collect_naver_tag_evidence,
    evidence_polarity,
    identity_matches,
)


class NaverTagEvidenceProviderTests(SimpleTestCase):
    place = SimpleNamespace(
        name='서면 테스트 카페',
        address='부산광역시 부산진구 부전동 1',
        category='cafe',
    )

    def test_matches_brand_and_branch_tokens_when_separated(self):
        branch = SimpleNamespace(
            name='스타벅스 강서녹산DT점',
            address='부산 강서구 낙동남로511번길 42',
        )
        text = '스타벅스 샌드위치 후기 중 강서 녹산 DT점 방문 기록'

        self.assertTrue(identity_matches(branch, text))

    def test_conflicting_sentiment_is_not_automatically_classified(self):
        self.assertEqual(
            evidence_polarity('조용함', '평일은 조용하지만 주말은 북적이고 시끄럽다'),
            'unknown',
        )

    @patch('recommendations.services.naver_tag_evidence_provider._request_channel')
    def test_collects_positive_and_negative_identity_matched_snippets(self, request_channel):
        request_channel.return_value = {'items': [
            {
                'title': '서면 테스트 카페 조용한 후기',
                'description': '부산진구 부전동에서 평일에는 조용하고 차분했다.',
                'link': 'https://blog.example.com/positive',
                'postdate': '20260801',
            },
            {
                'title': '서면 테스트 카페 주말 후기',
                'description': '부산진구에 있는 곳으로 주말에는 북적이고 시끄럽다.',
                'link': 'https://blog.example.com/negative',
                'postdate': '20260802',
            },
        ]}

        result = collect_naver_tag_evidence(self.place, '조용함')

        self.assertEqual(
            [item['polarity'] for item in result['evidences']],
            ['positive', 'negative'],
        )
        self.assertEqual(result['evidences'][0]['observed_date'], '2026-08-01')

    @patch('recommendations.services.naver_tag_evidence_provider._request_channel')
    def test_rejects_same_name_without_address_identity(self, request_channel):
        request_channel.return_value = {'items': [{
            'title': '서면 테스트 카페 조용한 후기',
            'description': '서울 강남구에서 방문한 조용한 카페다.',
            'link': 'https://blog.example.com/wrong-place',
        }]}

        result = collect_naver_tag_evidence(self.place, '조용함')

        self.assertEqual(result['polarity'], 'unknown')
        self.assertEqual(result['error'], 'insufficient_evidence')

    @patch('recommendations.services.naver_tag_evidence_provider._request_channel')
    def test_keeps_only_one_evidence_per_independent_url(self, request_channel):
        item = {
            'title': '서면 테스트 카페 조용한 후기',
            'description': '부산진구 부전동에서 평일에는 조용했다.',
            'link': 'https://blog.example.com/same-post',
            'postdate': '20260801',
        }
        request_channel.return_value = {'items': [item, dict(item)]}

        result = collect_naver_tag_evidence(self.place, '조용함')

        self.assertEqual(len(result['evidences']), 1)
