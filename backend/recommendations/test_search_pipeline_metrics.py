from unittest import TestCase

from recommendations.services.search_pipeline_metrics import build_search_metrics


class SearchPipelineMetricsTests(TestCase):
    def test_metrics_exclude_query_place_and_evidence_text(self):
        metrics = build_search_metrics({
            "decision_action": "search", "query": "private search",
            "results": [{"name": "private place", "hard_gate_passed": True,
                         "result_tier": "all_conditions_met", "evidence": "private quote"}],
            "timings": {"total_latency_ms": 123.456},
            "debug_pipeline": {
                "candidate_counts": {"db": 2, "identity_attempts": 1, "identity_matches": 1},
                "reranker": {"common_hard_gate": {"removed_by_type": {"feature": 4}}},
            },
        })
        self.assertEqual(metrics["counts"]["db"], 2)
        self.assertEqual(metrics["gate_rejections"]["feature"], 4)
        self.assertEqual(metrics["verified_top_five"], 1)
        self.assertNotIn("private", str(metrics))
