import json
from collections import Counter

from django.core.management.base import BaseCommand

from recommendations.models import PlaceTagCollectionJob


class Command(BaseCommand):
    help = "Report collection KPI for an inclusive PlaceTagCollectionJob id range."

    def add_arguments(self, parser):
        parser.add_argument("--min-job-id", type=int, required=True)
        parser.add_argument("--max-job-id", type=int, required=True)

    def handle(self, *args, **options):
        rows = list(
            PlaceTagCollectionJob.objects.filter(
                id__gte=options["min_job_id"],
                id__lte=options["max_job_id"],
            ).select_related("place")
        )
        result = {
            "job_range": [options["min_job_id"], options["max_job_id"]],
            "places": len(rows),
            "status": dict(Counter(row.status for row in rows)),
            "calls": sum(int((row.stats or {}).get("requests") or 0) for row in rows),
            "evidence": sum(int((row.stats or {}).get("evidences") or 0) for row in rows),
            "new_evidence": sum(int((row.stats or {}).get("new_evidences") or 0) for row in rows),
            "new_active": sum(int((row.stats or {}).get("new_active_evidences") or 0) for row in rows),
            "ai_calls": sum(int((row.stats or {}).get("ai_calls") or 0) for row in rows),
            "failures": sum(bool(row.error_code and row.error_code != "insufficient_evidence") for row in rows),
            "rate_limited": sum(row.error_code == "rate_limited" for row in rows),
            "miss_reasons": dict(Counter(
                (row.stats or {}).get("miss_reason") or "SUCCESS"
                for row in rows
            )),
            "regions": dict(Counter((row.context or {}).get("region") or "UNKNOWN" for row in rows)),
            "strategies": dict(Counter((row.context or {}).get("budget_bucket") or "unclassified" for row in rows)),
        }
        calls = result["calls"]
        result["calls_per_place"] = round(calls / len(rows), 4) if rows else 0
        result["evidence_per_call"] = round(result["new_evidence"] / calls, 4) if calls else 0
        result["active_per_call"] = round(result["new_active"] / calls, 4) if calls else 0
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
