import json
import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

AI_WEB_SEARCH_MIN_DB_RESULTS = 3
AI_WEB_SEARCH_MIN_TOTAL_RESULTS = 5
AI_WEB_SEARCH_MAX_CANDIDATES = 5
AI_WEB_SEARCH_MAX_SOURCES_PER_CANDIDATE = 3

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

    return (
        db_count < AI_WEB_SEARCH_MIN_DB_RESULTS
        or total_count < AI_WEB_SEARCH_MIN_TOTAL_RESULTS
        or (db_count > 0 and weak_match_count >= db_count)
        or _has_detail_conditions(query, condition or {})
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
        "You are a Korean local-place recommendation evidence structurer. "
        "Use only actual web-search or grounding results available to the model. "
        "Do not invent places, coordinates, addresses, menus, business hours, quietness, "
        "solo-dining suitability, or operation status. Treat all candidates as low confidence. "
        "Return source titles and URLs, but do not store or return long original text, reviews, "
        "or article bodies. Return JSON only."
    )


def _build_user_prompt(query, lat, lng, condition, existing_results_summary):
    prompt_data = {
        "user_query": _safe_text(query, 500),
        "reference_location": {
            "lat": lat,
            "lng": lng,
        },
        "condition": {
            "scenario": _safe_text((condition or {}).get("scenario"), 80),
            "intent": _safe_text((condition or {}).get("intent"), 180),
            "categories": _safe_list((condition or {}).get("categories")),
            "required_tags": _safe_list((condition or {}).get("required_tags")),
            "preferred_tags": _safe_list((condition or {}).get("preferred_tags")),
            "keywords": _safe_list((condition or {}).get("keywords")),
        },
        "existing_results_summary": existing_results_summary or {},
        "rules": [
            "실제 웹 검색 또는 grounding 결과에서 확인 가능한 장소 후보만 제안하세요.",
            "좌표를 임의 생성하지 마세요.",
            "운영 여부, 메뉴 제공 여부, 조용함, 혼밥 가능 여부를 확정하지 마세요.",
            "후보는 낮은 신뢰도 정보로 취급하세요.",
            "출처 제목과 URL을 함께 반환하세요.",
            "긴 원문, 리뷰 전문, 블로그 본문은 반환하지 마세요.",
            "JSON만 반환하세요.",
        ],
        "response_schema": {
            "candidates": [
                {
                    "name": "장소명",
                    "address_hint": "주소 또는 지역 힌트",
                    "category_hint": "카페 / 식당 / 공원 등",
                    "matched_conditions": ["브런치", "카페"],
                    "evidence_summary": "웹 검색 결과에서 사용자의 조건과 관련된 후보로 확인되었습니다.",
                    "evidence_sources": [
                        {
                            "title": "출처 제목",
                            "url": "출처 URL",
                        }
                    ],
                    "confidence": "low",
                }
            ],
            "search_queries": [],
            "summary": "",
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

        evidence_sources = _normalize_sources(raw_candidate.get("evidence_sources"))
        if not evidence_sources:
            continue

        evidence_summary = (
            _safe_text(raw_candidate.get("evidence_summary"), 300)
            or "웹 검색 결과에서 사용자의 조건과 관련된 후보로 확인되었습니다."
        )
        recommendation_reason = (
            f"{evidence_summary} 세부 정보는 방문 전 확인이 필요합니다."
        )

        candidates.append({
            "name": name,
            "address_hint": _safe_text(raw_candidate.get("address_hint"), 160),
            "category_hint": _safe_text(raw_candidate.get("category_hint"), 80),
            "matched_conditions": _safe_list(
                raw_candidate.get("matched_conditions"),
                max_items=6,
                max_length=80,
            ),
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

    return candidates[:AI_WEB_SEARCH_MAX_CANDIDATES]


def get_ai_web_search_result(
    query,
    lat=None,
    lng=None,
    condition=None,
    existing_results_summary=None,
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

    summary = existing_results_summary or {}
    if not should_execute_ai_web_search(query, condition, summary):
        return _base_response(
            enabled=True,
            reason="enough_existing_results",
        )

    api_key = getattr(settings, "GMS_API_KEY", "")
    api_url = getattr(settings, "GMS_API_URL", "")
    lat = _safe_float(lat)
    lng = _safe_float(lng)

    if not api_key or not api_url:
        return _base_response(
            enabled=False,
            error="not_configured",
            reason="missing_api_configuration",
        )

    payload = {
        "model": getattr(settings, "AI_WEB_SEARCH_MODEL", "gpt-5-mini"),
        "messages": [
            {
                "role": "system",
                "content": _build_system_prompt(),
            },
            {
                "role": "user",
                "content": _build_user_prompt(query, lat, lng, condition or {}, summary),
            },
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 1200,
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
        parsed = _parse_gms_response(response.json())
    except requests.RequestException:
        logger.exception("AI web search provider request failed")
        return _base_response(
            enabled=True,
            executed=False,
            error="api_error",
            reason="request_failed",
        )
    except ValueError:
        logger.exception("AI web search provider returned invalid JSON")
        return _base_response(
            enabled=True,
            executed=True,
            error="invalid_json",
            reason="response_json_parse_failed",
        )

    candidates = _normalize_candidates(parsed.get("candidates"))

    return {
        **_base_response(enabled=True, executed=True),
        "candidates": candidates,
        "search_queries": _safe_list(parsed.get("search_queries"), max_items=8),
        "summary": _safe_text(parsed.get("summary"), 300),
        "error": "" if candidates else "empty_candidates",
        "reason": "completed" if candidates else "no_valid_candidates",
    }
