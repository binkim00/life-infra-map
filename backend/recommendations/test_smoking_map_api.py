from django.test import TestCase, override_settings

from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.conversational_search_planner import build_conversational_search_plan
from recommendations.services.map_search import get_matching_categories


class SmokingMapApiTests(TestCase):
    url = "/api/recommendations/places/"

    def make_place(self, name, lat, lng, *, external_id, raw=None, source="test"):
        return Place.objects.create(
            name=name, category="smoking_area", address="부산", lat=lat, lng=lng,
            source=source, external_id=external_id, raw=raw or {}, data_quality_score=70,
        )

    def test_category_and_bounds_filter_return_smoking_metadata(self):
        inside = self.make_place("연산 흡연실", 35.18, 129.08, external_id="inside", raw={"흡연실여부": "Y"}, source="부산광역시 연제구_흡연실 현황_20250905")
        self.make_place("범위 밖", 35.30, 129.20, external_id="outside")
        response = self.client.get(self.url, {"category": "smoking_area", "min_lat": 35.17, "min_lng": 129.07, "max_lat": 35.19, "max_lng": 129.09})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [inside.id])
        self.assertEqual(response.data["results"][0]["smoking"]["facility_type"], "smoking_room")
        self.assertEqual(response.data["results"][0]["smoking"]["verification_level"], "PUBLIC_DATA")

    def test_radius_and_read_time_dedup(self):
        self.make_place("같은 흡연실", 35.18, 129.08, external_id="one", raw={"흡연실여부": "Y"})
        self.make_place("같은 흡연실", 35.18001, 129.08001, external_id="two", raw={"흡연실여부": "Y"}, source="test2")
        response = self.client.get(self.url, {"category": "smoking_area", "lat": 35.18, "lng": 129.08, "radius": 500})
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["duplicate_count"], 2)

    def test_ashtray_is_unknown_and_filterable(self):
        place = self.make_place("재떨이 후보", 35.18, 129.08, external_id="ashtray")
        tag = Tag.objects.create(name="재떨이위치", tag_type="warning")
        PlaceTag.objects.create(place=place, tag=tag, source="checked", status="confirmed", confidence=90)
        response = self.client.get(self.url, {"category": "smoking_area", "facility_type": "ashtray_only"})
        metadata = response.data["results"][0]["smoking"]
        self.assertEqual(metadata["smoking_permission"], "unknown")
        self.assertEqual(metadata["verification_level"], "ASHTRAY_ONLY")

    def test_stale_hidden_by_default_and_official_filter_excludes_unverified(self):
        stale = self.make_place("오래된 부스", 35.18, 129.08, external_id="stale")
        official = self.make_place("공식 부스", 35.181, 129.081, external_id="official")
        tag = Tag.objects.create(name="흡연부스", tag_type="recommendation")
        for place, status in ((stale, "STALE"), (official, "VERIFIED_OFFICIAL")):
            PlaceTag.objects.create(place=place, tag=tag, source="checked", status="confirmed", confidence=90)
            PlaceTagEvidence.objects.create(place=place, tag=tag, source="official", confidence=90, context={"verification_status": status})
        default = self.client.get(self.url, {"category": "smoking_area"})
        self.assertEqual([row["name"] for row in default.data["results"]], ["공식 부스"])
        official_only = self.client.get(self.url, {"category": "smoking_area", "verification": "VERIFIED_OFFICIAL"})
        self.assertEqual([row["name"] for row in official_only.data["results"]], ["공식 부스"])
        with_stale = self.client.get(self.url, {"category": "smoking_area", "include_stale": "true"})
        self.assertEqual(len(with_stale.data["results"]), 2)

    @override_settings(AI_INTENT_PLANNER_ENABLED=False)
    def test_smoking_natural_language_aliases(self):
        queries = ["부산역 흡연구역", "서면 담배 피울 곳", "근처 흡연실", "해운대 흡연부스", "부산역 재떨이"]
        for query in queries:
            self.assertIn("smoking_area", get_matching_categories(query), query)
            plan = build_conversational_search_plan(query)
            self.assertEqual(plan.get("search_plan", {}).get("scenario"), "smoking_area", query)
        self.assertEqual(build_conversational_search_plan("해운대 흡연부스")["search_plan"]["smoking_filters"]["facility_type"], "smoking_booth")
        self.assertEqual(build_conversational_search_plan("부산역 재떨이")["search_plan"]["smoking_filters"]["facility_type"], "ashtray_only")
        self.assertEqual(build_conversational_search_plan("부산역 공식 흡연구역")["search_plan"]["smoking_filters"]["verification"], "VERIFIED_OFFICIAL")
