from django.test import SimpleTestCase

from recommendations.services.ai_search_orchestrator import _grounded_semantic_reason


class SemanticReasonGroundingTests(SimpleTestCase):
    def test_stale_or_unsupported_document_feature_is_not_claimed(self):
        reason = _grounded_semantic_reason({
            "category": "cafe",
            "retrieval_semantic_features": ["조용함"],
            "hard_gate_active_tags": [],
        })
        self.assertNotIn("조용", reason)
        self.assertIn("카페", reason)

    def test_only_current_document_feature_is_claimed(self):
        reason = _grounded_semantic_reason({
            "category": "cafe",
            "retrieval_semantic_features": ["조용함", "분위기좋음"],
            "hard_gate_active_tags": ["조용함"],
        })
        self.assertIn("조용함", reason)
        self.assertNotIn("분위기좋음", reason)
