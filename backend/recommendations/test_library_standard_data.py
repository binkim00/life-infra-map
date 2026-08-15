import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from recommendations.models import Place, PlaceTag, PlaceTagEvidence, SourcePlaceRecord


class LibraryStandardDataTests(TestCase):
    def write_csv(self, path):
        fields = [
            "도서관명", "시도명", "시군구명", "도서관유형", "휴관일",
            "평일운영시작시각", "평일운영종료시각", "토요일운영시작시각",
            "토요일운영종료시각", "공휴일운영시작시각", "공휴일운영종료시각",
            "열람좌석수", "소재지도로명주소", "운영기관명", "도서관전화번호",
            "홈페이지주소", "위도", "경도", "데이터기준일자",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "도서관명": "테스트중앙도서관",
                "시도명": "서울특별시",
                "시군구명": "중구",
                "도서관유형": "공공도서관",
                "휴관일": "매주 월요일",
                "평일운영시작시각": "09:00",
                "평일운영종료시각": "22:00",
                "토요일운영시작시각": "09:00",
                "토요일운영종료시각": "18:00",
                "공휴일운영시작시각": "09:00",
                "공휴일운영종료시각": "17:00",
                "열람좌석수": "120",
                "소재지도로명주소": "서울특별시 중구 테스트로 1",
                "운영기관명": "서울특별시 중구청",
                "도서관전화번호": "02-1234-5678",
                "홈페이지주소": "https://library.example",
                "위도": "37.5",
                "경도": "127.0",
                "데이터기준일자": "2026-06-01",
            })

    def test_imports_library_registry_then_generates_only_official_attributes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "libraries.csv"
            self.write_csv(path)
            call_command("import_library_standard_data", str(path), stdout=StringIO())

        record = SourcePlaceRecord.objects.get()
        self.assertEqual(record.category, "library")
        self.assertEqual(record.coordinate_reference_system, "EPSG:4326")
        self.assertEqual(record.raw["seat_count"], 120)
        place = Place.objects.create(
            name=record.name, category="library", address=record.road_address,
            lat=37.5, lng=127, source="kakao_local", external_id="library-1",
        )
        record.normalized_place = place
        record.save(update_fields=["normalized_place"])

        call_command("generate_library_meaningful_tags", stdout=StringIO())
        tags = set(PlaceTag.objects.values_list("tag__name", flat=True))
        self.assertSetEqual(tags, {"야간운영", "토요일운영", "공휴일운영", "열람좌석많음"})
        self.assertFalse(tags & {"도서관", "콘센트있음", "무료와이파이", "노트북작업"})
        self.assertEqual(PlaceTagEvidence.objects.count(), 4)
        self.assertTrue(all(PlaceTag.objects.values_list("is_verified", flat=True)))

    def test_zero_weekend_hours_do_not_infer_opening(self):
        from recommendations.management.commands.generate_library_meaningful_tags import library_attributes

        attributes = library_attributes({
            "weekday_close": "18:00",
            "saturday_open": "00:00",
            "saturday_close": "00:00",
            "holiday_open": "00:00",
            "holiday_close": "00:00",
            "seat_count": 20,
        })
        self.assertEqual(attributes, [])
