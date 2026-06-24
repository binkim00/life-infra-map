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
AI_WEB_SEARCH_TEXT_CANDIDATE_MAX_CHARS = 2000
AI_WEB_SEARCH_RETRY_STATUS_CODES = {500, 502, 503, 504}
AI_WEB_SEARCH_MAX_RETRIES = 1
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


def _get_reasoning_effort():
    effort = _safe_text(
        getattr(settings, "AI_WEB_SEARCH_REASONING_EFFORT", ""),
        32,
    ).lower()
    if effort not in {"minimal", "low", "medium", "high"}:
        return ""
    return effort


def _get_reasoning_payload_for_tools(tools):
    requested_effort = _get_reasoning_effort()
    tool_types = {
        tool.get("type")
        for tool in tools or []
        if isinstance(tool, dict)
    }

    if not requested_effort:
        return None, {
            "reasoning_effort_requested": "",
            "reasoning_effort_applied": None,
            "reasoning_effort_skipped_reason": "not_configured",
        }

    if "web_search" in tool_types:
        return None, {
            "reasoning_effort_requested": requested_effort,
            "reasoning_effort_applied": None,
            "reasoning_effort_skipped_reason": "web_search_incompatible",
        }

    return {"effort": requested_effort}, {
        "reasoning_effort_requested": requested_effort,
        "reasoning_effort_applied": requested_effort,
        "reasoning_effort_skipped_reason": "",
    }


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


def _log_safe_request(query="", condition=None, manual=False, existing_results_summary=None):
    condition = condition or {}
    summary = existing_results_summary or {}
    existing_result_count = int(summary.get("relevant_result_count") or summary.get("total_count") or 0)
    if not existing_result_count:
        existing_result_count = int(summary.get("db_count") or 0) + int(
            summary.get("kakao_fallback_count") or 0
        )

    logger.info(
        "[AI_WEB_SEARCH_REQUEST] query=%s scenario=%s menu_keywords=%s "
        "place_type_keywords=%s manual=%s existing_result_count=%s",
        _safe_text(query, 120),
        _safe_text(condition.get("scenario"), 80),
        _safe_list(condition.get("menu_keywords"), max_items=5),
        _safe_list(condition.get("place_type_keywords"), max_items=5),
        bool(manual),
        existing_result_count,
    )


def _log_safe_result(
    executed=False,
    candidates_count=0,
    error="",
    reason="",
    model="",
    max_output_tokens=None,
    has_sources=False,
    has_text=False,
):
    logger.info(
        "[AI_WEB_SEARCH_RESPONSE] executed=%s reason=%s error=%s "
        "candidate_count=%s has_sources=%s has_text=%s model=%s max_output_tokens=%s",
        executed,
        reason,
        error,
        candidates_count,
        bool(has_sources),
        bool(has_text),
        model,
        max_output_tokens,
    )


def _base_response(enabled=None, executed=False, candidates=None, error="", reason=""):
    provider = getattr(settings, "AI_WEB_SEARCH_PROVIDER", "gms")
    if enabled is None:
        enabled = bool(getattr(settings, "AI_WEB_SEARCH_AVAILABLE", False))

    return {
        "enabled": enabled,
        "executed": executed,
        "supported": (
            provider == "naver_search"
            or bool(getattr(settings, "AI_WEB_SEARCH_GROUNDING_SUPPORTED", False))
        ),
        "provider": provider,
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


def _is_web_search_reasoning_incompatible_error(error):
    status_code = _get_response_status_code(error)
    if status_code != 400:
        return False

    message = _extract_response_error_message(getattr(error, "response", None)).lower()
    return (
        "web_search" in message
        and "reasoning.effort" in message
        and "minimal" in message
    )


def _get_response_status_code(error):
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def _is_retryable_server_error(error):
    return _get_response_status_code(error) in AI_WEB_SEARCH_RETRY_STATUS_CODES


def _build_temporary_server_error_detail(status_code):
    return {
        "status_code": status_code,
        "type": "server_error",
        "message": "AI web search server response failed temporarily.",
    }


def _build_request_failed_response(error):
    status_code = _get_response_status_code(error)

    if status_code and status_code >= 500:
        result = _base_response(
            enabled=True,
            executed=True,
            error="temporary_server_error",
            reason="server_error",
        )
        result["error_detail"] = _build_temporary_server_error_detail(status_code)
        return result

    if _is_web_search_reasoning_incompatible_error(error):
        result = _base_response(
            enabled=True,
            executed=True,
            error="api_error",
            reason="invalid_request",
        )
        result["error_detail"] = {
            "status_code": 400,
            "type": "bad_request",
            "message": "web_search cannot be used with reasoning.effort minimal.",
        }
        return result

    result = _base_response(
        enabled=True,
        executed=True,
        error="api_error",
        reason="request_failed",
    )
    result["error_detail"] = _build_request_error_detail(error)
    return result


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
            " ".join(_safe_list((condition or {}).get("menu_keywords"), max_items=20)),
            " ".join(_safe_list((condition or {}).get("place_type_keywords"), max_items=20)),
            " ".join(_safe_list((condition or {}).get("purpose_keywords"), max_items=20)),
            " ".join(_safe_list((condition or {}).get("required_tags"), max_items=20)),
            " ".join(_safe_list((condition or {}).get("preferred_tags"), max_items=20)),
        ]
    )
    return any(keyword in haystack for keyword in DETAIL_CONDITION_KEYWORDS)


def should_execute_ai_web_search(query, condition=None, existing_results_summary=None):
    summary = existing_results_summary or {}
    db_count = int(summary.get("relevant_result_count") or summary.get("db_count") or 0)
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
    relevant_count = sum(
        1
        for result in results
        if int(result.get("relevance_score") or 0) > 0 or result.get("matched_evidence")
    )
    return {
        "db_count": db_count,
        "relevant_result_count": relevant_count or db_count,
        "kakao_fallback_count": int(kakao_fallback_count or 0),
        "total_count": db_count + int(kakao_fallback_count or 0),
        "weak_match_count": weak_match_count,
    }


def _build_system_prompt():
    return (
        "Use web_search. Find at most one real local place for the user request. "
        "Return JSON only: {\"candidates\":[{\"name\":\"place name\",\"source_url\":\"<source_url>\"}]}. "
        "If no source URL is found, return {\"candidates\":[]}. "
        "Do not invent coordinates, hours, menu availability, quietness, or atmosphere."
    )


def _build_user_prompt(query, lat, lng, condition, existing_results_summary):
    condition = condition or {}
    menu_keywords = _safe_list(condition.get("menu_keywords"), max_items=2)
    place_type_keywords = _safe_list(condition.get("place_type_keywords"), max_items=2)

    lines = [
        f'query: "{_safe_text(query, 160)}"',
    ]

    if lat is not None and lng is not None:
        lines.append(f"location_hint: lat={lat:.5f}, lng={lng:.5f}")

    if menu_keywords:
        lines.append(f"menu_keywords: {', '.join(menu_keywords)}")

    if place_type_keywords:
        lines.append(f"place_type_keywords: {', '.join(place_type_keywords)}")

    lines.extend([
        "Find one place mentioned in web search results.",
        'Return JSON only: {"candidates":[{"name":"place name","source_url":"<source_url>"}]}',
        'If no source URL is found, return {"candidates":[]}.',
    ])
    return "\n".join(lines)


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


def _append_source(sources, title="", url=""):
    url = _safe_text(url, 500)
    if not url.startswith(("http://", "https://")):
        return

    title = _safe_text(title or url, 120)
    if any(source["url"] == url for source in sources):
        return

    sources.append({
        "title": title,
        "url": url,
    })


def _extract_sources_from_value(value):
    sources = []

    def visit(item):
        if isinstance(item, dict):
            if item.get("type") in {"url_citation", "citation"} or item.get("url"):
                _append_source(
                    sources,
                    item.get("title") or item.get("name") or item.get("text") or "",
                    item.get("url")
                    or item.get("uri")
                    or item.get("source_url")
                    or item.get("link")
                    or "",
                )

            for key in (
                "sources",
                "citations",
                "references",
                "annotations",
                "evidence_sources",
                "ai_evidence_sources",
                "action",
                "results",
            ):
                nested = item.get(key)
                if nested:
                    visit(nested)

            for key in ("content", "output", "message", "choices"):
                nested = item.get(key)
                if nested:
                    visit(nested)
            return

        if isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return sources[:AI_WEB_SEARCH_MAX_SOURCES_PER_CANDIDATE]


def _extract_queries_from_value(value):
    queries = []

    def add_query(raw_query):
        query = _safe_text(raw_query, 160)
        if query and query not in queries:
            queries.append(query)

    def visit(item):
        if isinstance(item, dict):
            add_query(item.get("query"))

            nested_queries = item.get("queries")
            if isinstance(nested_queries, (list, tuple)):
                for nested_query in nested_queries:
                    if isinstance(nested_query, dict):
                        add_query(nested_query.get("query") or nested_query.get("text"))
                    else:
                        add_query(nested_query)
            elif nested_queries:
                add_query(nested_queries)

            for key in ("action", "output", "content", "message", "choices"):
                nested = item.get(key)
                if nested:
                    visit(nested)
            return

        if isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return queries[:2]


def _safe_debug_keys(value, max_items=12):
    if not isinstance(value, dict):
        return []

    return [_safe_text(key, 80) for key in list(value.keys())[:max_items]]


def _count_debug_items(value):
    counts = {
        "source_count": 0,
        "url_count": 0,
        "annotation_count": 0,
        "url_citation_count": 0,
    }
    urls = set()

    def add_url(raw_url):
        url = _safe_text(raw_url, 500)
        if url.startswith(("http://", "https://")):
            urls.add(url)

    def visit(item):
        if isinstance(item, str):
            for url in _extract_urls_from_text(item):
                add_url(url)
            return

        if isinstance(item, dict):
            item_type = _safe_text(item.get("type"), 80)
            if item_type in {"url_citation", "citation"}:
                counts["url_citation_count"] += 1

            url_value = (
                item.get("url")
                or item.get("uri")
                or item.get("source_url")
                or item.get("link")
            )
            if url_value:
                before_count = len(urls)
                add_url(url_value)
                if len(urls) > before_count:
                    counts["source_count"] += 1

            annotations = item.get("annotations")
            if isinstance(annotations, (list, tuple)):
                counts["annotation_count"] += len(annotations)

            for nested in item.values():
                visit(nested)
            return

        if isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    counts["url_count"] = len(urls)
    return counts


def _build_response_debug_summary(data, response_texts=None, instruction_texts=None):
    if not isinstance(data, dict):
        return {
            "top_level_keys": [],
            "status": "",
            "output_count": 0,
            "output_types": [],
        }

    output = data.get("output") if isinstance(data.get("output"), list) else []
    response_texts = response_texts or []
    instruction_texts = instruction_texts or []
    output_types = []
    output_statuses = []
    web_search_action_keys = []
    web_search_source_count = 0
    first_output_preview = {}
    message_count = 0
    reasoning_count = 0
    web_search_call_count = 0

    for index, item in enumerate(output):
        if not isinstance(item, dict):
            continue

        item_type = _safe_text(item.get("type"), 80)
        item_status = _safe_text(item.get("status"), 80)
        if item_type and item_type not in output_types:
            output_types.append(item_type)
        if item_status and item_status not in output_statuses:
            output_statuses.append(item_status)

        if index == 0:
            first_output_preview = {
                "type": item_type,
                "status": item_status,
                "keys": _safe_debug_keys(item),
            }

        if item_type == "message":
            message_count += 1
        elif item_type == "reasoning":
            reasoning_count += 1
        elif item_type == "web_search_call":
            web_search_call_count += 1

        if item_type == "web_search_call":
            action = item.get("action")
            if isinstance(action, dict):
                if not web_search_action_keys:
                    web_search_action_keys = _safe_debug_keys(action)

                action_sources = action.get("sources")
                if isinstance(action_sources, (list, tuple)):
                    web_search_source_count += len(action_sources)

            item_sources = item.get("sources")
            if isinstance(item_sources, (list, tuple)):
                web_search_source_count += len(item_sources)

    incomplete_details = data.get("incomplete_details") or {}
    debug_counts = _count_debug_items(data)
    output_text_length = sum(len(text) for text in response_texts)
    instruction_url_count = sum(
        len(_extract_urls_from_text(text))
        for text in instruction_texts
    )

    return {
        "top_level_keys": _safe_debug_keys(data),
        "status": _safe_text(data.get("status"), 80),
        "incomplete_reason": _safe_text(incomplete_details.get("reason"), 120),
        "output_count": len(output),
        "output_types": output_types[:10],
        "output_statuses": output_statuses[:10],
        "has_output_text": output_text_length > 0,
        "output_text_length": output_text_length,
        "source_count": debug_counts["source_count"],
        "url_count": debug_counts["url_count"],
        "output_url_count": debug_counts["url_count"],
        "instruction_url_count": instruction_url_count,
        "annotation_count": debug_counts["annotation_count"],
        "url_citation_count": debug_counts["url_citation_count"],
        "message_count": message_count,
        "reasoning_count": reasoning_count,
        "web_search_call_count": web_search_call_count,
        "first_output_preview": first_output_preview,
        "web_search_action_keys": web_search_action_keys,
        "web_search_source_count": web_search_source_count,
    }


def _is_reasoning_output_exhausted(debug_summary):
    return (
        _safe_text(debug_summary.get("incomplete_reason"), 120) == "max_output_tokens"
        and not debug_summary.get("has_output_text")
        and int(debug_summary.get("source_count") or 0) == 0
        and int(debug_summary.get("web_search_call_count") or 0) > 0
    )


def _extract_response_texts_and_sources(data):
    texts = []

    def add_text(value):
        text = _safe_text(value, AI_WEB_SEARCH_TEXT_CANDIDATE_MAX_CHARS)
        if text:
            texts.append(text)

    if isinstance(data, dict):
        add_text(data.get("output_text"))

        output = data.get("output") or []
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue

                if item.get("type") == "message":
                    for content in item.get("content") or []:
                        if not isinstance(content, dict):
                            continue
                        if content.get("type") in {"output_text", "text"}:
                            add_text(content.get("text"))

                if item.get("text"):
                    add_text(item.get("text"))

        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            add_text(message.get("content"))

    return texts, _extract_sources_from_value(data)


def _parse_gms_response(data):
    if not isinstance(data, dict):
        return {}

    texts, _sources = _extract_response_texts_and_sources(data)

    for text in texts:
        parsed = _extract_json_object(text)
        if parsed:
            return parsed

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


def _normalize_source_url(source_url, title=""):
    url = _safe_text(source_url, 500)
    if not url.startswith(("http://", "https://")):
        return []

    return [{
        "title": _safe_text(title or "web search source", 120),
        "url": url,
    }]


def _candidate_sources_from_raw(raw_candidate):
    return (
        _normalize_source_url(
            raw_candidate.get("source_url"),
            raw_candidate.get("source_title"),
        )
        or _normalize_sources(raw_candidate.get("evidence_sources"))
        or _normalize_sources(raw_candidate.get("sources"))
        or _normalize_sources(raw_candidate.get("ai_evidence_sources"))
    )


def _extract_urls_from_text(text):
    urls = []
    for match in re.finditer(r"https?://[^\s)\]}>,\"']+", text or ""):
        url = match.group(0).rstrip(".,;")
        if url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
    return urls


def _extract_markdown_link(text):
    match = re.search(r"\[([^\]]{2,120})\]\((https?://[^)]+)\)", text or "")
    if not match:
        return "", ""
    return _safe_text(match.group(1), 120), _safe_text(match.group(2), 500)


def _extract_labeled_value(text, labels, max_length=120):
    for label in labels:
        pattern = rf"(?:^|\n)\s*(?:[-*]\s*)?{re.escape(label)}\s*[:：]\s*([^\n]+)"
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            value = re.sub(r"https?://\S+", "", match.group(1)).strip(" -:：,")
            return _safe_text(value, max_length)
    return ""


def _extract_candidate_name_from_text(text, source_url=""):
    markdown_name, markdown_url = _extract_markdown_link(text)
    if markdown_name and (not source_url or markdown_url == source_url):
        return markdown_name

    labeled_name = _extract_labeled_value(
        text,
        ["name", "place", "candidate", "place name", "장소명", "후보명", "이름"],
    )
    if labeled_name:
        return labeled_name

    for raw_line in (text or "").splitlines():
        line = raw_line.strip(" -*\t")
        if not line or "http://" in line or "https://" in line:
            continue
        if line.endswith((".", "!", "?")):
            continue
        if "source" in line.lower() or "candidate" in line.lower():
            continue
        if ":" in line:
            line = line.split(":", 1)[-1].strip()
        if " - " in line:
            line = line.split(" - ", 1)[0].strip()
        if 2 <= len(line) <= 80:
            return _safe_text(line, 120)

    return ""


def _build_text_candidate(texts, sources):
    text = "\n".join(texts or [])
    if not text:
        return []

    source_list = list(sources or [])
    for url in _extract_urls_from_text(text):
        _append_source(source_list, "web search source", url)

    if not source_list:
        return []

    source_url = source_list[0]["url"]
    name = _extract_candidate_name_from_text(text, source_url)
    if not name:
        return []

    raw_candidate = {
        "name": name,
        "source_url": source_url,
    }
    return _normalize_candidates([raw_candidate])


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

        evidence_sources = _candidate_sources_from_raw(raw_candidate)
        if not evidence_sources:
            continue

        evidence_summary = _one_sentence_text(raw_candidate.get("evidence_summary"), 140)
        recommendation_reason = evidence_summary
        source_title = _safe_text(raw_candidate.get("source_title"), 120)
        source_query = _safe_text(raw_candidate.get("source_query"), 160)

        candidates.append({
            "name": name,
            "address_hint": _safe_text(raw_candidate.get("address_hint"), 160),
            "category_hint": _safe_text(raw_candidate.get("category_hint"), 80),
            "source_url": evidence_sources[0]["url"],
            "source_title": source_title or evidence_sources[0]["title"],
            "source_query": source_query,
            "candidate_type": _safe_text(raw_candidate.get("candidate_type"), 80),
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


def _build_source_reference_candidates(sources, queries=None):
    if not sources:
        return []

    reference_candidates = []
    source_query = _safe_text((queries or [""])[0], 160)

    for source in sources[:_get_max_candidates()]:
        url = _safe_text(source.get("url"), 500)
        if not url.startswith(("http://", "https://")):
            continue

        title = _safe_text(source.get("title"), 120)
        reference_candidates.append({
            "name": "웹 검색 참고 결과",
            "source_url": url,
            "source_title": title,
            "source_query": source_query,
            "candidate_type": "web_source_reference",
            "evidence_summary": "GMS 웹 검색 결과에서 확인된 참고 링크입니다.",
        })

    return _normalize_candidates(reference_candidates)


def _build_cache_key(query, lat, lng, condition, existing_results_summary, manual=False):
    cache_payload = {
        "query": _safe_text(query, 500),
        "lat": _safe_text(lat, 32),
        "lng": _safe_text(lng, 32),
        "condition": condition or {},
        "existing_results_summary": existing_results_summary or {},
        "model": getattr(settings, "AI_WEB_SEARCH_MODEL", "gpt-5-nano"),
        "reasoning_effort": _get_reasoning_effort(),
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
    location_hint="",
    search_plan=None,
    manual=False,
):
    provider = getattr(settings, "AI_WEB_SEARCH_PROVIDER", "gms")

    if not getattr(settings, "AI_WEB_SEARCH_ENABLED", False):
        return _base_response(
            enabled=False,
            reason="disabled",
        )

    if provider == "naver_search":
        from recommendations.services.naver_search_provider import get_naver_search_result

        return get_naver_search_result(
            query=query,
            location_hint=location_hint,
            search_plan=search_plan or {},
            manual=manual,
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
    _log_safe_request(
        query=query,
        condition=condition or {},
        manual=manual,
        existing_results_summary=summary,
    )
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
            reason=cached_response.get("reason", ""),
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

    tools = [{"type": "web_search"}]
    reasoning_payload, reasoning_debug = _get_reasoning_payload_for_tools(tools)
    payload = {
        "model": model,
        "instructions": _build_system_prompt(),
        "input": _build_user_prompt(query, lat, lng, condition or {}, summary),
        "tools": tools,
        "tool_choice": "auto",
        "max_output_tokens": max_output_tokens,
    }
    if reasoning_payload:
        payload["reasoning"] = reasoning_payload
    elif getattr(settings, "DEBUG", False) and reasoning_debug.get("reasoning_effort_requested"):
        logger.info("[AI_WEB_SEARCH_REASONING_SKIPPED] %s", reasoning_debug)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        last_error = None
        for attempt in range(AI_WEB_SEARCH_MAX_RETRIES + 1):
            try:
                response = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=getattr(settings, "AI_REQUEST_TIMEOUT", 20),
                )
                response.raise_for_status()
                last_error = None
                break
            except requests.RequestException as exc:
                last_error = exc
                status_code = _get_response_status_code(exc)
                should_retry = (
                    attempt < AI_WEB_SEARCH_MAX_RETRIES
                    and _is_retryable_server_error(exc)
                )

                if should_retry:
                    if getattr(settings, "DEBUG", False):
                        logger.info(
                            "[AI_WEB_SEARCH_RETRY] status_code=%s attempt=%s reason=%s",
                            status_code,
                            attempt + 1,
                            "server_error",
                        )
                    continue

                raise

        if last_error is not None:
            raise last_error

        data = response.json()
        response_texts, response_sources = _extract_response_texts_and_sources(data)
        response_queries = _extract_queries_from_value(data)
        response_debug_summary = _build_response_debug_summary(
            data,
            response_texts,
            instruction_texts=[payload["instructions"], payload["input"]],
        )
        parsed = _parse_gms_response(data)
    except requests.RequestException as exc:
        logger.exception("AI web search provider request failed")
        result = _build_request_failed_response(exc)
        if result["error"] != "temporary_server_error":
            _set_cached_response(cache_key, result)
        _log_safe_result(
            executed=True,
            candidates_count=0,
            error=result["error"],
            reason=result["reason"],
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
            reason=result["reason"],
            model=model,
            max_output_tokens=max_output_tokens,
        )
        return result

    candidates = _normalize_candidates(parsed.get("candidates"))
    used_source_reference_fallback = False
    if not candidates:
        candidates = _build_text_candidate(response_texts, response_sources)
    if not candidates and response_sources:
        candidates = _build_source_reference_candidates(response_sources, response_queries)
        used_source_reference_fallback = bool(candidates)

    is_incomplete = _is_incomplete_response(data)

    if is_incomplete and not candidates:
        exhausted_reasoning = _is_reasoning_output_exhausted(response_debug_summary)
        result = _base_response(
            enabled=True,
            executed=True,
            error="incomplete_response",
            reason="reasoning_output_exhausted" if exhausted_reasoning else "incomplete_response",
        )
        result["error_detail"] = {
            "status": "incomplete",
            "message": (
                "AI web search stopped before generating a final message."
                if exhausted_reasoning
                else "Response was incomplete, so a reliable candidate could not be confirmed."
            ),
            "debug_summary": response_debug_summary,
        }
        if response_sources:
            result["error_detail"]["source_count"] = len(response_sources)
        if getattr(settings, "DEBUG", False):
            logger.info(
                "[AI_WEB_SEARCH_DEBUG_SUMMARY] %s",
                json.dumps(response_debug_summary, ensure_ascii=False),
            )
        _set_cached_response(cache_key, result)
        _log_safe_result(
            executed=True,
            candidates_count=0,
            error=result["error"],
            reason=result["reason"],
            model=model,
            max_output_tokens=max_output_tokens,
            has_sources=bool(response_sources),
            has_text=bool(response_texts),
        )
        return result

    result = {
        **_base_response(enabled=True, executed=True),
        "candidates": candidates,
        "search_queries": (
            _safe_list(parsed.get("search_queries"), max_items=2)
            or response_queries
        ),
        "summary": _safe_text(parsed.get("summary"), 160),
        "error": "" if candidates else "empty_candidates",
        "reason": (
            "source_reference_fallback"
            if used_source_reference_fallback
            else ("completed" if candidates else "no_valid_candidates")
        ),
    }
    if is_incomplete and candidates:
        result["warning"] = "incomplete_response"
        result["debug_summary"] = response_debug_summary
        if not used_source_reference_fallback:
            result["reason"] = "completed_with_incomplete_response"

    if not candidates and response_sources:
        result["reason"] = "no_candidate_from_sources"
        result["error_detail"] = {
            "type": "no_candidate_from_sources",
            "message": "Sources were returned, but no reliable place candidate name was found.",
            "source_count": len(response_sources),
        }

    _set_cached_response(cache_key, result)
    _log_safe_result(
        executed=True,
        candidates_count=len(candidates),
        error=result["error"],
        reason=result["reason"],
        model=model,
        max_output_tokens=max_output_tokens,
        has_sources=bool(response_sources),
        has_text=bool(response_texts),
    )
    return result
