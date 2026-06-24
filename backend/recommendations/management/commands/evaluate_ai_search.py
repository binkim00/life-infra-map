import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.services.ai_search_orchestrator import run_ai_search


DEFAULT_EVALUATION_QUERIES = [
    "오늘 날씨 어때",
    "비 오는데 잠깐 피할 곳",
    "허리가 아프네",
    "노래 한 곡 땡기고 싶은데",
    "사상역 근처 쌀국수 맛집",
]


class Command(BaseCommand):
    help = "Run live /ai-search/ evaluation cases and save JSON diagnostics."

    def add_arguments(self, parser):
        parser.add_argument("--repeat", type=int, default=1)
        parser.add_argument("--query", action="append", default=[])
        parser.add_argument("--lat", type=float, default=35.1556)
        parser.add_argument("--lng", type=float, default=129.0641)
        parser.add_argument("--output", default="")

    def handle(self, *args, **options):
        repeat = max(1, min(int(options["repeat"] or 1), 20))
        queries = options["query"] or DEFAULT_EVALUATION_QUERIES
        output = options["output"]
        if output:
            output_path = Path(output)
        else:
            output_path = Path("ai_search_evaluation_latest.json")

        rows = []
        for round_index in range(repeat):
            for raw_query in queries:
                started = time.perf_counter()
                data = run_ai_search({
                    "query": raw_query,
                    "originalQuery": raw_query,
                    "lat": options["lat"],
                    "lng": options["lng"],
                    "limit": 15,
                })
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                debug = data.get("debug_pipeline") or {}
                ai_debug = data.get("ai_debug") or {}
                reranker = debug.get("reranker") or ai_debug.get("reranker") or {}
                rows.append({
                    "round": round_index + 1,
                    "raw_query": raw_query,
                    "action": data.get("decision_action") or data.get("decisionAction"),
                    "normalized_frame": data.get("place_intent_frame") or {},
                    "clarification_question": data.get("clarification_question") or "",
                    "generated_queries": (debug.get("query_generation") or {}).get("primary_queries") or [],
                    "source_candidate_counts": data.get("candidate_source_counts") or {},
                    "semantic_reranker": reranker,
                    "total_latency_ms": elapsed_ms,
                    "planner_latency_ms": None,
                    "retrieval_latency_ms": None,
                    "reranker_latency_ms": None,
                    "debug_pipeline": debug,
                })

        payload = {
            "created_at": timezone.now().isoformat(),
            "repeat": repeat,
            "count": len(rows),
            "results": rows,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Saved AI search evaluation to {output_path}"))
