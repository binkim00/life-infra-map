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
