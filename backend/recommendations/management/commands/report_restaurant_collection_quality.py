import json
from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from recommendations.models import Place, PlaceTagCollectionJob
from recommendations.services.restaurant_collection_quality import restaurant_collection_quality


class Command(BaseCommand):
    help = "Report explainable restaurant enrichment priority penalties without changing Places."

    def add_arguments(self, parser):
        parser.add_argument("--region", default="서울")

    def handle(self, *args, **options):
        region = options["region"].strip()
        places = Place.objects.filter(category="restaurant").filter(
            Q(address__startswith=region) | Q(detail_location__startswith=region)
        )
        ids = places.values_list("id", flat=True)
        history = {
            row["place_id"]: row
            for row in PlaceTagCollectionJob.objects.filter(place_id__in=ids).values("place_id").annotate(
                identity_misses=Count("id", filter=Q(stats__miss_reason="IDENTITY_MISMATCH")),
                successful_jobs=Count("id", filter=Q(stats__evidences__gt=0)),
            )
        }
        flags = Counter()
        lowered = 0
        distribution = Counter()
        examples = {}
        for place in places.iterator(chunk_size=2000):
            stats = history.get(place.id, {})
            result = restaurant_collection_quality(
                place,
                identity_misses=stats.get("identity_misses", 0),
                successful_jobs=stats.get("successful_jobs", 0),
            )
            bucket = "low" if result["score"] < 0 else "normal"
            distribution[bucket] += 1
            lowered += int(result["score"] < 0)
            for flag in result["flags"]:
                flags[flag] += 1
                examples.setdefault(flag, {"place_id": place.id, "name": place.name, "score": result["score"]})
        self.stdout.write(json.dumps({
            "region": region,
            "places": places.count(),
            "priority_lowered": lowered,
            "deleted": 0,
            "distribution": dict(distribution),
            "flags": dict(flags.most_common()),
            "examples": examples,
        }, ensure_ascii=False, indent=2))
