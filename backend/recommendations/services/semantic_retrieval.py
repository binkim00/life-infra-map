import math
import time

from django.conf import settings

from recommendations.models import PlaceFeatureDocument
from recommendations.services.semantic_embeddings import embed_openai_texts
from recommendations.services.pgvector_pilot import connect_pilot, sql_vector_search


class SemanticRetrievalUnavailable(RuntimeError):
    pass


def semantic_retrieval_status():
    provider = getattr(settings, "SEMANTIC_EMBEDDING_PROVIDER", "")
    enabled = bool(getattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", False))
    if not enabled:
        return {"available": False, "reason": "feature_disabled", "provider": provider}
    if not provider:
        return {"available": False, "reason": "embedding_provider_not_configured", "provider": ""}
    if provider != "openai":
        return {"available": False, "reason": "unsupported_embedding_provider", "provider": provider}
    indexed = PlaceFeatureDocument.objects.exclude(embedding=[]).count()
    if not indexed:
        return {"available": False, "reason": "embedding_index_empty", "provider": provider}
    backend = "pgvector_pilot" if getattr(settings, "SEMANTIC_PGVECTOR_DSN", "") else "python_cosine_pilot"
    return {
        "available": True,
        "reason": backend,
        "provider": provider,
        "indexed_documents": indexed,
        "backend": backend,
    }


def _cosine(left, right):
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def retrieve_semantic_places(query, *, top_k=10, query_embedding=None):
    status = semantic_retrieval_status()
    if not status["available"]:
        raise SemanticRetrievalUnavailable(status["reason"])
    started = time.perf_counter()
    embedding_latency_ms = 0.0
    if query_embedding is None:
        embedded = embed_openai_texts([query])
        query_embedding = embedded["vectors"][0]
        embedding_latency_ms = embedded["latency_ms"]
    rows = []
    dsn = getattr(settings, "SEMANTIC_PGVECTOR_DSN", "")
    if dsn:
        connection = connect_pilot(dsn)
        try:
            sql_rows, vector_latency_ms = sql_vector_search(connection, query_embedding, top_k=top_k)
        finally:
            connection.close()
        document_ids = [row[0] for row in sql_rows]
        by_id = {
            row.id: row for row in PlaceFeatureDocument.objects.filter(id__in=document_ids).select_related("place")
        }
        documents = [(by_id[row[0]], float(row[2])) for row in sql_rows if row[0] in by_id]
    else:
        documents = [
            (document, _cosine(query_embedding, document.embedding))
            for document in PlaceFeatureDocument.objects.exclude(embedding=[]).select_related("place")
        ]
        documents.sort(key=lambda item: (-item[1], item[0].place_id))
        vector_latency_ms = round((time.perf_counter() - started) * 1000 - embedding_latency_ms, 2)
    for document, similarity in documents[:max(1, min(int(top_k), 50))]:
        rows.append({
            "document_id": document.id,
            "place_id": document.place_id,
            "place": document.place,
            "document": document.document,
            "features": document.features,
            "semantic_similarity": round(similarity, 6),
            "semantic_score": round(max(0.0, similarity) * 100, 2),
        })
    return {
        "results": rows,
        "query_embedding_latency_ms": embedding_latency_ms,
        "vector_search_latency_ms": vector_latency_ms,
        "backend": status["backend"],
    }


def attach_semantic_scores(candidates, semantic_results):
    """Attach a component score only; hard filtering remains upstream."""
    scores = {row["place_id"]: row["semantic_score"] for row in semantic_results}
    for candidate in candidates:
        place_id = candidate.get("place_id")
        if place_id in scores:
            candidate["retrieval_semantic_score"] = scores[place_id]
    return candidates
