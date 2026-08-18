from datetime import datetime
from urllib.parse import urlsplit

from django.db.models import Q
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence
from recommendations.services.evidence_scoring import evidence_confidence, parse_observed_date
from recommendations.services.naver_tag_evidence_provider import polarity_assessment
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


def validate_candidate(row, *, now=None):
    now = now or timezone.now()
    result = {"status": "rejected", "reason": "", "candidate": row}
    research_status = str(row.get("research_status") or "").strip().upper()
    if research_status not in VALID_RESEARCH_STATUSES:
        result["reason"] = "INVALID_RESEARCH_STATUS"
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
    if tag not in CATEGORY_TAGS.get(place.category, ()):
        result["reason"] = "NON_CANONICAL_OR_CATEGORY_TAG"
        return result
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
    if extraction["polarity"] != polarity:
        result["reason"] = "POLARITY_OR_RULE_MISMATCH"
        return result
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
    status = "accepted" if source_type in {"official", "public", "brand_official"} and observed_at else "needs_verification"
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
            "extraction": {**extraction, "method": "rule"},
        },
    })
    return result
