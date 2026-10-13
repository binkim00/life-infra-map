from django.test import SimpleTestCase
from django.test import TestCase, override_settings
from unittest.mock import patch

from recommendations.services.ai_search_orchestrator import apply_selected_filters, run_ai_search


class SelectedFilterTests(SimpleTestCase):
    def test_selected_values_override_parser_category_and_location(self):
        frame = {"anchor_location": "", "candidate_category_codes": ["cafe"],
                 "constraints": ["가족과 함께"]}
        result = apply_selected_filters(frame, {
            "location": "부산 해운대", "category": "restaurant",
            "required": ["parking", "high_chair", "parking"],
        })
        self.assertEqual(result["anchor_location"], "부산 해운대")
        self.assertEqual(result["candidate_category_codes"], ["restaurant"])
        self.assertEqual(result["required_features"], ["주차가능", "유아의자있음"])
        self.assertFalse(result["fallback_enabled"])
        self.assertEqual([item["source"] for item in result["structured_conditions"]],
                         ["selected_filter", "selected_filter"])

    def test_unknown_or_incomplete_choice_is_ignored(self):
        frame = {"candidate_category_codes": ["cafe"]}
        for selected in (
            {"location": "부산", "category": "unknown", "required": []},
            {"location": "", "category": "cafe", "required": []},
            {"location": "부산", "category": "cafe", "required": ["arbitrary"]},
        ):
            self.assertIs(apply_selected_filters(frame, selected), frame)


class SelectedFilterSearchTests(TestCase):
    @override_settings(AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False)
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], []))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    def test_search_plan_uses_explicit_category_location_and_hard_condition(self, db, kakao):
        result = run_ai_search({
            "query": "부산에서 공원 추천해줘", "lat": 35.1, "lng": 129.1,
            "selected_filters": {
                "location": "부산", "category": "city_park", "required": ["pet"],
            },
        })
        frame = result["search_plan"]["place_intent_frame"]
        self.assertEqual(result["decision_action"], "search")
        self.assertEqual(frame["anchor_location"], "부산")
        self.assertEqual(frame["candidate_category_codes"], ["city_park"])
        self.assertEqual(frame["required_features"], ["반려동물동반"])
