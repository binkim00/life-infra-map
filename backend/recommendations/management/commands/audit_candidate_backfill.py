import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence
from recommendations.services.canonical_tag_policy import CANONICAL_TAGS


class Command(BaseCommand):
    help = "Classify existing candidate PlaceTags as evidence-backed, stale, missing, or conflict."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tmp/candidate_backfill_audit.json")

    def handle(self, *args, **options):
        now = timezone.now()
        candidates = PlaceTag.objects.filter(status="candidate")
        evidence = PlaceTagEvidence.objects.filter(place_id=OuterRef("place_id"), tag_id=OuterRef("tag_id"))
        active = evidence.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        positive = active.filter(polarity="positive")
        negative = active.filter(polarity="negative")
        rows = candidates.annotate(
            has_evidence=Exists(evidence),
            has_active=Exists(active),
            has_positive=Exists(positive),
            has_negative=Exists(negative),
        )
        report = {
            "candidate_total": candidates.count(),
            "A_active_evidence": rows.filter(has_active=True).count(),
            "B_source_mismatch": rows.filter(source="ai_suggested", has_evidence=True).count(),
            "C_expired_only": rows.filter(has_evidence=True, has_active=False).count(),
            "D_no_evidence": rows.filter(has_evidence=False).count(),
            "E_conflict": rows.filter(has_positive=True, has_negative=True).count(),
            "F_noncanonical_tag": candidates.exclude(tag__name__in=CANONICAL_TAGS).count(),
        }
        path = Path(options["output"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps(report, ensure_ascii=False))
