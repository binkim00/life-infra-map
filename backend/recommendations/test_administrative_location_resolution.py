from unittest.mock import patch

from django.test import SimpleTestCase

from recommendations.services.ai_search_orchestrator import _resolve_anchor_location
from recommendations.services.ai_candidate_reranker import semantic_rerank_candidates
from recommendations.services.ai_intent_planner import _canonicalize, _local_rule_anchor_location


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
        for label in ("서면", "부산역", "하단역", "센텀시티역", "명지"):
            with self.subTest(label=label):
                result = _resolve_anchor_location(label, lat=37.5, lng=127.0)
                self.assertEqual(result["status"], "resolved")
                self.assertEqual(result["source"], "area_gazetteer")

        centum = _resolve_anchor_location("센텀시티역", lat=37.5, lng=127.0)
        self.assertAlmostEqual(centum["lat"], 35.169000, places=6)
        self.assertAlmostEqual(centum["lng"], 129.130200, places=6)

    def test_explicit_area_survives_descriptive_words_between_area_and_category(self):
        self.assertEqual(_local_rule_anchor_location("명지 분위기 좋은 카페"), "명지")
        self.assertEqual(
            _local_rule_anchor_location("아이랑 망원동 분위기 좋은 카페"),
            "망원동",
        )

        plan, errors = _canonicalize(
            {
                "action": "search",
                "normalized_query": "카페",
                "frame": {
                    "location_mode": "current_context",
                    "anchor_location": "",
                    "target_objects": ["카페"],
                    "candidate_place_types": ["카페"],
                    "result_match_terms": ["카페"],
                    "constraints": ["분위기 좋음"],
                    "exclusions": [],
                    "ranking_policy": "evidence_first",
                    "primary_search_queries": ["카페"],
                    "secondary_search_queries": [],
                },
                "clarification": {},
                "confidence": 0.8,
            },
            raw_query="명지 분위기 좋은 카페",
            lat=35.096454,
            lng=128.853952,
        )

        self.assertEqual(errors, [])
        self.assertEqual(plan["frame"]["location_mode"], "explicit")
        self.assertEqual(plan["frame"]["anchor_location"], "명지")


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
