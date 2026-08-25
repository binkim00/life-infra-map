from collections import Counter

from django.test import TestCase

from recommendations.management.commands.prepare_codex_web_research import select_places
from recommendations.models import Place, TagEnrichmentRequest
from recommendations.services.launch_evidence_priority import prioritize_launch_evidence


class LaunchEvidencePriorityTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="서면 출시카페",
            category="cafe",
            address="부산광역시 부산진구 중앙대로 1",
            lat=35.1579,
            lng=129.0592,
            source="semas",
            external_id="launch-priority-cafe",
        )

    def payload(self):
        return {
            "created_at": "2026-08-25T05:00:00+09:00",
            "results": [{
                "id": "cafe_seomyeon_work",
                "case_id": "cafe_seomyeon_work",
                "frame": {"constraints": ["조용함", "콘센트있음"]},
                "top_results": [{
                    "rank": 1,
                    "id": str(self.place.id),
                    "name": self.place.name,
                    "category": "cafe",
                    "address": self.place.address,
                    "source": "db",
                    "result_tier": "best_available",
                    "missing_conditions": ["조용함", "콘센트있음"],
                    "unverified_conditions": [],
                }],
            }],
        }

    def test_creates_idempotent_place_tag_demands_from_top_results(self):
        first = prioritize_launch_evidence(self.payload())
        second = prioritize_launch_evidence(self.payload())

        self.assertEqual(first["requests_created"], 2)
        self.assertEqual(second["requests_idempotent"], 2)
        self.assertEqual(TagEnrichmentRequest.objects.count(), 2)
        request = TagEnrichmentRequest.objects.get(place=self.place, tag_name="조용함")
        self.assertEqual(request.context["launch_quality"]["source"], "busan_launch_quality")

    def test_launch_demand_allows_codex_selection_without_previous_naver_identity_job(self):
        prioritize_launch_evidence(self.payload())

        rows = select_places("cafe", 1, Counter())

        self.assertEqual(rows[0]["place"], self.place)
        self.assertIn(rows[0]["tag"], {"조용함", "콘센트있음"})
        self.assertTrue(rows[0]["launch_demand"])

    def test_external_results_do_not_create_local_place_demands(self):
        payload = self.payload()
        payload["results"][0]["top_results"][0]["source"] = "kakao"

        report = prioritize_launch_evidence(payload)

        self.assertEqual(report["demand_places"], 0)
        self.assertEqual(report["unresolved_results"], 1)
