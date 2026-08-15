from django.core.management.base import BaseCommand

from recommendations.models import Place, PlaceFeatureDocument
from recommendations.services.place_feature_document import build_place_feature_document


class Command(BaseCommand):
    help = "Build fact-only Place feature documents without calling an embedding API."

    def add_arguments(self, parser):
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--category", action="append")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        queryset = Place.objects.filter(id__gt=max(0, options["after_id"])).order_by("id")
        if options["category"]:
            queryset = queryset.filter(category__in=options["category"])
        if options["limit"] is not None:
            queryset = queryset[:max(1, options["limit"])]
        stats = {"read": 0, "created": 0, "updated": 0, "unchanged": 0, "last_id": options["after_id"]}
        for place in queryset.iterator(chunk_size=max(1, options["batch_size"])):
            stats["read"] += 1
            stats["last_id"] = place.id
            payload = build_place_feature_document(place)
            existing = PlaceFeatureDocument.objects.filter(place=place).first()
            if existing and existing.fingerprint == payload["fingerprint"]:
                stats["unchanged"] += 1
                continue
            stats["updated" if existing else "created"] += 1
            if not options["dry_run"]:
                PlaceFeatureDocument.objects.update_or_create(
                    place=place,
                    defaults={**payload, "embedding": [], "embedding_dimensions": 0, "embedding_provider": "", "embedding_model": "", "indexed_at": None},
                )
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Feature documents: read={stats['read']} created={stats['created']} "
            f"updated={stats['updated']} unchanged={stats['unchanged']} last_id={stats['last_id']}"
        ))
