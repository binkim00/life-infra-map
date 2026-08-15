from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from recommendations.models import (
    KakaoPlaceMatch,
    Place,
    SourcePlaceRecord,
    TagEnrichmentRequest,
)


class NationwideTagSampleTests(TestCase):
    def make_confirmed(self, *, index, sido, category="cafe"):
        place = Place.objects.create(
            name=f"카카오 장소 {index}",
            category=category,
            address=f"{sido} 테스트로 {index}",
            lat=37 + index / 1000,
            lng=127 + index / 1000,
            source="kakao_local",
            external_id=f"kakao-{index}",
        )
        record = SourcePlaceRecord.objects.create(
            source="localdata",
            dataset="rest_restaurant",
            source_record_id=f"source-{index}",
            name=place.name,
            category=category,
            sido_name=sido,
            normalized_place=place,
        )
        KakaoPlaceMatch.objects.create(
            source_record=record,
            status="confirmed",
            canonical_place=place,
            kakao_place_id=place.external_id,
            score=95,
        )
        return place

    def test_builds_balanced_queue_only_from_confirmed_kakao_places(self):
        seoul = self.make_confirmed(index=1, sido="서울특별시")
        busan = self.make_confirmed(index=2, sido="부산광역시")
        local_place = Place.objects.create(
            name="미확인 장소", category="cafe", address="대구", lat=35.8, lng=128.6,
            source="localdata", external_id="unmatched",
        )
        SourcePlaceRecord.objects.create(
            source="localdata", dataset="rest_restaurant", source_record_id="unmatched",
            name=local_place.name, category="cafe", sido_name="대구광역시",
            normalized_place=local_place,
        )

        output = StringIO()
        call_command(
            "build_nationwide_tag_enrichment_sample",
            categories="cafe",
            tags="조용함",
            per_stratum=1,
            stdout=output,
        )

        self.assertEqual(TagEnrichmentRequest.objects.count(), 2)
        self.assertSetEqual(
            set(TagEnrichmentRequest.objects.values_list("place_id", flat=True)),
            {seoul.id, busan.id},
        )
        self.assertIn("strata=17", output.getvalue())
        self.assertIn("covered=2", output.getvalue())

    def test_dry_run_reports_without_writing(self):
        self.make_confirmed(index=1, sido="서울특별시")
        output = StringIO()
        call_command(
            "build_nationwide_tag_enrichment_sample",
            categories="cafe",
            tags="조용함",
            per_stratum=1,
            dry_run=True,
            stdout=output,
        )
        self.assertFalse(TagEnrichmentRequest.objects.exists())
        self.assertIn("[dry-run]", output.getvalue())

    def test_accepts_direct_kakao_registry_places_without_a_source_match(self):
        direct = Place.objects.create(
            name="카카오 직접 공원",
            category="city_park",
            address="제주특별자치도 제주시 테스트로 1",
            lat=33.5,
            lng=126.5,
            source="kakao_local",
            external_id="direct-park-1",
        )
        Place.objects.create(
            name="외부 공원",
            category="city_park",
            address="제주특별자치도 제주시 테스트로 2",
            lat=33.5,
            lng=126.5,
            source="citypark_standard",
            external_id="external-park-1",
        )

        call_command(
            "build_nationwide_tag_enrichment_sample",
            categories="city_park",
            tags="조용함",
            per_stratum=1,
            stdout=StringIO(),
        )

        self.assertSetEqual(
            set(TagEnrichmentRequest.objects.values_list("place_id", flat=True)),
            {direct.id},
        )
