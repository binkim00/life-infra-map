from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from recommendations.management.commands.plan_daily_tag_collection import plan_daily_jobs
from recommendations.management.commands.process_place_tag_collection_jobs import process_jobs
from recommendations.management.commands.recover_tag_collection_jobs import recover_stale_jobs
from recommendations.models import (
    Place,
    PlaceTagCollectionJob,
    PlaceTagEvidence,
    ProviderQuotaUsage,
)
from recommendations.services.place_tag_collection import collect_naver_place_evidence


@override_settings(
    TAG_COLLECTION_DAILY_API_LIMIT=10,
    TAG_COLLECTION_QUOTA_PERCENT=90,
    TAG_COLLECTION_DAILY_PLACE_LIMIT=3,
    TAG_COLLECTION_REVISIT_DAYS=90,
    TAG_COLLECTION_STALE_LOCK_MINUTES=30,
)
class DailyTagCollectionTests(TestCase):
    def make_place(self, index, *, category="cafe", region="서울특별시"):
        return Place.objects.create(
            name="수집 테스트 {}".format(index),
            category=category,
            address="{} 중구 테스트로 {}".format(region, index),
            lat=37.5 + index / 1000,
            lng=127.0,
            source="kakao_local",
            external_id="daily-{}-{}".format(category, index),
        )

    def test_plans_balanced_idempotent_jobs_within_request_budget(self):
        self.make_place(1, category="cafe", region="서울특별시")
        self.make_place(2, category="restaurant", region="부산광역시")
        self.make_place(3, category="city_park", region="제주특별자치도")

        first = plan_daily_jobs(cycle_date=timezone.localdate(), place_limit=3)
        second = plan_daily_jobs(cycle_date=timezone.localdate(), place_limit=3)

        self.assertEqual(first["places"], 3)
        self.assertLessEqual(first["planned_requests"], 9)
        self.assertEqual(second["places"], 0)
        self.assertEqual(PlaceTagCollectionJob.objects.count(), 3)

    def test_worker_collects_multiple_tags_and_accounts_for_quota(self):
        place = self.make_place(1)
        PlaceTagCollectionJob.objects.create(
            place=place,
            provider="naver_search",
            cycle_date=timezone.localdate(),
            requested_tags=["조용함", "콘센트있음"],
            planned_requests=2,
        )

        result = process_jobs(
            limit=1,
            worker_id="test-worker",
            collector=lambda place, tags: {
                "executed": True,
                "requests": 2,
                "evidences": [
                    {
                        "tag_name": tag,
                        "polarity": "positive",
                        "evidence_summary": "직접 확인된 의미 속성",
                        "source_url": "https://example.com/{}".format(index),
                    }
                    for index, tag in enumerate(tags)
                ],
            },
        )

        job = PlaceTagCollectionJob.objects.get()
        quota = ProviderQuotaUsage.objects.get()
        self.assertEqual(result["evidences"], 2)
        self.assertEqual(job.status, "completed")
        self.assertEqual(quota.request_count, 2)
        self.assertEqual(quota.reserved_count, 0)
        self.assertEqual(PlaceTagEvidence.objects.count(), 2)
        self.assertEqual(
            set(PlaceTagEvidence.objects.values_list("source", flat=True)),
            {"web_search"},
        )

    @patch("recommendations.services.place_tag_collection._request_channel")
    def test_place_collection_queries_one_representative_keyword_per_pack(self, request_channel):
        place = self.make_place(1)
        request_channel.return_value = {
            "items": [{
                "title": "수집 테스트 1 서울 중구 카페",
                "description": "분위기 좋고 콘센트 있음",
                "link": "https://example.com/review",
                "postdate": "20260816",
            }],
        }

        result = collect_naver_place_evidence(
            place,
            requested_tags=["콘센트있음", "분위기좋음", "조용함"],
        )

        queries = [call.args[1] for call in request_channel.call_args_list]
        self.assertEqual(len(queries), 2)
        self.assertTrue(any(query.endswith("노트북") for query in queries))
        self.assertTrue(any(query.endswith("분위기") for query in queries))
        self.assertFalse(any("노트북 콘센트" in query for query in queries))
        self.assertEqual({item["tag_name"] for item in result["evidences"]}, {
            "콘센트있음",
            "분위기좋음",
        })

    def test_stale_processing_job_is_recovered_and_releases_reservation(self):
        place = self.make_place(1)
        locked_at = timezone.now() - timedelta(hours=1)
        job = PlaceTagCollectionJob.objects.create(
            place=place,
            provider="naver_search",
            cycle_date=timezone.localdate(),
            status="processing",
            planned_requests=3,
            locked_at=locked_at,
            worker_id="dead-worker",
        )
        ProviderQuotaUsage.objects.create(
            provider="naver_search",
            usage_date=timezone.localdate(),
            daily_limit=10,
            reserved_count=3,
        )

        self.assertEqual(recover_stale_jobs(), 1)

        job.refresh_from_db()
        quota = ProviderQuotaUsage.objects.get()
        self.assertEqual(job.status, "retry")
        self.assertEqual(quota.reserved_count, 0)
