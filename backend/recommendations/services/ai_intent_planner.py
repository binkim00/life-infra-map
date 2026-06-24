import json
import logging
import re

from django.conf import settings
import requests

from recommendations.services.ai_situation_parser import _call_gms_chat_json


logger = logging.getLogger(__name__)


ALLOWED_ACTIONS = {"search", "ask_clarification", "out_of_scope", "blocked"}
ALLOWED_RANKING_POLICIES = {
    "evidence_first",
    "urgent_nearest",
    "cost_sensitive",
    "distance_first",
}

TRUSTED_FRAME_SOURCE = "ai_extracted"
CLARIFICATION_PATCH_SOURCE = "clarification_patch"

AI_INTENT_SYSTEM_PROMPT = """
You are the AI Intent Planner for a Korean situation-based place recommendation service.

Return only one JSON object. Do not write prose outside JSON.

Your job is to decide whether the user is asking for a place recommendation.
If yes, produce a structured place intent frame. If not, return out_of_scope.
If the user's situation is ambiguous, return ask_clarification with a concrete Korean question.

Hard rules:
- Do not use keyword rules or default place types.
- Do not invent real place names, addresses, coordinates, opening hours, facilities, or menu availability.
- Do not add cafe, shelter, restaurant, or any broad default unless the user's meaning specifically supports it.
- Profanity, slang, dialect, typo, and incomplete Korean should be normalized by meaning, not blocked by default.
- A general information question without an actionable place target is out_of_scope.
- A weather-related or health-related sentence can be search only when it clearly asks for a place to go.
- For medical symptoms, do not diagnose. If the target is unclear, ask whether the user wants medical/pharmacy help or a place to rest.
- For music/singing ambiguity, ask whether the user wants a place to sing or a place to listen.
- Follow-up answers are patches to the previous frame, not standalone raw queries.
- Preserve an earlier explicit location unless the current user message provides a new location.
- Search queries must be Korean keyword queries for place search.
- Long, noisy, vague, typo-heavy, slang, or dialect input must be normalized into the user's likely actionable place target.
- For activity phrasing, infer the place or facility that enables the activity when that is clear; do not search the raw verb phrase.
- Use canonical Korean place-search nouns rather than literal casual wording when building target_objects and primary_search_queries.
- When the request is searchable, produce 2 to 4 concise atomic primary_search_queries that preserve the same target from different search angles.
- Each primary_search_query must contain one place-search intent, not a list, not an explanation, and not a full natural-language sentence.
- If the user has a specific target, keep that target in the queries; do not replace it with a broad category.
- Do not put latitude/longitude, coordinate strings, "near 35.x,129.x", or radius text inside search queries.
- Put explicit location names only in anchor_location; current coordinates are supplied separately.

Schema:
{
  "action": "search | ask_clarification | out_of_scope | blocked",
  "normalized_query": "",
  "frame": {
    "location_mode": "explicit | current_context | clarification_required",
    "anchor_location": "",
    "target_objects": [],
    "candidate_place_types": [],
    "result_match_terms": [],
    "constraints": [],
    "exclusions": [],
    "ranking_policy": "evidence_first | urgent_nearest | cost_sensitive | distance_first",
    "primary_search_queries": [],
    "secondary_search_queries": []
  },
  "clarification": {
    "question": "",
    "options": [],
    "missing_fields": [],
    "expected_patch_fields": []
  },
  "confidence": 0.0
}

Validation expectations:
- search requires non-empty frame.target_objects and non-empty frame.primary_search_queries.
- explicit location_mode requires frame.anchor_location.
- ask_clarification requires clarification.question.
- out_of_scope and blocked must not include search queries.
""".strip()


AI_INTENT_REPAIR_SYSTEM_PROMPT = """
You repair one invalid AI Intent Planner JSON response.

Return only one valid JSON object that follows the schema exactly.
Do not add keyword-rule defaults. Do not invent place facts.
If the original answer cannot be repaired into a valid search frame, choose ask_clarification,
out_of_scope, or blocked as appropriate.
""".strip()


AI_QUERY_REPAIR_SYSTEM_PROMPT = """
You repair or expand search queries for an already valid place intent frame.

Return only JSON:
{"queries": [{"query": "", "relationship": "", "preserves_target": true}]}

Rules:
- Preserve the current target_objects and result_match_terms.
- Semantic expansions are allowed when they preserve the user's specific target.
- Do not replace a specific target with a generic category.
- Do not invent real place facts.
- Return at most 3 concise Korean search queries.
- Do not include latitude/longitude or radius text in the query string.
- Set preserves_target=false when the query only broadens to a generic category.
- Each query must be one atomic place-search keyword, not a list or explanatory sentence.
""".strip()


QUERY_LIST_SEPARATOR_RE = re.compile(r"[,/;|]|(?:\s+or\s+)|(?:\s+and\s+)", re.IGNORECASE)


def _clean_text(value, max_length=240):
    text = str(value or "").strip()
    if max_length and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _compact(value):
    return _clean_text(value, max_length=300).lower().replace(" ", "")


def _as_list(value, max_items=12, max_length=80):
    if value in (None, ""):
        return []
    if isinstance(value, (str, int, float, bool)):
        value = [value]
    if not isinstance(value, list):
        return []

    result = []
    seen = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("value") or item.get("text") or item.get("label")
        text = _clean_text(item, max_length=max_length)
        key = _compact(text)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def _to_float(value, default=0.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(parsed, 1.0))


def _has_coordinates(lat=None, lng=None, map_center=None):
    if lat not in (None, "") and lng not in (None, ""):
        return True
    if isinstance(map_center, dict):
        return map_center.get("lat") not in (None, "") and map_center.get("lng") not in (None, "")
    return False


def _broad_frame_terms():
    return {
        "place",
        "places",
        "somewhere",
        "recommendation",
        "spot",
        "place to go",
        "things to do",
        "\uc7a5\uc18c",
        "\ucd94\ucc9c\uc7a5\uc18c",
        "\uac08\ub9cc\ud55c\uacf3",
        "\uac08\ub9cc\ud55c\ub370",
        "\uac00\ubcfc\ub9cc\ud55c\uacf3",
        "\uc5b4\ub514",
        "\uc5b4\ub518\uac00",
        "\uacf3",
        "\uacf5\uac04",
        "장소",
        "추천장소",
        "어디",
        "어딘가",
        "갈만한곳",
        "갈만한데",
        "곳",
        "공간",
    }


def _is_broad_term(value):
    compact = _compact(value)
    if not compact:
        return False
    broad = {_compact(item) for item in _broad_frame_terms()}
    if compact in broad:
        return True
    return any(item and len(item) >= 4 and item in compact for item in broad)


def _normalize_frame(raw_frame):
    raw_frame = raw_frame if isinstance(raw_frame, dict) else {}
    ranking_policy = _clean_text(raw_frame.get("ranking_policy") or raw_frame.get("rankingPolicy"))
    if ranking_policy not in ALLOWED_RANKING_POLICIES:
        ranking_policy = "evidence_first"

    location_mode = _clean_text(raw_frame.get("location_mode") or raw_frame.get("locationMode"))
    if location_mode not in {"explicit", "current_context", "clarification_required"}:
        location_mode = "current_context"

    return {
        "location_mode": location_mode,
        "anchor_location": _clean_text(raw_frame.get("anchor_location") or raw_frame.get("anchorLocation"), 80),
        "target_objects": _as_list(raw_frame.get("target_objects") or raw_frame.get("targetObjects")),
        "candidate_place_types": _as_list(
            raw_frame.get("candidate_place_types") or raw_frame.get("candidatePlaceTypes")
        ),
        "result_match_terms": _as_list(
            raw_frame.get("result_match_terms") or raw_frame.get("resultMatchTerms")
        ),
        "constraints": _as_list(raw_frame.get("constraints")),
        "exclusions": _as_list(raw_frame.get("exclusions")),
        "ranking_policy": ranking_policy,
        "primary_search_queries": _as_list(
            raw_frame.get("primary_search_queries")
            or raw_frame.get("primarySearchQueries")
            or raw_frame.get("search_queries")
            or raw_frame.get("searchQueries"),
            max_items=6,
            max_length=100,
        ),
        "secondary_search_queries": _as_list(
            raw_frame.get("secondary_search_queries") or raw_frame.get("secondarySearchQueries"),
            max_items=6,
            max_length=100,
        ),
    }


def _normalize_clarification(raw):
    raw = raw if isinstance(raw, dict) else {}
    return {
        "question": _clean_text(raw.get("question") or raw.get("clarification_question"), 300),
        "options": _as_list(raw.get("options") or raw.get("clarification_options"), max_items=5, max_length=80),
        "missing_fields": _as_list(raw.get("missing_fields") or raw.get("missingFields"), max_items=8),
        "expected_patch_fields": _as_list(
            raw.get("expected_patch_fields") or raw.get("expectedPatchFields"),
            max_items=8,
        ),
    }


def _is_raw_repeat_only(raw_query, frame):
    query_compact = _compact(raw_query)
    primary = frame.get("primary_search_queries") or []
    if not query_compact or len(primary) != 1:
        return False
    if _compact(primary[0]) != query_compact:
        return False
    evidence_terms = [
        *frame.get("target_objects", []),
        *frame.get("result_match_terms", []),
        *frame.get("candidate_place_types", []),
    ]
    return not any(_compact(term) and _compact(term) != query_compact for term in evidence_terms)


def _clarification_requests_place_target(clarification):
    text = _compact(" ".join([
        clarification.get("question", ""),
        *clarification.get("options", []),
        *clarification.get("missing_fields", []),
        *clarification.get("expected_patch_fields", []),
    ]))
    place_target_markers = {
        "target_objects",
        "targetobjects",
        "result_match_terms",
        "resultmatchterms",
        "candidate_place_types",
        "candidateplacetypes",
        "user_goal",
        "usergoal",
        "place",
        "destination",
        "\uc7a5\uc18c",
        "\ubaa9\uc801",
    }
    return any(_compact(marker) in text for marker in place_target_markers)


def _validate_plan(plan, raw_query="", lat=None, lng=None, map_center=None):
    errors = []
    action = plan.get("action")
    frame = plan.get("frame") if isinstance(plan.get("frame"), dict) else {}
    clarification = plan.get("clarification") if isinstance(plan.get("clarification"), dict) else {}

    if action not in ALLOWED_ACTIONS:
        errors.append("invalid_action")
        return errors

    if action == "search":
        if not frame.get("target_objects"):
            errors.append("missing_target_objects")
        if not frame.get("primary_search_queries"):
            errors.append("missing_primary_search_queries")
        if frame.get("location_mode") == "explicit" and not frame.get("anchor_location"):
            errors.append("missing_anchor_location")
        if frame.get("location_mode") == "clarification_required":
            errors.append("search_requires_location_clarification")
        if _is_raw_repeat_only(raw_query, frame):
            errors.append("raw_query_repeat_only")
        if all(_is_broad_term(term) for term in frame.get("target_objects", [])):
            errors.append("broad_target_only")

    if action == "ask_clarification" and not clarification.get("question"):
        errors.append("missing_clarification_question")
    if action == "ask_clarification":
        frame_terms = [
            *frame.get("target_objects", []),
            *frame.get("result_match_terms", []),
            *frame.get("candidate_place_types", []),
        ]
        if not frame_terms and not _clarification_requests_place_target(clarification):
            errors.append("non_place_clarification")

    if action in {"out_of_scope", "blocked"}:
        if frame.get("primary_search_queries") or frame.get("secondary_search_queries"):
            errors.append("non_search_action_contains_queries")

    if action == "search" and frame.get("location_mode") == "current_context":
        plan["has_current_coordinates"] = _has_coordinates(lat=lat, lng=lng, map_center=map_center)

    return errors


def _canonicalize(raw_plan, raw_query="", lat=None, lng=None, map_center=None):
    raw_plan = raw_plan if isinstance(raw_plan, dict) else {}
    frame = _normalize_frame(raw_plan.get("frame") or raw_plan.get("place_intent_frame") or {})
    clarification = _normalize_clarification(raw_plan.get("clarification") or raw_plan)
    action = _clean_text(raw_plan.get("action") or raw_plan.get("decision_action"))
    plan = {
        "action": action,
        "normalized_query": _clean_text(raw_plan.get("normalized_query") or raw_plan.get("normalizedQuery") or raw_query),
        "frame": frame,
        "clarification": clarification,
        "confidence": _to_float(raw_plan.get("confidence"), 0.0),
    }
    errors = _validate_plan(plan, raw_query=raw_query, lat=lat, lng=lng, map_center=map_center)
    return plan, errors


def _planner_payload(query, lat=None, lng=None, map_center=None, previous_context=None):
    previous_context = previous_context if isinstance(previous_context, dict) else {}
    return {
        "query": query,
        "current_coordinates": {
            "lat": lat,
            "lng": lng,
        },
        "map_center": map_center if isinstance(map_center, dict) else None,
        "previous_frame": previous_context.get("pending_clarification_frame")
        or previous_context.get("place_intent_frame")
        or previous_context.get("search_plan", {}).get("place_intent_frame")
        or previous_context.get("search_plan", {}).get("placeIntentFrame")
        or {},
        "pending_clarification_question": previous_context.get("clarification_question")
        or previous_context.get("question")
        or "",
        "clarification_answer": previous_context.get("clarification_answer") or "",
        "previous_user_query": previous_context.get("previous_user_query") or previous_context.get("original_query") or "",
        "last_resolved_location_context": previous_context.get("last_resolved_location_context") or {},
        "is_clarification_followup": bool(previous_context.get("is_clarification_followup")),
    }


def _is_ai_enabled():
    if getattr(settings, "CONVERSATIONAL_SEARCH_AI_ENABLED", False) is not True:
        return False, "conversational_search_ai_disabled"
    if not getattr(settings, "GMS_API_KEY", ""):
        return False, "missing_gms_api_key"
    if not (getattr(settings, "GMS_API_URL", "") or getattr(settings, "GMS_API_BASE_URL", "")):
        return False, "missing_gms_api_url"
    return True, ""


def _call_planner(payload, *, repair=False, max_completion_tokens=900):
    prompt = AI_INTENT_REPAIR_SYSTEM_PROMPT if repair else AI_INTENT_SYSTEM_PROMPT
    return _call_gms_chat_json(
        query=json.dumps(payload, ensure_ascii=False),
        system_prompt=prompt,
        max_completion_tokens=max_completion_tokens,
        model=getattr(settings, "AI_INTENT_MODEL", getattr(settings, "GMS_MODEL", "gpt-5-mini")),
        timeout=getattr(settings, "AI_INTENT_TIMEOUT", getattr(settings, "AI_REQUEST_TIMEOUT", 20)),
    )


def _is_retryable_ai_error(exc):
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return bool(status_code and 500 <= status_code < 600)


def _unavailable(reason, retry_count=0, validation_errors=None, call_count=0):
    return {
        "action": "ai_unavailable",
        "decision_action": "ai_unavailable",
        "can_search_now": False,
        "normalized_query": "",
        "frame": {},
        "clarification": {},
        "confidence": 0.0,
        "ai_retry_count": retry_count,
        "validation_errors": validation_errors or [],
        "ai_fallback_reason": reason,
        "ai_debug": {
            "planner": {
                "status": "unavailable",
                "reason": reason,
                "validation_errors": validation_errors or [],
                "retry_count": retry_count,
                "call_count": call_count,
            }
        },
    }


def build_ai_intent_plan(query, *, lat=None, lng=None, map_center=None, previous_context=None):
    raw_query = _clean_text(query, 500)
    if not raw_query:
        return {
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "can_search_now": False,
            "normalized_query": "",
            "frame": {},
            "clarification": {
                "question": "찾고 싶은 장소 상황을 조금 더 알려주세요.",
                "options": [],
                "missing_fields": ["user_goal"],
                "expected_patch_fields": ["target_objects"],
            },
            "confidence": 0.0,
            "ai_retry_count": 0,
            "ai_debug": {"planner": {"status": "empty_query"}},
        }

    enabled, reason = _is_ai_enabled()
    if not enabled:
        return _unavailable(reason)

    payload = _planner_payload(
        raw_query,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )

    try:
        max_attempts = int(getattr(settings, "AI_SEARCH_INTENT_MAX_ATTEMPTS", 2) or 2)
    except (TypeError, ValueError):
        max_attempts = 2
    max_attempts = max(1, min(max_attempts, 3))

    raw_plan = None
    last_error = ""
    retry_count = 0
    ai_call_count = 0
    for attempt_index in range(max_attempts + 1):
        try:
            ai_call_count += 1
            raw_plan = _call_planner(payload)
            retry_count = attempt_index
            break
        except Exception as exc:
            logger.info("AI intent planner call failed.", exc_info=True)
            last_error = f"ai_call_failed:{exc.__class__.__name__}"
            retry_count = attempt_index + 1
            if not _is_retryable_ai_error(exc) or attempt_index >= max_attempts:
                break

    if not isinstance(raw_plan, dict):
        if last_error:
            return _unavailable(last_error, retry_count=retry_count, call_count=ai_call_count)
        return _unavailable("empty_ai_response", retry_count=retry_count, call_count=ai_call_count)

    plan, errors = _canonicalize(raw_plan, raw_query=raw_query, lat=lat, lng=lng, map_center=map_center)
    if not errors:
        return {
            **plan,
            "decision_action": plan["action"],
            "can_search_now": plan["action"] == "search",
            "ai_retry_count": retry_count,
            "ai_debug": {
                "planner": {
                    "status": "ok",
                    "retry_count": retry_count,
                    "call_count": ai_call_count,
                    "validation_errors": [],
                }
            },
        }

    repair_payload = {
        "original_payload": payload,
        "invalid_response": raw_plan,
        "validation_errors": errors,
    }
    try:
        ai_call_count += 1
        repaired_raw = _call_planner(repair_payload, repair=True, max_completion_tokens=700)
    except Exception as exc:
        logger.info("AI intent planner repair failed.", exc_info=True)
        return _unavailable(
            f"ai_schema_repair_failed:{exc.__class__.__name__}",
            retry_count=retry_count,
            validation_errors=errors,
            call_count=ai_call_count,
        )

    repaired_plan, repair_errors = _canonicalize(
        repaired_raw,
        raw_query=raw_query,
        lat=lat,
        lng=lng,
        map_center=map_center,
    )
    if repair_errors:
        return _unavailable(
            "ai_schema_repair_invalid",
            retry_count=retry_count,
            validation_errors=[*errors, *repair_errors],
            call_count=ai_call_count,
        )

    return {
        **repaired_plan,
        "decision_action": repaired_plan["action"],
        "can_search_now": repaired_plan["action"] == "search",
        "ai_retry_count": retry_count,
        "ai_debug": {
            "planner": {
                "status": "repaired",
                "retry_count": retry_count,
                "call_count": ai_call_count,
                "validation_errors": errors,
            }
        },
    }


def frame_with_sources(frame, source=TRUSTED_FRAME_SOURCE):
    frame = frame if isinstance(frame, dict) else {}

    def sourced(values):
        return [
            {
                "value": value,
                "source": source,
                "evidence_source": source,
            }
            for value in values or []
        ]

    return {
        **frame,
        "target_objects": sourced(frame.get("target_objects")),
        "targetObjects": sourced(frame.get("target_objects")),
        "candidate_place_types": sourced(frame.get("candidate_place_types")),
        "candidatePlaceTypes": sourced(frame.get("candidate_place_types")),
        "result_match_terms": sourced(frame.get("result_match_terms")),
        "resultMatchTerms": sourced(frame.get("result_match_terms")),
        "constraints": sourced(frame.get("constraints")),
        "exclusions": sourced(frame.get("exclusions")),
        "search_queries": sourced(frame.get("primary_search_queries")),
        "searchQueries": sourced(frame.get("primary_search_queries")),
        "primary_search_queries": sourced(frame.get("primary_search_queries")),
        "primarySearchQueries": sourced(frame.get("primary_search_queries")),
        "secondary_search_queries": sourced(frame.get("secondary_search_queries")),
        "secondarySearchQueries": sourced(frame.get("secondary_search_queries")),
    }


def to_search_plan(intent_plan, raw_query=""):
    frame = intent_plan.get("frame") if isinstance(intent_plan.get("frame"), dict) else {}
    sourced_frame = frame_with_sources(frame)
    action = intent_plan.get("action") or intent_plan.get("decision_action") or ""
    display_label = (
        (frame.get("target_objects") or [""])[0]
        or intent_plan.get("normalized_query")
        or raw_query
    )
    search_plan = {
        "originalQuery": raw_query,
        "original_query": raw_query,
        "normalizedQuery": intent_plan.get("normalized_query") or raw_query,
        "normalized_query": intent_plan.get("normalized_query") or raw_query,
        "targetQuery": display_label,
        "target_query": display_label,
        "locationQuery": frame.get("anchor_location") if frame.get("location_mode") == "explicit" else "",
        "location_query": frame.get("anchor_location") if frame.get("location_mode") == "explicit" else "",
        "baseLocationQuery": frame.get("anchor_location") if frame.get("location_mode") == "explicit" else "",
        "base_location_query": frame.get("anchor_location") if frame.get("location_mode") == "explicit" else "",
        "has_explicit_location": frame.get("location_mode") == "explicit",
        "location_resolution_required": frame.get("location_mode") == "explicit",
        "scenario": "ai_place_search",
        "decision_action": action,
        "decisionAction": action,
        "can_search_now": action == "search",
        "canSearchNow": action == "search",
        "parser_provider": "ai_intent_planner",
        "parser_fallback": False,
        "plan_source": "ai",
        "execution_mode": "ai_first_orchestrator",
        "ranking_policy": frame.get("ranking_policy") or "evidence_first",
        "rankingPolicy": frame.get("ranking_policy") or "evidence_first",
        "place_intent_frame": sourced_frame,
        "placeIntentFrame": sourced_frame,
        "target_objects": sourced_frame.get("target_objects", []),
        "candidate_place_types": sourced_frame.get("candidate_place_types", []),
        "result_match_terms": sourced_frame.get("result_match_terms", []),
        "constraints": sourced_frame.get("constraints", []),
        "exclusions": sourced_frame.get("exclusions", []),
        "search_queries": sourced_frame.get("search_queries", []),
        "searchQueries": sourced_frame.get("searchQueries", []),
        "primary_search_queries": sourced_frame.get("primary_search_queries", []),
        "secondary_search_queries": sourced_frame.get("secondary_search_queries", []),
        "ai_retry_count": intent_plan.get("ai_retry_count", 0),
    }
    clarification = intent_plan.get("clarification") if isinstance(intent_plan.get("clarification"), dict) else {}
    if action == "ask_clarification":
        search_plan["clarification_question"] = clarification.get("question", "")
        search_plan["clarification_options"] = clarification.get("options", [])
    return search_plan


def repair_search_queries(query, frame, *, candidate_counts=None):
    enabled, reason = _is_ai_enabled()
    if not enabled:
        return [], {"status": "skipped", "reason": reason}
    payload = {
        "query": query,
        "frame": frame,
        "candidate_counts": candidate_counts or {},
    }
    try:
        raw = _call_gms_chat_json(
            query=json.dumps(payload, ensure_ascii=False),
            system_prompt=AI_QUERY_REPAIR_SYSTEM_PROMPT,
            max_completion_tokens=220,
            model=getattr(settings, "AI_QUERY_REPAIR_MODEL", "gpt-5-nano"),
            timeout=getattr(settings, "AI_QUERY_REPAIR_TIMEOUT", getattr(settings, "AI_REQUEST_TIMEOUT", 20)),
        )
    except Exception as exc:
        logger.info("AI query repair failed.", exc_info=True)
        return [], {"status": "failed", "reason": f"ai_query_repair_failed:{exc.__class__.__name__}"}

    raw_queries = (raw or {}).get("queries") if isinstance(raw, dict) else []
    raw_queries = raw_queries if isinstance(raw_queries, list) else []
    filtered = []
    blocked = []
    generated = []
    blocked_relationships = {
        "generic_category_replacement",
        "generic_category",
        "broad_category",
        "broad_default",
        "unsupported",
        "unrelated",
    }

    def is_atomic_query(value):
        text = _clean_text(value, 100)
        if not text or len(text) > 28:
            return False, "query_too_long_or_empty"
        if QUERY_LIST_SEPARATOR_RE.search(text):
            return False, "multi_candidate_separator"
        compact_text = _compact(text)
        if "또는" in compact_text or "혹은" in compact_text or "그리고" in compact_text:
            return False, "multi_candidate_conjunction"
        if any(mark in text for mark in (":", "：", "(", ")", "[", "]")):
            return False, "explanatory_query"
        if len(text.split()) > 5:
            return False, "explanatory_query"
        return True, ""

    for item in raw_queries[:3]:
        if not isinstance(item, dict):
            blocked.append({
                "query": _clean_text(item, 100),
                "relationship": "missing_structured_contract",
                "preserves_target": False,
            })
            continue
        query_text = _clean_text(item.get("query"), 100)
        relationship = _clean_text(item.get("relationship"), 80).lower()
        preserves_target = item.get("preserves_target")
        if isinstance(preserves_target, str):
            preserves_target = preserves_target.strip().lower() in {"1", "true", "yes"}
        else:
            preserves_target = bool(preserves_target)
        row = {
            "query": query_text,
            "relationship": relationship,
            "preserves_target": preserves_target,
        }
        generated.append(row)
        is_atomic, atomic_reason = is_atomic_query(query_text)
        if not query_text or not preserves_target or relationship in blocked_relationships or not is_atomic:
            blocked.append({**row, "blocked_reason": atomic_reason or relationship or "does_not_preserve_target"})
            continue
        filtered.append(query_text)
    return filtered, {
        "status": "executed",
        "generated": generated,
        "accepted": filtered,
        "blocked": blocked,
        "call_count": 1,
    }
