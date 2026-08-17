import csv
import json
import statistics
from pathlib import Path

from django.core.management.base import BaseCommand
from django.test.utils import override_settings

from recommendations.services.ai_search_orchestrator import run_ai_search


class Command(BaseCommand):
    help = "Compare existing candidate retrieval with limited semantic candidate injection."

    def add_arguments(self, parser):
        default = Path(__file__).resolve().parents[2] / "data" / "semantic_pilot_queries.json"
        parser.add_argument("--queries", default=str(default))
        parser.add_argument("--pgvector-dsn", default="")
        parser.add_argument("--json", default="tmp/semantic_injection_off_on.json")
        parser.add_argument("--csv", default="tmp/semantic_injection_review.csv")
        parser.add_argument("--review-queries", type=int, default=20)

    def handle(self, *args, **options):
        queries = json.loads(Path(options["queries"]).resolve().read_text(encoding="utf-8"))
        runs = {}
        for mode in ("off", "on"):
            rows = []
            with override_settings(
                CONVERSATIONAL_SEARCH_AI_ENABLED=False,
                AI_RERANK_ENABLED=False,
                SEMANTIC_RETRIEVAL_ENABLED=mode == "on",
                SEMANTIC_CANDIDATE_INJECTION_ENABLED=mode == "on",
                SEMANTIC_EMBEDDING_PROVIDER="openai",
                SEMANTIC_PGVECTOR_DSN=options["pgvector_dsn"] if mode == "on" else "",
            ):
                for query_row in queries:
                    response = run_ai_search({
                        "query": query_row["query"], "lat": 35.1579, "lng": 129.0592,
                        "radius": 20000, "limit": 5,
                    })
                    results = response.get("results") or []
                    rows.append({
                        "query": query_row["query"], "type": query_row.get("type", ""),
                        "results": [self._result(row, rank, query_row["query"]) for rank, row in enumerate(results[:5], 1)],
                        "latency_ms": (response.get("timings") or {}).get("total_latency_ms"),
                        "semantic_timings": {
                            key: (response.get("timings") or {}).get(key)
                            for key in (
                                "semantic_query_embedding_latency_ms", "semantic_vector_search_latency_ms",
                                "semantic_merge_latency_ms", "ranking_latency_ms",
                            )
                        },
                    })
            runs[mode] = rows
        report = {"query_count": len(queries), "runs": runs, "metrics": {
            mode: self._metrics(rows) for mode, rows in runs.items()
        }, "relevance_metrics": "NOT_MEASURED"}
        json_path = Path(options["json"]).resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        csv_path = Path(options["csv"]).resolve()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        review_count = max(1, min(int(options["review_queries"]), 20, len(queries)))
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            fields = [
                "query", "rank", "off_place", "off_tags", "off_score", "on_place", "on_tags",
                "on_semantic_score", "on_final_score", "off_relevant", "on_relevant", "preferred", "notes",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index in range(review_count):
                off = runs["off"][index]
                on = runs["on"][index]
                for rank in range(5):
                    left = off["results"][rank] if rank < len(off["results"]) else {}
                    right = on["results"][rank] if rank < len(on["results"]) else {}
                    writer.writerow({
                        "query": off["query"], "rank": rank + 1,
                        "off_place": left.get("name", ""), "off_tags": "|".join(left.get("tags", [])),
                        "off_score": left.get("final_score", ""), "on_place": right.get("name", ""),
                        "on_tags": "|".join(right.get("tags", [])),
                        "on_semantic_score": right.get("semantic_score", ""),
                        "on_final_score": right.get("final_score", ""),
                        "off_relevant": "", "on_relevant": "", "preferred": "", "notes": "",
                    })
        self.stdout.write(json.dumps({"metrics": report["metrics"], "json": str(json_path), "csv": str(csv_path)}, ensure_ascii=False, indent=2))

    @staticmethod
    def _result(row, rank, query):
        breakdown = row.get("score_breakdown") or {}
        actual_tags = list(dict.fromkeys([
            *(row.get("verified_tags") or []), *(row.get("suggested_tags") or []),
            *(row.get("candidate_tags") or []),
        ]))
        expected_category = ""
        if "카페" in query:
            expected_category = "cafe"
        elif "관광지" in query:
            expected_category = "tourism"
        elif "공원" in query:
            expected_category = "city_park"
        elif any(term in query for term in ("식당", "밥 먹", "혼밥")):
            expected_category = "restaurant"
        category_text = str(row.get("category") or "").lower()
        category_alias = {
            "cafe": ("cafe", "카페"), "restaurant": ("restaurant", "식당", "음식점"),
            "tourism": ("tourism", "관광"), "city_park": ("city_park", "공원"),
        }
        category_violation = bool(expected_category) and not any(
            value in category_text for value in category_alias[expected_category]
        )
        expected_region = next((name for name in ("서울", "부산", "인천", "대구", "대전", "광주", "울산") if name in query), "")
        region_violation = bool(expected_region) and not str(row.get("address") or "").startswith(expected_region)
        required_tags = []
        if "무료" in query:
            required_tags.append({"무료이용"})
        if "주차 가능" in query:
            required_tags.append({"주차가능"})
        if "장애인시설" in query:
            required_tags.append({"장애인시설"})
        if "밤 늦게" in query:
            required_tags.append({"야간운영", "24시간운영"})
        hard_feature_violation = any(not (choices & set(actual_tags)) for choices in required_tags)
        return {
            "rank": rank, "id": row.get("id"), "name": row.get("name"),
            "category": row.get("category"), "address": row.get("address"),
            "tags": actual_tags or row.get("matched_tags") or [],
            "semantic_score": row.get("retrieval_semantic_score") or breakdown.get("semantic_score"),
            "final_score": breakdown.get("final_score") or row.get("score"),
            "hard_satisfied": not bool(row.get("pre_ai_unmet_constraints") or row.get("unmet_constraints")) and not hard_feature_violation,
            "category_violation": category_violation,
            "region_violation": region_violation,
        }

    @staticmethod
    def _metrics(rows):
        latencies = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
        results = [result for row in rows for result in row["results"]]
        duplicate_count = sum(
            max(0, len(row["results"]) - len({result["id"] for result in row["results"]})) for row in rows
        )
        return {
            "success": sum(bool(row["results"]) for row in rows),
            "no_result": sum(not row["results"] for row in rows),
            "hard_violations": sum(not result["hard_satisfied"] for result in results),
            "category_violations": sum(result["category_violation"] for result in results),
            "region_violations": sum(result["region_violation"] for result in results),
            "duplicates": duplicate_count,
            "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else None,
            "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
            "p95_latency_ms": round(sorted(latencies)[max(0, int(len(latencies) * .95) - 1)], 2) if latencies else None,
            "max_latency_ms": round(max(latencies), 2) if latencies else None,
        }
