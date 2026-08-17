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

## API-yield adaptive collection

Before spending another provider request, `reextract_web_evidence_tags` ran the
current canonical rules over 3,134 stored web title/snippet rows. Dry-run found
328 new Evidence rows across 295 Place–Tag pairs; apply created all 328 and a
second dry-run found zero. The rows inherit source URL, source, observed time,
expiry, polarity context, and raw metadata. Of these, 92 are current and 236
remain stale; 59 new aggregate PlaceTag rows materialized. No external or AI
call was made.

The Bootstrap collector now uses two stages. Discovery issues one category-
appropriate high-yield query. It stops immediately when identity does not pass.
Only candidate hints, NO_TAG_EXPRESSION, stale web tags, or prior successful
identity/evidence trigger up to two targeted cluster queries. The current
22,368-request ledger left 132 safe requests; a 5,000-Place dry-run therefore
planned 125 Places with 132 requests (1.056 calls/Place), versus the historical
3.0 for cafe and 2.0 for restaurant.

Historical yield explains the discovery choice. Cafe work / ambience / visit
packs produced 827 / 1,688 / 149 Evidence rows from approximately 3,205 calls
each (0.258 / 0.527 / 0.046 Evidence per call). Restaurant visit / ambience
produced 326 / 93 from approximately 1,271 calls each (0.257 / 0.073). Targeted
clusters use one keyword per call and never concatenate multiple keywords as
AND-like search terms.

The request ledger, queued reservations, and 90% safety reserve now bound the
planner directly. Configurable initial bucket weights are Seoul cafe 45%, Busan
cafe 15%, high-quality restaurant 10%, sparse-targeted 15%, stale refresh 10%,
and exploration 5%. Unused shares spill to other buckets. After a bucket has at
least 200 calls with the new worker metrics, its active-Evidence/call yield
adjusts its next allocation within a 0.5–1.5 multiplier; small samples and old
jobs without active-yield metrics do not affect weights.

Current candidate hints provide 2,164 canonical Place–Tag targets across 1,585
Seoul/Busan cafe/restaurant Places without active Evidence. There are 800 prior
NO_TAG_EXPRESSION jobs with identity matches and 1,333 Places with stale web
Evidence. Replaying the historical mismatch/no-result mix with one-call
discovery would avoid an estimated 3,768 calls without lowering identity rules.

The optional AI extractor remains disabled. At most 800 current
NO_TAG_EXPRESSION rows meet the first eligibility screen. With the configured
`gpt-5-nano`, an illustrative 500–1,500 input and 100–300 output token request
costs about $0.000065–$0.000195 at the official $0.05/$0.40 per-million token
rates, or roughly $0.052–$0.156 for 800 calls. This is only a token-assumption
estimate, not an authorization to enable calls. Pricing source:
https://developers.openai.com/api/docs/models/gpt-5-nano

The final 11-query AI-off regression returned ten results each, no results in
zero cases, and zero hard violations among 55 inspected results. Average / p95
latency was 847.16 / 3,061.84 ms, with DB 840.07 ms and Kakao 10.98 ms average.

## 2026-08-17 yield run

The new quota cycle started with 240 requests already consumed by the previous
container image. After rebuilding scheduler and worker from the current branch,
a same-Place 50-row A/B used 250 requests. Discovery produced 0.06 Evidence per
call; WORK_INFRA 0.14; SOLO 0.06; LONG_STAY 0.02; TALK 0.06. Only WORK_INFRA is
adopted by default. Unadopted packs remain available to the bounded evaluation
command and cannot silently enter the daily collector.

The adaptive 500 run used 528 requests (1.056 calls/Place), returned 181 raw
Evidence observations, created 123 Evidence rows and 21 PlaceTag rows, and added
23 net active Evidence rows. The following 2,000-row discovery run used exactly
2,000 calls but its raw yield fell to 0.1175 Evidence/call, so no 5,000-row
expansion was attempted. A NO_TAG_EXPRESSION WORK_INFRA pass then used 612 calls
over all 612 available distinct Seoul cafe targets and created 248 Evidence rows
(31 net active) and 28 PlaceTag rows. Its two cohorts yielded 0.614 and 0.337
Evidence/call.

A stale WORK_INFRA test used 200 calls and created 130 Evidence rows, but only
two were current; old blog posts dominated. This is why dynamic budget history
now stores `new_evidences`, `active_evidences`, and `new_active_evidences` and
optimizes the active metric instead of rewarding stale volume. Existing stale
rows are preserved.

After API-free re-extraction, the remaining active-gap WORK Candidate hints
were entirely in Busan cafe (97 distinct Places; Seoul had zero). Candidate
values were used only as query hints. One targeted call per Place found 224
observations, created 199 Evidence rows, 19 active Evidence rows, and 19
PlaceTag rows: 2.309 Evidence/call and 0.196 new-active/call. The Candidate rows
themselves were never treated as proof or promoted without the fetched source.
One further API-free pass recovered one grounded `조용함` row and was then
idempotent.

Stored-snippet context analysis added only repeated grounded aliases: explicit
outlet presence, 1-person seating/solo-cafe wording, long laptop work, and
positive conversation wording. Generic `장시간` was rejected because sampled
uses frequently described limits or bans. API-free re-extraction created 214
additional rows across 200 Place–Tag pairs; 49 inherited current expiry and 165
remained stale. A second dry-run returned zero.

Final warm AI-off regression remained healthy: 11/11 queries returned ten
results, hard violations were 0/55, and no-result/fallback were both zero.
Average / median / p95(max) latency was 718.67 / 413.09 / 2,427.26 ms. Average
DB/evidence loading was 712.14 ms and Kakao was 15.53 ms.

Official brand pages are a possible next source, but no bulk adapter was added.
The official Hollys store finder states that Wi-Fi is available at all stores
except rest-area and special stores and exposes store-specific parking,
terrace, and 24-hour filters. The official Starbucks finder exposes parking
and store-type/service filters, but not outlet availability. Neither inspected
page provided a clear bulk-reuse/API license, and the Hollys exception requires
store-level exclusion data, so treating every matched brand Place as having the
feature would be unsafe. Sources inspected:
`https://www.hollys.co.kr/store/korea/korStore.do` and
`https://www.starbucks.co.kr/store/store_map.do?disp=locale`.

## 2026-08-17 Candidate-first coverage run

The sparse-pack evaluator now records idempotent per-place checkpoints in
`PlaceTagCollectionJob.context.targeted_attempts`. Candidate hints choose the
query feature but never become Evidence. Candidate rows use the existing
bootstrap priority score, and same-day NO_TAG runs exclude already targeted
places.

| bucket | calls | new Evidence | new active | new PlaceTag | active/call |
| --- | ---: | ---: | ---: | ---: | ---: |
| Busan cafe Candidate ambience/date (first) | 500 | 615 | 211 | 171 | 0.422 |
| Busan cafe Candidate ambience/date (remainder) | 1,052 | 725 | 275 | 195 | 0.261 |
| Busan cafe Candidate solo | 89 | 82 | 10 | 5 | 0.112 |
| Seoul cafe NO_TAG work | 500 | 45 | 9 | 7 | 0.018 |
| Seoul restaurant ambience | 67 | 12 | 3 | 3 | 0.045 |
| Seoul restaurant solo | 67 | 3 | 0 | 0 | 0.000 |
| Seoul cafe stale work | 50 | 8 | 0 | 0 | 0.000 |

Candidate ambience/date was exhausted instead of filling the requested batch
with general Discovery. The final Naver ledger was 6,380 requests, 6,375
successes, five pre-existing failures and zero 429 responses.

An explicitly bounded AI experiment covered 100 NO_TAG discovery places.
`gpt-5-nano` was called 28 times; 21 rows passed the canonical-tag, polarity,
identity and verbatim-span validators (18 laptop-work, 3 work-friendly), and
four were current at the final snapshot. The daily AI extractor remains off.
At the official $0.05/M input and $0.40/M output token rates, even the configured
500-output-token ceiling keeps these 28 calls below $0.01; the current JSON
client does not expose exact token usage.

Final changes from the start snapshot:

- Busan cafe active Evidence places 296 -> 540; atmosphere 159 -> 313,
  quiet 118 -> 205, date 20 -> 56, solo 6 -> 11.
- Seoul cafe active Evidence places 140 -> 147; laptop 86 -> 92,
  outlet 15 -> 17, quiet 42 -> 44.
- Seoul restaurant active Evidence places 8 -> 9. Its measured yield did not
  justify a larger budget share.
- API-free re-extraction scanned 6,076 web rows and created four grounded rows
  (quiet 2, date 1, atmosphere 1).

The final warm 11-query AI-off regression returned ten results per query, zero
hard violations and zero no-result cases. Average/p95 latency was
670.55/1,865.96 ms.
