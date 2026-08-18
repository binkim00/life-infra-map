# Naver + Web Evidence Hybrid Pipeline

## Scope

The focused region remains Busan and the eligible categories are `cafe` and
`restaurant`. Semantic retrieval remains disabled in production. Web evidence
search is a second-stage coverage-gap provider, not a replacement for Naver.

## Routing

1. Reuse structured and official evidence.
2. Reuse existing Naver blog evidence and completed identity diagnostics.
3. Paid Web Search may discover only URL, title, domain, query, and response diagnostics.
4. A separate, policy-allowed page verification step establishes exact-place identity and a verbatim span.
5. The validator enforces canonical tag, category profile, polarity rule, freshness, and duplicate checks.
6. Only validator-passed rows may later be imported as `source=web_search`; Web-only evidence never confirms a tag.

`WEB_EVIDENCE_SEARCH_ENABLED` defaults to `false`. The explicit pilot command
can execute without enabling the scheduler route. No automatic planner route is
enabled until pilot yield and human identity review support it.

## Source and storage policy

Allowed sources are official store or brand pages, public institutions and
tourism pages, public blogs, articles, and public web documents. Naver Map,
Kakao Map, Google Maps, map reviews, login-only pages, and inaccessible pages
are rejected. The database stores URL, canonical URL, title, source type,
published date when available, retrieval timestamp, and a short evidence span.
It does not store whole pages.

An unknown publication date remains unknown in `observed_at`; retrieval time is
used only as the TTL anchor. A Web-only row cannot become confirmed by itself.
The existing independent-evidence and conflict policy remains authoritative.

## Cost policy

OpenAI Web Search is priced at `$10 / 1,000 calls` plus search-content tokens at
the selected model rate. The pilot uses a `$5` total hard cap, a daily request
limit, exact token usage from Responses API, and a conservative `$0.02` reserve
per provider request. A 200-place one-query pilot has a minimum tool cost of
about `$2`. An additional 500-place run cannot fit in the same `$5` task budget
and is therefore not automatically executed.

## Commands

Dry-run selection and Naver-only baseline:

```powershell
python manage.py pilot_web_tag_evidence --cafe 100 --restaurant 100
```

Paid discovery remains disabled after the 2026-08-18 pilot. The historical
99 requests produced 255 tool actions, 97 source candidates, 2 provider errors,
and no final structured output or Evidence. Historical `PAGE_NOT_ACCESSIBLE`
rows are report-classified as `NO_FINAL_OUTPUT` without rewriting DB history.

Failure and corrected cost report:

```powershell
python manage.py report_web_search_failures --date 2026-08-18
```

Codex research seed and dry-run validation:

```powershell
python manage.py prepare_codex_web_research --cafe 50 --restaurant 50
python manage.py validate_codex_web_evidence tmp/codex_web_evidence_busan_pilot.json --dry-run
```

Outputs are written under `backend/tmp` as baseline JSON, result JSON, and a
30-row review CSV. Human review columns are intentionally blank.

## Routing decision fields

The result artifact reports tag-level searched places, provider/tool calls,
sources checked, new evidence, new active evidence, active/API, cost/active,
failure reasons, source types, latency, and incremental PlaceTag creation.
Operational routing must be based on these measured values rather than the
example feature lists in the implementation request.
