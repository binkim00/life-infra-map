"""Canonical source names shared by evidence collection, aggregation, and review."""

NAVER_BLOG_SEARCH = "naver_blog_search"
WEB_SEARCH = "web_search"
WEB_EVIDENCE_SOURCES = frozenset({
    NAVER_BLOG_SEARCH,
    WEB_SEARCH,
    # Legacy values remain readable while existing rows are backfilled.
    "ai_suggested",
    "blog_search",
    "naver_search",
})

OFFICIAL_EVIDENCE_SOURCES = frozenset({"field_rule", "external_data", "external_api"})
USER_EVIDENCE_SOURCE = "user_feedback"
ADMIN_EVIDENCE_SOURCE = "admin_review"

# PlaceTag.source describes an aggregate, not the provider of one evidence row.
WEB_AGGREGATE_SOURCE = "web_evidence"


def evidence_source_for(raw):
    channel = str((raw or {}).get("channel") or "").strip().lower()
    if channel == "naver_blog":
        return NAVER_BLOG_SEARCH
    return WEB_SEARCH

