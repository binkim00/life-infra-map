from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from recommendations.models import Place


class PlaceKakaoDetailLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.place = Place.objects.create(
            name="라이다운 커피 로스터스",
            category="cafe",
            address="부산 부산진구 서전로 12",
            lat=35.1579,
            lng=129.0592,
            source="public_data",
            external_id="source-123",
        )
        self.url = f"/api/recommendations/places/{self.place.id}/kakao-detail/"

    @patch("recommendations.views.search_places_by_keyword")
    def test_resolves_only_nearby_matching_name(self, search):
        search.return_value = {"documents": [
            {"id": "12345678", "place_name": self.place.name,
             "road_address_name": self.place.address, "y": "35.1579", "x": "129.0592"},
            {"id": "87654321", "place_name": "다른 카페",
             "road_address_name": self.place.address, "y": "35.1579", "x": "129.0592"},
        ]}
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "url": "https://place.map.kakao.com/12345678", "status": "matched",
        })
        self.client.get(self.url)
        search.assert_called_once()

    @patch("recommendations.views.search_places_by_keyword")
    def test_rejects_multiple_nearby_places_with_same_name(self, search):
        search.return_value = {"documents": [
            {"id": "12345678", "place_name": self.place.name,
             "road_address_name": self.place.address, "y": "35.1579", "x": "129.0592"},
            {"id": "87654321", "place_name": self.place.name,
             "road_address_name": self.place.address, "y": "35.1580", "x": "129.0593"},
        ]}
        response = self.client.get(self.url)
        self.assertEqual(response.json(), {"url": "", "status": "unmatched"})

    @patch("recommendations.views.search_places_by_keyword")
    def test_rejects_distant_place_with_same_name(self, search):
        search.return_value = {"documents": [
            {"id": "12345678", "place_name": self.place.name,
             "road_address_name": "부산 다른구 다른로 1", "y": "35.1700", "x": "129.0700"},
        ]}
        response = self.client.get(self.url)
        self.assertEqual(response.json(), {"url": "", "status": "unmatched"})

    @patch("recommendations.views.search_places_by_keyword")
    def test_existing_link_needs_no_provider_call(self, search):
        self.place.raw = {"place_url": "https://place.map.kakao.com/99999999"}
        self.place.save(update_fields=["raw"])
        response = self.client.get(self.url)
        self.assertEqual(response.json(), {
            "url": "https://place.map.kakao.com/99999999", "status": "stored",
        })
        search.assert_not_called()
