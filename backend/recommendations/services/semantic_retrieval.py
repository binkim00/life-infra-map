from django.conf import settings


class SemanticRetrievalUnavailable(RuntimeError):
    pass


def semantic_retrieval_status():
    provider = getattr(settings, "SEMANTIC_EMBEDDING_PROVIDER", "")
    enabled = bool(getattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", False))
    if not enabled:
        return {"available": False, "reason": "feature_disabled", "provider": provider}
    if not provider:
        return {"available": False, "reason": "embedding_provider_not_configured", "provider": ""}
    return {"available": False, "reason": "vector_index_not_configured", "provider": provider}


def retrieve_semantic_places(*args, **kwargs):
    status = semantic_retrieval_status()
    if not status["available"]:
        raise SemanticRetrievalUnavailable(status["reason"])
    raise SemanticRetrievalUnavailable("semantic_retrieval_backend_not_implemented")
