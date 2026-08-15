from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.coverage_reporting import build_coverage_report


class BootstrapReportingTests(TestCase):
    def test_reports_region_category_tag_unknown_conflict_and_stale(self):
        place = Place.objects.create(
            name="부산 보고서 카페",
            category="cafe",
            address="부산광역시 해운대구 테스트로 1",
            lat=35.1,
            lng=129.1,
            source="kakao_local",
            external_id="reporting-1",
        )
        tag = Tag.objects.create(name="조용함")
        now = timezone.now()
        for polarity, reference in (("positive", "https://blog/p"), ("negative", "https://blog/n")):
            PlaceTagEvidence.objects.create(
                place=place,
                tag=tag,
                source="naver_blog_search",
                source_reference=reference,
                polarity=polarity,
                confidence=70,
                observed_at=now,
                expires_at=now + timedelta(days=30),
            )
        PlaceTag.objects.create(
            place=place,
            tag=tag,
            source="web_evidence",
            status="needs_verification",
            confidence=50,
        )

        report = build_coverage_report(now=now)
        quiet = report["cells"]["부산광역시/cafe"]["tags"]["조용함"]
        self.assertEqual(quiet["conflict"], 1)
        self.assertEqual(quiet["needs_verification"], 1)
        self.assertEqual(quiet["unknown_places"], 0)
        self.assertEqual(report["regions"]["부산광역시"]["readiness"], "PARTIAL")
