from unittest.mock import patch

from django.test import SimpleTestCase

from recommendations.services.ai_search_orchestrator import _resolve_anchor_location
from recommendations.services.ai_candidate_reranker import semantic_rerank_candidates


class AdministrativeLocationResolutionTests(SimpleTestCase):
    def test_administrative_names_use_db_derived_centers_without_kakao_poi_lookup(self):
        expected = {
            "서울": (37.549381, 126.987914),
            "서울특별시": (37.549381, 126.987914),
            "부산": (35.158163, 129.060231),
            "부산광역시": (35.158163, 129.060231),
            "강남구": (37.506051, 127.040758),
            "해운대구": (35.172704, 129.158029),
        }

        with patch(
            "recommendations.services.ai_search_orchestrator.search_places_by_keyword",
            side_effect=AssertionError("administrative areas must not use Kakao POI lookup"),
        ):
            for label, coordinates in expected.items():
                with self.subTest(label=label):
                    result = _resolve_anchor_location(label, lat=35.1, lng=129.1)
                    self.assertEqual(result["status"], "resolved")
                    self.assertEqual(result["source"], "area_gazetteer")
                    self.assertAlmostEqual(result["lat"], coordinates[0], places=6)
                    self.assertAlmostEqual(result["lng"], coordinates[1], places=6)

    def test_station_and_neighborhood_anchors_keep_their_specific_centers(self):
        for label in ("서면", "부산역", "하단역"):
            with self.subTest(label=label):
                result = _resolve_anchor_location(label, lat=37.5, lng=127.0)
                self.assertEqual(result["status"], "resolved")
                self.assertEqual(result["source"], "area_gazetteer")


class DisabledRerankerTests(SimpleTestCase):
    @patch("recommendations.services.ai_candidate_reranker._call_ai_chat_json")
    def test_disabled_reranker_does_not_attempt_an_ai_call(self, call_ai):
        with self.settings(
            CONVERSATIONAL_SEARCH_AI_ENABLED=True,
            AI_RERANK_ENABLED=False,
        ):
            ranked, debug = semantic_rerank_candidates(
                {"target_objects": ["카페"]},
                [{"id": "db:1", "name": "테스트 카페"}],
            )

        self.assertEqual(ranked, [])
        self.assertEqual(debug["reason"], "ai_reranker_disabled")
        call_ai.assert_not_called()
