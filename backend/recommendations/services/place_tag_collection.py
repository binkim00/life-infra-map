"""Place-level collection profiles and multi-tag evidence extraction."""

from recommendations.services.naver_search_provider import _clean_html, _request_channel, _safe_text
from recommendations.services.naver_tag_evidence_provider import (
    SEARCH_KEYWORDS,
    TAG_TERMS,
    address_identity_terms,
    evidence_polarity,
    identity_matches,
)


COLLECTION_PROFILES = {
    "cafe": (
        ("work", ("노트북작업", "콘센트있음", "무료와이파이", "작업하기좋음")),
        ("ambience", ("조용함", "분위기좋음", "데이트좋음", "대화하기좋음")),
        ("visit", ("전망좋음", "웨이팅적음")),
    ),
    "restaurant": (
        ("visit", ("혼밥좋음", "웨이팅적음", "데이트좋음", "대화하기좋음")),
        ("ambience", ("조용함", "분위기좋음", "전망좋음")),
    ),
    "tourism": (
        ("experience", ("전망좋음", "분위기좋음", "데이트좋음", "조용함")),
        ("crowding", ("웨이팅적음", "대화하기좋음")),
    ),
    "city_park": (
        ("experience", ("조용함", "분위기좋음", "데이트좋음", "전망좋음")),
        ("crowding", ("웨이팅적음", "대화하기좋음")),
    ),
}

CATEGORY_ALIASES = {
    "bakery": "cafe",
    "food_service": "restaurant",
    "beach": "tourism",
}


def canonical_category(category):
    value = str(category or "").strip().lower()
    return CATEGORY_ALIASES.get(value, value)


def collection_profile(category):
    return COLLECTION_PROFILES.get(canonical_category(category), ())


def requested_tags_for_category(category):
    return list(dict.fromkeys(
        tag_name
        for _, tag_names in collection_profile(category)
        for tag_name in tag_names
    ))


def planned_requests_for_category(category):
    return len(collection_profile(category))


def collect_naver_place_evidence(place, requested_tags=None):
    """Collect multiple tag observations with one request per semantic pack."""
    requested = set(requested_tags or requested_tags_for_category(place.category))
    profiles = [
        (pack_name, tuple(tag for tag in tags if tag in requested and tag in TAG_TERMS))
        for pack_name, tags in collection_profile(place.category)
    ]
    profiles = [(name, tags) for name, tags in profiles if tags]
    if not profiles:
        return {"executed": True, "requests": 0, "evidences": [], "error": "unsupported_category"}

    location = " ".join(address_identity_terms(place.address)[-2:])
    evidences = []
    seen = set()
    requests_made = 0
    for pack_name, tag_names in profiles:
        keywords = " ".join(SEARCH_KEYWORDS.get(tag, tag) for tag in tag_names)
        query = "{} {} {}".format(place.name, location, keywords).strip()
        try:
            payload = _request_channel("blog", query)
            requests_made += 1
        except Exception:
            return {
                "executed": True,
                "requests": requests_made + 1,
                "evidences": evidences,
                "error": "request_failed",
            }

        for item in (payload or {}).get("items") or []:
            title = _clean_html(item.get("title"), 180)
            summary = _clean_html(item.get("description"), 500)
            combined = "{} {}".format(title, summary)
            if not identity_matches(place, combined):
                continue
            source_url = _safe_text(item.get("link"), 500)
            if not source_url.startswith(("http://", "https://")):
                continue
            for tag_name in tag_names:
                polarity = evidence_polarity(tag_name, combined)
                key = (tag_name, source_url, polarity)
                if polarity == "unknown" or key in seen:
                    continue
                seen.add(key)
                evidences.append({
                    "tag_name": tag_name,
                    "polarity": polarity,
                    "evidence_summary": summary or title,
                    "source_url": source_url,
                    "source_title": title,
                    "observed_date": item.get("postdate") or None,
                    "raw": {"channel": "naver_blog", "query": query, "pack": pack_name},
                })

    return {
        "executed": True,
        "requests": requests_made,
        "evidences": evidences,
        "error": "" if evidences else "insufficient_evidence",
    }
