from django.test import SimpleTestCase

from recommendations.management.commands.evaluate_ai_search import _evaluation_metrics


class SearchEvaluationMetricTests(SimpleTestCase):
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
