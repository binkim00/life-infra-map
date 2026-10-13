"""Restore only this run's untouched automatic review decisions from its preimage."""

import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.models import EvidenceReview, PlaceTagEvidence
from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence


class Command(BaseCommand):
    help = "Preview or restore a Codex content-review backup without changing evidence dates."

    def add_arguments(self, parser):
        parser.add_argument("backup")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        backup = json.loads(Path(options["backup"]).read_text(encoding="utf-8"))
        entries = backup.get("entries")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 25:
            raise CommandError("Invalid backup entries")
        ids = [entry.get("evidence", {}).get("id") for entry in entries]
        if len(set(ids)) != len(ids) or any(not isinstance(pk, int) for pk in ids):
            raise CommandError("Invalid backup evidence IDs")
        restored = []
        with transaction.atomic():
            locked = []
            for entry in entries:
                pk = entry["evidence"]["id"]
                row = PlaceTagEvidence.objects.select_for_update().select_related("place", "tag").get(pk=pk)
                review = EvidenceReview.objects.select_for_update().get(evidence=row)
                original = entry["review"]
                current_history = review.history or []
                if (review.id != original.get("id") or original.get("evidence_id") != pk
                        or original.get("status") != "pending" or review.status != "approved"
                        or not current_history or current_history[-1].get("mode") != "automatic_codex"
                        or current_history[:-1] != original.get("history")
                        or current_history[-1].get("quote_hash") != hashlib.sha256(row.evidence.encode()).hexdigest()
                        or row.evidence != entry["evidence"].get("evidence")):
                    raise CommandError(f"Review changed after Codex approval: {pk}")
                locked.append((row, review, original))
            if options["apply"]:
                for row, review, original in locked:
                    review.status = original["status"]
                    review.note = original["note"]
                    review.history = original["history"]
                    review.reviewer_id = original["reviewer_id"]
                    review.save(update_fields=["status", "note", "history", "reviewer", "updated_at"])
                    aggregate_tag_evidence(row.place, row.tag)
                    restored.append(row.id)
            else:
                transaction.set_rollback(True)
        self.stdout.write(json.dumps({
            "mode": "apply" if options["apply"] else "preview",
            "eligible": len(entries), "restored": restored,
        }))
