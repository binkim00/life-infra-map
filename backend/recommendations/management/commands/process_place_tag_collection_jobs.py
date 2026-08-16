import socket
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from recommendations.management.commands.process_tag_enrichment_queue import (
    save_place_candidate_evidence,
)
from recommendations.management.commands.generate_meaningful_place_tags import generate_meaningful_tags
from recommendations.models import Place, PlaceTagCollectionJob, ProviderQuotaUsage
from recommendations.services.place_tag_collection import collect_naver_place_evidence


class Command(BaseCommand):
    help = "Safely process place-level meaningful-tag collection jobs."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--poll-seconds", type=int, default=None)
        parser.add_argument("--worker-id", default="")

    def handle(self, *args, **options):
        if not settings.TAG_ENRICHMENT_ENABLED:
            raise CommandError("TAG_ENRICHMENT_ENABLED is false.")
        worker_id = options["worker_id"] or "{}:{}".format(socket.gethostname(), id(self))
        batch_size = options["limit"] or settings.TAG_COLLECTION_WORKER_BATCH_SIZE
        poll_seconds = options["poll_seconds"] or settings.TAG_COLLECTION_POLL_SECONDS
        totals = {"processed": 0, "evidences": 0, "insufficient": 0, "retried": 0, "failed": 0}
        while True:
            stats = process_jobs(limit=batch_size, worker_id=worker_id)
            for key in totals:
                totals[key] += stats[key]
            if not options["watch"]:
                break
            if stats.get("quota_exhausted"):
                time.sleep(min(60, poll_seconds))
            elif not stats["processed"]:
                time.sleep(min(60, poll_seconds))
        self.stdout.write(self.style.SUCCESS(
            "Place tag worker: processed={processed} evidences={evidences} "
            "insufficient={insufficient} retried={retried} failed={failed}".format(**totals)
        ))


def process_jobs(*, limit=10, worker_id="worker", collector=None):
    default_collector = collector is None
    collector = collector or collect_naver_place_evidence
    stats = {
        "processed": 0,
        "evidences": 0,
        "insufficient": 0,
        "retried": 0,
        "failed": 0,
        "quota_exhausted": False,
    }
    for _ in range(max(1, limit)):
        job, quota = claim_next_job(worker_id=worker_id)
        if job is None:
            stats["quota_exhausted"] = quota == "quota_exhausted"
            break
        stats["processed"] += 1
        structured_evidences = 0
        if getattr(settings, "TAG_COLLECTION_STRUCTURED_FIRST", True):
            structured_stats = generate_meaningful_tags(
                Place.objects.filter(id=job.place_id),
                dry_run=False,
            )
            structured_evidences = structured_stats["evidence"]
        try:
            if default_collector:
                result = collector(
                    job.place,
                    job.requested_tags,
                    strategy="adaptive" if job.context.get("adaptive") else "standard",
                    targeted_tags=job.context.get("targeted_tags") or (),
                    allow_ai=(
                        getattr(settings, "TAG_COLLECTION_AI_EXTRACTOR_ENABLED", False)
                        and job.priority >= settings.TAG_COLLECTION_AI_PRIORITY_THRESHOLD
                    ),
                )
            else:
                result = collector(job.place, job.requested_tags)
        except Exception as exc:
            result = {"executed": True, "requests": 0, "evidences": [], "error": exc.__class__.__name__}
        requests_made = max(0, min(job.planned_requests, int(result.get("requests") or 0)))
        settle_quota(
            job,
            requests_made,
            succeeded=not result.get("error") or result.get("error") == "insufficient_evidence",
            rate_limited=result.get("error") == "rate_limited",
        )
        evidences = result.get("evidences") or []
        for evidence in evidences:
            observed_at = _observed_at(evidence.get("observed_date"))
            save_place_candidate_evidence(
                job.place,
                evidence["tag_name"],
                evidence,
                observed_at=observed_at,
            )
        stats["evidences"] += len(evidences)
        error = str(result.get("error") or "")
        if error in {"", "insufficient_evidence"}:
            job.status = "completed"
            job.error_code = error
            job.next_attempt_at = None
            if error:
                stats["insufficient"] += 1
        elif job.attempt_count < 3:
            job.status = "retry"
            job.error_code = error[:100]
            job.next_attempt_at = timezone.now() + timedelta(minutes=15 * (2 ** (job.attempt_count - 1)))
            stats["retried"] += 1
        else:
            job.status = "failed"
            job.error_code = error[:100]
            job.next_attempt_at = None
            stats["failed"] += 1
        job.stats = {
            "requests": requests_made,
            "evidences": len(evidences),
            "structured_evidences": structured_evidences,
            "ai_calls": int(result.get("ai_calls") or 0),
            "miss_reason": result.get("miss_reason") or "",
            "diagnostics": result.get("diagnostics") or {},
        }
        job.error_message = error[:1000]
        job.locked_at = None
        job.worker_id = ""
        job.save(update_fields=[
            "status", "error_code", "error_message", "next_attempt_at", "stats",
            "locked_at", "worker_id", "updated_at",
        ])
    return stats


def claim_next_job(*, worker_id):
    today = timezone.localdate()
    now = timezone.now()
    with transaction.atomic():
        job = PlaceTagCollectionJob.objects.select_for_update(skip_locked=True).filter(
            status__in=("queued", "retry"),
            cycle_date__lte=today,
        ).filter(
            next_attempt_at__isnull=True,
        ).select_related("place").order_by("-priority", "created_at").first()
        if job is None:
            job = PlaceTagCollectionJob.objects.select_for_update(skip_locked=True).filter(
                status="retry",
                cycle_date__lte=today,
                next_attempt_at__lte=now,
            ).select_related("place").order_by("-priority", "created_at").first()
        if job is None:
            return None, "empty"
        quota, _ = ProviderQuotaUsage.objects.select_for_update().get_or_create(
            provider=job.provider,
            usage_date=today,
            defaults={"daily_limit": settings.TAG_COLLECTION_DAILY_API_LIMIT},
        )
        safe_limit = quota.daily_limit * settings.TAG_COLLECTION_QUOTA_PERCENT // 100
        if quota.reserved_count + quota.request_count + job.planned_requests > safe_limit:
            return None, "quota_exhausted"
        quota.reserved_count += job.planned_requests
        quota.save(update_fields=["reserved_count", "updated_at"])
        job.status = "processing"
        job.locked_at = now
        job.worker_id = worker_id[:100]
        job.attempt_count += 1
        job.save(update_fields=["status", "locked_at", "worker_id", "attempt_count", "updated_at"])
        return job, quota


def settle_quota(job, requests_made, *, succeeded, rate_limited=False):
    today = timezone.localdate()
    ProviderQuotaUsage.objects.filter(
        provider=job.provider,
        usage_date=today,
    ).update(
        reserved_count=F("reserved_count") - job.planned_requests,
        request_count=F("request_count") + requests_made,
        success_count=F("success_count") + (requests_made if succeeded else 0),
        failed_count=F("failed_count") + (0 if succeeded else requests_made),
        rate_limited_count=F("rate_limited_count") + (requests_made if rate_limited else 0),
    )


def _observed_at(value):
    text = str(value or "").strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return timezone.make_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return timezone.now()
