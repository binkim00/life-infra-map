from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from recommendations.models import Place, PlaceFeatureDocument


@override_settings(
    SEMANTIC_EMBEDDING_MODEL="text-embedding-3-small",
    SEMANTIC_EMBEDDING_DIMENSIONS=2,
    SEMANTIC_PILOT_MAX_DOCUMENTS=100,
)
class SemanticEmbeddingCommandTests(TestCase):
    def setUp(self):
        place = Place.objects.create(
            name="파일럿 카페", category="cafe", address="부산광역시 중구",
            lat=35.1, lng=129.0, source="test", external_id="semantic-pilot",
        )
        self.document = PlaceFeatureDocument.objects.create(
            place=place, document="파일럿 카페 / cafe / 부산 / 조용함",
            features=["조용함"], fingerprint="f" * 64,
        )

    @patch("recommendations.management.commands.embed_place_feature_documents.embed_openai_texts")
    def test_embedding_is_idempotent_for_unchanged_document(self, mocked_embed):
        mocked_embed.return_value = {
            "vectors": [[1.0, 0.0]], "model": "text-embedding-3-small",
            "dimensions": 2, "input_tokens": 5, "estimated_cost_usd": 0.000001,
            "latency_ms": 10.0,
        }
        call_command("embed_place_feature_documents", limit=1, stdout=StringIO())
        call_command("embed_place_feature_documents", limit=1, stdout=StringIO())

        self.document.refresh_from_db()
        self.assertEqual(self.document.embedding, [1.0, 0.0])
        self.assertEqual(mocked_embed.call_count, 1)
