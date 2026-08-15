from django.core.management.base import BaseCommand, CommandError

from recommendations.management.commands.import_localdata_records import (
    parse_administrative_names,
    save_batch,
)
from recommendations.models import Place, SourcePlaceRecord


class Command(BaseCommand):
    help = "Stage legacy official Place rows for Kakao ID matching."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)
        parser.add_argument("--dataset", required=True)
        parser.add_argument("--category", default="")
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 1:
            raise CommandError("--limit must be at least 1.")
        queryset = Place.objects.filter(
            source=options["source"],
            id__gt=max(0, options["after_id"]),
        ).exclude(name="").exclude(external_id="").order_by("id")
        if options["category"]:
            queryset = queryset.filter(category=options["category"])
        if options["limit"] is not None:
            queryset = queryset[:options["limit"]]

        stats = {"read": 0, "created": 0, "updated": 0, "duplicates": 0, "last_id": options["after_id"]}
        batch = []
        for place in queryset.iterator(chunk_size=max(1, options["batch_size"])):
            stats["read"] += 1
            stats["last_id"] = place.id
            sido_name, sigungu_name = parse_administrative_names(
                place.address or place.detail_location
            )
            batch.append(SourcePlaceRecord(
                source=options["source"][:50],
                dataset=options["dataset"][:100],
                source_record_id=place.external_id[:160],
                name=place.name[:255],
                category=place.category[:100],
                is_active=True,
                address=place.address[:500],
                road_address=place.detail_location[:500],
                sido_name=sido_name[:50],
                sigungu_name=sigungu_name[:80],
                source_x=str(place.lng),
                source_y=str(place.lat),
                coordinate_reference_system="EPSG:4326",
                raw={"legacy_place_id": place.id, "source_name": place.source_name},
            ))
            if not options["dry_run"] and len(batch) >= max(1, options["batch_size"]):
                save_batch(batch, stats)
                batch = []
        if not options["dry_run"] and batch:
            save_batch(batch, stats)

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Existing-place staging complete: read={stats['read']} "
            f"created={stats['created']} updated={stats['updated']} "
            f"duplicates={stats['duplicates']} last_id={stats['last_id']}"
        ))
