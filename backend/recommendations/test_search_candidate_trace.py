from unittest import TestCase

from recommendations.services.search_candidate_trace import build_candidate_trace
from recommendations.services.ai_search_orchestrator import _grounded_internal_fallback, should_collect_sparse_web


class SearchCandidateTraceTests(TestCase):
    def test_joined_candidates_keep_distinct_evidence_and_tag_states_without_source_text(self):
        db = {"id": "db:17", "candidate_source": "db", "place_id": 17,
              "name": "private place", "verified_tags": []}
        kakao = {"id": "kakao:8", "candidate_source": "kakao", "name": "private place"}
        joined = {**db, "duplicate_candidate_ids": ["kakao:8"],
                  "hard_gate_active_tags": ["조용함"]}
        result = {**joined, "backend_rank": 1}
        trace = build_candidate_trace(
            db=[db], kakao=[kakao], web=[], gate_kept=[joined],
            gate_removed=[], ranked=[joined], results=[result],
        )
        self.assertEqual(trace["counts"]["db"], 1)
        self.assertEqual(trace["counts"]["kakao"], 1)
        self.assertEqual(trace["counts"]["active_evidence_join"], 2)
        self.assertEqual(trace["counts"]["confirmed_place_tag"], 0)
        self.assertEqual(trace["counts"]["final"], 1)
        self.assertNotIn("private place", str(trace))
        self.assertNotIn("db:17", str(trace))

    def test_gate_rejection_records_only_reason_type(self):
        candidate = {"id": "web:secret", "candidate_source": "web",
                     "hard_gate_violations": [{"type": "feature", "actual": "secret address"}]}
        trace = build_candidate_trace(
            db=[], kakao=[], web=[candidate], gate_kept=[],
            gate_removed=[candidate], ranked=[], results=[],
        )
        self.assertEqual(trace["candidates"][0]["gate_reasons"], ["feature"])
        self.assertNotIn("secret", str(trace))

    def test_grounded_internal_fallback_requires_current_gate_evidence(self):
        candidate = {
            "place_id": 17, "hard_gate_passed": True,
            "hard_gate_active_tags": ["조용함"],
        }
        self.assertTrue(_grounded_internal_fallback(candidate))
        self.assertFalse(_grounded_internal_fallback({**candidate, "place_id": None}))
        self.assertFalse(_grounded_internal_fallback({**candidate, "hard_gate_passed": False}))
        self.assertFalse(_grounded_internal_fallback({**candidate, "hard_gate_active_tags": []}))

    def test_sparse_web_pilot_thresholds(self):
        self.assertTrue(should_collect_sparse_web(0))
        self.assertTrue(should_collect_sparse_web(1))
        self.assertFalse(should_collect_sparse_web(2))
        self.assertTrue(should_collect_sparse_web(2, expand_requested=True))
        self.assertFalse(should_collect_sparse_web(3, expand_requested=True))
