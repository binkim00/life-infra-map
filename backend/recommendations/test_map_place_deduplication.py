from unittest.mock import patch
from django.test import SimpleTestCase, TestCase

from recommendations.views import merge_map_place_results
from recommendations.models import Place
from recommendations.services.map_search import search_saved_places
from recommendations.services import map_search


class MapPlaceDeduplicationTests(SimpleTestCase):
    def test_english_alias_and_same_address_collapse(self):
        results = merge_map_place_results([
            {"id": 1, "name": "셰르라이프앤스타일", "address": "부산 부산진구 전포대로 10", "lat": 35.15, "lng": 129.06, "result_source": "db"},
            {"id": 2, "name": "셰르라이프앤스타일(Cher Life&Style)", "address": "부산 부산진구 전포대로 10", "lat": 35.1504, "lng": 129.06, "result_source": "db"},
        ])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["duplicate_count"], 2)

    def test_similarly_named_branches_at_different_addresses_remain_separate(self):
        results = merge_map_place_results([
            {"id": 1, "name": "스타벅스 서면", "address": "부산 부산진구 중앙대로 1", "lat": 35.15, "lng": 129.06},
            {"id": 2, "name": "스타벅스 서면점", "address": "부산 부산진구 중앙대로 2", "lat": 35.151, "lng": 129.06},
        ])
        self.assertEqual(len(results), 2)

    def test_same_road_address_with_unit_note_and_branch_suffix_collapses(self):
        results = merge_map_place_results([
            {"id": 1, "name": "스타벅스 서면센트럴스퀘어", "address": "부산광역시 부산진구 중앙대로666번길 50", "lat": 35.1518464, "lng": 129.0603038},
            {"id": 2, "name": "스타벅스 서면센트럴스퀘어점", "address": "부산광역시 부산진구 중앙대로666번길 50 (부전동,101호(1층))", "lat": 35.1514578, "lng": 129.0611065},
            {"id": 3, "name": "스타벅스 서면센트럴스퀘어점", "address": "부산 부산진구 중앙대로666번길 50", "lat": 35.15140657895, "lng": 129.06083470477, "result_source": "kakao"},
        ])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["duplicate_count"], 3)


class PrefilteredNameSearchTests(TestCase):
    def test_name_search_without_explicit_radius_uses_one_db_radius_pass(self):
        place = Place.objects.create(
            name="스타벅스 서면점", category="cafe", address="부산 부산진구 중앙대로 1",
            source="test", lat=35.15, lng=129.06,
        )
        with patch("recommendations.services.map_search.apply_radius_filter", wraps=map_search.apply_radius_filter) as radius_filter:
            results, _, _ = search_saved_places(
                keyword="스타벅스 서면", lat=35.15, lng=129.06,
                queryset=Place.objects.filter(pk=place.pk), prefiltered=True,
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(radius_filter.call_count, 1)

    @patch("recommendations.views._resolve_anchor_location", return_value={"status": "unresolved"})
    def test_prefix_shortfall_falls_back_to_infix_name_matches(self, _resolve):
        for name, external_id in (
            ("스타벅스 서면점", "prefix"),
            ("카페 스타벅스 서면별관", "infix"),
        ):
            Place.objects.create(
                name=name, category="cafe", address="부산 부산진구 서면로 10",
                source="test", external_id=external_id, lat=35.15, lng=129.06,
            )
        response = self.client.get(
            "/api/recommendations/place-search/",
            {"q": "스타벅스 서면", "source": "db", "limit": 2},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            {item["name"] for item in response.json()["results"]},
            {"스타벅스 서면점", "카페 스타벅스 서면별관"},
        )
