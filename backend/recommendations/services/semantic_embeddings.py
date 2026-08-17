import time

import requests
from django.conf import settings


OPENAI_EMBEDDING_PRICE_PER_MILLION_TOKENS = 0.02


class EmbeddingProviderError(RuntimeError):
    pass


def embed_openai_texts(texts, *, model=None, dimensions=None, timeout=30):
    texts = [str(text or "").strip() for text in texts]
    if not texts or any(not text for text in texts):
        raise EmbeddingProviderError("embedding_input_is_empty")
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        raise EmbeddingProviderError("missing_openai_api_key")
    model = model or getattr(settings, "SEMANTIC_EMBEDDING_MODEL", "text-embedding-3-small")
    dimensions = dimensions or int(getattr(settings, "SEMANTIC_EMBEDDING_DIMENSIONS", 512))
    base_url = str(getattr(settings, "OPENAI_API_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    started = time.perf_counter()
    try:
        response = requests.post(
            f"{base_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": texts, "dimensions": dimensions},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise EmbeddingProviderError(f"embedding_request_failed:{exc.__class__.__name__}") from exc
    if response.status_code >= 400:
        raise EmbeddingProviderError(f"embedding_http_{response.status_code}:{response.text[:300]}")
    payload = response.json()
    rows = sorted(payload.get("data") or [], key=lambda row: row.get("index", 0))
    vectors = [row.get("embedding") or [] for row in rows]
    if len(vectors) != len(texts) or any(len(vector) != dimensions for vector in vectors):
        raise EmbeddingProviderError("embedding_response_shape_mismatch")
    usage = payload.get("usage") or {}
    total_tokens = int(usage.get("total_tokens") or usage.get("prompt_tokens") or 0)
    return {
        "vectors": vectors,
        "model": payload.get("model") or model,
        "dimensions": dimensions,
        "input_tokens": total_tokens,
        "estimated_cost_usd": total_tokens * OPENAI_EMBEDDING_PRICE_PER_MILLION_TOKENS / 1_000_000,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
