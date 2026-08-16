from django.test import SimpleTestCase, override_settings

from recommendations.services.ai_intent_planner import build_ai_intent_plan


@override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
class LocalCompositionalIntentTests(SimpleTestCase):
    def assert_local_search(self, query, *, categories, tags, anchor=""):
        plan = build_ai_intent_plan(query)
        self.assertEqual(plan["action"], "search")
        frame = plan["frame"]
        self.assertTrue(set(categories).issubset(set(frame["candidate_category_codes"])))
        self.assertTrue(set(tags).issubset(set(frame["constraints"])))
        if anchor:
            self.assertEqual(frame["anchor_location"], anchor)
        self.assertEqual(plan["ai_debug"]["planner"]["call_count"], 0)

    def test_quiet_laptop_work_uses_canonical_features(self):
        self.assert_local_search(
            "조용히 노트북 작업할 곳",
            categories={"cafe", "library"},
            tags={"조용함", "노트북작업", "작업하기좋음"},
        )

    def test_free_place_near_station_preserves_location(self):
        self.assert_local_search(
            "부산역 근처 무료로 이용 가능한 곳",
            categories={"library", "city_park", "tourism"},
            tags={"무료이용"},
            anchor="부산역",
        )

    def test_late_night_place_uses_night_operation_feature(self):
        self.assert_local_search(
            "밤 늦게 이용 가능한 곳",
            categories={"cafe", "restaurant", "library", "parking", "toilet", "tourism"},
            tags={"야간운영"},
        )

    def test_parking_tourism_uses_existing_canonical_tag(self):
        self.assert_local_search(
            "주차 가능한 관광지",
            categories={"tourism"},
            tags={"주차가능"},
        )
