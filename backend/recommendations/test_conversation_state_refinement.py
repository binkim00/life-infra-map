from django.test import SimpleTestCase, override_settings

from recommendations.services.ai_intent_planner import build_ai_intent_plan


@override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
class ConversationStateRefinementTests(SimpleTestCase):
    def _context(self):
        return {
            "search_plan": {
                "place_intent_frame": {
                    "location_mode": "explicit",
                    "anchor_location": "서면",
                    "target_objects": ["식당"],
                    "candidate_place_types": ["식당", "음식점"],
                    "result_match_terms": ["식당", "음식점"],
                    "constraints": ["부모님 동행"],
                    "exclusions": [],
                    "primary_search_queries": ["식당"],
                    "candidate_category_codes": ["restaurant"],
                    "ranking_policy": "evidence_first",
                }
            }
        }

    def test_accumulates_parking_and_quiet_constraints_across_turns(self):
        first = build_ai_intent_plan("그중에서 주차되는 곳만", previous_context=self._context())
        second_context = {"search_plan": {"place_intent_frame": first["frame"]}}
        second = build_ai_intent_plan("더 조용한 데", previous_context=second_context)

        self.assertEqual(first["action"], "search")
        self.assertIn("주차 가능", first["frame"]["constraints"])
        self.assertEqual(second["frame"]["anchor_location"], "서면")
        self.assertIn("주차 가능", second["frame"]["constraints"])
        self.assertIn("조용함", second["frame"]["constraints"])

    def test_preserves_target_while_adding_exclusion(self):
        plan = build_ai_intent_plan("그중에서 술집 분위기는 빼줘", previous_context=self._context())

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["frame"]["target_objects"], ["식당"])
        self.assertIn("술집", plan["frame"]["exclusions"])

    def test_adds_library_as_alternative_work_place(self):
        context = self._context()
        frame = context["search_plan"]["place_intent_frame"]
        frame["target_objects"] = ["카페"]
        frame["candidate_place_types"] = ["카페", "작업 카페"]
        frame["candidate_category_codes"] = ["cafe"]

        plan = build_ai_intent_plan("카페 말고 도서관도 괜찮아", previous_context=context)

        self.assertIn("도서관", plan["frame"]["candidate_place_types"])
        self.assertIn("library", plan["frame"]["candidate_category_codes"])

    def test_distance_refinement_keeps_existing_constraints(self):
        context = self._context()
        context["search_plan"]["place_intent_frame"]["constraints"].append("주차 가능")

        plan = build_ai_intent_plan("좀 더 가까운 데", previous_context=context)

        self.assertEqual(plan["frame"]["ranking_policy"], "distance_first")
        self.assertIn("주차 가능", plan["frame"]["constraints"])

    def test_general_family_meal_uses_deterministic_restaurant_plan(self):
        plan = build_ai_intent_plan("광안리에서 가족끼리 저녁 먹을 곳")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["frame"]["candidate_category_codes"], ["restaurant"])
        self.assertIn("가족 식사", plan["frame"]["constraints"])

    def test_local_boundaries_do_not_depend_on_external_ai(self):
        finance = build_ai_intent_plan("비트코인 지금 사도 될까")
        unsafe = build_ai_intent_plan("불법적인 장소 알려줘")

        self.assertEqual(finance["action"], "out_of_scope")
        self.assertEqual(unsafe["action"], "blocked")

    def test_rain_shelter_phrase_is_searchable(self):
        plan = build_ai_intent_plan("비 피하면서 앉아 있을 곳")

        self.assertEqual(plan["action"], "search")
        self.assertIn("실내 쉬어갈 곳", plan["frame"]["target_objects"])

    def test_ambiguous_result_reference_without_context_asks_clarification(self):
        plan = build_ai_intent_plan("거기 말고 더 조용한 데")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertIn("이전 검색 결과", plan["clarification"]["question"])

    def test_generic_quiet_request_asks_for_purpose(self):
        plan = build_ai_intent_plan("조용한 곳 추천해줘")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertIn("무엇을 하려는지", plan["clarification"]["question"])
