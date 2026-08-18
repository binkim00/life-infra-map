from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from recommendations.management.commands.plan_daily_tag_collection import plan_daily_jobs
from recommendations.management.commands.process_place_tag_collection_jobs import process_jobs
from recommendations.management.commands.recover_tag_collection_jobs import recover_stale_jobs
from recommendations.management.commands.evaluate_sparse_query_packs import record_targeted_attempt
from recommendations.management.commands.run_tag_collection_scheduler import scheduler_tick
from recommendations.models import (
    Place,
    PlaceTag,
    Tag,
    PlaceTagCollectionJob,
    PlaceTagEvidence,
    ProviderQuotaUsage,
)
from recommendations.services.place_tag_collection import collect_naver_place_evidence
from recommendations.services.place_tag_collection import requested_tags_for_category
from recommendations.services.bootstrap_priority import priority_context
from recommendations.services.restaurant_collection_quality import restaurant_collection_quality
from recommendations.services.adaptive_budget import allocate_by_request_budget, collection_bucket, recommend_scaled_budget


@override_settings(
    TAG_COLLECTION_DAILY_API_LIMIT=10,
    TAG_COLLECTION_QUOTA_PERCENT=90,
    TAG_COLLECTION_DAILY_PLACE_LIMIT=3,
    TAG_COLLECTION_REVISIT_DAYS=90,
    TAG_COLLECTION_STALE_LOCK_MINUTES=30,
    TAG_COLLECTION_MODE="balanced",
    TAG_COLLECTION_RATE_LIMIT_ENABLED=False,
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

    def test_solo_use_is_collected_for_relevant_non_restaurant_profiles(self):
        for category in ("cafe", "tourism", "city_park", "library"):
            with self.subTest(category=category):
                self.assertIn("혼자이용좋음", requested_tags_for_category(category))

    def test_restaurant_quality_only_lowers_collection_priority(self):
        place = self.make_place(91, category="restaurant")
        place.name = "주식회사 푸디스트 본사 직원식당"
        place.save(update_fields=["name"])
        result = restaurant_collection_quality(place, identity_misses=2)
        self.assertLess(result["score"], 0)
        self.assertIn("institutional_food_service", result["flags"])
        self.assertTrue(Place.objects.filter(pk=place.pk).exists())

    def test_volatile_stale_web_evidence_gets_refresh_priority(self):
        place = self.make_place(92)
        tag = Tag.objects.create(name="콘센트있음")
        PlaceTagEvidence.objects.create(
            place=place, tag=tag, source="naver_blog_search",
            observed_at=timezone.now() - timedelta(days=200),
            expires_at=timezone.now() - timedelta(days=20),
        )
        context = priority_context([place])[place.id]
        self.assertEqual(context["expired_web_evidence_count"], 1)
        self.assertEqual(context["expired_structured_evidence_count"], 0)
        self.assertEqual(context["volatile_expired_tag_count"], 1)
        self.assertGreaterEqual(context["components"]["freshness_gap"], 7)

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

    @override_settings(
        TAG_COLLECTION_DAILY_API_LIMIT=100,
        TAG_COLLECTION_BOOTSTRAP_TIER_WEIGHTS="70,15,10,5",
        TAG_COLLECTION_CATEGORY_PRIORITIES={
            "cafe": 20, "restaurant": 20, "tourism": 12, "city_park": 12,
        },
    )
    def test_bootstrap_plan_prioritizes_tier_one_without_excluding_other_tiers(self):
        regions = ["서울특별시", "인천광역시", "경기도 수원시", "전라남도"]
        for tier, region in enumerate(regions, start=1):
            for index in range(10):
                self.make_place(tier * 100 + index, region=region)

        stats = plan_daily_jobs(
            cycle_date=timezone.localdate(),
            place_limit=10,
            mode="bootstrap",
        )

        tiers = list(PlaceTagCollectionJob.objects.values_list("context__tier", flat=True))
        self.assertEqual(stats["places"], 10)
        self.assertGreater(tiers.count(1), 0)
        self.assertTrue(any(tier > 1 for tier in tiers))

    @override_settings(
        TAG_COLLECTION_DAILY_API_LIMIT=1000,
        TAG_COLLECTION_BOOTSTRAP_TIER_WEIGHTS="70,15,10,5",
        TAG_COLLECTION_BOOTSTRAP_CATEGORY_MAX_SHARE=40,
        TAG_COLLECTION_CATEGORY_PRIORITIES={"cafe": 100, "city_park": 1},
    )
    def test_bootstrap_pool_does_not_starve_a_category_concentrated_in_one_city(self):
        for index in range(80):
            self.make_place(index, category="cafe", region="부산광역시")
            self.make_place(1000 + index, category="city_park", region="부산광역시")

        stats = plan_daily_jobs(
            cycle_date=timezone.localdate(),
            place_limit=100,
            mode="bootstrap",
        )

        cafe_jobs = PlaceTagCollectionJob.objects.filter(place__category="cafe").count()
        self.assertEqual(stats["places"], 100)
        self.assertGreaterEqual(cafe_jobs, 40)

    @override_settings(
        TAG_COLLECTION_DAILY_API_LIMIT=1000,
        TAG_COLLECTION_BOOTSTRAP_CATEGORY_MAX_SHARE=40,
        TAG_COLLECTION_CATEGORY_PRIORITIES={"cafe": 20, "restaurant": 20},
    )
    def test_bootstrap_can_target_only_food_registry_categories(self):
        for index in range(20):
            self.make_place(index, category="cafe", region="서울특별시")
            self.make_place(100 + index, category="restaurant", region="부산광역시")
            self.make_place(200 + index, category="city_park", region="서울특별시")

        stats = plan_daily_jobs(
            cycle_date=timezone.localdate(),
            place_limit=30,
            mode="bootstrap",
            categories=("cafe", "restaurant"),
        )

        self.assertEqual(stats["places"], 30)
        self.assertEqual(
            set(PlaceTagCollectionJob.objects.values_list("place__category", flat=True)),
            {"cafe", "restaurant"},
        )

    @override_settings(
        TAG_COLLECTION_DAILY_API_LIMIT=1000,
        TAG_COLLECTION_BOOTSTRAP_CATEGORY_MAX_SHARE=100,
        TAG_COLLECTION_CATEGORY_PRIORITIES={"cafe": 20},
    )
    def test_bootstrap_can_target_one_region_without_leaking_to_another(self):
        for index in range(20):
            self.make_place(index, category="cafe", region="서울특별시")
            self.make_place(100 + index, category="cafe", region="부산광역시")

        stats = plan_daily_jobs(
            cycle_date=timezone.localdate(),
            place_limit=10,
            mode="bootstrap",
            categories=("cafe",),
            regions=("서울특별시",),
        )

        self.assertEqual(stats["places"], 10)
        self.assertFalse(
            PlaceTagCollectionJob.objects.exclude(place__address__startswith="서울특별시").exists()
        )

    @override_settings(
        TAG_COLLECTION_DAILY_API_LIMIT=100,
        TAG_COLLECTION_BOOTSTRAP_CATEGORY_MAX_SHARE=100,
        TAG_COLLECTION_CATEGORY_PRIORITIES={"cafe": 20},
    )
    def test_bootstrap_prefers_unverified_candidate_hint_over_plain_discovery(self):
        self.make_place(501, category="cafe", region="서울특별시")
        candidate = self.make_place(502, category="cafe", region="서울특별시")
        tag = Tag.objects.create(name="분위기좋음")
        PlaceTag.objects.create(place=candidate, tag=tag, status="candidate", confidence=50)

        stats = plan_daily_jobs(
            cycle_date=timezone.localdate(), place_limit=1, mode="bootstrap",
            categories=("cafe",), regions=("서울특별시",),
        )

        self.assertEqual(stats["places"], 1)
        job = PlaceTagCollectionJob.objects.get()
        self.assertEqual(job.place_id, candidate.id)
        self.assertEqual(job.context["budget_bucket"], "candidate_hint")

    def test_scheduler_refills_a_partial_daily_plan(self):
        places = [self.make_place(index) for index in range(1, 5)]
        PlaceTagCollectionJob.objects.create(
            place=places[0],
            provider="naver_search",
            cycle_date=timezone.localdate(),
            requested_tags=["조용함"],
            planned_requests=1,
        )

        stats = scheduler_tick()

        self.assertEqual(stats["planned"], 2)
        self.assertEqual(PlaceTagCollectionJob.objects.count(), 3)

    @override_settings(
        TAG_COLLECTION_MODE="bootstrap",
        TAG_COLLECTION_FOCUS_REGION="부산광역시",
        TAG_COLLECTION_FOCUS_CATEGORIES=("cafe", "restaurant"),
        TAG_COLLECTION_DAILY_API_LIMIT=100,
        TAG_COLLECTION_DAILY_PLACE_LIMIT=2,
    )
    def test_scheduler_keeps_bootstrap_collection_in_focus_region(self):
        self.make_place(801, category="cafe", region="부산광역시")
        self.make_place(802, category="restaurant", region="부산광역시")
        self.make_place(803, category="cafe", region="서울특별시")
        scheduler_tick()
        self.assertFalse(PlaceTagCollectionJob.objects.exclude(place__address__startswith="부산").exists())

    def test_stale_budget_is_a_hard_cap_during_fallback(self):
        candidates = [
            (self.make_place(820 + index), {"budget_bucket": "stale_refresh", "score": 10, "targeted_tags": []})
            for index in range(5)
        ]
        selected, used = allocate_by_request_budget(
            candidates, budget=100,
            weights={"stale_refresh": 1, "candidate_hint": 99},
            request_count=lambda context: 1,
        )
        self.assertLessEqual(used.get("stale_refresh", 0), 1)
        self.assertEqual(len(selected), 1)

    def test_region_enrichment_command_reports_focus_state(self):
        self.make_place(840, category="cafe", region="부산광역시")
        output = StringIO()
        from django.core.management import call_command
        call_command("report_region_enrichment", "부산", stdout=output)
        self.assertIn("Focus Region: 부산", output.getvalue())
        self.assertIn("Recommendation:", output.getvalue())

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

    @patch("recommendations.services.place_tag_collection._request_channel")
    def test_adaptive_collection_stops_after_discovery_identity_mismatch(self, request_channel):
        request_channel.return_value = {"items": [{
            "title": "전혀 다른 장소", "description": "다른 지역 카페 후기",
            "link": "https://example.com/wrong-adaptive",
        }]}
        result = collect_naver_place_evidence(
            self.make_place(71), strategy="adaptive",
            targeted_tags=["콘센트있음", "혼자이용좋음"],
        )
        self.assertEqual(result["requests"], 1)
        self.assertEqual(result["miss_reason"], "IDENTITY_MISMATCH")

    @override_settings(TAG_COLLECTION_ADOPTED_TARGET_CLUSTERS=("work_sparse", "solo"))
    @patch("recommendations.services.place_tag_collection._request_channel")
    def test_adaptive_collection_runs_targeted_pack_only_after_identity_pass(self, request_channel):
        request_channel.return_value = {"items": [{
            "title": "수집 테스트 72 서울 중구 카페",
            "description": "혼자 책 읽기 좋고 자리마다 콘센트가 있다",
            "link": "https://example.com/adaptive", "postdate": "20260816",
        }]}
        result = collect_naver_place_evidence(
            self.make_place(72), strategy="adaptive",
            targeted_tags=["콘센트있음", "혼자이용좋음"],
        )
        self.assertEqual(result["requests"], 3)
        self.assertEqual(
            {row["tag_name"] for row in result["evidences"]},
            {"콘센트있음", "혼자이용좋음"},
        )

    @override_settings(TAG_COLLECTION_ADOPTED_TARGET_CLUSTERS=("work_sparse",))
    @patch("recommendations.services.place_tag_collection._request_channel")
    def test_targeted_only_collection_uses_one_sparse_pack(self, request_channel):
        request_channel.return_value = {"items": []}
        result = collect_naver_place_evidence(
            self.make_place(73), strategy="targeted_only",
            targeted_tags=["콘센트있음", "무료와이파이", "노트북작업"],
        )
        self.assertEqual(result["requests"], 1)
        self.assertTrue(request_channel.call_args.args[1].endswith("콘센트"))

    @patch("recommendations.services.place_tag_collection._request_channel")
    def test_targeted_only_candidate_ambience_uses_candidate_tag_keyword(self, request_channel):
        request_channel.return_value = {"items": []}
        result = collect_naver_place_evidence(
            self.make_place(74), strategy="targeted_only",
            targeted_tags=["데이트좋음"],
        )
        self.assertEqual(result["requests"], 1)
        self.assertTrue(request_channel.call_args.args[1].endswith("데이트"))

    def test_targeted_attempt_checkpoint_is_idempotently_recorded(self):
        place = self.make_place(75)
        result = {"requests": 1}
        record_targeted_attempt(place, "candidate:ambience", result)
        record_targeted_attempt(place, "candidate:ambience", result)
        jobs = PlaceTagCollectionJob.objects.filter(place=place)
        self.assertEqual(jobs.count(), 1)
        self.assertIn(
            "candidate:ambience",
            jobs.get().context["targeted_attempts"],
        )
        self.assertEqual(
            jobs.get().context["targeted_attempt_results"]["candidate:ambience"]["requests"],
            1,
        )
        self.assertEqual(
            jobs.get().context["targeted_metrics"]["candidate_hint"]["calls"],
            2,
        )

    def test_collection_bucket_prefers_candidate_and_limits_stale(self):
        place = self.make_place(76)
        self.assertEqual(collection_bucket(place, {"adaptive_reason": "candidate_hint"}), "candidate_hint")
        self.assertEqual(collection_bucket(place, {"adaptive_reason": "no_tag_expression"}), "no_tag_targeted")
        self.assertEqual(collection_bucket(place, {"adaptive_reason": "stale_refresh"}), "stale_refresh")
        self.assertEqual(collection_bucket(place, {"adaptive_reason": "discovery"}), "cafe_discovery")

    def test_scaling_increases_only_after_three_stable_cycles(self):
        result = recommend_scaled_budget(
            [{"calls": 500, "active_evidence": 100, "failures": 0, "rate_limited": 0}] * 3,
            current_budget=1000,
        )
        self.assertEqual(result["action"], "increase")
        self.assertEqual(result["recommended_budget"], 1200)

    @patch("recommendations.services.place_tag_collection._request_channel")
    def test_collection_reports_no_search_result(self, request_channel):
        request_channel.return_value = {"items": []}
        result = collect_naver_place_evidence(self.make_place(1))
        self.assertEqual(result["miss_reason"], "NO_SEARCH_RESULT")

    @patch("recommendations.services.place_tag_collection._request_channel")
    def test_collection_reports_identity_mismatch(self, request_channel):
        request_channel.return_value = {"items": [{
            "title": "다른 장소 후기",
            "description": "서울 강남구의 분위기 좋은 장소",
            "link": "https://example.com/wrong",
        }]}
        result = collect_naver_place_evidence(self.make_place(1))
        self.assertEqual(result["miss_reason"], "IDENTITY_MISMATCH")

    @patch("recommendations.services.canonical_ai_evidence_extractor.extract_canonical_tags_from_evidence")
    @patch("recommendations.services.place_tag_collection._request_channel")
    def test_rule_success_does_not_call_optional_ai(self, request_channel, ai_extract):
        request_channel.return_value = {"items": [{
            "title": "수집 테스트 1 서울 중구 카페",
            "description": "분위기 좋고 조용한 공간",
            "link": "https://example.com/rule-success",
            "postdate": "20260816",
        }]}
        result = collect_naver_place_evidence(
            self.make_place(1),
            requested_tags=["분위기좋음"],
            allow_ai=True,
        )
        self.assertGreater(len(result["evidences"]), 0)
        ai_extract.assert_not_called()

    def test_rate_limited_result_is_counted_and_retried(self):
        place = self.make_place(1)
        PlaceTagCollectionJob.objects.create(
            place=place,
            provider="naver_search",
            cycle_date=timezone.localdate(),
            requested_tags=["조용함"],
            planned_requests=1,
        )
        process_jobs(
            limit=1,
            collector=lambda place, tags: {
                "executed": True,
                "requests": 1,
                "evidences": [],
                "error": "rate_limited",
            },
        )
        job = PlaceTagCollectionJob.objects.get()
        quota = ProviderQuotaUsage.objects.get(provider="naver_search")
        self.assertEqual(job.status, "retry")
        self.assertEqual(quota.rate_limited_count, 1)

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
