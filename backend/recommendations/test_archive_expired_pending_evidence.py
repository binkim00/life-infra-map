import io
import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from recommendations.models import EvidenceReview, Place, PlaceTagEvidence, Tag


class ArchiveExpiredPendingEvidenceTests(TestCase):
    def setUp(self):
        place = Place.objects.create(name="테스트 카페", category="cafe", address="부산 중앙대로 1", source="test", lat=35.1, lng=129.1)
        tag = Tag.objects.create(name="콘센트있음")
        self.expired = PlaceTagEvidence.objects.create(
            place=place, tag=tag, source="web_search", source_reference="https://example.com/old",
            evidence="테스트 카페에 콘센트가 있어요.",
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.current = PlaceTagEvidence.objects.create(
            place=place, tag=tag, source="web_search", source_reference="https://example.com/new",
            evidence="테스트 카페에 콘센트가 있어요.",
            expires_at=timezone.now() + timedelta(days=1),
        )
        for row in (self.expired, self.current):
            EvidenceReview.objects.create(evidence=row, status="pending", history=[{
                "mode": "automatic_content", "reason": "different_address_needs_branch_or_move_check",
            }])

    def test_preview_then_archive_only_expired_automatic_hold(self):
        output = io.StringIO()
        call_command("archive_expired_pending_evidence", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["eligible"], 1)
        self.assertEqual(self.expired.review.status, "pending")
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "preimage.json"
            call_command("archive_expired_pending_evidence", "--apply", "--backup", str(backup), stdout=io.StringIO())
            saved = json.loads(backup.read_text(encoding="utf-8"))
            self.assertEqual(saved["reviews"][0]["evidence_id"], self.expired.id)
            self.assertEqual(saved["reviews"][0]["status"], "pending")
        self.expired.review.refresh_from_db()
        self.current.review.refresh_from_db()
        self.assertEqual(self.expired.review.status, "approved_limited")
        self.assertEqual(self.current.review.status, "pending")
        self.assertEqual(self.expired.review.history[-1]["reason"], "expired_pending_historical")

    def test_manual_hold_is_preserved(self):
        review = self.expired.review
        review.history = [{"mode": "manual"}]
        review.save(update_fields=["history"])
        output = io.StringIO()
        call_command("archive_expired_pending_evidence", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["eligible"], 0)
