import json
from pathlib import Path

from django.test import SimpleTestCase


CASE_FILE = Path(__file__).with_name("evaluation_cases") / "conversation_golden_30.json"
ALLOWED_ACTIONS = {
    "search",
    "ask_clarification",
    "refine_previous_search",
    "compare_previous_results",
    "select_previous_result",
    "reset_conversation",
    "out_of_scope",
    "blocked",
}


class ConversationGoldenCaseContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.payload = json.loads(CASE_FILE.read_text(encoding="utf-8"))
        cls.cases = cls.payload["cases"]

    def test_contains_exactly_thirty_unique_conversations(self):
        self.assertEqual(len(self.cases), 30)
        ids = [case["id"] for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_conversation_has_executable_steps_and_expected_actions(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                steps = case.get("steps") or [case]
                self.assertTrue(steps)
                for step in steps:
                    self.assertTrue(str(step.get("query") or "").strip())
                    self.assertIn(step.get("expected_action"), ALLOWED_ACTIONS)

    def test_suite_covers_multi_turn_state_and_safe_boundaries(self):
        multi_turn = [case for case in self.cases if len(case.get("steps") or []) >= 2]
        actions = {
            step["expected_action"]
            for case in self.cases
            for step in (case.get("steps") or [case])
        }
        expectation_keys = {
            key
            for case in self.cases
            for step in (case.get("steps") or [case])
            for key in step
        }

        self.assertGreaterEqual(len(multi_turn), 20)
        self.assertTrue({"ask_clarification", "out_of_scope", "blocked"}.issubset(actions))
        self.assertTrue({
            "expected_conditions_all",
            "expected_exclusions_all",
            "expected_sort_hint",
            "expected_location_terms",
        }.issubset(expectation_keys))
