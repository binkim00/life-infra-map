KAKAO_PLACE_URL_KEYS = (
    "kakao_place_url",
    "kakao_url",
    "place_url",
    "detail_url",
)


def _clean_text(value):
    if value in (None, ""):
        return ""

    return str(value).strip()


def _normalize_kakao_place_url(url):
    cleaned = _clean_text(url)
    if not cleaned:
        return ""

    if cleaned.startswith("http://place.map.kakao.com/"):
        return cleaned.replace("http://", "https://", 1)

    if cleaned.startswith("place.map.kakao.com/"):
        return f"https://{cleaned}"

    if cleaned.startswith("https://place.map.kakao.com/"):
        return cleaned

    return ""


def _find_kakao_place_url(value, depth=0):
    if depth > 4:
        return ""

    if isinstance(value, dict):
        for key in KAKAO_PLACE_URL_KEYS:
            url = _normalize_kakao_place_url(value.get(key))
            if url:
                return url

        for nested_value in value.values():
            url = _find_kakao_place_url(nested_value, depth + 1)
            if url:
                return url

    if isinstance(value, list):
        for item in value:
            url = _find_kakao_place_url(item, depth + 1)
            if url:
                return url

    return ""


def is_kakao_place_id(value):
    text = _clean_text(value)
    return text.isdigit() and 5 <= len(text) <= 20


def has_kakao_source_hint(place):
    source_text = " ".join(
        _clean_text(value).lower()
        for value in [
            getattr(place, "source", ""),
            getattr(place, "source_name", ""),
        ]
    )
    return "kakao" in source_text


def get_kakao_place_url(place):
    annotated_url = _find_kakao_place_url({
        "kakao_place_url": getattr(place, "collect_kakao_place_url", ""),
        "kakao_url": getattr(place, "collect_kakao_url", ""),
        "place_url": getattr(place, "collect_place_url", ""),
        "detail_url": getattr(place, "collect_detail_url", ""),
    })
    if annotated_url:
        return annotated_url

    # A deferred JSON field must remain deferred here; touching it would issue
    # one query per result during recommendation serialization.
    raw_url = _find_kakao_place_url(place.__dict__.get("raw", {}) or {})
    if raw_url:
        return raw_url

    external_id = _clean_text(getattr(place, "external_id", ""))
    if has_kakao_source_hint(place) and is_kakao_place_id(external_id):
        return f"https://place.map.kakao.com/{external_id}"

    return ""
