from django.test import TestCase
from django.utils import timezone

from recommendations.management.commands.generate_meaningful_place_tags import (
    generate_meaningful_tags,
    observed_at_for_place,
)
from recommendations.models import Place, PlaceTag, PlaceTagEvidence
from recommendations.services.meaningful_tag_rules import extract_meaningful_tags


class MeaningfulTagRuleTests(TestCase):
    def test_source_date_becomes_timezone_aware_evidence_observation(self):
        place = Place(source_updated_at=timezone.localdate())
        self.assertTrue(timezone.is_aware(observed_at_for_place(place, timezone.now())))

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

    def test_extracts_direct_toilet_accessibility_and_all_day_facts(self):
        matches = extract_meaningful_tags({
            "남성용-장애인용대변기수": "1",
            "여성용-장애인용대변기수": "0",
            "개방시간상세": "24시간 연중무휴",
        })
        self.assertEqual(
            {match["tag"] for match in matches},
            {"장애인시설", "24시간운영"},
        )

    def test_does_not_infer_accessibility_or_all_day_without_direct_facts(self):
        matches = extract_meaningful_tags({
            "category": "toilet",
            "남성용-장애인용대변기수": "0",
            "개방시간상세": "평일 09:00~18:00",
        })
        self.assertEqual(matches, [])

    def test_does_not_treat_year_round_operation_as_24_hours(self):
        self.assertEqual(extract_meaningful_tags({"개방시간상세": "연중무휴 09:00~18:00"}), [])

    def test_extracts_direct_diaper_table_and_card_payment(self):
        matches = extract_meaningful_tags({
            "기저귀교환대유무": "Y",
            "결제방법": "현금, 신용카드",
        })
        self.assertEqual({match["tag"] for match in matches}, {"기저귀교환대", "카드결제가능"})

    def test_extracts_all_day_parking_only_when_every_day_is_full_day(self):
        matches = extract_meaningful_tags({
            "운영요일": "평일+토요일+공휴일",
            "평일운영시작시각": "00:00", "평일운영종료시각": "23:59",
            "토요일운영시작시각": "00:00", "토요일운영종료시각": "23:59",
            "공휴일운영시작시각": "00:00", "공휴일운영종료시각": "23:59",
        })
        self.assertEqual({match["tag"] for match in matches}, {"24시간운영"})

    def test_extracts_only_direct_shelter_facilities_and_hours(self):
        matches = extract_meaningful_tags({
            "CHCK_MATTER_NIGHT_OPN_AT": "Y",
            "CHCK_MATTER_WKEND_HDAY_OPN_AT": "Y",
            "CHCK_MATTER_STAYNG_PSBL_AT": "Y",
            "COLR_HOLD_ARCNDTN": 2,
            "WKDAY_OPER_BEGIN_TIME": "0000", "WKDAY_OPER_END_TIME": "2400",
            "WKEND_HDAY_OPER_BEGIN_TIME": "0000", "WKEND_HDAY_OPER_END_TIME": "2400",
        })
        self.assertEqual({match["tag"] for match in matches}, {
            "야간운영", "주말휴일운영", "숙박가능", "냉방시설있음", "24시간운영",
        })

    def test_does_not_infer_all_day_shelter_from_night_flag_alone(self):
        matches = extract_meaningful_tags({"CHCK_MATTER_NIGHT_OPN_AT": "Y"})
        self.assertEqual({match["tag"] for match in matches}, {"야간운영"})

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
