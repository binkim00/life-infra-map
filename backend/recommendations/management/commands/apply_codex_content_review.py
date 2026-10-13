"""Preview or apply source-verified Codex content decisions with a rollback preimage."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from recommendations.models import EvidenceReview, PlaceTag, PlaceTagEvidence
from recommendations.services.codex_content_review import assess_codex_verdict
from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence


class Command(BaseCommand):
    help = "Re-fetch Codex-cited pages, preview approvals, and optionally apply with a preimage backup."

    def add_arguments(self, parser):
        parser.add_argument("seed")
        parser.add_argument("result")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("--apply requires a new --backup path")
        seed = json.loads(Path(options["seed"]).read_text(encoding="utf-8"))
        result = json.loads(Path(options["result"]).read_text(encoding="utf-8"))
        items = seed.get("items")
        decisions = result.get("results")
        if (seed.get("schema_version") != 1 or not isinstance(items, list)
                or not isinstance(decisions, list) or len(items) != len(decisions)
                or len(items) > 25 or len({item.get("id") for item in items}) != len(items)
                or {item.get("id") for item in items} != {item.get("id") for item in decisions}):
            raise CommandError("Invalid or incomplete Codex review result")
        by_id = {decision["id"]: decision for decision in decisions}
        page_cache = {}
        outcomes = []
        eligible = []
        for item in items:
            row = PlaceTagEvidence.objects.select_related("place", "tag", "review").get(pk=item["id"])
            review = EvidenceReview.objects.filter(evidence=row).first()
            reason = assess_codex_verdict(row, review, item, by_id[row.id], page_cache=page_cache) if review else "review_missing"
            outcomes.append({"id": row.id, "outcome": reason})
            if reason == "approve":
                eligible.append((row, item, by_id[row.id]))
        if options["apply"] and eligible:
            backup = Path(options["backup"])
            backup.parent.mkdir(parents=True, exist_ok=True)
            changed = []
            with transaction.atomic():
                locked_items = []
                for row, item, decision in eligible:
                    locked = PlaceTagEvidence.objects.select_for_update().select_related("place", "tag").get(pk=row.id)
                    review = EvidenceReview.objects.select_for_update().get(evidence=locked)
                    locked_items.append((locked, review, item, decision))
                # Capture locked preimages before any write. A prior backup is never overwritten.
                with backup.open("x", encoding="utf-8") as handle:
                    json.dump({
                        "created_at": timezone.now().isoformat(),
                        "seed": options["seed"], "result": options["result"],
                        "entries": [{
                            "evidence": PlaceTagEvidence.objects.filter(pk=locked.id).values().get(),
                            "review": EvidenceReview.objects.filter(evidence=locked).values().get(),
                            "aggregate": list(PlaceTag.objects.filter(
                                place_id=locked.place_id, tag_id=locked.tag_id).values()),
                        } for locked, _, _, _ in locked_items],
                    }, handle, ensure_ascii=False, default=str)
                for locked, review, item, decision in locked_items:
                    # Content and manual decision may have changed since the live page fetch.
                    if assess_codex_verdict(locked, review, item, decision, page_cache=page_cache) != "approve":
                        continue
                    review.status = "approved"
                    review.note = "Codex 2차 내용 검토: 원문 인용·장소명·주소·저장 문장 대조 통과. 현장 확인이나 최신성 보증은 아닙니다."
                    review.history = [*review.history, {
                        "mode": "automatic_codex", "status": "approved",
                        "reason": str(decision.get("reason") or "source_verified")[:300],
                        "source_span": str(decision["source_span"])[:2000],
                        "quote_hash": item["quote_hash"], "at": timezone.now().isoformat(),
                    }]
                    review.save(update_fields=["status", "note", "history", "updated_at"])
                    aggregate_tag_evidence(locked.place, locked.tag)
                    changed.append(locked.id)
        else:
            changed = []
        self.stdout.write(json.dumps({
            "mode": "apply" if options["apply"] else "preview",
            "items": len(items), "eligible": len(eligible),
            "applied": len(changed), "applied_ids": changed, "outcomes": outcomes,
        }, ensure_ascii=False))
