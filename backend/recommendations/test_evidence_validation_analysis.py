import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import SimpleTestCase

from recommendations.management.commands.analyze_evidence_validation import analyze_rows


class EvidenceValidationAnalysisTests(SimpleTestCase):
    def test_excludes_blank_and_ambiguous_labels_from_precision(self):
        report = analyze_rows([
            {
                "sample_type": "accepted_evidence", "category": "cafe",
                "evidence_source": "naver_blog_search", "evidence_confidence": "72",
                "identity_correct": "O", "evidence_about_place": "x",
                "tag_supported": "", "polarity_correct": "애매",
            },
            {
                "sample_type": "accepted_evidence", "category": "cafe",
                "evidence_source": "naver_blog_search", "evidence_confidence": "60",
                "identity_correct": "", "evidence_about_place": "",
                "tag_supported": "", "polarity_correct": "",
            },
        ])
        self.assertEqual(report["reviewed_rows"], 1)
        self.assertEqual(report["metrics"]["identity_precision"]["rate"], 1.0)
        self.assertEqual(report["metrics"]["evidence_relevance_precision"]["rate"], 0.0)
        self.assertIsNone(report["metrics"]["tag_precision"]["rate"])
        self.assertEqual(report["ambiguous_label_cells"], 1)

    def test_command_does_not_modify_validation_csv(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "validation.csv"
            fields = [
                "sample_type", "category", "evidence_source", "evidence_confidence",
                "identity_correct", "evidence_about_place", "tag_supported", "polarity_correct",
            ]
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"sample_type": "rejected_identity", "identity_correct": "O"})
            before = path.read_bytes()
            call_command("analyze_evidence_validation", str(path))
            self.assertEqual(path.read_bytes(), before)
