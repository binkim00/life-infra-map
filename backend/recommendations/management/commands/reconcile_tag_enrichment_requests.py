from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from recommendations.models import PlaceTagEvidence, TagEnrichmentRequest


class Command(BaseCommand):
    help = "Close queued tag-enrichment requests already satisfied by active evidence."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        now = timezone.now()
        active_evidence = PlaceTagEvidence.objects.filter(
            place_id=OuterRef("place_id"),
            tag__name=OuterRef("tag_name"),
            polarity__in=("positive", "negative"),
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        queryset = TagEnrichmentRequest.objects.exclude(status="completed").annotate(
            has_active_evidence=Exists(active_evidence),
        ).filter(has_active_evidence=True).order_by("-priority", "created_at")
        limit = options.get("limit")
        request_ids = list(queryset.values_list("id", flat=True)[:limit]) if limit else list(
            queryset.values_list("id", flat=True)
        )
        updated = 0
        if options["apply"] and request_ids:
            updated = TagEnrichmentRequest.objects.filter(id__in=request_ids).update(
                status="completed",
                next_attempt_at=None,
                locked_at=None,
                error_message="",
                updated_at=now,
            )
        mode = "applied" if options["apply"] else "dry-run"
        self.stdout.write(
            "Tag enrichment reconciliation: mode={} matched={} updated={}".format(
                mode,
                len(request_ids),
                updated,
            )
        )
