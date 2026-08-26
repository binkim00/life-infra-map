import json

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagCollectionJob, PlaceTagEvidence, ProviderQuotaUsage
from recommendations.services.tag_source_policy import NAVER_BLOG_SEARCH, WEB_AGGREGATE_SOURCE, WEB_SEARCH


class Command(BaseCommand):
    help = "Report daily Naver and Codex web collection outcomes for operations email."

    def add_arguments(self, parser):
        parser.add_argument("--date", default="")

    def handle(self, *args, **options):
        report_date = (
            timezone.localdate()
            if not options["date"]
            else timezone.datetime.fromisoformat(options["date"]).date()
        )
        self.stdout.write(json.dumps(build_daily_collection_report(report_date), ensure_ascii=False))


def build_daily_collection_report(report_date):
    jobs = list(PlaceTagCollectionJob.objects.filter(
        cycle_date=report_date,
        provider="naver_search",
    ).only("status", "error_code", "stats"))
    completed = [job for job in jobs if job.status == "completed"]
    useful = [job for job in completed if int((job.stats or {}).get("evidences") or 0) > 0]
    quota = ProviderQuotaUsage.objects.filter(
        provider="naver_search",
        usage_date=report_date,
    ).first()

    naver_evidence = _evidence_metrics(report_date, NAVER_BLOG_SEARCH)
    codex_evidence = _evidence_metrics(report_date, WEB_SEARCH)
    web_tags = _tag_metrics(report_date, WEB_AGGREGATE_SOURCE)
    return {
        "date": report_date.isoformat(),
        "generated_at": timezone.now().isoformat(),
        "naver": {
            "planned_jobs": len(jobs),
            "queued_jobs": sum(job.status == "queued" for job in jobs),
            "processing_jobs": sum(job.status == "processing" for job in jobs),
            "completed_jobs": len(completed),
            "useful_jobs": len(useful),
            "insufficient_jobs": sum(
                job.status == "completed" and job.error_code == "insufficient_evidence"
                for job in jobs
            ),
            "failed_jobs": sum(job.status in {"failed", "retry"} for job in jobs),
            "api_requests": quota.request_count if quota else 0,
            "rate_limited_requests": quota.rate_limited_count if quota else 0,
            **naver_evidence,
        },
        "codex_web": codex_evidence,
        "aggregate_tags": web_tags,
    }


def _day_bounds(report_date):
    start = timezone.make_aware(timezone.datetime.combine(report_date, timezone.datetime.min.time()))
    return start, start + timezone.timedelta(days=1)


def _evidence_metrics(report_date, source):
    start, end = _day_bounds(report_date)
    rows = PlaceTagEvidence.objects.filter(source=source, created_at__gte=start, created_at__lt=end)
    return {
        "new_evidence_rows": rows.count(),
        "new_evidence_places": rows.values("place_id").distinct().count(),
        "new_evidence_tags": rows.values("tag_id").distinct().count(),
    }


def _tag_metrics(report_date, source):
    start, end = _day_bounds(report_date)
    rows = PlaceTag.objects.filter(source=source, created_at__gte=start, created_at__lt=end)
    grouped = rows.values("status").annotate(count=Count("id"))
    return {
        "new_place_tags": rows.count(),
        "new_tagged_places": rows.values("place_id").distinct().count(),
        "by_status": {row["status"]: row["count"] for row in grouped},
    }
