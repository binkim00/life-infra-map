from django.test import SimpleTestCase

from recommendations.services.adaptive_budget import (
    allocate_by_request_budget,
    yield_adjusted_weights,
)


class AdaptiveBudgetTests(SimpleTestCase):
    def test_yield_adjustment_waits_for_minimum_sample(self):
        base = {"a": 50, "b": 50}
        unchanged = yield_adjusted_weights(base, {"a": {"calls": 199, "evidence": 199}})
        self.assertEqual(unchanged, base)
        adjusted = yield_adjusted_weights(base, {
            "a": {"calls": 200, "evidence": 100},
            "b": {"calls": 200, "evidence": 20},
        })
        self.assertGreater(adjusted["a"], adjusted["b"])

    def test_yield_adjustment_prefers_active_evidence_when_recorded(self):
        adjusted = yield_adjusted_weights({"fresh": 50, "stale": 50}, {
            "fresh": {"calls": 200, "evidence": 40, "active_evidence": 30},
            "stale": {"calls": 200, "evidence": 200, "active_evidence": 2},
        })
        self.assertGreater(adjusted["fresh"], adjusted["stale"])

    def test_allocation_respects_total_request_budget_and_spills_unused_share(self):
        rows = [
            (object(), {"budget_bucket": "a", "calls": 2}),
            (object(), {"budget_bucket": "a", "calls": 2}),
            (object(), {"budget_bucket": "b", "calls": 1}),
        ]
        selected, used = allocate_by_request_budget(
            rows, budget=4, weights={"a": 50, "b": 50},
            request_count=lambda context: context["calls"],
        )
        self.assertLessEqual(sum(used.values()), 4)
        self.assertEqual(len(selected), 2)
