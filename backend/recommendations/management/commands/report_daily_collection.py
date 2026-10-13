import json
from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
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
    now = timezone.now()
    start, end = _day_bounds(report_date)
    jobs = list(PlaceTagCollectionJob.objects.filter(
        cycle_date=report_date,
        provider="naver_search",
    ).values("status", "error_code", "stats__evidences", "stats__new_evidences",
             "stats__requests", "stats__miss_reason", "stats__telemetry", "stats__attempt_metrics"))
    completed = [job for job in jobs if job["status"] == "completed"]
    useful = [job for job in completed if int(job["stats__evidences"] or 0) > 0]
    quota = ProviderQuotaUsage.objects.filter(
        provider="naver_search",
        usage_date=report_date,
    ).first()

    naver_evidence = _evidence_metrics(report_date, NAVER_BLOG_SEARCH, now=now)
    codex_evidence = _evidence_metrics(report_date, WEB_SEARCH, now=now)
    web_tags = _tag_metrics(report_date, WEB_AGGREGATE_SOURCE)
    return {
        "date": report_date.isoformat(),
        "generated_at": now.isoformat(),
        "periods": {"timezone": str(timezone.get_current_timezone()),
                    "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat(),
                    "jobs": "cycle_date", "evidence_and_new_tags": "created_at",
                    "quota": "reservation usage_date", "validity_as_of": now.isoformat()},
        "calendar_completion": _calendar_completion(report_date, start, end),
        "naver": {
            "planned_jobs": len(jobs),
            "queued_jobs": sum(job["status"] == "queued" for job in jobs),
            "processing_jobs": sum(job["status"] == "processing" for job in jobs),
            "completed_jobs": len(completed),
            "useful_jobs": len(useful),
            "insufficient_jobs": sum(
                job["status"] == "completed" and job["error_code"] == "insufficient_evidence"
                for job in jobs
            ),
            "failed_jobs": sum(job["status"] in {"failed", "retry"} for job in jobs),
            "api_requests": quota.request_count if quota else 0,
            "rate_limited_requests": quota.rate_limited_count if quota else 0,
            "cycle_metrics": _cycle_metrics(jobs),
            **naver_evidence,
        },
        "codex_web": codex_evidence,
        "aggregate_tags": web_tags,
    }


def _day_bounds(report_date):
    start = timezone.make_aware(timezone.datetime.combine(report_date, timezone.datetime.min.time()))
    return start, start + timezone.timedelta(days=1)


def _evidence_metrics(report_date, source, *, now):
    start, end = _day_bounds(report_date)
    rows = PlaceTagEvidence.objects.filter(source=source, created_at__gte=start, created_at__lt=end)
    active = Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    accepted = Q(review__isnull=True) | Q(review__status="approved")
    positive = Q(polarity="positive")
    metrics = rows.aggregate(
        new_evidence_rows=Count("id"), new_evidence_places=Count("place_id", distinct=True),
        new_evidence_tags=Count("tag_id", distinct=True),
        active_rows=Count("id", filter=active),
        expired_rows=Count("id", filter=Q(expires_at__lte=now)),
        active_positive_rows=Count("id", filter=active & positive),
        active_accepted_rows=Count("id", filter=active & accepted),
        active_positive_accepted_rows=Count("id", filter=active & positive & accepted),
    )
    return {**metrics, "by_review_status": {
        row["review__status"] or "unreviewed": row["n"]
        for row in rows.values("review__status").annotate(n=Count("id"))
    }}


def _cycle_metrics(jobs):
    reasons, timings, stages, attempts = Counter(), Counter(), Counter(), Counter()
    measured = 0
    checkpoint_resumed = 0
    checkpoint_unmeasured = 0
    for job in jobs:
        if job["status"] == "completed":
            reasons[job["stats__miss_reason"] or "evidence_or_no_reason"] += 1
        telemetry = job["stats__telemetry"] or {}
        measured += int(bool(telemetry))
        checkpoint_resumed += int(bool(telemetry.get("resumed_checkpoint")))
        checkpoint_unmeasured += int(bool(telemetry.get("checkpoint_collection_unmeasured")))
        stages.update(telemetry.get("extractions") or {})
        # Last-attempt snapshots only; retry attempts are kept separately in DB.
        timings.update(telemetry.get("timings_ms") or {})
        for attempt in job["stats__attempt_metrics"] or []:
            attempts.update(attempt.get("timings_ms") or {})
    return {
        "completed_miss_reasons": dict(reasons), "measured_jobs": measured,
        "unmeasured_jobs": len(jobs) - measured,
        "checkpoint_resumed_jobs": checkpoint_resumed,
        "checkpoint_original_timing_unmeasured_jobs": checkpoint_unmeasured,
        "last_attempt_timings_ms": dict(timings), "last_attempt_extractions": dict(stages),
        "retained_attempt_timings_ms": dict(attempts),
        "returned_evidence_rows": sum(int(row["stats__evidences"] or 0) for row in jobs),
        "new_saved_evidence_rows": sum(int(row["stats__new_evidences"] or 0) for row in jobs),
        "cycle_settled_requests": sum(int(row["stats__requests"] or 0) for row in jobs),
    }


def _calendar_completion(report_date, start, end):
    # Keep the query bounded by the indexed cycle_date/provider prefix.
    # Older backlogs are explicitly outside this window, not silently zero.
    lookback = report_date - timezone.timedelta(days=7)
    rows = PlaceTagCollectionJob.objects.filter(
        provider="naver_search", status="completed", cycle_date__gte=lookback,
        cycle_date__lte=report_date,
    ).filter(
        Q(stats__telemetry__completed_date=report_date.isoformat()) |
        (Q(stats__telemetry__isnull=True) & Q(updated_at__gte=start, updated_at__lt=end))
    ).values("cycle_date", "stats__telemetry")
    by_cycle = Counter()
    exact, legacy = 0, 0
    for row in rows:
        by_cycle[row["cycle_date"].isoformat()] += 1
        if row["stats__telemetry"]:
            exact += 1
        else:
            legacy += 1
    return {"completed_jobs": exact + legacy, "instrumented_completed_jobs": exact,
            "legacy_updated_at_proxy_jobs": legacy, "by_cycle_date": dict(by_cycle),
            "cycle_window_start": lookback.isoformat(), "older_cycles_excluded": True}


def _tag_metrics(report_date, source):
    start, end = _day_bounds(report_date)
    rows = PlaceTag.objects.filter(source=source, created_at__gte=start, created_at__lt=end)
    grouped = rows.values("status").annotate(count=Count("id"))
    return {
        "new_place_tags": rows.count(),
        "new_tagged_places": rows.values("place_id").distinct().count(),
        "new_verified_place_tags": rows.filter(status="confirmed", is_verified=True).count(),
        "existing_tag_status_transitions": None,
        "by_status": {row["status"]: row["count"] for row in grouped},
    }
