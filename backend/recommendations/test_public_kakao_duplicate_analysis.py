from types import SimpleNamespace

from django.test import SimpleTestCase

from recommendations.management.commands.analyze_public_kakao_duplicates import assess_pair


class PublicKakaoDuplicateAnalysisTests(SimpleTestCase):
    def place(self, **overrides):
        values = {
            "name": "한강공원", "address": "서울특별시 영등포구 여의도동 1",
            "lat": 37.528, "lng": 126.934,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_exact_nearby_name_and_supported_address_is_high_confidence(self):
        result = assess_pair(self.place(), self.place(lat=37.52801, lng=126.93401))
        self.assertEqual(result["status"], "high_confidence")

    def test_similar_name_with_weak_address_remains_ambiguous(self):
        result = assess_pair(
            self.place(name="중앙공원", address="부산광역시 중구 중앙동"),
            self.place(name="중앙 근린공원", address="부산광역시 중구 다른동", lat=37.5281),
        )
        self.assertNotEqual(result["status"], "high_confidence")

    def test_region_mismatch_is_never_a_candidate(self):
        result = assess_pair(
            self.place(address="서울특별시 영등포구 여의도동"),
            self.place(address="경기도 수원시 팔달구", lat=37.52801, lng=126.93401),
        )
        self.assertEqual(result["status"], "unmatched")
