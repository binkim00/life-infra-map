"""
Manual, opt-in OpenAI web_search probe.

This file is intentionally not part of the default Django test suite. It will
not make a live API call unless RUN_OPENAI_WEB_SEARCH_LIVE=true is set.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent


def load_env_file(path):
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def build_endpoint():
    base_url = os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    path = os.environ.get("OPENAI_RESPONSES_PATH", "responses").strip("/")
    return f"{base_url}/{path}"


def main():
    if os.environ.get("RUN_OPENAI_WEB_SEARCH_LIVE", "").lower() != "true":
        print("SKIP: set RUN_OPENAI_WEB_SEARCH_LIVE=true to run the live OpenAI probe.")
        return

    load_env_file(BACKEND_DIR / ".env")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    endpoint = build_endpoint()
    model = os.environ.get("AI_WEB_SEARCH_MODEL", "gpt-5-nano")
    max_output_tokens = min(
        max(int(os.environ.get("AI_WEB_SEARCH_MAX_OUTPUT_TOKENS", "800")), 200),
        800,
    )

    payload = {
        "model": model,
        "input": (
            "Find exactly one currently operating brunch cafe near Bujeon Station in Busan. "
            "Return JSON only with name, address_hint, category_hint, evidence_summary, "
            "and evidence_sources as title/url pairs. Do not invent coordinates or facts."
        ),
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
        "max_output_tokens": max_output_tokens,
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    print("endpoint:", endpoint)
    print("model:", model)
    print("max_output_tokens:", max_output_tokens)
    print("OpenAI key: not printed")

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status_code = response.status
            raw = response.read().decode("utf-8")

        data = json.loads(raw)
        pretty = json.dumps(data, ensure_ascii=False)
        urls = sorted(set(re.findall(r"https?://[^\s\"'<>]+", pretty)))

        print("HTTP status:", status_code)
        print("top-level keys:", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
        print("status:", data.get("status") if isinstance(data, dict) else "")
        print("output types:", [
            item.get("type")
            for item in (data.get("output") or [])[:10]
            if isinstance(item, dict)
        ] if isinstance(data, dict) else [])
        print("url count:", len(urls))
        print("has incomplete_details:", bool(data.get("incomplete_details")) if isinstance(data, dict) else False)

    except urllib.error.HTTPError as error:
        print("HTTPError:", error.code)
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            err = parsed.get("error", {}) if isinstance(parsed, dict) else {}
            print("error type:", err.get("type") if isinstance(err, dict) else type(err).__name__)
            print("error message:", str(err.get("message", ""))[:400] if isinstance(err, dict) else "")
        except ValueError:
            print("non-json error body")
    except Exception as error:
        print("ERROR:", type(error).__name__)
        print(str(error)[:400])


if __name__ == "__main__":
    main()
