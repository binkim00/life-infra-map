import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from recommendations.management.commands.validate_codex_web_evidence import (
    close_research_requests,
    preserve_unavailable_candidate,
    related_rule_evidences,
)
from recommendations.models import Place, PlaceTagEvidence, Tag, TagEnrichmentRequest
from recommendations.services.codex_web_evidence_validator import validate_candidate


class CodexWebEvidenceValidatorTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="서면 테스트카페", category="cafe", address="부산광역시 부산진구 부전동 1",
            lat=35.1, lng=129.0, source="semas", external_id="codex-validator-cafe",
        )

    def row(self):
        return {
            "place_id": self.place.id, "place_name": self.place.name, "category": "cafe",
            "target_tag": "콘센트있음", "extracted_tag": "콘센트있음", "polarity": "positive",
            "source_url": "https://example.com/cafe", "source_title": "서면 테스트카페",
            "source_type": "blog", "evidence_span": "자리마다 콘센트가 있다",
            "published_at": "2026-08-01", "identity_status": "verified", "identity_confidence": 90,
            "page_verified": True, "source_candidate_only": False, "research_status": "FOUND",
        }

    def test_valid_web_candidate_requires_verification_but_passes_validator(self):
        result = validate_candidate(self.row())
        self.assertEqual(result["status"], "needs_verification")

    def test_rejects_unverified_page(self):
        row = self.row()
        row["page_verified"] = False
        self.assertEqual(validate_candidate(row)["reason"], "PAGE_NOT_VERIFIED")

    def test_page_unavailable_is_preserved_as_retry_candidate(self):
        row = self.row()
        row.update({
            "research_status": "PAGE_UNAVAILABLE",
            "page_verified": False,
            "source_candidate_only": True,
            "candidate_sources": [{
                "url": "https://example.com/review?utm_source=search",
                "title": "서면 테스트카페 후기",
                "snippet": "콘센트가 있다는 검색 결과 문구",
                "source_type": "blog",
                "access_error": "PAGE_BLOCKED",
            }],
            "failure_detail": "본문을 다시 열 수 없음",
        })

        result = validate_candidate(row, live_verify=True)

        self.assertEqual(result["status"], "candidate_pending")
        self.assertEqual(result["candidate_sources"][0]["url"], "https://example.com/review")

    def test_preserved_retry_candidate_is_queued_without_creating_evidence(self):
        row = self.row()
        row.update({
            "research_status": "PAGE_UNAVAILABLE",
            "failure_detail": "본문을 다시 열 수 없음",
            "candidate_sources": [{
                "url": "https://example.com/review",
                "title": "서면 테스트카페 후기",
                "snippet": "콘센트가 있다는 검색 결과 문구",
                "source_type": "blog",
                "access_error": "PAGE_BLOCKED",
            }],
        })
        result = validate_candidate(row)

        saved = preserve_unavailable_candidate(row, result)

        request = TagEnrichmentRequest.objects.get(place=self.place, tag_name="콘센트있음")
        self.assertEqual(saved, 1)
        self.assertEqual(request.status, "queued")
        self.assertEqual(
            request.context["codex_candidate_research"]["sources"][0]["url"],
            "https://example.com/review",
        )
        self.assertFalse(PlaceTagEvidence.objects.exists())

    def test_rejects_polarity_not_supported_by_rule(self):
        row = self.row()
        row["evidence_span"] = "좌석이 넓다"
        self.assertEqual(validate_candidate(row)["reason"], "POLARITY_OR_RULE_MISMATCH")

    @patch("recommendations.services.codex_web_evidence_validator.fetch_public_page")
    def test_live_verified_unknown_phrase_is_kept_as_low_confidence_evidence(self, fetch):
        row = self.row()
        row["evidence_span"] = "노트북을 펴 두고 오래 머물기 편한 곳이었다"
        fetch.return_value = {
            "ok": True,
            "url": row["source_url"],
            "title": self.place.name,
            "text": "{} {}".format(self.place.name, row["evidence_span"]),
            "published_at": "2026-08-01",
        }

        result = validate_candidate(row, live_verify=True)

        self.assertEqual(result["status"], "needs_verification")
        self.assertEqual(result["normalized"]["extraction"]["method"], "semantic_quote_fallback")
        self.assertLessEqual(result["normalized"]["confidence"], 55)

    @patch("recommendations.services.codex_web_evidence_validator.fetch_public_page")
    def test_live_verified_opposite_rule_polarity_is_still_rejected(self, fetch):
        row = self.row()
        row["evidence_span"] = "콘센트 없음"
        fetch.return_value = {
            "ok": True,
            "url": row["source_url"],
            "title": self.place.name,
            "text": "{} {}".format(self.place.name, row["evidence_span"]),
            "published_at": "2026-08-01",
        }

        result = validate_candidate(row, live_verify=True)

        self.assertEqual(result["reason"], "POLARITY_OR_RULE_MISMATCH")

    def test_rejects_mismatched_target_and_extracted_tags(self):
        row = self.row()
        row["target_tag"] = "조용함"

        self.assertEqual(
            validate_candidate(row)["reason"],
            "TARGET_EXTRACTED_TAG_MISMATCH",
        )

    def test_rejects_known_server_unreadable_aggregator(self):
        row = self.row()
        row["source_url"] = "https://www.tabling.co.kr/restaurant/15085"

        self.assertEqual(validate_candidate(row)["reason"], "SOURCE_POLICY_REJECTED")

    def test_detects_duplicate_url_tag_and_polarity(self):
        tag = Tag.objects.create(name="콘센트있음", tag_type="recommendation")
        PlaceTagEvidence.objects.create(
            place=self.place, tag=tag, source="web_search", source_reference="https://example.com/cafe",
            polarity="positive", evidence="자리마다 콘센트가 있다",
        )
        self.assertEqual(validate_candidate(self.row())["status"], "duplicate")

    @patch("recommendations.services.codex_web_evidence_validator.fetch_public_page")
    def test_live_verification_rejects_a_quote_missing_from_page(self, fetch):
        fetch.return_value = {
            "ok": True, "url": "https://example.com/cafe", "title": self.place.name,
            "text": "이 카페에는 넓은 좌석이 있다", "published_at": "2026-08-01",
        }
        result = validate_candidate(self.row(), live_verify=True)
        self.assertEqual(result["reason"], "LIVE_EVIDENCE_SPAN_MISMATCH")

    @patch("recommendations.services.codex_web_evidence_validator.fetch_public_page")
    def test_live_verification_uses_fetched_page_not_model_claim(self, fetch):
        row = self.row()
        row["page_verified"] = False
        row["identity_confidence"] = 0
        fetch.return_value = {
            "ok": True, "url": "https://example.com/cafe", "title": self.place.name,
            "text": "자리마다 콘센트가 있다", "published_at": "2026-08-01",
        }
        result = validate_candidate(row, live_verify=True)
        self.assertEqual(result["status"], "needs_verification")
        self.assertEqual(result["normalized"]["identity"]["score"], 90)

    @patch("recommendations.services.codex_web_evidence_validator.fetch_public_page")
    def test_apply_completes_matching_launch_enrichment_request(self, fetch):
        fetch.return_value = {
            "ok": True, "url": "https://example.com/cafe", "title": self.place.name,
            "text": "자리마다 콘센트가 있다", "published_at": "2026-08-01",
        }
        request = TagEnrichmentRequest.objects.create(
            place=self.place,
            tag_name="콘센트있음",
            status="queued",
            context={"launch_quality": {"source": "busan_launch_quality"}},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(json.dumps({"results": [self.row()]}, ensure_ascii=False), encoding="utf-8")

            call_command("validate_codex_web_evidence", str(path), live_verify=True, apply=True)

        request.refresh_from_db()
        self.assertEqual(request.status, "completed")

    def test_identity_mismatch_closes_all_launch_requests_for_place(self):
        first = TagEnrichmentRequest.objects.create(
            place=self.place, tag_name="조용함", status="queued",
            context={"launch_quality": {"source": "busan_launch_quality"}},
        )
        second = TagEnrichmentRequest.objects.create(
            place=self.place, tag_name="콘센트있음", status="queued",
            context={"launch_quality": {"source": "busan_launch_quality"}},
        )

        closed = close_research_requests({
            "place_id": self.place.id,
            "target_tag": "조용함",
            "research_status": "IDENTITY_MISMATCH",
        }, "IDENTITY_MISMATCH")

        self.assertEqual(closed, 2)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual({first.status, second.status}, {"failed"})

    def test_no_result_closes_only_the_attempted_launch_tag(self):
        first = TagEnrichmentRequest.objects.create(
            place=self.place, tag_name="조용함", status="queued",
            context={"launch_quality": {"source": "busan_launch_quality"}},
        )
        second = TagEnrichmentRequest.objects.create(
            place=self.place, tag_name="콘센트있음", status="queued",
            context={"launch_quality": {"source": "busan_launch_quality"}},
        )

        closed = close_research_requests({
            "place_id": self.place.id,
            "target_tag": "조용함",
            "research_status": "NO_RESULT",
        }, "NO_RESULT")

        self.assertEqual(closed, 1)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "queued")

    @patch(
        "recommendations.management.commands.validate_codex_web_evidence.requested_tags_for_category",
        return_value=["primary", "related", "unknown"],
    )
    @patch("recommendations.management.commands.validate_codex_web_evidence.polarity_assessment")
    def test_verified_quote_mines_additional_rule_supported_tags(self, assess, _requested):
        assess.side_effect = [
            {"polarity": "positive", "clarity_score": 82, "strength": "DIRECT"},
            {"polarity": "unknown", "clarity_score": 0, "strength": "UNKNOWN"},
        ]
        normalized = {
            "place": self.place,
            "tag_name": "primary",
        }
        evidence = {
            "evidence_summary": "one verified quote",
            "polarity": "positive",
            "confidence": 70,
            "extraction": {},
            "raw": {"channel": "codex_cli_web_search"},
        }

        related = related_rule_evidences(normalized, evidence)

        self.assertEqual([tag for tag, _row in related], ["related"])
        self.assertEqual(related[0][1]["confidence"], 70)
        self.assertEqual(related[0][1]["extraction"]["method"], "related_rule")
