import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.models import PlaceTagEvidence


class Command(BaseCommand):
    help = "Export grounded AI extractions for fast human review without filling answers."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=30)
        parser.add_argument("--output", default="tmp/ai_evidence_validation_30.csv")

    def handle(self, *args, **options):
        rows = PlaceTagEvidence.objects.filter(
            context__extraction__method="ai",
        ).select_related("place", "tag").order_by("-created_at")[:max(1, options["limit"])]
        output = Path(options["output"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        fields = (
            "place_id", "place_name", "address", "category", "evidence_title",
            "evidence_snippet", "source_url", "tag", "polarity", "evidence_span",
            "confidence", "identity_confidence", "published_at", "tag_correct",
            "span_correct", "polarity_correct", "review_notes",
        )
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for evidence in rows:
                context = evidence.context or {}
                extraction = context.get("extraction") or {}
                identity = context.get("identity") or {}
                writer.writerow({
                    "place_id": evidence.place_id,
                    "place_name": evidence.place.name,
                    "address": evidence.place.address,
                    "category": evidence.place.category,
                    "evidence_title": context.get("source_title") or "",
                    "evidence_snippet": evidence.evidence,
                    "source_url": evidence.source_reference,
                    "tag": evidence.tag.name,
                    "polarity": evidence.polarity,
                    "evidence_span": extraction.get("evidence_span") or evidence.evidence,
                    "confidence": evidence.confidence,
                    "identity_confidence": identity.get("score") or "",
                    "published_at": evidence.observed_at.isoformat() if evidence.observed_at else "",
                    "tag_correct": "",
                    "span_correct": "",
                    "polarity_correct": "",
                    "review_notes": "",
                })
        self.stdout.write("AI evidence validation rows={} output={}".format(len(rows), output))
