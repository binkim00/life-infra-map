import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from recommendations.management.commands.backfill_public_facility_raw import (
    merge_missing_official_fields,
    official_fields,
    parse_source_date,
    source_date_value,
)
from recommendations.management.commands.import_fixture_places import enrich_items_with_raw_fallback


class PublicFacilityRawBackfillTests(SimpleTestCase):
    def test_import_raw_fallback_preserves_official_fields(self):
        items = [{"source_id": "toilet_1", "name": "시설"}]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "fallback.json"
            path.write_text(json.dumps([{
                "external_id": "toilet_1",
                "source_updated_at": "2025-01-01",
                "raw": {"개방시간": "상시"},
            }], ensure_ascii=False), encoding="utf-8")
            enriched, restored = enrich_items_with_raw_fallback(items, {"raw_fallback": path})
        self.assertEqual(restored, 1)
        self.assertEqual(enriched[0]["raw"]["official_source"]["개방시간"], "상시")
        self.assertEqual(enriched[0]["source_updated_at"], "2025-01-01")

    def test_adds_only_missing_fields_under_compatible_namespace(self):
        current = {"name": "시설", "raw": {"관리기관명": "기존 기관"}}
        merged, added = merge_missing_official_fields(current, {
            "관리기관명": "새 기관",
            "데이터기준일자": "2025-01-01",
        })
        self.assertEqual(merged["raw"]["관리기관명"], "기존 기관")
        self.assertNotIn("관리기관명", added)
        self.assertEqual(merged["official_backfill"]["데이터기준일자"], "2025-01-01")

    def test_reads_nested_db_ready_official_payload(self):
        self.assertEqual(
            official_fields({"raw": {"raw": {"요금정보": "무료"}}}),
            {"요금정보": "무료"},
        )

    def test_parses_source_basis_date_without_inventing_missing_date(self):
        self.assertEqual(str(parse_source_date("2026-05-21")), "2026-05-21")
        self.assertIsNone(parse_source_date(""))
        self.assertEqual(str(parse_source_date("20250604092532")), "2025-06-04")
        self.assertEqual(
            source_date_value({"raw": {"source_updated_at": "2026-06-04"}}, {}),
            "2026-06-04",
        )
