import hashlib
import json
import logging
import re

from django.conf import settings
from django.core.cache import cache

from recommendations.services.ai_situation_parser import _call_ai_chat_json as _shared_call_ai_chat_json
from recommendations.services.ai_json_client import get_ai_json_unavailable_reason


logger = logging.getLogger(__name__)

_call_gms_chat_json = _shared_call_ai_chat_json


def _call_ai_chat_json(*args, **kwargs):
    return _call_gms_chat_json(*args, **kwargs)


EVIDENCE_LEVEL_RANK = {
    "strong": 0,
    "medium": 1,
    "weak": 2,
}

AI_CANDIDATE_RERANKER_PROMPT = """
You are the semantic candidate reranker for a place recommendation service.

Return only one JSON object. The "candidates" array must contain exactly one row
per candidate in the input, in the same order, using this row shape:
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
- The input tells you candidate_count. Return exactly that many rows.
- Never omit a candidate. Judge every candidate, and use exclude for the ones that do not fit.
- semantic_score is 0-100 and must reflect how well the candidate matches the frame target.
  Use 70-100 for include, 40-69 for needs_verification, and 0-39 for exclude. Never leave it at 0 for a kept candidate.
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
- reason must be natural Korean for end users, one short sentence.
- Do not mention internal field names such as frame, evidence_level, semantic_score, candidate_id, or retrieval_query in reason.
""".strip()


STRING_ARRAY_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
}

AI_CANDIDATE_RERANKER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "enum": ["include", "exclude", "needs_verification"],
                    },
                    "semantic_score": {"type": "number"},
                    "evidence_level": {
                        "type": "string",
                        "enum": ["strong", "medium", "weak"],
                    },
                    "matched_fields": STRING_ARRAY_SCHEMA,
                    "unmet_constraints": STRING_ARRAY_SCHEMA,
                    "reason": {"type": "string"},
                },
                "required": [
                    "candidate_id",
                    "decision",
                    "semantic_score",
                    "evidence_level",
                    "matched_fields",
                    "unmet_constraints",
                    "reason",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


def _rerank_cache_ttl():
    return max(0, int(getattr(settings, "AI_RERANK_CACHE_TTL", 900) or 0))


def _rerank_cache_key(batch_query, *, model, effort, token_budget):
    if not _rerank_cache_ttl():
        return ""
    fingerprint = f"{model}|{effort}|{token_budget}|{batch_query}"
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    return f"ai_rerank:{digest}"


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


def _format_distance(distance):
    if distance is None or distance >= 999999999.0:
        return ""
    if distance >= 1000:
        return f"약 {distance / 1000:.1f}km"
    return f"약 {int(round(distance))}m"


def _has_korean(value):
    return any("\uac00" <= char <= "\ud7a3" for char in _clean_text(value, 500))


def _has_ascii_word(value):
    return bool(re.search(r"[A-Za-z]{3,}", _clean_text(value, 500)))


def _looks_internal_or_english_reason(value):
    text = _clean_text(value, 500)
    if not text:
        return True
    lowered = text.lower()
    internal_markers = (
        "candidate",
        "frames require",
        "frame",
        "evidence_level",
        "semantic_score",
        "retrieval_query",
        "pre_ai",
        "details need verification",
        "compatible evidence",
        "within target type",
        "matching with",
        "프레임",
        "타깃",
        "타겟",
    )
    if any(marker in lowered for marker in internal_markers):
        return True
    return _has_ascii_word(text) and not _has_korean(text)


def _reason_conflicts_with_candidate_type(candidate, reason):
    reason_text = _clean_text(reason, 500)
    if not reason_text:
        return False
    candidate_text = " ".join(
        _clean_text(candidate.get(key), 500)
        for key in (
            "name",
            "category",
            "kakao_category",
            "source_category",
            "external_category",
        )
    )
    for field in (
        "matched_tags",
        "matched_tag_labels",
        "verified_tags",
        "verified_tag_labels",
        "suggested_tags",
        "suggested_tag_labels",
        "candidate_tags",
        "candidate_tag_labels",
    ):
        candidate_text = f"{candidate_text} {' '.join(_as_list(candidate.get(field), max_items=8))}"
    compact_candidate = candidate_text.replace(" ", "").lower()
    type_terms = [
        "도서관",
        "카페",
        "식당",
        "음식점",
        "공원",
        "화장실",
        "흡연구역",
        "흡연실",
        "주차장",
        "노래방",
        "쇼핑몰",
        "백화점",
        "아울렛",
        "박물관",
        "미술관",
        "갤러리",
    ]
    for term in type_terms:
        compact_term = term.replace(" ", "").lower()
        if compact_term in reason_text.replace(" ", "").lower() and compact_term not in compact_candidate:
            return True
    return False


def _public_source_label(candidate):
    source = _clean_text(
        candidate.get("candidate_source")
        or candidate.get("source_type")
        or candidate.get("source")
    ).lower()
    if "db" in source:
        return "저장된 장소 정보"
    if "kakao" in source:
        return "카카오 지도 정보"
    if "web" in source:
        return "웹 참고 정보"
    return "수집된 장소 정보"


def _public_category(candidate):
    category = _clean_text(candidate.get("category"), 80)
    return category if category and _has_korean(category) else ""


def _public_matched_labels(candidate, decision, max_items=2):
    labels = []
    evidence = candidate.get("matched_evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "retrieval_query_target":
                continue
            text = _clean_text(item.get("label") or item.get("value"), 40)
            if text and _has_korean(text) and text not in labels:
                labels.append(text)
            if len(labels) >= max_items:
                return labels
    for field in decision.get("matched_fields") or []:
        text = _clean_text(field, 40)
        if text and _has_korean(text) and text not in labels:
            labels.append(text)
        if len(labels) >= max_items:
            break
    return labels


def _public_semantic_reason(candidate, decision, *, needs_verification=False):
    matched_labels = _public_matched_labels(candidate, decision)
    category = _public_category(candidate)
    source_label = _public_source_label(candidate)
    distance_text = _format_distance(_distance(candidate))

    if matched_labels:
        reason = f"{', '.join(matched_labels)} 조건이 보여서 후보로 정리했어요."
    elif category:
        reason = f"{category} 분류가 요청 조건과 맞아 보여 후보로 정리했어요."
    else:
        reason = f"{source_label}를 기준으로 요청 조건과 가까운 후보로 정리했어요."

    if distance_text:
        reason = f"{reason} 기준 위치에서 {distance_text} 거리예요."

    if needs_verification and "확인" not in reason:
        reason = f"{reason} 세부 정보는 방문 전에 확인해 주세요."

    return reason


def _safe_semantic_reason(candidate, decision, *, needs_verification=False):
    # The model may phrase a plausible qualitative claim that is absent from
    # the supplied candidate facts.  User-facing reasons therefore come only
    # from deterministic matched evidence/category/distance fields.
    return _public_semantic_reason(candidate, decision, needs_verification=needs_verification)


def _distance_score(candidate):
    distance = _distance(candidate)
    if distance >= 999999999.0:
        return 50.0
    if distance <= 300:
        return 100.0
    if distance <= 700:
        return 85.0
    if distance <= 1500:
        return 70.0
    if distance <= 3000:
        return 50.0
    if distance <= 5000:
        return 30.0
    return 10.0


def _hybrid_score(candidate, decision):
    weights = getattr(settings, "AI_SEARCH_HYBRID_WEIGHTS", {}) or {}
    default_weights = {
        "condition": 0.20, "tag": 0.10, "semantic": 0.35,
        "distance": 0.10, "evidence": 0.10, "freshness": 0.05,
        "reliability": 0.10,
    }
    resolved = {key: max(0.0, float(weights.get(key, value))) for key, value in default_weights.items()}
    total_weight = sum(resolved.values()) or 1.0

    condition_score = _score(candidate.get("score"))
    matched = _as_list(candidate.get("matched_tags")) or _as_list(candidate.get("matched_tag_labels"))
    tag_score = min(100.0, len(matched) * 25.0)
    semantic_score = _score(decision.get("semantic_score"))
    evidence_level = _clean_text(
        candidate.get("pre_ai_evidence_level") or decision.get("evidence_level")
    )
    evidence_score = {"strong": 90.0, "medium": 65.0, "weak": 35.0}.get(evidence_level, 40.0)
    source = _clean_text(candidate.get("candidate_source") or candidate.get("source")).lower()
    has_verified = bool(_as_list(candidate.get("verified_tags")) or _as_list(candidate.get("verified_tag_labels")))
    reliability_score = 90.0 if source == "db" and has_verified else 75.0 if source == "db" else 65.0 if source == "kakao" else 50.0
    freshness_score = _score((candidate.get("score_breakdown") or {}).get("freshness_score")) or 50.0
    penalty = min(100.0, len(_as_list(candidate.get("pre_ai_unmet_constraints"))) * 100.0)
    components = {
        "condition_score": condition_score,
        "tag_score": tag_score,
        "semantic_score": semantic_score,
        "distance_score": _distance_score(candidate),
        "evidence_score": evidence_score,
        "freshness_score": freshness_score,
        "reliability_score": reliability_score,
        "penalty": penalty,
    }
    weighted = sum(
        components[f"{key}_score"] * value
        for key, value in resolved.items()
    ) / total_weight
    final_score = max(0.0, min(100.0, round(weighted - penalty, 2)))
    return final_score, {**components, "final_score": final_score, "weights": resolved}


def _is_ai_enabled():
    if getattr(settings, "AI_RERANK_ENABLED", True) is not True:
        return False, "ai_reranker_disabled"
    if getattr(settings, "CONVERSATIONAL_SEARCH_AI_ENABLED", False) is not True:
        return False, "conversational_search_ai_disabled"
    reason = get_ai_json_unavailable_reason()
    if reason:
        return False, reason
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
            "candidate_count": len(candidate_batch),
            "candidates": [_candidate_payload(candidate) for candidate in candidate_batch],
        }
        batch_query = json.dumps(batch_payload, ensure_ascii=False)
        model = getattr(settings, "AI_RERANK_MODEL", "gpt-5-nano")
        effort = getattr(settings, "AI_RERANK_REASONING_EFFORT", "low")

        # 같은 후보 묶음에는 같은 판정이 나오므로 재호출 없이 재사용한다.
        # 판정 내용은 그대로 쓰고 호출만 건너뛰기 때문에 정확도에는 영향이 없다.
        cache_key = _rerank_cache_key(batch_query, model=model, effort=effort, token_budget=token_budget)
        cached = cache.get(cache_key) if cache_key else None
        if isinstance(cached, dict):
            return batch_ids, {
                candidate_id: decision
                for candidate_id, decision in cached.items()
                if candidate_id in batch_ids
            }

        raw_response = _call_ai_chat_json(
            query=batch_query,
            system_prompt=AI_CANDIDATE_RERANKER_PROMPT,
            max_completion_tokens=token_budget,
            model=model,
            timeout=getattr(settings, "AI_RERANK_TIMEOUT", getattr(settings, "AI_REQUEST_TIMEOUT", 20)),
            response_schema=AI_CANDIDATE_RERANKER_RESPONSE_SCHEMA,
            schema_name="ai_candidate_rerank",
            reasoning_effort=effort,
        )
        decisions = _normalize_reranker_rows(raw_response, batch_ids)
        if cache_key and decisions:
            cache.set(cache_key, decisions, _rerank_cache_ttl())
        return batch_ids, decisions

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
        hard_unmet = _as_list(candidate.get("pre_ai_unmet_constraints"))
        if hard_unmet:
            excluded.append({
                **candidate,
                "semantic_reranker": decision,
                "compatibility_gate": "excluded",
                "compatibility_gate_reason": "hard_condition_failed",
                "hard_condition_failures": hard_unmet,
            })
            continue
        needs_verification = decision["decision"] == "needs_verification"
        final_score, hybrid_breakdown = _hybrid_score(candidate, decision)
        semantic_reason = _safe_semantic_reason(
            candidate,
            decision,
            needs_verification=needs_verification,
        )
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
            "score": final_score,
            "score_breakdown": {
                **(candidate.get("score_breakdown") or {}),
                **hybrid_breakdown,
            },
        }
        if decision["decision"] in {"include", "needs_verification"}:
            ranked.append(updated)
        else:
            excluded.append(updated)

    if ranking_policy == "urgent_nearest":
        ranked = [candidate for candidate in ranked if candidate.get("semantic_score", 0) >= 40]
        ranked.sort(key=lambda candidate: (
            _distance(candidate),
            -float(candidate.get("score") or 0),
            EVIDENCE_LEVEL_RANK.get(candidate.get("evidence_level"), 9),
            str(candidate.get("id")),
        ))
    else:
        ranked.sort(key=lambda candidate: (
            -float(candidate.get("score") or 0),
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
