import json
import logging
import re
import time
from copy import deepcopy
from hashlib import sha256

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

AI_WEB_SEARCH_MIN_DB_RESULTS = 3
AI_WEB_SEARCH_MIN_TOTAL_RESULTS = 5
AI_WEB_SEARCH_MAX_SOURCES_PER_CANDIDATE = 1
AI_WEB_SEARCH_CACHE_TTL_SECONDS = 600
AI_WEB_SEARCH_CACHE_MAX_SIZE = 100
_AI_WEB_SEARCH_CACHE = {}


def clear_ai_web_search_cache():
    _AI_WEB_SEARCH_CACHE.clear()


DETAIL_CONDITION_KEYWORDS = {
    "메뉴",
    "브런치",
    "혼밥",
    "혼자",
    "조용",
    "분위기",
    "노트북",
    "콘센트",
    "와이파이",
    "주차",
    "아이",
    "반려동물",
    "비건",
    "목적",
    "데이트",
    "추천",
    "좋은",
}

AI_SEARCH_CANDIDATE_METADATA = {
    "source_type": "ai_search_candidate",
    "source_label": "AI 웹 검색 후보",
    "confidence": "low",
    "confidence_label": "낮은 신뢰도",
    "fallback_level": 6,
    "fallback_label": "AI 웹 검색 기반 후보",
    "fallback_description": "DB 추천 결과가 부족하거나 세부 조건 검증이 약해 AI 웹 검색 결과를 참고한 후보입니다.",
    "caution_message": "AI 웹 검색 기반 후보이므로 위치, 운영 여부, 메뉴, 분위기는 방문 전 카카오 상세 정보나 공식 정보를 확인해 주세요.",
}


def _get_max_candidates():
    try:
        value = int(getattr(settings, "AI_WEB_SEARCH_MAX_CANDIDATES", 1))
    except (TypeError, ValueError):
        value = 1
    return min(max(value, 1), 1)


def _get_max_output_tokens():
    try:
        value = int(getattr(settings, "AI_WEB_SEARCH_MAX_OUTPUT_TOKENS", 800))
    except (TypeError, ValueError):
        value = 800
    return min(max(value, 200), 800)


def _get_gms_responses_url():
    explicit_base_url = _safe_text(getattr(settings, "GMS_API_BASE_URL", ""), 500)
    raw_api_url = _safe_text(getattr(settings, "GMS_API_URL", ""), 500)
    base_url = explicit_base_url

    if not base_url and raw_api_url:
        base_url = raw_api_url.split("/api.openai.com/", 1)[0]

    base_url = (base_url or "https://gms.ssafy.io/gmsapi").rstrip("/")
    responses_path = _safe_text(
        getattr(settings, "GMS_OPENAI_RESPONSES_PATH", "api.openai.com/v1/responses"),
        200,
    ).strip("/")
    return f"{base_url}/{responses_path}"


def _log_safe_result(executed=False, candidates_count=0, error="", model="", max_output_tokens=None):
    logger.info(
        "AI web search result executed=%s candidates=%s error=%s model=%s max_output_tokens=%s",
        executed,
        candidates_count,
        error,
        model,
        max_output_tokens,
    )


def _base_response(enabled=None, executed=False, candidates=None, error="", reason=""):
    if enabled is None:
        enabled = bool(getattr(settings, "AI_WEB_SEARCH_AVAILABLE", False))

    return {
        "enabled": enabled,
        "executed": executed,
        "supported": bool(getattr(settings, "AI_WEB_SEARCH_GROUNDING_SUPPORTED", False)),
        "provider": getattr(settings, "AI_WEB_SEARCH_PROVIDER", "gms"),
        "candidates": candidates or [],
        "error": error,
        "reason": reason,
    }


def _sanitize_error_message(message, max_length=300):
    text = _safe_text(message, max_length=2000)
    if not text:
        return ""

    api_key = _safe_text(getattr(settings, "GMS_API_KEY", ""), 500)
    if api_key:
        text = text.replace(api_key, "[redacted]")

    text = re.sub(r"(?i)authorization\s*:\s*bearer\s+[^\s,]+", "authorization: bearer [redacted]", text)
    text = re.sub(r"(?i)bearer\s+[a-z0-9._\-]+", "bearer [redacted]", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text[:max_length]


def _error_type_from_status(status_code):
    if status_code == 400:
        return "bad_request"
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not_found"
    if status_code == 429:
        return "rate_limited"
    if status_code and status_code >= 500:
        return "server_error"
    if status_code:
        return "http_error"
    return "network_error"


def _extract_response_error_message(response):
    if response is None:
        return ""

    try:
        data = response.json()
    except ValueError:
        return _sanitize_error_message(getattr(response, "text", ""))

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return _sanitize_error_message(
                error.get("message")
                or error.get("code")
                or error.get("type")
                or json.dumps(error, ensure_ascii=False)
            )
        if isinstance(error, str):
            return _sanitize_error_message(error)
        return _sanitize_error_message(
            data.get("message")
            or data.get("detail")
            or data.get("code")
            or json.dumps(data, ensure_ascii=False)
        )

    return _sanitize_error_message(data)


def _build_request_error_detail(error):
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    error_type = _error_type_from_status(status_code)

    if isinstance(error, requests.Timeout):
        error_type = "timeout"

    message = _extract_response_error_message(response) or _sanitize_error_message(str(error))
    detail = {
        "type": error_type,
        "message": message,
    }
    if status_code:
        detail["status_code"] = status_code
    return detail


def get_ai_web_search_status(reason="manual_required"):
    return _base_response(
        enabled=bool(getattr(settings, "AI_WEB_SEARCH_AVAILABLE", False)),
        executed=False,
        reason=reason,
    )


def _safe_text(value, max_length=240):
    if value is None:
        return ""
    return str(value).strip()[:max_length]


def _safe_list(values, max_items=8, max_length=80):
    if isinstance(values, str):
        values = [values]

    if not isinstance(values, (list, tuple)):
        return []

    cleaned = []
    for value in values:
        text = _safe_text(value, max_length=max_length)
        if text:
            cleaned.append(text)

    return list(dict.fromkeys(cleaned))[:max_items]


def _safe_float(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_detail_conditions(query, condition):
    haystack = " ".join(
        [
            _safe_text(query, 500),
            _safe_text((condition or {}).get("intent"), 500),
            _safe_text((condition or {}).get("keyword"), 500),
            " ".join(_safe_list((condition or {}).get("keywords"), max_items=20)),
            " ".join(_safe_list((condition or {}).get("required_tags"), max_items=20)),
            " ".join(_safe_list((condition or {}).get("preferred_tags"), max_items=20)),
        ]
    )
    return any(keyword in haystack for keyword in DETAIL_CONDITION_KEYWORDS)


def should_execute_ai_web_search(query, condition=None, existing_results_summary=None):
    summary = existing_results_summary or {}
    db_count = int(summary.get("db_count") or 0)
    kakao_fallback_count = int(summary.get("kakao_fallback_count") or 0)
    total_count = int(summary.get("total_count") or db_count + kakao_fallback_count)
    weak_match_count = int(summary.get("weak_match_count") or 0)
    has_detail_conditions = _has_detail_conditions(query, condition or {})
    db_results_are_weak = db_count == 0 or weak_match_count >= db_count

    return (
        db_count < AI_WEB_SEARCH_MIN_DB_RESULTS
        and kakao_fallback_count < AI_WEB_SEARCH_MIN_DB_RESULTS
        and total_count < AI_WEB_SEARCH_MIN_TOTAL_RESULTS
        and db_results_are_weak
        and has_detail_conditions
    )


def summarize_existing_results(results, kakao_fallback_count=0):
    results = results or []
    weak_match_count = 0

    for result in results:
        matched_tags = result.get("matched_tags") or result.get("matched_tag_labels") or []
        match_level = result.get("match_level") or ""
        source_type = result.get("source_type") or ""

        if (
            not matched_tags
            or match_level == "category_distance_fallback"
            or source_type == "db_category_fallback"
        ):
            weak_match_count += 1

    db_count = len(results)
    return {
        "db_count": db_count,
        "kakao_fallback_count": int(kakao_fallback_count or 0),
        "total_count": db_count + int(kakao_fallback_count or 0),
        "weak_match_count": weak_match_count,
    }


def _build_system_prompt():
    return (
        "Use web_search to find only one real local place related to the user request. "
        "Return JSON only. If there is no source URL, return {\"candidates\":[]}. "
        "Do not invent coordinates, business hours, menu availability, quietness, or atmosphere. "
        "Keep evidence_summary one short sentence."
    )


def _build_user_prompt(query, lat, lng, condition, existing_results_summary):
    prompt_data = {
        "query": _safe_text(query, 220),
        "location_hint": {"lat": lat, "lng": lng},
        "categories": _safe_list((condition or {}).get("categories"), max_items=3),
        "keywords": _safe_list((condition or {}).get("keywords"), max_items=5),
        "instruction": "Use at most 1-2 search queries. Return one candidate max. source_url is required.",
        "json_shape": {
            "candidates": [
                {
                    "name": "",
                    "category_hint": "",
                    "address_hint": "",
                    "evidence_summary": "",
                    "source_url": "",
                }
            ],
        },
    }
    return json.dumps(prompt_data, ensure_ascii=False)


def _extract_json_object(value):
    if isinstance(value, dict):
        return value

    if not isinstance(value, str):
        return {}

    stripped = value.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.replace("json\n", "", 1).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or start >= end:
            return {}

        try:
            return json.loads(stripped[start:end + 1])
        except json.JSONDecodeError:
            return {}


def _parse_gms_response(data):
    output_text = data.get("output_text")
    if output_text:
        parsed = _extract_json_object(output_text)
        if parsed:
            return parsed

    output = data.get("output") or []
    if isinstance(output, list):
        texts = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue

            for content in item.get("content") or []:
                if not isinstance(content, dict):
                    continue

                if content.get("type") in {"output_text", "text"}:
                    texts.append(content.get("text") or "")

        if texts:
            parsed = _extract_json_object("\n".join(texts))
            if parsed:
                return parsed

    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        parsed = _extract_json_object(content)
        if parsed:
            return parsed

    return _extract_json_object(
        data.get("parsed")
        or data.get("result")
        or data.get("output")
        or data
    )


def _is_incomplete_response(data):
    if not isinstance(data, dict):
        return False

    return bool(data.get("incomplete_details")) or data.get("status") == "incomplete"


def _normalize_sources(sources):
    normalized = []

    if not isinstance(sources, (list, tuple)):
        return normalized

    for source in sources:
        if not isinstance(source, dict):
            continue

        url = _safe_text(source.get("url"), 500)
        if not url.startswith(("http://", "https://")):
            continue

        title = _safe_text(source.get("title") or url, 120)
        normalized.append({
            "title": title,
            "url": url,
        })

    return normalized[:AI_WEB_SEARCH_MAX_SOURCES_PER_CANDIDATE]


def _normalize_source_url(source_url):
    url = _safe_text(source_url, 500)
    if not url.startswith(("http://", "https://")):
        return []

    return [{
        "title": "web search source",
        "url": url,
    }]


def _one_sentence_text(value, max_length=180):
    text = " ".join(_safe_text(value, max_length=max_length).split())
    if not text:
        return ""

    indexes = []
    for ending in (".", "!", "?"):
        index = text.find(ending)
        if index != -1:
            indexes.append(index)

    if indexes:
        return text[:min(indexes) + 1].strip()

    return text


def _normalize_candidates(raw_candidates):
    if not isinstance(raw_candidates, (list, tuple)):
        return []

    candidates = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            continue

        name = _safe_text(raw_candidate.get("name"), 120)
        if not name:
            continue

        evidence_sources = _normalize_source_url(raw_candidate.get("source_url"))
        if not evidence_sources:
            continue

        evidence_summary = (
            _one_sentence_text(raw_candidate.get("evidence_summary"), 180)
            or "웹 검색 결과에서 사용자의 조건과 관련된 후보로 확인되었습니다."
        )
        recommendation_reason = (
            f"{evidence_summary} 세부 정보는 방문 전 확인이 필요합니다."
        )

        candidates.append({
            "name": name,
            "address_hint": _safe_text(raw_candidate.get("address_hint"), 160),
            "category_hint": _safe_text(raw_candidate.get("category_hint"), 80),
            "matched_conditions": [],
            "evidence_summary": evidence_summary,
            "evidence_sources": evidence_sources,
            "ai_evidence_summary": evidence_summary,
            "ai_evidence_sources": evidence_sources,
            "confidence": "low",
            "recommendation_reason": recommendation_reason,
            "recommend_reason": recommendation_reason,
            "score": 45,
            "is_verified": False,
            **AI_SEARCH_CANDIDATE_METADATA,
        })

    return candidates[:_get_max_candidates()]


def _build_cache_key(query, lat, lng, condition, existing_results_summary, manual=False):
    cache_payload = {
        "query": _safe_text(query, 500),
        "lat": _safe_text(lat, 32),
        "lng": _safe_text(lng, 32),
        "condition": condition or {},
        "existing_results_summary": existing_results_summary or {},
        "model": getattr(settings, "AI_WEB_SEARCH_MODEL", "gpt-5-nano"),
        "manual": bool(manual),
        "max_output_tokens": _get_max_output_tokens(),
        "max_candidates": _get_max_candidates(),
    }
    raw_key = json.dumps(cache_payload, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(raw_key.encode("utf-8")).hexdigest()


def _get_cached_response(cache_key):
    cached = _AI_WEB_SEARCH_CACHE.get(cache_key)
    if not cached:
        return None

    created_at, response = cached
    if time.time() - created_at > AI_WEB_SEARCH_CACHE_TTL_SECONDS:
        _AI_WEB_SEARCH_CACHE.pop(cache_key, None)
        return None

    cached_response = deepcopy(response)
    cached_response["cached"] = True
    cached_response["executed"] = False
    cached_response["reason"] = "cached_result"
    return cached_response


def _set_cached_response(cache_key, response):
    if len(_AI_WEB_SEARCH_CACHE) >= AI_WEB_SEARCH_CACHE_MAX_SIZE:
        oldest_key = min(
            _AI_WEB_SEARCH_CACHE,
            key=lambda key: _AI_WEB_SEARCH_CACHE[key][0],
        )
        _AI_WEB_SEARCH_CACHE.pop(oldest_key, None)

    _AI_WEB_SEARCH_CACHE[cache_key] = (time.time(), deepcopy(response))


def get_ai_web_search_result(
    query,
    lat=None,
    lng=None,
    condition=None,
    existing_results_summary=None,
    manual=False,
):
    provider = getattr(settings, "AI_WEB_SEARCH_PROVIDER", "gms")

    if not getattr(settings, "AI_WEB_SEARCH_ENABLED", False):
        return _base_response(
            enabled=False,
            reason="disabled",
        )

    if provider != "gms":
        return _base_response(
            enabled=False,
            error="unsupported_provider",
            reason="unsupported_provider",
        )

    if not getattr(settings, "AI_WEB_SEARCH_AVAILABLE", False):
        return _base_response(
            enabled=False,
            error="not_configured",
            reason="missing_api_configuration",
        )

    if not getattr(settings, "AI_WEB_SEARCH_GROUNDING_SUPPORTED", False):
        return _base_response(
            enabled=True,
            error="unsupported_web_search",
            reason="gms_grounding_not_confirmed",
        )

    if not _safe_text(query):
        return _base_response(
            enabled=True,
            error="missing_query",
            reason="missing_query",
        )

    summary = existing_results_summary or {}
    if not manual and not should_execute_ai_web_search(query, condition, summary):
        return _base_response(
            enabled=True,
            reason="enough_existing_results",
        )

    cache_key = _build_cache_key(query, lat, lng, condition or {}, summary, manual=manual)
    cached_response = _get_cached_response(cache_key)
    if cached_response is not None:
        _log_safe_result(
            executed=False,
            candidates_count=len(cached_response.get("candidates") or []),
            error=cached_response.get("error", ""),
            model=getattr(settings, "AI_WEB_SEARCH_MODEL", "gpt-5-nano"),
            max_output_tokens=_get_max_output_tokens(),
        )
        return cached_response

    api_key = getattr(settings, "GMS_API_KEY", "")
    api_url = _get_gms_responses_url()
    lat = _safe_float(lat)
    lng = _safe_float(lng)
    model = getattr(settings, "AI_WEB_SEARCH_MODEL", "gpt-5-nano")
    max_output_tokens = _get_max_output_tokens()

    if not api_key or not api_url:
        return _base_response(
            enabled=False,
            error="not_configured",
            reason="missing_api_configuration",
        )

    payload = {
        "model": model,
        "instructions": _build_system_prompt(),
        "input": _build_user_prompt(query, lat, lng, condition or {}, summary),
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
        "max_output_tokens": max_output_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=getattr(settings, "AI_REQUEST_TIMEOUT", 20),
        )
        response.raise_for_status()
        data = response.json()
        if _is_incomplete_response(data):
            result = _base_response(
                enabled=True,
                executed=True,
                error="incomplete_response",
                reason="incomplete_response",
            )
            _set_cached_response(cache_key, result)
            _log_safe_result(
                executed=True,
                candidates_count=0,
                error=result["error"],
                model=model,
                max_output_tokens=max_output_tokens,
            )
            return result
        parsed = _parse_gms_response(data)
    except requests.RequestException as exc:
        logger.exception("AI web search provider request failed")
        result = _base_response(
            enabled=True,
            executed=False,
            error="api_error",
            reason="request_failed",
        )
        result["error_detail"] = _build_request_error_detail(exc)
        _set_cached_response(cache_key, result)
        _log_safe_result(
            executed=False,
            candidates_count=0,
            error=result["error"],
            model=model,
            max_output_tokens=max_output_tokens,
        )
        return result
    except ValueError:
        logger.exception("AI web search provider returned invalid JSON")
        result = _base_response(
            enabled=True,
            executed=True,
            error="invalid_json",
            reason="response_json_parse_failed",
        )
        _set_cached_response(cache_key, result)
        _log_safe_result(
            executed=True,
            candidates_count=0,
            error=result["error"],
            model=model,
            max_output_tokens=max_output_tokens,
        )
        return result

    candidates = _normalize_candidates(parsed.get("candidates"))

    result = {
        **_base_response(enabled=True, executed=True),
        "candidates": candidates,
        "search_queries": _safe_list(parsed.get("search_queries"), max_items=2),
        "summary": _safe_text(parsed.get("summary"), 160),
        "error": "" if candidates else "empty_candidates",
        "reason": "completed" if candidates else "no_valid_candidates",
    }
    _set_cached_response(cache_key, result)
    _log_safe_result(
        executed=True,
        candidates_count=len(candidates),
        error=result["error"],
        model=model,
        max_output_tokens=max_output_tokens,
    )
    return result
