import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.models import Place, PlaceFeatureDocument
from recommendations.services.place_feature_document import feature_document_payload
from recommendations.services.semantic_sampling import sample_distribution, stratified_feature_sample


class Command(BaseCommand):
    help = "Prepare at most 1,000 fact-only, region/category/feature-stratified documents."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=1000)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--json", default="tmp/semantic_stratified_1000.json")
        parser.add_argument("--csv", default="tmp/semantic_stratified_1000.csv")

    def handle(self, *args, **options):
        rows = stratified_feature_sample(limit=options["limit"])
        places = Place.objects.in_bulk(row["place_id"] for row in rows)
        stats = {"new": 0, "updated": 0, "unchanged": 0, "skipped": 0}
        for row in rows:
            place = places.get(row["place_id"])
            if not place or not row["features"]:
                stats["skipped"] += 1
                continue
            payload = feature_document_payload(place, row["features"])
            existing = PlaceFeatureDocument.objects.filter(place_id=place.id).first()
            if existing and existing.fingerprint == payload["fingerprint"]:
                stats["unchanged"] += 1
                continue
            stats["updated" if existing else "new"] += 1
            if not options["dry_run"]:
                PlaceFeatureDocument.objects.update_or_create(
                    place=place,
                    defaults={
                        **payload, "embedding": [], "embedding_dimensions": 0,
                        "embedding_provider": "", "embedding_model": "",
                        "embedding_strategy": "", "embedding_source_hash": "", "indexed_at": None,
                    },
                )
        report = {
            **sample_distribution(rows), "documents": stats,
            "place_ids": [row["place_id"] for row in rows],
        }
        json_path = Path(options["json"]).resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        csv_path = Path(options["csv"]).resolve()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=(
                "place_id", "name", "region", "category", "address", "features", "cluster",
            ))
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "place_id": row["place_id"], "name": row["name"], "region": row["region"],
                    "category": row["category"], "address": row["address"],
                    "features": "|".join(row["features"]),
                    "cluster": row["selection_stratum"]["cluster"],
                })
        output = {**report, "place_ids": f"{len(rows)} ids"}
        self.stdout.write(json.dumps(output, ensure_ascii=False, indent=2))
