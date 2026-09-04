import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.conversational_search_planner import build_conversational_search_plan
from recommendations.services.map_search import get_matching_categories
from recommendations.management.commands.discover_busan_smoking_places import CANDIDATES


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
        self.assertEqual(response.data["results"][0]["smoking"]["facility_type_label"], "흡연실")
        self.assertEqual(response.data["results"][0]["smoking"]["verification_level"], "PUBLIC_DATA")
        self.assertEqual(response.data["results"][0]["smoking"]["verification_level_label"], "공공데이터 확인")

    @patch("recommendations.views.search_places_by_keyword", return_value={"documents": []})
    @patch("recommendations.views._resolve_anchor_location")
    def test_general_place_search_combines_location_with_smoking_db_category(
        self,
        mock_resolve_anchor,
        _mock_kakao,
    ):
        place = self.make_place(
            "괘법동 지정 흡연구역",
            35.1622,
            128.9846,
            external_id="sasang-smoking-area",
            raw={"location_description": "사상역 4번 출구 밖"},
        )
        mock_resolve_anchor.return_value = {
            "status": "resolved",
            "source": "kakao_keyword",
            "label": "사상역",
            "lat": 35.1622,
            "lng": 128.9846,
        }

        response = self.client.get(
            "/api/recommendations/place-search/",
            {"q": "사상역 흡연구역", "source": "all", "limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["db_search_skipped"])
        self.assertEqual(response.data["query_info"]["include_tokens"], ["흡연구역"])
        result = next(row for row in response.data["results"] if row["id"] == place.id)
        self.assertEqual(result["result_source"], "db")
        self.assertEqual(result["smoking"]["location_description"], "사상역 4번 출구 밖")

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


class BusanSmokingCandidateImportTests(TestCase):
    def _input_files(self, directory):
        candidates = [row for row in CANDIDATES if row["status"] not in {"EXISTING", "REJECTED"}]
        discovery = Path(directory) / "discovery.json"
        reverification = Path(directory) / "reverification.json"
        discovery.write_text(json.dumps({"candidates": candidates}, ensure_ascii=False), encoding="utf-8")
        reverification.write_text(json.dumps({"rows": [{"name": row["candidate_name"], "previous_status": row["status"], "new_status": row["status"], "reason": "test"} for row in candidates]}, ensure_ascii=False), encoding="utf-8")
        return discovery, reverification

    def test_apply_is_idempotent_and_preserves_evidence_and_location(self):
        with tempfile.TemporaryDirectory() as directory:
            discovery, reverification = self._input_files(directory)
            kwargs = {"apply": True, "discovery": str(discovery), "reverification": str(reverification), "output_dir": directory}
            call_command("import_busan_smoking_candidates", **kwargs)
            call_command("import_busan_smoking_candidates", **kwargs)
            imported = Place.objects.filter(raw__import_batch="busan_smoking_candidates_2026_08")
            self.assertEqual(imported.count(), 19)
            self.assertEqual(PlaceTag.objects.filter(place__in=imported).count(), 19)
            self.assertEqual(PlaceTagEvidence.objects.filter(place__in=imported).count(), 19)
            self.assertTrue(all(34.8 <= p.lat <= 35.4 and 128.7 <= p.lng <= 129.35 for p in imported))
            busan_station = imported.get(name="부산역 5번 출구 외부 흡연구역")
            self.assertEqual(busan_station.raw["coordinate_accuracy"], "ENTRANCE")
            self.assertIn("5번 출구", busan_station.detail_location)

    def test_imported_visibility_and_ashtray_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            discovery, reverification = self._input_files(directory)
            call_command("import_busan_smoking_candidates", apply=True, discovery=str(discovery), reverification=str(reverification), output_dir=directory)
        default = self.client.get("/api/recommendations/places/", {"category": "smoking_area", "min_lat": 34.8, "min_lng": 128.7, "max_lat": 35.4, "max_lng": 129.35, "limit": 100})
        self.assertEqual(default.data["count"], 17)
        with_stale = self.client.get("/api/recommendations/places/", {"category": "smoking_area", "min_lat": 34.8, "min_lng": 128.7, "max_lat": 35.4, "max_lng": 129.35, "include_stale": "true", "limit": 100})
        self.assertEqual(with_stale.data["count"], 19)
        ashtrays = [row for row in default.data["results"] if row["smoking"]["facility_type"] == "ashtray_only"]
        self.assertEqual(len(ashtrays), 4)
        self.assertTrue(all(row["smoking"]["smoking_permission"] == "unknown" for row in ashtrays))
        self.assertTrue(all(row["smoking"]["location_description"] for row in default.data["results"]))
        centum = self.client.get("/api/recommendations/places/", {"category": "smoking_area", "q": "센텀"})
        self.assertEqual([row["name"] for row in centum.data["results"]], ["센텀시티역 6번 출구 흡연구역"])
        sasang_ashtray = self.client.get("/api/recommendations/places/", {"category": "smoking_area", "q": "사상", "facility_type": "ashtray_only"})
        self.assertEqual([row["name"] for row in sasang_ashtray.data["results"]], ["어반풋볼파크 부산사상점 B구장 뒤 재떨이"])
