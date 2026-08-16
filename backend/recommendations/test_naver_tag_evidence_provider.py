from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from recommendations.services.naver_tag_evidence_provider import (
    collect_naver_tag_evidence,
    evidence_polarity,
    identity_assessment,
    identity_matches,
    place_search_location_terms,
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

    def test_semas_query_location_prefers_official_district_and_neighborhood(self):
        place = SimpleNamespace(
            address='서울특별시 송파구 송파대로28길 27',
            raw={
                'source_address': '서울특별시 송파구 가락동 100-1',
                'source_road_address': '서울특별시 송파구 송파대로28길 27',
            },
        )
        self.assertEqual(place_search_location_terms(place), ['송파구', '가락동'])

    def test_semas_food_name_in_summary_is_not_enough_when_title_is_another_place(self):
        place = SimpleNamespace(
            name='아비꼬 강남역점',
            address='서울특별시 강남구 봉은사로6길 38',
            category='restaurant',
            source='semas',
        )
        result = identity_assessment(
            place,
            '분위기 좋은 이름없는파스타 후기. 오른편에는 아비꼬 강남역점이 있다. '
            '서울 강남구 봉은사로6길 38',
            title='강남 혼밥 맛집 이름없는파스타 강남역점',
        )
        self.assertFalse(result['matched'])
        self.assertTrue(result['signals']['semas_food_title_required'])

    def test_conflicting_sentiment_is_not_automatically_classified(self):
        self.assertEqual(
            evidence_polarity('조용함', '평일은 조용하지만 주말은 북적이고 시끄럽다'),
            'unknown',
        )

    def test_existing_solo_use_tag_requires_an_explicit_expression(self):
        self.assertEqual(
            evidence_polarity('혼자이용좋음', '혼자 이용하기 좋은 조용한 공간'),
            'positive',
        )
        self.assertEqual(
            evidence_polarity('혼자이용좋음', '혼자 가기 부담스러운 공간'),
            'negative',
        )

    def test_repeated_cafe_feature_phrases_map_to_existing_canonical_tags(self):
        cases = {
            '콘센트있음': '자리마다 콘센트가 설치되어 있다',
            '무료와이파이': '와이파이도 잘 터져서 작업하기 편하다',
            '혼자이용좋음': '혼자 책 읽기 좋은 카페다',
            '대화하기좋음': '친구와 이야기 나누기 좋은 공간이다',
            '장기체류좋음': '오래 앉아서 시간을 보내기 좋은 곳이다',
        }
        for tag_name, snippet in cases.items():
            with self.subTest(tag_name=tag_name):
                self.assertEqual(evidence_polarity(tag_name, snippet), 'positive')

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

    def test_accepts_distinctive_exact_name_in_title_without_snippet_address(self):
        place = SimpleNamespace(
            name='남도해양열차 에스트레인(S-train)',
            address='부산광역시 동구 중앙대로 206',
            source='tour_api',
        )
        title = '남도해양열차 에스트레인 S-train 후기'
        result = identity_assessment(place, title + ' 창밖 전망이 좋다', title=title)
        self.assertTrue(result['matched'])
        self.assertEqual(result['signals']['contextual_score'], 15)

    def test_does_not_accept_incidental_exact_name_in_summary(self):
        place = SimpleNamespace(
            name='그런고로',
            address='부산광역시 부산진구 서전로 40',
            source='tour_api',
        )
        result = identity_assessment(
            place,
            '부산 돈까스 후기 그런고로 맛있게 먹었다',
            title='부산 돈까스 후기',
        )
        self.assertFalse(result['matched'])

    def test_generic_facility_word_does_not_make_two_distinctive_terms(self):
        place = SimpleNamespace(
            name='운현궁 화장실',
            address='서울특별시 종로구 삼일대로 464',
            source='public_toilet_standard',
        )
        text = '서울 종로구 숙소 화장실 후기이며 주변에는 운현궁이 있다'
        result = identity_assessment(place, text, title='서울 숙소 후기')
        self.assertFalse(result['matched'])
        self.assertEqual(result['signals']['distinctive_name_terms'], ['운현궁'])

    def test_tourism_parking_wait_is_not_attraction_wait_evidence(self):
        result = evidence_polarity(
            '웨이팅적음',
            '주차 기준 대기시간과 웨이팅 없이 바로 주차 가능',
            category='tourism',
        )
        self.assertEqual(result, 'unknown')

    def test_explicit_other_region_blocks_title_match(self):
        place = SimpleNamespace(
            name='강변둥지공원',
            address='부산광역시 북구 화명동 188-2',
            source='citypark_standard',
        )
        result = identity_assessment(
            place,
            '서울 강변둥지공원 산책 후기',
            title='서울 강변둥지공원 산책 후기',
        )
        self.assertFalse(result['matched'])
        self.assertTrue(result['signals']['explicit_region_mismatch'])

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
