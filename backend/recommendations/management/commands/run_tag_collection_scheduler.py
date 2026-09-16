import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from recommendations.management.commands.plan_daily_tag_collection import plan_daily_jobs
from recommendations.management.commands.recover_tag_collection_jobs import recover_stale_jobs
from recommendations.models import OperationsDashboardSnapshot, PlaceTagCollectionJob, ProviderQuotaUsage
from recommendations.services.operations_dashboard import refresh_operations_snapshot


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
                "queued={queued} processing={processing} completed={completed} useful={useful_completed} "
                "insufficient={insufficient_evidence} requests={requests} "
                "dashboard_snapshot={snapshot_refreshed}".format(**stats)
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
        focus_regions = tuple(
            getattr(settings, "TAG_COLLECTION_FOCUS_REGIONS", ()) or ()
        )
        if not focus_regions:
            focus_region = getattr(settings, "TAG_COLLECTION_FOCUS_REGION", "").strip()
            focus_regions = (focus_region,) if focus_region else ()
        raw_weights = str(
            getattr(settings, "TAG_COLLECTION_FOCUS_REGION_WEIGHTS", "") or ""
        ).split(",")
        try:
            parsed_weights = tuple(max(0, int(value.strip())) for value in raw_weights)
        except ValueError:
            parsed_weights = ()
        region_priority_weights = (
            dict(zip(focus_regions, parsed_weights))
            if len(parsed_weights) == len(focus_regions) and sum(parsed_weights) > 0
            else None
        )
        if region_priority_weights:
            total_weight = sum(region_priority_weights.values())
            targets = {
                region: settings.TAG_COLLECTION_DAILY_PLACE_LIMIT * weight // total_weight
                for region, weight in region_priority_weights.items()
            }
            for region in focus_regions:
                if sum(targets.values()) >= settings.TAG_COLLECTION_DAILY_PLACE_LIMIT:
                    break
                targets[region] += 1
            existing_regions = dict(
                PlaceTagCollectionJob.objects.filter(cycle_date=today)
                .values_list("context__region")
                .annotate(count=Count("id"))
            )
            deficits = {
                region: max(0, targets[region] - int(existing_regions.get(region, 0)))
                for region in focus_regions
            }
            if sum(deficits.values()) == remaining:
                region_priority_weights = deficits
        focus_categories = tuple(
            getattr(settings, "TAG_COLLECTION_FOCUS_CATEGORIES", ()) or ()
        )
        result = plan_daily_jobs(
            cycle_date=today,
            place_limit=remaining,
            provider=settings.TAG_ENRICHMENT_PROVIDER,
            mode=settings.TAG_COLLECTION_MODE,
            regions=focus_regions if settings.TAG_COLLECTION_MODE == "bootstrap" and focus_regions else None,
            categories=focus_categories if settings.TAG_COLLECTION_MODE == "bootstrap" and focus_categories else None,
            region_priority_weights=region_priority_weights,
        )
        planned = result["places"]
    counts = {
        status: PlaceTagCollectionJob.objects.filter(cycle_date=today, status=status).count()
        for status in ("queued", "processing", "completed")
    }
    insufficient_evidence = PlaceTagCollectionJob.objects.filter(
        cycle_date=today,
        status="completed",
        error_code="insufficient_evidence",
    ).count()
    useful_completed = max(0, counts["completed"] - insufficient_evidence)
    quota = ProviderQuotaUsage.objects.filter(
        provider=settings.TAG_ENRICHMENT_PROVIDER,
        usage_date=today,
    ).first()
    snapshot_refreshed = False
    if not counts["queued"] and not counts["processing"]:
        latest_completed = PlaceTagCollectionJob.objects.filter(
            cycle_date=today, status="completed",
        ).order_by("-updated_at").values_list("updated_at", flat=True).first()
        snapshot = OperationsDashboardSnapshot.objects.filter(snapshot_date=today).first()
        quiet_cutoff = timezone.now() - timedelta(
            minutes=settings.TAG_COLLECTION_SNAPSHOT_QUIET_MINUTES
        )
        if (
            latest_completed
            and latest_completed <= quiet_cutoff
            and (not snapshot or snapshot.generated_at < latest_completed)
        ):
            refresh_operations_snapshot()
            snapshot_refreshed = True
    return {
        "date": today,
        "planned": planned,
        "recovered": recovered,
        "requests": quota.request_count if quota else 0,
        "useful_completed": useful_completed,
        "insufficient_evidence": insufficient_evidence,
        "snapshot_refreshed": snapshot_refreshed,
        **counts,
    }
