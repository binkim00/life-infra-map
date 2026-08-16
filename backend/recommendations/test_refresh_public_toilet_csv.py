import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase

from recommendations.management.commands.refresh_public_toilet_csv import refresh_toilets
from recommendations.models import Place


class RefreshPublicToiletCsvTests(TestCase):
    def test_refreshes_matching_identity_and_keeps_unmatched_without_creating_place(self):
        place = Place.objects.create(
            name="이전 이름", category="toilet", address="서울 종로구 이전로 1",
            lat=37.5, lng=127.0, source="public_toilet_standard", external_id="toilet_M1",
            raw={"legacy": True},
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "toilet.csv"
            fields = ["관리번호", "화장실명", "소재지도로명주소", "데이터기준일자", "데이터갱신시점", "기저귀교환대유무"]
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"관리번호": "M1", "화장실명": "새 이름", "소재지도로명주소": "서울특별시 종로구 새로 1", "데이터기준일자": "2025-01-01", "데이터갱신시점": "2026-05-01 10:00:00", "기저귀교환대유무": "Y"})
                writer.writerow({"관리번호": "M2", "화장실명": "좌표 없는 신규", "소재지도로명주소": "서울특별시 종로구 새로 2"})
            report = refresh_toilets(path)
        place.refresh_from_db()
        self.assertEqual(place.name, "새 이름")
        self.assertEqual(str(place.source_updated_at), "2026-05-01")
        self.assertEqual(place.raw["기저귀교환대유무"], "Y")
        self.assertEqual(report["stats"]["matched"], 1)
        self.assertEqual(report["stats"]["unmatched"], 1)
        self.assertEqual(Place.objects.count(), 1)
