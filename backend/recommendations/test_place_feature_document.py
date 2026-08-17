from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from recommendations.models import Place, PlaceFeatureDocument, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.place_feature_document import (
    build_place_feature_document,
    embedding_document,
    embedding_source_hash,
)
from recommendations.services.semantic_retrieval import retrieve_semantic_places, semantic_retrieval_status


class PlaceFeatureDocumentTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="근거 카페", category="cafe", address="부산광역시 부산진구",
            lat=35.1, lng=129.0, source="kakao_local", external_id="feature-doc-1",
        )

    def add_tag(self, name, *, status="confirmed", expires_at=None, polarity="positive"):
        tag = Tag.objects.create(name=name)
        PlaceTag.objects.create(
            place=self.place, tag=tag, source="field_rule", status=status,
            confidence=90, is_verified=status == "confirmed",
        )
        PlaceTagEvidence.objects.create(
            place=self.place, tag=tag, source="field_rule", polarity=polarity,
            confidence=90, evidence_key=f"feature-{name}", expires_at=expires_at,
        )

    def test_document_contains_only_active_supported_features(self):
        self.add_tag("콘센트있음", expires_at=timezone.now() + timedelta(days=1))
        self.add_tag("조용함", expires_at=timezone.now() - timedelta(days=1))
        self.add_tag("무료와이파이", status="rejected", expires_at=timezone.now() + timedelta(days=1))

        payload = build_place_feature_document(self.place)

        self.assertIn("콘센트있음", payload["features"])
        self.assertNotIn("조용함", payload["features"])
        self.assertNotIn("무료와이파이", payload["features"])
        self.assertIn("근거 카페 / cafe / 부산광역시 부산진구", payload["document"])

    def test_embedding_document_strategies_use_only_stored_facts(self):
        self.add_tag("콘센트있음", expires_at=timezone.now() + timedelta(days=1))
        payload = build_place_feature_document(self.place)
        document = PlaceFeatureDocument.objects.create(place=self.place, **payload)

        self.assertEqual(embedding_document(document, strategy="tags"), "콘센트있음")
        self.assertEqual(
            embedding_document(document, strategy="contextual"),
            "근거 카페 / cafe / 부산 / 콘센트있음",
        )
        self.assertEqual(embedding_document(document, strategy="full"), payload["document"])
        self.assertEqual(len(embedding_source_hash(document, strategy="contextual")), 64)

    @override_settings(SEMANTIC_RETRIEVAL_ENABLED=False, SEMANTIC_EMBEDDING_PROVIDER="")
    def test_semantic_retrieval_reports_disabled_without_fake_vectors(self):
        self.assertEqual(semantic_retrieval_status()["reason"], "feature_disabled")

    @override_settings(SEMANTIC_RETRIEVAL_ENABLED=True, SEMANTIC_EMBEDDING_PROVIDER="openai")
    def test_semantic_retrieval_ranks_existing_places_without_creating_places(self):
        payload = build_place_feature_document(self.place)
        PlaceFeatureDocument.objects.create(
            place=self.place, **payload, embedding=[1.0, 0.0], embedding_dimensions=2,
            embedding_provider="openai", embedding_model="test",
        )
        before = Place.objects.count()
        result = retrieve_semantic_places("조용한 곳", query_embedding=[1.0, 0.0], top_k=5)
        self.assertEqual(result["results"][0]["place_id"], self.place.id)
        self.assertEqual(result["results"][0]["semantic_score"], 100.0)
        self.assertEqual(Place.objects.count(), before)
