from django.test import SimpleTestCase

from recommendations.management.commands.evaluate_ai_search import (
    _evaluation_metrics,
    _issues_for_case,
    _matches_expected_action,
    _matches_expected_conversation_scenario,
)


class SearchEvaluationMetricTests(SimpleTestCase):
    def test_feature_metrics_do_not_treat_five_unmatched_results_as_quality(self):
        rows = [{
            "action": "search",
            "frame": {"constraints": ["조용함", "콘센트있음"]},
            "top_results": [
                {
                    "result_tier": "best_available",
                    "matched_conditions": [],
                    "missing_conditions": ["조용함", "콘센트있음"],
                    "reason": "부족하거나 확인이 필요한 조건이 있습니다.",
                }
                for _ in range(5)
            ],
            "timing_ms": {"total_observed": 100},
        }]

        metrics = _evaluation_metrics(rows)

        self.assertEqual(metrics["top_five_coverage_rate"]["value"], 1.0)
        self.assertEqual(metrics["feature_query_hit_at_5_rate"]["value"], 0.0)
        self.assertEqual(metrics["verified_feature_result_rate_at_5"]["value"], 0.0)
        self.assertEqual(metrics["honest_no_hit_fallback_rate"]["value"], 1.0)

    def test_feature_metrics_count_verified_condition_hits(self):
        rows = [{
            "action": "search",
            "frame": {"constraints": ["조용함"]},
            "top_results": [
                {
                    "result_tier": "all_conditions_met",
                    "matched_conditions": ["조용함"],
                    "missing_conditions": [],
                    "reason": "조용함이 확인됐습니다.",
                },
                {
                    "result_tier": "best_available",
                    "matched_conditions": [],
                    "missing_conditions": ["조용함"],
                    "reason": "조용함 근거가 부족합니다.",
                },
            ],
            "timing_ms": {"total_observed": 100},
        }]

        metrics = _evaluation_metrics(rows)

        self.assertEqual(metrics["feature_query_hit_at_5_rate"]["value"], 1.0)
        self.assertEqual(metrics["verified_feature_result_rate_at_5"]["value"], 0.5)
        self.assertEqual(metrics["honest_no_hit_fallback_rate"]["value"], 0.0)

    def test_refinement_expectation_accepts_executed_search_action(self):
        self.assertTrue(_matches_expected_action("refine_previous_search", "search"))
        self.assertFalse(_matches_expected_action("compare_previous_results", "search"))

    def test_unified_ai_scenario_uses_frame_semantics_for_conversation_expectation(self):
        self.assertTrue(_matches_expected_conversation_scenario(
            "restaurant",
            "ai_place_search",
            {
                "candidate_category_codes": ["restaurant"],
                "target_objects": ["식당"],
            },
        ))
        self.assertTrue(_matches_expected_conversation_scenario(
            "work_cafe",
            "ai_place_search",
            {
                "target_objects": ["카페"],
                "constraints": ["노트북 작업"],
            },
        ))
        self.assertTrue(_matches_expected_conversation_scenario(
            "work_cafe",
            "ai_place_search",
            {
                "situation": "work",
                "candidate_category_codes": ["cafe"],
                "target_objects": ["카페"],
            },
        ))
        self.assertFalse(_matches_expected_conversation_scenario(
            "walk_healing",
            "ai_place_search",
            {"situation": "work"},
        ))

    def test_conversation_expectations_report_missing_preserved_state(self):
        issues = _issues_for_case(
            {
                "query": "주차되는 곳만",
                "expected_action": "refine_previous_search",
                "expected_scenario": "restaurant",
                "expected_location_terms": ["서면"],
                "expected_conditions_all": ["주차", "조용"],
                "expected_exclusions_all": ["카페"],
                "expected_target_terms": ["식당"],
                "expected_sort_hint": "distance",
                "allow_empty": True,
            },
            {
                "decision_action": "refine_previous_search",
                "conditions": ["주차"],
                "search_plan": {
                    "scenario": "restaurant",
                    "locationQuery": "서면",
                    "targetQuery": "식당",
                    "requestedConditions": ["주차"],
                    "sort_hint": "",
                },
            },
            {
                "anchor_location": "서면",
                "target_objects": ["식당"],
                "constraints": ["주차"],
                "exclusions": [],
            },
            [],
        )

        self.assertIn("대화 조건 문맥 누락: 조용", issues)
        self.assertIn("대화 제외 문맥 누락: 카페", issues)
        self.assertIn("기대 sort_hint=distance, 실제 sort_hint=-", issues)

    def test_conversation_expectations_accept_preserved_state(self):
        issues = _issues_for_case(
            {
                "query": "좀 더 가까운 곳",
                "expected_action": "refine_previous_search",
                "expected_scenario": "restaurant",
                "expected_location_terms": ["서면"],
                "expected_conditions_all": ["주차", "조용"],
                "expected_exclusions_all": ["카페"],
                "expected_target_terms": ["식당"],
                "expected_sort_hint": "distance",
                "allow_empty": True,
            },
            {
                "decision_action": "refine_previous_search",
                "conditions": ["주차", "조용"],
                "avoid": ["카페"],
                "search_plan": {
                    "scenario": "restaurant",
                    "locationQuery": "서면",
                    "targetQuery": "식당",
                    "requestedConditions": ["주차", "조용"],
                    "exclude_terms": ["카페"],
                    "sort_hint": "distance",
                },
            },
            {
                "anchor_location": "서면",
                "target_objects": ["식당"],
                "constraints": ["주차", "조용"],
                "exclusions": ["카페"],
            },
            [],
        )

        self.assertEqual(issues, [])

    def test_reports_rank_metrics_only_with_explicit_relevance_labels(self):
        rows = [{
            "action": "search",
            "expected_action": "search",
            "expected_anchor_location": "부산역",
            "frame": {"anchor_location": "부산역"},
            "relevance_labels": {"p1": 3, "p2": 1},
            "top_results": [
                {"id": "p2", "unmet_constraints": []},
                {"id": "p1", "unmet_constraints": []},
            ],
            "timing_ms": {"total_observed": 120},
        }]

        metrics = _evaluation_metrics(rows)

        self.assertEqual(metrics["intent_accuracy"]["value"], 1.0)
        self.assertEqual(metrics["region_accuracy"]["value"], 1.0)
        self.assertEqual(metrics["recall_at_k"]["value"], 1.0)
        self.assertEqual(metrics["mrr"]["value"], 1.0)
        self.assertNotEqual(metrics["ndcg_at_k"], "NOT_MEASURED")

    def test_marks_ground_truth_dependent_metrics_not_measured(self):
        metrics = _evaluation_metrics([{
            "action": "search",
            "frame": {},
            "relevance_labels": {},
            "top_results": [],
            "timing_ms": {"total_observed": 50},
        }])

        self.assertEqual(metrics["candidate_recall"], "NOT_MEASURED")
        self.assertEqual(metrics["recall_at_k"], "NOT_MEASURED")
        self.assertEqual(metrics["mrr"], "NOT_MEASURED")
        self.assertEqual(metrics["ndcg_at_k"], "NOT_MEASURED")
        self.assertEqual(metrics["unsupported_reason_rate"], "NOT_MEASURED")
