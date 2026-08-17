from unittest.mock import patch
from datetime import timedelta

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from recommendations.services.ai_candidate_reranker import _hybrid_score
from recommendations.services.semantic_retrieval import attach_semantic_scores
from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.ai_search_orchestrator import collect_semantic_candidates


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


class SemanticCandidateInjectionTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="근거 카페", category="cafe", address="부산광역시 부산진구",
            lat=35.1579, lng=129.0592, source="test", external_id="semantic-injection",
        )
        tag = Tag.objects.create(name="조용함")
        PlaceTag.objects.create(
            place=self.place, tag=tag, source="web_evidence", status="candidate", confidence=70,
        )
        PlaceTagEvidence.objects.create(
            place=self.place, tag=tag, source="naver_blog_search", polarity="positive",
            confidence=70, evidence_key="semantic-injection", expires_at=timezone.now() + timedelta(days=30),
        )

    @override_settings(
        SEMANTIC_RETRIEVAL_ENABLED=True, SEMANTIC_CANDIDATE_INJECTION_ENABLED=True,
        SEMANTIC_TOP_K=10, SEMANTIC_CANDIDATE_LIMIT=5,
    )
    @patch("recommendations.services.ai_search_orchestrator.retrieve_semantic_places")
    def test_injection_uses_existing_place_and_factual_features(self, retrieve):
        retrieve.return_value = {
            "results": [{
                "place_id": self.place.id, "place": self.place, "features": ["조용함"],
                "document": "근거 카페 / cafe / 부산 / 조용함", "document_id": 1,
                "semantic_similarity": .9, "semantic_score": 90,
            }],
            "query_embedding_latency_ms": 1, "vector_search_latency_ms": 1, "backend": "test",
        }
        frame = {"target_objects": ["카페"], "candidate_place_types": ["카페"], "candidate_category_codes": ["cafe"]}
        rows, debug = collect_semantic_candidates(
            "조용히 쉬고 싶어", frame, lat=35.1579, lng=129.0592, radius=3000,
        )
        self.assertEqual([row["place_id"] for row in rows], [self.place.id])
        self.assertEqual(rows[0]["matched_tags"], ["조용함"])
        self.assertEqual(debug["injected_count"], 1)

    @override_settings(
        SEMANTIC_RETRIEVAL_ENABLED=True, SEMANTIC_CANDIDATE_INJECTION_ENABLED=True,
    )
    @patch("recommendations.services.ai_search_orchestrator.retrieve_semantic_places")
    def test_explicit_category_blocks_semantically_similar_wrong_category(self, retrieve):
        retrieve.return_value = {
            "results": [{
                "place_id": self.place.id, "place": self.place, "features": ["조용함"],
                "document": "근거 카페", "document_id": 1,
                "semantic_similarity": .99, "semantic_score": 99,
            }],
            "query_embedding_latency_ms": 1, "vector_search_latency_ms": 1, "backend": "test",
        }
        frame = {"target_objects": ["공원"], "candidate_place_types": ["공원"], "candidate_category_codes": ["city_park"]}
        rows, _ = collect_semantic_candidates("조용한 공원", frame, radius=3000)
        self.assertEqual(rows, [])

    @override_settings(
        SEMANTIC_RETRIEVAL_ENABLED=True, SEMANTIC_CANDIDATE_INJECTION_ENABLED=True,
    )
    @patch("recommendations.services.ai_search_orchestrator.retrieve_semantic_places")
    def test_unknown_hard_feature_blocks_semantic_candidate(self, retrieve):
        retrieve.return_value = {
            "results": [{
                "place_id": self.place.id, "place": self.place, "features": ["조용함"],
                "document": "근거 카페", "document_id": 1,
                "semantic_similarity": .99, "semantic_score": 99,
            }],
            "query_embedding_latency_ms": 1, "vector_search_latency_ms": 1, "backend": "test",
        }
        frame = {
            "target_objects": ["카페"], "candidate_place_types": ["카페"],
            "candidate_category_codes": ["cafe"], "constraints": ["무료"],
        }
        rows, _ = collect_semantic_candidates("무료 카페", frame, radius=3000)
        self.assertEqual(rows, [])

    @override_settings(
        SEMANTIC_RETRIEVAL_ENABLED=True, SEMANTIC_CANDIDATE_INJECTION_ENABLED=True,
    )
    @patch("recommendations.services.ai_search_orchestrator.retrieve_semantic_places")
    def test_query_category_blocks_wrong_semantic_category_when_frame_is_ambiguous(self, retrieve):
        retrieve.return_value = {
            "results": [{
                "place_id": self.place.id, "place": self.place, "features": [],
                "document": "cafe", "document_id": 1,
                "semantic_similarity": .99, "semantic_score": 99,
            }],
            "query_embedding_latency_ms": 1, "vector_search_latency_ms": 1, "backend": "test",
        }
        mistaken_frame = {"candidate_category_codes": ["cafe"], "target_objects": ["카페"]}
        rows, _ = collect_semantic_candidates("혼밥하기 좋은 식당", mistaken_frame, radius=3000)
        self.assertEqual(rows, [])

    @override_settings(
        SEMANTIC_RETRIEVAL_ENABLED=True, SEMANTIC_CANDIDATE_INJECTION_ENABLED=True,
    )
    @patch("recommendations.services.ai_search_orchestrator.retrieve_semantic_places")
    def test_optional_semantic_failure_falls_back_to_existing_search(self, retrieve):
        retrieve.side_effect = RuntimeError("pilot database unavailable")
        rows, debug = collect_semantic_candidates("semantic pilot", {}, radius=3000)
        self.assertEqual(rows, [])
        self.assertEqual(debug["status"], "unavailable")
