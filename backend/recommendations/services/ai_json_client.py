import json
import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

OPENAI_RESPONSES_PATH = "responses"


def _clean_text(value, max_length=500):
    text = str(value or "").strip()
    if max_length and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def extract_json_object(value):
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


def _provider(provider=None):
    return _clean_text(provider or getattr(settings, "AI_PROVIDER", "openai"), 40).lower()


def get_ai_provider_name(provider=None):
    return _provider(provider) or "unknown"


def get_ai_json_unavailable_reason(provider=None):
    selected = _provider(provider)
    if selected == "gms":
        if not getattr(settings, "GMS_API_KEY", ""):
            return "missing_gms_api_key"
        if not (
            getattr(settings, "GMS_API_URL", "")
            or getattr(settings, "GMS_API_BASE_URL", "")
        ):
            return "missing_gms_api_url"
        return ""

    if selected == "openai":
        if not getattr(settings, "OPENAI_API_KEY", ""):
            return "missing_openai_api_key"
        return ""

    return f"unsupported_ai_provider:{selected or 'unknown'}"


def _gms_chat_completions_url():
    explicit = _clean_text(getattr(settings, "GMS_API_URL", ""), 500)
    if explicit:
        return explicit

    base_url = _clean_text(getattr(settings, "GMS_API_BASE_URL", ""), 500).rstrip("/")
    if not base_url:
        return ""
    return f"{base_url}/api.openai.com/v1/chat/completions"


def _openai_responses_url():
    base_url = _clean_text(
        getattr(settings, "OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
        500,
    ).rstrip("/")
    return f"{base_url}/{OPENAI_RESPONSES_PATH}"


def _json_schema_format(schema_name, response_schema):
    if not response_schema:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "name": _clean_text(schema_name or "ai_response", 64) or "ai_response",
        "schema": response_schema,
        "strict": True,
    }


def _call_gms_chat_json(
    query,
    system_prompt,
    max_completion_tokens,
    *,
    model=None,
    timeout=None,
    response_schema=None,
    schema_name="ai_response",
):
    api_key = getattr(settings, "GMS_API_KEY", "")
    api_url = _gms_chat_completions_url()
    model = model or getattr(settings, "AI_INTENT_MODEL", getattr(settings, "GMS_MODEL", "gpt-5-nano"))

    if not api_key or not api_url:
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        "response_format": (
            {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": response_schema,
                    "strict": True,
                },
            }
            if response_schema
            else {"type": "json_object"}
        ),
        "reasoning_effort": "minimal",
        "max_completion_tokens": max_completion_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=timeout or getattr(settings, "AI_REQUEST_TIMEOUT", 4),
    )
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        parsed = message.get("parsed")
        if parsed:
            return parsed
        content = message.get("content")
        if content:
            return extract_json_object(content)

    structured = data.get("parsed") or data.get("result") or data.get("output")
    if isinstance(structured, dict):
        return structured
    if isinstance(structured, str):
        return extract_json_object(structured)

    if any(key in data for key in ("is_searchable", "searchable", "scenario")):
        return data

    return None


def _extract_openai_output_text(data):
    texts = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if isinstance(content.get("parsed"), dict):
                return content["parsed"]
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                texts.append(str(content.get("text")))
            if content.get("type") == "refusal":
                logger.info("OpenAI refused structured JSON request: %s", content.get("refusal"))
    return "\n".join(texts).strip()


def _call_openai_responses_json(
    query,
    system_prompt,
    max_completion_tokens,
    *,
    model=None,
    timeout=None,
    response_schema=None,
    schema_name="ai_response",
    reasoning_effort=None,
    include_usage=False,
):
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        return None

    model = model or getattr(settings, "AI_INTENT_MODEL", "gpt-5-mini")
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        "text": {
            "format": _json_schema_format(schema_name, response_schema),
        },
        "max_output_tokens": max_completion_tokens,
    }

    effort = _clean_text(
        reasoning_effort or getattr(settings, "AI_REASONING_EFFORT", ""),
        40,
    ).lower()
    if effort:
        payload["reasoning"] = {"effort": effort}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        _openai_responses_url(),
        headers=headers,
        json=payload,
        timeout=timeout or getattr(settings, "AI_REQUEST_TIMEOUT", 20),
    )
    response.raise_for_status()
    data = response.json()

    parsed = None
    if isinstance(data.get("output_parsed"), dict):
        parsed = data["output_parsed"]
    elif isinstance(data.get("parsed"), dict):
        parsed = data["parsed"]
    else:
        output = _extract_openai_output_text(data)
        if isinstance(output, dict):
            parsed = output
        elif output:
            parsed = extract_json_object(output)
    if not include_usage:
        return parsed
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return {
        "data": parsed or {},
        "usage": {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "cached_input_tokens": int(
                ((usage.get("input_tokens_details") or {}).get("cached_tokens") or 0)
            ),
        },
        "model": str(data.get("model") or model),
        "response_id": str(data.get("id") or ""),
    }


def call_ai_json(
    query,
    system_prompt,
    max_completion_tokens,
    *,
    model=None,
    timeout=None,
    provider=None,
    response_schema=None,
    schema_name="ai_response",
    reasoning_effort=None,
):
    selected = _provider(provider)
    if selected == "gms":
        return _call_gms_chat_json(
            query,
            system_prompt,
            max_completion_tokens,
            model=model,
            timeout=timeout,
            response_schema=response_schema,
            schema_name=schema_name,
        )
    if selected == "openai":
        return _call_openai_responses_json(
            query,
            system_prompt,
            max_completion_tokens,
            model=model,
            timeout=timeout,
            response_schema=response_schema,
            schema_name=schema_name,
            reasoning_effort=reasoning_effort,
        )
    raise ValueError(f"Unsupported AI provider: {selected}")


def call_ai_json_with_usage(*args, **kwargs):
    """Return parsed data and exact provider usage without changing legacy callers."""
    selected = _provider(kwargs.get("provider"))
    if selected != "openai":
        return {"data": call_ai_json(*args, **kwargs) or {}, "usage": {}, "model": ""}
    kwargs = dict(kwargs)
    kwargs.pop("provider", None)
    return _call_openai_responses_json(*args, include_usage=True, **kwargs)
