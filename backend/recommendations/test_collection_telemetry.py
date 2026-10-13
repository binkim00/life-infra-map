from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from recommendations.management.commands.process_place_tag_collection_jobs import process_jobs
from recommendations.management.commands.recover_tag_collection_jobs import recover_stale_jobs
from recommendations.management.commands.report_daily_collection import build_daily_collection_report
from recommendations.models import EvidenceReview, Place, PlaceTag, PlaceTagCollectionJob, PlaceTagEvidence, ProviderQuotaUsage, Tag
from recommendations.services.collection_telemetry import extraction_counts, observed_sleep
from recommendations.management.commands.summarize_collection_metrics import summarize


class CollectionEventTests(SimpleTestCase):
    def test_cumulative_reducer_sums_only_allowed_numeric_events(self):
        import json
        event = {"component": "planner", "recorded_at": "2026-10-12T15:00:00+00:00",
                 "places": 2, "reasons": {"recent": 3, "private label": 99}, "source_text": "secret"}
        result = summarize(["collection_metrics " + json.dumps(event)] * 2 + ["unrelated private log"])
        self.assertEqual(result["ignored_lines"], 1)
        group = result["groups"][0]
        self.assertEqual(group["date"], "2026-10-13")
        self.assertEqual(group["totals"], {"events": 2, "places": 4, "reasons.recent": 6})
        self.assertNotIn("private", str(result))
        self.assertNotIn("secret", str(result))

    def test_numeric_extraction_event_excludes_source_text_and_unrecognized_labels(self):
        counts = extraction_counts([{"actual_query": "private query", "results": [{
            "title": "private title", "identity_matched": True,
            "rejection_reason": "secret-value", "extractions": [
                {"polarity": "unknown", "strength": "WEAK", "positive_terms": ["private text"]},
                {"polarity": "negative", "strength": "CONTRADICTING"},
            ],
        }]}])
        self.assertEqual(counts["search_results"], 1)
        self.assertEqual(counts["identity_matches"], 1)
        self.assertEqual(counts["polarity_unknown"], 1)
        self.assertEqual(counts["strength_CONTRADICTING"], 1)
        self.assertNotIn("private", str(counts))
        self.assertNotIn("secret", str(counts))

    @patch("recommendations.services.collection_telemetry.emit_event")
    @patch("recommendations.services.collection_telemetry.time.sleep")
    @patch("recommendations.services.collection_telemetry.time.monotonic", side_effect=[10, 12.5])
    def test_observed_wait_reports_actual_duration_and_date_boundary(self, clock, sleep, event):
        with patch("recommendations.services.collection_telemetry.timezone.localdate", side_effect=[
            datetime(2026, 10, 12).date(), datetime(2026, 10, 13).date(),
        ]):
            observed_sleep(2, component="worker", reason="empty_queue")
        sleep.assert_called_once_with(2)
        metrics = event.call_args.args[1]
        self.assertEqual(metrics["actual_sleep_ms"], 2500)
        self.assertEqual(metrics["start_date"], "2026-10-12")
        self.assertEqual(metrics["end_date"], "2026-10-13")


@override_settings(TIME_ZONE="Asia/Seoul", TAG_COLLECTION_STRUCTURED_FIRST=False,
                   TAG_COLLECTION_DAILY_API_LIMIT=100, TAG_COLLECTION_QUOTA_PERCENT=90,
                   TAG_COLLECTION_RATE_LIMIT_ENABLED=False)
class CollectionTelemetryTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 12, 14, 59, 59, tzinfo=dt_timezone.utc)
        self.clock_patch = patch("django.utils.timezone.now", side_effect=lambda: self.now)
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.event_patch = patch("recommendations.services.collection_telemetry.logger.info")
        self.event_patch.start()
        self.addCleanup(self.event_patch.stop)
        self.place = Place.objects.create(name="계측 카페", category="cafe", address="부산광역시",
                                          lat=35.1, lng=129.1, source="test", external_id="telemetry")
        self.tag = Tag.objects.create(name="조용함")
        self.day = timezone.localdate(self.now)

    def job(self, **fields):
        return PlaceTagCollectionJob.objects.create(place=self.place, cycle_date=self.day,
                                                    planned_requests=2, requested_tags=[self.tag.name], **fields)

    def evidence(self, *, polarity="positive", active=True, review=None):
        row = PlaceTagEvidence.objects.create(place=self.place, tag=self.tag, source="naver_blog_search",
                                             polarity=polarity, expires_at=self.now + timedelta(days=1 if active else -1))
        if review:
            EvidenceReview.objects.create(evidence=row, status=review)
        return row

    def test_midnight_processing_releases_original_reservation_and_reports_calendar_completion(self):
        job = self.job()
        def collect(*args):
            self.now += timedelta(seconds=2)
            return {"requests": 2, "evidences": [], "error": "insufficient_evidence",
                    "miss_reason": "IDENTITY_MISMATCH"}
        result = process_jobs(limit=1, collector=collect)
        job.refresh_from_db()
        self.assertEqual(result["insufficient"], 1)
        self.assertEqual(job.status, "completed")
        old = ProviderQuotaUsage.objects.get(usage_date=self.day)
        self.assertEqual((old.reserved_count, old.request_count, old.success_count), (0, 2, 2))
        self.assertFalse(ProviderQuotaUsage.objects.filter(usage_date=self.day + timedelta(days=1)).exists())
        self.assertEqual(job.stats["telemetry"]["reservation_date"], self.day.isoformat())
        self.assertEqual(job.stats["telemetry"]["settlement_date"], self.day.isoformat())
        self.assertEqual(job.stats["telemetry"]["completed_date"], (self.day + timedelta(days=1)).isoformat())
        self.assertIn("collector_ms", job.stats["telemetry"]["timings_ms"])
        before = build_daily_collection_report(self.day)
        after = build_daily_collection_report(self.day + timedelta(days=1))
        self.assertEqual(before["naver"]["completed_jobs"], 1)
        self.assertEqual(before["naver"]["useful_jobs"], 0)
        self.assertEqual(before["calendar_completion"]["completed_jobs"], 0)
        self.assertEqual(after["naver"]["planned_jobs"], 0)
        self.assertEqual(after["calendar_completion"]["instrumented_completed_jobs"], 1)
        self.assertEqual(after["calendar_completion"]["by_cycle_date"], {self.day.isoformat(): 1})

    def test_slow_collector_duration_is_measured_without_wall_clock_estimation(self):
        job = self.job()
        monotonic = [10.0]
        def collect(*args):
            monotonic[0] += 2.5
            return {"requests": 1, "error": "insufficient_evidence"}
        with patch("recommendations.management.commands.process_place_tag_collection_jobs.time.monotonic",
                   side_effect=lambda: monotonic[0]):
            process_jobs(limit=1, collector=collect)
        job.refresh_from_db()
        timings = job.stats["telemetry"]["timings_ms"]
        self.assertEqual(timings["collector_ms"], 2500)
        self.assertEqual(timings["processing_ms"], 2500)
        self.assertEqual(timings["structured_ms"], 0)

    def test_materialization_crash_resumes_checkpoint_across_midnight_without_call_or_double_quota(self):
        job = self.job()
        saved = self.evidence(review="approved")
        payload = {"requests": 3, "evidences": [{
            "tag_name": self.tag.name, "source_url": "https://example.org/synthetic",
            "polarity": "positive", "evidence_summary": "synthetic fixture",
        }]}
        target = "recommendations.management.commands.process_place_tag_collection_jobs.save_place_candidate_evidence"
        with patch(target, side_effect=RuntimeError("synthetic materialization crash")):
            with self.assertRaises(RuntimeError):
                process_jobs(limit=1, worker_id="original", collector=lambda *args: payload)
        job.refresh_from_db()
        self.assertEqual(job.status, "processing")
        self.assertIsNotNone(job.result_checkpoint)
        self.assertIsNotNone(job.quota_settled_at)
        self.assertEqual(job.result_checkpoint["_collection_telemetry"]["attempt"], 1)
        self.now += timedelta(minutes=31)
        self.assertEqual(recover_stale_jobs(), 1)
        with patch(target, return_value=(saved, False)), patch(
            "recommendations.management.commands.process_place_tag_collection_jobs.collect_naver_place_evidence"
        ) as collector:
            process_jobs(limit=1, worker_id="recovered")
        collector.assert_not_called()
        job.refresh_from_db()
        self.assertIsNone(job.result_checkpoint)
        self.assertEqual(job.status, "completed")
        telemetry = job.stats["telemetry"]
        self.assertTrue(telemetry["resumed_checkpoint"])
        self.assertEqual(telemetry["checkpoint_collection"]["attempt"], 1)
        self.assertEqual(telemetry["timings_ms"]["collector_ms"], 0)
        self.assertEqual(telemetry["reservation_date"], self.day.isoformat())
        self.assertEqual(telemetry["completed_date"], (self.day + timedelta(days=1)).isoformat())
        quota = ProviderQuotaUsage.objects.get(usage_date=self.day)
        self.assertEqual((quota.request_count, quota.reserved_count), (3, 0))
        self.assertEqual(ProviderQuotaUsage.objects.get(usage_date=self.day + timedelta(days=1)).request_count, 0)

    def test_legacy_checkpoint_is_marked_unmeasured_without_fabricated_original_timing(self):
        from recommendations.management.commands.process_place_tag_collection_jobs import claim_next_job, settle_quota
        job = self.job()
        claimed, _ = claim_next_job(worker_id="original")
        settle_quota(claimed, 1, succeeded=True)
        PlaceTagCollectionJob.objects.filter(pk=job.pk).update(
            result_checkpoint={"requests": 1, "evidences": [], "error": "insufficient_evidence"},
            locked_at=self.now - timedelta(hours=1),
        )
        recover_stale_jobs()
        process_jobs(limit=1, collector=lambda *args: self.fail("must use checkpoint"))
        job.refresh_from_db()
        telemetry = job.stats["telemetry"]
        self.assertTrue(telemetry["checkpoint_collection_unmeasured"])
        self.assertEqual(telemetry["checkpoint_collection"], {})
        self.assertEqual(ProviderQuotaUsage.objects.get().request_count, 1)
        metrics = build_daily_collection_report(self.day)["naver"]["cycle_metrics"]
        self.assertEqual(metrics["checkpoint_resumed_jobs"], 1)
        self.assertEqual(metrics["checkpoint_original_timing_unmeasured_jobs"], 1)

    def test_fenced_collector_result_cannot_write_checkpoint_or_completion_metrics(self):
        job = self.job()
        def lost_lease(*args):
            PlaceTagCollectionJob.objects.filter(pk=job.pk).update(worker_id="another-worker")
            return {"requests": 1, "evidences": [], "error": "insufficient_evidence"}
        process_jobs(limit=1, worker_id="original", collector=lost_lease)
        job.refresh_from_db()
        self.assertIsNone(job.result_checkpoint)
        self.assertIsNone(job.quota_settled_at)
        self.assertEqual(job.stats, {})

    def test_quality_at_save_separates_reused_expired_negative_pending_and_accepted(self):
        job = self.job()
        saved = [self.evidence(active=False, review="approved"),
                 self.evidence(review="pending"), self.evidence(review="approved_limited"),
                 self.evidence(polarity="negative", review="approved"), self.evidence(review="approved")]
        evidence = {"tag_name": self.tag.name, "source_url": "https://example.org/test",
                    "polarity": "positive", "evidence_summary": "synthetic fixture"}
        with patch("recommendations.management.commands.process_place_tag_collection_jobs.save_place_candidate_evidence",
                   side_effect=[(row, False) for row in saved]):
            process_jobs(limit=1, collector=lambda *args: {"requests": 1, "evidences": [evidence] * 5})
        job.refresh_from_db()
        self.assertEqual(job.stats["new_evidences"], 0)
        self.assertEqual(job.stats["telemetry"]["quality_at_save"], {
            "expired": 1, "reused": 5, "active_positive": 3,
            "active_accepted": 2, "active_positive_accepted": 1,
        })

    def test_report_keeps_current_validity_approval_and_new_verified_separate(self):
        self.evidence(active=False, review="approved")
        self.evidence(review="pending")
        self.evidence(review="approved_limited")
        self.evidence(polarity="negative", review="approved")
        self.evidence(review="approved")
        self.evidence()  # Existing policy allows unreviewed evidence.
        PlaceTag.objects.create(place=self.place, tag=self.tag, source="web_evidence", status="candidate")
        report = build_daily_collection_report(self.day)
        naver = report["naver"]
        self.assertEqual(naver["new_evidence_rows"], 6)
        self.assertEqual(naver["active_rows"], 5)
        self.assertEqual(naver["expired_rows"], 1)
        self.assertEqual(naver["active_positive_rows"], 4)
        self.assertEqual(naver["active_accepted_rows"], 3)
        self.assertEqual(naver["active_positive_accepted_rows"], 2)
        self.assertEqual(report["aggregate_tags"]["new_verified_place_tags"], 0)
        self.assertIsNone(report["aggregate_tags"]["existing_tag_status_transitions"])

    def test_legacy_completion_has_explicit_proxy_and_missing_telemetry(self):
        self.job(status="completed", stats={"evidences": 1})
        report = build_daily_collection_report(self.day)
        self.assertEqual(report["calendar_completion"]["legacy_updated_at_proxy_jobs"], 1)
        self.assertEqual(report["naver"]["cycle_metrics"]["unmeasured_jobs"], 1)
        self.assertEqual(report["naver"]["cycle_metrics"]["last_attempt_timings_ms"], {})

    def test_retry_attempt_durations_are_retained_and_not_counted_as_completion(self):
        job = self.job()
        process_jobs(limit=1, collector=lambda *args: {"requests": 1, "error": "request_failed"})
        job.refresh_from_db()
        self.assertIsNone(job.stats["telemetry"]["completed_date"])
        job.next_attempt_at = None
        job.save(update_fields=["next_attempt_at"])
        process_jobs(limit=1, collector=lambda *args: {"requests": 1, "error": "insufficient_evidence"})
        job.refresh_from_db()
        self.assertEqual([row["attempt"] for row in job.stats["attempt_metrics"]], [1, 2])
        quota = ProviderQuotaUsage.objects.get(usage_date=self.day)
        self.assertEqual((quota.request_count, quota.reserved_count, quota.failed_count), (2, 0, 1))

    def test_completion_date_survives_later_non_processing_update(self):
        job = self.job()
        process_jobs(limit=1, collector=lambda *args: {"requests": 1, "error": "insufficient_evidence"})
        self.now += timedelta(days=1)
        job.refresh_from_db()
        job.priority += 1
        job.save(update_fields=["priority", "updated_at"])
        self.assertEqual(build_daily_collection_report(self.day)["calendar_completion"]["instrumented_completed_jobs"], 1)
        self.assertEqual(build_daily_collection_report(self.day + timedelta(days=1))["calendar_completion"]["completed_jobs"], 0)
