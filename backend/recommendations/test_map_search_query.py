from django.test import SimpleTestCase

from recommendations.services.map_search import split_location_category_query


class GeneralMapSearchQueryTests(SimpleTestCase):
    def test_splits_explicit_location_and_public_category(self):
        self.assertEqual(
            split_location_category_query("사상역 흡연구역"),
            {"anchor_location": "사상역", "category_query": "흡연구역"},
        )

    def test_preserves_literal_category_modifiers(self):
        self.assertEqual(
            split_location_category_query("종로 무료 주차장"),
            {"anchor_location": "종로", "category_query": "무료 주차장"},
        )

    def test_does_not_reinterpret_a_named_place(self):
        self.assertEqual(
            split_location_category_query("광안리해수욕장"),
            {"anchor_location": "", "category_query": ""},
        )
