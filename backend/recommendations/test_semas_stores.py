import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from recommendations.models import SourcePlaceRecord


class SemasStoreImportTests(TestCase):
    def test_imports_bookstore_and_cafe_with_original_store_ids(self):
        fields = [
            "상가업소번호", "상호명", "지점명", "상권업종대분류명",
            "상권업종중분류명", "상권업종소분류명", "표준산업분류명",
            "시도명", "시군구명", "행정동코드", "지번주소", "도로명주소", "경도", "위도",
        ]
        rows = [
            {
                "상가업소번호": "BOOK-1", "상호명": "전국책방", "지점명": "부산점",
                "상권업종대분류명": "소매", "상권업종중분류명": "서적 및 문구용품 소매업",
                "상권업종소분류명": "서점", "표준산업분류명": "서적 소매업",
                "시도명": "부산광역시", "시군구명": "중구", "행정동코드": "26110510",
                "지번주소": "부산 중구 중앙동 1", "도로명주소": "부산 중구 중앙대로 1",
                "경도": "129.03", "위도": "35.1",
            },
            {
                "상가업소번호": "CAFE-1", "상호명": "테스트커피", "지점명": "",
                "상권업종대분류명": "음식", "상권업종중분류명": "비알코올 음료점업",
                "상권업종소분류명": "카페", "표준산업분류명": "커피 전문점",
                "시도명": "서울특별시", "시군구명": "중구", "행정동코드": "11140550",
                "지번주소": "서울 중구 테스트동 1", "도로명주소": "서울 중구 테스트로 1",
                "경도": "127.0", "위도": "37.5",
            },
            {
                "상가업소번호": "OTHER-1", "상호명": "테스트문구", "지점명": "",
                "상권업종대분류명": "소매", "상권업종중분류명": "문구용품 소매업",
                "상권업종소분류명": "문구점", "표준산업분류명": "문구용품 소매업",
                "시도명": "서울특별시", "시군구명": "중구", "행정동코드": "11140550",
                "지번주소": "서울 중구 테스트동 2", "도로명주소": "서울 중구 테스트로 2",
                "경도": "127.0", "위도": "37.5",
            },
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "stores.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            call_command("import_semas_stores", str(path), stdout=StringIO())

        self.assertEqual(SourcePlaceRecord.objects.count(), 2)
        bookstore = SourcePlaceRecord.objects.get(source_record_id="BOOK-1")
        self.assertEqual(bookstore.name, "전국책방 부산점")
        self.assertEqual(bookstore.category, "bookstore")
        self.assertEqual(bookstore.raw["industry_minor_name"], "서점")
        self.assertEqual(
            SourcePlaceRecord.objects.get(source_record_id="CAFE-1").category,
            "cafe",
        )
        self.assertFalse(SourcePlaceRecord.objects.filter(source_record_id="OTHER-1").exists())
