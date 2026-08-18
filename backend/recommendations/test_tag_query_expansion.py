from unittest.mock import patch

from django.test import TestCase, override_settings

from recommendations.models import Place
from recommendations.services.adaptive_tag_collection import targeted_profiles
from recommendations.services.naver_tag_evidence_provider import polarity_assessment
from recommendations.services.naver_tag_evidence_provider import identity_assessment
from recommendations.services.place_tag_collection import collect_naver_place_evidence


class TagQueryExpansionTests(TestCase):
    def make_place(self, category="cafe"):
        return Place.objects.create(
            name="확장테스트카페" if category == "cafe" else "확장테스트식당",
            category=category,
            address="부산광역시 부산진구 테스트로 1",
            lat=35.1,
            lng=129.0,
            source="kakao_local",
            external_id="expansion-{}".format(category),
        )

    def test_qualitative_variants_are_supporting_or_direct(self):
        cases = (
            ("작업하기좋음", "작업이나 공부하러 가기도 괜찮고", "SUPPORTING"),
            ("혼자이용좋음", "혼자 온 손님들이 많았다", "DIRECT"),
            ("데이트좋음", "데이트 장소로 추천한다", "DIRECT"),
            ("대화하기좋음", "좌석 간격이 넓고 한적해서 이야기 나누기 좋다", "DIRECT"),
        )
        for tag, text, strength in cases:
            with self.subTest(tag=tag):
                result = polarity_assessment(tag, text, category="cafe")
                self.assertEqual(result["polarity"], "positive")
                self.assertEqual(result["strength"], strength)

    def test_weak_signal_is_not_saved_as_positive(self):
        result = polarity_assessment("작업하기좋음", "테이블 넓은 카페", category="cafe")
        self.assertEqual(result["polarity"], "unknown")
        self.assertEqual(result["strength"], "WEAK")

    def test_short_food_name_must_be_exact_in_title(self):
        place = Place.objects.create(
            name="우드로", category="cafe", address="부산광역시 금정구 부산대학로 64",
            lat=35.1, lng=129.0, source="kakao_local", external_id="short-name",
        )
        result = identity_assessment(
            place,
            "부산 금정구의 다른 카페입니다. 본문 주변 문장에 우드로라는 단어가 있습니다.",
            title="헤이위치 카페 후기",
        )
        self.assertFalse(result["matched"])
        self.assertTrue(result["signals"]["short_food_title_required"])

    @override_settings(TAG_COLLECTION_ADOPTED_TARGET_CLUSTERS=("work_sparse",))
    def test_targeted_profiles_expand_to_three_stages(self):
        rows = targeted_profiles(
            ("노트북작업", "콘센트있음"),
            ("노트북작업", "콘센트있음", "작업하기좋음"),
            max_stages=3,
        )
        self.assertEqual([row[1] for row in rows], ["노트북", "카공 공부", "콘센트 충전"])

    @patch("recommendations.services.place_tag_collection.acquire_provider_slot")
    @patch("recommendations.services.place_tag_collection._request_channel")
    def test_one_result_extracts_multiple_tags_and_early_exits(self, request, _slot):
        place = self.make_place()
        request.return_value = {"items": [{
            "title": "확장테스트카페 부산진구 카공 후기",
            "description": "자리마다 콘센트가 있고 노트북 작업과 공부하기 좋은 조용한 카페입니다.",
            "link": "https://example.com/post/1",
            "postdate": "20260801",
        }]}
        result = collect_naver_place_evidence(
            place,
            ("노트북작업", "콘센트있음", "작업하기좋음", "조용함"),
            strategy="targeted_only",
            targeted_tags=("노트북작업", "콘센트있음"),
        )
        self.assertEqual(result["requests"], 1)
        self.assertGreaterEqual(len(result["evidences"]), 3)
        self.assertEqual(result["search_attempts"][0]["actual_query"], "확장테스트카페 부산진구 노트북")
        self.assertTrue(result["search_attempts"][0]["results"][0]["evidence_candidate"])
