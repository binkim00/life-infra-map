"""Run against the CPU foundation snapshot; skip when that foundation is absent."""
import importlib.util
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from recommendations.models import Place, PlaceTagCollectionJob, ProviderQuotaUsage


@skipUnless(importlib.util.find_spec("recommendations.services.bounded_collection_planner"),
            "CPU foundation is absent in this checkout; run in the isolated 76e2 snapshot")
@override_settings(TAG_COLLECTION_BOUNDED_PLANNER_ENABLED=True, TAG_COLLECTION_REFILL_LIMIT=3,
                   TAG_COLLECTION_SCAN_PAGE=5, TAG_COLLECTION_DAILY_API_LIMIT=100,
                   TAG_COLLECTION_QUOTA_PERCENT=90, TAG_COLLECTION_PLANNER_COOLDOWN_SECONDS=60)
class BoundedCollectionTelemetryTests(TestCase):
    def setUp(self):
        from recommendations.models import CollectionPlannerState
        from recommendations.services.bounded_collection_planner import plan_bounded_jobs
        self.state_model = CollectionPlannerState
        self.plan_function = plan_bounded_jobs
        self.logger_patch = patch("recommendations.services.collection_telemetry.logger.info")
        self.logger_patch.start()
        self.addCleanup(self.logger_patch.stop)

    def place(self, index, *, region="서울특별시", category="cafe"):
        return Place.objects.create(name=f"계측 fixture {index}", category=category,
                                    address=region, lat=37, lng=127,
                                    source="telemetry", external_id=str(index))

    def plan(self, **kwargs):
        return self.plan_function(cycle_date=timezone.localdate(), place_limit=3,
                                  provider="naver_search", mode="balanced", categories=("cafe",),
                                  regions=(("서울특별시", ("서울특별시",)),), dry_run=False, **kwargs)

    def test_recent_category_and_region_losses_are_counted_per_considered_visit(self):
        old = self.place(1)
        PlaceTagCollectionJob.objects.create(place=old, cycle_date=timezone.localdate(), status="completed")
        self.place(2, category="restaurant")
        self.place(3, region="부산광역시")
        self.place(4)
        result = self.plan()
        counts = result["telemetry"]["reasons"]
        self.assertEqual(counts["considered"], 4)
        self.assertEqual((counts["recent"], counts["category_mismatch"], counts["region_mismatch"]), (1, 1, 1))
        self.assertEqual(result["places"], 1)
        self.assertEqual(result["telemetry"]["scanned"], 4)

    def test_quota_deferral_is_reported_without_scan(self):
        self.place(1)
        ProviderQuotaUsage.objects.create(provider="naver_search", usage_date=timezone.localdate(), request_count=90)
        result = self.plan()
        self.assertEqual(result["telemetry"]["reasons"]["quota_budget"], 1)
        self.assertEqual(result["scanned"], 0)

    def test_cooldown_is_distinct_from_empty_candidate_pool(self):
        self.place(1)
        self.plan()
        result = self.plan()
        self.assertEqual(result["telemetry"]["reasons"]["cooldown"], 1)
        self.assertEqual(result["scanned"], 0)

    def test_bounded_router_emits_one_planner_event(self):
        from recommendations.management.commands.plan_daily_tag_collection import plan_daily_jobs
        self.place(1)
        with patch("recommendations.services.collection_telemetry.emit_event") as emit:
            plan_daily_jobs(cycle_date=timezone.localdate(), place_limit=3,
                            categories=("cafe",), regions=("서울특별시",), dry_run=True)
        self.assertEqual(emit.call_count, 1)
        self.assertEqual(emit.call_args.args[1]["planner_path"], "bounded")

    @override_settings(TAG_COLLECTION_PLANNER_WALL_SECONDS=-1)
    def test_deadline_emits_loss_and_preserves_rollback(self):
        self.place(1)
        result = self.plan()
        self.assertEqual(result["telemetry"]["reasons"]["deadline_or_sql_timeout"], 1)
        self.assertEqual(result["places"], 0)
        self.assertFalse(PlaceTagCollectionJob.objects.exists())
        self.assertEqual(self.state_model.objects.get().cursor, 0)

    @override_settings(TAG_COLLECTION_DAILY_PLACE_LIMIT=2)
    def test_region_cap_is_counted_only_for_rows_matching_capped_region(self):
        old = self.place(1)
        self.place(2)
        PlaceTagCollectionJob.objects.create(place=old, cycle_date=timezone.localdate(),
                                            context={"region": "서울특별시", "category": "cafe"})
        result = self.plan_function(cycle_date=timezone.localdate(), place_limit=3,
                                   provider="naver_search", mode="bootstrap", categories=("cafe",),
                                   regions=(("서울특별시", ("서울특별시",)), ("부산광역시", ("부산광역시",))),
                                   region_priority_weights={"서울특별시": 1, "부산광역시": 1}, dry_run=False)
        self.assertEqual(result["telemetry"]["reasons"]["region_cap"], 1)
        self.assertEqual(result["places"], 0)

    @override_settings(TAG_COLLECTION_DAILY_PLACE_LIMIT=2)
    def test_category_cap_has_distinct_counter(self):
        old = self.place(1)
        self.place(2)
        PlaceTagCollectionJob.objects.create(place=old, cycle_date=timezone.localdate(),
                                            context={"region": "서울특별시", "category": "cafe"})
        result = self.plan_function(cycle_date=timezone.localdate(), place_limit=3,
                                   provider="naver_search", mode="bootstrap", categories=("cafe", "library"),
                                   regions=(("서울특별시", ("서울특별시",)),), dry_run=False)
        self.assertEqual(result["telemetry"]["reasons"]["category_cap"], 1)
        self.assertEqual(result["places"], 0)
