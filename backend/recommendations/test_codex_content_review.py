import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from recommendations.models import EvidenceReview, Place, PlaceTagEvidence, Tag
from recommendations.management.commands.prepare_codex_content_review import source_excerpt
from recommendations.services.automatic_content_review import auto_review_content
from recommendations.services.codex_content_review import assess_codex_verdict
from recommendations.services.tag_evidence_aggregation import active_evidence


class CodexContentReviewTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="테스트커피 서면점", category="cafe", address="부산 중앙대로 100",
            source="test", lat=35.1, lng=129.1,
        )
        self.tag = Tag.objects.create(name="콘센트있음")
        self.span = "부산 중앙대로 100 테스트커피 서면점에는 좌석마다 콘센트가 있어서 편리했습니다."
        self.row = PlaceTagEvidence.objects.create(
            place=self.place, tag=self.tag, source="web_search",
            source_reference="https://example.com/place", polarity="positive",
            evidence=self.span, context={"source_title": "테스트커피 서면점 후기"},
        )
        self.review = EvidenceReview.objects.create(
            evidence=self.row, status="pending",
            history=[{"mode": "automatic_content", "reason": "requires_human_context_review"}],
        )
        self.seed = {
            "id": self.row.id, "place_id": self.place.id, "tag": self.tag.name,
            "polarity": "positive", "source_url": self.row.source_reference,
            "quote_hash": hashlib.sha256(self.span.encode()).hexdigest(),
            "updated_at": self.row.updated_at.isoformat(),
        }
        self.result = {
            "id": self.row.id, "quote_hash": self.seed["quote_hash"],
            "decision": "approve", "source_url": self.row.source_reference,
            "source_span": self.span, "reason": "direct source claim",
        }
        self.page = {"ok": True, "text": "테스트커피 서면점 후기 " + self.span}

    @patch("recommendations.services.codex_content_review.fetch_public_page")
    def test_rechecks_source_identity_address_and_pinned_quote(self, fetch):
        fetch.return_value = self.page
        self.assertEqual(assess_codex_verdict(self.row, self.review, self.seed, self.result), "approve")
        fetch.return_value = {"ok": True, "text": "테스트커피 서면점 후기 " + self.span.replace("100", "999")}
        self.assertEqual(assess_codex_verdict(self.row, self.review, self.seed, self.result), "source_span_not_found")
        fetch.return_value = {"ok": True, "text": self.span.replace("중앙대로 100", "다른 주소")}
        self.assertEqual(assess_codex_verdict(self.row, self.review, self.seed, self.result), "source_span_not_found")
        fetch.return_value = self.page
        changed = {**self.seed, "quote_hash": "0" * 64}
        self.assertEqual(assess_codex_verdict(self.row, self.review, changed, self.result), "input_or_source_drift")
        no_address_span = self.span.replace("부산 중앙대로 100 ", "")
        fetch.return_value = {"ok": True, "text": no_address_span}
        no_address_result = {**self.result, "source_span": no_address_span}
        self.assertEqual(assess_codex_verdict(self.row, self.review, self.seed, no_address_result), "address_not_verified")
        self.review.history = [{"mode": "manual"}]
        self.assertEqual(assess_codex_verdict(self.row, self.review, self.seed, self.result), "not_automatic_pending")

    @patch("recommendations.management.commands.prepare_codex_content_review.fetch_public_page")
    def test_prepare_exports_only_automatic_pending_and_source_excerpt(self, fetch):
        fetch.return_value = self.page
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "queue.json"
            call_command("prepare_codex_content_review", output=str(output), limit=10, live_page_excerpts=True)
            exported = json.loads(output.read_text(encoding="utf-8"))["items"]
            self.assertEqual([item["id"] for item in exported], [self.row.id])
            self.assertEqual(exported[0]["quote_hash"], self.seed["quote_hash"])
            self.assertIn(self.span, exported[0]["source_excerpt"])

    def test_excerpt_skips_distant_place_name_to_save_model_tokens(self):
        distant = "테스트커피 서면점 " + ("다른 글 내용 " * 100) + self.span.replace("테스트커피 서면점", "다른 카페")
        self.assertEqual(source_excerpt(distant, self.span.replace("테스트커피 서면점", "다른 카페"), self.place.name), "")

    @patch("recommendations.services.codex_content_review.fetch_public_page")
    def test_cafe_study_claim_does_not_prove_laptop_work(self, fetch):
        self.row.tag = Tag.objects.create(name="노트북작업")
        self.row.evidence = "부산 중앙대로 100 테스트커피 서면점은 카공족도 환영해 공부하기 좋은 카페입니다."
        self.row.save()
        self.seed.update({
            "tag": "노트북작업",
            "quote_hash": hashlib.sha256(self.row.evidence.encode()).hexdigest(),
            "updated_at": self.row.updated_at.isoformat(),
        })
        self.result.update({
            "quote_hash": self.seed["quote_hash"],
            "source_span": self.row.evidence,
        })
        fetch.return_value = {"ok": True, "text": self.row.evidence}
        self.assertEqual(
            assess_codex_verdict(self.row, self.review, self.seed, self.result),
            "laptop_not_explicit",
        )

    def test_prepare_skips_recent_attempt_and_advances_queue(self):
        next_row = PlaceTagEvidence.objects.create(
            place=self.place, tag=self.tag, source="web_search",
            source_reference="https://example.com/next", polarity="positive",
            evidence=self.span,
        )
        EvidenceReview.objects.create(
            evidence=next_row, status="pending",
            history=[{"mode": "automatic_content", "reason": "requires_human_context_review"}],
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "queue.json"
            call_command(
                "prepare_codex_content_review", output=str(output), limit=1,
                exclude_ids=str(self.row.id),
            )
            exported = json.loads(output.read_text(encoding="utf-8"))["items"]
            self.assertEqual([item["id"] for item in exported], [next_row.id])

    @patch("recommendations.services.codex_content_review.fetch_public_page")
    def test_preview_is_read_only_and_apply_backs_up_then_approves(self, fetch):
        fetch.return_value = self.page
        with tempfile.TemporaryDirectory() as directory:
            seed = Path(directory) / "seed.json"
            result = Path(directory) / "result.json"
            backup = Path(directory) / "backup.json"
            seed.write_text(json.dumps({"schema_version": 1, "items": [self.seed]}), encoding="utf-8")
            result.write_text(json.dumps({"results": [self.result]}), encoding="utf-8")
            call_command("apply_codex_content_review", str(seed), str(result))
            self.review.refresh_from_db()
            self.assertEqual(self.review.status, "pending")
            call_command("apply_codex_content_review", str(seed), str(result), apply=True, backup=str(backup))
            self.review.refresh_from_db()
            self.assertEqual(self.review.status, "approved")
            self.assertEqual(self.review.history[-1]["mode"], "automatic_codex")
            self.assertTrue(active_evidence(self.place, self.tag).exists())
            self.assertEqual(auto_review_content(self.row), "preserved_manual")
            self.review.refresh_from_db()
            self.assertEqual(self.review.status, "approved")
            self.assertTrue(backup.exists())
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8"))["entries"][0]["review"]["status"], "pending")
            call_command("rollback_codex_content_review", str(backup))
            self.review.refresh_from_db()
            self.assertEqual(self.review.status, "approved")
            call_command("rollback_codex_content_review", str(backup), apply=True)
            self.review.refresh_from_db()
            self.assertEqual(self.review.status, "pending")
            self.assertEqual(self.review.history[-1]["mode"], "automatic_content")
