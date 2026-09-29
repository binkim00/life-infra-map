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

    def test_parenthesized_korean_branch_and_floor_note_collapse(self):
        results = merge_map_place_results([
            {"id": 1, "name": "투썸플레이스서면지오플레이스점", "address": "부산광역시 부산진구 동천로 4", "lat": 35.1494319, "lng": 129.0639733},
            {"id": 2, "name": "투썸플레이스(서면지오플레이스점)", "address": "부산광역시 부산진구 동천로 4, 1층 1015호 (전포동)", "lat": 35.1495263, "lng": 129.0648619},
        ])
        self.assertEqual(len(results), 1)

    def test_different_parenthesized_korean_branches_remain_separate(self):
        results = merge_map_place_results([
            {"id": 1, "name": "투썸플레이스(서면점)", "address": "부산 부산진구 중앙대로 1", "lat": 35.15, "lng": 129.06},
            {"id": 2, "name": "투썸플레이스(전포점)", "address": "부산 부산진구 중앙대로 1", "lat": 35.15, "lng": 129.06},
        ])
        self.assertEqual(len(results), 2)

    def test_optional_city_and_branch_at_same_address_collapse(self):
        results = merge_map_place_results([
            {"id": 1, "name": "투썸플레이스문현금융단지점", "address": "부산광역시 부산진구 중앙번영로 31, 1-3층", "lat": 35.1451209, "lng": 129.0627095},
            {"id": 2, "name": "투썸플레이스 부산문현금융단지점", "address": "부산 부산진구 중앙번영로 31", "lat": 35.1450871, "lng": 129.0627170},
        ])
        self.assertEqual(len(results), 1)

    def test_short_brand_and_branch_at_identical_address_collapse(self):
        results = merge_map_place_results([
            {"id": 1, "name": "투썸플레이스", "address": "부산광역시 남구 전포대로 26", "lat": 35.1393063, "lng": 129.0679961},
            {"id": 2, "name": "투썸플레이스 부산문현점", "address": "부산 남구 전포대로 26", "lat": 35.1392124, "lng": 129.0679542},
        ])
        self.assertEqual(len(results), 1)

    def test_brand_alias_and_optional_area_at_same_address_collapse(self):
        results = merge_map_place_results([
            {"id": 1, "name": "이디야커피 부산서면롯데후문점", "address": "부산 부산진구 부전로66번길 22", "lat": 35.1558054, "lng": 129.0558850},
            {"id": 2, "name": "이디야롯데후문점", "address": "부산광역시 부산진구 부전로66번길 22, 지상1층", "lat": 35.1557777, "lng": 129.0558787},
        ])
        self.assertEqual(len(results), 1)

    @patch("recommendations.views.search_saved_map_places", return_value=([], 0, {}))
    @patch("recommendations.views._resolve_anchor_location", return_value={
        "status": "resolved", "source": "area_gazetteer", "lat": 35.156790,
        "lng": 129.056416, "label": "서면",
    })
    def test_brand_and_known_area_use_area_center_and_radius(self, resolve_anchor, search_places):
        response = self.client.get(
            "/api/recommendations/place-search/",
            {"q": "투썸플레이스 서면", "source": "db", "limit": 10},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["filters"]["effective_radius"], 5000)
        self.assertEqual(search_places.call_args.kwargs["lat"], 35.156790)
        self.assertEqual(search_places.call_args.kwargs["lng"], 129.056416)
        resolve_anchor.assert_called_with("서면", address_first=False)


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
