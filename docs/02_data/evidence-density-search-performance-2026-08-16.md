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

## Refresh priority and second DB optimization

The ledger had not reset, so a fair A/B test of five sparse-feature query packs
was not run with only 132 safe requests remaining. Existing cafe web Evidence
was inspected instead: `콘센트` appeared in 103 snippets, Wi-Fi in 16, solo-use
language in 128, long-stay language in 5–6, and conversation language in 7–16.
The canonical aliases already cover the explicit safe phrases. No unmeasured
query pack or broader alias was promoted, and no additional Naver request was
made.

Bootstrap web refresh now distinguishes source semantics. Only expired web
Evidence reopens a recently processed Place for Naver collection; expired
official Evidence remains the responsibility of its structured source sync.
Volatile expired web tags (`웨이팅적음`, operating hours, outlet, Wi-Fi, work,
laptop, long stay) receive an extra explainable priority component. Current DB
counts were 55,760 stale Evidence rows: 2,442 web and 53,318 structured, with
346 Places holding volatile stale web Evidence. No stale row was deleted and
quota constraints meant actual refresh execution was zero.

Restaurant enrichment quality is also an ordering signal, never a deletion or
Place rejection policy. Of 91,316 Seoul restaurants, 5,768 were moved behind
higher-quality rows: 5,708 very short names, 259 with past identity mismatch,
133 institutional-context names, 122 contract-food operator names, and four
explicit institutional food-service names (flags can overlap). A 100-row human
validation CSV was generated at
`backend/tmp/restaurant_identity_validation_100.csv`; its labels remain blank.

PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` showed the direct restaurant query
sorting 23,463 wide Place rows including JSON and applying `DISTINCT`, taking
1,480.83 ms. Removing unnecessary `DISTINCT` reduced it to 907.64 ms. Ordering
with the existing PostGIS GiST KNN operator (`geog <-> point`) scanned only 181
rows to return 100 and took 121.20 ms, so no speculative index was added.

On the same 11 AI-off regression queries, all returned 10 results with zero
hard violations. A warm run changed average / median / p95 / max latency to
704.40 / 377.86 / 2,446.15 / 2,446.15 ms from the prior average 1,473.58 ms and
p95 4,075.13 ms. Average DB/evidence retrieval was 698.30 ms and Kakao 15.53 ms;
the two retrieval branches run concurrently. The remaining outliers are broad
semantic queries whose direct category set spans multiple categories.
