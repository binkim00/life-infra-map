from django.test import TestCase

from recommendations.models import Place, PlaceTagEvidence, Tag
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

    def test_rejects_polarity_not_supported_by_rule(self):
        row = self.row()
        row["evidence_span"] = "좌석이 넓다"
        self.assertEqual(validate_candidate(row)["reason"], "POLARITY_OR_RULE_MISMATCH")

    def test_detects_duplicate_url_tag_and_polarity(self):
        tag = Tag.objects.create(name="콘센트있음", tag_type="recommendation")
        PlaceTagEvidence.objects.create(
            place=self.place, tag=tag, source="web_search", source_reference="https://example.com/cafe",
            polarity="positive", evidence="자리마다 콘센트가 있다",
        )
        self.assertEqual(validate_candidate(self.row())["status"], "duplicate")
