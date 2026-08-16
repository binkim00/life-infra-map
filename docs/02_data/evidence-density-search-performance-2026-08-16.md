# Evidence density and search performance — 2026-08-16

## Seoul cafe bootstrap

The remaining Naver 90% safety budget was 4,332 requests. A region/category
bounded bootstrap planned 1,300 Seoul cafes at three requests per Place, leaving
quota for restaurant diagnostics.

- Places processed: 1,300
- Naver requests: 3,900
- Evidence-hit Places: 305 (23.46%)
- new Naver Evidence: 607
- new PlaceTags: 65 (`candidate` 2, `needs_verification` 63)
- misses: identity 645, no result 116, no tag expression 234
- new failures / 429: 0 / 0

Seoul cafe coverage changed as follows:

| Metric | Before | After |
| --- | ---: | ---: |
| Evidence Places | 92 | 397 |
| active Evidence Places | 12 | 62 |
| stale Evidence Places | 89 | 373 |
| active Tag coverage | 0.0063% | 0.0344% |
| quiet | 1 | 17 |
| work-friendly | 1 | 9 |
| laptop | 8 | 28 |
| ambience | 3 | 21 |
| date-friendly | 1 | 2 |

Outlet, Wi-Fi, solo-use, conversation, and long-stay active coverage remains
zero in Seoul. Stored snippets contain direct but previously unmapped variants,
so only repeated explicit aliases were added. No existing Evidence was
reclassified or backfilled automatically.

## Restaurant identity diagnostics

One hundred recent restaurant mismatches were re-queried with 200 requests.
The original diagnostic reasons were:

- name mismatch 76
- wrong search result 12
- branch mismatch 6
- identity threshold 4
- region mismatch 1
- insufficient identity information 1

Sixty-four of the `NAME_MISMATCH` rows actually had zero place-name signal and
only a broad address token, so diagnostics now classify those as wrong search
results. SEMAS lot addresses retain the neighborhood that road addresses omit;
collection queries now prefer district + neighborhood without lowering the
identity threshold.

On the same latest 50 jobs, the specific query produced five identity passes,
but manual evidence inspection showed that three were incidental summary
mentions of another Place. SEMAS cafe/restaurant results therefore require the
exact normalized Place name in the result title. The conservative usable
improvement is 0/50 to 2/50; no bulk restaurant batch was run.

## Location and latency

Administrative aliases use DB-derived coordinate medians before Kakao POI
search. Seoul, Busan, their full metropolitan names, Gangnam-gu, and
Haeundae-gu are covered. Existing neighborhood/station anchors such as Seomyeon,
Busan Station, and Hadan Station remain more specific.

The search reranker now has an independent `AI_RERANK_ENABLED` feature flag.
It is disabled in the local AI-off environment, preventing failed/undesired AI
attempts while retaining deterministic evidence-first ranking and hard gates.
Explicit category retrieval applies its category constraint before the wide
PlaceTag text join.

Eleven identical regression queries produced ten results each and zero hard
violations among the inspected top 55.

| Latency | Before | After |
| --- | ---: | ---: |
| average | 6,816.26 ms | 1,473.58 ms |
| p95 | 9,550.85 ms | 4,075.13 ms |

Final average stage timings were intent 1.54 ms, location 0.01 ms, DB/evidence
retrieval 1,336.95 ms, Kakao 882.61 ms, filtering 0.95 ms, deterministic ranking
0.27 ms, reranker 0.01 ms, and response assembly 3.53 ms. DB and Kakao retrieval
run in parallel, so their values are not additive. The remaining search
bottleneck is DB candidate/evidence retrieval for large Seoul categories.

Final Naver ledger: 22,368 / 25,000 requests, 21,864 successful, 504 historical
failed, four historical 429, and 132 requests remaining below the 90% safety
line. OpenAI calls for this work were zero.
