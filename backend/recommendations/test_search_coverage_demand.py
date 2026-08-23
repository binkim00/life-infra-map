from django.test import TestCase

from recommendations.models import Place, PlaceInteractionEvent
from recommendations.services.bootstrap_priority import priority_context
from recommendations.services.search_coverage_demand import record_search_coverage_demand


class SearchCoverageDemandTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="서면 작업 카페",
            category="cafe",
            address="부산광역시 부산진구 서면로 1",
            lat=35.157,
            lng=129.059,
            source="test",
            external_id="coverage-demand-cafe",
        )

    def test_sparse_search_records_only_normalized_demand(self):
        event = record_search_coverage_demand({
            "decision_action": "search",
            "result_count": 0,
            "scenario": "ai_place_search",
            "search_plan": {"scenario": "work_cafe"},
            "place_intent_frame": {
                "anchor_location": "서면",
                "candidate_category_codes": ["cafe"],
                "target_objects": [{"value": "노트북 카페"}],
                "constraints": [{"value": "콘센트 있음"}],
            },
        }, session_key="raw-anonymous-token", search_id="session:1")

        self.assertEqual(event.query, "")
        self.assertNotEqual(event.session_key, "raw-anonymous-token")
        self.assertEqual(event.context["location_hint"], "서면")
        self.assertEqual(event.context["category_codes"], ["cafe"])
        self.assertEqual(event.context["result_count"], 0)
        self.assertIn("콘센트있음", event.requested_tags)

    def test_abundant_search_does_not_create_coverage_signal(self):
        result = record_search_coverage_demand({
            "decision_action": "search",
            "result_count": 10,
            "place_intent_frame": {"candidate_category_codes": ["cafe"]},
        })

        self.assertIsNone(result)
        self.assertFalse(PlaceInteractionEvent.objects.exists())

    def test_sparse_regional_demand_boosts_matching_collection_candidate(self):
        other = Place.objects.create(
            name="해운대 카페",
            category="cafe",
            address="부산광역시 해운대구 해운대로 1",
            lat=35.16,
            lng=129.16,
            source="test",
            external_id="coverage-demand-other",
        )
        record_search_coverage_demand({
            "decision_action": "search",
            "result_count": 0,
            "place_intent_frame": {
                "anchor_location": "서면",
                "candidate_category_codes": ["cafe"],
                "constraints": ["콘센트 있음"],
            },
        })

        contexts = priority_context([self.place, other])

        self.assertEqual(contexts[self.place.id]["components"]["search_coverage_demand"], 3)
        self.assertEqual(contexts[other.id]["components"]["search_coverage_demand"], 0)
        self.assertIn("콘센트있음", contexts[self.place.id]["targeted_tags"])
        self.assertEqual(contexts[self.place.id]["adaptive_reason"], "search_coverage_demand")
