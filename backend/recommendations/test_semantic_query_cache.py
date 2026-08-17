from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from recommendations.services.semantic_embeddings import embed_openai_query_cached


@override_settings(
    SEMANTIC_EMBEDDING_MODEL="text-embedding-3-small",
    SEMANTIC_EMBEDDING_DIMENSIONS=2,
    SEMANTIC_QUERY_EMBEDDING_CACHE_TTL=900,
    SEMANTIC_QUERY_EMBEDDING_CACHE_VERSION="test-v1",
)
class SemanticQueryEmbeddingCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("recommendations.services.semantic_embeddings.embed_openai_texts")
    def test_normalized_repeat_query_uses_process_cache(self, embed):
        embed.return_value = {
            "vectors": [[0.1, 0.2]], "model": "text-embedding-3-small",
            "dimensions": 2, "input_tokens": 5, "estimated_cost_usd": 0.000001,
            "latency_ms": 100,
        }
        miss = embed_openai_query_cached("  조용한   카페 ")
        hit = embed_openai_query_cached("조용한 카페")

        self.assertFalse(miss["cache_hit"])
        self.assertEqual(miss["api_calls"], 1)
        self.assertTrue(hit["cache_hit"])
        self.assertEqual(hit["api_calls"], 0)
        self.assertEqual(hit["vector"], [0.1, 0.2])
        self.assertEqual(embed.call_count, 1)

    @patch("recommendations.services.semantic_embeddings.embed_openai_texts")
    def test_model_and_dimension_are_part_of_cache_key(self, embed):
        embed.side_effect = [
            {"vectors": [[0.1, 0.2]], "model": "model-a", "dimensions": 2,
             "input_tokens": 1, "estimated_cost_usd": 0, "latency_ms": 1},
            {"vectors": [[0.3, 0.4, 0.5]], "model": "model-a", "dimensions": 3,
             "input_tokens": 1, "estimated_cost_usd": 0, "latency_ms": 1},
        ]
        embed_openai_query_cached("같은 검색", model="model-a", dimensions=2)
        embed_openai_query_cached("같은 검색", model="model-a", dimensions=3)
        self.assertEqual(embed.call_count, 2)
