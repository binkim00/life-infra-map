import json
import html
import re

import requests
from django.conf import settings


NAVER_SEARCH_ENDPOINTS = {
    "local": "https://openapi.naver.com/v1/search/local.json",
    "blog": "https://openapi.naver.com/v1/search/blog.json",
    "webkr": "https://openapi.naver.com/v1/search/webkr.json",
}
NAVER_SEARCH_CHANNEL_ORDER = ("local", "blog", "webkr")
NAVER_SEARCH_MAX_CANDIDATES = 5
NAVER_SEARCH_SUMMARY_MAX_CANDIDATES = 5
LOCATION_SUFFIXES = ("역", "동", "구", "시", "군", "읍", "면", "대", "시장")
GENERIC_TARGET_TERMS = {
    "맛집",
    "추천",
    "찾아줘",
    "찾기",
    "가능",
    "있는",
    "근처",
    "주변",
    "인근",
    "가까운",
    "곳",
    "장소",
    "식당",
    "음식점",
    "카페",
}
PROHIBITED_SUMMARY_PATTERNS = (
    "맛집입니다",
    "판매합니다",
    "영업 중입니다",
    "영업중입니다",
    "주차 가능합니다",
    "콘센트가 있습니다",
    "흡연 가능합니다",
)
DEFAULT_SUMMARY_CAUTION = (
    "웹 검색 출처 기반 참고 정보이며, 실제 메뉴와 운영 정보는 방문 전 확인이 필요합니다."
)


def _safe_text(value, max_length=240):
    if value is None:
        return ""
    text = str(value).strip()
    return text[:max_length]


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


def _clean_html(value, max_length=240):
    text = html.unescape(_safe_text(value, max_length=max_length * 4))
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text[:max_length]


def _is_http_url(value):
    return _safe_text(value, 600).startswith(("http://", "https://"))


def _base_response(executed=False, candidates=None, error="", reason=""):
    return {
        "enabled": True,
        "executed": executed,
        "supported": True,
        "provider": "naver_search",
        "candidates": candidates or [],
        "error": error,
        "reason": reason,
    }


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


def _get_plan_value(search_plan, *keys):
    if not isinstance(search_plan, dict):
        return ""

    for key in keys:
        value = _safe_text(search_plan.get(key), 160)
        if value:
            return value
    return ""


def _get_plan_list(search_plan, *keys):
    if not isinstance(search_plan, dict):
        return []

    for key in keys:
        values = _safe_list(search_plan.get(key), max_items=5)
        if values:
            return values
    return []


def _join_query_terms(*terms):
    return " ".join(
        dict.fromkeys(_safe_text(term, 120) for term in terms if _safe_text(term, 120))
    )


def _split_terms(value):
    return [
        term
        for term in re.split(r"[\s,./|·\-]+", _safe_text(value, 240))
        if term
    ]


def _compact_text(value):
    return re.sub(r"[\s,./|·\-]+", "", _safe_text(value, 500)).lower()


def _derive_location_terms(location_text):
    terms = []
    for term in _split_terms(location_text):
        cleaned = term.strip()
        if not cleaned:
            continue

        terms.append(cleaned)
        if len(cleaned) > 2 and cleaned[-1] in {"구", "시", "군", "읍", "면", "동", "역"}:
            terms.append(cleaned[:-1])

    return list(dict.fromkeys(terms))


def _infer_location_terms_from_query(query):
    terms = []
    for term in _split_terms(query)[:2]:
        if len(term) >= 2 and term.endswith(LOCATION_SUFFIXES):
            terms.append(term)

    return _derive_location_terms(" ".join(terms))


def get_naver_location_terms(query="", location_hint="", search_plan=None):
    search_plan = search_plan or {}
    location_text = _join_query_terms(
        _get_plan_value(search_plan, "locationQuery", "location_query"),
        _get_plan_value(search_plan, "baseLocationQuery", "base_location_query"),
        location_hint,
    )
    terms = _derive_location_terms(location_text)
    if terms:
        return terms

    return _infer_location_terms_from_query(query)


def _get_relevance_terms(query="", search_plan=None):
    search_plan = search_plan or {}
    terms = []

    for value in (
        _get_plan_value(search_plan, "targetQuery", "target_query", "targetKeyword", "target_keyword"),
        _get_plan_value(search_plan, "categoryHint", "category_hint"),
    ):
        terms.extend(_split_terms(value))

    terms.extend(_get_plan_list(search_plan, "menu_keywords", "menuKeywords"))
    terms.extend(_get_plan_list(search_plan, "place_type_keywords", "placeTypeKeywords"))

    if not terms:
        terms.extend(_split_terms(query))

    cleaned = []
    for term in terms:
        term = _safe_text(term, 40)
        if len(term) < 2 or term in GENERIC_TARGET_TERMS:
            continue
        cleaned.append(term)

    return list(dict.fromkeys(cleaned))[:8]


def _text_has_any_term(text, terms):
    compacted = _compact_text(text)
    return any(_compact_text(term) in compacted for term in terms if _compact_text(term))


def build_naver_search_query(query, location_hint="", search_plan=None):
    search_plan = search_plan or {}
    location_query = _get_plan_value(search_plan, "locationQuery", "location_query")
    base_location_query = _get_plan_value(
        search_plan,
        "baseLocationQuery",
        "base_location_query",
    )
    target_query = _get_plan_value(search_plan, "targetQuery", "target_query", "targetKeyword", "target_keyword")
    location_hint = _safe_text(location_hint, 120)
    menu_keywords = _get_plan_list(search_plan, "menu_keywords", "menuKeywords")
    place_type_keywords = _get_plan_list(search_plan, "place_type_keywords", "placeTypeKeywords")

    if location_query and target_query:
        return _join_query_terms(location_query, target_query)

    if base_location_query and target_query:
        return _join_query_terms(base_location_query, target_query)

    if location_hint and target_query:
        return _join_query_terms(location_hint, target_query)

    if location_hint and (menu_keywords or place_type_keywords):
        return _join_query_terms(location_hint, *menu_keywords, *place_type_keywords)

    return _safe_text(query, 160)


def _get_display_count():
    try:
        value = int(getattr(settings, "NAVER_SEARCH_DISPLAY", 5))
    except (TypeError, ValueError):
        value = 5
    return min(max(value, 1), 100)


def _get_sort_for_channel(channel):
    sort = _safe_text(getattr(settings, "NAVER_SEARCH_SORT", "sim"), 20) or "sim"
    if channel == "local":
        return sort if sort in {"random", "comment"} else ""
    if channel in {"blog", "webkr"}:
        return sort if sort in {"sim", "date"} else "sim"
    return ""


def _request_channel(channel, search_query):
    params = {
        "query": search_query,
        "display": _get_display_count(),
    }
    sort = _get_sort_for_channel(channel)
    if sort:
        params["sort"] = sort

    response = requests.get(
        NAVER_SEARCH_ENDPOINTS[channel],
        headers={
            "X-Naver-Client-Id": getattr(settings, "NAVER_SEARCH_CLIENT_ID", ""),
            "X-Naver-Client-Secret": getattr(settings, "NAVER_SEARCH_CLIENT_SECRET", ""),
        },
        params=params,
        timeout=getattr(settings, "AI_REQUEST_TIMEOUT", 20),
    )
    response.raise_for_status()
    return response.json()


def _sanitize_error_message(message, max_length=180):
    text = _safe_text(message, 1000)
    for secret in (
        getattr(settings, "NAVER_SEARCH_CLIENT_ID", ""),
        getattr(settings, "NAVER_SEARCH_CLIENT_SECRET", ""),
    ):
        if secret:
            text = text.replace(secret, "[redacted]")
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


def _build_error_detail(error):
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    message = ""

    if response is not None:
        try:
            data = response.json()
        except ValueError:
            data = {}

        if isinstance(data, dict):
            message = (
                data.get("errorMessage")
                or data.get("message")
                or data.get("error")
                or data.get("detail")
                or ""
            )

    if not message:
        message = str(error)

    detail = {
        "type": _error_type_from_status(status_code),
        "message": _sanitize_error_message(message),
    }
    if status_code:
        detail["status_code"] = status_code
    return detail


def _candidate_from_item(item, channel, search_query, requested_conditions):
    if not isinstance(item, dict):
        return None

    title = _clean_html(item.get("title"), 140)
    source_url = _safe_text(item.get("link"), 600)
    if not title or not _is_http_url(source_url):
        return None

    evidence_summary = _clean_html(item.get("description"), 220)
    address_hint = ""
    if channel == "local":
        address_hint = _clean_html(
            item.get("roadAddress") or item.get("address"),
            180,
        )

    candidate = {
        "name": title,
        "candidate_type": "web_source_reference",
        "source_url": source_url,
        "source_title": title,
        "source_query": search_query,
        "evidence_summary": evidence_summary,
        "address_hint": address_hint,
        "category_hint": _clean_html(item.get("category"), 100),
        "source_provider": "naver_search",
        "source_channel": channel,
        "confidence": "low",
        "matched_conditions": [],
        "evidence_sources": [{
            "title": title,
            "url": source_url,
        }],
        "ai_evidence_sources": [{
            "title": title,
            "url": source_url,
        }],
        "is_verified": False,
    }

    if requested_conditions:
        candidate["requested_conditions"] = requested_conditions
        candidate["condition_notice"] = (
            "요청한 조건은 검색 API 결과만으로 확인되지 않았습니다. 방문 전 확인이 필요합니다."
        )

    return candidate


def _fallback_summary(query, location_hint, candidates):
    keyword_source = " ".join([
        _safe_text(location_hint, 80),
        _safe_text(query, 120),
        " ".join(_safe_text(candidate.get("source_title"), 80) for candidate in candidates[:3]),
    ])
    keywords = []
    for term in _split_terms(keyword_source):
        if len(term) < 2 or term in GENERIC_TARGET_TERMS:
            continue
        keywords.append(term)

    return {
        "title": "AI 웹 검색 요약",
        "main_text": "웹 검색 결과에서 요청과 관련된 참고 링크가 확인되었습니다.",
        "keywords": list(dict.fromkeys(keywords))[:5],
        "caution": DEFAULT_SUMMARY_CAUTION,
    }


def _build_summary_system_prompt():
    return (
        "You summarize Korean search API results for a local place reference UI. "
        "Use only the provided title, description, source channel, address hint, "
        "and source URL. Do not invent place names, addresses, coordinates, "
        "opening status, menu availability, parking, outlets, smoking availability, "
        "or other facilities. Use cautious wording only, such as '웹 검색 결과에서 "
        "확인됩니다', '관련 글이 확인됩니다', and '방문 전 확인이 필요합니다'. "
        "Never say a place is a 맛집, sells a menu, is open, has parking, has outlets, "
        "or allows smoking. Return only JSON: {\"summary\":{\"title\":\"AI 웹 검색 요약\","
        "\"main_text\":\"...\",\"keywords\":[\"...\"],\"caution\":\"...\"}}."
    )


def _build_summary_user_payload(query, location_hint, candidates):
    safe_candidates = []
    for candidate in candidates[:NAVER_SEARCH_SUMMARY_MAX_CANDIDATES]:
        safe_candidates.append({
            "source_title": _safe_text(candidate.get("source_title") or candidate.get("name"), 160),
            "evidence_summary": _safe_text(candidate.get("evidence_summary"), 220),
            "source_url": _safe_text(candidate.get("source_url"), 500),
            "source_channel": _safe_text(candidate.get("source_channel"), 20),
            "address_hint": _safe_text(candidate.get("address_hint"), 160),
        })

    return json.dumps({
        "query": _safe_text(query, 160),
        "location_hint": _safe_text(location_hint, 120),
        "candidates": safe_candidates,
    }, ensure_ascii=False)


def _normalize_summary(raw_summary, query, location_hint, candidates):
    raw = _extract_json_object(raw_summary)
    summary = raw.get("summary") if isinstance(raw.get("summary"), dict) else raw
    if not isinstance(summary, dict):
        return _fallback_summary(query, location_hint, candidates)

    fallback = _fallback_summary(query, location_hint, candidates)
    main_text = _safe_text(summary.get("main_text"), 220)
    if not main_text or any(pattern in main_text for pattern in PROHIBITED_SUMMARY_PATTERNS):
        main_text = fallback["main_text"]

    evidence_text = " ".join([
        _safe_text(query, 160),
        _safe_text(location_hint, 120),
        " ".join(
            " ".join([
                _safe_text(candidate.get("source_title") or candidate.get("name"), 160),
                _safe_text(candidate.get("evidence_summary"), 220),
                _safe_text(candidate.get("address_hint"), 160),
            ])
            for candidate in candidates[:NAVER_SEARCH_SUMMARY_MAX_CANDIDATES]
        ),
    ])
    compacted_evidence = _compact_text(evidence_text)
    keywords = [
        keyword
        for keyword in _safe_list(summary.get("keywords"), max_items=5, max_length=40)
        if _compact_text(keyword) in compacted_evidence
    ]
    if not keywords:
        keywords = fallback["keywords"]

    caution = _safe_text(summary.get("caution"), 180)
    if not caution or any(pattern in caution for pattern in PROHIBITED_SUMMARY_PATTERNS):
        caution = DEFAULT_SUMMARY_CAUTION

    return {
        "title": "AI 웹 검색 요약",
        "main_text": main_text,
        "keywords": keywords,
        "caution": caution,
    }


def _call_ai_summary(query, location_hint, candidates):
    api_key = getattr(settings, "GMS_API_KEY", "")
    api_url = getattr(settings, "GMS_API_URL", "")
    if not api_key or not api_url:
        return None

    model = getattr(
        settings,
        "AI_INTENT_MODEL",
        getattr(settings, "GMS_MODEL", "gpt-5-nano"),
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": _build_summary_system_prompt(),
            },
            {
                "role": "user",
                "content": _build_summary_user_payload(query, location_hint, candidates),
            },
        ],
        "response_format": {"type": "json_object"},
        "reasoning_effort": "minimal",
        "max_completion_tokens": 700,
    }
    response = requests.post(
        api_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=getattr(settings, "AI_REQUEST_TIMEOUT", 20),
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content:
            return _extract_json_object(content)

    return data.get("parsed") or data.get("result") or data.get("output") or data


def build_ai_web_search_summary(query, location_hint, candidates):
    fallback = _fallback_summary(query, location_hint, candidates)
    try:
        raw_summary = _call_ai_summary(query, location_hint, candidates)
    except (requests.RequestException, ValueError):
        return {
            **fallback,
            "summary_source": "fallback",
        }

    if not raw_summary:
        return {
            **fallback,
            "summary_source": "fallback",
        }

    summary = _normalize_summary(raw_summary, query, location_hint, candidates)
    summary["summary_source"] = "ai"
    return summary


def _is_local_item_relevant(item, relevance_terms):
    if not relevance_terms:
        return True

    haystack = " ".join([
        _clean_html(item.get("title"), 180),
        _clean_html(item.get("category"), 120),
        _clean_html(item.get("address"), 180),
        _clean_html(item.get("roadAddress"), 180),
    ])
    return _text_has_any_term(haystack, relevance_terms)


def _is_location_matched_item(item, location_terms):
    if not location_terms:
        return False

    haystack = " ".join([
        _clean_html(item.get("title"), 180),
        _clean_html(item.get("description"), 240),
        _clean_html(item.get("address"), 180),
        _clean_html(item.get("roadAddress"), 180),
    ])
    return _text_has_any_term(haystack, location_terms)


def _normalize_items(
    items,
    channel,
    search_query,
    requested_conditions,
    location_terms=None,
    relevance_terms=None,
):
    candidates = []
    location_terms = location_terms or []
    relevance_terms = relevance_terms or []

    for item in items or []:
        if channel == "local" and not _is_local_item_relevant(item, relevance_terms):
            continue

        if channel in {"blog", "webkr"} and not _is_location_matched_item(item, location_terms):
            continue

        candidate = _candidate_from_item(item, channel, search_query, requested_conditions)
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= NAVER_SEARCH_MAX_CANDIDATES:
            break
    return candidates


def get_naver_search_result(
    query,
    location_hint="",
    search_plan=None,
    manual=False,
):
    if not manual:
        return _base_response(
            executed=False,
            reason="manual_required",
        )

    if not _safe_text(query):
        return _base_response(
            executed=False,
            error="missing_query",
            reason="missing_query",
        )

    if not getattr(settings, "NAVER_SEARCH_CLIENT_ID", "") or not getattr(
        settings,
        "NAVER_SEARCH_CLIENT_SECRET",
        "",
    ):
        return _base_response(
            executed=False,
            error="missing_credentials",
            reason="missing_naver_search_credentials",
        )

    search_query = build_naver_search_query(
        query,
        location_hint=location_hint,
        search_plan=search_plan or {},
    )
    location_terms = get_naver_location_terms(
        query=query,
        location_hint=location_hint,
        search_plan=search_plan or {},
    )
    relevance_terms = _get_relevance_terms(query=query, search_plan=search_plan or {})
    requested_conditions = _get_plan_list(
        search_plan or {},
        "requestedConditions",
        "requested_conditions",
    )
    debug_summary = {
        "provider": "naver_search",
        "query": search_query,
        "source_channel": "",
        "raw_result_count": 0,
        "location_matched_count": 0,
        "filtered_out_count": 0,
        "location_terms": location_terms,
    }
    saw_raw_results = False
    saw_location_filtered_results = False
    location_filtered_debug_summary = None

    try:
        for channel in NAVER_SEARCH_CHANNEL_ORDER:
            if channel in {"blog", "webkr"} and not location_terms:
                result = _base_response(
                    executed=True,
                    candidates=[],
                    reason="missing_location_hint_for_broad_search",
                )
                result["search_queries"] = [search_query]
                if getattr(settings, "DEBUG", False):
                    debug_summary["source_channel"] = channel
                    result["debug_summary"] = debug_summary
                return result

            data = _request_channel(channel, search_query)
            raw_items = data.get("items") if isinstance(data, dict) else []
            raw_count = len(raw_items or [])
            saw_raw_results = saw_raw_results or raw_count > 0
            location_matched_count = (
                sum(1 for item in raw_items if _is_location_matched_item(item, location_terms))
                if channel in {"blog", "webkr"} and location_terms
                else raw_count
            )
            candidates = _normalize_items(
                raw_items,
                channel,
                search_query,
                requested_conditions,
                location_terms=location_terms,
                relevance_terms=relevance_terms,
            )
            filtered_out_count = max(raw_count - len(candidates), 0)
            debug_summary = {
                "provider": "naver_search",
                "query": search_query,
                "source_channel": channel,
                "raw_result_count": raw_count,
                "location_matched_count": location_matched_count,
                "filtered_out_count": filtered_out_count,
                "location_terms": location_terms,
            }
            if channel in {"blog", "webkr"} and raw_count and not location_matched_count:
                saw_location_filtered_results = True
                location_filtered_debug_summary = debug_summary

            if candidates:
                summary = build_ai_web_search_summary(query, location_hint, candidates)
                result = _base_response(
                    executed=True,
                    candidates=candidates,
                    reason="search_api_reference",
                )
                result["summary"] = summary
                result["search_queries"] = [search_query]
                result["source_channel"] = channel
                if getattr(settings, "DEBUG", False):
                    result["debug_summary"] = debug_summary
                return result
    except (requests.RequestException, ValueError) as exc:
        result = _base_response(
            executed=True,
            error="api_error",
            reason="request_failed",
        )
        result["error_detail"] = _build_error_detail(exc)
        return result

    if saw_location_filtered_results:
        result = _base_response(
            executed=True,
            candidates=[],
            reason="no_location_matched_search_result",
        )
        result["search_queries"] = [search_query]
        if getattr(settings, "DEBUG", False):
            result["debug_summary"] = location_filtered_debug_summary or debug_summary
        return result

    result = _base_response(
        executed=True,
        candidates=[],
        reason="no_search_result",
    )
    result["search_queries"] = [search_query]
    if getattr(settings, "DEBUG", False):
        result["debug_summary"] = debug_summary
    return result
