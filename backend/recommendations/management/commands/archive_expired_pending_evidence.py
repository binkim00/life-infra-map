"""Move expired, automatically held web evidence out of the human queue."""

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from recommendations.models import EvidenceReview
from recommendations.services.automatic_content_review import auto_review_content
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES


class Command(BaseCommand):
    help = "Preview expired automatic holds; apply with a durable review preimage."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("--apply requires --backup")
        now = timezone.now()
        with transaction.atomic():
            reviews = list(
                EvidenceReview.objects.select_for_update()
                .select_related("evidence")
                .filter(
                    status="pending", reviewer__isnull=True,
                    evidence__source__in=WEB_EVIDENCE_SOURCES,
                    evidence__expires_at__lte=now,
                )
                .order_by("id")[:5000]
            )
            eligible = [
                review for review in reviews
                if review.history and review.history[-1].get("mode") == "automatic_content"
            ]
            if options["apply"] and eligible:
                backup = Path(options["backup"])
                backup.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation and fsync keep the preimage before the DB write.
                with backup.open("x", encoding="utf-8") as handle:
                    json.dump({
                        "created_at": now.isoformat(),
                        "reason": "expired_pending_historical",
                        "reviews": [{
                            "id": review.id,
                            "evidence_id": review.evidence_id,
                            "status": review.status,
                            "note": review.note,
                            "history": review.history,
                            "reviewer_id": review.reviewer_id,
                            "updated_at": review.updated_at.isoformat(),
                            "expires_at": review.evidence.expires_at.isoformat(),
                        } for review in eligible],
                    }, handle, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                for review in eligible:
                    auto_review_content(
                        review.evidence, decision="limited",
                        reason="expired_pending_historical",
                        run_key="expired_pending_daily",
                    )
        self.stdout.write(json.dumps({
            "mode": "apply" if options["apply"] else "preview",
            "eligible": len(eligible),
            "sample_ids": [review.evidence_id for review in eligible[:20]] if not options["apply"] else [],
        }))
