import csv
import json
import statistics
from pathlib import Path

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.test.utils import override_settings

from recommendations.services.ai_search_orchestrator import run_ai_search


WEIGHTS = (0.10, 0.15, 0.20)
REASON_FEATURES = {
    "조용": {"조용함"}, "노트북": {"노트북작업"}, "작업": {"작업하기좋음", "노트북작업"},
    "콘센트": {"콘센트있음"}, "와이파이": {"무료와이파이"}, "혼자": {"혼자이용좋음", "혼밥좋음"},
    "분위기": {"분위기좋음"}, "데이트": {"데이트좋음"}, "대화": {"대화하기좋음"},
    "장기": {"장기체류좋음"}, "주차": {"주차가능"}, "무료": {"무료이용", "무료와이파이"},
}


class Command(BaseCommand):
    help = "Compare Semantic OFF and weighted candidate injection with objective safety metrics."

    def add_arguments(self, parser):
        default = Path(__file__).resolve().parents[2] / "data" / "semantic_safety_queries_50.json"
        parser.add_argument("--queries", default=str(default))
        parser.add_argument("--pgvector-dsn", default="")
        parser.add_argument("--json", default="tmp/semantic_weight_safety.json")
        parser.add_argument("--csv", default="tmp/semantic_weight_review.csv")
        parser.add_argument("--review-queries", type=int, default=30)

    def handle(self, *args, **options):
        queries = json.loads(Path(options["queries"]).resolve().read_text(encoding="utf-8"))
        runs = {"off": self._run(queries, enabled=False, dsn="", weight=0.0)}

        # This makes 0.10 a real cache-miss benchmark. The immediate repeat and
        # other weights reuse only vectors within this process.
        cache.clear()
        runs["0.10_miss"] = self._run(queries, enabled=True, dsn=options["pgvector_dsn"], weight=0.10)
        runs["0.10_hit"] = self._run(queries, enabled=True, dsn=options["pgvector_dsn"], weight=0.10)
        for weight in WEIGHTS[1:]:
            runs[f"{weight:.2f}"] = self._run(
                queries, enabled=True, dsn=options["pgvector_dsn"], weight=weight,
            )

        metrics = {name: self._metrics(rows) for name, rows in runs.items()}
        off_signatures = {row["query"]: self._signature(row) for row in runs["off"]}
        changed = []
        for query_row in queries:
            query = query_row["query"]
            variants = {
                name: next(row for row in rows if row["query"] == query)
                for name, rows in runs.items() if name != "0.10_miss"
            }
            if any(self._signature(row) != off_signatures[query] for name, row in variants.items() if name != "off"):
                changed.append({"query": query, "type": query_row.get("type", ""), "variants": variants})

        report = {
            "query_count": len(queries),
            "runs": runs,
            "metrics": metrics,
            "changed_query_count": len(changed),
            "query_embedding_api_calls": sum(
                row["semantic_timings"].get("query_embedding_api_calls") or 0
                for rows in runs.values() for row in rows
            ),
            "relevance_metrics": "NOT_MEASURED",
        }
        json_path = Path(options["json"]).resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        csv_path = Path(options["csv"]).resolve()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_review(csv_path, changed[:max(1, min(options["review_queries"], 30))])
        self.stdout.write(json.dumps({
            "metrics": metrics,
            "changed_query_count": len(changed),
            "query_embedding_api_calls": report["query_embedding_api_calls"],
            "json": str(json_path),
            "csv": str(csv_path),
        }, ensure_ascii=False, indent=2))

    def _run(self, queries, *, enabled, dsn, weight):
        rows = []
        with override_settings(
            CONVERSATIONAL_SEARCH_AI_ENABLED=False,
            AI_RERANK_ENABLED=False,
            SEMANTIC_RETRIEVAL_ENABLED=enabled,
            SEMANTIC_CANDIDATE_INJECTION_ENABLED=enabled,
            SEMANTIC_RETRIEVAL_WEIGHT=weight,
            SEMANTIC_EMBEDDING_PROVIDER="openai",
            SEMANTIC_PGVECTOR_DSN=dsn if enabled else "",
        ):
            for query_row in queries:
                response = run_ai_search({
                    "query": query_row["query"], "lat": 35.1579, "lng": 129.0592,
                    "radius": 20000, "limit": 5,
                })
                timings = response.get("timings") or {}
                results = response.get("results") or []
                rows.append({
                    "query": query_row["query"],
                    "type": query_row.get("type", ""),
                    "results": [self._result(row, rank) for rank, row in enumerate(results[:5], 1)],
                    "latency_ms": timings.get("total_latency_ms"),
                    "semantic_timings": {
                        "query_embedding_ms": timings.get("semantic_query_embedding_latency_ms", 0.0),
                        "query_embedding_cache_hit": timings.get("semantic_query_embedding_cache_hit"),
                        "query_embedding_api_calls": timings.get("semantic_query_embedding_api_calls", 0),
                        "vector_ms": timings.get("semantic_vector_search_latency_ms", 0.0),
                        "merge_ms": timings.get("semantic_merge_latency_ms", 0.0),
                        "ranking_ms": timings.get("ranking_latency_ms", 0.0),
                    },
                })
        return rows

    @staticmethod
    def _result(row, rank):
        breakdown = row.get("score_breakdown") or {}
        actual_tags = list(dict.fromkeys([
            *(row.get("hard_gate_active_tags") or []),
            *(row.get("verified_tags") or []),
            *(row.get("suggested_tags") or []),
            *(row.get("candidate_tags") or []),
        ]))
        violations = list(row.get("hard_gate_violations") or [])
        return {
            "rank": rank, "id": row.get("id"), "name": row.get("name"),
            "source": row.get("candidate_source") or row.get("source"),
            "category": row.get("category"), "address": row.get("address"),
            "tags": actual_tags, "reason": row.get("recommendation_reason") or row.get("recommend_reason"),
            "semantic_score": row.get("retrieval_semantic_score") or breakdown.get("semantic_score"),
            "final_score": breakdown.get("final_score") or row.get("score"),
            "hard_satisfied": not violations and not bool(
                row.get("pre_ai_unmet_constraints") or row.get("unmet_constraints")
            ),
            "category_violation": any(v.get("type") == "category" for v in violations),
            "region_violation": any(v.get("type") == "region" for v in violations),
            "hard_gate_violations": violations,
        }

    @staticmethod
    def _signature(row):
        return tuple(result.get("id") for result in row["results"])

    @staticmethod
    def _metrics(rows):
        latencies = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
        results = [result for row in rows for result in row["results"]]
        cache_values = [
            row["semantic_timings"].get("query_embedding_cache_hit")
            for row in rows if row["semantic_timings"].get("query_embedding_cache_hit") is not None
        ]
        embedding = [float(row["semantic_timings"].get("query_embedding_ms") or 0) for row in rows]
        vector = [float(row["semantic_timings"].get("vector_ms") or 0) for row in rows]
        duplicate_count = sum(
            max(0, len(row["results"]) - len({result["id"] for result in row["results"]})) for row in rows
        )
        unsupported_reasons = sum(Command._reason_unsupported(result) for result in results)
        return {
            "success": sum(bool(row["results"]) for row in rows),
            "no_result": sum(not row["results"] for row in rows),
            "hard_violations": sum(not result["hard_satisfied"] for result in results),
            "category_violations": sum(result["category_violation"] for result in results),
            "region_violations": sum(result["region_violation"] for result in results),
            "duplicates": duplicate_count,
            "unsupported_reasons": unsupported_reasons,
            "featureless_qualitative_reasons": unsupported_reasons,
            "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else None,
            "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
            "p95_latency_ms": round(sorted(latencies)[max(0, int(len(latencies) * .95) - 1)], 2) if latencies else None,
            "max_latency_ms": round(max(latencies), 2) if latencies else None,
            "avg_query_embedding_ms": round(statistics.mean(embedding), 2) if embedding else None,
            "avg_vector_ms": round(statistics.mean(vector), 2) if vector else None,
            "query_embedding_api_calls": sum(
                row["semantic_timings"].get("query_embedding_api_calls") or 0 for row in rows
            ),
            "query_embedding_cache_hits": sum(value is True for value in cache_values),
            "query_embedding_cache_misses": sum(value is False for value in cache_values),
        }

    @staticmethod
    def _reason_unsupported(result):
        reason = str(result.get("reason") or "")
        tags = set(result.get("tags") or [])
        marker = " 근거가 있는 후보"
        if marker in reason:
            claimed = {value.strip() for value in reason.split(marker, 1)[0].split(",") if value.strip()}
            return not claimed.issubset(tags)
        # Category/distance-only reasons do not make qualitative feature claims.
        if "분류에 맞는 후보" in reason or "거리의 " in reason:
            return False
        return any(term in reason and not tags.intersection(required) for term, required in REASON_FEATURES.items())

    @staticmethod
    def _write_review(path, changed):
        fields = [
            "query", "type", "off_top5", "weight_010_top5", "weight_015_top5",
            "weight_020_top5", "preferred_variant", "relevant_places", "notes",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for item in changed:
                def compact_results(name):
                    return json.dumps([{
                        "rank": row["rank"], "place": row["name"], "tags": row["tags"],
                        "semantic_score": row["semantic_score"], "final_score": row["final_score"],
                    } for row in item["variants"][name]["results"]], ensure_ascii=False)
                writer.writerow({
                    "query": item["query"], "type": item["type"],
                    "off_top5": compact_results("off"),
                    "weight_010_top5": compact_results("0.10_hit"),
                    "weight_015_top5": compact_results("0.15"),
                    "weight_020_top5": compact_results("0.20"),
                    "preferred_variant": "", "relevant_places": "", "notes": "",
                })
