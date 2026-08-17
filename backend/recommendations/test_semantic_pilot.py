from django.test import SimpleTestCase, override_settings

from recommendations.services.ai_candidate_reranker import _hybrid_score
from recommendations.services.semantic_retrieval import attach_semantic_scores


class SemanticPilotRankingTests(SimpleTestCase):
    def test_vector_score_is_a_component_not_a_final_score(self):
        candidate = {"place_id": 1, "score": 80, "candidate_source": "db"}
        attach_semantic_scores([candidate], [{"place_id": 1, "semantic_score": 92}])
        final, breakdown = _hybrid_score(candidate, {"semantic_score": 5, "evidence_level": "medium"})
        self.assertEqual(breakdown["semantic_score"], 92)
        self.assertNotEqual(final, 92)

    @override_settings(AI_SEARCH_HYBRID_WEIGHTS={"semantic": 1.0})
    def test_hard_violation_penalty_beats_semantic_similarity(self):
        candidate = {
            "place_id": 1,
            "score": 80,
            "candidate_source": "db",
            "retrieval_semantic_score": 100,
            "pre_ai_unmet_constraints": ["무료이용"],
        }
        final, breakdown = _hybrid_score(candidate, {"semantic_score": 100, "evidence_level": "strong"})
        self.assertEqual(breakdown["penalty"], 100)
        self.assertEqual(final, 0)
