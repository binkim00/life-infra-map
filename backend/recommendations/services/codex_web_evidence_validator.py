from datetime import datetime
from urllib.parse import urlsplit

from django.db.models import Q
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence
from recommendations.services.evidence_scoring import evidence_confidence, parse_observed_date
from recommendations.services.naver_tag_evidence_provider import polarity_assessment
from recommendations.services.public_page_tag_evidence import fetch_public_page
from recommendations.services.web_tag_evidence_provider import (
    CATEGORY_TAGS,
    canonical_url,
    is_blocked_source,
)


VALID_POLARITIES = {"positive", "negative"}
VALID_SOURCE_TYPES = {"official", "public", "brand_official", "blog", "news", "web_content"}
VALID_RESEARCH_STATUSES = {
    "FOUND", "NO_RESULT", "PAGE_UNAVAILABLE", "IDENTITY_MISMATCH",
    "NO_FEATURE_EVIDENCE", "AMBIGUOUS", "STALE_ONLY",
}


def validate_candidate(row, *, now=None, live_verify=False, live_page_cache=None):
    now = now or timezone.now()
    result = {"status": "rejected", "reason": "", "candidate": row}
    research_status = str(row.get("research_status") or "").strip().upper()
    if research_status not in VALID_RESEARCH_STATUSES:
        result["reason"] = "INVALID_RESEARCH_STATUS"
        return result
    if research_status == "PAGE_UNAVAILABLE":
        result["status"] = "candidate_pending"
        result["reason"] = research_status
        result["candidate_sources"] = normalize_candidate_sources(row)
        return result
    if research_status != "FOUND":
        result["status"] = "ambiguous" if research_status == "AMBIGUOUS" else "rejected"
        result["reason"] = research_status
        return result
    try:
        place = Place.objects.get(id=int(row.get("place_id")))
    except (Place.DoesNotExist, TypeError, ValueError):
        result["reason"] = "PLACE_NOT_FOUND"
        return result
    if str(row.get("place_name") or "").strip() != place.name:
        result["reason"] = "PLACE_IDENTITY_MISMATCH"
        return result
    if row.get("category") != place.category:
        result["reason"] = "CATEGORY_MISMATCH"
        return result
    tag = str(row.get("extracted_tag") or row.get("target_tag") or "").strip()
    if row.get("extracted_tag") and str(row.get("target_tag") or "").strip() != tag:
        result["reason"] = "TARGET_EXTRACTED_TAG_MISMATCH"
        return result
    if tag not in CATEGORY_TAGS.get(place.category, ()):
        result["reason"] = "NON_CANONICAL_OR_CATEGORY_TAG"
        return result
    if live_verify:
        verified, reason = verify_live_source(place, row, page_cache=live_page_cache)
        if reason:
            result["reason"] = reason
            return result
        row = verified
        result["candidate"] = row
    if row.get("page_verified") is not True or row.get("source_candidate_only") is True:
        result["reason"] = "PAGE_NOT_VERIFIED"
        return result
    identity_status = str(row.get("identity_status") or "").lower()
    identity_score = int(row.get("identity_confidence") or 0)
    if identity_status not in {"pass", "verified"} or identity_score < 70:
        result["status"] = "ambiguous"
        result["reason"] = "IDENTITY_MISMATCH"
        return result
    url = canonical_url(row.get("source_url"))
    if not url or is_blocked_source(url):
        result["reason"] = "SOURCE_POLICY_REJECTED"
        return result
    if str(row.get("source_type") or "") not in VALID_SOURCE_TYPES:
        result["reason"] = "SOURCE_TYPE_REJECTED"
        return result
    span = str(row.get("evidence_span") or "").strip()
    if len(span) < 3:
        result["reason"] = "EVIDENCE_SPAN_REQUIRED"
        return result
    polarity = str(row.get("polarity") or "").strip().lower()
    if polarity not in VALID_POLARITIES:
        result["reason"] = "INVALID_POLARITY"
        return result
    extraction = polarity_assessment(tag, span, category=place.category)
    semantic_quote_fallback = False
    if extraction["polarity"] != polarity:
        # The live verifier has already re-fetched the page, found the exact
        # quoted span, and matched the place identity.  A deterministic term
        # list can still miss natural Korean paraphrases (for example
        # "예뻤던 카페" for 분위기좋음).  Preserve those grounded claims as
        # low-confidence evidence instead of discarding them.  Never use this
        # fallback without live verification, or when the rule engine found
        # the opposite polarity.
        if not live_verify or extraction["polarity"] != "unknown":
            result["reason"] = "POLARITY_OR_RULE_MISMATCH"
            return result
        semantic_quote_fallback = True
        extraction = {
            **extraction,
            "polarity": polarity,
            "clarity_score": 45,
            "strength": "SEMANTIC_QUOTE",
            "semantic_quote_fallback": True,
        }
    duplicate = PlaceTagEvidence.objects.filter(
        place=place, tag__name=tag, polarity=polarity, source_reference=url,
    ).exists()
    if duplicate:
        result["status"] = "duplicate"
        result["reason"] = "DUPLICATE_EVIDENCE"
        return result
    published_at = str(row.get("published_at") or "").strip()
    observed_at = parse_observed_date(published_at)
    source_type = str(row.get("source_type") or "")
    confidence, factors = evidence_confidence(
        source="web_search",
        identity_score=identity_score,
        clarity_score=extraction["clarity_score"],
        observed_at=observed_at,
    )
    if semantic_quote_fallback:
        confidence = min(confidence, 55)
        factors = {**factors, "semantic_quote_fallback": True}
    status = (
        "accepted"
        if not semantic_quote_fallback
        and source_type in {"official", "public", "brand_official"}
        and observed_at
        else "needs_verification"
    )
    result.update({
        "status": status,
        "reason": "",
        "normalized": {
            "place": place,
            "tag_name": tag,
            "polarity": polarity,
            "source_url": url,
            "source_title": str(row.get("source_title") or "")[:180],
            "source_domain": urlsplit(url).netloc.lower(),
            "source_type": source_type,
            "evidence_summary": span,
            "observed_at": observed_at,
            "confidence": confidence,
            "confidence_factors": factors,
            "identity": {"matched": True, "score": identity_score, "source": "codex_page_verification"},
            "extraction": {
                **extraction,
                "method": "semantic_quote_fallback" if semantic_quote_fallback else "rule",
            },
        },
    })
    return result


def verify_live_source(place, row, *, page_cache=None):
    """Re-fetch the cited page and replace model-reported verification fields."""
    cache_key = canonical_url(row.get("source_url"))
    if page_cache is not None and cache_key in page_cache:
        page = page_cache[cache_key]
    else:
        page = fetch_public_page(row.get("source_url"))
        if page_cache is not None and cache_key:
            page_cache[cache_key] = page
    if not page.get("ok"):
        return None, "LIVE_{}".format(page.get("error") or "FETCH_FAILED")

    span = str(row.get("evidence_span") or "").strip()
    page_text = " ".join(str(page.get("text") or "").split())
    normalized_span = " ".join(span.split())
    if not normalized_span or normalized_span not in page_text:
        return None, "LIVE_EVIDENCE_SPAN_MISMATCH"

    compact_name = _compact(place.name)
    identity_text = "{} {}".format(page.get("title") or "", page_text[:1500])
    if not compact_name or compact_name not in _compact(identity_text):
        return None, "LIVE_PLACE_IDENTITY_MISMATCH"

    host = urlsplit(page.get("url") or row.get("source_url") or "").netloc.lower()
    source_type = "blog" if "blog" in host or host.endswith("tistory.com") else "web_content"
    verified = dict(row)
    verified.update({
        "source_url": page.get("url") or row.get("source_url"),
        "source_title": page.get("title") or row.get("source_title") or "",
        "source_type": source_type,
        "published_at": page.get("published_at") or "unknown",
        "identity_status": "verified",
        "identity_confidence": 90,
        "page_verified": True,
        "source_candidate_only": False,
    })
    return verified, ""


def _compact(value):
    return "".join(character.lower() for character in str(value or "") if character.isalnum())


def normalize_candidate_sources(row):
    """Retain safe retry metadata without treating snippets as tag evidence."""
    normalized = []
    seen = set()
    sources = row.get("candidate_sources")
    if not isinstance(sources, list):
        sources = []
    for source in sources[:5]:
        if not isinstance(source, dict):
            continue
        url = canonical_url(source.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        source_type = str(source.get("source_type") or "")
        normalized.append({
            "url": url,
            "title": str(source.get("title") or "")[:180],
            "snippet": str(source.get("snippet") or "")[:500],
            "source_type": source_type if source_type in VALID_SOURCE_TYPES else "",
            "access_error": str(source.get("access_error") or "")[:120],
        })
    return normalized
