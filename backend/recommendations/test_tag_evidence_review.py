import csv
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from recommendations.models import (
    Place,
    PlaceTag,
    PlaceTagEvidence,
    Tag,
    TagEnrichmentRequest,
)


class TagEvidenceReviewTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="검수 카페",
            category="cafe",
            address="서울특별시 중구 테스트로 1",
            lat=37.5,
            lng=127,
            source="kakao_local",
            external_id="review-1",
        )
        self.tag = Tag.objects.create(name="조용함")
        now = timezone.now()
        self.positive = PlaceTagEvidence.objects.create(
            place=self.place,
            tag=self.tag,
            source="ai_suggested",
            source_reference="https://blog.example/positive",
            polarity="positive",
            confidence=55,
            evidence="조용하게 머물렀다는 독립 후기",
            observed_at=now,
            expires_at=now + timedelta(days=120),
        )
        PlaceTagEvidence.objects.create(
            place=self.place,
            tag=self.tag,
            source="ai_suggested",
            source_reference="https://blog.example/negative",
            polarity="negative",
            confidence=55,
            evidence="붐비고 시끄럽다는 독립 후기",
            observed_at=now,
            expires_at=now + timedelta(days=120),
        )
        PlaceTag.objects.create(
            place=self.place,
            tag=self.tag,
            source="ai_suggested",
            status="candidate",
            confidence=50,
        )
        TagEnrichmentRequest.objects.create(
            place=self.place,
            tag_name="조용함",
            status="completed",
            error_message="insufficient_evidence",
        )

    def test_exports_review_csv_and_quality_report(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "review.csv"
            report = Path(directory) / "report.json"
            call_command(
                "export_tag_evidence_review",
                output=str(output),
                report=str(report),
            )
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            payload = json.loads(report.read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["place_name"], "검수 카페")
        self.assertEqual(payload["tags"]["조용함"]["conflict_rate"], 1.0)
        self.assertEqual(payload["tags"]["조용함"]["adoption_rate"], 1.0)
        self.assertEqual(payload["overall"]["no_evidence_rate"], 1.0)

    def test_calculates_precision_from_reviewed_csv(self):
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            labels = directory / "labels.csv"
            with labels.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["evidence_id", "manual_correct", "manual_note"])
                writer.writeheader()
                writer.writerow({
                    "evidence_id": self.positive.id,
                    "manual_correct": "맞음",
                    "manual_note": "장소 동일성 확인",
                })
            report = directory / "report.json"
            call_command(
                "export_tag_evidence_review",
                output=str(directory / "review.csv"),
                report=str(report),
                labels=str(labels),
            )
            payload = json.loads(report.read_text(encoding="utf-8"))

        self.assertEqual(payload["overall"]["manual_reviewed"], 1)
        self.assertEqual(payload["overall"]["manual_precision"], 1.0)
