import csv
import json
import math
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.models import Place, PlaceFeatureDocument
from recommendations.services.place_feature_document import embedding_source_hash, feature_document_payload
from recommendations.services.semantic_sampling import (
    eligible_feature_rows,
    sample_distribution,
    stratified_feature_sample,
)


class Command(BaseCommand):
    help = "Design a stratified 10k semantic sample without creating documents or embeddings."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10000)
        parser.add_argument("--json", default="tmp/semantic_10k_dryrun.json")
        parser.add_argument("--csv", default="tmp/semantic_10k_dryrun.csv")

    def handle(self, *args, **options):
        limit = max(1, min(int(options["limit"]), 10000))
        rows = stratified_feature_sample(limit=limit, hard_limit=10000)
        places = Place.objects.in_bulk(row["place_id"] for row in rows)
        existing = {
            row.place_id: row
            for row in PlaceFeatureDocument.objects.filter(place_id__in=places).select_related("place").only(
                "place_id", "fingerprint", "embedding_source_hash", "embedding_dimensions",
                "embedding_model", "embedding_strategy", "place__name", "place__category",
                "place__address", "features",
            )
        }
        statuses = Counter()
        estimated_characters = 0
        for row in rows:
            place = places.get(row["place_id"])
            if not place:
                statuses["skipped"] += 1
                continue
            payload = feature_document_payload(place, row["features"])
            estimated_characters += len(payload["document"])
            document = existing.get(place.id)
            if not document:
                statuses["new"] += 1
            elif document.fingerprint != payload["fingerprint"]:
                statuses["updated"] += 1
            elif (
                document.embedding_dimensions == 512
                and document.embedding_model == "text-embedding-3-small"
                and document.embedding_strategy == "contextual"
                and document.embedding_source_hash == embedding_source_hash(document, strategy="contextual")
            ):
                statuses["already_embedded"] += 1
            else:
                statuses["existing_pending"] += 1
        pending = statuses["new"] + statuses["updated"] + statuses["existing_pending"]
        # Grounded in the completed 1k run: 35,100 tokens / 1,000 selected,
        # 14,731.29 ms embedding and 3,728.21 ms storage for 914 pending.
        tokens_per_document = 35.1
        embedding_ms_per_document = 14731.29 / 914
        storage_ms_per_document = 3728.21 / 914
        estimated_tokens = round(pending * tokens_per_document)
        distribution = sample_distribution(rows)
        eligible_places = eligible_feature_rows().values("place_id").distinct().count()
        minimum_cell = max(10, round(limit * 0.01))
        sparse_categories = {
            name: count for name, count in distribution["categories"].items() if count < minimum_cell
        }
        sparse_clusters = {
            name: count for name, count in distribution["selection_clusters"].items() if count < minimum_cell
        }
        report = {
            **distribution,
            "requested": limit,
            "eligible_active_feature_places": eligible_places,
            "selected_share_of_eligible": round(len(rows) / eligible_places, 4) if eligible_places else 0.0,
            "undersupplied_cells": {
                "threshold": minimum_cell,
                "categories": sparse_categories,
                "feature_clusters": sparse_clusters,
                "reason": "active-positive eligible supply below the one-percent planning floor",
            },
            "document_status": dict(statuses),
            "pending_embeddings": pending,
            "estimated_input_tokens": estimated_tokens,
            "estimated_openai_cost_usd": round(estimated_tokens * 0.02 / 1_000_000, 8),
            "estimated_api_calls_at_batch_100": math.ceil(pending / 100) if pending else 0,
            "estimated_embedding_seconds": round(pending * embedding_ms_per_document / 1000, 2),
            "estimated_storage_seconds": round(pending * storage_ms_per_document / 1000, 2),
            "estimated_raw_vector_bytes_float32": pending * 512 * 4,
            "hnsw_index_size": "NOT_MEASURED",
            "assumptions": {
                "tokens_per_selected_document": tokens_per_document,
                "price_usd_per_million_input_tokens": 0.02,
                "source_benchmark": "tmp/semantic_embedding_1000.json",
            },
        }
        json_path = Path(options["json"]).resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        csv_path = Path(options["csv"]).resolve()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=(
                "place_id", "name", "region", "category", "features", "cluster",
            ))
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "place_id": row["place_id"], "name": row["name"], "region": row["region"],
                    "category": row["category"], "features": "|".join(row["features"]),
                    "cluster": row["selection_stratum"]["cluster"],
                })
        self.stdout.write(json.dumps({**report, "tags": f"{len(report['tags'])} tags"}, ensure_ascii=False, indent=2))
