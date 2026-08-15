from django.core.management.base import BaseCommand

from recommendations.models import PlaceTagEvidence
from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence


class Command(BaseCommand):
    help = "Materialize confirmed/candidate/rejected tags from active multi-source evidence."

    def add_arguments(self, parser):
        parser.add_argument("--place-id", type=int)
        parser.add_argument("--tag", action="append", default=[])
        parser.add_argument("--limit", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        pairs = PlaceTagEvidence.objects.select_related("place", "tag").order_by(
            "place_id", "tag_id"
        )
        if options["place_id"]:
            pairs = pairs.filter(place_id=options["place_id"])
        if options["tag"]:
            pairs = pairs.filter(tag__name__in=options["tag"])
        pairs = pairs.distinct().values_list("place_id", "tag_id")
        if options["limit"] is not None:
            pairs = pairs[: max(1, options["limit"])]

        from recommendations.models import Place, Tag

        stats = {"pairs": 0, "confirmed": 0, "candidate": 0, "rejected": 0, "none": 0}
        for place_id, tag_id in pairs.iterator():
            result = aggregate_tag_evidence(
                Place.objects.get(id=place_id),
                Tag.objects.get(id=tag_id),
                dry_run=options["dry_run"],
            )
            stats["pairs"] += 1
            stats[result["status"]] += 1
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Evidence aggregation complete: pairs={stats['pairs']} "
            f"confirmed={stats['confirmed']} candidate={stats['candidate']} "
            f"rejected={stats['rejected']} none={stats['none']}"
        ))
