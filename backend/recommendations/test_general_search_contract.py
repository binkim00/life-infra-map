"""General map search contracts: no query-specific production exceptions."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from recommendations.services.area_gazetteer import resolve_area_coordinates
from recommendations.services.area_gazetteer import resolve_area_coordinates_by_token
from recommendations.services.map_search import (
    build_kakao_keyword_variants,
    kakao_place_matches_keyword,
    split_branch_qualified_query,
    split_location_category_query,
)
from recommendations.services.conversation_sessions import result_references
from recommendations.services.ai_search_orchestrator import _resolve_anchor_location
from recommendations.services.ai_search_orchestrator import collect_kakao_candidates


class GeneralSearchContractTests(TestCase):
    url = "/api/recommendations/place-search/"

    def setUp(self):
        cache.clear()

    def test_db_nearby_order_is_applied_before_result_limit(self):
        from recommendations.models import Place
        from recommendations.services.map_search import search_saved_places
        Place.objects.create(name="테스트브랜드", external_id="far-limit", category="cafe", lat=35.13, lng=129.1)
        nearby = Place.objects.create(name="테스트브랜드 부산점", external_id="near-limit", category="cafe", lat=35.101, lng=129.1)
        results, _, _ = search_saved_places(keyword="테스트브랜드", lat=35.1, lng=129.1, radius=5000, limit=1, nearest_first=True)
        self.assertEqual(results[0]["id"], nearby.id)

    @patch("recommendations.views.search_places_by_keyword", return_value={"documents": []})
    @patch("recommendations.views.search_saved_map_places", return_value=([], 0, {}))
    @patch("recommendations.views._resolve_anchor_location")
    @patch("recommendations.views.get_naver_search_result", return_value={"candidates": []})
    def test_explicit_region_centers_both_providers_before_search(self, naver, resolve, db, kakao):
        resolve.return_value = {"status": "resolved", "lat": 35.16, "lng": 129.06, "label": "부산"}
        self.client.get(self.url, {"q": "부산 스타벅스", "lat": 37.5, "lng": 127.1})
        self.assertEqual(db.call_args.kwargs["lat"], 35.16)
        self.assertEqual(kakao.call_args_list[0].kwargs["lat"], 35.16)
        resolve.reset_mock()
        self.client.get(self.url, {"q": "부산 스타벅스", "lat": 35.2, "lng": 129.1, "center_mode": "map", "radius": 3000})
        self.assertEqual(db.call_args.kwargs["lat"], 35.2)
        self.assertEqual(kakao.call_args_list[-1].kwargs["lat"], None)
        resolve.assert_not_called()

    @patch("recommendations.views.get_naver_search_result", return_value={"candidates": []})
    @patch("recommendations.views.search_places_by_keyword")
    def test_nearby_kakao_branch_precedes_distant_exact_db_name(self, kakao, naver):
        from recommendations.models import Place
        Place.objects.create(name="테스트커피랩", external_id="far-exact", category="cafe", address="서울", lat=37.5, lng=127.1)
        kakao.return_value = {"documents": [{"id": "near-branch", "place_name": "테스트커피랩 부산점", "category_name": "카페", "x": "129.101", "y": "35.101", "address_name": "부산"}]}
        data = self.client.get(self.url, {"q": "테스트커피랩", "source": "all", "lat": 35.1, "lng": 129.1}).json()
        self.assertEqual([p["name"] for p in data["results"]], ["테스트커피랩 부산점", "테스트커피랩"])
        self.assertLess(data["results"][0]["distance"], data["results"][1]["distance"])

    @patch("recommendations.views.get_naver_search_result", return_value={"candidates": []})
    @patch("recommendations.views.search_places_by_keyword", return_value={"documents": []})
    def test_named_db_place_is_merged_without_category_broadening(self, kakao, naver):
        from recommendations.models import Place
        Place.objects.create(name="희망공원", external_id="qa1", category="city_park", address="부산", lat=35.1, lng=129.1)
        Place.objects.create(name="다른공원", external_id="qa2", category="city_park", address="부산", lat=35.1, lng=129.1)
        data = self.client.get(self.url, {"q": "희망공원", "source": "all", "lat": 35.1, "lng": 129.1}).json()
        self.assertEqual([p["name"] for p in data["results"]], ["희망공원"])
        self.assertFalse(data["db_search_skipped"])

    @patch("recommendations.views.get_naver_search_result")
    @patch("recommendations.views.search_places_by_keyword")
    def test_map_filters_far_kakao_but_keeps_local_naver_coordinates(self, kakao, naver):
        kakao.return_value = {"documents": [{"id": "far", "place_name": "테스트커피", "category_name": "카페", "x": "127.1", "y": "37.5"}]}
        naver.return_value = {"candidates": [{"name": "테스트커피 부산점", "source_url": "https://example.com/place", "lat": 35.1, "lng": 129.1, "coordinate_source": "naver_local_wgs84"}]}
        data = self.client.get(self.url, {"q": "테스트커피", "source": "all", "lat": 35.1, "lng": 129.1, "radius": 3000, "center_mode": "map"}).json()
        self.assertEqual([p["name"] for p in data["results"]], ["테스트커피 부산점"])
        self.assertEqual(data["results"][0]["distance"], 0)
        self.assertTrue(data["results"][0]["can_show_on_map"])
        naver.assert_called_once()

    def test_naver_coordinates_do_not_verify_conditions(self):
        from recommendations.services.naver_search_provider import _candidate_from_item
        candidate = _candidate_from_item({"title": "테스트커피", "mapx": "1291000000", "mapy": "351000000"}, "local", "테스트커피", [])
        self.assertEqual((candidate["lat"], candidate["lng"]), (35.1, 129.1))
        self.assertFalse(candidate["is_verified"])
        old = _candidate_from_item({"title": "테스트커피", "mapx": "311277", "mapy": "552097"}, "local", "테스트커피", [])
        self.assertNotIn("lat", old)

    @patch("recommendations.views.get_naver_search_result", return_value={"candidates": []})
    @patch("recommendations.views.search_places_by_keyword", return_value={"documents": []})
    def test_compact_named_db_search_can_find_a_distant_place(self, kakao, naver):
        from recommendations.models import Place
        Place.objects.create(name="테스트 커피랩", external_id="qa-remote", category="cafe", address="서울", lat=37.5, lng=127.1)
        data = self.client.get(self.url, {"q": "테스트커피랩", "source": "all", "lat": 35.1, "lng": 129.1}).json()
        self.assertEqual([p["name"] for p in data["results"]], ["테스트 커피랩"])
        self.assertGreater(data["results"][0]["distance"], 100000)

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

    def test_branch_suffix_variant_accepts_longer_provider_branch_name(self):
        place = {
            "place_name": "테스트브랜드 경성대부경대점",
            "address_name": "부산 남구 대연동",
            "category_name": "카페",
        }
        self.assertEqual(
            build_kakao_keyword_variants("테스트브랜드 경성대점"),
            ["테스트브랜드 경성대"],
        )
        self.assertTrue(kakao_place_matches_keyword(place, "테스트브랜드 경성대점"))
        self.assertEqual(
            split_branch_qualified_query("테스트브랜드 경성대점"),
            {"name_query": "테스트브랜드", "branch_location": "경성대"},
        )

    @patch("recommendations.views.search_places_by_keyword")
    def test_empty_exact_branch_query_retries_a_limited_suffix_variant(self, search):
        search.side_effect = [
            {"documents": []},
            {"documents": []},
            {"documents": [{
                "id": "branch",
                "place_name": "테스트브랜드 경성대부경대점",
                "category_name": "음식점 > 카페",
                "category_group_code": "CE7",
                "address_name": "부산 남구 대연동",
                "x": "129.10",
                "y": "35.14",
            }]},
        ]
        response = self.client.get(self.url, {
            "q": "테스트브랜드 경성대점",
            "lat": 35.09,
            "lng": 128.85,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["name"], "테스트브랜드 경성대부경대점")
        self.assertEqual(search.call_args_list[-1].kwargs["keyword"], "테스트브랜드 경성대")

    @patch("recommendations.views._resolve_anchor_location")
    @patch("recommendations.views.search_places_by_keyword")
    def test_branch_query_searches_the_brand_around_the_branch_location(self, search, resolve):
        resolve.return_value = {"status": "resolved", "lat": 35.14, "lng": 129.10}
        search.side_effect = [
            {"documents": []},
            {"documents": []},
            {"documents": []},
            {"documents": [{
                "id": "branch-nearby",
                "place_name": "테스트브랜드 경성대부경대점",
                "category_name": "음식점 > 카페",
                "category_group_code": "CE7",
                "address_name": "부산 남구 대연동",
                "x": "129.10",
                "y": "35.14",
            }]},
        ]
        response = self.client.get(self.url, {
            "q": "테스트브랜드 경성대점",
            "lat": 35.09,
            "lng": 128.85,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["name"], "테스트브랜드 경성대부경대점")
        resolve.assert_called_once_with("경성대", address_first=False)
        self.assertEqual(search.call_args_list[0].kwargs["lat"], 35.14)
        self.assertEqual(response.json()["location_context"]["lat"], 35.14)
        self.assertEqual(search.call_args_list[-1].kwargs["keyword"], "테스트브랜드")
        self.assertEqual(search.call_args_list[-1].kwargs["lat"], 35.14)

    @override_settings(
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
    )
    @patch("recommendations.views.get_naver_search_result")
    @patch("recommendations.views._resolve_anchor_location")
    @patch("recommendations.views.search_places_by_keyword")
    def test_zero_db_and_kakao_results_return_a_labeled_naver_candidate(
        self, search, resolve, naver,
    ):
        search.return_value = {"documents": []}
        resolve.return_value = {"status": "unresolved"}
        naver.return_value = {
            "candidates": [{
                "name": "테스트브랜드 경성대점",
                "source_url": "https://example.com/place",
                "evidence_summary": "부산 남구의 카페 검색 결과",
                "address_hint": "부산 남구 테스트로 1",
                "category_hint": "카페",
            }],
        }
        response = self.client.get(self.url, {
            "q": "테스트브랜드 경성대점",
            "lat": 35.09,
            "lng": 128.85,
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["candidate_counts"]["web"], 1)
        self.assertEqual(data["results"][0]["name"], "테스트브랜드 경성대점")
        self.assertEqual(data["results"][0]["source_label"], "네이버 검색 후보")
        self.assertFalse(data["results"][0]["can_show_on_map"])

        repeated = self.client.get(self.url, {
            "q": "테스트브랜드 경성대점",
            "lat": 35.09,
            "lng": 128.85,
        })
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["candidate_counts"]["web"], 1)
        naver.assert_called_once()

    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword")
    def test_situation_search_retries_the_same_branch_suffix_variant(self, search):
        search.side_effect = [
            {"documents": []},
            {"documents": [{
                "id": "situation-branch",
                "place_name": "테스트브랜드 경성대부경대점",
                "category_name": "음식점 > 카페",
                "category_group_code": "CE7",
                "address_name": "부산 남구 대연동",
                "x": "129.10",
                "y": "35.14",
            }]},
        ]
        candidates, counts = collect_kakao_candidates(
            {
                "target_objects": ["카페"],
                "candidate_place_types": ["카페"],
                "result_match_terms": ["테스트브랜드"],
                "constraints": [],
                "structured_conditions": [],
            },
            ["테스트브랜드 경성대점"],
            lat=35.09,
            lng=128.85,
            radius=5000,
        )
        self.assertEqual([candidate["name"] for candidate in candidates], ["테스트브랜드 경성대부경대점"])
        self.assertEqual(counts[0]["count"], 1)
        self.assertEqual(search.call_args_list[-1].kwargs["keyword"], "테스트브랜드 경성대")

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
