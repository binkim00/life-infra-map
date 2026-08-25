from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from recommendations.management.commands.report_city_food_coverage import build_report
from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag


class CityFoodCoverageTests(TestCase):
    def test_reports_active_stale_and_status_by_core_tag(self):
        place = Place.objects.create(
            name="서울 카페", category="cafe", address="서울특별시 중구 테스트로 1",
            lat=37.5, lng=127.0, source="semas", external_id="coverage-1",
        )
        tag = Tag.objects.create(name="조용함")
        PlaceTag.objects.create(place=place, tag=tag, source="web_evidence", status="candidate")
        now = timezone.now()
        PlaceTagEvidence.objects.create(
            place=place, tag=tag, evidence_key="active", source="naver_blog_search",
            source_reference="https://example.com/active", polarity="positive", expires_at=now + timedelta(days=1),
        )
        PlaceTagEvidence.objects.create(
            place=place, tag=tag, evidence_key="stale", source="naver_blog_search",
            source_reference="https://example.com/stale", polarity="positive", expires_at=now - timedelta(days=1),
        )

        cafe = build_report(now=now)["regions"]["서울"]["cafe"]

        self.assertEqual(cafe["places"], 1)
        self.assertEqual(cafe["active_evidence_places"], 1)
        self.assertEqual(cafe["stale_evidence_places"], 1)
        self.assertEqual(cafe["recommendation_quality_levels"]["thin"], 1)
        self.assertEqual(cafe["recommendation_quality_levels"]["empty"], 0)
        self.assertEqual(cafe["tags"]["조용함"]["statuses"]["candidate"], 1)
