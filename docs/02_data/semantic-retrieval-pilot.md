# Semantic Retrieval 100-document pilot

## Scope and safety

The pilot is feature-flagged and remains disabled by default. It never creates a
Place or a Feature. `PlaceFeatureDocument` is built from the Place name,
category, region/address and active positive Canonical Tags. Stale Evidence,
negative Evidence, `rejected`, and `needs_verification` PlaceTags are excluded.

Three deterministic document renderers are available:

- `tags`: Canonical Tag names only.
- `contextual`: Place name, category, region and Canonical Tags.
- `full`: the existing fact-only FeatureDocument.

The 100-document run used `contextual`. No generated recommendation sentence is
stored. Documents without a supported Feature remain in the registry but are
not selected for embedding.

## Storage decision

The pilot reuses the existing JSON embedding on `PlaceFeatureDocument`. It adds
`embedding_strategy` and `embedding_source_hash` so an unchanged document is
not billed twice. Provider, model, dimensions and `indexed_at` are already
stored. This is appropriate for 100 rows and Python cosine comparison.

For production, a separate `PlaceFeatureEmbedding` vector entity is preferred:
it allows multiple providers/models/dimensions, reversible re-indexing and an
independent pgvector index. That migration is intentionally not included until
the operating DB image supports pgvector.

## pgvector compatibility

The operating DB remains `postgis/postgis:16-3.4`; its volume and image were not
changed. A temporary image derived from it installed
`postgresql-16-pgvector`. In a disposable database, PostgreSQL 16.15, PostGIS
3.4.3 and pgvector 0.8.6 successfully coexisted. `CREATE EXTENSION vector` and a
three-row cosine-distance query succeeded. The container uses no operating
volume; the expanded pilot keeps a separate development instance for inspection.

## Pilot result

- Embedded documents: 100/100
- Provider/model: OpenAI `text-embedding-3-small`
- Dimensions: 512
- Document input tokens: 2,423
- Estimated document cost: USD 0.00004846
- Embedding latency: 4,410.99 ms
- Storage latency: 1,460.98 ms
- Immediate rerun: 100 unchanged, 0 API calls
- Evaluation queries: 20
- Top-K export: 20 per query, 400 rows
- Query tokens: 294 per evaluation run
- Query embedding latency: 1,317.11 ms for one batch
- Average Python vector search: 104.35 ms per query over 100 vectors

The sample is intentionally small but is biased toward 부산 cafe and
`분위기좋음`/`전망좋음`. Direct queries such as 조용한 카페 and 노트북 작업
produced natural candidates. Hard+semantic queries for 무료, Wi-Fi or 장애인
시설 exposed the expected limitation: semantic similarity is not proof of a
hard condition. Hard filtering therefore remains upstream and the vector score
is only one Hybrid Ranking component.

## Commands

```bash
python manage.py build_place_feature_documents --category cafe --require-features --limit 100
python manage.py embed_place_feature_documents --limit 100 --strategy contextual --dry-run
python manage.py embed_place_feature_documents --limit 100 --strategy contextual
python manage.py evaluate_semantic_pilot --top-k 20
```

The evaluation CSV leaves `relevant` and `notes` blank. Recall, MRR and NDCG are
`NOT_MEASURED` until a person supplies relevance labels.

## Expansion gate

The storage and idempotency gates passed, but 1,000-document expansion is not
automatic. First create a stratified Region × Category × Tag sample, collect
human relevance labels for the 20-query set, and run the pgvector-backed query
path against a restored copy of the development database. Production default
remains `SEMANTIC_RETRIEVAL_ENABLED=false`.

## 1,000-document stratified pilot (2026-08-18)

The second pilot selects only Places with current positive Evidence and a
searchable `confirmed` or sufficiently confident `candidate` PlaceTag. It
excludes stale, negative, rejected and needs-verification facts. Selection is
stratified across seven regions, eight useful categories and Work,
Solo/Social, Outdoor and Facility feature clusters; it is not random.

- Regions: Seoul 149, Busan 250, Incheon 126, Daegu 136, Daejeon 115,
  Gwangju 101, Ulsan 123.
- Categories: cafe 211, restaurant 3, city park 251, library 133, parking
  130, shelter 128, toilet 109, tourism 35.
- Feature counts per document: one 217, two 305, three 414, four 64.
- Documents: 914 new, 0 updated, 86 unchanged, 0 skipped.
- Embedding: 1,000/1,000 successful; 914 newly called and 86 reused.
- Input tokens: 35,100; estimated cost: USD 0.000702 at USD 0.02 per million
  input tokens; embedding time 14,731.29 ms; DB write time 3,728.21 ms.
- Immediate rerun: 1,000 unchanged and zero API calls.

## Separate pgvector development database

The operating PostGIS database and volume were not changed. A separate,
volume-free development container named `semantic-pgvector-pilot` runs
PostgreSQL 16.15, PostGIS 3.4.3 and pgvector 0.8.6. It contains only the pilot
embedding table. `vector(512)`, cosine `<=>`, and an HNSW
`vector_cosine_ops` index were verified together. After `ANALYZE`, the measured
Top-20 SQL plan used the HNSW index and executed in 0.319 ms (forced-index
repeat: 0.300 ms). Host-observed Top-K timings include connection overhead and
are therefore reported separately from SQL execution time.

The pilot storage shape is the production recommendation for a future
`PlaceFeatureEmbedding`: document FK, place ID, vector, provider, model,
dimension, strategy, source hash and embedded timestamp. It permits model or
dimension replacement and hash-based re-indexing without coupling vector
storage to the fact document. No operating migration was created.

An operating transition requires a verified backup, staging restore, a pinned
PostGIS+pgvector image compatible with PostgreSQL 16, `CREATE EXTENSION
vector`, schema migration, index build and search verification. Rollback must
restore the prior image and backup/volume snapshot. PostgreSQL major-version
compatibility alone is not a substitute for that backup. No such transition
was performed in this work.

## Candidate injection pilot

Semantic retrieval and candidate injection have independent feature flags and
both default to false. When enabled for the pilot, the search path merges a
small semantic Top-K with existing DB/Kakao candidates, removes duplicate
Places, applies the same region/distance/category and evidence policy, and
uses semantic similarity only as one Hybrid Ranking component (weight 0.15).
Explicit required facts such as free use, 24-hour operation, parking and
accessibility must exist as actual Canonical Features; similarity cannot satisfy
them. Provider or pilot-DB failure falls back to the existing search path.

The 30-query OFF/ON benchmark returned results for 16 queries in both modes.
Semantic ON did not increase no-result, category or region violations and
reduced measured hard violations from 20 to 16, but it increased mean latency
from 1,205.02 ms to 1,708.60 ms and p95 from 2,142.02 ms to 2,315.26 ms.
Useful changes were visible for laptop/work, outlet and quiet/ambience queries;
some indirect or category-ambiguous queries remained mixed. Human relevance
labels are blank in `backend/tmp/semantic_injection_review_release.csv`,
so Precision, Recall, MRR and NDCG remain `NOT_MEASURED`.

These results support continued 1,000-row development validation, but not a
10,000-row automatic expansion, operating pgvector switch, or default-on
candidate injection yet. Relevance labels and query-embedding latency work are
the next gates.

### Second-pilot commands

```bash
python manage.py prepare_semantic_stratified_pilot --limit 1000 --dry-run
python manage.py prepare_semantic_stratified_pilot --limit 1000
python manage.py embed_place_feature_documents --sample tmp/semantic_stratified_1000.json --limit 1000
python manage.py benchmark_pgvector_pilot --sample tmp/semantic_stratified_1000.json --pgvector-dsn postgresql://pilot:pilot@127.0.0.1:55432/semantic_pilot
python manage.py evaluate_semantic_candidate_injection --pgvector-dsn postgresql://pilot:pilot@127.0.0.1:55432/semantic_pilot
```

## Common Hard Gate and weight benchmark (2026-08-18)

The earlier 30-query report counted 20 OFF hard violations. Trace inspection
found 15 real DB-candidate violations: five late-night requests without current
`야간운영`/`24시간운영` evidence and ten parking requests without current
`주차가능` evidence. Five additional rows were evaluator false positives: a
`freewifi` category correctly answered "무료 와이파이", but the evaluator
incorrectly interpreted every occurrence of "무료" as the `무료이용` feature.
The five category violations came from restaurant-intent queries receiving cafe
DB candidates after candidate merge.

All DB, Kakao, fallback and Semantic candidates now pass one post-merge gate.
Explicit category and region must match, and objective facility requirements
must be supported by current positive `PlaceTagEvidence`. Unknown, expired,
negative, and Semantic-document-only features do not satisfy a hard condition.
The 50-query regression measured zero hard, category, region and duplicate
violations for OFF and every Semantic weight. The conservative gate increased
the OFF no-result count to 22/50; this is intentional until current evidence is
available rather than treating unknown as true.

Query embeddings use a process-local cache keyed by SHA-256 of normalized
query, model, dimensions and cache version. Raw queries are not stored in the
key or DB. Default TTL is 900 seconds. On 35 embeddable evaluation queries,
cache-miss embedding averaged 527.26 ms while cache hits averaged 0.09 ms.
Across four Semantic passes, calls fell from an uncached 140 to 35 (75%).
Vector SQL remained 17.17--28.78 ms on average.

Weights 0.10, 0.15 and 0.20 changed 14/50 queries relative to OFF but produced
the same Top-5 ordering as each other. They changed final scores, not ordering,
because the injected pilot candidates share similar non-Semantic components.
Without relevance labels, 0.10 is the conservative recommendation; default
flags remain off. The compact, unlabeled review file is
`backend/tmp/semantic_weight_review_release.csv` (14 rows). The prior 100-row
review file contains no human labels, so Precision/MRR/NDCG remain
`NOT_MEASURED`.

The benchmark had one 49--54 second external-search outlier per variant. For
that reason means (OFF 2,590.78 ms; ON-hit 2,696.41--2,807.72 ms) are less
representative than medians and p95. OFF median/p95 were 815.98/2,521.68 ms;
0.10 miss 1,757.02/4,106.25 ms; 0.10 hit 1,033.32/2,232.79 ms.

## 10,000-document dry-run

No new document or embedding was written. The fact-only dry-run selected
10,000 active-positive candidates: Seoul 1,846, Busan 1,791, Incheon 1,835,
Daegu 1,762, Daejeon 1,103, Gwangju 700, and Ulsan 963. Categories were cafe
442, restaurant 3, city park 500, library 842, parking 1,496, shelter 3,001,
toilet 3,682, and tourism 34. The restaurant shortage is an actual active
Feature gap and is reported rather than filled with unsupported documents.

Of the selected rows, 1,013 already have the matching 512-dimensional
contextual embedding and 8,987 would be new. Based on the measured 1,000-row
run, the estimate is 315,444 input tokens, USD 0.00630888, about 144.85 seconds
of embedding time, 36.66 seconds of JSON storage time, and 18,405,376 raw
float32 vector bytes. HNSW index size is `NOT_MEASURED`. These estimates use
the current official `text-embedding-3-small` price of USD 0.02 per million
input tokens and are not execution results.

There are 19,257 eligible active-Feature Places in the seven-region/eight-
category scope, so the plan covers 51.93%. Cells below the one-percent planning
floor are restaurant (3), tourism (34), and the Work cluster (63). They are
explicit supply gaps; the sampler does not substitute stale or unsupported
facts to make the distribution look balanced.

## Staging pgvector transition plan

The operating PostGIS database and volume remain unchanged. A future staging
test must use this order:

1. Produce and verify a logical backup plus a separately restorable volume
   snapshot; record PostgreSQL/PostGIS versions.
2. Restore the backup into an isolated staging volume.
3. Start a pinned PostgreSQL 16 image containing compatible PostGIS and
   pgvector packages; never attach the operating volume to the pilot.
4. Verify PostGIS, run `CREATE EXTENSION vector`, and run a cosine smoke test.
5. Apply the separate `PlaceFeatureEmbedding` migration with provider/model/
   dimension/strategy/source-hash metadata.
6. Import only hash-current embeddings and verify counts and checksums.
7. Build and `ANALYZE` an HNSW `vector_cosine_ops` index, then capture query
   plans and index size.
8. Run Semantic OFF/ON search, Hard Gate, latency, Dashboard and API regression.
9. Run scheduler/worker against staging without enabling Semantic by default.
10. Roll back by stopping staging, restoring the verified backup to the prior
    pinned image/volume, and re-running counts and checks; no in-place downgrade.

The current 10k decision is **HOLD**. Technical safety and cache gates pass,
but human relevance is still unlabeled and weights do not yet discriminate
candidate ordering. Operating pgvector migration and default-on injection stay
blocked on that relevance comparison, not on embedding price.
