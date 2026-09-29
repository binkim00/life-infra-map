"""Export a small, pinned queue for a second Codex review of held web evidence."""

import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recommendations.models import EvidenceReview
from recommendations.services.public_page_tag_evidence import fetch_public_page
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES


class Command(BaseCommand):
    help = "Export pending automatic web-evidence holds for Codex review. Read-only."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--live-page-excerpts", action="store_true")
        parser.add_argument("--exclude-ids", default="")

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 25:
            raise CommandError("Limit must be between 1 and 25")
        raw_excluded = options["exclude_ids"]
        excluded = set()
        if raw_excluded:
            values = raw_excluded.split(",")
            if len(values) > 500 or any(
                not value.isascii() or not value.isdecimal()
                or len(value) > 19 or int(value) < 1
                for value in values
            ):
                raise CommandError("Exclude IDs must be 1 to 500 positive integers")
            excluded = {int(value) for value in values}
        output = Path(options["output"])
        if output.exists():
            raise CommandError("Output already exists")
        reviews = (
            EvidenceReview.objects.filter(
                status="pending", reviewer__isnull=True,
                evidence__source__in=WEB_EVIDENCE_SOURCES,
            )
            .exclude(evidence_id__in=excluded)
            .select_related("evidence__place", "evidence__tag")
            .order_by("updated_at", "id")
        )
        items = []
        # Skip manually held and incomplete records, while bounding DB reads.
        for review in reviews[: max(30, limit * (5 if options["live_page_excerpts"] else 30))]:
            if not review.history or review.history[-1].get("mode") != "automatic_content":
                continue
            row = review.evidence
            if not row.source_reference.startswith("https://") or not row.evidence.strip():
                continue
            page_context = {}
            if options["live_page_excerpts"]:
                page = fetch_public_page(row.source_reference)
                if not page.get("ok"):
                    continue
                page_text = " ".join(str(page.get("text") or "").split())
                excerpt = source_excerpt(page_text, row.evidence, row.place.name)
                if not excerpt:
                    continue
                page_context = {
                    "source_page_title": str(page.get("title") or "")[:200],
                    "source_excerpt": excerpt,
                    "source_identity_excerpt": page_text[
                        max(0, page_text.find(row.place.name) - 150):
                        page_text.find(row.place.name) + 450
                    ] if row.place.name in page_text else "",
                }
            items.append({
                "id": row.id,
                "place_id": row.place_id,
                "place_name": row.place.name,
                "address": row.place.address,
                "category": row.place.category,
                "tag": row.tag.name,
                "polarity": row.polarity,
                "source_url": row.source_reference,
                "source_title": (row.context or {}).get("source_title", ""),
                "stored_quote": row.evidence[:4000],
                "quote_hash": hashlib.sha256(row.evidence.encode()).hexdigest(),
                "updated_at": row.updated_at.isoformat(),
                "observed_at": row.observed_at.isoformat() if row.observed_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "hold_reason": review.history[-1].get("reason", ""),
                **page_context,
            })
            if len(items) == limit:
                break
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            json.dump({"schema_version": 1, "items": items}, handle, ensure_ascii=False)
        self.stdout.write(json.dumps({"items": len(items), "output": str(output)}))


def source_excerpt(page_text, stored_quote, place_name):
    """Spend model tokens only when the saved quote appears near this place."""
    quote = " ".join(str(stored_quote or "").split())[:4000]
    position = -1
    for length in (80, 50, 25):
        if len(quote) < length:
            continue
        for offset in range(0, len(quote) - length + 1, max(5, length // 2)):
            position = page_text.find(quote[offset:offset + length])
            if position >= 0:
                break
        if position >= 0:
            break
    if position < 0:
        return ""
    nearby = page_text[max(0, position - 350):position + 350]
    if place_name not in nearby:
        return ""
    return page_text[max(0, position - 350):position + 1000]
