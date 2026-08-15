from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from recommendations.models import Place, SourcePlaceRecord


class StageExistingPlacesTests(TestCase):
    def test_stages_official_legacy_place_without_treating_it_as_canonical(self):
        place = Place.objects.create(
            name="전국 관광지",
            category="tourism",
            address="제주특별자치도 제주시 테스트로 1",
            detail_location="제주특별자치도 제주시 테스트로 1",
            lat=33.5,
            lng=126.5,
            source="tour_api",
            external_id="TOUR-1",
            source_name="TourAPI",
        )

        call_command(
            "stage_existing_places_for_matching",
            source="tour_api",
            dataset="tourism",
            stdout=StringIO(),
        )

        record = SourcePlaceRecord.objects.get()
        self.assertEqual(record.source_record_id, "TOUR-1")
        self.assertEqual(record.sido_name, "제주특별자치도")
        self.assertEqual(record.raw["legacy_place_id"], place.id)
        self.assertIsNone(record.normalized_place)

    def test_dry_run_does_not_write(self):
        Place.objects.create(
            name="관광지",
            category="tourism",
            address="부산광역시 중구",
            lat=35.1,
            lng=129.0,
            source="tour_api",
            external_id="TOUR-2",
        )

        call_command(
            "stage_existing_places_for_matching",
            source="tour_api",
            dataset="tourism",
            dry_run=True,
            stdout=StringIO(),
        )

        self.assertFalse(SourcePlaceRecord.objects.exists())
