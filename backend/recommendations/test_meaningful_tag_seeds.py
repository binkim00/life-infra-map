from django.test import TestCase

from recommendations.management.commands.generate_meaningful_place_tags import (
    generate_meaningful_tags,
)
from recommendations.models import Place, PlaceTag, PlaceTagEvidence
from recommendations.services.meaningful_tag_rules import extract_meaningful_tags


class MeaningfulTagRuleTests(TestCase):
    def test_extracts_only_evidence_backed_non_category_attributes(self):
        matches = extract_meaningful_tags({
            "category": "카페",
            "parkingfood": "건물 뒤 5대 주차 가능",
            "kidsfacility": "없음",
            "packing": "가능",
            "reservationfood": "불가",
        })

        self.assertEqual(
            {match["tag"] for match in matches},
            {"주차가능", "포장가능"},
        )

    def test_reads_nested_public_facility_fields(self):
        matches = extract_meaningful_tags({
            "raw": {
                "요금정보": "무료",
                "공원보유시설(유희시설)": "조합놀이대",
                "공원보유시설(운동시설)": "",
            }
        })
        self.assertEqual(
            {match["tag"] for match in matches},
            {"무료이용", "놀이시설"},
        )

    def test_persists_confirmed_tag_and_stable_evidence_idempotently(self):
        place = Place.objects.create(
            name="공식 상세정보 식당",
            category="restaurant",
            address="부산광역시 중구",
            lat=35.1,
            lng=129.0,
            source="tour_api",
            external_id="tourism_39_1",
            raw={"tag_evidence_sources": {"tourapi_intro": {
                "parkingfood": "주차 가능",
                "reservationfood": "전화 예약 가능",
            }}},
        )

        first = generate_meaningful_tags(Place.objects.all())
        second = generate_meaningful_tags(Place.objects.all())

        self.assertEqual(first["matches"], 2)
        self.assertEqual(second["matches"], 2)
        self.assertEqual(PlaceTag.objects.count(), 2)
        self.assertEqual(PlaceTagEvidence.objects.count(), 2)
        self.assertTrue(all(PlaceTag.objects.values_list("is_verified", flat=True)))
        self.assertEqual(
            set(PlaceTag.objects.values_list("tag__name", flat=True)),
            {"주차가능", "예약가능"},
        )
