from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from recommendations.management.commands.report_daily_collection import build_daily_collection_report
from recommendations.models import Place, PlaceTag, PlaceTagCollectionJob, PlaceTagEvidence, ProviderQuotaUsage, Tag


class DailyCollectionReportTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.place = Place.objects.create(
            name="보고서 카페", category="cafe", address="부산광역시", lat=35.1, lng=129.1,
            source="test", external_id="daily-report-place",
        )
        self.tag = Tag.objects.create(name="분위기좋음")

    def test_report_separates_naver_and_codex_results(self):
        PlaceTagCollectionJob.objects.create(
            place=self.place, provider="naver_search", cycle_date=self.today,
            status="completed", stats={"requests": 2, "evidences": 1},
        )
        ProviderQuotaUsage.objects.create(
            provider="naver_search", usage_date=self.today, request_count=2,
        )
        PlaceTagEvidence.objects.create(
            place=self.place, tag=self.tag, source="naver_blog_search", evidence="네이버 근거",
        )
        PlaceTagEvidence.objects.create(
            place=self.place, tag=self.tag, source="web_search", evidence="웹 근거",
        )
        PlaceTag.objects.create(
            place=self.place, tag=self.tag, source="web_evidence", status="needs_verification",
        )

        report = build_daily_collection_report(self.today)

        self.assertEqual(report["naver"]["planned_jobs"], 1)
        self.assertEqual(report["naver"]["useful_jobs"], 1)
        self.assertEqual(report["naver"]["api_requests"], 2)
        self.assertEqual(report["naver"]["new_evidence_rows"], 1)
        self.assertEqual(report["codex_web"]["new_evidence_rows"], 1)
        self.assertEqual(report["aggregate_tags"]["by_status"], {"needs_verification": 1})

    def test_report_excludes_rows_outside_requested_day(self):
        evidence = PlaceTagEvidence.objects.create(
            place=self.place, tag=self.tag, source="web_search", evidence="어제 근거",
        )
        yesterday = timezone.now() - timedelta(days=1)
        PlaceTagEvidence.objects.filter(pk=evidence.pk).update(created_at=yesterday)

        report = build_daily_collection_report(self.today)

        self.assertEqual(report["codex_web"]["new_evidence_rows"], 0)
