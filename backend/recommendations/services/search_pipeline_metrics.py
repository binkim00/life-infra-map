"""Small, bounded search stage metrics with no query or evidence text."""

import json
import logging


logger = logging.getLogger("recommendations.search_pipeline_metrics")


def _number(value):
    try:
        return round(max(0, float(value)), 2)
    except (TypeError, ValueError):
        return 0


def build_search_metrics(response):
    debug = response.get("debug_pipeline") or {}
    counts = debug.get("candidate_counts") or {}
    timings = response.get("timings") or debug
    gate = (debug.get("reranker") or {}).get("common_hard_gate") or {}
    results = response.get("results") or []
    top = results[:5]
    return {
        "schema": 1,
        "action": response.get("decision_action") if response.get("decision_action") in {
            "search", "ask_clarification", "ai_unavailable",
        } else "other",
        "latency_ms": {
            key: _number(timings.get(key)) for key in (
                "intent_parsing_latency_ms", "db_candidate_retrieval_latency_ms",
                "kakao_search_latency_ms", "web_latency_ms", "ranking_latency_ms",
                "total_latency_ms",
            )
        },
        "counts": {
            key: int(counts.get(key) or 0) for key in (
                "db", "kakao", "web", "identity_attempts", "identity_matches",
                "verified_before_web", "evidence_join_success", "confirmed_candidates",
                "top_results", "web_verified_top_five",
            )
        },
        "gate_rejections": {
            key: int((gate.get("removed_by_type") or {}).get(key) or 0)
            for key in ("category", "region", "feature")
        },
        "zero_result": len(results) == 0,
        "verified_top_five": sum(
            bool(item.get("hard_gate_passed") and item.get("result_tier") == "all_conditions_met")
            for item in top
        ),
        "top_five_count": len(top),
    }


def log_search_metrics(response):
    try:
        logger.warning("search_pipeline_metrics %s", json.dumps(build_search_metrics(response), separators=(",", ":")))
    except Exception:
        logger.warning("Search pipeline metric collection failed.")
