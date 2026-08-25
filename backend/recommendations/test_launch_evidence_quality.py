from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from recommendations.management.commands.report_launch_evidence_quality import build_report
from recommendations.models import Place, PlaceTagEvidence, Tag


class LaunchEvidenceQualityTests(TestCase):
    def test_reports_only_busan_launch_categories(self):
        busan = Place.objects.create(
            name="부산 출시카페", category="cafe", address="부산광역시 부산진구 테스트로 1",
            lat=35.1, lng=129.0, source="semas", external_id="launch-quality-busan",
        )
        Place.objects.create(
            name="서울 제외카페", category="cafe", address="서울특별시 중구 테스트로 1",
            lat=37.5, lng=127.0, source="semas", external_id="launch-quality-seoul",
        )
        tag = Tag.objects.create(name="조용함")
        PlaceTagEvidence.objects.create(
            place=busan,
            tag=tag,
            evidence_key="launch-active",
            source="naver_blog_search",
            source_reference="https://example.com/busan",
            polarity="positive",
            expires_at=timezone.now() + timedelta(days=1),
        )

        report = build_report()

        self.assertEqual(report["region"], "부산")
        self.assertEqual(report["categories"]["cafe"]["places"], 1)
        self.assertEqual(report["categories"]["cafe"]["active_evidence_places"], 1)
        self.assertEqual(report["categories"]["cafe"]["recommendation_quality_levels"]["thin"], 1)
        self.assertEqual(report["categories"]["restaurant"]["places"], 0)
