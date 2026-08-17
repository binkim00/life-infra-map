from django.test import TestCase

from recommendations.management.commands.materialize_commercial_places import materialize_records
from recommendations.models import Place, SourcePlaceRecord
from recommendations.services.commercial_place_registry import is_service_category


class CommercialPlaceRegistryTests(TestCase):
    def record(self, *, source_id, name="테스트커피", category="cafe", business_type="카페", address="서울특별시 중구 테스트로 1", lng="127.0", lat="37.5"):
        return SourcePlaceRecord.objects.create(
            source="semas", dataset="commercial_store", source_record_id=source_id,
            name=name, category=category, business_type=business_type, is_active=True,
            address=address, road_address=address, sido_name="서울특별시", sigungu_name="중구",
            source_x=lng, source_y=lat, coordinate_reference_system="EPSG:4326",
        )

    def test_filters_study_cafes_and_alcohol_businesses(self):
        self.assertFalse(is_service_category(self.record(source_id="study", business_type="독서실/스터디 카페")))
        self.assertFalse(is_service_category(self.record(source_id="pub", category="restaurant", business_type="요리 주점")))
        self.assertTrue(is_service_category(self.record(
            source_id="food", name="서울식당", category="restaurant", business_type="백반/한정식"
        )))
        self.assertFalse(is_service_category(self.record(
            source_id="conflict", name="웰카페", category="restaurant", business_type="백반/한정식"
        )))

    def test_links_exact_name_nearby_without_creating_duplicate(self):
        existing = Place.objects.create(
            name="테스트 커피", category="cafe", address="서울 중구 테스트로 1",
            lat=37.50001, lng=127.00001, source="kakao_local", external_id="kakao-1",
        )
        record = self.record(source_id="cafe-1")
        stats, _ = materialize_records(SourcePlaceRecord.objects.filter(id=record.id), regions=("서울특별시",), categories=("cafe",), batch_size=10)
        record.refresh_from_db()
        self.assertEqual(record.normalized_place, existing)
        self.assertEqual(stats["existing_match"], 1)
        self.assertEqual(Place.objects.count(), 1)

    def test_keeps_similar_nearby_name_ambiguous(self):
        Place.objects.create(
            name="테스트커피 본점", category="cafe", address="서울 중구 테스트로 1",
            lat=37.5, lng=127.0, source="kakao_local", external_id="kakao-2",
        )
        record = self.record(source_id="cafe-2")
        stats, _ = materialize_records(SourcePlaceRecord.objects.filter(id=record.id), regions=("서울특별시",), categories=("cafe",), batch_size=10)
        record.refresh_from_db()
        self.assertIsNone(record.normalized_place)
        self.assertEqual(stats["ambiguous"], 1)

    def test_materializes_verified_official_row(self):
        record = self.record(source_id="cafe-3")
        stats, _ = materialize_records(SourcePlaceRecord.objects.filter(id=record.id), regions=("서울특별시",), categories=("cafe",), batch_size=10)
        record.refresh_from_db()
        self.assertEqual(stats["new_place"], 1)
        self.assertEqual(record.normalized_place.source, "semas")
        self.assertEqual(record.normalized_place.raw["source_record_id"], "cafe-3")

    def test_materializes_legacy_combined_gwangju_row_with_canonical_address(self):
        record = self.record(
            source_id="gwangju-cafe-1",
            address="전남광주통합특별시 북구 테스트로 1",
            lng="126.91",
            lat="35.17",
        )
        record.sido_name = "전남광주통합특별시"
        record.sigungu_name = "북구"
        record.save(update_fields=["sido_name", "sigungu_name"])

        stats, _ = materialize_records(
            SourcePlaceRecord.objects.filter(id=record.id),
            regions=("광주광역시",),
            categories=("cafe",),
            batch_size=10,
        )

        record.refresh_from_db()
        self.assertEqual(stats["new_place"], 1)
        self.assertEqual(record.normalized_place.address, "광주광역시 북구 테스트로 1")
        self.assertEqual(record.normalized_place.raw["normalized_sido_name"], "광주광역시")
