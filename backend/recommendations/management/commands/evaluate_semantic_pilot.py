import csv
import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from recommendations.services.semantic_embeddings import EmbeddingProviderError, embed_openai_texts
from recommendations.services.semantic_retrieval import retrieve_semantic_places


class Command(BaseCommand):
    help = "Evaluate the feature-flagged 100-document semantic pilot without relevance labels."

    def add_arguments(self, parser):
        default_queries = Path(__file__).resolve().parents[2] / "data" / "semantic_pilot_queries.json"
        parser.add_argument("--queries", default=str(default_queries))
        parser.add_argument("--top-k", type=int, default=10)
        parser.add_argument("--csv", default="tmp/semantic_pilot_validation.csv")
        parser.add_argument("--json", default="tmp/semantic_pilot_report.json")

    def handle(self, *args, **options):
        query_path = Path(options["queries"]).resolve()
        queries = json.loads(query_path.read_text(encoding="utf-8"))
        if not isinstance(queries, list) or not 1 <= len(queries) <= 100:
            raise CommandError("queries must be a JSON list with 1..100 items")
        texts = [str(row.get("query") or "").strip() for row in queries]
        try:
            embedded = embed_openai_texts(texts)
        except EmbeddingProviderError as exc:
            raise CommandError(str(exc)) from exc
        top_k = max(1, min(options["top_k"], 20))
        rows = []
        search_latencies = []
        started = time.perf_counter()
        for query_row, vector in zip(queries, embedded["vectors"]):
            result = retrieve_semantic_places(query_row["query"], top_k=top_k, query_embedding=vector)
            search_latencies.append(result["vector_search_latency_ms"])
            for rank, candidate in enumerate(result["results"], start=1):
                features = candidate["features"] or []
                lexical_matches = [tag for tag in features if tag in query_row["query"]]
                rows.append({
                    "query": query_row["query"], "query_type": query_row.get("type", ""),
                    "place": candidate["place"].name, "place_id": candidate["place_id"],
                    "rank": rank, "semantic_score": candidate["semantic_score"],
                    "tag_score": min(100, len(lexical_matches) * 25),
                    "final_score": candidate["semantic_score"],
                    "actual_tags": ",".join(features), "address": candidate["place"].address,
                    "feature_document": candidate["document"], "relevant": "", "notes": "",
                })
        csv_path = Path(options["csv"]).resolve()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        report = {
            "query_count": len(queries), "top_k": top_k, "result_rows": len(rows),
            "embedding_model": embedded["model"], "dimensions": embedded["dimensions"],
            "query_input_tokens": embedded["input_tokens"],
            "query_embedding_cost_usd": embedded["estimated_cost_usd"],
            "query_embedding_latency_ms": embedded["latency_ms"],
            "average_vector_search_latency_ms": round(sum(search_latencies) / len(search_latencies), 2),
            "total_evaluation_latency_ms": round((time.perf_counter() - started) * 1000 + embedded["latency_ms"], 2),
            "csv": str(csv_path), "relevance_metrics": "NOT_MEASURED",
        }
        json_path = Path(options["json"]).resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
