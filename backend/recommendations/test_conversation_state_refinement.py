from django.test import SimpleTestCase, override_settings

from recommendations.services.ai_intent_planner import build_ai_intent_plan, to_search_plan
from recommendations.services.ai_search_orchestrator import (
    _enforce_required_result_policy,
    _required_evidence_conditions,
    _structured_conversation_action_plan,
)


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

    def test_family_gathering_is_a_preference_not_a_required_party_feature(self):
        plan = build_ai_intent_plan("해운대역 근처 모임하기 좋은 식당")
        party = next(
            condition
            for condition in plan["frame"]["structured_conditions"]
            if condition["label"] == "단체 이용"
        )

        self.assertFalse(party["required"])
        self.assertNotIn("단체 이용", _required_evidence_conditions(plan["frame"]))

    def test_explicit_party_seating_requirement_remains_required(self):
        plan = build_ai_intent_plan("해운대역 단체석 필수 식당")
        party = next(
            condition
            for condition in plan["frame"]["structured_conditions"]
            if condition["label"] == "단체 이용"
        )

        self.assertTrue(party["required"])
        self.assertIn("단체 이용", _required_evidence_conditions(plan["frame"]))

    def test_complete_new_search_resets_incompatible_clarification_frame(self):
        context = self._context()
        context["is_clarification_followup"] = True
        context["pending_clarification_frame"] = context["search_plan"]["place_intent_frame"]

        plan = build_ai_intent_plan("서면역 근처 조용한 카페", previous_context=context)

        self.assertEqual(plan["frame"]["anchor_location"], "서면역")
        self.assertEqual(plan["frame"]["candidate_category_codes"], ["cafe"])
        self.assertEqual(plan["frame"]["target_objects"], ["카페"])
        self.assertNotIn("부모님 동행", plan["frame"]["constraints"])
        self.assertEqual(
            plan["ai_debug"]["planner"]["reason"],
            "complete_new_search_resets_previous_frame",
        )

    def test_structured_relax_action_changes_only_the_selected_condition(self):
        frame = {
            **self._context()["search_plan"]["place_intent_frame"],
            "structured_conditions": [
                {"label": "단체 이용", "type": "party", "required": True},
                {"label": "주차 가능", "type": "facility", "required": True},
            ],
        }
        plan, action_type = _structured_conversation_action_plan(
            {
                "conversation_action": {
                    "type": "relax_constraints",
                    "condition_labels": ["단체 이용"],
                },
            },
            {"pending_clarification_frame": frame},
            "단체 이용 조건 빼기",
        )

        self.assertEqual(action_type, "relax_constraints")
        self.assertEqual(plan["frame"]["anchor_location"], "서면")
        self.assertEqual(_required_evidence_conditions(plan["frame"]), ["주차 가능"])
        self.assertIn("단체 이용", plan["frame"]["preferred_features"])

    def test_structured_show_unverified_action_bypasses_only_the_evidence_gate(self):
        frame = {
            **self._context()["search_plan"]["place_intent_frame"],
            "structured_conditions": [
                {"label": "주차 가능", "type": "facility", "required": True},
            ],
        }
        plan, action_type = _structured_conversation_action_plan(
            {"conversation_action": {"type": "show_unverified"}},
            {"pending_clarification_frame": frame},
            "미확인 후보도 보기",
        )
        candidates = [{"id": "db:1", "missing_conditions": ["주차 가능"]}]

        results, required, needs_question = _enforce_required_result_policy(
            candidates,
            plan["frame"],
            "미확인 후보도 보기",
            allow_unverified=action_type == "show_unverified",
        )

        self.assertEqual(results, candidates)
        self.assertEqual(required, ["주차 가능"])
        self.assertFalse(needs_question)

    def test_local_boundaries_do_not_depend_on_external_ai(self):
        finance = build_ai_intent_plan("비트코인 지금 사도 될까")
        unsafe = build_ai_intent_plan("불법적인 장소 알려줘")

        self.assertEqual(finance["action"], "out_of_scope")
        self.assertEqual(unsafe["action"], "blocked")

    def test_rain_shelter_phrase_asks_location_then_searches(self):
        first = build_ai_intent_plan("비 피하면서 앉아 있을 곳")

        self.assertEqual(first["action"], "ask_clarification")
        self.assertEqual(first["frame"]["situation"], "weather_shelter")
        self.assertEqual(first["frame"]["location_mode"], "clarification_required")
        self.assertEqual(to_search_plan(first)["scenario"], "waiting_place")

        second = build_ai_intent_plan("서면", previous_context={
            "place_intent_frame": first["frame"],
            "is_clarification_followup": True,
        })
        self.assertEqual(second["action"], "search")
        self.assertEqual(second["frame"]["anchor_location"], "서면")
        self.assertIn("비 피하기", second["frame"]["constraints"])
        self.assertIn("실내", second["frame"]["constraints"])

    def test_ambiguous_result_reference_without_context_asks_clarification(self):
        plan = build_ai_intent_plan("거기 말고 더 조용한 데")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertIn("이전 검색 결과", plan["clarification"]["question"])

    def test_generic_quiet_request_asks_for_purpose(self):
        plan = build_ai_intent_plan("조용한 곳 추천해줘")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertIn("무엇을 하려는지", plan["clarification"]["question"])
        self.assertIn("휴식", [option["label"] for option in plan["clarification"]["options"]])

    def test_followup_keeps_situation_and_category_codes(self):
        context = self._context()
        frame = context["search_plan"]["place_intent_frame"]
        frame["situation"] = "work"
        frame["candidate_category_codes"] = ["cafe"]
        frame["target_objects"] = ["카페"]
        frame["candidate_place_types"] = ["카페"]

        plan = build_ai_intent_plan("좀 더 가까운 데", previous_context=context)

        self.assertEqual(plan["frame"]["situation"], "work")
        self.assertEqual(plan["frame"]["candidate_category_codes"], ["cafe"])
        self.assertEqual(plan["frame"]["ranking_policy"], "distance_first")

    def test_quiet_purpose_answer_turns_clarification_into_search(self):
        first = build_ai_intent_plan("조용한 곳 추천해줘")
        context = {
            "place_intent_frame": first["frame"],
            "is_clarification_followup": True,
            "previous_user_query": "조용한 곳 추천해줘",
        }

        plan = build_ai_intent_plan("혼자 쉬고 싶어", previous_context=context)

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["frame"]["situation"], "quiet_rest")
        self.assertIn("조용함", plan["frame"]["constraints"])
        self.assertIn("혼자 이용", plan["frame"]["constraints"])
        self.assertEqual(to_search_plan(plan)["scenario"], "waiting_place")

    def test_location_only_answer_updates_pending_place_frame(self):
        context = self._context()
        frame = context["search_plan"]["place_intent_frame"]
        frame["location_mode"] = "clarification_required"
        frame["anchor_location"] = ""
        context["is_clarification_followup"] = True

        plan = build_ai_intent_plan("서면", previous_context=context)

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["frame"]["location_mode"], "explicit")
        self.assertEqual(plan["frame"]["anchor_location"], "서면")

    def test_location_inside_weather_sentence_and_indoor_condition_are_kept(self):
        plan = build_ai_intent_plan("비 오는 날 센텀에서 아이와 갈 실내 장소")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["frame"]["anchor_location"], "센텀")
        self.assertIn("실내", plan["frame"]["constraints"])
