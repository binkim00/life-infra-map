import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from recommendations.models import PlaceFeatureDocument
from recommendations.services.place_feature_document import (
    DOCUMENT_STRATEGIES,
    embedding_document,
    embedding_source_hash,
)
from recommendations.services.semantic_embeddings import EmbeddingProviderError, embed_openai_texts


class Command(BaseCommand):
    help = "Embed fact-only feature documents for semantic retrieval up to the pilot cap."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--strategy", choices=sorted(DOCUMENT_STRATEGIES), default="contextual")
        parser.add_argument("--max-documents", type=int, default=None, help="Override SEMANTIC_PILOT_MAX_DOCUMENTS for this run.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--report", default="")
        parser.add_argument("--sample", default="", help="JSON report containing an ordered place_ids list.")
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        effective_max = int(
            options.get("max_documents")
            if options.get("max_documents") not in (None, 0, "")
            else getattr(settings, "SEMANTIC_PILOT_MAX_DOCUMENTS", 10000)
        )
        limit = min(max(1, options["limit"]), effective_max)
        strategy = options["strategy"]
        model = getattr(settings, "SEMANTIC_EMBEDDING_MODEL", "text-embedding-3-small")
        dimensions = int(getattr(settings, "SEMANTIC_EMBEDDING_DIMENSIONS", 512))
        queryset = PlaceFeatureDocument.objects.exclude(features=[]).select_related("place")
        if options["sample"]:
            sample = json.loads(Path(options["sample"]).resolve().read_text(encoding="utf-8"))
            place_ids = [int(value) for value in (sample.get("place_ids") or [])[:limit]]
            by_place = {row.place_id: row for row in queryset.filter(place_id__in=place_ids)}
            selected = [by_place[place_id] for place_id in place_ids if place_id in by_place]
        else:
            selected = list(queryset.order_by("id")[:limit])
        pending = []
        skipped = 0
        for document in selected:
            source_hash = embedding_source_hash(document, strategy=strategy)
            if (
                document.embedding
                and document.embedding_provider == "openai"
                and document.embedding_model == model
                and document.embedding_dimensions == dimensions
                and document.embedding_strategy == strategy
                and document.embedding_source_hash == source_hash
            ):
                skipped += 1
                continue
            pending.append((document, source_hash, embedding_document(document, strategy=strategy)))
        report = {
            "selected": len(selected), "pending": len(pending), "unchanged": skipped,
            "success": 0, "failed": 0, "provider": "openai", "model": model,
            "dimensions": dimensions, "strategy": strategy, "input_tokens": 0,
            "estimated_cost_usd": 0.0, "embedding_latency_ms": 0.0,
            "storage_latency_ms": 0.0, "api_calls": 0,
        }
        if options["dry_run"] or not pending:
            self._finish(report, options["report"])
            return
        batch_size = max(1, min(int(options["batch_size"]), 100))
        vectors = []
        aggregate = {"input_tokens": 0, "estimated_cost_usd": 0.0, "latency_ms": 0.0}
        try:
            for offset in range(0, len(pending), batch_size):
                batch = pending[offset:offset + batch_size]
                result = embed_openai_texts(
                    [text for _, _, text in batch], model=model, dimensions=dimensions,
                )
                vectors.extend(result["vectors"])
                report["api_calls"] += 1
                for key in aggregate:
                    aggregate[key] += result[key]
        except EmbeddingProviderError as exc:
            raise CommandError(str(exc)) from exc
        storage_started = time.perf_counter()
        now = timezone.now()
        for (document, source_hash, _), vector in zip(pending, vectors):
            document.embedding = vector
            document.embedding_provider = "openai"
            document.embedding_model = model
            document.embedding_dimensions = dimensions
            document.embedding_strategy = strategy
            document.embedding_source_hash = source_hash
            document.indexed_at = now
        PlaceFeatureDocument.objects.bulk_update(
            [item[0] for item in pending],
            ["embedding", "embedding_provider", "embedding_model", "embedding_dimensions",
             "embedding_strategy", "embedding_source_hash", "indexed_at"],
            batch_size=100,
        )
        report.update({
            "success": len(pending),
            "input_tokens": aggregate["input_tokens"],
            "estimated_cost_usd": aggregate["estimated_cost_usd"],
            "embedding_latency_ms": round(aggregate["latency_ms"], 2),
            "storage_latency_ms": round((time.perf_counter() - storage_started) * 1000, 2),
        })
        self._finish(report, options["report"])

    def _finish(self, report, report_path):
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(rendered)
        if report_path:
            path = Path(report_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
