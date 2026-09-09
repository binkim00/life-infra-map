"""General map search contracts: no query-specific production exceptions."""
from unittest.mock import patch

from django.test import TestCase

from recommendations.services.area_gazetteer import resolve_area_coordinates
from recommendations.services.area_gazetteer import resolve_area_coordinates_by_token
from recommendations.services.map_search import (
    kakao_place_matches_keyword,
    split_location_category_query,
)
from recommendations.services.conversation_sessions import result_references
from recommendations.services.ai_search_orchestrator import _resolve_anchor_location


class GeneralSearchContractTests(TestCase):
    url = "/api/recommendations/place-search/"

    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword")
    @patch("recommendations.services.ai_search_orchestrator.search_address")
    def test_address_coordinates_precede_similarly_named_poi(self, address, keyword):
        address.return_value = {"documents": [{"address_name": "임의지역", "y": "36.35", "x": "127.38"}]}
        resolved = _resolve_anchor_location("임의지역", address_first=True)
        self.assertEqual(resolved["source"], "kakao_address")
        self.assertEqual(resolved["lat"], 36.35)
        keyword.assert_not_called()

    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword")
    @patch("recommendations.services.ai_search_orchestrator.search_address")
    def test_ambiguous_address_does_not_guess_a_poi(self, address, keyword):
        address.return_value = {"documents": [{"y": "36", "x": "127"}, {"y": "35", "x": "128"}]}
        self.assertEqual(_resolve_anchor_location("동명이인지역", address_first=True)["status"], "unresolved")
        keyword.assert_not_called()

    def test_station_names_are_not_replaced_by_city_centres(self):
        for query in ("서울역", "하단역", "사상역", "가상의신규역"):
            with self.subTest(query=query):
                self.assertIsNone(resolve_area_coordinates(query))

    def test_compound_locality_prefers_the_more_specific_trailing_area(self):
        self.assertEqual(resolve_area_coordinates_by_token("부산 전포")[2], "전포")
        self.assertEqual(resolve_area_coordinates_by_token("서울 강남구")[2], "강남구")

    def test_category_before_brand_is_not_a_geographic_anchor(self):
        for query in ("카페 테스트브랜드", "식당 임의상호", "카페 테스트 브랜드"):
            with self.subTest(query=query):
                self.assertEqual(split_location_category_query(query)["anchor_location"], "")

    def test_region_can_match_address_without_being_in_place_name(self):
        for region in ("부산", "대전", "서울"):
            with self.subTest(region=region):
                place = {"place_name": "테스트브랜드 중앙점", "address_name": f"{region} 중앙동", "category_name": "카페"}
                self.assertTrue(kakao_place_matches_keyword(place, f"{region} 테스트브랜드"))
                self.assertFalse(kakao_place_matches_keyword(place, "없는상호"))

    @patch("recommendations.views.search_places_by_keyword", return_value={"documents": []})
    def test_named_search_forwards_device_location_without_changing_query(self, search):
        for query in ("테스트브랜드", "새로운 상호", "테스트브랜드 중앙점"):
            for lat, lng in ((35.16, 129.06), (37.56, 126.97), (36.35, 127.38)):
                with self.subTest(query=query, lat=lat):
                    response = self.client.get(self.url, {"q": query, "lat": lat, "lng": lng})
                    self.assertEqual(response.status_code, 200)
                    calls = [call.kwargs for call in search.call_args_list]
                    self.assertTrue(any(call["keyword"] == query and call["lat"] == lat and call["lng"] == lng for call in calls))
                    self.assertTrue(any(call["keyword"] == query and call["lat"] is None and call["lng"] is None for call in calls))
                    search.reset_mock()

    @patch("recommendations.views.search_places_by_keyword", return_value={"documents": []})
    @patch("recommendations.views._resolve_anchor_location")
    def test_commercial_anchor_does_not_replace_brand_with_category(self, resolve, search):
        resolve.return_value = {"status": "resolved", "lat": 37.56, "lng": 126.97, "category_group_code": "CE7"}
        self.client.get(self.url, {"q": "테스트브랜드 카페", "lat": 35.16, "lng": 129.06})
        calls = [call.kwargs for call in search.call_args_list]
        self.assertTrue(any(call["keyword"] == "테스트브랜드 카페" and call["lat"] == 35.16 for call in calls))
        self.assertTrue(any(call["keyword"] == "테스트브랜드 카페" and call["lat"] is None for call in calls))

    @patch("recommendations.views.search_places_by_keyword", return_value={"documents": []})
    @patch("recommendations.views._resolve_anchor_location")
    def test_map_research_uses_map_coordinates_and_category(self, resolve, search):
        resolve.return_value = {"status": "resolved", "lat": 37.56, "lng": 126.97, "category_group_code": "SW8"}
        self.client.get(self.url, {"q": "서울역 카페", "center_mode": "map", "lat": 35.16, "lng": 129.06, "radius": 2300})
        resolve.assert_called_once()
        self.assertEqual(search.call_args.kwargs["keyword"], "카페")
        self.assertEqual(search.call_args.kwargs["lat"], 35.16)
        self.assertEqual(search.call_args.kwargs["radius"], 2300)

    @patch("recommendations.views.search_places_by_keyword")
    @patch("recommendations.views._resolve_anchor_location")
    def test_map_research_keeps_unresolved_brand_with_category(self, resolve, search):
        resolve.return_value = {"status": "failed", "reason": "not_a_location"}
        search.side_effect = [
            {"documents": [{"id": "near-generic", "place_name": "가까운 일반카페", "category_name": "음식점 > 카페", "category_group_code": "CE7", "x": "129.06", "y": "35.16"}]},
            {"documents": [{"id": "brand", "place_name": "테스트브랜드 중앙점", "category_name": "음식점 > 카페", "category_group_code": "CE7", "x": "129.061", "y": "35.161"}]},
        ]
        response = self.client.get(self.url, {"q": "테스트브랜드 카페", "center_mode": "map", "lat": 35.16, "lng": 129.06, "radius": 1500})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([place["name"] for place in response.json()["results"]], ["테스트브랜드 중앙점"])
        self.assertTrue(all(call.kwargs["keyword"] == "테스트브랜드 카페" for call in search.call_args_list))

    @patch("recommendations.views.search_places_by_keyword")
    def test_relevance_page_recovers_exact_named_place_and_ranks_it_first(self, search):
        search.side_effect = [
            {"documents": [{"id": "incidental", "place_name": "서울역떡집", "category_name": "음식점", "x": "129.0", "y": "35.2"}]},
            {"documents": [{"id": "station", "place_name": "서울역", "category_name": "교통 > 기차역", "x": "126.97", "y": "37.55"}]},
        ]
        response = self.client.get(self.url, {"q": "서울역", "lat": 35.16, "lng": 129.06})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["name"], "서울역")

    def test_followup_references_keep_details_and_evidence_status(self):
        result = {"id": "kakao:123", "name": "테스트", "place_url": "https://place.map.kakao.com/123", "result_tier": "best_available", "missing_conditions": ["주차"], "phone": "051-000-0000"}
        self.assertEqual(result_references([result]), [result])

    @patch("recommendations.views.search_places_by_keyword")
    @patch("recommendations.views.search_saved_map_places")
    def test_sufficient_public_infrastructure_db_results_do_not_wait_for_kakao(self, db_search, kakao):
        db_search.return_value = ([{
            "id": index, "name": f"공원 {index}", "category": "city_park",
            "lat": 35.15, "lng": 129.06, "distance": index,
        } for index in range(30)], 30, {"matched_categories": ["city_park"]})
        response = self.client.get(self.url, {
            "q": "공원", "source": "all", "lat": 35.15, "lng": 129.06,
            "radius": 3000, "limit": 30, "detail_level": "summary",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 30)
        kakao.assert_not_called()
