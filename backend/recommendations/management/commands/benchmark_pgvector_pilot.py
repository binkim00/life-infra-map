import json
import re
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from recommendations.models import PlaceFeatureDocument
from recommendations.services.pgvector_pilot import (
    connect_pilot, ensure_pilot_schema, rebuild_hnsw_index, sql_vector_search,
    upsert_documents, vector_literal,
)


class Command(BaseCommand):
    help = "Load selected embeddings into a separate pilot DB and benchmark SQL cosine retrieval."

    def add_arguments(self, parser):
        parser.add_argument("--dsn", default="")
        parser.add_argument("--sample", required=True)
        parser.add_argument("--max-documents", type=int, default=10000)
        parser.add_argument("--report", default="tmp/pgvector_1000_benchmark.json")

    def handle(self, *args, **options):
        dsn = options["dsn"] or getattr(settings, "SEMANTIC_PGVECTOR_DSN", "")
        if not dsn:
            raise CommandError("missing_pgvector_pilot_dsn")
        sample = json.loads(Path(options["sample"]).resolve().read_text(encoding="utf-8"))
        max_documents = max(1, min(int(options["max_documents"]), 10000))
        place_ids = [int(value) for value in (sample.get("place_ids") or [])[:max_documents]]
        documents = list(PlaceFeatureDocument.objects.filter(
            place_id__in=place_ids, embedding_dimensions=512,
        ).exclude(embedding=[]).order_by("id"))
        if len(place_ids) != len(documents):
            raise CommandError("sample_documents_mismatch")
        if not documents:
            raise CommandError("no_embedded_sample_documents")
        try:
            connection = connect_pilot(dsn)
            ensure_pilot_schema(connection, dimensions=512)
            with connection.cursor() as cursor:
                cursor.execute("DROP INDEX IF EXISTS semantic_pilot_embedding_hnsw")
                cursor.execute("TRUNCATE TABLE place_feature_embedding")
            connection.commit()
            write_latency = upsert_documents(connection, documents)
            hnsw_build_latency = rebuild_hnsw_index(connection)
            analyze_started = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.execute("ANALYZE place_feature_embedding")
            connection.commit()
            analyze_latency = round((time.perf_counter() - analyze_started) * 1000, 2)
            query_vector = documents[0].embedding
            latency = {}
            results = {}
            for top_k in (5, 10, 20, 50):
                rows, elapsed = sql_vector_search(connection, query_vector, top_k=top_k)
                latency[str(top_k)] = elapsed
                results[str(top_k)] = [
                    {"document_id": row[0], "place_id": row[1], "similarity": round(float(row[2]), 6)}
                    for row in rows
                ]
            with connection.cursor() as cursor:
                cursor.execute("SELECT version(), postgis_full_version(), extversion FROM pg_extension WHERE extname='vector'")
                version, postgis, pgvector = cursor.fetchone()
                cursor.execute("""
                    SELECT count(*), count(DISTINCT document_id), count(DISTINCT place_id),
                           count(*) FILTER (WHERE dimensions <> 512),
                           count(*) FILTER (WHERE vector_dims(embedding) <> 512)
                    FROM place_feature_embedding
                """)
                stored, document_ids, place_ids_stored, metadata_dimension_errors, vector_dimension_errors = cursor.fetchone()
                cursor.execute("""
                    SELECT pg_size_pretty(pg_relation_size('semantic_pilot_embedding_hnsw')),
                           pg_relation_size('semantic_pilot_embedding_hnsw'),
                           pg_size_pretty(pg_total_relation_size('place_feature_embedding')),
                           pg_total_relation_size('place_feature_embedding')
                """)
                index_size, index_size_bytes, table_size, table_size_bytes = cursor.fetchone()
                cursor.execute("SELECT document_id, source_hash FROM place_feature_embedding")
                stored_hashes = dict(cursor.fetchall())
                expected_hashes = {document.id: document.embedding_source_hash for document in documents}
                source_hash_mismatches = sum(
                    stored_hashes.get(document_id) != source_hash
                    for document_id, source_hash in expected_hashes.items()
                )
                cursor.execute("""
                    SELECT count(*) FROM (
                        SELECT source_hash FROM place_feature_embedding
                        GROUP BY source_hash HAVING count(*) > 1
                    ) duplicate_content
                """)
                duplicate_source_hash_groups = cursor.fetchone()[0]
                cursor.execute("EXPLAIN (ANALYZE, FORMAT TEXT) SELECT place_id FROM place_feature_embedding ORDER BY embedding <=> %s::vector LIMIT 20", (vector_literal(query_vector),))
                explain = self._compact_explain(cursor.fetchall())
                cursor.execute("SET LOCAL enable_seqscan = off")
                cursor.execute("EXPLAIN (ANALYZE, FORMAT TEXT) SELECT place_id FROM place_feature_embedding ORDER BY embedding <=> %s::vector LIMIT 20", (vector_literal(query_vector),))
                forced_index_explain = self._compact_explain(cursor.fetchall())
            report = {
                "documents": len(documents), "stored": stored, "dimensions": 512,
                "write_latency_ms": write_latency, "hnsw_build_latency_ms": hnsw_build_latency,
                "analyze_latency_ms": analyze_latency, "top_k_latency_ms": latency,
                "top_results": results, "postgresql": version, "postgis": postgis,
                "pgvector": pgvector, "index": "hnsw/vector_cosine_ops",
                "hnsw_size": index_size, "hnsw_size_bytes": index_size_bytes,
                "table_total_size": table_size, "table_total_size_bytes": table_size_bytes,
                "duplicate_document_ids": stored - document_ids,
                "duplicate_place_ids": stored - place_ids_stored,
                "metadata_dimension_errors": metadata_dimension_errors,
                "vector_dimension_errors": vector_dimension_errors,
                "source_hash_mismatches": source_hash_mismatches,
                "duplicate_source_hash_groups": duplicate_source_hash_groups,
                "unique_source_hash_count": len({document.embedding_source_hash for document in documents}),
                "explain": explain,
                "forced_index_explain": forced_index_explain,
            }
            connection.close()
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        path = Path(options["report"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))

    @staticmethod
    def _compact_explain(rows):
        return [re.sub(r"'\[[^']+\]'::vector", "'<512-d vector>'::vector", row[0]) for row in rows]
