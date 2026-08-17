import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from recommendations.models import PlaceFeatureDocument
from recommendations.services.pgvector_pilot import (
    connect_pilot, ensure_pilot_schema, sql_vector_search, upsert_documents, vector_literal,
)


class Command(BaseCommand):
    help = "Load selected embeddings into a separate pilot DB and benchmark SQL cosine retrieval."

    def add_arguments(self, parser):
        parser.add_argument("--dsn", default="")
        parser.add_argument("--sample", required=True)
        parser.add_argument("--report", default="tmp/pgvector_1000_benchmark.json")

    def handle(self, *args, **options):
        dsn = options["dsn"] or getattr(settings, "SEMANTIC_PGVECTOR_DSN", "")
        if not dsn:
            raise CommandError("missing_pgvector_pilot_dsn")
        sample = json.loads(Path(options["sample"]).resolve().read_text(encoding="utf-8"))
        place_ids = [int(value) for value in (sample.get("place_ids") or [])[:1000]]
        documents = list(PlaceFeatureDocument.objects.filter(
            place_id__in=place_ids, embedding_dimensions=512,
        ).exclude(embedding=[]).order_by("id"))
        if not documents:
            raise CommandError("no_embedded_sample_documents")
        try:
            connection = connect_pilot(dsn)
            ensure_pilot_schema(connection, dimensions=512)
            write_latency = upsert_documents(connection, documents)
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
                cursor.execute("ANALYZE place_feature_embedding")
                cursor.execute("SELECT version(), postgis_full_version(), extversion FROM pg_extension WHERE extname='vector'")
                version, postgis, pgvector = cursor.fetchone()
                cursor.execute("SELECT count(*) FROM place_feature_embedding")
                stored = cursor.fetchone()[0]
                cursor.execute("EXPLAIN (ANALYZE, FORMAT TEXT) SELECT place_id FROM place_feature_embedding ORDER BY embedding <=> %s::vector LIMIT 20", (vector_literal(query_vector),))
                explain = [row[0] for row in cursor.fetchall()]
                cursor.execute("SET LOCAL enable_seqscan = off")
                cursor.execute("EXPLAIN (ANALYZE, FORMAT TEXT) SELECT place_id FROM place_feature_embedding ORDER BY embedding <=> %s::vector LIMIT 20", (vector_literal(query_vector),))
                forced_index_explain = [row[0] for row in cursor.fetchall()]
            report = {
                "documents": len(documents), "stored": stored, "dimensions": 512,
                "write_latency_ms": write_latency, "top_k_latency_ms": latency,
                "top_results": results, "postgresql": version, "postgis": postgis,
                "pgvector": pgvector, "index": "hnsw/vector_cosine_ops", "explain": explain,
                "forced_index_explain": forced_index_explain,
            }
            connection.close()
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        path = Path(options["report"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
