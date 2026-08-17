import hashlib
import re
import time
import unicodedata

import requests
from django.conf import settings
from django.core.cache import cache


OPENAI_EMBEDDING_PRICE_PER_MILLION_TOKENS = 0.02


class EmbeddingProviderError(RuntimeError):
    pass


def _normalized_query(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).strip().casefold())


def embed_openai_query_cached(query, *, model=None, dimensions=None, timeout=30):
    """Cache only the vector in the process cache; raw user queries are never persisted."""
    model = model or getattr(settings, "SEMANTIC_EMBEDDING_MODEL", "text-embedding-3-small")
    dimensions = dimensions or int(getattr(settings, "SEMANTIC_EMBEDDING_DIMENSIONS", 512))
    version = str(getattr(settings, "SEMANTIC_QUERY_EMBEDDING_CACHE_VERSION", "v1"))
    normalized = _normalized_query(query)
    if not normalized:
        raise EmbeddingProviderError("embedding_input_is_empty")
    digest = hashlib.sha256(
        f"{version}\n{model}\n{dimensions}\n{normalized}".encode("utf-8")
    ).hexdigest()
    key = f"semantic-query:{digest}"
    started = time.perf_counter()
    cached = cache.get(key)
    if isinstance(cached, list) and len(cached) == dimensions:
        return {
            "vector": cached,
            "model": model,
            "dimensions": dimensions,
            "input_tokens": 0,
            "estimated_cost_usd": 0.0,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "cache_hit": True,
            "api_calls": 0,
        }
    embedded = embed_openai_texts([normalized], model=model, dimensions=dimensions, timeout=timeout)
    ttl = int(getattr(settings, "SEMANTIC_QUERY_EMBEDDING_CACHE_TTL", 900))
    if ttl > 0:
        cache.set(key, embedded["vectors"][0], timeout=ttl)
    return {
        "vector": embedded["vectors"][0],
        "model": embedded["model"],
        "dimensions": embedded["dimensions"],
        "input_tokens": embedded["input_tokens"],
        "estimated_cost_usd": embedded["estimated_cost_usd"],
        "latency_ms": embedded["latency_ms"],
        "cache_hit": False,
        "api_calls": 1,
    }


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
