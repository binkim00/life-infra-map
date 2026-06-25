import json
import logging

from django.conf import settings

from recommendations.services.ai_situation_parser import _call_gms_chat_json


logger = logging.getLogger(__name__)


EVIDENCE_LEVEL_RANK = {
    "strong": 0,
    "medium": 1,
    "weak": 2,
}

AI_CANDIDATE_RERANKER_PROMPT = """
You are the semantic candidate reranker for a place recommendation service.

Return only one JSON object:
{
  "candidates": [
    {
      "candidate_id": "",
      "decision": "include | exclude | needs_verification",
      "semantic_score": 0,
      "evidence_level": "strong | medium | weak",
      "matched_fields": [],
      "unmet_constraints": [],
      "reason": ""
    }
  ]
}

Rules:
- Use only the candidate facts provided in the input.
- Do not invent place facts, menus, addresses, facilities, coordinates, or opening hours.
- Source is not priority. DB, Kakao, and Web are candidate evidence sources.
- Verified/admin/user-approved DB evidence is stronger than suggested DB evidence.
- Suggested-only or category-only evidence cannot be strong by itself.
- pre_ai_evidence_level is only a hint; make the final decision from frame/candidate compatibility.
- Compare target_objects, result_match_terms, candidate_place_types, constraints, and exclusions against candidate name/category/tags/snippet.
- If the candidate category/type clearly conflicts with the frame target, exclude it even when it has unrelated DB tags.
- DB tags only help when they directly support the current frame target or constraints.
- pre_ai_unmet_constraints are deterministic compatibility warnings; do not mark those candidates strong.
- policy_verification_needed means the requested facility policy is not proven by the candidate facts.
- retrieval_query shows how a candidate was collected; it is not direct proof that a specific menu/facility exists.
- For specific menu/item/facility targets, prefer direct evidence in name/category/tags/snippet. Use needs_verification for compatible but unproven candidates, and exclude clearly incompatible types.
- Use needs_verification when the candidate type is semantically compatible but details are not proven.
- Missing detail evidence is not a contradiction by itself.
- Exclude only candidates that are clearly incompatible with the current frame target.
- If the target is specific, do not include broad unrelated cafe/shelter/restaurant candidates.
- For urgent_nearest, include only semantically compatible candidates; distance is sorted later.
- Return a row only for candidate_id values that exist in the input.
""".strip()


def _clean_text(value, max_length=500):
    text = str(value or "").strip()
    if max_length and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _as_list(value, max_items=12):
    if value in (None, ""):
        return []
    if isinstance(value, (str, int, float, bool)):
        value = [value]
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:max_items]:
        if isinstance(item, dict):
            item = item.get("value") or item.get("label") or item.get("text")
        text = _clean_text(item, 120)
        if text and text not in result:
            result.append(text)
    return result


def _score(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(parsed, 100.0))


def _distance(candidate):
    for key in ("distance", "distance_m", "distanceM"):
        try:
            value = float(candidate.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return 999999999.0


def _is_ai_enabled():
    if getattr(settings, "CONVERSATIONAL_SEARCH_AI_ENABLED", False) is not True:
        return False, "conversational_search_ai_disabled"
    if not getattr(settings, "GMS_API_KEY", ""):
        return False, "missing_gms_api_key"
    if not (getattr(settings, "GMS_API_URL", "") or getattr(settings, "GMS_API_BASE_URL", "")):
        return False, "missing_gms_api_url"
    return True, ""


def _candidate_payload(candidate):
    return {
        "candidate_id": _clean_text(candidate.get("id")),
        "source": _clean_text(candidate.get("candidate_source") or candidate.get("source_type") or candidate.get("source")),
        "name": _clean_text(candidate.get("name"), 160),
        "category": _clean_text(candidate.get("category"), 160),
        "address": _clean_text(
            candidate.get("address") or candidate.get("road_address") or candidate.get("detail_location"),
            240,
        ),
        "distance": candidate.get("distance") or candidate.get("distance_m"),
        "retrieval_query": _clean_text(candidate.get("retrieval_query"), 160),
        "db_verified_tags": _as_list(candidate.get("verified_tags") or candidate.get("verified_tag_labels")),
        "db_suggested_tags": _as_list(candidate.get("suggested_tags") or candidate.get("suggested_tag_labels")),
        "db_candidate_tags": _as_list(candidate.get("candidate_tags") or candidate.get("candidate_tag_labels")),
        "warning_tags": _as_list(candidate.get("warning_tags")),
        "kakao_category": _clean_text(candidate.get("kakao_category") or candidate.get("category"), 160),
        "web_snippet": _clean_text(candidate.get("web_snippet") or candidate.get("evidence_text"), 500),
        "source_url": _clean_text(candidate.get("external_url") or candidate.get("place_url"), 500),
        "pre_ai_evidence_level": _clean_text(candidate.get("pre_ai_evidence_level") or candidate.get("evidence_level")),
        "pre_ai_matched_fields": _as_list(candidate.get("pre_ai_matched_fields") or candidate.get("matched_fields")),
        "pre_ai_matched_evidence": candidate.get("matched_evidence")[:8]
        if isinstance(candidate.get("matched_evidence"), list)
        else [],
        "pre_ai_unmet_constraints": _as_list(candidate.get("pre_ai_unmet_constraints"), max_items=8),
        "policy_matched_constraints": _as_list(candidate.get("policy_matched_constraints"), max_items=8),
        "policy_verification_needed": _as_list(candidate.get("policy_verification_needed"), max_items=8),
    }


def _normalize_reranker_rows(raw, candidate_ids):
    if not isinstance(raw, dict):
        return {}
    rows = raw.get("candidates")
    if not isinstance(rows, list):
        return {}
    normalized = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_id = _clean_text(row.get("candidate_id"))
        if candidate_id not in candidate_ids:
            continue
        decision = _clean_text(row.get("decision")).lower()
        if decision not in {"include", "exclude", "needs_verification"}:
            decision = "exclude"
        evidence_level = _clean_text(row.get("evidence_level")).lower()
        if evidence_level not in EVIDENCE_LEVEL_RANK:
            evidence_level = "weak"
        if decision == "needs_verification" and evidence_level == "strong":
            evidence_level = "medium"
        normalized[candidate_id] = {
            "decision": decision,
            "semantic_score": _score(row.get("semantic_score")),
            "evidence_level": evidence_level,
            "matched_fields": _as_list(row.get("matched_fields"), max_items=10),
            "unmet_constraints": _as_list(row.get("unmet_constraints"), max_items=10),
            "reason": _clean_text(row.get("reason"), 300),
        }
    return normalized


def semantic_rerank_candidates(frame, candidates, *, ranking_policy="evidence_first", max_candidates=20):
    enabled, reason = _is_ai_enabled()
    if not enabled:
        return [], {
            "status": "unavailable",
            "reason": reason,
            "input_count": len(candidates or []),
            "included_count": 0,
        }

    input_candidates = [
        candidate
        for candidate in (candidates or [])
        if isinstance(candidate, dict) and _clean_text(candidate.get("id"))
    ][:max_candidates]

    def run_reranker(candidate_batch, token_budget):
        batch_ids = {_clean_text(candidate.get("id")) for candidate in candidate_batch}
        batch_payload = {
            "frame": frame if isinstance(frame, dict) else {},
            "ranking_policy": ranking_policy or "evidence_first",
            "candidates": [_candidate_payload(candidate) for candidate in candidate_batch],
        }
        raw_response = _call_gms_chat_json(
            query=json.dumps(batch_payload, ensure_ascii=False),
            system_prompt=AI_CANDIDATE_RERANKER_PROMPT,
            max_completion_tokens=token_budget,
            model=getattr(settings, "AI_RERANK_MODEL", "gpt-5-nano"),
            timeout=getattr(settings, "AI_RERANK_TIMEOUT", getattr(settings, "AI_REQUEST_TIMEOUT", 20)),
        )
        return batch_ids, _normalize_reranker_rows(raw_response, batch_ids)

    token_budget = int(getattr(settings, "AI_SEARCH_RERANK_MAX_COMPLETION_TOKENS", 2500) or 2500)
    retry_used = False
    call_count = 0
    failure_reasons = []

    def collect_decisions(candidate_batch, *, retry=False):
        nonlocal retry_used, call_count
        if not candidate_batch:
            return {}, set()
        batch_ids = {_clean_text(candidate.get("id")) for candidate in candidate_batch}
        try:
            call_count += 1
            _, batch_decisions = run_reranker(
                candidate_batch,
                max(1200, token_budget // 2) if retry else token_budget,
            )
        except Exception as exc:
            logger.info("AI candidate reranker batch failed.", exc_info=True)
            failure_reasons.append(f"{exc.__class__.__name__}:{len(candidate_batch)}")
            return {}, batch_ids

        missing_ids = batch_ids - set(batch_decisions.keys())
        return batch_decisions, missing_ids

    decisions, missing_ids = collect_decisions(input_candidates)
    if missing_ids and call_count < 2:
        retry_used = True
        by_id = {_clean_text(candidate.get("id")): candidate for candidate in input_candidates}
        missing_candidates = [
            by_id[candidate_id]
            for candidate_id in sorted(missing_ids)
            if candidate_id in by_id
        ]
        retry_decisions, retry_missing_ids = collect_decisions(missing_candidates, retry=True)
        decisions.update(retry_decisions)
        missing_ids = (missing_ids - set(retry_decisions.keys())) | retry_missing_ids

    if not decisions and input_candidates:
        unresolved_ids = missing_ids or {_clean_text(candidate.get("id")) for candidate in input_candidates}
        return [], {
            "status": "failed" if failure_reasons else "invalid_response",
            "reason": failure_reasons[-1] if failure_reasons else "missing_candidate_decisions",
            "input_count": len(input_candidates),
            "included_count": 0,
            "needs_verification_count": 0,
            "excluded_count": 0,
            "ai_included_count": 0,
            "ai_needs_verification_count": 0,
            "ai_excluded_count": 0,
            "unresolved_count": len(unresolved_ids),
            "unresolved_candidate_ids": sorted(unresolved_ids),
            "missing_candidate_ids": sorted(unresolved_ids),
            "reranker_partial": False,
            "reranker_call_count": call_count,
            "retry_used": retry_used,
            "call_count": call_count,
            "failure_reasons": failure_reasons,
            "excluded_candidates": [],
            "unresolved_candidates": [
                {
                    "id": candidate.get("id"),
                    "name": candidate.get("name"),
                    "source": candidate.get("candidate_source"),
                    "reason": "missing_candidate_decision",
                }
                for candidate in input_candidates
                if _clean_text(candidate.get("id")) in unresolved_ids
            ],
            "decisions": decisions,
        }

    ranked = []
    excluded = []
    by_id = {_clean_text(candidate.get("id")): candidate for candidate in input_candidates}
    for candidate_id, decision in decisions.items():
        candidate = by_id.get(candidate_id)
        if not candidate:
            continue
        needs_verification = decision["decision"] == "needs_verification"
        semantic_reason = decision["reason"]
        if needs_verification:
            semantic_reason = (
                semantic_reason or "Candidate type is compatible, but details need verification."
            )
            if "확인" not in semantic_reason and "verification" not in semantic_reason.lower():
                semantic_reason = f"{semantic_reason} 세부 조건은 방문 전 확인 필요."
        updated = {
            **candidate,
            "semantic_reranker": decision,
            "semantic_score": decision["semantic_score"],
            "evidence_level": decision["evidence_level"],
            "frame_evidence_tier": decision["evidence_level"],
            "matched_fields": decision["matched_fields"],
            "unmet_constraints": decision["unmet_constraints"],
            "semantic_reason": semantic_reason,
            "verification_required": needs_verification,
            "recommendation_reason": semantic_reason,
            "recommend_reason": semantic_reason,
            "compatibility_gate": (
                "needs_verification"
                if needs_verification
                else ("passed" if decision["decision"] == "include" else "excluded")
            ),
            "compatibility_gate_reason": (
                "details_need_verification"
                if needs_verification
                else ("" if decision["decision"] == "include" else "semantic_reranker_excluded")
            ),
            "score": decision["semantic_score"],
        }
        if decision["decision"] in {"include", "needs_verification"}:
            ranked.append(updated)
        else:
            excluded.append(updated)

    if ranking_policy == "urgent_nearest":
        ranked = [candidate for candidate in ranked if candidate.get("semantic_score", 0) >= 40]
        ranked.sort(key=lambda candidate: (
            _distance(candidate),
            -float(candidate.get("semantic_score") or 0),
            EVIDENCE_LEVEL_RANK.get(candidate.get("evidence_level"), 9),
            str(candidate.get("id")),
        ))
    else:
        ranked.sort(key=lambda candidate: (
            -float(candidate.get("semantic_score") or 0),
            EVIDENCE_LEVEL_RANK.get(candidate.get("evidence_level"), 9),
            _distance(candidate),
            str(candidate.get("id")),
        ))

    ranked = [
        {
            **candidate,
            "backend_rank": index + 1,
            "unified_rank": index + 1,
            "unified_ranker_applied": True,
        }
        for index, candidate in enumerate(ranked)
    ]

    included_count = sum(1 for decision in decisions.values() if decision["decision"] == "include")
    needs_verification_count = sum(
        1 for decision in decisions.values() if decision["decision"] == "needs_verification"
    )
    excluded_count = sum(1 for decision in decisions.values() if decision["decision"] == "exclude")
    unresolved_ids = set(missing_ids or set()) - set(decisions.keys())
    status = "partial_executed" if unresolved_ids else "executed"

    return ranked, {
        "status": status,
        "reason": "missing_candidate_decisions" if unresolved_ids else "",
        "input_count": len(input_candidates),
        "included_count": len(ranked),
        "needs_verification_count": needs_verification_count,
        "excluded_count": len(excluded),
        "ai_included_count": included_count,
        "ai_needs_verification_count": needs_verification_count,
        "ai_excluded_count": excluded_count,
        "unresolved_count": len(unresolved_ids),
        "unresolved_candidate_ids": sorted(unresolved_ids),
        "reranker_partial": bool(unresolved_ids),
        "reranker_call_count": call_count,
        "retry_used": retry_used,
        "call_count": call_count,
        "missing_candidate_ids": sorted(unresolved_ids),
        "failure_reasons": failure_reasons,
        "excluded_candidates": [
            {
                "id": candidate.get("id"),
                "name": candidate.get("name"),
                "source": candidate.get("candidate_source"),
                "reason": candidate.get("semantic_reason") or candidate.get("compatibility_gate_reason"),
            }
            for candidate in excluded[:50]
        ],
        "unresolved_candidates": [
            {
                "id": candidate.get("id"),
                "name": candidate.get("name"),
                "source": candidate.get("candidate_source"),
                "reason": "missing_candidate_decision",
            }
            for candidate in input_candidates
            if _clean_text(candidate.get("id")) in unresolved_ids
        ],
        "decisions": decisions,
    }
