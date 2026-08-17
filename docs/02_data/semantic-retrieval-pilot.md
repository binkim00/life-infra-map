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
three-row cosine-distance query succeeded. The container used no operating
volume and was removed after validation.

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
