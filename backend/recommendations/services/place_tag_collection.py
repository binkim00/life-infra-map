"""Place-level collection profiles and multi-tag evidence extraction."""

from django.conf import settings

from recommendations.services.naver_search_provider import _clean_html, _request_channel, _safe_text
from recommendations.services.naver_tag_evidence_provider import (
    SEARCH_KEYWORDS,
    TAG_TERMS,
    address_identity_terms,
    identity_assessment,
    polarity_assessment,
)
from recommendations.services.evidence_scoring import evidence_confidence, parse_observed_date
from recommendations.services.tag_source_policy import NAVER_BLOG_SEARCH
from recommendations.services.provider_rate_limit import acquire_provider_slot


COLLECTION_PROFILES = {
    "cafe": (
        ("work", ("노트북작업", "콘센트있음", "무료와이파이", "작업하기좋음", "장기체류좋음")),
        ("ambience", ("분위기좋음", "조용함", "데이트좋음", "대화하기좋음")),
        ("visit", ("전망좋음", "웨이팅적음")),
    ),
    "restaurant": (
        ("visit", ("혼밥좋음", "웨이팅적음", "데이트좋음", "대화하기좋음", "가족동반좋음")),
        ("ambience", ("분위기좋음", "조용함", "전망좋음")),
    ),
    "tourism": (
        ("experience", ("전망좋음", "분위기좋음", "데이트좋음", "조용함")),
        ("crowding", ("웨이팅적음", "대화하기좋음")),
    ),
    "city_park": (
        ("experience", ("조용함", "분위기좋음", "데이트좋음", "전망좋음", "산책좋음", "가족동반좋음", "야외활동좋음")),
        ("crowding", ("웨이팅적음", "대화하기좋음")),
    ),
    "library": (
        ("work", ("노트북작업", "콘센트있음", "무료와이파이", "작업하기좋음")),
        ("stay", ("조용함", "장기체류좋음")),
    ),
    "beach": (
        ("experience", ("전망좋음", "조용함", "가족동반좋음", "야외활동좋음")),
    ),
    "parking": (
        ("access", ("24시간운영", "장애인전용주차")),
        ("pricing", ("무료이용",)),
    ),
    "toilet": (
        ("access", ("휠체어접근", "장애인시설", "24시간운영")),
        ("condition", ("관리잘됨",)),
    ),
    "shelter": (
        ("access", ("24시간운영", "휠체어접근", "장애인시설")),
    ),
}

CATEGORY_ALIASES = {
    "bakery": "cafe",
    "food_service": "restaurant",
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


def collect_naver_place_evidence(place, requested_tags=None, *, allow_ai=False):
    """Collect multiple tag observations with one request per semantic pack."""
    requested = set(requested_tags or requested_tags_for_category(place.category))
    profiles = [
        (
            pack_name,
            SEARCH_KEYWORDS.get(tags[0], tags[0]),
            tuple(tag for tag in tags if tag in requested and tag in TAG_TERMS),
        )
        for pack_name, tags in collection_profile(place.category)
    ]
    profiles = [(name, keyword, tags) for name, keyword, tags in profiles if tags]
    if not profiles:
        return {"executed": True, "requests": 0, "evidences": [], "error": "unsupported_category"}

    location = " ".join(address_identity_terms(place.address)[-2:])
    evidences = []
    seen = set()
    requests_made = 0
    diagnostics = {"search_results": 0, "identity_matches": 0, "tag_expressions": 0, "short_snippets": 0}
    ai_calls = 0
    for pack_name, keyword, tag_names in profiles:
        # Naver treats a long list of semantic words as restrictive search terms.
        # Search with one representative word, then extract every tag in the pack
        # from the returned title/summary.
        query = "{} {} {}".format(place.name, location, keyword).strip()
        try:
            acquire_provider_slot("naver_search")
            payload = _request_channel("blog", query)
            requests_made += 1
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            return {
                "executed": True,
                "requests": requests_made + 1,
                "evidences": evidences,
                "error": "rate_limited" if status_code == 429 else "request_failed",
                "miss_reason": "OTHER",
                "diagnostics": diagnostics,
            }

        for item in (payload or {}).get("items") or []:
            diagnostics["search_results"] += 1
            title = _clean_html(item.get("title"), 180)
            summary = _clean_html(item.get("description"), 500)
            combined = "{} {}".format(title, summary)
            identity = identity_assessment(place, combined)
            if not identity["matched"]:
                continue
            diagnostics["identity_matches"] += 1
            if len(combined.strip()) < 60:
                diagnostics["short_snippets"] += 1
            source_url = _safe_text(item.get("link"), 500)
            if not source_url.startswith(("http://", "https://")):
                continue
            snippet_evidences = 0
            for tag_name in tag_names:
                extraction = polarity_assessment(tag_name, combined)
                polarity = extraction["polarity"]
                key = (tag_name, source_url, polarity)
                if polarity == "unknown" or key in seen:
                    continue
                diagnostics["tag_expressions"] += 1
                snippet_evidences += 1
                seen.add(key)
                observed_at = parse_observed_date(item.get("postdate"))
                confidence, confidence_factors = evidence_confidence(
                    source=NAVER_BLOG_SEARCH,
                    identity_score=identity["score"],
                    clarity_score=extraction["clarity_score"],
                    observed_at=observed_at,
                )
                evidences.append({
                    "tag_name": tag_name,
                    "polarity": polarity,
                    "evidence_summary": summary or title,
                    "source_url": source_url,
                    "source_title": title,
                    "observed_date": item.get("postdate") or None,
                    "confidence": confidence,
                    "identity": identity,
                    "extraction": extraction,
                    "confidence_factors": confidence_factors,
                    "raw": {"channel": "naver_blog", "query": query, "pack": pack_name},
                })
            if (
                allow_ai
                and snippet_evidences == 0
                and ai_calls < getattr(settings, "TAG_COLLECTION_AI_MAX_CALLS_PER_PLACE", 1)
            ):
                from recommendations.services.canonical_ai_evidence_extractor import (
                    extract_canonical_tags_from_evidence,
                )
                ai_calls += 1
                for extracted in extract_canonical_tags_from_evidence(combined, tag_names):
                    key = (extracted["tag_name"], source_url, extracted["polarity"])
                    if key in seen:
                        continue
                    seen.add(key)
                    diagnostics["tag_expressions"] += 1
                    confidence, confidence_factors = evidence_confidence(
                        source=NAVER_BLOG_SEARCH,
                        identity_score=identity["score"],
                        clarity_score=65,
                        observed_at=parse_observed_date(item.get("postdate")),
                    )
                    evidences.append({
                        "tag_name": extracted["tag_name"],
                        "polarity": extracted["polarity"],
                        "evidence_summary": extracted["evidence_span"],
                        "source_url": source_url,
                        "source_title": title,
                        "observed_date": item.get("postdate") or None,
                        "confidence": confidence,
                        "identity": identity,
                        "extraction": {"method": "ai", "evidence_span": extracted["evidence_span"]},
                        "confidence_factors": confidence_factors,
                        "raw": {"channel": "naver_blog", "query": query, "pack": pack_name},
                    })

    miss_reason = ""
    if not evidences:
        if diagnostics["search_results"] == 0:
            miss_reason = "NO_SEARCH_RESULT"
        elif diagnostics["identity_matches"] == 0:
            miss_reason = "IDENTITY_MISMATCH"
        elif diagnostics["short_snippets"] == diagnostics["identity_matches"]:
            miss_reason = "INSUFFICIENT_SNIPPET"
        elif diagnostics["tag_expressions"] == 0:
            miss_reason = "NO_TAG_EXPRESSION"
        else:
            miss_reason = "OTHER"
    return {
        "executed": True,
        "requests": requests_made,
        "evidences": evidences,
        "error": "" if evidences else "insufficient_evidence",
        "miss_reason": miss_reason,
        "diagnostics": diagnostics,
        "ai_calls": ai_calls,
    }
