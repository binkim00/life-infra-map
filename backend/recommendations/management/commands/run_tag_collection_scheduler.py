import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.management.commands.plan_daily_tag_collection import plan_daily_jobs
from recommendations.management.commands.recover_tag_collection_jobs import recover_stale_jobs
from recommendations.models import PlaceTagCollectionJob, ProviderQuotaUsage


class Command(BaseCommand):
    help = "Continuously plan and maintain unattended nationwide tag collection."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=int, default=60)

    def handle(self, *args, **options):
        while True:
            stats = scheduler_tick()
            self.stdout.write(
                "Tag scheduler: date={date} planned={planned} recovered={recovered} "
                "queued={queued} processing={processing} completed={completed} requests={requests}".format(**stats)
            )
            if options["once"]:
                break
            time.sleep(min(60, max(1, options["poll_seconds"])))


def scheduler_tick():
    today = timezone.localdate()
    recovered = recover_stale_jobs()
    planned = 0
    existing = PlaceTagCollectionJob.objects.filter(cycle_date=today).count()
    remaining = max(0, settings.TAG_COLLECTION_DAILY_PLACE_LIMIT - existing)
    if remaining:
        result = plan_daily_jobs(
            cycle_date=today,
            place_limit=remaining,
            provider=settings.TAG_ENRICHMENT_PROVIDER,
            mode=settings.TAG_COLLECTION_MODE,
        )
        planned = result["places"]
    counts = {
        status: PlaceTagCollectionJob.objects.filter(cycle_date=today, status=status).count()
        for status in ("queued", "processing", "completed")
    }
    quota = ProviderQuotaUsage.objects.filter(
        provider=settings.TAG_ENRICHMENT_PROVIDER,
        usage_date=today,
    ).first()
    return {
        "date": today,
        "planned": planned,
        "recovered": recovered,
        "requests": quota.request_count if quota else 0,
        **counts,
    }
