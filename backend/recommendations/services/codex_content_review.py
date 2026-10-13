"""Independent safety gates for a Codex second pass on held web evidence."""

import difflib
import hashlib
import re

from recommendations.models import PlaceTagEvidence
from recommendations.services.automatic_content_review import compact, roads
from recommendations.services.naver_tag_evidence_provider import polarity_assessment
from recommendations.services.public_page_tag_evidence import fetch_public_page
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES


def assess_codex_verdict(row, review, seed, result, *, page_cache=None):
    """Only a positive, re-fetched, source-bound verdict may change a hold."""
    if review.status != "pending" or review.reviewer_id or not review.history or review.history[-1].get("mode") != "automatic_content":
        return "not_automatic_pending"
    if row.source not in WEB_EVIDENCE_SOURCES or row.polarity != "positive":
        return "unsupported_source_or_polarity"
    if result.get("decision") != "approve":
        return "model_held"
    if (result.get("id") != row.id or seed.get("id") != row.id
            or result.get("quote_hash") != seed.get("quote_hash")
            or seed.get("quote_hash") != hashlib.sha256(row.evidence.encode()).hexdigest()
            or seed.get("updated_at") != row.updated_at.isoformat()
            or seed.get("place_id") != row.place_id
            or seed.get("tag") != row.tag.name
            or seed.get("polarity") != row.polarity
            or seed.get("source_url") != row.source_reference
            or result.get("source_url") != row.source_reference):
        return "input_or_source_drift"
    span = " ".join(str(result.get("source_span") or "").split())
    if len(span) < 20 or len(span) > 600:
        return "source_span_length"
    cache = page_cache if page_cache is not None else {}
    if row.source_reference not in cache:
        cache[row.source_reference] = fetch_public_page(row.source_reference)
    page = cache[row.source_reference]
    if not page.get("ok"):
        return "source_unavailable"
    page_text = " ".join(str(page.get("text") or "").split())
    if span not in page_text:
        return "source_span_not_found"
    name = compact(row.place.name)
    if len(name) < 4 or name not in compact(span):
        return "place_not_in_claim"
    place_roads = roads(row.place.address)
    page_compact = compact(page_text)
    if not place_roads or not any(re.search(re.escape(road) + r"(?!\d)", page_compact) for road in place_roads):
        return "address_not_verified"
    stored = compact(row.evidence[:4000])
    source = compact(span)
    if difflib.SequenceMatcher(None, stored, source, autojunk=False).find_longest_match(
            0, len(stored), 0, len(source)).size < 20:
        return "stored_quote_not_same_claim"
    assessment = polarity_assessment(row.tag.name, span, category=row.place.category)
    if assessment["polarity"] == "negative":
        return "opposite_claim"
    if assessment["polarity"] != "positive":
        return "direct_claim_not_verified"
    if row.tag.name == "노트북작업" and not re.search(r"노트북|랩탑|laptop", span, re.IGNORECASE):
        return "laptop_not_explicit"
    if PlaceTagEvidence.objects.filter(
            place_id=row.place_id, tag_id=row.tag_id, polarity="negative",
            review__status="approved").exclude(pk=row.id).exists():
        return "conflicting_approved_claim"
    return "approve"
