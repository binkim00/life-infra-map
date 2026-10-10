from datetime import timedelta
from unittest.mock import Mock, patch

from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from recommendations.models import CollectionPlannerState, Place, PlaceTagCollectionJob, ProviderQuotaUsage
from recommendations.management.commands.plan_daily_tag_collection import plan_daily_jobs
from recommendations.management.commands.process_place_tag_collection_jobs import claim_next_job, process_jobs, settle_quota
from recommendations.management.commands.recover_tag_collection_jobs import recover_stale_jobs
from recommendations.management.commands.run_tag_collection_scheduler import scheduler_tick
from recommendations.services.collection_resources import planner_transaction


@override_settings(TAG_COLLECTION_BOUNDED_PLANNER_ENABLED=True,
                   TAG_COLLECTION_REFILL_LIMIT=3, TAG_COLLECTION_SCAN_PAGE=5,
                   TAG_COLLECTION_PLANNER_COOLDOWN_SECONDS=60,
                   TAG_COLLECTION_DAILY_API_LIMIT=100, TAG_COLLECTION_QUOTA_PERCENT=90,
                   TAG_COLLECTION_STRUCTURED_FIRST=False)
class CollectionResourceTests(TestCase):
    def place(self, index, region="서울특별시", category="cafe"):
        return Place.objects.create(name=f"fixture {index}", category=category,
                                    address=f"{region} fixture", lat=37, lng=127,
                                    source="resource_test", external_id=str(index))

    def plan(self, **kwargs):
        return plan_daily_jobs(cycle_date=timezone.localdate(), place_limit=200,
                               categories=("cafe",), regions=("서울특별시",), **kwargs)

    def job(self, index=1):
        return PlaceTagCollectionJob.objects.create(place=self.place(index),
            cycle_date=timezone.localdate(), planned_requests=2)

    def test_page_and_refill_are_bounded(self):
        for i in range(20):
            self.place(i)
        with CaptureQueriesContext(connection) as queries:
            result = self.plan()
        self.assertEqual(result["places"], 3)
        self.assertEqual(result["scanned"], 5)
        self.assertEqual(result["candidates"], 5)
        self.assertFalse(any("LIKE" in row["sql"] for row in queries))
        self.assertFalse(any("COUNT(" in row["sql"] and 'recommendations_place"' in row["sql"] for row in queries))

    def test_restart_resumes_and_cooldown_prevents_repeat(self):
        for i in range(8):
            self.place(i)
        first = self.plan()
        cursor = CollectionPlannerState.objects.get().cursor
        self.assertTrue(self.plan()["deferred"])
        CollectionPlannerState.objects.update(next_attempt_at=None)
        second = self.plan()
        self.assertEqual(first["places"] + second["places"], 5)
        self.assertGreater(CollectionPlannerState.objects.get().cursor, cursor)
        CollectionPlannerState.objects.update(next_attempt_at=None)
        self.assertEqual(self.plan()["places"], 3)

    def test_empty_stratum_advances_cursor(self):
        places = []
        for i in range(6):
            places.append(self.place(i, region="부산광역시"))
        result = self.plan()
        self.assertEqual(result["places"], 0)
        self.assertEqual(CollectionPlannerState.objects.get().cursor, places[4].pk)

    def test_dry_run_has_no_jobs_or_checkpoint(self):
        self.place(1)
        self.assertEqual(self.plan(dry_run=True)["places"], 1)
        self.assertFalse(PlaceTagCollectionJob.objects.exists())
        self.assertFalse(CollectionPlannerState.objects.exists())

    def test_zero_limit_creates_nothing(self):
        self.place(1)
        result = plan_daily_jobs(cycle_date=timezone.localdate(), place_limit=0)
        self.assertEqual(result["places"], 0)

    def test_no_quota_does_not_scan_or_advance(self):
        self.place(1)
        ProviderQuotaUsage.objects.create(provider="naver_search", usage_date=timezone.localdate(), request_count=90)
        result = self.plan()
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(CollectionPlannerState.objects.get().cursor, 0)

    def test_dry_run_without_quota_does_not_create_checkpoint(self):
        ProviderQuotaUsage.objects.create(provider="naver_search", usage_date=timezone.localdate(), request_count=90)
        self.plan(dry_run=True)
        self.assertFalse(CollectionPlannerState.objects.exists())

    @override_settings(TAG_COLLECTION_PLANNER_WALL_SECONDS=-1)
    def test_deadline_rolls_back_jobs_and_cursor(self):
        self.place(1)
        self.assertTrue(self.plan()["deferred"])
        self.assertFalse(PlaceTagCollectionJob.objects.exists())
        self.assertFalse(CollectionPlannerState.objects.filter(cursor__gt=0).exists())

    @override_settings(TAG_COLLECTION_QUEUE_LOW=2, TAG_COLLECTION_QUEUE_HIGH=4)
    @patch("recommendations.management.commands.run_tag_collection_scheduler.plan_daily_jobs")
    def test_full_queue_skips_planner(self, planner):
        self.job(1)
        self.job(2)
        self.assertEqual(scheduler_tick()["planned"], 0)
        planner.assert_not_called()

    def test_quota_settlement_is_once_only(self):
        self.job()
        job, _ = claim_next_job(worker_id="one")
        self.assertTrue(settle_quota(job, 2, succeeded=True))
        self.assertFalse(settle_quota(job, 2, succeeded=True))
        quota = ProviderQuotaUsage.objects.get()
        self.assertEqual((quota.request_count, quota.reserved_count), (2, 0))

    def test_actual_calls_are_not_clamped_to_reservation_estimate(self):
        self.job()
        job, _ = claim_next_job(worker_id="one")
        settle_quota(job, 3, succeeded=True)
        self.assertEqual(ProviderQuotaUsage.objects.get().request_count, 3)

    def test_midnight_settlement_uses_reservation_day(self):
        self.job()
        job, _ = claim_next_job(worker_id="one")
        tomorrow = timezone.localdate() + timedelta(days=1)
        ProviderQuotaUsage.objects.create(provider=job.provider, usage_date=tomorrow, reserved_count=9)
        with patch("recommendations.management.commands.process_place_tag_collection_jobs.timezone.localdate", return_value=tomorrow):
            settle_quota(job, 2, succeeded=True)
        self.assertEqual(ProviderQuotaUsage.objects.get(usage_date=tomorrow).reserved_count, 9)
        self.assertEqual(ProviderQuotaUsage.objects.get(usage_date=job.reservation_date).request_count, 2)

    def test_recovery_does_not_release_settled_quota_twice(self):
        self.job()
        job, _ = claim_next_job(worker_id="one")
        settle_quota(job, 2, succeeded=True)
        PlaceTagCollectionJob.objects.filter(pk=job.pk).update(locked_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(recover_stale_jobs(), 1)
        self.assertEqual(ProviderQuotaUsage.objects.get().reserved_count, 0)

    def test_old_claim_cannot_settle_new_attempt(self):
        self.job()
        old, _ = claim_next_job(worker_id="one")
        PlaceTagCollectionJob.objects.filter(pk=old.pk).update(locked_at=timezone.now() - timedelta(hours=1))
        recover_stale_jobs()
        current, _ = claim_next_job(worker_id="two")
        self.assertFalse(settle_quota(old, 2, succeeded=True))
        self.assertTrue(settle_quota(current, 1, succeeded=True))
        self.assertEqual(ProviderQuotaUsage.objects.get().request_count, 1)

    def test_checkpoint_resumes_without_external_call(self):
        job = self.job()
        job, _ = claim_next_job(worker_id="one")
        settle_quota(job, 1, succeeded=True)
        PlaceTagCollectionJob.objects.filter(pk=job.pk).update(
            result_checkpoint={"requests": 1, "evidences": [], "error": "insufficient_evidence"},
            locked_at=timezone.now() - timedelta(hours=1))
        recover_stale_jobs()
        collector = Mock(side_effect=AssertionError("must resume persisted result"))
        self.assertEqual(process_jobs(limit=1, worker_id="two", collector=collector)["processed"], 1)
        collector.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertIsNone(job.result_checkpoint)
        self.assertEqual(ProviderQuotaUsage.objects.get().request_count, 1)

    def test_postgresql_limits_restore_after_success_and_error(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires isolated PostgreSQL")
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            before = cursor.fetchone()[0]
        with planner_transaction():
            with connection.cursor() as cursor:
                cursor.execute("SHOW max_parallel_workers_per_gather")
                self.assertEqual(cursor.fetchone()[0], "0")
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            self.assertEqual(cursor.fetchone()[0], before)
        with self.assertRaises(Exception):
            with planner_transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 / 0")
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            self.assertEqual(cursor.fetchone()[0], before)

    @override_settings(TAG_COLLECTION_PLANNER_STATEMENT_MS=30)
    def test_postgresql_timeout_cancels_and_restores_transaction(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires isolated PostgreSQL")
        from django.db import OperationalError
        with self.assertRaises(OperationalError):
            with planner_transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_sleep(0.1)")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 42")
            self.assertEqual(cursor.fetchone()[0], 42)

    @override_settings(TAG_COLLECTION_PLANNER_STATEMENT_MS=30)
    def test_postgresql_planner_timeout_saves_backoff_without_advancing(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires isolated PostgreSQL")
        self.place(1)

        def slow_context(*args, **kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(0.1)")

        for failures in (1, 2):
            CollectionPlannerState.objects.update(next_attempt_at=None)
            with patch("recommendations.services.bounded_collection_planner.priority_context", side_effect=slow_context):
                self.assertTrue(self.plan()["deferred"])
            state = CollectionPlannerState.objects.get()
            self.assertEqual(state.cursor, 0)
            self.assertEqual(state.metrics["consecutive_deferrals"], failures)
            self.assertGreater((state.next_attempt_at - timezone.now()).total_seconds(), 50 * failures)
        self.assertFalse(PlaceTagCollectionJob.objects.exists())

    def test_pacing_waits_between_successful_jobs(self):
        self.job()
        with patch("recommendations.management.commands.process_place_tag_collection_jobs.time.sleep") as sleep:
            process_jobs(limit=1, pace=True, collector=lambda *args: {
                "requests": 1, "evidences": [], "error": "insufficient_evidence"})
        self.assertEqual(sleep.call_count, 1)
        self.assertGreater(sleep.call_args.args[0], 0)

    @override_settings(TAG_COLLECTION_DAILY_PLACE_LIMIT=6, TAG_COLLECTION_REFILL_LIMIT=3,
                       TAG_COLLECTION_SCAN_PAGE=50)
    def test_bootstrap_preserves_daily_regional_targets_across_refills(self):
        regions = ("서울특별시", "부산광역시", "대구광역시")
        for r, region in enumerate(regions):
            for i in range(5):
                self.place(r * 10 + i, region=region)
        for _ in range(10):
            CollectionPlannerState.objects.update(next_attempt_at=None)
            plan_daily_jobs(cycle_date=timezone.localdate(), place_limit=20, mode="bootstrap",
                categories=("cafe",), regions=regions,
                region_priority_weights=dict(zip(regions, (3, 2, 1))))
        counts = {region: PlaceTagCollectionJob.objects.filter(context__region=region).count() for region in regions}
        self.assertEqual(counts, dict(zip(regions, (3, 2, 1))))

    def test_bootstrap_retains_hard_bucket_request_cap(self):
        from recommendations.services.adaptive_budget import HARD_CAPPED_BUCKETS
        from recommendations.services.bootstrap_priority import priority_context
        bucket = next(iter(HARD_CAPPED_BUCKETS))
        self.place(1)

        def contexts(places, **kwargs):
            result = priority_context(places, **kwargs)
            for context in result.values():
                context["budget_bucket"] = bucket
            return result

        with override_settings(TAG_COLLECTION_BUDGET_WEIGHTS={bucket: 1, "discovery": 99}):
            with patch("recommendations.services.bounded_collection_planner.priority_context", side_effect=contexts):
                self.assertEqual(self.plan(mode="bootstrap")["places"], 0)

    @override_settings(TAG_COLLECTION_REFILL_LIMIT=100, TAG_COLLECTION_SCAN_PAGE=2000,
                       TAG_COLLECTION_DAILY_API_LIMIT=25000)
    def test_synthetic_large_registry_uses_primary_key_page(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires isolated PostgreSQL")
        Place.objects.bulk_create([Place(name=f"synthetic {i}", category="cafe",
            address="서울특별시 synthetic", lat=37, lng=127, source="synthetic_resource_test",
            external_id=str(i), raw={"synthetic": "x" * 2000}) for i in range(20000)], batch_size=500)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE recommendations_place")
        with CaptureQueriesContext(connection) as queries:
            result = self.plan(mode="bootstrap")
        self.assertEqual(result["scanned"], 2000)
        self.assertLessEqual(result["candidates"], 300)
        self.assertEqual(result["places"], 100)
        page_sql = next(row["sql"] for row in queries if 'FROM "recommendations_place"' in row["sql"] and "LIMIT 2000" in row["sql"])
        with connection.cursor() as cursor:
            cursor.execute("EXPLAIN (FORMAT JSON) " + page_sql)
            plan = cursor.fetchone()[0][0]["Plan"]
        self.assertEqual(plan["Node Type"], "Limit")
        self.assertIn("Index", str(plan))
        print("Synthetic planner: mode=bootstrap rows=20000 page=2000 candidates={} jobs={} elapsed_ms={} queries={} plan=PK-index".format(
            result["candidates"], result["places"], result["elapsed_ms"], len(queries)))

    def test_postgresql_additive_migration_preserves_existing_job(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires isolated PostgreSQL")
        from django.db.migrations.loader import MigrationLoader
        place = self.place(1000)
        with override_settings(MIGRATION_MODULES={}):
            loader = MigrationLoader(connection)
            old_state = loader.project_state(("recommendations", "0031_place_name_prefix_index"))
            migration = loader.get_migration("recommendations", "0032_collectionplannerstate_and_more")
        with connection.schema_editor() as editor:
            editor.delete_model(CollectionPlannerState)
            for field in ("quota_settled_at", "reservation_date", "result_checkpoint"):
                editor.remove_field(PlaceTagCollectionJob, PlaceTagCollectionJob._meta.get_field(field))
        old_job_model = old_state.apps.get_model("recommendations", "PlaceTagCollectionJob")
        old_job = old_job_model.objects.create(place_id=place.pk, cycle_date=timezone.localdate(), planned_requests=2)
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with connection.schema_editor() as editor:
            migration.apply(old_state, editor)
        upgraded = PlaceTagCollectionJob.objects.get(pk=old_job.pk)
        self.assertEqual(upgraded.status, "queued")
        self.assertEqual(upgraded.planned_requests, 2)
        self.assertIsNone(upgraded.reservation_date)
        self.assertIsNone(upgraded.result_checkpoint)


@override_settings(TAG_COLLECTION_DAILY_API_LIMIT=100, TAG_COLLECTION_QUOTA_PERCENT=90)
class CollectionPostgresConcurrencyTests(TransactionTestCase):
    def test_real_heartbeat_renews_claim_on_separate_connection(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires isolated PostgreSQL")
        import time
        from recommendations.management.commands.process_place_tag_collection_jobs import claim_heartbeat
        place = Place.objects.create(name="heartbeat fixture", category="cafe", lat=37, lng=127,
                                     source="resource_test", external_id="heartbeat")
        PlaceTagCollectionJob.objects.create(place=place, cycle_date=timezone.localdate(), planned_requests=1)
        job, _ = claim_next_job(worker_id="heartbeat")
        past = timezone.now() - timedelta(hours=1)
        PlaceTagCollectionJob.objects.filter(pk=job.pk).update(locked_at=past)
        with claim_heartbeat(job, enabled=True, interval=0.01):
            for _ in range(50):
                time.sleep(0.02)
                job.refresh_from_db()
                if job.locked_at > past:
                    break
        self.assertGreater(job.locked_at, past)

    def test_claim_skips_row_locked_by_another_connection(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires isolated PostgreSQL")
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connections
        places = [Place.objects.create(name=f"lock fixture {i}", category="cafe",
                  lat=37, lng=127, source="resource_test", external_id=f"lock-{i}") for i in range(2)]
        jobs = [PlaceTagCollectionJob.objects.create(place=place, cycle_date=timezone.localdate(),
                planned_requests=1, priority=10-i) for i, place in enumerate(places)]

        def claim():
            try:
                job, _ = claim_next_job(worker_id="parallel")
                return job.pk
            finally:
                connections.close_all()

        with transaction.atomic():
            PlaceTagCollectionJob.objects.select_for_update().get(pk=jobs[0].pk)
            with ThreadPoolExecutor(max_workers=1) as pool:
                claimed = pool.submit(claim).result(timeout=5)
        self.assertEqual(claimed, jobs[1].pk)
