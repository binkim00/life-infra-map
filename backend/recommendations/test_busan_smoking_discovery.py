import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from recommendations.management.commands.discover_busan_smoking_places import CANDIDATES, FACILITY_INVENTORY
from recommendations.models import Place


class BusanSmokingDiscoveryTests(TestCase):
    def test_inventory_has_one_hundred_targets(self):
        self.assertEqual(len(FACILITY_INVENTORY), 100)

    def test_ashtray_policy_never_confirms_smoking(self):
        ashtrays = [row for row in CANDIDATES if row["facility_type"] == "ashtray_only"]
        self.assertTrue(ashtrays)
        self.assertTrue(all(row["smoking_permission"] == "unknown" for row in ashtrays))

    def test_new_candidates_without_coordinate_evidence_remain_unlocated(self):
        new_rows = [row for row in CANDIDATES if row["status"] != "EXISTING"]
        self.assertTrue(all(row["latitude"] is None and row["longitude"] is None for row in new_rows))

    def test_command_is_read_only_and_generates_review_files(self):
        before = Place.objects.count()
        with tempfile.TemporaryDirectory() as directory:
            call_command("discover_busan_smoking_places", output_dir=directory)
            self.assertEqual(Place.objects.count(), before)
            expected = {
                "busan_smoking_existing_audit.json", "busan_smoking_existing_audit.csv",
                "busan_smoking_facility_discovery.json", "busan_smoking_facility_discovery.csv",
                "busan_ashtray_candidates.csv", "busan_smoking_sources.json",
            }
            self.assertTrue(expected.issubset({path.name for path in Path(directory).iterdir()}))
            report = json.loads((Path(directory) / "busan_smoking_facility_discovery.json").read_text(encoding="utf-8"))
            self.assertTrue(report["dry_run"])
            self.assertEqual(report["database_writes"], 0)
