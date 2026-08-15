from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from recommendations.models import PlaceTagCollectionJob, ProviderQuotaUsage


class Command(BaseCommand):
    help = "Recover place-tag jobs abandoned by stopped workers."

    def handle(self, *args, **options):
        count = recover_stale_jobs()
        self.stdout.write(self.style.SUCCESS("Recovered stale place-tag jobs: {}".format(count)))


def recover_stale_jobs():
    cutoff = timezone.now() - timedelta(minutes=settings.TAG_COLLECTION_STALE_LOCK_MINUTES)
    recovered = 0
    stale_ids = list(PlaceTagCollectionJob.objects.filter(
        status="processing",
        locked_at__lt=cutoff,
    ).values_list("id", flat=True))
    for job_id in stale_ids:
        with transaction.atomic():
            job = PlaceTagCollectionJob.objects.select_for_update().get(id=job_id)
            if job.status != "processing" or not job.locked_at or job.locked_at >= cutoff:
                continue
            quota = ProviderQuotaUsage.objects.select_for_update().filter(
                provider=job.provider,
                usage_date__in={
                    timezone.localdate(job.locked_at),
                    timezone.localdate(),
                    job.cycle_date,
                },
            ).order_by("-usage_date").first()
            if quota:
                quota.reserved_count = max(0, quota.reserved_count - job.planned_requests)
                quota.save(update_fields=["reserved_count", "updated_at"])
            job.status = "retry"
            job.next_attempt_at = timezone.now()
            job.locked_at = None
            job.worker_id = ""
            job.error_code = "stale_lock_recovered"
            job.save(update_fields=[
                "status", "next_attempt_at", "locked_at", "worker_id", "error_code", "updated_at",
            ])
            recovered += 1
    return recovered
