import socket
import time
from recommendations.services.collection_telemetry import observed_sleep, emit_event, elapsed_ms, extraction_counts
from contextlib import contextmanager
from threading import Event, Thread
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections, DatabaseError, transaction
from django.utils import timezone

from recommendations.management.commands.process_tag_enrichment_queue import (
    save_place_candidate_evidence,
)
from recommendations.management.commands.generate_meaningful_place_tags import generate_meaningful_tags
from recommendations.models import (
    Place, PlaceTag, PlaceTagCollectionJob, ProviderQuotaUsage, TagEnrichmentRequest,
)
from recommendations.services.place_tag_collection import collect_naver_place_evidence
from recommendations.services.collection_resources import planner_transaction


@contextmanager
def claim_heartbeat(job, *, enabled, interval=30):
    stop = Event()

    def renew():
        try:
            while not stop.wait(interval):
                try:
                    with planner_transaction():
                        updated = PlaceTagCollectionJob.objects.filter(
                            pk=job.pk, status="processing", worker_id=job.worker_id,
                            attempt_count=job.attempt_count,
                        ).update(locked_at=timezone.now())
                    if not updated:
                        return
                except DatabaseError:
                    # Ownership checks still fence a result after a lost lease.
                    return
        finally:
            connections.close_all()

    thread = Thread(target=renew, daemon=True) if enabled else None
    if thread:
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread:
            thread.join(timeout=3)


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
            stats = process_jobs(limit=batch_size, worker_id=worker_id,
                                 pace=options["watch"] and getattr(settings, "TAG_COLLECTION_WORKER_PACING_ENABLED", False))
            for key in totals:
                totals[key] += stats[key]
            if not options["watch"]:
                break
            if stats.get("quota_exhausted"):
                observed_sleep(min(60, poll_seconds), component="worker", reason="quota_exhausted")
            elif not stats["processed"]:
                observed_sleep(min(60, poll_seconds), component="worker", reason="empty_queue")
        self.stdout.write(self.style.SUCCESS(
            "Place tag worker: processed={processed} evidences={evidences} "
            "insufficient={insufficient} retried={retried} failed={failed}".format(**totals)
        ))


def process_jobs(*, limit=10, worker_id="worker", collector=None, pace=False):
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
        started = time.monotonic()
        started_at = timezone.now()
        job, quota = claim_next_job(worker_id=worker_id)
        if job is None:
            stats["quota_exhausted"] = quota == "quota_exhausted"
            emit_event("worker", {"reason": "quota_exhausted" if stats["quota_exhausted"] else "empty_queue",
                                  "claim_ms": elapsed_ms(started)})
            break
        stats["processed"] += 1
        timings = {"claim_ms": elapsed_ms(started)}
        stage_started = time.monotonic()
        collector_started = None
        resumed_checkpoint = job.result_checkpoint is not None
        structured_evidences = 0
        try:
            if job.result_checkpoint is None and getattr(settings, "TAG_COLLECTION_STRUCTURED_FIRST", True):
                with planner_transaction():
                    structured_stats = generate_meaningful_tags(
                        Place.objects.filter(id=job.place_id),
                        dry_run=False,
                    )
                structured_evidences = structured_stats["evidence"]
            timings["structured_ms"] = elapsed_ms(stage_started)
            collector_started = time.monotonic()
            if job.result_checkpoint is not None:
                result = job.result_checkpoint
            elif default_collector:
                with claim_heartbeat(job, enabled=connection.vendor == "postgresql"):
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
        timings.setdefault("structured_ms", elapsed_ms(stage_started) if collector_started is None else 0)
        timings["collector_ms"] = elapsed_ms(collector_started) if collector_started is not None and not resumed_checkpoint else 0
        if not resumed_checkpoint:
            result = {**result, "_collection_telemetry": {
                "attempt": job.attempt_count, "started_at": started_at.isoformat(),
                "structured_ms": timings["structured_ms"], "collector_ms": timings["collector_ms"],
            }}
        checkpoint_origin = result.get("_collection_telemetry") or {}
        stage_started = time.monotonic()
        # Persist external-call facts before evidence materialization. A crash
        # during that later DB phase resumes this result without another API call.
        with planner_transaction():
            current = PlaceTagCollectionJob.objects.select_for_update().get(pk=job.pk)
            if (current.status != "processing" or current.worker_id != job.worker_id or
                    current.attempt_count != job.attempt_count):
                continue
            settled_now = settle_quota(job, int(result.get("requests") or 0),
                         succeeded=not result.get("error") or result.get("error") == "insufficient_evidence",
                         rate_limited=result.get("error") == "rate_limited")
            current.result_checkpoint = result
            current.save(update_fields=["result_checkpoint", "updated_at"])
        timings["settle_ms"] = elapsed_ms(stage_started)
        emit_event("worker_checkpoint", {
            "cycle_date": job.cycle_date.isoformat(), "attempt": job.attempt_count,
            "resumed_checkpoint": int(resumed_checkpoint), "settled_now": int(settled_now),
            "requests": max(0, int(result.get("requests") or 0)) if settled_now else 0,
        })
        stage_started = time.monotonic()
        with planner_transaction():
            current = PlaceTagCollectionJob.objects.select_for_update().get(pk=job.pk)
            if (current.status != "processing" or current.worker_id != job.worker_id or
                    current.attempt_count != job.attempt_count):
                continue
            requests_made = max(0, int(result.get("requests") or 0))
            settle_quota(
                job,
                requests_made,
                succeeded=not result.get("error") or result.get("error") == "insufficient_evidence",
                rate_limited=result.get("error") == "rate_limited",
            )
            evidences = result.get("evidences") or []
            new_evidences = 0
            active_evidences = 0
            new_active_evidences = 0
            ai_saved_evidences = 0
            ai_new_evidences = 0
            ai_active_evidences = 0
            strength_counts = {}
            satisfied_tag_names = set()
            quality = {"expired": 0, "reused": 0, "active_positive": 0,
                       "active_accepted": 0, "active_positive_accepted": 0}
            for evidence in evidences:
                observed_at = _observed_at(evidence.get("observed_date"))
                saved, created = save_place_candidate_evidence(
                    job.place,
                    evidence["tag_name"],
                    evidence,
                    observed_at=observed_at,
                )
                is_active = saved.expires_at is None or saved.expires_at > timezone.now()
                new_evidences += int(created)
                active_evidences += int(is_active)
                new_active_evidences += int(created and is_active)
                review = getattr(saved, "review", None)
                accepted = review is None or review.status == "approved"
                quality["expired"] += int(not is_active)
                quality["reused"] += int(not created)
                quality["active_positive"] += int(is_active and saved.polarity == "positive")
                quality["active_accepted"] += int(is_active and accepted)
                quality["active_positive_accepted"] += int(is_active and accepted and saved.polarity == "positive")
                extraction = evidence.get("extraction") or {}
                strength = extraction.get("strength") or "UNKNOWN"
                strength_counts[strength] = int(strength_counts.get(strength) or 0) + 1
                if extraction.get("method") == "ai":
                    ai_saved_evidences += 1
                    ai_new_evidences += int(created)
                    ai_active_evidences += int(is_active)
                if is_active and saved.polarity in {"positive", "negative"}:
                    satisfied_tag_names.add(saved.tag.name)
            completed_requests = 0
            if satisfied_tag_names:
                completed_requests = TagEnrichmentRequest.objects.filter(
                    place_id=job.place_id,
                    tag_name__in=satisfied_tag_names,
                ).exclude(status="completed").update(
                    status="completed",
                    next_attempt_at=None,
                    locked_at=None,
                    error_message="",
                    updated_at=timezone.now(),
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
            finished_at = timezone.now()
            timings["save_and_finalize_ms"] = elapsed_ms(stage_started)
            timings["processing_ms"] = elapsed_ms(started)
            telemetry = {
                "resumed_checkpoint": resumed_checkpoint, "checkpoint_collection": checkpoint_origin,
                "checkpoint_collection_unmeasured": resumed_checkpoint and not bool(checkpoint_origin),
                "version": 1, "cycle_date": job.cycle_date.isoformat(),
                "started_at": started_at.isoformat(), "finished_at": finished_at.isoformat(),
                "completed_date": timezone.localdate(finished_at).isoformat() if job.status == "completed" else None,
                "reservation_date": (job.reservation_date or quota.usage_date).isoformat(),
                "settlement_date": (job.reservation_date or quota.usage_date).isoformat(), "attempt": job.attempt_count,
                "timings_ms": timings, "quality_at_save": quality,
                "extractions": extraction_counts(result.get("search_attempts") or []),
            }
            attempt_metrics = list((current.stats or {}).get("attempt_metrics") or [])
            attempt_metrics.append(telemetry)
            job.stats = {
                "telemetry": telemetry,
                "attempt_metrics": attempt_metrics[-3:],
                "requests": requests_made,
                "evidences": len(evidences),
                "new_evidences": new_evidences,
                "active_evidences": active_evidences,
                "new_active_evidences": new_active_evidences,
                "completed_enrichment_requests": completed_requests,
                "structured_evidences": structured_evidences,
                "ai_calls": int(result.get("ai_calls") or 0),
                "ai_metrics": result.get("ai_metrics") or {},
                "ai_attribution": {
                    "saved_evidences": ai_saved_evidences,
                    "new_evidences": ai_new_evidences,
                    "active_evidences": ai_active_evidences,
                },
                "evidence_strengths": strength_counts,
                "miss_reason": result.get("miss_reason") or "",
                "diagnostics": result.get("diagnostics") or {},
                "search_attempts": result.get("search_attempts") or [],
            }
            job.error_message = error[:1000]
            job.result_checkpoint = None
            job.locked_at = None
            job.worker_id = ""
            job.save(update_fields=[
                "status", "error_code", "error_message", "next_attempt_at", "stats",
                "locked_at", "worker_id", "result_checkpoint", "updated_at",
            ])
        emit_event("worker_attempt", {
            "cycle_date": job.cycle_date.isoformat(), "status": job.status,
            "attempt": job.attempt_count, "completed_date": telemetry["completed_date"],
            "reservation_date": telemetry["reservation_date"], "settlement_date": telemetry["settlement_date"],
            "evidences": len(evidences), "new_evidences": new_evidences,
            "requests": requests_made, "quality_at_save": quality, "timings_ms": timings,
        })
        if pace:
            interval = 86400 / max(1, settings.TAG_COLLECTION_DAILY_PLACE_LIMIT)
            observed_sleep(min(60, max(0, interval - (time.monotonic() - started))), component="worker", reason="pacing")
    return stats


def claim_next_job(*, worker_id):
    today = timezone.localdate()
    now = timezone.now()
    with transaction.atomic():
        job = PlaceTagCollectionJob.objects.select_for_update(skip_locked=True).filter(
            provider=settings.TAG_ENRICHMENT_PROVIDER,
            status__in=("queued", "retry"),
            cycle_date__lte=today,
        ).filter(
            next_attempt_at__isnull=True,
        ).select_related("place").order_by("-priority", "created_at").first()
        if job is None:
            job = PlaceTagCollectionJob.objects.select_for_update(skip_locked=True).filter(
                provider=settings.TAG_ENRICHMENT_PROVIDER,
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
        safe_limit = min(quota.daily_limit, settings.TAG_COLLECTION_DAILY_API_LIMIT) * settings.TAG_COLLECTION_QUOTA_PERCENT // 100
        if job.result_checkpoint is None and quota.reserved_count + quota.request_count + job.planned_requests > safe_limit:
            return None, "quota_exhausted"
        if job.result_checkpoint is None:
            quota.reserved_count += job.planned_requests
            quota.save(update_fields=["reserved_count", "updated_at"])
        job.status = "processing"
        job.locked_at = now
        job.worker_id = worker_id[:100]
        job.attempt_count += 1
        if job.result_checkpoint is None:
            job.reservation_date = today
            job.quota_settled_at = None
        job.save(update_fields=["status", "locked_at", "worker_id", "attempt_count", "reservation_date", "quota_settled_at", "updated_at"])
        return job, quota


def settle_quota(job, requests_made, *, succeeded, rate_limited=False):
    with transaction.atomic():
        current = PlaceTagCollectionJob.objects.select_for_update().get(pk=job.pk)
        if (current.status != "processing" or current.worker_id != job.worker_id or
                current.attempt_count != job.attempt_count or current.quota_settled_at):
            return False
        reservation_date = current.reservation_date or timezone.localdate(current.locked_at)
        quota = ProviderQuotaUsage.objects.select_for_update().get(
            provider=job.provider, usage_date=reservation_date,
        )
        # A collector exceeding its estimate must consume its actual quota;
        # clamping here hides overruns from the next claim's safety check.
        requests_made = max(0, int(requests_made))
        quota.reserved_count = max(0, quota.reserved_count - current.planned_requests)
        quota.request_count += requests_made
        quota.success_count += requests_made if succeeded else 0
        quota.failed_count += 0 if succeeded else requests_made
        quota.rate_limited_count += requests_made if rate_limited else 0
        quota.save(update_fields=["reserved_count", "request_count", "success_count", "failed_count", "rate_limited_count", "updated_at"])
        current.quota_settled_at = timezone.now()
        current.save(update_fields=["quota_settled_at", "updated_at"])
        job.quota_settled_at = current.quota_settled_at
        return True


def _observed_at(value):
    text = str(value or "").strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return timezone.make_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None
