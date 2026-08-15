import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from recommendations.models import PlaceTagCollectionJob, ProviderQuotaUsage


class Command(BaseCommand):
    help = "Report evidence hit rate and classified miss reasons for collection jobs."

    def add_arguments(self, parser):
        parser.add_argument("--date", default="")
        parser.add_argument("--output", default="")
        parser.add_argument("--mode", default="")
        parser.add_argument("--latest", type=int)

    def handle(self, *args, **options):
        cycle_date = timezone.localdate() if not options["date"] else timezone.datetime.fromisoformat(options["date"]).date()
        report = build_collection_report(cycle_date, mode=options["mode"], latest=options["latest"])
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if options["output"]:
            path = Path(options["output"]).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        self.stdout.write(rendered)


def build_collection_report(cycle_date, *, mode="", latest=None):
    queryset = PlaceTagCollectionJob.objects.filter(cycle_date=cycle_date)
    if mode:
        queryset = queryset.filter(context__mode=mode)
    if latest:
        job_ids = queryset.order_by("-id").values_list("id", flat=True)[:latest]
        queryset = PlaceTagCollectionJob.objects.filter(id__in=job_ids)
    jobs = list(queryset.select_related("place"))
    misses = Counter()
    by_category = defaultdict(lambda: {"places": 0, "with_evidence": 0, "evidences": 0})
    by_region = defaultdict(lambda: {"places": 0, "with_evidence": 0, "evidences": 0})
    for job in jobs:
        stats = job.stats or {}
        evidence_count = int(stats.get("evidences") or 0)
        miss = stats.get("miss_reason") or ("NO_EVIDENCE_UNCLASSIFIED" if not evidence_count else "")
        if miss:
            misses[miss] += 1
        category = job.place.category
        region = (job.context or {}).get("region") or "tier:{}".format((job.context or {}).get("tier", "unknown"))
        for bucket in (by_category[category], by_region[region]):
            bucket["places"] += 1
            bucket["evidences"] += evidence_count
            bucket["with_evidence"] += int(evidence_count > 0)
    quota = ProviderQuotaUsage.objects.filter(usage_date=cycle_date).values(
        "provider", "request_count", "success_count", "failed_count", "rate_limited_count"
    )
    with_evidence = sum(int((job.stats or {}).get("evidences") or 0) > 0 for job in jobs)
    return {
        "date": cycle_date.isoformat(),
        "mode": mode or "all",
        "latest": latest,
        "places": len(jobs),
        "places_with_evidence": with_evidence,
        "evidence_hit_rate": round(with_evidence / len(jobs), 4) if jobs else None,
        "evidence_count": sum(int((job.stats or {}).get("evidences") or 0) for job in jobs),
        "structured_evidence_count": sum(int((job.stats or {}).get("structured_evidences") or 0) for job in jobs),
        "ai_call_count": sum(int((job.stats or {}).get("ai_calls") or 0) for job in jobs),
        "api_requests_from_job_stats": sum(int((job.stats or {}).get("requests") or 0) for job in jobs),
        "average_processing_seconds": round(
            sum(max(0, (job.updated_at - job.created_at).total_seconds()) for job in jobs) / len(jobs), 3
        ) if jobs else None,
        "batch_elapsed_seconds": round(
            (max(job.updated_at for job in jobs) - min(job.created_at for job in jobs)).total_seconds(), 3
        ) if jobs else None,
        "miss_reasons": dict(sorted(misses.items())),
        "by_category": dict(sorted(by_category.items())),
        "by_region": dict(sorted(by_region.items())),
        "provider_usage": list(quota),
    }
