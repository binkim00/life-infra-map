import json
from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.models import PlaceTagCollectionJob, ProviderQuotaUsage
from recommendations.services.web_tag_evidence_provider import (
    PROVIDER,
    classify_legacy_failure,
    estimate_web_cost_usd,
)


class Command(BaseCommand):
    help = "Report paid web-search failures without rewriting historical jobs."

    def add_arguments(self, parser):
        parser.add_argument("--date", default="")

    def handle(self, *args, **options):
        usage_date = timezone.localdate() if not options["date"] else __import__("datetime").date.fromisoformat(options["date"])
        jobs = PlaceTagCollectionJob.objects.filter(provider=PROVIDER, cycle_date=usage_date)
        failures = Counter(
            classify_legacy_failure(error, stats)
            for error, stats in jobs.values_list("error_code", "stats")
        )
        quota = ProviderQuotaUsage.objects.filter(provider=PROVIDER, usage_date=usage_date).first()
        metadata = quota.metadata or {} if quota else {}
        usage = {key: int(metadata.get(key) or 0) for key in (
            "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"
        )}
        model = str(metadata.get("model") or "")
        tool_actions = int(metadata.get("web_search_calls") or 0)
        self.stdout.write(json.dumps({
            "date": usage_date.isoformat(),
            "requests": quota.request_count if quota else 0,
            "tool_actions": tool_actions,
            "model": model,
            "usage": usage,
            "estimated_total_cost_usd": estimate_web_cost_usd(model, usage, tool_actions),
            "stored_evidence": sum(int((stats or {}).get("evidences") or 0) for stats in jobs.values_list("stats", flat=True)),
            "failures": dict(failures),
            "historical_rows_rewritten": False,
        }, ensure_ascii=False, indent=2))
