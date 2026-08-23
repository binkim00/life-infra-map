import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from recommendations.management.commands.report_place_inventory import build_inventory_report
from recommendations.models import KakaoPlaceMatch, Place, SourcePlaceRecord


class PlaceInventoryReportTests(TestCase):
    def setUp(self):
        self.kakao = Place.objects.create(
            name="서울 카페",
            category="cafe",
            address="서울특별시 중구 테스트로 1",
            lat=37.56,
            lng=126.97,
            source="kakao_local",
            external_id="kakao-1",
        )
        Place.objects.create(
            name="부산 공원",
            category="city_park",
            address="부산광역시 해운대구 테스트로 2",
            lat=35.16,
            lng=129.16,
            source="data_go_kr",
            external_id="park-1",
        )
        record = SourcePlaceRecord.objects.create(
            source="localdata",
            dataset="rest_restaurant",
            source_record_id="source-1",
            name=self.kakao.name,
            category="cafe",
            sido_name="서울특별시",
            normalized_place=self.kakao,
        )
        KakaoPlaceMatch.objects.create(
            source_record=record,
            status="confirmed",
            canonical_place=self.kakao,
            kakao_place_id=self.kakao.external_id,
            score=95,
        )

    def test_reports_place_source_region_and_match_inventory(self):
        report = build_inventory_report()

        self.assertEqual(report["database_vendor"], connection.vendor)
        self.assertEqual(report["places"]["total"], 2)
        self.assertEqual(report["places"]["kakao_canonical"], 1)
        self.assertIn({"sido": "서울특별시", "count": 1}, report["places"]["regions"])
        self.assertEqual(report["source_records"]["normalized"], 1)
        self.assertEqual(report["kakao_matches"]["statuses"], [{"status": "confirmed", "count": 1}])
        self.assertEqual(report["kakao_matches"]["integrity"]["confirmed_non_kakao_canonical"], 0)

    def test_command_writes_json_file(self):
        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "inventory.json"
            stdout = StringIO()
            call_command("report_place_inventory", output=output_path, stdout=stdout)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["places"]["total"], 2)
            self.assertIn("Inventory written", stdout.getvalue())
