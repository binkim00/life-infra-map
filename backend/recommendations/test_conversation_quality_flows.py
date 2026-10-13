"""Sixty reproducible multi-turn flows using fixed place evidence."""
from copy import deepcopy
from unittest.mock import Mock, patch
import requests
from django.test import SimpleTestCase, override_settings
from recommendations.services.ai_intent_planner import build_ai_intent_plan, to_search_plan
from recommendations.services.ai_search_orchestrator import run_ai_search, _enforce_required_result_policy, _condition_supported
from recommendations.services.conversation_patches import patch_frame
from recommendations.services.conversation_sessions import build_previous_context, state_from_search_response, result_references
from recommendations.services.kakao_local import search_places_by_keyword


@override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
class ConversationQualityFlows(SimpleTestCase):
    def exercise_flow(self, region, target, condition, phrase):
        plan = build_ai_intent_plan(f"{region} {target}")
        self.assertEqual(plan["action"], "search")
        frame = patch_frame(phrase, plan["frame"], source_turn=2)[0]
        self.assertIn(condition, frame["required_features"])
        confirmed = {"id": "db:1", "name": "확인 장소", "distance": 500, "verified_tags": [condition], "matched_conditions": [condition], "missing_conditions": []}
        unknown = {"id": "db:2", "name": "미확인 장소", "distance": 300, "matched_conditions": [], "missing_conditions": [condition]}
        conflicted = {**confirmed, "id": "db:3", "hard_gate_violations": [{"status": "CONFLICTED"}]}
        qualified, _, _ = _enforce_required_result_policy([confirmed, unknown, conflicted], frame, phrase)
        self.assertEqual([item["id"] for item in qualified], ["db:1"])
        default, _, _ = _enforce_required_result_policy([unknown], frame, "확인 안 돼도 보여줘")
        self.assertEqual(default, [])
        response = {"decision_action": "search", "results": qualified, "place_intent_frame": frame,
                    "search_plan": to_search_plan({**plan, "frame": frame})}
        state = state_from_search_response(phrase, response)
        with patch("recommendations.services.ai_search_orchestrator.collect_db_candidates") as retrieval:
            selected = run_ai_search({"query": "1번이 좋아", "previous_context": build_previous_context(state)})
            state = state_from_search_response("1번이 좋아", selected, state)
            explanation = run_ai_search({"query": "거기는 왜 추천했어?", "previous_context": build_previous_context(state)})
            self.assertIn("확인 장소", explanation["message"])
            self.assertIn("확인되지 않았습니다", explanation["message"])
            retrieval.assert_not_called()
        saved = deepcopy(state)
        clarification = state_from_search_response("다시 설명", {"decision_action": "ask_clarification", "results": []}, state)
        self.assertEqual(clarification["previous_results"], saved["previous_results"])
        self.assertEqual(clarification["selected_result_key"], saved["selected_result_key"])
        patched = build_ai_intent_plan("1km 안으로", previous_context=build_previous_context(state))
        self.assertEqual(patched["frame"]["anchor_location"], frame["anchor_location"])
        self.assertIn(condition, patched["frame"]["required_features"])
        changed = state_from_search_response("1km 안으로", {**response, "place_intent_frame": patched["frame"]}, state)
        undo = run_ai_search({"query": "방금 조건 되돌려", "previous_context": build_previous_context(changed)})
        restored = state_from_search_response("방금 조건 되돌려", undo, changed)
        self.assertEqual(restored["place_intent_frame"], saved["place_intent_frame"])
        with patch("recommendations.services.ai_search_orchestrator._run_ai_search", return_value=deepcopy(response)):
            excluded = run_ai_search({"query": "1번 빼고 다른 곳", "previous_context": build_previous_context(restored)})
        self.assertEqual(excluded["results"], [])
        self.assertIn("db:1", excluded["excluded_place_keys"])


for ri, region in enumerate(("서면", "해운대", "광안리", "연산동", "서울역", "부산역")):
    for ti, target in enumerate(("카페", "식당")):
        for fi, (condition, phrase) in enumerate((("주차 가능", "주차 필수"), ("콘센트있음", "콘센트 필수"),
                 ("와이파이있음", "와이파이 필수"), ("조용함", "조용한 곳만"), ("단체 이용", "단체석 필수"))):
            def flow(self, r=region, t=target, c=condition, p=phrase):
                self.exercise_flow(r, t, c, p)
            setattr(ConversationQualityFlows, f"test_flow_{ri}_{ti}_{fi}", flow)


class EvidenceAndProviderContracts(SimpleTestCase):
    def test_negative_or_substring_is_not_positive_evidence(self):
        self.assertFalse(_condition_supported("주차", ["주차불가"]))
        self.assertFalse(_condition_supported("반려견 실내동반", ["반려견 실외동반"]))

    def test_external_identity_is_stable_across_queries(self):
        refs = result_references([{"id": "kakao:77:query1", "source": "kakao", "external_id": "77"},
                                  {"id": "kakao:77:query2", "source": "kakao", "external_id": "77"}])
        self.assertEqual(refs[0]["place_key"], refs[1]["place_key"])

    @override_settings(KAKAO_REST_API_KEY="test-key")
    @patch("recommendations.services.kakao_local.requests.get")
    def test_pagination_deduplicates_and_preserves_partial_success(self, get):
        first = Mock(); first.json.return_value = {"documents": [{"id": "1"}, {"id": "2"}], "meta": {"is_end": False}}
        second = Mock(); second.json.return_value = {"documents": [{"id": "2"}, {"id": "3"}], "meta": {"is_end": False}}
        get.side_effect = [first, second, requests.Timeout()]
        data = search_places_by_keyword("카페")
        self.assertEqual([row["id"] for row in data["documents"]], ["1", "2", "3"])
        self.assertEqual(data["provider_status"], "partial")
        self.assertEqual(get.call_args_list[1].kwargs["params"]["page"], 2)

    @override_settings(KAKAO_REST_API_KEY="test-key")
    @patch("recommendations.services.kakao_local.requests.get", side_effect=requests.Timeout())
    def test_initial_provider_error_is_not_real_zero(self, get):
        with self.assertRaises(requests.Timeout):
            search_places_by_keyword("카페")

    def test_unknown_ordinal_never_runs_retrieval(self):
        with patch("recommendations.services.ai_search_orchestrator.collect_db_candidates") as get:
            response = run_ai_search({"query": "9번 주차 가능해?", "previous_context": {"previous_results": []}})
        get.assert_not_called()
        self.assertEqual(response["results"], [])

    def test_compare_preserves_original_ordinals(self):
        state = {"previous_results": result_references([{"id": "db:1", "name": "A"}, {"id": "db:2", "name": "B"}, {"id": "db:3", "name": "C"}])}
        compare = run_ai_search({"query": "1번 3번 비교", "previous_context": build_previous_context(state)})
        next_state = state_from_search_response("1번 3번 비교", compare, state)
        selected = run_ai_search({"query": "2번이 좋아", "previous_context": build_previous_context(next_state)})
        self.assertEqual(selected["results"][0]["name"], "B")

    def test_optional_feature_does_not_become_mandatory(self):
        frame = patch_frame("주차 필수, 콘센트는 있으면 좋아", {"required_features": []})[0]
        self.assertEqual(frame["required_features"], ["주차 가능"])
        self.assertEqual(frame["preferred_features"], ["콘센트있음"])
        results, _, _ = _enforce_required_result_policy([{"matched_conditions": ["주차 가능"], "missing_conditions": []}], frame, "")
        self.assertEqual(len(results), 1)

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_required_accumulation_remove_and_preference_roundtrip(self):
        plan = build_ai_intent_plan("서면 카페")
        frame = plan["frame"]
        for turn, query in enumerate(("주차 필수", "더 가까운 데", "콘센트도 필수"), start=2):
            plan = build_ai_intent_plan(query, previous_context={"place_intent_frame": frame, "turn_count": turn - 1})
            frame = plan["frame"]
        self.assertEqual(set(frame["required_features"]), {"주차 가능", "콘센트있음"})
        self.assertEqual(frame["anchor_location"], "서면")
        frame = build_ai_intent_plan("주차 조건 취소", previous_context={"place_intent_frame": frame})["frame"]
        self.assertEqual(frame["required_features"], ["콘센트있음"])
        frame = build_ai_intent_plan("콘센트는 있으면 좋아", previous_context={"place_intent_frame": frame})["frame"]
        self.assertEqual(frame["required_features"], [])
        self.assertEqual(frame["preferred_features"], ["콘센트있음"])
        frame = build_ai_intent_plan("콘센트 필수", previous_context={"place_intent_frame": frame})["frame"]
        self.assertEqual(frame["required_features"], ["콘센트있음"])

    def test_replacement_then_undo_restores_only_last_change(self):
        old = patch_frame("주차 필수", {"anchor_location": "서면", "target_objects": ["카페"]})[0]
        state = state_from_search_response("주차 필수", {"decision_action": "search", "place_intent_frame": old, "results": []})
        replacement = patch_frame("주차 대신 콘센트", old, source_turn=2)[0]
        self.assertEqual(replacement["required_features"], ["콘센트있음"])
        changed = state_from_search_response("주차 대신 콘센트", {"decision_action": "search", "place_intent_frame": replacement, "results": []}, state)
        response = run_ai_search({"query": "방금 변경 취소", "previous_context": build_previous_context(changed)})
        restored = state_from_search_response("방금 변경 취소", response, changed)
        self.assertEqual(restored["place_intent_frame"]["required_features"], ["주차 가능"])

    def test_explained_place_becomes_pronoun_reference_and_stays_excluded(self):
        frame = {"target_objects": ["카페"], "anchor_location": "서면"}
        state = state_from_search_response("카페 찾아줘", {"decision_action": "search", "place_intent_frame": frame,
                    "results": [{"id": "db:1", "name": "A"}, {"id": "db:2", "name": "B"}]})
        reason = run_ai_search({"query": "두 번째는 왜?", "previous_context": build_previous_context(state)})
        state = state_from_search_response("두 번째는 왜?", reason, state)
        self.assertEqual(state["selected_result_key"], "db:2")
        provider = {"decision_action": "search", "place_intent_frame": frame, "results": [{"id": "db:2", "name": "B"}, {"id": "db:3", "name": "C"}]}
        with patch("recommendations.services.ai_search_orchestrator._run_ai_search", return_value=deepcopy(provider)):
            excluded = run_ai_search({"query": "그곳은 빼줘", "previous_context": build_previous_context(state)})
        self.assertEqual([p["name"] for p in excluded["results"]], ["C"])
        state = state_from_search_response("그곳은 빼줘", excluded, state)
        with patch("recommendations.services.ai_search_orchestrator._run_ai_search", return_value=deepcopy(provider)):
            other = run_ai_search({"query": "다른 곳 보여줘", "previous_context": build_previous_context(state)})
        self.assertNotIn("B", [p["name"] for p in other["results"]])

    def test_optional_missing_evidence_does_not_block_required_match(self):
        frame = patch_frame("주차 필수 콘센트는 있으면 좋아", {})[0]
        qualified, _, _ = _enforce_required_result_policy([{"matched_conditions": ["주차 가능"], "missing_conditions": ["콘센트있음"]}], frame, "")
        self.assertEqual(len(qualified), 1)

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_location_change_retains_semantic_condition_metadata(self):
        frame = patch_frame("주차 필수 콘센트는 있으면 좋아", {"target_objects": ["카페"], "anchor_location": "서면"}, source_turn=2)[0]
        plan = build_ai_intent_plan("해운대로 바꿔", previous_context={"place_intent_frame": frame, "turn_count": 2})
        self.assertEqual(plan["frame"]["required_features"], ["주차 가능"])
        self.assertEqual(plan["frame"]["preferred_features"], ["콘센트있음"])
        self.assertEqual(plan["frame"]["structured_conditions"], frame["structured_conditions"])
        self.assertNotEqual(plan["frame"]["anchor_location"], "서면")

    @override_settings(DEBUG=False)
    def test_production_response_strips_state_history_and_diagnostics(self):
        from recommendations.views import _public_search_response
        data = _public_search_response({"results": [], "debug_pipeline": {}, "ai_debug": {}, "conversation_trace": {}, "restored_state": {"state_history": []}})
        self.assertEqual(data, {"results": []})

    def test_undo_records_valid_patch_even_when_provider_fails(self):
        original = patch_frame("콘센트 필수", {"anchor_location": "서면", "target_objects": ["카페"]})[0]
        state = state_from_search_response("콘센트 필수", {"decision_action": "search", "place_intent_frame": original, "results": []})
        narrowed = patch_frame("1km 안으로", original)[0]
        failed = state_from_search_response("1km 안으로", {"decision_action": "ai_unavailable", "place_intent_frame": narrowed, "results": []}, state)
        response = run_ai_search({"query": "방금 변경 취소", "previous_context": build_previous_context(failed)})
        restored = state_from_search_response("방금 변경 취소", response, failed)
        self.assertEqual(restored["place_intent_frame"], original)

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False, SEMANTIC_RETRIEVAL_ENABLED=False)
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], []))
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates", return_value=([], {"status": "failed"}))
    def test_understood_empty_patch_is_data_zero_not_ai_outage(self, rerank, kakao, db):
        response = run_ai_search({"query": "1km 안으로", "lat": 35.1579, "lng": 129.0592,
                    "previous_context": {"place_intent_frame": {"anchor_location": "서면", "location_mode": "explicit", "target_objects": ["카페"], "candidate_place_types": ["카페"], "candidate_category_codes": ["cafe"], "primary_search_queries": ["카페"]}}})
        self.assertEqual(response["decision_action"], "search")
        self.assertEqual(response["results"], [])
