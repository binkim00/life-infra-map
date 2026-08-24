import json
from pathlib import Path

from django.test import SimpleTestCase


CASE_FILE = Path(__file__).with_name("evaluation_cases") / "busan_launch_quality_24.json"


class BusanLaunchQualityCaseContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cases = json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"]

    def test_contains_twenty_four_unique_search_queries(self):
        self.assertEqual(len(self.cases), 24)
        self.assertEqual(len({case["id"] for case in self.cases}), 24)
        self.assertEqual(len({case["query"] for case in self.cases}), 24)
        self.assertTrue(all(case["expected_action"] == "search" for case in self.cases))

    def test_balances_launch_categories_and_core_areas(self):
        cohorts = [case["cohort"] for case in self.cases]
        self.assertEqual(cohorts.count("cafe"), 12)
        self.assertEqual(cohorts.count("restaurant"), 12)
        areas = {case["area"] for case in self.cases}
        self.assertTrue({"서면", "하단", "부산대", "경성대", "해운대", "광안리"}.issubset(areas))

    def test_every_query_measures_feature_evidence(self):
        feature_terms = (
            "조용", "콘센트", "노트북", "좌석", "테이블", "오래", "전망", "사진", "자연광", "디저트",
            "반려동물", "혼자", "혼밥", "가성비", "대표메뉴", "데이트", "아이",
            "단체석", "개별룸", "유모차", "유아의자", "엘리베이터", "웨이팅", "메뉴",
        )
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(any(term in case["query"] for term in feature_terms))
