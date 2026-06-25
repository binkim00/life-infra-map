from datetime import timedelta
import json
from pathlib import Path
import shutil
import tempfile
from unittest import skip
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from recommendations.models import (
    Place,
    PlaceReport,
    PlaceReportImage,
    PlaceTag,
    Tag,
    UserPreference,
    UserSearchLog,
)
from recommendations.services.ai_situation_parser import parse_situation
from recommendations.services.ai_web_search_provider import (
    clear_ai_web_search_cache,
    get_ai_web_search_result,
)
from recommendations.services.conversational_search_planner import build_conversational_search_plan
from recommendations.services.db_recommender import search_db_recommendations
from recommendations.services.naver_search_provider import build_naver_search_query
from recommendations.services.recommendation_condition import build_recommendation_condition


@override_settings(ALLOWED_HOSTS=["localhost", "testserver"])
class RecommendationSearchTests(TestCase):
    REPO_ROOT = Path(__file__).resolve().parents[2]

    def _repo_file_text(self, relative_path):
        return (self.REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def setUp(self):
        self._media_root = tempfile.mkdtemp()
        self._media_override = override_settings(MEDIA_ROOT=self._media_root)
        self._media_override.enable()
        clear_ai_web_search_cache()
        self.client = Client(HTTP_HOST="localhost")
        self.user = get_user_model().objects.create_user(
            username="searcher",
            password="pass",
        )
        self.token = Token.objects.create(user=self.user)
        self.place = Place.objects.create(
            name="테스트 작업 카페",
            category="cafe",
            address="부산 테스트로 1",
            lat=35.1556,
            lng=129.0641,
            source="test",
            external_id="cafe-1",
            source_name="test",
            data_quality_score=90,
        )
        self.fallback_place = Place.objects.create(
            name="태그 없는 테스트 카페",
            category="cafe",
            address="부산 테스트로 2",
            lat=35.1557,
            lng=129.0642,
            source="test",
            external_id="cafe-2",
            source_name="test",
            data_quality_score=60,
        )
        tag = Tag.objects.create(name="와이파이", tag_type="recommendation")
        PlaceTag.objects.create(
            place=self.place,
            tag=tag,
            source="checked",
            status="confirmed",
            confidence=90,
            is_verified=True,
        )

    def tearDown(self):
        self._media_override.disable()
        shutil.rmtree(self._media_root, ignore_errors=True)

    def _make_naver_response(self, items):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"items": items}
        return response

    def _auth_headers(self):
        return {
            "HTTP_AUTHORIZATION": f"Token {self.token.key}",
            "HTTP_HOST": "localhost",
        }

    def _staff_headers(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = get_user_model().objects.create_user(
                username="staff-user",
                password="pass",
                is_staff=True,
            )
            self.staff_token = Token.objects.create(user=self.staff_user)

        return {
            "HTTP_AUTHORIZATION": f"Token {self.staff_token.key}",
            "HTTP_HOST": "localhost",
        }

    def _create_search_log(self, user=None, query="검색어", created_at=None, **kwargs):
        search_log = UserSearchLog.objects.create(
            user=user or self.user,
            query=query,
            **kwargs,
        )

        if created_at is not None:
            UserSearchLog.objects.filter(id=search_log.id).update(created_at=created_at)
            search_log.refresh_from_db()

        return search_log

    def _create_place(
        self,
        name,
        category,
        external_id,
        lat=35.1556,
        lng=129.0641,
        data_quality_score=70,
        raw=None,
    ):
        return Place.objects.create(
            name=name,
            category=category,
            address="부산 테스트로 10",
            lat=lat,
            lng=lng,
            source="walk-test",
            external_id=external_id,
            source_name="test",
            data_quality_score=data_quality_score,
            raw=raw or {},
        )

    def _add_tag(self, place, name, is_verified=True, status="confirmed"):
        tag, _ = Tag.objects.get_or_create(
            name=name,
            defaults={"tag_type": "recommendation"},
        )
        PlaceTag.objects.create(
            place=place,
            tag=tag,
            source="checked" if is_verified else "ai_suggested",
            status=status,
            confidence=90 if is_verified else 60,
            is_verified=is_verified,
        )
        return tag

    def _frame_search_payload(self, frame, query="하단역인데 화장실 급해"):
        search_plan = {
            "scenario": "waiting_place",
            "execution_mode": "frame",
            "plan_source": "ai",
            "place_intent_frame": frame,
            "location_mode": frame.get("location_mode"),
            "target_objects": frame.get("target_objects", []),
            "candidate_category_codes": frame.get("candidate_category_codes", []),
            "candidate_place_types": frame.get("candidate_place_types", []),
            "search_queries": frame.get("search_queries", []),
            "result_match_terms": frame.get("result_match_terms", []),
            "constraints": frame.get("constraints", []),
            "exclusions": frame.get("exclusions", []),
            "ranking_policy": frame.get("ranking_policy", ""),
        }
        return {
            "query": frame.get("display_label") or query,
            "originalQuery": query,
            "lat": 35.1556,
            "lng": 129.0641,
            "limit": 10,
            "search_plan": search_plan,
            "place_intent_frame": frame,
        }

    def _ai_planner_frame_response(
        self,
        *,
        query,
        display_label,
        situation="general_place",
        anchor_location="",
        location_mode="current_context",
        target_objects=None,
        candidate_category_codes=None,
        candidate_place_types=None,
        search_queries=None,
        result_match_terms=None,
        constraints=None,
        exclusions=None,
        ranking_policy="evidence_first",
        scenario="waiting_place",
        can_search_now=True,
    ):
        frame = {
            "decision_action": "search",
            "user_goal": f"{display_label} 찾기",
            "normalized_user_intent": f"{display_label} 장소 검색",
            "anchor_location": anchor_location,
            "location_mode": location_mode,
            "situation": situation,
            "display_label": display_label,
            "target_objects": target_objects or [display_label],
            "candidate_category_codes": candidate_category_codes or [],
            "candidate_place_types": candidate_place_types or [display_label],
            "search_queries": search_queries or [display_label],
            "result_match_terms": result_match_terms or [display_label],
            "constraints": constraints or [],
            "exclusions": exclusions or [],
            "preferred_place_natures": [],
            "excluded_place_natures": [],
            "ranking_policy": ranking_policy,
            "missing_info": [],
            "assumptions": [],
            "clarification_question": "",
            "clarification_options": [],
            "can_search_now": can_search_now,
            "confidence": 0.9,
        }
        return {
            "action": "search",
            "decision_action": "search",
            "intent_type": "place_recommendation",
            "user_intent_summary": f"{display_label} 검색 요청",
            "message": "",
            "location": {
                "text": anchor_location,
                "is_explicit": bool(anchor_location),
                "fallback": "" if anchor_location else "current_location",
            },
            "targets": [display_label],
            "conditions": constraints or [],
            "preferences": [],
            "avoid": exclusions or [],
            "search_plan": {
                "locationQuery": anchor_location,
                "baseLocationQuery": anchor_location,
                "targetQuery": display_label,
                "scenario": scenario,
                "categories": candidate_category_codes or [],
                "place_intent_frame": frame,
            },
            "execution_policy": {
                "run_search": can_search_now,
                "preserve_explicit_location": bool(anchor_location),
                "allow_kakao_fallback": True,
                "allow_ai_web_search_auto": False,
                "merge_ai_web_results": False,
            },
            "needs_clarification": False,
            "clarification_question": "",
            "clarification_options": [],
            "confidence": 0.9,
        }

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_plan_api_decision_action_search_cases(self, mock_ai):
        cases = [
            {
                "query": "하단역인데 화장실 급해",
                "ai": self._ai_planner_frame_response(
                    query="하단역인데 화장실 급해",
                    display_label="공중화장실",
                    situation="toilet",
                    anchor_location="하단역",
                    location_mode="explicit",
                    target_objects=["화장실"],
                    candidate_category_codes=["toilet"],
                    candidate_place_types=["공중화장실", "개방화장실", "화장실"],
                    search_queries=["하단역 공중화장실", "하단역 화장실"],
                    result_match_terms=["화장실", "공중화장실", "개방화장실"],
                    constraints=["가까운 곳", "긴급"],
                    ranking_policy="urgent_nearest",
                    scenario="waiting_place",
                ),
                "repair": None,
            },
            {
                "query": "사상역 근처 쌀국수 맛집",
                "ai": self._ai_planner_frame_response(
                    query="사상역 근처 쌀국수 맛집",
                    display_label="쌀국수 맛집",
                    situation="food",
                    anchor_location="사상역",
                    location_mode="explicit",
                    target_objects=["쌀국수"],
                    candidate_category_codes=["restaurant"],
                    candidate_place_types=["음식점", "식당"],
                    search_queries=["사상역 쌀국수", "사상역 쌀국수 맛집"],
                    result_match_terms=["쌀국수", "베트남음식", "음식점"],
                    scenario="restaurant",
                ),
                "repair": None,
            },
            {
                "query": "달달한거 먹고 싶어",
                "ai": self._ai_planner_frame_response(
                    query="달달한거 먹고 싶어",
                    display_label="달달한 음식",
                    situation="food",
                    location_mode="current_context",
                    target_objects=["달달한 음식"],
                    candidate_category_codes=["cafe", "restaurant"],
                    candidate_place_types=["카페", "음식점"],
                    search_queries=["디저트", "베이커리", "카페"],
                    result_match_terms=["디저트", "베이커리", "케이크", "빙수", "아이스크림"],
                    scenario="restaurant",
                ),
                "repair": {"explicit_anchor_location": ""},
            },
            {
                "query": "강남역 작업할 만한 카페",
                "ai": self._ai_planner_frame_response(
                    query="강남역 작업할 만한 카페",
                    display_label="작업할 만한 카페",
                    situation="work",
                    anchor_location="강남역",
                    location_mode="explicit",
                    target_objects=["작업할 공간"],
                    candidate_category_codes=["cafe"],
                    candidate_place_types=["카페", "스터디카페"],
                    search_queries=["강남역 작업 카페", "강남역 노트북 카페"],
                    result_match_terms=["노트북", "콘센트", "와이파이", "조용함", "작업 가능"],
                    constraints=["노트북 작업 가능", "콘센트", "와이파이"],
                    scenario="work_cafe",
                ),
                "repair": None,
            },
            {
                "query": "카페 말고 조용히 쉴 곳",
                "ai": self._ai_planner_frame_response(
                    query="카페 말고 조용히 쉴 곳",
                    display_label="조용히 쉴 곳",
                    situation="quiet_rest",
                    location_mode="current_context",
                    target_objects=["조용히 쉬기"],
                    candidate_category_codes=["library", "shelter", "city_park"],
                    candidate_place_types=["도서관", "쉼터", "공원"],
                    search_queries=["조용한 공공공간", "도서관", "쉼터"],
                    result_match_terms=["조용함", "휴식", "도서관", "쉼터"],
                    constraints=["조용함"],
                    exclusions=["카페 제외"],
                    scenario="waiting_place",
                ),
                "repair": {"explicit_anchor_location": ""},
            },
        ]

        for case in cases:
            with self.subTest(query=case["query"]):
                mock_ai.reset_mock()
                mock_ai.side_effect = (
                    [case["ai"], case["repair"]]
                    if case["repair"] is not None
                    else [case["ai"]]
                )

                response = self.client.post(
                    "/api/recommendations/conversational-search-plan/",
                    data=json.dumps({"query": case["query"]}, ensure_ascii=False),
                    content_type="application/json",
                    **self._auth_headers(),
                )

                self.assertEqual(response.status_code, 200)
                data = response.json()
                search_plan = data["search_plan"]
                frame = search_plan["place_intent_frame"]
                self.assertEqual(data["action"], "search")
                self.assertEqual(data["decision_action"], "search")
                self.assertTrue(data["can_search_now"])
                self.assertTrue(data["execution_policy"]["run_search"])
                self.assertEqual(data["plan_source"], "ai")
                self.assertEqual(data["execution_mode"], "frame")
                self.assertEqual(search_plan["decision_action"], "search")
                self.assertTrue(search_plan["can_search_now"])
                self.assertEqual(frame["decision_action"], "search")
                self.assertTrue(frame["can_search_now"])
                self.assertTrue(frame["target_objects"])
                self.assertTrue(frame["result_match_terms"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.views.search_db_recommendations")
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_plan_api_decision_action_ask_clarification_does_not_search(self, mock_ai, mock_search):
        mock_ai.return_value = {
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "intent_type": "place_recommendation",
            "user_intent_summary": "목적이 넓어 추가 확인이 필요함",
            "message": "어떤 목적의 장소를 찾으시나요?",
            "search_plan": {
                "targetQuery": "장소",
                "place_intent_frame": {
                    "decision_action": "ask_clarification",
                    "user_goal": "목적이 불명확한 장소 추천 요청",
                    "normalized_user_intent": "목적이 넓어 되묻기가 필요한 장소 추천 요청",
                    "anchor_location": "",
                    "location_mode": "clarification_required",
                    "situation": "general_place",
                    "display_label": "장소 추천",
                    "target_objects": [],
                    "candidate_place_types": ["장소"],
                    "search_queries": [],
                    "result_match_terms": [],
                    "constraints": [],
                    "exclusions": [],
                    "missing_info": ["목적"],
                    "clarification_question": "쉬는 곳, 먹을 곳, 산책할 곳 중 어떤 쪽을 원하시나요?",
                    "clarification_options": ["쉬는 곳", "먹을 곳", "산책할 곳", "작업할 곳"],
                    "can_search_now": False,
                    "confidence": 0.55,
                },
            },
            "execution_policy": {"run_search": False},
            "needs_clarification": True,
            "clarification_question": "쉬는 곳, 먹을 곳, 산책할 곳 중 어떤 쪽을 원하시나요?",
            "clarification_options": ["쉬는 곳", "먹을 곳", "산책할 곳", "작업할 곳"],
            "confidence": 0.55,
        }

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": "어디 갈만한 데"}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        frame = data["search_plan"]["place_intent_frame"]
        self.assertEqual(data["type"], "clarification")
        self.assertEqual(data["decision_action"], "ask_clarification")
        self.assertFalse(data["can_search_now"])
        self.assertFalse(data["execution_policy"]["run_search"])
        self.assertEqual(data["results"], [])
        self.assertTrue(data["clarification_question"])
        self.assertTrue(data["clarification_options"])
        self.assertEqual(frame["decision_action"], "ask_clarification")
        self.assertFalse(frame["can_search_now"])
        mock_search.assert_not_called()

    def _broad_ai_search_response(self, query):
        return {
            "action": "search",
            "decision_action": "search",
            "intent_type": "place_recommendation",
            "user_intent_summary": "목적이 넓은 장소 추천 요청",
            "message": "",
            "location": {
                "text": "",
                "is_explicit": False,
                "fallback": "current_location",
            },
            "targets": [query],
            "conditions": [],
            "preferences": [],
            "avoid": [],
            "search_plan": {
                "locationQuery": "",
                "baseLocationQuery": "",
                "targetQuery": query,
                "scenario": "waiting_place",
                "categories": [],
                "place_intent_frame": {
                    "decision_action": "search",
                    "user_goal": "목적이 넓은 장소 추천 요청",
                    "normalized_user_intent": "심심함 해소 또는 갈만한 곳 찾기",
                    "anchor_location": "",
                    "location_mode": "current_context",
                    "situation": "general_place",
                    "display_label": query,
                    "target_objects": [query],
                    "candidate_category_codes": [],
                    "candidate_place_types": ["카페", "쉼터", query],
                    "search_queries": ["카페", "쉼터", query],
                    "result_match_terms": [query, "cafe", "shelter", "카페", "쉼터"],
                    "constraints": [],
                    "exclusions": [],
                    "preferred_place_natures": [],
                    "excluded_place_natures": [],
                    "ranking_policy": "",
                    "missing_info": [],
                    "can_search_now": True,
                    "confidence": 0,
                },
            },
            "execution_policy": {"run_search": True},
            "needs_clarification": False,
            "clarification_question": "",
            "clarification_options": [],
            "confidence": 0,
        }

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.views.search_db_recommendations")
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_plan_api_post_validation_forces_clarification_for_broad_search_frame(self, mock_ai, mock_search):
        for query in ["어디 갈만한 데", "나 심심한데 뭐 하지"]:
            with self.subTest(query=query):
                mock_ai.reset_mock()
                mock_search.reset_mock()
                mock_ai.return_value = self._broad_ai_search_response(query)

                response = self.client.post(
                    "/api/recommendations/conversational-search-plan/",
                    data=json.dumps({"query": query}, ensure_ascii=False),
                    content_type="application/json",
                    **self._auth_headers(),
                )

                self.assertEqual(response.status_code, 200)
                data = response.json()
                search_plan = data["search_plan"]
                frame = search_plan["place_intent_frame"]
                self.assertEqual(data["type"], "clarification")
                self.assertEqual(data["decision_action"], "ask_clarification")
                self.assertFalse(data["can_search_now"])
                self.assertFalse(data["execution_policy"]["run_search"])
                self.assertEqual(data["results"], [])
                self.assertTrue(data["clarification_question"])
                self.assertEqual(data["clarification_options"], [])
                self.assertEqual(data["parser_provider"], "gms")
                self.assertFalse(data["parser_fallback"])
                self.assertEqual(data["plan_source"], "ai")
                self.assertEqual(data["execution_mode"], "decision_gate")
                self.assertEqual(search_plan["decision_action"], "ask_clarification")
                self.assertFalse(search_plan["can_search_now"])
                self.assertEqual(frame["decision_action"], "ask_clarification")
                self.assertFalse(frame["can_search_now"])
                self.assertEqual(
                    data["ai_debug"]["post_validation"]["status"],
                    "forced_clarification",
                )
                self.assertIn(
                    "target_repeats_raw_query_without_evidence",
                    data["ai_debug"]["post_validation"]["reasons"],
                )
                mock_search.assert_not_called()

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_post_validation_blocks_broad_search_frame_without_db_search(self):
        query = "어디 갈만한 데"
        broad_plan = self._broad_ai_search_response(query)
        search_plan = broad_plan["search_plan"]
        frame = search_plan["place_intent_frame"]
        payload = {
            "query": query,
            "originalQuery": query,
            "lat": 35.1,
            "lng": 129.0,
            "decision_action": "search",
            "search_plan": search_plan,
            "place_intent_frame": frame,
        }

        with patch("recommendations.views.search_db_recommendations") as mock_search, \
            patch("recommendations.views.search_places_by_keyword") as mock_kakao:
            response = self.client.post(
                "/api/recommendations/ai-search/",
                data=json.dumps(payload, ensure_ascii=False),
                content_type="application/json",
                **self._auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["type"], "clarification")
        self.assertEqual(data["decision_action"], "ask_clarification")
        self.assertFalse(data["can_search_now"])
        self.assertEqual(data["results"], [])
        self.assertEqual(data["markers"], [])
        self.assertFalse(data["execution_policy"]["run_search"])
        self.assertIn(
            "target_repeats_raw_query_without_evidence",
            data["ai_debug"]["post_validation"]["reasons"],
        )
        mock_search.assert_not_called()
        mock_kakao.assert_not_called()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_clarification_followup_merges_answer_without_treating_it_as_location(self, mock_ai):
        original_query = "어디 갈만한 데"
        answer = "먹기"
        followup_ai_response = self._ai_planner_frame_response(
            query=f"{original_query} {answer}",
            display_label="음식점",
            situation="food",
            target_objects=["음식점"],
            candidate_category_codes=["restaurant"],
            candidate_place_types=["식당", "음식점"],
            search_queries=["음식점", "식당"],
            result_match_terms=["음식점", "식당"],
            scenario="restaurant",
        )

        def ai_side_effect(*args, **kwargs):
            system_prompt = kwargs.get("system_prompt") or ""
            payload = kwargs.get("query") or ""
            if "AI Location Repair" in system_prompt:
                return {
                    "explicit_anchor_location": "",
                    "location_mode": "current_context",
                    "reason": "no_explicit_location_found",
                }
            if answer in payload:
                return followup_ai_response
            return self._broad_ai_search_response(original_query)

        mock_ai.side_effect = ai_side_effect

        first_response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": original_query, "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(first_response.status_code, 200)
        first_data = first_response.json()
        self.assertEqual(first_data["decision_action"], "ask_clarification")

        mock_ai.reset_mock()
        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps(
                {
                    "query": answer,
                    "clarification_answer": answer,
                    "is_clarification_followup": True,
                    "previous_search_plan": first_data["search_plan"],
                    "pending_clarification_frame": first_data["search_plan"]["place_intent_frame"],
                    "previous_user_query": original_query,
                    "lat": 35.1556,
                    "lng": 129.0641,
                    "last_resolved_location_context": {
                        "locationMode": "current_context",
                        "lat": 35.1556,
                        "lng": 129.0641,
                    },
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        frame = data["search_plan"]["place_intent_frame"]
        self.assertEqual(data["decision_action"], "search")
        self.assertTrue(data["can_search_now"])
        self.assertTrue(data["execution_policy"]["run_search"])
        self.assertEqual(data["fallback_reason"], "clarification_follow_up_ai_merge")
        self.assertEqual(frame["location_mode"], "current_context")
        self.assertEqual(frame.get("anchor_location") or "", "")
        self.assertIn("음식점", frame["target_objects"])
        self.assertIn("음식점", frame["result_match_terms"])
        self.assertIn("음식점", frame["search_queries"])
        self.assertNotEqual(data["location"]["text"], answer)
        self.assertGreaterEqual(mock_ai.call_count, 2)

    def test_clarification_followup_preserves_previous_explicit_anchor(self):
        original_query = "하단역 근처 어디 갈만한 데"
        answer = "화장실"
        broad_plan = self._broad_ai_search_response(original_query)
        search_plan = broad_plan["search_plan"]
        frame = search_plan["place_intent_frame"]
        frame["anchor_location"] = "하단역"
        frame["location_mode"] = "explicit"
        search_plan["locationQuery"] = "하단역"
        search_plan["baseLocationQuery"] = "하단역"
        search_plan["place_intent_frame"] = frame

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps(
                {
                    "query": answer,
                    "clarification_answer": answer,
                    "is_clarification_followup": True,
                    "previous_search_plan": search_plan,
                    "pending_clarification_frame": frame,
                    "previous_user_query": original_query,
                    "lat": 35.1556,
                    "lng": 129.0641,
                    "last_resolved_location_context": {
                        "locationQuery": "하단역",
                        "anchorLocation": "하단역",
                        "locationMode": "explicit",
                        "lat": 35.1556,
                        "lng": 129.0641,
                    },
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        frame = data["search_plan"]["place_intent_frame"]
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(frame["anchor_location"], "하단역")
        self.assertEqual(frame["location_mode"], "explicit")
        self.assertIn("하단역", data["search_plan"]["search_queries"][0])
        self.assertIn(answer, frame["target_objects"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_low_confidence_urgent_frame_uses_ranking_policy_and_evidence(self, mock_ai):
        query = "하단역인데 화장실 급해"
        ai_response = self._ai_planner_frame_response(
            query=query,
            display_label="공중화장실",
            situation="toilet",
            anchor_location="하단역",
            location_mode="explicit",
            target_objects=["화장실"],
            candidate_category_codes=["toilet"],
            candidate_place_types=["공중화장실", "개방화장실"],
            search_queries=["하단역 공중화장실"],
            result_match_terms=["화장실", "공중화장실"],
            constraints=["가까운 곳"],
            ranking_policy="urgent_nearest",
        )
        ai_response["confidence"] = 0.2
        ai_response["search_plan"]["place_intent_frame"]["confidence"] = 0.2
        mock_ai.return_value = ai_response

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": query, "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["search_plan"]["place_intent_frame"]["ranking_policy"], "urgent_nearest")
        self.assertEqual(data["search_plan"]["place_intent_frame"]["anchor_location"], "하단역")
        self.assertNotEqual(data["type"], "clarification")

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_clarification_does_not_override_rule_search_with_evidence(self, mock_ai):
        query = "하단역인데 화장실 급해"
        mock_ai.return_value = {
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "intent_type": "place_recommendation",
            "user_intent_summary": "목적 확인 필요",
            "message": "어떤 목적의 장소를 찾으시나요?",
            "search_plan": {},
            "execution_policy": {"run_search": False},
            "needs_clarification": True,
            "clarification_question": "어떤 목적의 장소를 찾으시나요?",
            "clarification_options": ["쉬기", "먹기"],
            "confidence": 0.2,
        }

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": query, "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "ask_clarification")
        self.assertFalse(data["can_search_now"])
        self.assertFalse(data["execution_policy"]["run_search"])
        self.assertNotEqual(
            data.get("ai_fallback_reason"),
            "ai_clarification_overridden_by_rule_evidence",
        )

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False,
    )
    @patch("recommendations.views.map_kakao_place_to_recommendation", side_effect=AssertionError("legacy place mapper must not run"))
    @patch("recommendations.views.search_db_recommendations", side_effect=AssertionError("legacy DB recommender must not run"))
    @patch("recommendations.views.build_conversational_search_plan", side_effect=AssertionError("legacy conversational planner must not run"))
    @patch("recommendations.views.parse_situation", side_effect=AssertionError("parse_situation must not reroute /ai-search"))
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword")
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_single_path_resolves_explicit_anchor_without_legacy_runtime(
        self,
        mock_intent,
        mock_kakao,
        mock_rerank,
        mock_parse,
        mock_legacy_plan,
        mock_legacy_db,
        mock_place_mapper,
    ):
        place = self._create_place(
            name="Pho House",
            category="restaurant",
            external_id="pho-house",
            lat=35.2004,
            lng=129.2004,
            data_quality_score=95,
        )
        self._add_tag(place, "pho", is_verified=True)
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "Station pho",
            "frame": {
                "location_mode": "explicit",
                "anchor_location": "Station",
                "target_objects": ["pho"],
                "candidate_place_types": ["restaurant"],
                "result_match_terms": ["pho"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["Station pho"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.93,
            "ai_retry_count": 0,
        }

        def fake_kakao(keyword, lat=None, lng=None, radius=1000, size=5):
            if keyword == "Station":
                if lat is not None or lng is not None:
                    return {"documents": []}
                return {
                    "documents": [{
                        "id": "anchor-1",
                        "place_name": "Station",
                        "x": "129.2",
                        "y": "35.2",
                        "address_name": "Anchor address",
                    }]
                }
            self.assertEqual(keyword, "Station pho")
            self.assertEqual(lat, 35.2)
            self.assertEqual(lng, 129.2)
            return {
                "documents": [{
                    "id": "kakao-pho",
                    "place_name": "Kakao Pho",
                    "category_name": "Vietnamese restaurant",
                    "address_name": "Kakao address",
                    "road_address_name": "Kakao road",
                    "x": "129.2005",
                    "y": "35.2005",
                    "distance": "80",
                    "place_url": "https://place.map.kakao.com/kakao-pho",
                }]
            }

        def fake_rerank(frame, candidates, **kwargs):
            self.assertEqual(frame["target_objects"], ["pho"])
            self.assertTrue(candidates)
            selected = next(candidate for candidate in candidates if candidate["candidate_source"] == "db")
            return [
                {
                    **selected,
                    "semantic_score": 96,
                    "evidence_level": "strong",
                    "semantic_reason": "verified DB evidence matches target",
                    "backend_rank": 1,
                    "unified_rank": 1,
                    "unified_ranker_applied": True,
                }
            ], {
                "status": "executed",
                "input_count": len(candidates),
                "included_count": 1,
                "excluded_count": max(len(candidates) - 1, 0),
                "excluded_candidates": [],
            }

        mock_kakao.side_effect = fake_kakao
        mock_rerank.side_effect = fake_rerank

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "Station pho", "lat": 35.1, "lng": 129.1, "limit": 10}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["debug_pipeline"]["used_path"], "ai_first_orchestrator")
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["status"], "resolved")
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["lat"], 35.2)
        self.assertEqual(data["debug_pipeline"]["search_origin"]["search_lat"], 35.2)
        self.assertEqual(data["debug_pipeline"]["search_origin"]["search_lng"], 129.2)
        self.assertIn("db", data["debug_pipeline"]["search_origin"]["marker_sources"])
        self.assertEqual(data["debug_pipeline"]["candidate_counts"]["db"], 1)
        self.assertTrue(data["frontend_should_skip_kakao_fallback"])
        self.assertFalse(data["execution_policy"]["allow_kakao_fallback"])
        self.assertEqual(data["results"][0]["name"], "Pho House")
        self.assertEqual(data["results"][0]["score_breakdown"]["personalization_boost"], 0)
        self.assertEqual(mock_kakao.call_args_list[0].kwargs["keyword"], "Station")
        candidate_search_calls = [
            call.kwargs
            for call in mock_kakao.call_args_list
            if call.kwargs.get("keyword") == "Station pho"
        ]
        self.assertTrue(
            any(call.get("lat") == 35.2 and call.get("lng") == 129.2 for call in candidate_search_calls)
        )
        mock_rerank.assert_called_once()

    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword")
    def test_ai_search_anchor_resolution_prefers_exact_short_place_name(self, mock_kakao):
        from recommendations.services.ai_search_orchestrator import _resolve_anchor_location

        mock_kakao.return_value = {
            "documents": [
                {
                    "id": "long-nearby",
                    "place_name": "부산시청역중앙하이츠 홍보관",
                    "x": "129.05",
                    "y": "35.14",
                    "address_name": "부산 부산진구 중앙대로 622",
                },
                {
                    "id": "station",
                    "place_name": "부산시청역",
                    "x": "129.0595",
                    "y": "35.1798",
                    "address_name": "부산 연제구 중앙대로 지하",
                },
            ]
        }

        resolved = _resolve_anchor_location("부산시청역", lat=35.1, lng=129.1)

        self.assertEqual(resolved["label"], "부산시청역")
        self.assertEqual(resolved["external_id"], "station")
        self.assertEqual(resolved["lat"], 35.1798)
        self.assertEqual(resolved["lng"], 129.0595)

    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword")
    def test_ai_search_anchor_resolution_accepts_admin_area_address_tokens(self, mock_kakao):
        from recommendations.services.ai_search_orchestrator import _resolve_anchor_location

        mock_kakao.return_value = {
            "documents": [{
                "id": "yeonsan-admin-area",
                "place_name": "온천천시민공원 연산동입구",
                "x": "129.0831",
                "y": "35.1844",
                "address_name": "부산 연제구 연산동 503-1",
            }]
        }

        resolved = _resolve_anchor_location("부산 연산동", lat=35.1, lng=129.1)

        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["external_id"], "yeonsan-admin-area")
        self.assertEqual(resolved["lat"], 35.1844)
        self.assertEqual(resolved["lng"], 129.0831)

    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword")
    def test_ai_search_anchor_resolution_repairs_region_prefixed_station_alias(self, mock_kakao):
        from recommendations.services.ai_search_orchestrator import _resolve_anchor_location

        def fake_kakao(*, keyword, **kwargs):
            if keyword == "부산시청역":
                return {
                    "documents": [{
                        "id": "long-nearby",
                        "place_name": "부산시청역중앙하이츠 홍보관",
                        "x": "129.0595",
                        "y": "35.1481",
                        "address_name": "부산 부산진구 범천동 856-4",
                        "category_name": "부동산 > 부동산서비스 > 분양사무소",
                    }]
                }
            if keyword == "시청역":
                return {
                    "documents": [{
                        "id": "station",
                        "place_name": "시청역 부산1호선",
                        "x": "129.0766",
                        "y": "35.1797",
                        "address_name": "부산 연제구 연산동 1416-2",
                        "category_name": "교통,수송 > 지하철,전철 > 부산1호선",
                    }]
                }
            return {"documents": []}

        mock_kakao.side_effect = fake_kakao

        resolved = _resolve_anchor_location("부산시청역", lat=35.1, lng=129.1)

        self.assertEqual(resolved["label"], "시청역 부산1호선")
        self.assertEqual(resolved["external_id"], "station")
        self.assertEqual(resolved["lat"], 35.1797)
        self.assertEqual(resolved["lng"], 129.0766)

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False,
    )
    @patch("recommendations.views.search_db_recommendations", side_effect=AssertionError("legacy DB recommender must not run"))
    @patch("recommendations.views.build_conversational_search_plan", side_effect=AssertionError("legacy conversational planner must not run"))
    @patch("recommendations.views.parse_situation", side_effect=AssertionError("parse_situation must not reroute /ai-search"))
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword")
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_coordinate_anchor_uses_coordinates_without_anchor_keyword_lookup(
        self,
        mock_intent,
        mock_kakao,
        mock_db_collector,
        mock_rerank,
        mock_parse,
        mock_legacy_plan,
        mock_legacy_db,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "rain shelter",
            "frame": {
                "location_mode": "explicit",
                "anchor_location": "35.2,129.2",
                "target_objects": ["shelter"],
                "candidate_place_types": ["indoor place"],
                "result_match_terms": ["shelter"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "distance_first",
                "primary_search_queries": ["35.2,129.2 rain shelter"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.91,
            "ai_retry_count": 0,
        }

        def fake_kakao(keyword, lat=None, lng=None, radius=1000, size=5):
            self.assertEqual(keyword, "rain shelter")
            self.assertEqual(lat, 35.2)
            self.assertEqual(lng, 129.2)
            return {
                "documents": [{
                    "id": "shelter-1",
                    "place_name": "Shelter Candidate",
                    "category_name": "indoor place",
                    "address_name": "Shelter address",
                    "road_address_name": "Shelter road",
                    "x": "129.2001",
                    "y": "35.2001",
                    "distance": "40",
                    "place_url": "https://place.map.kakao.com/shelter-1",
                }]
            }

        def fake_rerank(frame, candidates, **kwargs):
            self.assertEqual(frame["anchor_location"], "35.2,129.2")
            self.assertEqual(candidates[0]["candidate_source"], "kakao")
            return [
                {
                    **candidates[0],
                    "semantic_score": 92,
                    "evidence_level": "strong",
                    "semantic_reason": "external evidence matches target",
                    "backend_rank": 1,
                    "unified_rank": 1,
                    "unified_ranker_applied": True,
                }
            ], {
                "status": "executed",
                "input_count": len(candidates),
                "included_count": 1,
                "excluded_count": 0,
                "excluded_candidates": [],
            }

        mock_kakao.side_effect = fake_kakao
        mock_rerank.side_effect = fake_rerank

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "rain shelter", "lat": 35.1, "lng": 129.1, "limit": 10}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["status"], "resolved")
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["source"], "coordinate_anchor")
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["lat"], 35.2)
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["lng"], 129.2)
        self.assertEqual(mock_kakao.call_count, 1)
        self.assertEqual(mock_kakao.call_args.kwargs["keyword"], "rain shelter")

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False,
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates", side_effect=AssertionError("reranker must not run without collected candidates"))
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], [{"query": "target place", "count": 0}]))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_no_collected_candidates_returns_empty_search_not_ai_unavailable(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_rerank,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "target place",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["target"],
                "candidate_place_types": ["place"],
                "result_match_terms": ["target"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["target place"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "target place", "lat": 35.1, "lng": 129.1, "limit": 10}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["results"], [])
        self.assertEqual(data["markers"], [])
        self.assertTrue(data["can_search_now"])
        self.assertEqual(data["debug_pipeline"]["reranker"]["status"], "skipped")
        self.assertEqual(data["debug_pipeline"]["reranker"]["reason"], "no_candidates_collected")

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False,
    )
    @patch("recommendations.services.ai_search_orchestrator._resolve_anchor_location", side_effect=AssertionError("current coordinates must not be geocoded"))
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates", side_effect=AssertionError("reranker must not run without collected candidates"))
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], [{"query": "카페", "count": 0}]))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_treats_current_coordinates_anchor_as_current_context(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_rerank,
        mock_resolve_anchor,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "카페",
            "frame": {
                "location_mode": "explicit",
                "anchor_location": "current_coordinates",
                "target_objects": ["카페"],
                "candidate_place_types": ["카페"],
                "result_match_terms": ["카페"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["카페"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "카페", "lat": 35.1, "lng": 129.1, "limit": 10}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        frame = data["search_plan"]["place_intent_frame"]
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(frame["location_mode"], "current_context")
        self.assertEqual(frame["anchor_location"], "")
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["status"], "resolved")
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["source"], "request_coordinates")
        mock_resolve_anchor.assert_not_called()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False,
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_partial_reranker_keeps_valid_results(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_rerank,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "target place",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["target"],
                "candidate_place_types": ["place"],
                "result_match_terms": ["target"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["target place"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }
        candidates = [
            {
                "id": f"kakao-{index}",
                "candidate_source": "kakao",
                "name": f"Target Candidate {index}",
                "category": "target place",
                "address": "address",
                "distance": 100 + index,
                "retrieval_query": "target place",
            }
            for index in range(10)
        ]
        mock_kakao_collector.return_value = (candidates, [{"query": "target place", "count": 10}])
        mock_rerank.return_value = (
            [
                {
                    **candidates[0],
                    "semantic_score": 94,
                    "evidence_level": "strong",
                    "semantic_reason": "direct target match",
                    "backend_rank": 1,
                    "unified_rank": 1,
                    "unified_ranker_applied": True,
                },
                {
                    **candidates[1],
                    "semantic_score": 61,
                    "evidence_level": "medium",
                    "semantic_reason": "compatible but needs verification",
                    "verification_required": True,
                    "backend_rank": 2,
                    "unified_rank": 2,
                    "unified_ranker_applied": True,
                },
            ],
            {
                "status": "partial_executed",
                "reason": "missing_candidate_decisions",
                "input_count": 10,
                "included_count": 2,
                "ai_included_count": 1,
                "ai_needs_verification_count": 1,
                "ai_excluded_count": 1,
                "excluded_count": 1,
                "excluded_candidates": [{"id": "kakao-2", "name": "Target Candidate 2"}],
                "unresolved_count": 7,
                "unresolved_candidate_ids": [f"kakao-{index}" for index in range(3, 10)],
                "unresolved_candidates": [{"id": f"kakao-{index}"} for index in range(3, 10)],
                "reranker_partial": True,
                "reranker_call_count": 2,
                "call_count": 2,
            },
        )

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "target place", "lat": 35.1, "lng": 129.1, "limit": 10}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["debug_pipeline"]["reranker"]["status"], "partial_executed")
        self.assertEqual(data["debug_pipeline"]["candidate_counts"]["removed_incompatible"], 1)
        self.assertEqual(data["debug_pipeline"]["candidate_counts"]["unresolved"], 7)
        self.assertEqual(data["debug_pipeline"]["unresolved_count"], 7)
        self.assertEqual(data["debug_pipeline"]["ai_included_count"], 1)
        self.assertEqual(data["debug_pipeline"]["ai_needs_verification_count"], 1)
        self.assertEqual(data["debug_pipeline"]["ai_excluded_count"], 1)
        self.assertTrue(data["debug_pipeline"]["reranker_partial"])
        self.assertLessEqual(data["debug_pipeline"]["reranker_call_count"], 2)
        self.assertTrue(data["frontend_should_skip_kakao_fallback"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False,
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_reranker_total_failure_returns_ai_unavailable(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_rerank,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "target place",
            "frame": {
                "location_mode": "current_context",
                "target_objects": ["target"],
                "candidate_place_types": ["place"],
                "result_match_terms": ["target"],
                "primary_search_queries": ["target place"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
        }
        candidates = [
            {"id": f"kakao-{index}", "candidate_source": "kakao", "name": f"Candidate {index}"}
            for index in range(3)
        ]
        mock_kakao_collector.return_value = (candidates, [{"query": "target place", "count": 3}])
        mock_rerank.return_value = (
            [],
            {
                "status": "failed",
                "reason": "ReadTimeout:3",
                "input_count": 3,
                "included_count": 0,
                "excluded_count": 0,
                "unresolved_count": 3,
                "unresolved_candidate_ids": ["kakao-0", "kakao-1", "kakao-2"],
                "reranker_partial": False,
                "reranker_call_count": 2,
                "call_count": 2,
            },
        )

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "target place", "lat": 35.1, "lng": 129.1}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "ai_unavailable")
        self.assertEqual(data["results"], [])
        self.assertEqual(data["debug_pipeline"]["candidate_counts"]["removed_incompatible"], 0)
        self.assertEqual(data["debug_pipeline"]["candidate_counts"]["unresolved"], 3)
        self.assertTrue(data["frontend_should_skip_kakao_fallback"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False,
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_all_explicit_excludes_returns_empty_search(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_rerank,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "target place",
            "frame": {
                "location_mode": "current_context",
                "target_objects": ["target"],
                "candidate_place_types": ["place"],
                "result_match_terms": ["target"],
                "primary_search_queries": ["target place"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
        }
        candidates = [
            {"id": f"kakao-{index}", "candidate_source": "kakao", "name": f"Candidate {index}"}
            for index in range(3)
        ]
        mock_kakao_collector.return_value = (candidates, [{"query": "target place", "count": 3}])
        mock_rerank.return_value = (
            [],
            {
                "status": "executed",
                "reason": "",
                "input_count": 3,
                "included_count": 0,
                "ai_included_count": 0,
                "ai_needs_verification_count": 0,
                "ai_excluded_count": 3,
                "excluded_count": 3,
                "excluded_candidates": [{"id": f"kakao-{index}"} for index in range(3)],
                "unresolved_count": 0,
                "unresolved_candidate_ids": [],
                "reranker_partial": False,
                "reranker_call_count": 1,
                "call_count": 1,
            },
        )

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "target place", "lat": 35.1, "lng": 129.1}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["results"], [])
        self.assertEqual(data["debug_pipeline"]["candidate_counts"]["removed_incompatible"], 3)
        self.assertEqual(data["debug_pipeline"]["candidate_counts"]["unresolved"], 0)
        self.assertEqual(data["debug_pipeline"]["ai_excluded_count"], 3)
        self.assertTrue(data["frontend_should_skip_kakao_fallback"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.get_ai_web_search_result")
    @patch("recommendations.services.ai_search_orchestrator.repair_search_queries", return_value=([], {"status": "skipped"}))
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates")
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_collects_naver_web_when_db_kakao_are_weak(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_query_repair,
        mock_web,
        mock_rerank,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "target search",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["target"],
                "candidate_place_types": ["place"],
                "result_match_terms": ["target"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["target place"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }
        mock_db_collector.return_value = [{
            "id": "db-weak",
            "candidate_source": "db",
            "name": "Weak DB",
            "category": "category",
            "address": "address",
            "pre_ai_evidence_level": "weak",
            "distance": 100,
        }]
        mock_kakao_collector.return_value = ([{
            "id": "kakao-weak",
            "candidate_source": "kakao",
            "name": "Weak Kakao",
            "category": "category",
            "address": "address",
            "pre_ai_evidence_level": "weak",
            "distance": 120,
            "retrieval_query": "target place",
        }], [{"query": "target place", "count": 1}])
        mock_web.return_value = {
            "candidates": [{
                "name": "Naver Target Place",
                "category": "target place",
                "address_hint": "web address",
                "summary": "target evidence from Naver",
                "source_url": "https://example.com/naver-target",
            }]
        }

        def fake_rerank(frame, candidates, **kwargs):
            web_candidate = next(candidate for candidate in candidates if candidate["candidate_source"] == "web")
            return [{
                **web_candidate,
                "semantic_score": 91,
                "evidence_level": "strong",
                "semantic_reason": "web evidence matches target",
                "backend_rank": 1,
                "unified_rank": 1,
                "unified_ranker_applied": True,
            }], {
                "status": "executed",
                "input_count": len(candidates),
                "included_count": 1,
                "excluded_count": len(candidates) - 1,
                "excluded_candidates": [],
                "decisions": {candidate["id"]: {"decision": "include"} for candidate in candidates},
            }

        mock_rerank.side_effect = fake_rerank

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "target search", "lat": 35.1, "lng": 129.1}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["candidate_source_counts"]["web"], 1)
        self.assertEqual(data["results"][0]["candidate_source"], "web")
        mock_query_repair.assert_not_called()
        mock_web.assert_called_once()

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True)
    @patch("recommendations.views.search_db_recommendations", side_effect=AssertionError("legacy DB recommender must not run"))
    @patch("recommendations.views.build_conversational_search_plan", side_effect=AssertionError("legacy conversational planner must not run"))
    @patch("recommendations.views.parse_situation", side_effect=AssertionError("parse_situation must not reroute /ai-search"))
    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword", side_effect=AssertionError("collectors must not run for clarification"))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", side_effect=AssertionError("DB collector must not run for clarification"))
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_clarification_does_not_collect_or_call_legacy(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao,
        mock_parse,
        mock_legacy_plan,
        mock_legacy_db,
    ):
        mock_intent.return_value = {
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "normalized_query": "ambiguous situation",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": [],
                "candidate_place_types": [],
                "result_match_terms": [],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": [],
                "secondary_search_queries": [],
            },
            "clarification": {
                "question": "Which place-seeking goal should I use?",
                "options": ["medical help", "place to rest"],
                "missing_fields": ["target_objects"],
                "expected_patch_fields": ["target_objects"],
            },
            "confidence": 0.4,
            "ai_retry_count": 0,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "ambiguous situation", "lat": 35.1, "lng": 129.1}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "ask_clarification")
        self.assertEqual(data["results"], [])
        self.assertEqual(data["markers"], [])
        self.assertFalse(data["execution_policy"]["run_search"])
        self.assertEqual(data["debug_pipeline"]["candidate_counts"]["db"], 0)
        self.assertFalse(data["debug_pipeline"]["legacy_path_used"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True)
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", side_effect=AssertionError("Kakao collector must not run without coordinates"))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", side_effect=AssertionError("DB collector must not run without coordinates"))
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_current_context_without_coordinates_asks_location(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "nearby target",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["target"],
                "candidate_place_types": ["place"],
                "result_match_terms": ["target"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "distance_first",
                "primary_search_queries": ["target place"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "nearby target"}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "ask_clarification")
        self.assertFalse(data["execution_policy"]["run_search"])
        self.assertEqual(data["results"], [])
        self.assertEqual(
            data["debug_pipeline"]["location_resolution"]["reason"],
            "missing_current_context_coordinates",
        )

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True)
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates")
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_current_context_coordinates_are_used_and_traced(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "urgent restroom nearby",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["화장실"],
                "candidate_place_types": ["공중화장실"],
                "result_match_terms": ["화장실", "공중화장실"],
                "constraints": ["가까운 곳"],
                "exclusions": [],
                "ranking_policy": "urgent_nearest",
                "primary_search_queries": ["공중화장실"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }

        def fake_db(frame, *, lat=None, lng=None, **kwargs):
            self.assertEqual(lat, 35.106)
            self.assertEqual(lng, 128.966)
            return []

        def fake_kakao(frame, queries, *, lat=None, lng=None, **kwargs):
            self.assertEqual(lat, 35.106)
            self.assertEqual(lng, 128.966)
            return [], []

        mock_db_collector.side_effect = fake_db
        mock_kakao_collector.side_effect = fake_kakao

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                {"query": "지금 너무 급한데 근처 화장실 바로 갈 수 있는 곳 찾아줘", "lat": 35.106, "lng": 128.966},
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["status"], "resolved")
        self.assertEqual(data["debug_pipeline"]["location_resolution"]["reason"], "current_context")
        self.assertEqual(data["debug_pipeline"]["search_origin"]["search_lat"], 35.106)
        self.assertEqual(data["debug_pipeline"]["search_origin"]["search_lng"], 128.966)

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True)
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], []))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_followup_payload_generates_actionable_medical_target(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_rerank,
    ):
        def fake_intent(query, **kwargs):
            previous_context = kwargs.get("previous_context") or {}
            self.assertTrue(previous_context["is_clarification_followup"])
            self.assertEqual(previous_context["clarification_answer"], "병원")
            self.assertIn("허리", previous_context["previous_user_query"])
            self.assertTrue(previous_context["pending_clarification_question"])
            return {
                "action": "search",
                "decision_action": "search",
                "normalized_query": "병원 찾기",
                "frame": {
                    "location_mode": "current_context",
                    "anchor_location": "",
                    "target_objects": ["병원"],
                    "candidate_place_types": ["의료기관"],
                    "result_match_terms": ["병원"],
                    "constraints": [],
                    "exclusions": [],
                    "ranking_policy": "distance_first",
                    "primary_search_queries": ["병원"],
                    "secondary_search_queries": [],
                },
                "clarification": {},
                "confidence": 0.9,
                "ai_retry_count": 0,
                "ai_debug": {"planner": {"call_count": 1}},
            }

        mock_intent.side_effect = fake_intent
        mock_rerank.return_value = ([], {"status": "skipped", "reason": "no_candidates_collected", "call_count": 0})

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({
                "query": "병원",
                "lat": 35.1,
                "lng": 129.1,
                "is_clarification_followup": True,
                "clarification_answer": "병원",
                "previous_user_query": "허리가 아프네",
                "pending_clarification_question": "병원이나 약국을 찾으시나요?",
                "previous_search_plan": {"place_intent_frame": {"location_mode": "current_context"}},
                "pending_clarification_frame": {"location_mode": "current_context"},
                "last_resolved_location_context": {"lat": 35.1, "lng": 129.1},
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["search_plan"]["targetQuery"], "병원")
        self.assertTrue(data["search_plan"]["primary_search_queries"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True)
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates", return_value=([], {"status": "skipped", "reason": "no_candidates_collected", "call_count": 0}))
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], []))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_followup_payload_generates_actionable_song_target(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_rerank,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "노래방 찾기",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["노래방"],
                "candidate_place_types": ["노래 부르는 장소"],
                "result_match_terms": ["노래방"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "distance_first",
                "primary_search_queries": ["노래방"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
            "ai_debug": {"planner": {"call_count": 1}},
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({
                "query": "노래방",
                "lat": 35.1,
                "lng": 129.1,
                "is_clarification_followup": True,
                "clarification_answer": "노래방",
                "previous_user_query": "노래 한 곡 땡기고 싶은데",
                "pending_clarification_question": "노래를 부를 곳인가요, 들을 곳인가요?",
                "previous_search_plan": {"place_intent_frame": {"location_mode": "current_context"}},
                "pending_clarification_frame": {"location_mode": "current_context"},
                "last_resolved_location_context": {"lat": 35.1, "lng": 129.1},
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["search_plan"]["targetQuery"], "노래방")
        mock_intent.assert_called_once()
        previous_context = mock_intent.call_args.kwargs["previous_context"]
        self.assertEqual(previous_context["clarification_answer"], "노래방")

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True)
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates", return_value=([], {"status": "skipped", "reason": "no_candidates_collected", "call_count": 0}))
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], []))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_followup_preserves_explicit_location_context(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_rerank,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "하단역 병원",
            "frame": {
                "location_mode": "explicit",
                "anchor_location": "하단역",
                "target_objects": ["병원"],
                "candidate_place_types": ["의료기관"],
                "result_match_terms": ["병원"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "distance_first",
                "primary_search_queries": ["하단역 병원"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
            "ai_debug": {"planner": {"call_count": 1}},
        }

        with patch("recommendations.services.ai_search_orchestrator._resolve_anchor_location", return_value={
            "status": "resolved",
            "lat": 35.106,
            "lng": 128.966,
            "label": "하단역",
            "source": "test",
        }):
            response = self.client.post(
                "/api/recommendations/ai-search/",
                data=json.dumps({
                    "query": "병원",
                    "lat": 35.1,
                    "lng": 129.1,
                    "is_clarification_followup": True,
                    "clarification_answer": "병원",
                    "previous_user_query": "하단역 근처 어디 갈까",
                    "pending_clarification_question": "무엇을 찾으시나요?",
                    "previous_search_plan": {"locationQuery": "하단역", "place_intent_frame": {"location_mode": "explicit", "anchor_location": "하단역"}},
                    "pending_clarification_frame": {"location_mode": "explicit", "anchor_location": "하단역"},
                    "last_resolved_location_context": {"anchorLocation": "하단역", "lat": 35.106, "lng": 128.966},
                }, ensure_ascii=False),
                content_type="application/json",
                **self._auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(data["search_plan"]["resolved_anchor_location"]["label"], "하단역")

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True)
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", side_effect=AssertionError("collector must not run for empty follow-up frame"))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", side_effect=AssertionError("collector must not run for empty follow-up frame"))
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_followup_empty_target_query_is_not_search(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": [],
                "candidate_place_types": [],
                "result_match_terms": [],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": [],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.3,
            "ai_retry_count": 0,
            "ai_debug": {"planner": {"call_count": 1}},
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({
                "query": "병원",
                "lat": 35.1,
                "lng": 129.1,
                "is_clarification_followup": True,
                "clarification_answer": "병원",
                "previous_user_query": "허리가 아프네",
                "pending_clarification_question": "무엇을 찾으시나요?",
                "previous_search_plan": {"place_intent_frame": {"location_mode": "current_context"}},
                "pending_clarification_frame": {"location_mode": "current_context"},
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "ask_clarification")
        self.assertFalse(data["execution_policy"]["run_search"])

    def test_ai_search_orchestrator_source_does_not_import_legacy_planners(self):
        source = self._repo_file_text("backend/recommendations/services/ai_search_orchestrator.py")

        self.assertNotIn("parse_situation", source)
        self.assertNotIn("build_conversational_search_plan", source)
        self.assertNotIn("search_db_recommendations", source)
        self.assertNotIn("build_recommendation_condition", source)
        self.assertNotIn("map_kakao_place_to_recommendation", source)

    def test_frontend_ai_search_path_returns_before_local_planner(self):
        source = self._repo_file_text("frontend/src/views/Homeview.vue")
        start = source.index("const performUnifiedMapSearch = async")
        backend_only_start = source.index("if (!useMapBounds)", start)
        local_planner_start = source.index("let conversationalPlan =", start)
        backend_only_block = source[backend_only_start:local_planner_start]

        self.assertIn("await runAiMapSearchAtCenter", backend_only_block)
        self.assertIn("backendAiOnly: true", backend_only_block)
        self.assertIn("return", backend_only_block)
        self.assertNotIn("resolveConversationalSearchPlan", backend_only_block)
        self.assertNotIn("buildSearchPlan(", backend_only_block)
        self.assertNotIn("runKakaoRecommendationFallbackSearch", backend_only_block)

    def test_frontend_ai_first_response_returns_before_kakao_fallback_paths(self):
        source = self._repo_file_text("frontend/src/views/Homeview.vue")
        start = source.index("const runAiMapSearchAtCenter = async")
        ai_first_start = source.index("if (backendIsAiFirst)", start)
        post_ai_first_index = source.index("const menuSearchProfile =", ai_first_start)
        ai_first_block = source[ai_first_start:post_ai_first_index]

        self.assertIn("return", ai_first_block)
        self.assertIn("fallbackResults.value = []", ai_first_block)
        self.assertNotIn("shouldRunKakaoRecommendationFallback(", ai_first_block)
        self.assertNotIn("runKakaoRecommendationFallbackSearch(", ai_first_block)
        self.assertNotIn("[카카오 fallback 시작]", source)

    def test_frontend_ai_unavailable_and_zero_results_do_not_run_kakao_fallback(self):
        source = self._repo_file_text("frontend/src/views/Homeview.vue")
        start = source.index("const runAiMapSearchAtCenter = async")
        non_search_start = source.index("if (backendAction && backendAction !== 'search')", start)
        ai_first_start = source.index("if (backendIsAiFirst)", start)
        post_ai_first_index = source.index("const menuSearchProfile =", ai_first_start)
        non_search_block = source[non_search_start:ai_first_start]
        ai_first_block = source[ai_first_start:post_ai_first_index]

        self.assertIn("return", non_search_block)
        self.assertIn("mainResults.value = []", ai_first_block)
        self.assertIn("searchResultStatus.value = data.decision_action === 'ai_unavailable' ? 'error' : 'empty'", ai_first_block)
        self.assertNotIn("runKakaoRecommendationFallbackSearch(", ai_first_block)

    def test_frontend_ai_first_response_resets_rule_parser_banner_state(self):
        source = self._repo_file_text("frontend/src/views/Homeview.vue")
        parser_status_start = source.index("const mapParserStatus = computed")
        parser_status_end = source.index("const searchPlanStatus = computed", parser_status_start)
        parser_status_block = source[parser_status_start:parser_status_end]
        response_start = source.index("mapAiParse.value = {")
        response_end = source.index("if (backendAction && backendAction !== 'search')", response_start)
        response_block = source[response_start:response_end]

        self.assertIn("executionMode === 'ai_first_orchestrator'", parser_status_block)
        self.assertIn("parserProvider === 'ai_intent_planner'", parser_status_block)
        self.assertIn("parserFallback", parser_status_block)
        self.assertIn("parser_fallback: backendIsAiFirst ? false", response_block)
        self.assertIn("ai_fallback_reason: backendIsAiFirst ? ''", response_block)
        self.assertIn("fallback_reason: backendIsAiFirst ? ''", response_block)

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_candidate_reranker._call_gms_chat_json")
    def test_ai_candidate_reranker_keeps_partial_decisions_after_missing_retry_fails(self, mock_ai):
        from recommendations.services.ai_candidate_reranker import semantic_rerank_candidates

        candidates = [
            {
                "id": f"candidate-{index}",
                "candidate_source": "kakao",
                "name": f"Target Place {index}",
                "category": "target category",
                "distance": index,
            }
            for index in range(12)
        ]
        mock_ai.side_effect = [
            {
                "candidates": [
                    {
                        "candidate_id": "candidate-0",
                        "decision": "include",
                        "semantic_score": 93,
                        "evidence_level": "strong",
                        "matched_fields": ["name"],
                        "unmet_constraints": [],
                        "reason": "target evidence",
                    }
                ]
            },
            {"candidates": []},
            {"candidates": []},
            {"candidates": []},
            {"candidates": []},
        ]

        ranked, debug = semantic_rerank_candidates(
            {
                "target_objects": ["target"],
                "result_match_terms": ["target"],
                "candidate_place_types": ["target category"],
            },
            candidates,
        )

        self.assertEqual(debug["status"], "partial_executed")
        self.assertEqual(debug["reason"], "missing_candidate_decisions")
        self.assertTrue(debug["retry_used"])
        self.assertEqual([item["id"] for item in ranked], ["candidate-0"])
        self.assertEqual(debug["ai_included_count"], 1)
        self.assertEqual(debug["ai_excluded_count"], 0)
        self.assertEqual(debug["unresolved_count"], 11)
        self.assertTrue(debug["reranker_partial"])
        self.assertLessEqual(debug["call_count"], 2)
        self.assertIn("candidate-1", debug["unresolved_candidate_ids"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_candidate_reranker._call_gms_chat_json")
    def test_ai_candidate_reranker_reasks_only_missing_candidate_ids(self, mock_ai):
        from recommendations.services.ai_candidate_reranker import semantic_rerank_candidates

        candidates = [
            {
                "id": f"candidate-{index}",
                "candidate_source": "kakao",
                "name": f"Target Place {index}",
                "category": "target category",
                "distance": index,
            }
            for index in range(3)
        ]
        mock_ai.side_effect = [
            {
                "candidates": [
                    {
                        "candidate_id": "candidate-0",
                        "decision": "include",
                        "semantic_score": 93,
                        "evidence_level": "strong",
                        "matched_fields": ["name"],
                        "unmet_constraints": [],
                        "reason": "target evidence",
                    }
                ]
            },
            {
                "candidates": [
                    {
                        "candidate_id": "candidate-1",
                        "decision": "exclude",
                        "semantic_score": 5,
                        "evidence_level": "weak",
                        "matched_fields": [],
                        "unmet_constraints": ["target mismatch"],
                        "reason": "not compatible",
                    },
                    {
                        "candidate_id": "candidate-2",
                        "decision": "include",
                        "semantic_score": 80,
                        "evidence_level": "medium",
                        "matched_fields": ["category"],
                        "unmet_constraints": [],
                        "reason": "compatible",
                    },
                ]
            },
        ]

        ranked, debug = semantic_rerank_candidates(
            {
                "target_objects": ["target"],
                "result_match_terms": ["target"],
                "candidate_place_types": ["target category"],
            },
            candidates,
        )

        self.assertEqual(debug["status"], "executed")
        self.assertTrue(debug["retry_used"])
        self.assertEqual(len(debug["decisions"]), 3)
        self.assertEqual(debug["missing_candidate_ids"], [])
        self.assertEqual([item["id"] for item in ranked], ["candidate-0", "candidate-2"])
        second_payload = json.loads(mock_ai.call_args_list[1].kwargs["query"])
        self.assertEqual(
            {item["candidate_id"] for item in second_payload["candidates"]},
            {"candidate-1", "candidate-2"},
        )

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_candidate_reranker._call_gms_chat_json")
    def test_ai_candidate_reranker_rewrites_internal_english_reason(self, mock_ai):
        from recommendations.services.ai_candidate_reranker import semantic_rerank_candidates

        mock_ai.return_value = {
            "candidates": [
                {
                    "candidate_id": "cafe-1",
                    "decision": "needs_verification",
                    "semantic_score": 64,
                    "evidence_level": "medium",
                    "matched_fields": ["category"],
                    "unmet_constraints": [],
                    "reason": "Candidate is a cafe within target type. Frames require cafe and evidence_level is medium.",
                }
            ]
        }

        ranked, debug = semantic_rerank_candidates(
            {
                "target_objects": ["카페"],
                "result_match_terms": ["카페"],
                "candidate_place_types": ["카페"],
            },
            [
                {
                    "id": "cafe-1",
                    "candidate_source": "db",
                    "name": "조용한 카페",
                    "category": "카페",
                    "distance": 280,
                    "matched_evidence": [
                        {"type": "target_direct", "value": "카페", "field": "category"}
                    ],
                }
            ],
        )

        self.assertEqual(debug["status"], "executed")
        self.assertEqual(len(ranked), 1)
        reason = ranked[0]["recommendation_reason"]
        self.assertIn("카페", reason)
        self.assertIn("확인", reason)
        self.assertNotRegex(reason, r"Candidate|Frames|evidence_level|semantic_score")

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_candidate_reranker._call_gms_chat_json")
    def test_ai_candidate_reranker_retries_missing_batch_once_after_timeout(self, mock_ai):
        from recommendations.services.ai_candidate_reranker import semantic_rerank_candidates

        candidates = [
            {
                "id": f"candidate-{index}",
                "candidate_source": "kakao",
                "name": f"Target Place {index}",
                "category": "target category",
                "distance": index,
            }
            for index in range(12)
        ]
        retry_rows = []
        for index in range(12):
            retry_rows.append({
                "candidate_id": f"candidate-{index}",
                "decision": "include" if index % 2 == 0 else "exclude",
                "semantic_score": 90 - index,
                "evidence_level": "strong" if index % 2 == 0 else "weak",
                "matched_fields": ["name"] if index % 2 == 0 else [],
                "unmet_constraints": [] if index % 2 == 0 else ["target mismatch"],
                "reason": "processed after retry",
            })
        mock_ai.side_effect = [
            requests.exceptions.ReadTimeout("slow model response"),
            {"candidates": retry_rows[:10]},
            {"candidates": retry_rows[10:]},
        ]

        ranked, debug = semantic_rerank_candidates(
            {
                "target_objects": ["target"],
                "result_match_terms": ["target"],
                "candidate_place_types": ["target category"],
            },
            candidates,
        )

        self.assertEqual(debug["status"], "partial_executed")
        self.assertTrue(debug["retry_used"])
        self.assertEqual(len(debug["decisions"]), 10)
        self.assertEqual(debug["unresolved_candidate_ids"], ["candidate-10", "candidate-11"])
        self.assertEqual(len(ranked), 5)
        self.assertEqual(mock_ai.call_count, 2)
        self.assertLessEqual(debug["call_count"], 2)

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_intent_planner._call_gms_chat_json")
    def test_query_repair_allows_semantic_expansion_without_target_substring(self, mock_ai):
        from recommendations.services.ai_intent_planner import repair_search_queries

        mock_ai.return_value = {
            "queries": [
                {"query": "생선구이 맛집", "relationship": "semantic_expansion", "preserves_target": True},
                {"query": "음식점", "relationship": "generic_category_replacement", "preserves_target": False},
            ]
        }

        queries, debug = repair_search_queries(
            "고등어 먹고 싶어",
            {
                "target_objects": ["고등어"],
                "result_match_terms": ["고등어"],
                "candidate_place_types": ["식당"],
            },
        )

        self.assertEqual(queries, ["생선구이 맛집"])
        self.assertEqual(debug["blocked"][0]["relationship"], "generic_category_replacement")

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_intent_planner._call_gms_chat_json")
    def test_query_repair_allows_donburi_expansion_for_rice_bowl(self, mock_ai):
        from recommendations.services.ai_intent_planner import repair_search_queries

        mock_ai.return_value = {
            "queries": [
                {"query": "돈부리 맛집", "relationship": "semantic_expansion", "preserves_target": True},
                {"query": "일식", "relationship": "generic_category_replacement", "preserves_target": False},
            ]
        }

        queries, debug = repair_search_queries(
            "덮밥 먹고 싶어",
            {
                "target_objects": ["덮밥"],
                "result_match_terms": ["덮밥"],
                "candidate_place_types": ["식당"],
            },
        )

        self.assertEqual(queries, ["돈부리 맛집"])
        self.assertEqual(len(debug["blocked"]), 1)

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_intent_planner._call_gms_chat_json")
    def test_query_repair_blocks_non_atomic_query_lists(self, mock_ai):
        from recommendations.services.ai_intent_planner import repair_search_queries

        mock_ai.return_value = {
            "queries": [
                {"query": "지붕 있는 버스정류장, 지하상가, 쇼핑몰", "relationship": "semantic_expansion", "preserves_target": True},
                {"query": "짧게 머물기 좋은 카페 또는 편의점", "relationship": "semantic_expansion", "preserves_target": True},
                {"query": "실내 대기 공간", "relationship": "semantic_expansion", "preserves_target": True},
            ]
        }

        queries, debug = repair_search_queries(
            "비 피할 곳",
            {
                "target_objects": ["비 피할 곳"],
                "result_match_terms": ["실내"],
                "candidate_place_types": ["대기 공간"],
            },
        )

        self.assertEqual(queries, ["실내 대기 공간"])
        self.assertEqual(
            {item["blocked_reason"] for item in debug["blocked"]},
            {"multi_candidate_separator", "multi_candidate_conjunction"},
        )

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_candidate_reranker._call_gms_chat_json")
    def test_ai_candidate_reranker_keeps_needs_verification_candidates(self, mock_ai):
        from recommendations.services.ai_candidate_reranker import semantic_rerank_candidates

        candidates = [{
            "id": "candidate-1",
            "candidate_source": "kakao",
            "name": "Compatible Indoor Candidate",
            "category": "compatible category",
            "distance": 100,
        }]
        mock_ai.return_value = {
            "candidates": [{
                "candidate_id": "candidate-1",
                "decision": "needs_verification",
                "semantic_score": 55,
                "evidence_level": "strong",
                "matched_fields": ["category"],
                "unmet_constraints": ["detail not proven"],
                "reason": "Candidate type is compatible but condition details are not explicit.",
            }]
        }

        ranked, debug = semantic_rerank_candidates(
            {
                "target_objects": ["safe place"],
                "result_match_terms": ["indoor"],
                "candidate_place_types": ["compatible category"],
                "constraints": ["detail condition"],
            },
            candidates,
        )

        self.assertEqual(debug["status"], "executed")
        self.assertEqual(len(ranked), 1)
        self.assertTrue(ranked[0]["verification_required"])
        self.assertEqual(ranked[0]["evidence_level"], "medium")
        self.assertEqual(ranked[0]["compatibility_gate"], "needs_verification")

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_candidate_reranker._call_gms_chat_json")
    def test_ai_candidate_reranker_timeout_on_twenty_candidates_stops_after_one_retry(self, mock_ai):
        from recommendations.services.ai_candidate_reranker import semantic_rerank_candidates

        candidates = [
            {
                "id": f"candidate-{index}",
                "candidate_source": "kakao" if index % 2 else "db",
                "name": f"Target Place {index}",
                "category": "target category",
                "distance": index,
            }
            for index in range(20)
        ]

        def rows(start, end):
            return [
                {
                    "candidate_id": f"candidate-{index}",
                    "decision": "include" if index % 3 == 0 else "exclude",
                    "semantic_score": 90 - index,
                    "evidence_level": "strong" if index % 3 == 0 else "weak",
                    "matched_fields": ["name"] if index % 3 == 0 else [],
                    "unmet_constraints": [] if index % 3 == 0 else ["target mismatch"],
                    "reason": "processed chunk",
                }
                for index in range(start, end)
            ]

        mock_ai.side_effect = [
            requests.exceptions.ReadTimeout("slow model response"),
            {"candidates": rows(0, 10)},
            {"candidates": rows(10, 20)},
        ]

        ranked, debug = semantic_rerank_candidates(
            {
                "target_objects": ["target"],
                "result_match_terms": ["target"],
                "candidate_place_types": ["target category"],
            },
            candidates,
            max_candidates=20,
        )

        self.assertEqual(debug["status"], "partial_executed")
        self.assertEqual(debug["input_count"], 20)
        self.assertEqual(len(debug["decisions"]), 10)
        self.assertEqual(len(debug["unresolved_candidate_ids"]), 10)
        self.assertTrue(debug["reranker_partial"])
        self.assertTrue(debug["retry_used"])
        self.assertEqual(mock_ai.call_count, 2)
        self.assertLessEqual(debug["call_count"], 2)
        self.assertEqual(len(ranked), 4)

    def test_balanced_rerank_shortlist_preserves_db_kakao_web_sources(self):
        from recommendations.services.ai_search_orchestrator import _balanced_rerank_shortlist

        candidates = []
        for index in range(24):
            candidates.append({
                "id": f"db-{index}",
                "candidate_source": "db",
                "name": f"DB {index}",
                "pre_ai_evidence_level": "strong",
                "retrieval_query": "db",
                "distance": index,
            })
        for index in range(4):
            candidates.append({
                "id": f"kakao-{index}",
                "candidate_source": "kakao",
                "name": f"Kakao {index}",
                "pre_ai_evidence_level": "medium",
                "retrieval_query": f"query-{index % 2}",
                "distance": 100 + index,
            })
        for index in range(3):
            candidates.append({
                "id": f"web-{index}",
                "candidate_source": "web",
                "name": f"Web {index}",
                "pre_ai_evidence_level": "medium",
                "retrieval_query": f"web-query-{index}",
                "distance": None,
            })

        shortlisted = _balanced_rerank_shortlist(candidates, 10)
        sources = {candidate["candidate_source"] for candidate in shortlisted}
        query_keys = {
            (candidate["candidate_source"], candidate.get("retrieval_query"))
            for candidate in shortlisted
        }

        self.assertEqual(len(shortlisted), 10)
        self.assertEqual(sources, {"db", "kakao", "web"})
        self.assertIn(("kakao", "query-0"), query_keys)
        self.assertIn(("kakao", "query-1"), query_keys)
        self.assertTrue(any(source == "web" for source, _ in query_keys))

    def test_external_pre_ai_evidence_uses_retrieval_query_as_medium_only(self):
        from recommendations.services.ai_search_orchestrator import _external_pre_ai_evidence

        candidate = {
            "name": "General Candidate",
            "category": "general shop",
            "address": "address",
            "retrieval_query": "station target pastry",
        }
        frame = {
            "target_objects": ["target pastry"],
            "result_match_terms": ["target pastry"],
            "candidate_place_types": ["bakery"],
        }

        level, matched = _external_pre_ai_evidence(candidate, frame)

        self.assertEqual(level, "medium")
        self.assertEqual(matched[0]["type"], "retrieval_query_target")

    def test_external_web_evidence_requires_location_text_for_direct_match(self):
        from recommendations.services.ai_search_orchestrator import _external_pre_ai_evidence

        frame = {
            "location_mode": "explicit",
            "anchor_location": "서면역",
            "target_objects": ["공중화장실"],
            "result_match_terms": ["화장실", "공중화장실"],
            "candidate_place_types": ["공중화장실"],
        }
        wrong_region_candidate = {
            "candidate_source": "web",
            "name": "광화문 공중화장실 위치 안내",
            "evidence_text": "서울 도심 공중화장실 안내",
            "retrieval_query": "서면역 공중화장실",
        }
        local_candidate = {
            "candidate_source": "web",
            "name": "서면역 공중화장실 위치 안내",
            "evidence_text": "부산 서면역 주변 공중화장실 안내",
            "retrieval_query": "서면역 공중화장실",
        }

        wrong_level, wrong_matched = _external_pre_ai_evidence(wrong_region_candidate, frame)
        local_level, local_matched = _external_pre_ai_evidence(local_candidate, frame)

        self.assertEqual(wrong_level, "medium")
        self.assertTrue(wrong_matched)
        self.assertTrue(all(item["type"] == "retrieval_query_target" for item in wrong_matched))
        self.assertEqual(local_level, "strong")
        self.assertEqual(local_matched[0]["type"], "target_direct")

    def test_external_pre_ai_evidence_uses_ai_target_context_for_kakao_category(self):
        from recommendations.services.ai_search_orchestrator import _external_pre_ai_evidence

        frame = {
            "location_mode": "explicit",
            "anchor_location": "하단역",
            "target_objects": ["베트남 쌀국수 전문점"],
            "result_match_terms": ["쌀국수"],
            "candidate_place_types": ["쌀국수 전문점", "베트남 음식점"],
            "primary_search_queries": ["하단역 쌀국수"],
        }
        candidate = {
            "candidate_source": "kakao",
            "name": "하단 베트남 식당",
            "category": "음식점 > 아시아음식 > 동남아음식 > 베트남음식",
            "address": "부산 사하구 하단동",
            "retrieval_query": "하단역 쌀국수",
        }

        level, matched = _external_pre_ai_evidence(candidate, frame)

        self.assertEqual(level, "medium")
        self.assertTrue(any(item["type"] == "target_context" and item["value"] == "베트남" for item in matched))
        self.assertFalse(all(item["type"] == "retrieval_query_target" for item in matched))

    def test_merge_candidate_policy_review_marks_generic_exclusions(self):
        from recommendations.services.ai_search_orchestrator import _merge_candidate_policy_review

        frame = {
            "target_objects": ["공중화장실"],
            "result_match_terms": ["화장실"],
            "candidate_place_types": ["공중화장실"],
            "exclusions": ["주차장 제외"],
        }
        candidate = {
            "candidate_source": "kakao",
            "name": "지하 공영주차장",
            "category": "교통,수송 > 주차장",
            "address": "부산 부산진구",
        }

        _, _, _, policy_unmet, _ = _merge_candidate_policy_review(
            candidate,
            frame,
            "medium",
            [{"type": "candidate_type", "value": "화장실"}],
            field="kakao_text",
            source_strength="external",
        )

        self.assertTrue(any("주차장" in item for item in policy_unmet))

    def test_search_radius_uses_nearby_constraints_when_request_radius_missing(self):
        from recommendations.services.ai_search_orchestrator import _search_radius_for_frame

        self.assertEqual(
            _search_radius_for_frame(None, {"constraints": ["가까운 곳", "긴급"]}, "근처 화장실 바로 찾아줘"),
            1500,
        )
        self.assertEqual(
            _search_radius_for_frame(None, {"constraints": ["도보 가능한 거리"]}, "걸어서 갈 수 있는 쌀국수집"),
            2000,
        )
        self.assertEqual(
            _search_radius_for_frame(None, {"constraints": ["가까운 곳"]}, "서면역 근처 화장실"),
            3000,
        )
        self.assertEqual(
            _search_radius_for_frame(7000, {"constraints": ["가까운 곳"]}, "서면역 근처 화장실"),
            7000,
        )

    def test_external_verification_ignores_ai_generated_confirmation_constraint(self):
        from recommendations.services.ai_search_orchestrator import _explicit_external_verification_requested

        frame = {
            "constraints": ["방문 전 확인 필요"],
            "result_match_terms": ["화장실"],
        }

        self.assertFalse(_explicit_external_verification_requested("근처 화장실 찾아줘", frame))
        self.assertTrue(_explicit_external_verification_requested("공식 웹에서 최신 정보 확인해줘", frame))

    def test_top_up_ranked_candidates_keeps_excluded_removed(self):
        from recommendations.services.ai_search_orchestrator import _top_up_ranked_candidates

        ranked = [{
            "id": "candidate-0",
            "candidate_source": "kakao",
            "name": "Included",
            "semantic_score": 90,
            "evidence_level": "strong",
        }]
        candidate_pool = [
            *ranked,
            {
                "id": "candidate-1",
                "candidate_source": "kakao",
                "name": "Explicitly Excluded",
                "pre_ai_evidence_level": "strong",
                "score": 72,
            },
            {
                "id": "candidate-2",
                "candidate_source": "kakao",
                "name": "Compatible Candidate",
                "pre_ai_evidence_level": "medium",
                "score": 50,
            },
        ]

        merged, additions = _top_up_ranked_candidates(
            ranked,
            candidate_pool,
            [{"id": "candidate-1"}],
            limit=3,
        )

        self.assertEqual([item["id"] for item in merged], ["candidate-0", "candidate-2"])
        self.assertEqual([item["id"] for item in additions], ["candidate-2"])
        self.assertTrue(additions[0]["verification_required"])
        self.assertEqual(additions[0]["compatibility_gate"], "needs_verification")

    def test_top_up_ranked_candidates_skips_retrieval_query_only_evidence(self):
        from recommendations.services.ai_search_orchestrator import _top_up_ranked_candidates

        merged, additions = _top_up_ranked_candidates(
            [],
            [{
                "id": "candidate-1",
                "candidate_source": "kakao",
                "name": "Collected Only By Query",
                "pre_ai_evidence_level": "medium",
                "score": 50,
                "matched_evidence": [{
                    "type": "retrieval_query_target",
                    "value": "target",
                    "source_strength": "external_query",
                }],
            }],
            [],
            limit=5,
        )

        self.assertEqual(merged, [])
        self.assertEqual(additions, [])

    def test_top_up_ranked_candidates_can_restore_strong_db_direct_evidence(self):
        from recommendations.services.ai_search_orchestrator import _top_up_ranked_candidates

        candidate = {
            "id": "db-restroom",
            "candidate_source": "db",
            "name": "공중화장실",
            "pre_ai_evidence_level": "strong",
            "score": 80,
            "matched_evidence": [{
                "type": "target_direct",
                "field": "name",
                "value": "화장실",
                "source_strength": "verified",
            }],
        }

        merged, additions = _top_up_ranked_candidates(
            [],
            [candidate],
            [{"id": "db-restroom", "reason": "details need verification"}],
            limit=5,
        )

        self.assertEqual([item["id"] for item in merged], ["db-restroom"])
        self.assertEqual([item["id"] for item in additions], ["db-restroom"])
        self.assertEqual(additions[0]["compatibility_gate"], "needs_verification")

    def test_retrieval_query_only_candidate_is_filtered_before_rerank(self):
        from recommendations.services.ai_search_orchestrator import _has_only_retrieval_query_evidence

        self.assertTrue(_has_only_retrieval_query_evidence({
            "matched_evidence": [{
                "type": "retrieval_query_target",
                "value": "target",
                "source_strength": "external_query",
            }],
        }))
        self.assertFalse(_has_only_retrieval_query_evidence({
            "matched_evidence": [{
                "type": "target_direct",
                "value": "target",
                "source_strength": "external",
            }],
        }))

    def test_db_evidence_terms_prefer_specific_target_over_broad_context(self):
        from recommendations.services.ai_search_orchestrator import _db_evidence_terms

        frame = {
            "anchor_location": "\ud558\ub2e8\uc5ed",
            "target_objects": [
                "\ud558\ub2e8\uc5ed \uadfc\ucc98 \uc300\uad6d\uc218 \ub9db\uc9d1 \uc880 \ucc3e\uc544\uc918 \ub108\ubb34 \uba40\uc9c0 \uc54a\uc740 \ub370\ub85c"
            ],
            "result_match_terms": ["\ub9db\uc9d1"],
            "candidate_place_types": ["\uce74\ud398"],
            "constraints": ["\ub108\ubb34 \uba40\uc9c0 \uc54a\uc740 \ub370\ub85c"],
        }

        terms = _db_evidence_terms(frame)

        self.assertIn("\uc300\uad6d\uc218", terms["target"])
        self.assertEqual(terms["search"], ["\uc300\uad6d\uc218"])
        self.assertNotIn("\uce74\ud398", terms["search"])
        self.assertNotIn("\ub9db\uc9d1", terms["search"])

    def test_db_evidence_terms_drop_place_descriptors_when_result_supports_core_target(self):
        from recommendations.services.ai_search_orchestrator import _db_evidence_terms

        frame = {
            "anchor_location": "하단역",
            "target_objects": ["쌀국수 전문점", "베트남 쌀국수집"],
            "result_match_terms": ["쌀국수", "포", "맛집"],
            "candidate_place_types": ["쌀국수 전문점", "아시아 음식점"],
            "constraints": ["도보 가능한 거리"],
            "primary_search_queries": ["하단역 쌀국수 전문점", "하단역 도보 쌀국수 맛집"],
        }

        terms = _db_evidence_terms(frame)

        self.assertEqual(terms["search"], ["쌀국수"])
        self.assertNotIn("전문점", terms["search"])

    def test_db_evidence_terms_remove_auxiliary_words_from_long_facility_request(self):
        from recommendations.services.ai_search_orchestrator import _db_evidence_terms

        frame = {
            "location_mode": "current_context",
            "target_objects": [
                "\uc9c0\uae08 \ub108\ubb34 \uae09\ud55c\ub370 \uadfc\ucc98 \ud654\uc7a5\uc2e4 \ubc14\ub85c \uac08 \uc218 \uc788\ub294 \uacf3 \ucc3e\uc544\uc918"
            ],
            "result_match_terms": ["\ud654\uc7a5\uc2e4"],
            "candidate_place_types": ["\uacf5\uc911\ud654\uc7a5\uc2e4"],
            "constraints": ["\uac00\uae4c\uc6b4 \uacf3"],
        }

        terms = _db_evidence_terms(frame)

        self.assertEqual(terms["search"], ["\ud654\uc7a5\uc2e4"])
        self.assertNotIn("\uc218", terms["search"])
        self.assertNotIn("\uc788\ub294", terms["search"])
        self.assertNotIn("\uac08", terms["search"])

    def test_db_evidence_terms_prefer_restroom_core_over_access_place_types(self):
        from recommendations.services.ai_search_orchestrator import _db_evidence_terms

        frame = {
            "location_mode": "current_context",
            "target_objects": ["공중화장실", "편의점 화장실", "카페 화장실", "지하철역 화장실"],
            "result_match_terms": ["남녀구분 화장실", "장애인화장실", "24시간", "즉시 이용 가능"],
            "candidate_place_types": ["공중화장실", "편의점", "카페", "지하철역"],
            "constraints": ["가까운 곳"],
            "primary_search_queries": [
                "공중화장실 현재 위치 인근",
                "편의점 화장실 현재 위치 인근 24시간",
                "카페 화장실 현재 위치 인근 영업중",
            ],
        }

        terms = _db_evidence_terms(frame)

        self.assertEqual(terms["search"], ["화장실"])
        for unrelated in ["편의점", "카페", "지하철역", "24시간", "즉시", "이용", "가능"]:
            self.assertNotIn(unrelated, terms["search"])

    def test_db_evidence_terms_keep_smoking_facility_terms_not_activity_modifiers(self):
        from recommendations.services.ai_search_orchestrator import _db_evidence_terms

        frame = {
            "location_mode": "explicit",
            "anchor_location": "부산 연산동",
            "target_objects": ["흡연실", "실외 흡연구역", "흡연 가능한 야외 테라스"],
            "result_match_terms": ["흡연실", "흡연구역", "담배", "흡연 가능", "실외 흡연"],
            "candidate_place_types": ["흡연실(공용)", "흡연구역(도로변/공원)", "카페 테라스 내 지정 흡연실"],
            "constraints": [],
            "primary_search_queries": ["연산동 흡연실", "연산동 흡연구역", "연산동 지정 흡연부스"],
        }

        terms = _db_evidence_terms(frame)

        self.assertIn("흡연실", terms["search"])
        self.assertIn("흡연구역", terms["search"])
        for unrelated in ["담배", "가능", "가능한", "야외", "실외", "테라스"]:
            self.assertNotIn(unrelated, terms["search"])

    def test_db_evidence_terms_keep_explicit_walk_target_place_type(self):
        from recommendations.services.ai_search_orchestrator import _db_evidence_terms

        frame = {
            "location_mode": "current_context",
            "target_objects": ["산책로", "공원", "강변 산책로"],
            "result_match_terms": ["산책하기 좋은", "경치 좋은", "평탄한 길"],
            "candidate_place_types": ["공원", "도시산책로", "하천변 산책로", "숲길"],
            "constraints": ["도보 접근 가능"],
            "primary_search_queries": [
                "산책로 가까운 공원",
                "도심 가까운 숲길 산책로",
                "강변 산책로 근처",
            ],
        }

        terms = _db_evidence_terms(frame)

        self.assertEqual(terms["search"], ["산책로", "공원"])
        self.assertNotIn("도보", terms["search"])
        self.assertNotIn("가능", terms["search"])

    def test_collect_db_candidates_does_not_pull_cafe_from_candidate_type_when_target_is_specific(self):
        from recommendations.services.ai_search_orchestrator import collect_db_candidates

        rice_noodle_place = self._create_place(
            name="\ud558\ub2e8 \uc300\uad6d\uc218 \uc804\ubb38\uc810",
            category="restaurant",
            external_id="specific-rice-noodle-db",
            lat=35.106,
            lng=128.966,
            data_quality_score=70,
        )
        self._add_tag(rice_noodle_place, "\uc300\uad6d\uc218", is_verified=True)
        unrelated_cafe = self._create_place(
            name="\ub514\uc800\ud2b8 \uce74\ud398",
            category="cafe",
            external_id="unrelated-cafe-db",
            lat=35.1062,
            lng=128.9662,
            data_quality_score=95,
        )
        self._add_tag(unrelated_cafe, "\uce74\ud398", is_verified=False)
        self._add_tag(unrelated_cafe, "\ub9db\uc9d1", is_verified=False)

        frame = {
            "anchor_location": "\ud558\ub2e8\uc5ed",
            "target_objects": ["\uc300\uad6d\uc218"],
            "result_match_terms": ["\ub9db\uc9d1"],
            "candidate_place_types": ["\uce74\ud398"],
            "constraints": ["\ub108\ubb34 \uba40\uc9c0 \uc54a\uc740 \ub370\ub85c"],
        }

        candidates = collect_db_candidates(
            frame,
            lat=35.106,
            lng=128.966,
            limit=10,
            radius=2000,
        )
        candidate_names = [candidate["name"] for candidate in candidates]

        self.assertIn(rice_noodle_place.name, candidate_names)
        self.assertNotIn(unrelated_cafe.name, candidate_names)

    def test_collect_db_candidates_uses_smoking_frame_terms_without_outdoor_cafe_bleed(self):
        from recommendations.services.ai_search_orchestrator import collect_db_candidates

        smoking_place = self._create_place(
            name="연산 테스트 흡연구역",
            category="smoking_area",
            external_id="specific-smoking-area-db",
            lat=35.18,
            lng=129.08,
            data_quality_score=70,
        )
        self._add_tag(smoking_place, "실외흡연구역", is_verified=True)
        outdoor_cafe = self._create_place(
            name="연산 야외 카페",
            category="cafe",
            external_id="outdoor-cafe-not-smoking-db",
            lat=35.1802,
            lng=129.0802,
            data_quality_score=95,
        )
        self._add_tag(outdoor_cafe, "야외좌석", is_verified=True)

        frame = {
            "anchor_location": "부산 연산동",
            "target_objects": ["흡연실", "실외 흡연구역", "흡연 가능한 야외 공간"],
            "result_match_terms": ["흡연실", "흡연구역", "담배", "흡연 가능", "실외 흡연"],
            "candidate_place_types": ["흡연실(공용)", "흡연구역(도로변/공원)", "카페/시설 내 지정 흡연실"],
            "constraints": [],
            "primary_search_queries": ["연산동 흡연실", "연산동 흡연구역"],
        }

        candidates = collect_db_candidates(
            frame,
            lat=35.18,
            lng=129.08,
            limit=10,
            radius=2000,
        )
        candidate_names = [candidate["name"] for candidate in candidates]

        self.assertIn(smoking_place.name, candidate_names)
        self.assertNotIn(outdoor_cafe.name, candidate_names)

    def test_collect_db_candidates_prioritizes_structured_smoking_category_before_global_slice(self):
        from recommendations.services.ai_search_orchestrator import collect_db_candidates

        for index in range(130):
            Place.objects.create(
                name=f"원거리 흡연구역 {index}",
                category="smoking_area",
                address="서울특별시 테스트구 원거리로 1",
                lat=37.55 + (index * 0.0001),
                lng=126.98,
                source="test",
                external_id=f"far-smoking-area-{index}",
                source_name="서울특별시 흡연구역 현황",
                data_quality_score=99,
            )
        nearby_place = Place.objects.create(
            name="연산 공식 흡연실",
            category="smoking_area",
            address="연제구 연제로 2(연산동)",
            detail_location="연제구 연제로 2(연산동)",
            lat=35.1762,
            lng=129.0797,
            source="test",
            external_id="nearby-yeonsan-smoking-room",
            source_name="부산광역시 연제구_흡연실 현황_20250905",
            data_quality_score=10,
        )

        frame = {
            "anchor_location": "부산 연산동",
            "target_objects": ["흡연구역"],
            "result_match_terms": ["흡연구역"],
            "candidate_category_codes": ["smoking_area"],
            "candidate_place_types": ["흡연구역"],
            "constraints": [],
            "primary_search_queries": ["연산동 흡연구역"],
        }

        candidates = collect_db_candidates(
            frame,
            lat=35.176,
            lng=129.08,
            limit=10,
            radius=2000,
        )
        nearby_candidate = next(
            candidate
            for candidate in candidates
            if candidate["place_id"] == nearby_place.id
        )

        self.assertEqual(nearby_candidate["pre_ai_evidence_level"], "strong")
        self.assertIn(
            {
                "type": "structured_category_direct",
                "field": "category",
                "value": "smoking_area",
                "source_strength": "verified",
            },
            nearby_candidate["matched_evidence"],
        )

    def test_db_evidence_uses_frame_candidate_type_category_label_without_db_first(self):
        from recommendations.services.ai_search_orchestrator import _db_evidence

        park = self._create_place(
            name="신호공원",
            category="city_park",
            external_id="walk-category-label-park",
            lat=35.096,
            lng=128.854,
            data_quality_score=70,
        )
        frame = {
            "location_mode": "current_context",
            "target_objects": ["산책로", "공원"],
            "result_match_terms": ["산책하기 좋은", "경치 좋은"],
            "candidate_place_types": ["공원", "도시산책로", "숲길"],
            "constraints": ["도보 접근 가능"],
            "primary_search_queries": ["산책로 가까운 공원"],
        }

        level, matched, policy_unmet, policy_verification_needed = _db_evidence(
            park,
            {
                "verified": [],
                "suggested": [],
                "candidate": [],
                "warning": [],
            },
            frame,
        )

        self.assertEqual(level, "weak")
        self.assertEqual(policy_unmet, [])
        self.assertEqual(policy_verification_needed, [])
        self.assertTrue(any(
            item["type"] == "category_label" and item["label"] == "공원"
            for item in matched
        ))
        self.assertFalse(any(
            item["type"] == "structured_category_direct"
            for item in matched
        ))

    def test_collect_db_candidates_marks_smoking_indoor_outdoor_policy(self):
        from recommendations.services.ai_search_orchestrator import collect_db_candidates

        outdoor_place = self._create_place(
            name="연산 실외 흡연구역",
            category="smoking_area",
            external_id="outdoor-smoking-policy-db",
            lat=35.176,
            lng=129.08,
            data_quality_score=50,
        )
        self._add_tag(outdoor_place, "실외흡연구역", is_verified=True)
        indoor_place = self._create_place(
            name="연산 실내 흡연실",
            category="smoking_area",
            external_id="indoor-smoking-policy-db",
            lat=35.1761,
            lng=129.0801,
            data_quality_score=99,
        )
        self._add_tag(indoor_place, "실내흡연실", is_verified=True)

        frame = {
            "anchor_location": "부산 연산동",
            "target_objects": ["흡연구역"],
            "result_match_terms": ["흡연구역", "실외 흡연"],
            "candidate_category_codes": ["smoking_area"],
            "candidate_place_types": ["흡연구역", "흡연부스"],
            "constraints": ["밖에서 이용 가능"],
            "exclusions": ["음식점 내부"],
            "primary_search_queries": ["연산동 흡연구역"],
        }

        candidates = collect_db_candidates(
            frame,
            lat=35.176,
            lng=129.08,
            limit=10,
            radius=2000,
        )
        by_id = {candidate["place_id"]: candidate for candidate in candidates}
        outdoor_candidate = by_id[outdoor_place.id]
        indoor_candidate = by_id[indoor_place.id]

        self.assertIn("실외/외부 이용", outdoor_candidate["policy_matched_constraints"])
        self.assertEqual(outdoor_candidate["pre_ai_unmet_constraints"], [])
        self.assertTrue(any(
            item["type"] == "policy_constraint"
            for item in outdoor_candidate["matched_evidence"]
        ))
        self.assertIn("실외/외부 이용 요청", indoor_candidate["pre_ai_unmet_constraints"][0])
        self.assertEqual(indoor_candidate["confidence"], "low")
        self.assertLess(indoor_candidate["score"], outdoor_candidate["score"])

    def test_top_up_ranked_candidates_skips_smoking_policy_conflict(self):
        from recommendations.services.ai_search_orchestrator import _top_up_ranked_candidates

        conflict_candidate = {
            "id": "db:indoor-smoking-room",
            "candidate_source": "db",
            "source": "db",
            "name": "실내 흡연실",
            "pre_ai_evidence_level": "strong",
            "evidence_level": "strong",
            "score": 80,
            "matched_evidence": [
                {
                    "type": "structured_category_direct",
                    "field": "category",
                    "value": "smoking_area",
                    "source_strength": "verified",
                }
            ],
            "pre_ai_unmet_constraints": ["실외/외부 이용 요청과 다른 실내 이용 정보"],
        }
        matched_candidate = {
            **conflict_candidate,
            "id": "db:outdoor-smoking-area",
            "name": "실외 흡연구역",
            "pre_ai_unmet_constraints": [],
            "policy_matched_constraints": ["실외/외부 이용"],
        }

        ranked, additions = _top_up_ranked_candidates(
            [],
            [conflict_candidate, matched_candidate],
            [],
            limit=2,
        )

        self.assertEqual([candidate["id"] for candidate in ranked], ["db:outdoor-smoking-area"])
        self.assertEqual([candidate["id"] for candidate in additions], ["db:outdoor-smoking-area"])

    def test_broad_place_target_is_not_actionable_search_target(self):
        from recommendations.services.ai_search_orchestrator import _has_actionable_place_target

        self.assertFalse(_has_actionable_place_target({
            "target_objects": ["갈 만한 곳"],
            "result_match_terms": ["장소"],
            "candidate_place_types": ["추천 장소"],
            "primary_search_queries": ["해운대역 갈 만한 곳"],
        }))

    def test_specific_target_with_place_suffix_is_still_actionable(self):
        from recommendations.services.ai_search_orchestrator import _has_actionable_place_target

        self.assertTrue(_has_actionable_place_target({
            "target_objects": ["\ud761\uc5f0 \uc7a5\uc18c"],
            "result_match_terms": ["\ud761\uc5f0"],
            "candidate_place_types": ["\ud761\uc5f0\uad6c\uc5ed"],
            "primary_search_queries": ["\ud761\uc5f0\uad6c\uc5ed"],
        }))
        self.assertTrue(_has_actionable_place_target({
            "target_objects": ["\uc2e4\ub0b4 \ub300\uae30 \uacf5\uac04"],
            "result_match_terms": ["\ube44 \ud53c\ud560 \uacf3"],
            "candidate_place_types": ["\uc2e4\ub0b4 \uacf5\uac04"],
            "primary_search_queries": ["\uc2e4\ub0b4 \ub300\uae30 \uacf5\uac04"],
        }))

    def test_under_specified_place_request_requires_clarification(self):
        from recommendations.services.ai_search_orchestrator import _is_under_specified_place_request

        self.assertTrue(_is_under_specified_place_request(
            "해운대역 근처에서 어디 좀 갈 만한 곳 있어?",
            {
                "target_objects": ["카페"],
                "result_match_terms": ["카페"],
                "candidate_place_types": ["카페"],
                "constraints": [],
                "exclusions": [],
            },
        ))
        self.assertFalse(_is_under_specified_place_request(
            "비가 와서 해운대역 근처에서 잠깐 피할 곳 찾아줘",
            {
                "target_objects": ["실내 대기 공간"],
                "result_match_terms": ["비 피할 곳"],
                "candidate_place_types": ["실내 공간"],
                "constraints": ["비 피하기"],
                "exclusions": [],
            },
        ))

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_intent_planner._call_gms_chat_json")
    def test_ai_intent_planner_repairs_non_place_clarification_to_out_of_scope(self, mock_ai):
        from recommendations.services.ai_intent_planner import build_ai_intent_plan

        mock_ai.side_effect = [
            {
                "action": "ask_clarification",
                "normalized_query": "weather information",
                "frame": {
                    "location_mode": "clarification_required",
                    "anchor_location": "",
                    "target_objects": [],
                    "candidate_place_types": [],
                    "result_match_terms": [],
                    "constraints": [],
                    "exclusions": [],
                    "ranking_policy": "evidence_first",
                    "primary_search_queries": [],
                    "secondary_search_queries": [],
                },
                "clarification": {
                    "question": "Which region should I use for the information?",
                    "options": [],
                    "missing_fields": ["location"],
                    "expected_patch_fields": ["anchor_location"],
                },
                "confidence": 0.7,
            },
            {
                "action": "out_of_scope",
                "normalized_query": "weather information",
                "frame": {
                    "location_mode": "clarification_required",
                    "anchor_location": "",
                    "target_objects": [],
                    "candidate_place_types": [],
                    "result_match_terms": [],
                    "constraints": [],
                    "exclusions": [],
                    "ranking_policy": "evidence_first",
                    "primary_search_queries": [],
                    "secondary_search_queries": [],
                },
                "clarification": {},
                "confidence": 0.9,
            },
        ]

        plan = build_ai_intent_plan("weather information", lat=35.1, lng=129.1)

        self.assertEqual(plan["decision_action"], "out_of_scope")
        self.assertFalse(plan["can_search_now"])
        self.assertEqual(plan["ai_debug"]["planner"]["status"], "repaired")
        self.assertIn("non_place_clarification", plan["ai_debug"]["planner"]["validation_errors"])
        self.assertEqual(mock_ai.call_count, 2)

    def test_external_frame_evidence_candidate_sorts_above_db_weak_high_score(self):
        from recommendations.views import (
            _merge_and_sort_recommendation_results,
            _normalize_kakao_external_candidate,
        )

        db_weak = {
            "id": 999,
            "name": "태그 많은 DB 후보",
            "source_type": "db_category_fallback",
            "frame_match_strength": "weak",
            "fallback_level": 5,
            "score": 99,
            "score_breakdown": {
                "score_cap_reasons": ["frame_weak_category_fallback"],
            },
        }
        frame = {
            "target_objects": ["먹기"],
            "result_match_terms": ["먹기"],
            "candidate_place_types": ["식당"],
            "search_queries": ["식당"],
            "evidence": [{"type": "clarification_answer", "value": "먹기"}],
        }
        kakao_candidate = _normalize_kakao_external_candidate(
            {
                "id": "external-1",
                "place_name": "테스트 식당",
                "category_name": "음식점",
                "address_name": "부산 테스트 1",
                "road_address_name": "부산 테스트로 1",
                "x": "129.0",
                "y": "35.1",
                "distance": "200",
                "place_url": "https://place.map.kakao.com/external-1",
            },
            frame,
            "식당",
        )

        merged = _merge_and_sort_recommendation_results(
            [db_weak],
            [kakao_candidate],
            ranking_policy="evidence_first",
        )

        self.assertEqual(merged[0]["source_type"], "kakao_candidate")
        self.assertIn(merged[0]["frame_match_strength"], {"strong", "medium"})
        self.assertEqual(merged[1]["source_type"], "db_category_fallback")

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    @patch("recommendations.views.search_places_by_keyword")
    def test_ai_search_merges_kakao_strong_candidate_above_db_weak_fallback(self, mock_kakao):
        db_place = self._create_place(
            name="사상역 테스트 음식점",
            category="restaurant",
            external_id="frame-rice-noodle-db-weak",
            data_quality_score=80,
        )
        mock_kakao.return_value = {
            "documents": [
                {
                    "id": "123456789",
                    "place_name": "사상역 쌀국수 테스트",
                    "category_name": "음식점 > 베트남음식",
                    "address_name": "부산 사상구 테스트동 1",
                    "road_address_name": "부산 사상구 테스트로 1",
                    "x": "128.984",
                    "y": "35.162",
                    "distance": "120",
                    "place_url": "https://place.map.kakao.com/123456789",
                },
            ],
        }
        frame = {
            "decision_action": "search",
            "user_goal": "사상역 근처 쌀국수 맛집 찾기",
            "anchor_location": "사상역",
            "location_mode": "explicit",
            "situation": "food",
            "display_label": "쌀국수 맛집",
            "target_objects": ["쌀국수"],
            "candidate_category_codes": ["restaurant"],
            "candidate_place_types": ["베트남음식", "식당"],
            "search_queries": ["사상역 쌀국수", "사상역 베트남음식", "사상역 쌀국수 맛집"],
            "result_match_terms": ["쌀국수", "베트남음식"],
            "constraints": [],
            "exclusions": [],
            "preferred_place_natures": [],
            "excluded_place_natures": [],
            "ranking_policy": "evidence_first",
            "missing_info": [],
            "confidence": 0.9,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="사상역 근처 쌀국수 맛집"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["unified_candidate_pipeline"])
        self.assertTrue(data["external_search_triggered"])
        self.assertEqual(data["external_search_reason"], "unified_candidate_collectors")
        self.assertGreaterEqual(data["external_candidate_count"], 1)
        self.assertEqual(data["results"][0]["source_type"], "kakao_candidate")
        self.assertTrue(data["results"][0]["is_external"])
        self.assertTrue(data["results"][0]["can_show_on_map"])
        self.assertEqual(data["results"][0]["frame_match_strength"], "strong")
        self.assertIn("확인", data["results"][0]["caution_message"])
        self.assertIn(db_place.id, [result["id"] for result in data["hidden_weak_candidates"]])
        self.assertNotIn(db_place.id, [result["id"] for result in data["results"]])

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    @patch("recommendations.views.search_places_by_keyword")
    def test_db_suggested_tag_only_is_not_strong_evidence(self, mock_kakao):
        mock_kakao.return_value = {"documents": []}
        verified_place = self._create_place(
            name="검증 태그 식당",
            category="restaurant",
            external_id="db-verified-direct-evidence",
            data_quality_score=60,
        )
        self._add_tag(verified_place, "쌀국수", is_verified=True)
        suggested_place = self._create_place(
            name="후보 태그 식당",
            category="restaurant",
            external_id="db-suggested-direct-evidence",
            data_quality_score=99,
        )
        self._add_tag(suggested_place, "쌀국수", is_verified=False, status="candidate")
        frame = {
            "decision_action": "search",
            "user_goal": "쌀국수 맛집 찾기",
            "anchor_location": "사상역",
            "location_mode": "explicit",
            "situation": "food",
            "display_label": "쌀국수 맛집",
            "target_objects": ["쌀국수"],
            "candidate_category_codes": ["restaurant"],
            "candidate_place_types": ["음식점"],
            "search_queries": ["사상역 쌀국수", "사상역 베트남음식", "사상역 쌀국수 맛집"],
            "result_match_terms": ["쌀국수", "베트남음식", "음식점"],
            "constraints": [],
            "exclusions": [],
            "preferred_place_natures": [],
            "excluded_place_natures": [],
            "ranking_policy": "evidence_first",
            "missing_info": [],
            "confidence": 0.9,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="사상역 근처 쌀국수 맛집"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]
        self.assertIn(verified_place.id, result_ids, data)
        self.assertIn(suggested_place.id, result_ids, data)
        verified_result = next(result for result in data["results"] if result["id"] == verified_place.id)
        suggested_result = next(result for result in data["results"] if result["id"] == suggested_place.id)

        self.assertLess(result_ids.index(verified_place.id), result_ids.index(suggested_place.id))
        self.assertEqual(verified_result["frame_evidence_tier"], "verified_direct")
        self.assertEqual(verified_result["frame_match_strength"], "strong")
        self.assertEqual(verified_result["fallback_label"], "추천 근거 높음")
        self.assertEqual(suggested_result["frame_evidence_tier"], "suggested_direct")
        self.assertEqual(suggested_result["frame_match_strength"], "medium")
        self.assertEqual(suggested_result["fallback_label"], "추천 후보, 확인 필요")
        self.assertIn(
            "frame_suggested_direct_needs_verification",
            suggested_result["score_breakdown"]["score_cap_reasons"],
        )

    def test_web_external_candidate_without_coordinates_cannot_show_on_map(self):
        from recommendations.views import _normalize_web_external_candidate

        frame = {
            "target_objects": ["쌀국수"],
            "candidate_place_types": ["베트남음식", "식당"],
            "result_match_terms": ["쌀국수", "베트남음식"],
        }
        candidate = {
            "name": "사상역 쌀국수 참고 링크",
            "summary": "사상역 쌀국수 관련 검색 결과입니다.",
            "source_url": "https://example.com/rice-noodle",
        }

        normalized = _normalize_web_external_candidate(candidate, frame)

        self.assertEqual(normalized["source_type"], "web_evidence_candidate")
        self.assertTrue(normalized["is_external"])
        self.assertFalse(normalized["can_show_on_map"])
        self.assertIsNone(normalized["lat"])
        self.assertIsNone(normalized["lng"])
        self.assertIn("지도 표시는", normalized["caution_message"])

    @patch("recommendations.views.search_db_recommendations", side_effect=AssertionError("legacy DB recommender must not run"))
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", side_effect=AssertionError("Kakao collector must not run for clarification"))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", side_effect=AssertionError("DB collector must not run for clarification"))
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_decision_gate_request_returns_empty_results_without_db_search(
        self,
        mock_intent,
        mock_db_collector,
        mock_kakao_collector,
        mock_legacy_db,
    ):
        mock_intent.return_value = {
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "normalized_query": "어디 갈만한 데",
            "frame": {
                "location_mode": "clarification_required",
                "anchor_location": "",
                "target_objects": [],
                "candidate_place_types": [],
                "result_match_terms": [],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": [],
                "secondary_search_queries": [],
            },
            "clarification": {
                "question": "어떤 상황에서 갈 장소를 찾으시나요?",
                "options": [],
                "missing_fields": ["target_objects"],
                "expected_patch_fields": ["target_objects"],
            },
            "confidence": 0.4,
            "ai_retry_count": 0,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "어디 갈만한 데", "lat": 35.1, "lng": 129.0}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["type"], "clarification")
        self.assertEqual(data["decision_action"], "ask_clarification")
        self.assertFalse(data["can_search_now"])
        self.assertEqual(data["results"], [])
        self.assertEqual(data["markers"], [])
        self.assertEqual(data["result_count"], 0)
        self.assertEqual(data["relevant_result_count"], 0)
        self.assertFalse(data["execution_policy"]["run_search"])
        self.assertFalse(data["debug_pipeline"]["legacy_path_used"])
        mock_legacy_db.assert_not_called()
        mock_db_collector.assert_not_called()
        mock_kakao_collector.assert_not_called()

    def test_ai_search_ai_failure_fallback_does_not_collect_broad_candidates(self):
        fallback_frame = {
            "decision_action": "search",
            "user_goal": "legacy fallback frame",
            "anchor_location": "사상역",
            "location_mode": "explicit",
            "situation": "food",
            "display_label": "쌀국수 맛집",
            "target_objects": ["쌀국수 맛집"],
            "candidate_category_codes": ["restaurant", "cafe"],
            "candidate_place_types": ["식당", "음식점", "카페"],
            "search_queries": ["사상역 식당", "사상역 음식점", "사상역 카페"],
            "result_match_terms": ["식당", "음식점", "카페"],
            "constraints": [],
            "exclusions": [],
            "ranking_policy": "evidence_first",
            "confidence": 0.3,
        }
        fallback_plan = {
            "action": "search",
            "decision_action": "search",
            "parser_fallback": True,
            "plan_source": "legacy_fallback",
            "ai_fallback_reason": "ai_call_failed:ConnectionError",
            "search_plan": {
                "scenario": "food",
                "execution_mode": "frame",
                "parser_fallback": True,
                "plan_source": "legacy_fallback",
                "ai_fallback_reason": "ai_call_failed:ConnectionError",
                "locationQuery": "사상역",
                "place_intent_frame": fallback_frame,
            },
        }

        with patch("recommendations.views.parse_situation", return_value={
            "scenario": "custom",
            "situation_summary": "사상역 근처 쌀국수 맛집",
            "is_searchable": True,
            "blocked": False,
        }), patch("recommendations.views.build_conversational_search_plan", return_value=fallback_plan), patch(
            "recommendations.views.search_db_recommendations"
        ) as mock_db_search, patch("recommendations.views.search_places_by_keyword") as mock_kakao_search:
            response = self.client.post(
                "/api/recommendations/ai-search/",
                data=json.dumps({
                    "query": "사상역 근처 쌀국수 맛집",
                    "lat": 35.1556,
                    "lng": 129.0641,
                    "limit": 10,
                }, ensure_ascii=False),
                content_type="application/json",
                **self._auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "ai_unavailable")
        self.assertEqual(data["results"], [])
        self.assertEqual(data["markers"], [])
        self.assertTrue(data["debug_pipeline"]["ai_call_failed"])
        self.assertFalse(data["debug_pipeline"]["legacy_path_used"])
        self.assertFalse(data["debug_pipeline"]["has_actionable_place_target"])
        self.assertEqual(data["debug_pipeline"]["candidate_counts"]["db"], 0)
        self.assertFalse(data["debug_pipeline"]["fallback_created_candidates"])
        self.assertEqual(data["debug_pipeline"]["evidence_terms"]["fallback_placeholder"], [])
        self.assertEqual(data["debug_pipeline"]["evidence_terms"]["legacy_inferred"], [])
        self.assertEqual(data["debug_pipeline"]["evidence_terms"]["broad_default"], [])
        self.assertEqual(data["debug_pipeline"]["query_generation"]["primary_queries"], [])
        mock_db_search.assert_not_called()
        mock_kakao_search.assert_not_called()

    def test_query_generation_blocks_fallback_sources_and_raw_query_repeat(self):
        from recommendations.views import _query_generation_from_frame

        frame = {
            "anchor_location": "사상역",
            "location_mode": "explicit",
            "target_objects": [{"value": "쌀국수", "source": "user_explicit"}],
            "result_match_terms": [{"value": "쌀국수", "source": "user_explicit"}],
            "candidate_place_types": [{"value": "음식점", "source": "fallback_placeholder"}],
            "search_queries": [
                {"query": "사상역 쌀국수", "source": "user_explicit"},
                {"query": "사상역 음식점", "source": "fallback_placeholder"},
            ],
        }

        generation = _query_generation_from_frame(
            {"plan_source": "legacy_fallback", "parser_fallback": True},
            frame,
            fallback_query="사상역 근처 쌀국수 맛집",
        )

        self.assertEqual(generation["primary_queries"], ["사상역 쌀국수"])
        blocked_queries = [item["query"] for item in generation["blocked_queries"]]
        self.assertIn("사상역 음식점", blocked_queries)
        self.assertIn("사상역 근처 쌀국수 맛집", blocked_queries)
        self.assertNotIn("사상역 음식점", generation["primary_queries"])

    def test_query_generation_treats_clarification_followup_as_trusted_patch(self):
        from recommendations.views import _query_generation_from_frame

        frame = {
            "anchor_location": "하단역",
            "location_mode": "explicit",
            "target_objects": ["화장실"],
            "result_match_terms": ["화장실"],
            "candidate_place_types": ["공중화장실"],
            "search_queries": ["하단역 화장실"],
            "evidence": [{"type": "clarification_answer", "value": "화장실"}],
        }

        generation = _query_generation_from_frame(
            {
                "plan_source": "clarification_follow_up",
                "parser_fallback": True,
                "originalQuery": "하단역 근처 어디 갈만한 데",
            },
            frame,
            fallback_query="화장실",
        )

        self.assertIn("하단역 화장실", generation["primary_queries"])
        blocked_queries = [item["query"] for item in generation["blocked_queries"]]
        self.assertNotIn("하단역 화장실", blocked_queries)
        self.assertIn("화장실", blocked_queries)

    def test_query_generation_blocks_broad_default_sources_for_specific_target(self):
        from recommendations.views import _query_generation_from_frame

        frame = {
            "anchor_location": "사상역",
            "location_mode": "explicit",
            "target_objects": ["쌀국수"],
            "result_match_terms": ["쌀국수", "베트남음식", "음식점"],
            "candidate_place_types": ["식당", "음식점", "카페"],
            "search_queries": ["사상역 쌀국수", "사상역 식당", "사상역 cafe"],
        }
        generation = _query_generation_from_frame(
            {
                "plan_source": "ai",
                "parser_fallback": False,
                "originalQuery": "사상역 근처 쌀국수 맛집",
            },
            frame,
            fallback_query="사상역 근처 쌀국수 맛집",
        )

        self.assertIn("사상역 쌀국수", generation["primary_queries"])
        self.assertIn("사상역 베트남음식", generation["primary_queries"])
        self.assertNotIn("사상역 식당", generation["primary_queries"])
        self.assertNotIn("사상역 음식점", generation["primary_queries"])
        self.assertNotIn("사상역 cafe", generation["primary_queries"])
        blocked_queries = [item["query"] for item in generation["blocked_queries"]]
        self.assertIn("사상역 식당", blocked_queries)
        self.assertIn("사상역 cafe", blocked_queries)

    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", side_effect=AssertionError("Kakao collector must not run for AI clarification"))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", side_effect=AssertionError("DB collector must not run for AI clarification"))
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_ai_success_broad_default_frame_asks_without_collectors(
        self,
        mock_intent,
        mock_db,
        mock_kakao,
    ):
        mock_intent.return_value = {
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "normalized_query": "허리가 아픈 상황에서 필요한 장소 확인",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": [],
                "candidate_place_types": [],
                "result_match_terms": [],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": [],
                "secondary_search_queries": [],
            },
            "clarification": {
                "question": "병원이나 약국을 찾으시나요, 아니면 잠깐 쉬어갈 장소를 찾으시나요?",
                "options": ["병원 찾기", "약국 찾기", "잠깐 쉴 곳 찾기"],
                "missing_fields": ["target_objects"],
                "expected_patch_fields": ["target_objects"],
            },
            "confidence": 0.45,
            "ai_retry_count": 0,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "허리가 아프네", "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "ask_clarification")
        self.assertEqual(data["results"], [])
        self.assertEqual(data["markers"], [])
        self.assertFalse(data["execution_policy"]["run_search"])
        self.assertFalse(data["debug_pipeline"]["fallback_created_candidates"])
        mock_db.assert_not_called()
        mock_kakao.assert_not_called()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_SEARCH_MIN_STRONG_MEDIUM_CANDIDATES=0,
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], [{"query": "사상역 쌀국수", "count": 0}]))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", return_value=[])
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_specific_target_debug_marks_broad_defaults(
        self,
        mock_intent,
        mock_db,
        mock_kakao,
        mock_rerank,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "사상역 근처 쌀국수 맛집",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["쌀국수"],
                "candidate_place_types": ["베트남음식"],
                "result_match_terms": ["쌀국수", "베트남음식"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["사상역 쌀국수"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }
        mock_rerank.return_value = ([], {
            "status": "executed",
            "input_count": 0,
            "included_count": 0,
            "excluded_count": 0,
            "excluded_candidates": [],
        })

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "사상역 근처 쌀국수 맛집", "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["debug_pipeline"]["legacy_path_used"])
        self.assertIn("사상역 쌀국수", data["debug_pipeline"]["query_generation"]["primary_queries"])
        self.assertNotIn("사상역 restaurant", data["debug_pipeline"]["query_generation"]["primary_queries"])
        self.assertNotIn("사상역 카페", data["debug_pipeline"]["query_generation"]["primary_queries"])
        self.assertEqual(data["debug_pipeline"]["query_generation"]["blocked_queries"], [])
        self.assertEqual(data["debug_pipeline"]["evidence_terms"]["broad_default"], [])
        mock_db.assert_called_once()
        mock_kakao.assert_called_once()
        mock_rerank.assert_not_called()
        self.assertEqual(data["debug_pipeline"]["reranker"]["status"], "skipped")
        self.assertEqual(data["debug_pipeline"]["reranker"]["reason"], "no_candidates_collected")
        self.assertTrue(data["frontend_should_preserve_order"])

    def test_fallback_placeholder_is_not_displayed_as_matched_evidence(self):
        from recommendations.views import (
            _normalize_kakao_external_candidate,
            _sanitize_frame_for_ai_search,
        )

        frame = {
            "target_objects": [{"value": "쌀국수", "source": "ai_extracted"}],
            "result_match_terms": [{"value": "쌀국수", "source": "ai_extracted"}],
            "candidate_place_types": [{"value": "카페", "source": "fallback_placeholder"}],
            "search_queries": [{"query": "사상역 쌀국수", "source": "ai_extracted"}],
        }
        _, sanitized_frame, partitions = _sanitize_frame_for_ai_search(
            {"plan_source": "ai"},
            frame,
        )
        candidate = _normalize_kakao_external_candidate(
            {
                "id": "fallback-placeholder-cafe",
                "place_name": "테스트 카페",
                "category_name": "카페",
                "address_name": "부산 테스트동",
                "road_address_name": "부산 테스트로",
                "x": "129.0",
                "y": "35.1",
                "distance": "100",
            },
            sanitized_frame,
            "사상역 쌀국수",
        )

        self.assertIn("카페", [item["value"] for item in partitions["blocked_terms"]])
        self.assertEqual(candidate["matched_evidence"], [])
        self.assertNotIn("카페", candidate["matched_tag_labels"])
        self.assertEqual(candidate["frame_match_strength"], "weak")

    @patch("recommendations.views.get_ai_web_search_result")
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", side_effect=AssertionError("Kakao collector must not run for out_of_scope"))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates", side_effect=AssertionError("DB collector must not run for out_of_scope"))
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_execution_gate_blocks_weather_information_query(
        self,
        mock_intent,
        mock_db,
        mock_kakao,
        mock_web,
    ):
        mock_intent.return_value = {
            "action": "out_of_scope",
            "decision_action": "out_of_scope",
            "normalized_query": "오늘 날씨 정보 질문",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": [],
                "candidate_place_types": [],
                "result_match_terms": [],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": [],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "오늘 날씨 어때", "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["decision_action"], "out_of_scope")
        self.assertEqual(data["results"], [])
        self.assertEqual(data["markers"], [])
        self.assertFalse(data["execution_policy"]["run_search"])
        mock_db.assert_not_called()
        mock_kakao.assert_not_called()
        mock_web.assert_not_called()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False,
        AI_SEARCH_MIN_STRONG_MEDIUM_CANDIDATES=0,
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword", return_value={"documents": []})
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_allows_weather_related_place_request(
        self,
        mock_intent,
        mock_kakao,
        mock_rerank,
    ):
        shelter = self._create_place(
            name="비 피할 실내 쉼터",
            category="shelter",
            external_id="weather-shelter-place",
            data_quality_score=80,
        )
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "비 오는데 잠깐 피할 실내 장소",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["비 피할 곳"],
                "candidate_place_types": ["실내 쉼터"],
                "result_match_terms": ["실내 쉼터", "비 피할 곳"],
                "constraints": ["실내"],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["비 피할 실내 쉼터"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.88,
            "ai_retry_count": 0,
        }

        def fake_rerank(frame, candidates, **kwargs):
            selected = next(candidate for candidate in candidates if candidate.get("place_id") == shelter.id)
            return [
                {
                    **selected,
                    "semantic_score": 90,
                    "evidence_level": "strong",
                    "semantic_reason": "DB place text matches weather shelter target",
                    "backend_rank": 1,
                    "unified_rank": 1,
                    "unified_ranker_applied": True,
                }
            ], {
                "status": "executed",
                "input_count": len(candidates),
                "included_count": 1,
                "excluded_count": max(len(candidates) - 1, 0),
                "excluded_candidates": [],
            }

        mock_rerank.side_effect = fake_rerank

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "비 오는데 잠깐 피할 곳", "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["unified_candidate_pipeline"])
        self.assertEqual(data["decision_action"] if "decision_action" in data else "search", "search")
        self.assertIn(shelter.id, [result["place_id"] for result in data["results"]])
        self.assertEqual(data["debug_pipeline"]["used_path"], "ai_first_orchestrator")
        mock_kakao.assert_called()
        mock_rerank.assert_called_once()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_SEARCH_MIN_STRONG_MEDIUM_CANDIDATES=0,
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], []))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates")
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_compatibility_gate_removes_cafe_for_medical_target(
        self,
        mock_intent,
        mock_db,
        mock_kakao,
        mock_rerank,
    ):
        hospital = self._create_place(
            name="하단 테스트 병원",
            category="hospital",
            external_id="medical-target-hospital",
            data_quality_score=80,
        )
        cafe = self._create_place(
            name="하단 테스트 카페",
            category="cafe",
            external_id="medical-target-cafe",
            data_quality_score=99,
        )
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "허리가 아파서 병원 찾기",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["병원"],
                "candidate_place_types": ["병원", "약국"],
                "result_match_terms": ["병원", "약국", "의료기관"],
                "constraints": ["가까운 곳"],
                "exclusions": [],
                "ranking_policy": "urgent_nearest",
                "primary_search_queries": ["병원", "약국"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }
        hospital_candidate = {
            "id": f"db:{hospital.id}",
            "place_id": hospital.id,
            "candidate_source": "db",
            "source": "db",
            "name": hospital.name,
            "category": hospital.category,
            "address": "",
            "distance": 100,
            "pre_ai_evidence_level": "strong",
            "frame_match_strength": "strong",
        }
        cafe_candidate = {
            "id": f"db:{cafe.id}",
            "place_id": cafe.id,
            "candidate_source": "db",
            "source": "db",
            "name": cafe.name,
            "category": cafe.category,
            "address": "",
            "distance": 50,
            "pre_ai_evidence_level": "weak",
            "frame_match_strength": "weak",
        }
        mock_db.return_value = [hospital_candidate, cafe_candidate]
        mock_rerank.return_value = ([
            {
                **hospital_candidate,
                "semantic_score": 95,
                "evidence_level": "strong",
                "semantic_reason": "medical target compatible",
                "compatibility_gate": "passed",
                "backend_rank": 1,
                "unified_rank": 1,
            }
        ], {
            "status": "executed",
            "input_count": 2,
            "included_count": 1,
            "excluded_count": 1,
            "excluded_candidates": [{
                **cafe_candidate,
                "evidence_level": "weak",
                "semantic_reason": "not medical target compatible",
                "compatibility_gate": "excluded",
            }],
        })

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "허리가 아프네 병원", "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["place_id"] for result in data["results"]]
        cafe_results = [result for result in data["hidden_weak_candidates"] if result["category"] == "cafe"]
        self.assertIn(hospital.id, result_ids)
        self.assertNotIn("cafe", [result["category"] for result in data["results"]])
        for cafe_result in cafe_results:
            self.assertEqual(cafe_result["frame_match_strength"], "weak")
            self.assertEqual(cafe_result["compatibility_gate"], "excluded")

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_SEARCH_MIN_STRONG_MEDIUM_CANDIDATES=0,
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], []))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates")
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_compatibility_gate_removes_cafe_for_song_target(
        self,
        mock_intent,
        mock_db,
        mock_kakao,
        mock_rerank,
    ):
        karaoke = self._create_place(
            name="테스트 코인노래방",
            category="karaoke",
            external_id="song-target-karaoke",
            data_quality_score=80,
        )
        cafe = self._create_place(
            name="노래 없는 테스트 카페",
            category="cafe",
            external_id="song-target-cafe",
            data_quality_score=99,
        )
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "노래 부를 수 있는 곳 찾기",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["노래방"],
                "candidate_place_types": ["노래방", "코인노래방"],
                "result_match_terms": ["노래방", "코인노래방", "음악"],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["노래방", "코인노래방"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.86,
            "ai_retry_count": 0,
        }
        karaoke_candidate = {
            "id": f"db:{karaoke.id}",
            "place_id": karaoke.id,
            "candidate_source": "db",
            "source": "db",
            "name": karaoke.name,
            "category": karaoke.category,
            "address": "",
            "distance": 120,
            "pre_ai_evidence_level": "strong",
            "frame_match_strength": "strong",
        }
        cafe_candidate = {
            "id": f"db:{cafe.id}",
            "place_id": cafe.id,
            "candidate_source": "db",
            "source": "db",
            "name": cafe.name,
            "category": cafe.category,
            "address": "",
            "distance": 30,
            "pre_ai_evidence_level": "weak",
            "frame_match_strength": "weak",
        }
        mock_db.return_value = [karaoke_candidate, cafe_candidate]
        mock_rerank.return_value = ([
            {
                **karaoke_candidate,
                "semantic_score": 94,
                "evidence_level": "strong",
                "semantic_reason": "song target compatible",
                "compatibility_gate": "passed",
                "backend_rank": 1,
                "unified_rank": 1,
            }
        ], {
            "status": "executed",
            "input_count": 2,
            "included_count": 1,
            "excluded_count": 1,
            "excluded_candidates": [{
                **cafe_candidate,
                "evidence_level": "weak",
                "semantic_reason": "not song target compatible",
                "compatibility_gate": "excluded",
            }],
        })

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "노래 한 곡 땡기고 싶은데", "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["place_id"] for result in data["results"]]
        cafe_results = [result for result in data["hidden_weak_candidates"] if result["category"] == "cafe"]
        self.assertIn(karaoke.id, result_ids)
        self.assertNotIn("cafe", [result["category"] for result in data["results"]])
        for cafe_result in cafe_results:
            self.assertEqual(cafe_result["frame_match_strength"], "weak")
            self.assertEqual(cafe_result["compatibility_gate"], "excluded")

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_SEARCH_MIN_STRONG_MEDIUM_CANDIDATES=0,
    )
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.collect_kakao_candidates", return_value=([], []))
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates")
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_compatibility_gate_removes_cafe_for_rice_noodle_target(
        self,
        mock_intent,
        mock_db,
        mock_kakao,
        mock_rerank,
    ):
        restaurant = self._create_place(
            name="사상 테스트 쌀국수 식당",
            category="restaurant",
            external_id="rice-noodle-restaurant",
            data_quality_score=70,
        )
        cafe = self._create_place(
            name="사상 테스트 카페",
            category="cafe",
            external_id="rice-noodle-cafe",
            data_quality_score=99,
        )
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "사상역 근처 쌀국수 맛집",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["쌀국수"],
                "candidate_place_types": ["베트남음식"],
                "result_match_terms": ["쌀국수", "베트남음식"],
                "constraints": ["방문 전 메뉴 확인 필요"],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["사상역 쌀국수", "사상역 쌀국수 맛집"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }
        restaurant_candidate = {
            "id": f"db:{restaurant.id}",
            "place_id": restaurant.id,
            "candidate_source": "db",
            "source": "db",
            "name": restaurant.name,
            "category": restaurant.category,
            "address": "",
            "distance": 180,
            "pre_ai_evidence_level": "strong",
            "frame_match_strength": "strong",
        }
        cafe_candidate = {
            "id": f"db:{cafe.id}",
            "place_id": cafe.id,
            "candidate_source": "db",
            "source": "db",
            "name": cafe.name,
            "category": cafe.category,
            "address": "",
            "distance": 20,
            "pre_ai_evidence_level": "weak",
            "frame_match_strength": "weak",
        }
        mock_db.return_value = [restaurant_candidate, cafe_candidate]
        mock_rerank.return_value = ([
            {
                **restaurant_candidate,
                "semantic_score": 96,
                "evidence_level": "strong",
                "semantic_reason": "rice noodle target compatible",
                "compatibility_gate": "passed",
                "backend_rank": 1,
                "unified_rank": 1,
            }
        ], {
            "status": "executed",
            "input_count": 2,
            "included_count": 1,
            "excluded_count": 1,
            "excluded_candidates": [{
                **cafe_candidate,
                "evidence_level": "weak",
                "semantic_reason": "not rice noodle target compatible",
                "compatibility_gate": "excluded",
            }],
        })

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({"query": "사상역 근처 쌀국수 맛집", "lat": 35.1556, "lng": 129.0641}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        cafe_results = [result for result in data["hidden_weak_candidates"] if result["category"] == "cafe"]
        self.assertEqual(data["results"][0]["place_id"], restaurant.id)
        self.assertNotIn("cafe", [result["category"] for result in data["results"]])
        for cafe_result in cafe_results:
            self.assertEqual(cafe_result["frame_match_strength"], "weak")
            self.assertEqual(cafe_result["compatibility_gate"], "excluded")
        self.assertTrue(data["frontend_should_preserve_order"])
        self.assertTrue(data["frontend_should_skip_kakao_fallback"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.views.search_db_recommendations")
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_plan_api_decision_action_out_of_scope_does_not_search(self, mock_ai, mock_search):
        mock_ai.return_value = {
            "action": "out_of_scope",
            "decision_action": "out_of_scope",
            "intent_type": "out_of_scope",
            "user_intent_summary": "장소 추천 범위 밖 요청",
            "message": "생활 장소 추천 범위 밖 요청입니다.",
            "out_of_scope_reason": "not_place_recommendation",
            "confidence": 0.92,
        }

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": "오늘 주식 뭐 사?"}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["type"], "out_of_scope")
        self.assertEqual(data["decision_action"], "out_of_scope")
        self.assertEqual(data["plan_source"], "ai")
        self.assertEqual(data["execution_mode"], "decision_gate")
        self.assertFalse(data["can_search_now"])
        self.assertFalse(data["execution_policy"]["run_search"])
        self.assertEqual(data["results"], [])
        self.assertEqual(data["search_plan"], {})
        mock_search.assert_not_called()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_plan_api_location_missing_can_ask_or_search_with_context(self, mock_ai):
        mock_ai.return_value = {
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "user_intent_summary": "위치 확인이 필요한 운동 장소 요청",
            "message": "현재 위치 기준으로 찾을까요, 지역명을 입력해 주실까요?",
            "search_plan": {
                "targetQuery": "축구 연습할 곳",
                "place_intent_frame": {
                    "decision_action": "ask_clarification",
                    "user_goal": "축구 연습 장소 찾기",
                    "normalized_user_intent": "축구 연습할 장소를 찾고 싶음",
                    "anchor_location": "",
                    "location_mode": "clarification_required",
                    "situation": "general_place",
                    "display_label": "축구 연습할 곳",
                    "target_objects": ["축구 연습"],
                    "candidate_place_types": ["축구장", "풋살장", "운동장"],
                    "search_queries": [],
                    "result_match_terms": ["축구장", "풋살장", "운동장"],
                    "constraints": [],
                    "exclusions": [],
                    "missing_info": ["위치"],
                    "clarification_question": "현재 위치 기준으로 찾을까요, 지역명을 입력해 주실까요?",
                    "clarification_options": ["현재 위치", "지역명 입력"],
                    "can_search_now": False,
                    "confidence": 0.7,
                },
            },
            "needs_clarification": True,
            "clarification_question": "현재 위치 기준으로 찾을까요, 지역명을 입력해 주실까요?",
            "clarification_options": ["현재 위치", "지역명 입력"],
        }

        missing_location_response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": "근처에 축구 연습할 곳"}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(missing_location_response.status_code, 200)
        self.assertEqual(missing_location_response.json()["decision_action"], "ask_clarification")
        self.assertFalse(missing_location_response.json()["execution_policy"]["run_search"])

        mock_ai.reset_mock()
        mock_ai.side_effect = [
            self._ai_planner_frame_response(
                query="근처에 축구 연습할 곳",
                display_label="축구 연습할 곳",
                situation="general_place",
                location_mode="current_context",
                target_objects=["축구 연습"],
                candidate_category_codes=["sports_facility", "city_park"],
                candidate_place_types=["축구장", "풋살장", "운동장"],
                search_queries=["축구장", "풋살장", "운동장"],
                result_match_terms=["축구장", "풋살장", "운동장"],
                scenario="waiting_place",
            ),
            {"explicit_anchor_location": ""},
        ]

        current_context_response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps(
                {"query": "근처에 축구 연습할 곳", "lat": 35.1556, "lng": 129.0641},
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(current_context_response.status_code, 200)
        current_context_data = current_context_response.json()
        frame = current_context_data["search_plan"]["place_intent_frame"]
        self.assertEqual(current_context_data["decision_action"], "search")
        self.assertEqual(frame["location_mode"], "current_context")
        self.assertTrue(current_context_data["execution_policy"]["run_search"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_plan_api_colloquial_urgent_queries_are_not_blocked(self, mock_ai):
        mock_ai.side_effect = [
            self._ai_planner_frame_response(
                query="똥 마려운데 우야노",
                display_label="공중화장실",
                situation="toilet",
                location_mode="current_context",
                target_objects=["화장실"],
                candidate_category_codes=["toilet"],
                candidate_place_types=["공중화장실", "개방화장실", "화장실"],
                search_queries=["공중화장실", "화장실"],
                result_match_terms=["화장실", "공중화장실", "개방화장실"],
                constraints=["긴급", "가까운 곳"],
                ranking_policy="urgent_nearest",
            ),
            {"explicit_anchor_location": ""},
        ]

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": "똥 마려운데 우야노"}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        frame = data["search_plan"]["place_intent_frame"]
        self.assertEqual(data["decision_action"], "search")
        self.assertNotIn(data["decision_action"], {"blocked", "out_of_scope"})
        self.assertIn("화장실", frame["target_objects"])
        self.assertEqual(frame["ranking_policy"], "urgent_nearest")

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_uses_frame_category_and_relevance_metadata(self):
        toilet = self._create_place(
            name="하단역 테스트 공중화장실",
            category="toilet",
            external_id="frame-toilet-1",
            data_quality_score=85,
        )
        self._create_place(
            name="하단역 테스트 공원",
            category="city_park",
            external_id="frame-park-1",
            data_quality_score=95,
        )
        frame = {
            "user_goal": "가까운 화장실 찾기",
            "anchor_location": "하단역",
            "location_mode": "explicit",
            "situation": "toilet",
            "display_label": "화장실",
            "candidate_category_codes": ["toilet"],
            "candidate_place_types": ["공중화장실", "개방화장실"],
            "search_queries": ["하단역 공중화장실", "하단역 개방화장실"],
            "result_match_terms": ["화장실", "공중화장실", "개방화장실"],
            "constraints": ["가까운 곳"],
            "exclusions": [],
            "preferred_place_natures": ["ordinary_public_access"],
            "excluded_place_natures": [],
            "missing_info": [],
            "confidence": 0.92,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(self._frame_search_payload(frame), ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["execution_mode"], "frame")
        self.assertEqual(data["plan_source"], "ai")
        self.assertEqual(data["relevant_result_count"], 1)
        self.assertEqual(data["results"][0]["id"], toilet.id)
        self.assertEqual(data["results"][0]["category"], "toilet")
        self.assertEqual(data["results"][0]["matched_category_codes"], ["toilet"])
        self.assertEqual(data["results"][0]["matched_evidence"][0]["type"], "category_code")

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_with_unsupported_category_does_not_return_unrelated_db_results(self):
        self._create_place(
            name="하단역 테스트 쉼터",
            category="shelter",
            external_id="frame-shelter-1",
            data_quality_score=95,
        )
        frame = {
            "user_goal": "가까운 약국이나 병원 찾기",
            "anchor_location": "하단역",
            "location_mode": "explicit",
            "situation": "health_nearby",
            "display_label": "약국/병원",
            "candidate_category_codes": ["pharmacy", "hospital"],
            "candidate_place_types": ["약국", "병원"],
            "search_queries": ["하단역 약국", "하단역 병원"],
            "result_match_terms": ["약국", "병원"],
            "constraints": ["가까운 곳"],
            "exclusions": [],
            "preferred_place_natures": ["medical_facility"],
            "excluded_place_natures": [],
            "missing_info": [],
            "confidence": 0.88,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(self._frame_search_payload(frame, query="머리 아프다 하단역"), ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["execution_mode"], "frame")
        self.assertEqual(data["relevant_result_count"], 0)
        self.assertEqual(data["results"], [])

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_returns_health_category_results(self):
        pharmacy = self._create_place(
            name="하단역 테스트 약국",
            category="pharmacy",
            external_id="frame-pharmacy-1",
            data_quality_score=86,
        )
        hospital = self._create_place(
            name="하단역 테스트 병원",
            category="hospital",
            external_id="frame-hospital-1",
            data_quality_score=82,
            lat=35.1557,
            lng=129.0642,
        )
        self._create_place(
            name="하단역 테스트 산책공원",
            category="city_park",
            external_id="frame-health-park-1",
            data_quality_score=99,
        )
        frame = {
            "user_goal": "가까운 약국이나 병원 찾기",
            "anchor_location": "하단역",
            "location_mode": "explicit",
            "situation": "health_nearby",
            "display_label": "약국/병원",
            "candidate_category_codes": ["pharmacy", "hospital"],
            "candidate_place_types": ["약국", "병원"],
            "search_queries": ["하단역 약국", "하단역 병원"],
            "result_match_terms": ["약국", "병원"],
            "constraints": ["가까운 곳"],
            "exclusions": [],
            "preferred_place_natures": ["medical_facility"],
            "excluded_place_natures": [],
            "missing_info": [],
            "confidence": 0.88,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(self._frame_search_payload(frame, query="머리 아프다 하단역"), ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]
        result_categories = {result["category"] for result in data["results"]}
        self.assertEqual(data["execution_mode"], "frame")
        self.assertEqual(data["plan_source"], "ai")
        self.assertEqual(data["relevant_result_count"], 2)
        self.assertIn(pharmacy.id, result_ids)
        self.assertIn(hospital.id, result_ids)
        self.assertEqual(result_categories, {"pharmacy", "hospital"})

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_applies_exclusions_to_db_results(self):
        library = self._create_place(
            name="테스트 공공도서관",
            category="library",
            external_id="frame-library-1",
            data_quality_score=90,
        )
        frame = {
            "user_goal": "카페가 아닌 조용히 쉴 곳 찾기",
            "anchor_location": "",
            "location_mode": "current_context",
            "situation": "quiet_rest",
            "display_label": "조용히 쉴 곳",
            "candidate_category_codes": ["cafe", "library"],
            "candidate_place_types": ["도서관", "카페"],
            "search_queries": ["도서관", "조용한 공간"],
            "result_match_terms": ["도서관", "카페"],
            "constraints": ["조용함"],
            "exclusions": ["카페 제외"],
            "preferred_place_natures": ["library_like", "ordinary_public_access"],
            "excluded_place_natures": [],
            "missing_info": [],
            "confidence": 0.84,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(self._frame_search_payload(frame, query="카페 말고 조용히 쉴 곳"), ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]
        result_categories = [result["category"] for result in data["results"]]
        self.assertIn(library.id, result_ids)
        self.assertNotIn("cafe", result_categories)

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_demotes_conditional_shelters_for_general_rest(self):
        library = self._create_place(
            name="테스트 공공도서관",
            category="library",
            external_id="frame-rest-library-1",
            data_quality_score=70,
        )
        conditional_shelter = self._create_place(
            name="테스트 무더위쉼터",
            category="shelter",
            external_id="frame-rest-conditional-shelter-1",
            data_quality_score=99,
            raw={
                "place_tag_seed_raw": {
                    "original_tag_name": "무더위쉼터",
                    "place_source": "heat_shelter_api",
                },
            },
        )
        conditional_shelter.source = "heat_shelter_api"
        conditional_shelter.save(update_fields=["source"])
        frame = {
            "user_goal": "일반적으로 조용히 쉴 곳 찾기",
            "anchor_location": "서면역 롯데백화점",
            "location_mode": "explicit",
            "situation": "rest",
            "display_label": "쉴 곳",
            "candidate_category_codes": ["shelter", "library"],
            "candidate_place_types": ["쉼터", "도서관"],
            "search_queries": ["서면역 롯데백화점 쉼터", "서면역 롯데백화점 도서관"],
            "result_match_terms": ["쉼터", "도서관"],
            "constraints": ["일반 휴식"],
            "exclusions": [],
            "preferred_place_natures": ["ordinary_public_access", "library_like"],
            "excluded_place_natures": [],
            "missing_info": [],
            "confidence": 0.83,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="서면역 롯데백화점 근처 쉴 곳"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]
        self.assertIn(library.id, result_ids)
        self.assertNotIn(conditional_shelter.id, result_ids)

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_demotes_limited_access_facilities_for_quiet_rest(self):
        park = self._create_place(
            name="테스트 열린 공원",
            category="city_park",
            external_id="frame-rest-open-park",
            data_quality_score=72,
        )
        library = self._create_place(
            name="테스트 열린 도서관",
            category="library",
            external_id="frame-rest-open-library",
            data_quality_score=72,
        )
        senior_facility = self._create_place(
            name="테스트 어르신 프로그램 공간",
            category="shelter",
            external_id="frame-rest-senior-facility",
            data_quality_score=99,
            raw={
                "facility_profile": {
                    "audience": "노인복지 프로그램 이용자",
                    "operation": "회원제 쉼터",
                },
            },
        )
        institution_facility = self._create_place(
            name="테스트 기관 운영 휴게실",
            category="shelter",
            external_id="frame-rest-institution-facility",
            data_quality_score=99,
            raw={
                "facility_profile": {
                    "operator": "행정복지센터",
                    "operation": "민원센터 부속 공간",
                },
            },
        )
        frame = {
            "user_goal": "일반 사용자가 조용히 쉴 수 있는 곳 찾기",
            "anchor_location": "",
            "location_mode": "current_context",
            "situation": "quiet_rest",
            "display_label": "조용히 쉴 곳",
            "candidate_category_codes": ["city_park", "library", "shelter"],
            "candidate_place_types": ["공원", "도서관", "쉼터"],
            "search_queries": ["조용히 쉴 곳", "도서관", "공원", "쉼터"],
            "result_match_terms": ["공원", "도서관", "쉼터", "휴식"],
            "constraints": ["일반 사용 가능", "조용함"],
            "exclusions": [],
            "preferred_place_natures": ["ordinary_public_access", "library_like", "park_like"],
            "excluded_place_natures": [],
            "missing_info": [],
            "confidence": 0.85,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="조용히 쉴 곳"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]

        self.assertIn(park.id, result_ids)
        self.assertIn(library.id, result_ids)
        self.assertNotIn(senior_facility.id, result_ids)
        self.assertNotIn(institution_facility.id, result_ids)

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_prioritizes_work_cafe_with_evidence_over_category_only(self):
        work_ready_cafe = self._create_place(
            name="테스트 노트북 작업 카페",
            category="cafe",
            external_id="frame-work-ready-cafe",
            data_quality_score=68,
        )
        self._add_tag(work_ready_cafe, "노트북작업")
        category_only_cafe = self._create_place(
            name="테스트 일반 커피 매장",
            category="cafe",
            external_id="frame-work-category-only-cafe",
            data_quality_score=99,
        )
        takeout_cafe = self._create_place(
            name="테스트 포장 중심 커피 매장",
            category="cafe",
            external_id="frame-work-takeout-cafe",
            data_quality_score=99,
            raw={
                "facility_profile": {
                    "service_model": "테이크아웃 중심",
                    "seating": "좌석 부족",
                },
            },
        )
        frame = {
            "user_goal": "작업하기 좋은 카페 찾기",
            "anchor_location": "강남역",
            "location_mode": "explicit",
            "situation": "work_cafe",
            "display_label": "작업할 만한 카페",
            "candidate_category_codes": ["cafe"],
            "candidate_place_types": ["카페"],
            "search_queries": ["강남역 작업 카페", "강남역 노트북 카페"],
            "result_match_terms": ["카페", "노트북작업", "콘센트", "와이파이"],
            "constraints": ["노트북 작업 가능", "콘센트", "와이파이", "조용함"],
            "exclusions": [],
            "preferred_place_natures": ["ordinary_public_access"],
            "excluded_place_natures": [],
            "missing_info": [],
            "confidence": 0.88,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="강남역 작업할 만한 카페"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]
        category_only_result = next(result for result in data["results"] if result["id"] == category_only_cafe.id)
        takeout_result = next(result for result in data["results"] if result["id"] == takeout_cafe.id)

        self.assertLess(result_ids.index(work_ready_cafe.id), result_ids.index(category_only_cafe.id))
        self.assertLess(result_ids.index(work_ready_cafe.id), result_ids.index(takeout_cafe.id))
        self.assertLessEqual(category_only_result["score"], 40)
        self.assertLessEqual(takeout_result["score"], 35)
        self.assertIn(
            "work_cafe_category_only_without_core",
            category_only_result["score_breakdown"]["score_cap_reasons"],
        )
        self.assertIn(
            "work_cafe_takeout_without_core",
            takeout_result["score_breakdown"]["score_cap_reasons"],
        )
        self.assertIn("takeout_focused", takeout_result["place_natures"])

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_prioritizes_target_object_menu_evidence(self):
        tagged_restaurant = self._create_place(
            name="테스트 아시아 식당",
            category="restaurant",
            external_id="frame-menu-target-restaurant",
            data_quality_score=66,
        )
        self._add_tag(tagged_restaurant, "쌀국수")
        generic_restaurant = self._create_place(
            name="테스트 일반 식당",
            category="restaurant",
            external_id="frame-menu-generic-restaurant",
            data_quality_score=99,
        )
        frame = {
            "user_goal": "쌀국수 맛집 찾기",
            "anchor_location": "사상역",
            "location_mode": "explicit",
            "situation": "food",
            "display_label": "쌀국수 맛집",
            "target_objects": ["쌀국수"],
            "candidate_category_codes": ["restaurant"],
            "candidate_place_types": ["음식점"],
            "search_queries": ["사상역 쌀국수", "사상역 쌀국수 맛집"],
            "result_match_terms": ["쌀국수", "베트남음식", "음식점"],
            "constraints": ["방문 전 메뉴 확인 필요"],
            "exclusions": [],
            "preferred_place_natures": ["ordinary_public_access"],
            "excluded_place_natures": [],
            "ranking_policy": "evidence_first",
            "missing_info": [],
            "confidence": 0.9,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="사상역 근처 쌀국수 맛집"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]
        hidden_ids = [result["id"] for result in data["hidden_weak_candidates"]]
        generic_result = next(result for result in data["hidden_weak_candidates"] if result["id"] == generic_restaurant.id)

        self.assertIn(tagged_restaurant.id, result_ids)
        self.assertIn(generic_restaurant.id, hidden_ids)
        self.assertNotIn(generic_restaurant.id, result_ids)
        self.assertEqual(data["results"][0]["frame_match_strength"], "strong")
        self.assertEqual(generic_result["frame_match_strength"], "weak")
        self.assertIn(
            "frame_weak_category_fallback",
            generic_result["score_breakdown"]["score_cap_reasons"],
        )

    def test_conversational_search_plan_preserves_target_object_kakao_queries(self):
        with patch("recommendations.services.conversational_search_planner._call_gms_chat_json") as mock_ai:
            mock_ai.return_value = {
                "action": "search",
                "search_plan": {
                    "locationQuery": "사상역",
                    "baseLocationQuery": "사상역",
                    "targetQuery": "쌀국수 맛집",
                    "scenario": "restaurant",
                    "place_intent_frame": {
                        "user_goal": "사상역 근처 쌀국수 맛집 찾기",
                        "anchor_location": "사상역",
                        "location_mode": "explicit",
                        "situation": "food",
                        "display_label": "쌀국수 맛집",
                        "target_objects": ["쌀국수"],
                        "candidate_category_codes": ["restaurant"],
                        "candidate_place_types": ["음식점"],
                        "search_queries": ["쌀국수", "쌀국수 맛집"],
                        "result_match_terms": ["쌀국수", "베트남음식"],
                        "constraints": ["방문 전 메뉴 확인 필요"],
                        "exclusions": [],
                        "preferred_place_natures": ["ordinary_public_access"],
                        "excluded_place_natures": [],
                        "ranking_policy": "evidence_first",
                        "missing_info": [],
                        "confidence": 0.9,
                    },
                },
                "confidence": 0.9,
            }

            with override_settings(
                CONVERSATIONAL_SEARCH_AI_ENABLED=True,
                AI_PROVIDER="gms",
                GMS_API_KEY="fake-gms",
                GMS_API_URL="https://example.invalid/parser",
            ):
                plan = build_conversational_search_plan("사상역 근처 쌀국수 맛집")

        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]
        self.assertEqual(frame["target_objects"], ["쌀국수"])
        self.assertEqual(frame["ranking_policy"], "evidence_first")
        self.assertIn("사상역 쌀국수", search_plan["kakaoKeywordCandidates"])
        self.assertIn("사상역 쌀국수 맛집", search_plan["kakaoKeywordCandidates"])

    def test_conversational_search_plan_strips_ai_broad_defaults_from_specific_target(self):
        with patch("recommendations.services.conversational_search_planner._call_gms_chat_json") as mock_ai:
            mock_ai.return_value = {
                "action": "search",
                "search_plan": {
                    "locationQuery": "사상역",
                    "baseLocationQuery": "사상역",
                    "targetQuery": "쌀국수 맛집",
                    "scenario": "restaurant",
                    "place_intent_frame": {
                        "decision_action": "search",
                        "user_goal": "사상역 근처 쌀국수 맛집 찾기",
                        "anchor_location": "사상역",
                        "location_mode": "explicit",
                        "situation": "food",
                        "display_label": "쌀국수 맛집",
                        "target_objects": ["쌀국수"],
                        "candidate_category_codes": ["restaurant", "cafe"],
                        "candidate_place_types": ["식당", "음식점", "카페"],
                        "search_queries": ["사상역 쌀국수", "사상역 식당", "사상역 카페"],
                        "result_match_terms": ["쌀국수", "베트남음식", "식당", "음식점"],
                        "constraints": ["방문 전 메뉴 확인 필요"],
                        "exclusions": [],
                        "preferred_place_natures": ["ordinary_public_access"],
                        "excluded_place_natures": [],
                        "ranking_policy": "evidence_first",
                        "missing_info": [],
                        "confidence": 0.9,
                    },
                },
                "confidence": 0.9,
            }

            with override_settings(
                CONVERSATIONAL_SEARCH_AI_ENABLED=True,
                AI_PROVIDER="gms",
                GMS_API_KEY="fake-gms",
                GMS_API_URL="https://example.invalid/parser",
            ):
                plan = build_conversational_search_plan("사상역 근처 쌀국수 맛집")

        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]
        self.assertEqual(frame["target_objects"], ["쌀국수"])
        self.assertEqual(frame["candidate_category_codes"], [])
        self.assertEqual(frame["candidate_place_types"], [])
        self.assertEqual(frame["result_match_terms"], ["쌀국수", "베트남음식"])
        self.assertIn("사상역 쌀국수", search_plan["kakaoKeywordCandidates"])
        blocked_terms = ["사상역 식당", "사상역 음식점", "사상역 카페", "사상역 restaurant"]
        for blocked_term in blocked_terms:
            self.assertNotIn(blocked_term, search_plan["kakaoKeywordCandidates"])
            self.assertNotIn(blocked_term, frame["search_queries"])

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_prioritizes_dessert_target_over_generic_food(self):
        dessert_cafe = self._create_place(
            name="테스트 디저트 카페",
            category="cafe",
            external_id="frame-dessert-cafe",
            data_quality_score=65,
        )
        self._add_tag(dessert_cafe, "디저트")
        generic_restaurant = self._create_place(
            name="테스트 일반 음식점",
            category="restaurant",
            external_id="frame-dessert-generic-restaurant",
            data_quality_score=99,
        )
        frame = {
            "user_goal": "달달한 음식 먹기",
            "anchor_location": "",
            "location_mode": "current_context",
            "situation": "food",
            "display_label": "달달한 음식",
            "target_objects": ["달달한 음식"],
            "candidate_category_codes": ["cafe", "restaurant"],
            "candidate_place_types": ["카페", "음식점"],
            "search_queries": ["디저트", "베이커리", "카페"],
            "result_match_terms": ["디저트", "베이커리", "케이크", "빙수", "아이스크림", "카페"],
            "constraints": ["방문 전 메뉴 확인 필요"],
            "exclusions": [],
            "preferred_place_natures": ["ordinary_public_access", "commercial_rest_place"],
            "excluded_place_natures": [],
            "ranking_policy": "evidence_first",
            "missing_info": [],
            "confidence": 0.86,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="달달한거 먹고 싶어"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]
        hidden_ids = [result["id"] for result in data["hidden_weak_candidates"]]
        generic_result = next(result for result in data["hidden_weak_candidates"] if result["id"] == generic_restaurant.id)

        self.assertIn(dessert_cafe.id, result_ids)
        self.assertIn(generic_restaurant.id, hidden_ids)
        self.assertNotIn(generic_restaurant.id, result_ids)
        self.assertEqual(data["results"][0]["frame_match_strength"], "strong")
        self.assertEqual(generic_result["frame_match_strength"], "weak")

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_prioritizes_sport_target_over_unrelated_fallback(self):
        sport_place = self._create_place(
            name="테스트 체육공원",
            category="sports_facility",
            external_id="frame-sport-facility",
            data_quality_score=66,
        )
        self._add_tag(sport_place, "축구장")
        generic_cafe = self._create_place(
            name="테스트 일반 카페",
            category="cafe",
            external_id="frame-sport-generic-cafe",
            data_quality_score=99,
        )
        frame = {
            "user_goal": "축구 연습 장소 찾기",
            "anchor_location": "",
            "location_mode": "current_context",
            "situation": "general_place",
            "display_label": "축구 연습 장소",
            "target_objects": ["축구 연습"],
            "candidate_category_codes": ["sports_facility", "city_park", "cafe"],
            "candidate_place_types": ["축구장", "풋살장", "운동장", "체육공원"],
            "search_queries": ["축구장", "풋살장", "운동장"],
            "result_match_terms": ["축구", "축구장", "풋살장", "운동장", "체육공원"],
            "constraints": ["이용 가능 여부 확인 필요"],
            "exclusions": [],
            "preferred_place_natures": ["ordinary_public_access", "park_like"],
            "excluded_place_natures": [],
            "ranking_policy": "evidence_first",
            "missing_info": ["실제 이용 가능 여부"],
            "confidence": 0.82,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="근처에 축구 연습하기 좋은 장소 추천해줘"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]

        self.assertIn(sport_place.id, result_ids)
        self.assertNotIn(generic_cafe.id, result_ids)
        self.assertEqual(data["results"][0]["frame_match_strength"], "strong")

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_demotes_commercial_places_for_low_cost_time_spending(self):
        park = self._create_place(
            name="테스트 열린 광장 공원",
            category="city_park",
            external_id="frame-low-cost-park",
            data_quality_score=70,
        )
        library = self._create_place(
            name="테스트 공공도서관",
            category="library",
            external_id="frame-low-cost-library",
            data_quality_score=70,
        )
        commercial_cafe = self._create_place(
            name="테스트 유료 소비 카페",
            category="cafe",
            external_id="frame-low-cost-cafe",
            data_quality_score=99,
        )
        frame = {
            "user_goal": "돈을 쓰지 않고 시간 보내기 좋은 곳 찾기",
            "anchor_location": "",
            "location_mode": "current_context",
            "situation": "quiet_rest",
            "display_label": "무료로 시간 보내기 좋은 곳",
            "target_objects": ["무료로 시간 보내기"],
            "candidate_category_codes": ["city_park", "library", "cafe"],
            "candidate_place_types": ["공원", "도서관", "광장", "공공공간"],
            "search_queries": ["무료 공공공간", "공원", "도서관"],
            "result_match_terms": ["무료", "공공공간", "공원", "도서관", "광장"],
            "constraints": ["무료 또는 저비용", "방문 전 이용 가능 여부 확인 필요"],
            "exclusions": [],
            "preferred_place_natures": ["ordinary_public_access", "park_like", "library_like"],
            "excluded_place_natures": [],
            "ranking_policy": "cost_sensitive",
            "missing_info": ["무료 이용 가능 여부"],
            "confidence": 0.84,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="돈 안쓰고 시간 때우기 좋은 곳"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = [result["id"] for result in data["results"]]

        self.assertIn(park.id, result_ids)
        self.assertIn(library.id, result_ids)
        self.assertNotIn(commercial_cafe.id, result_ids)

    @skip("Obsolete /ai-search frame-injection contract; ai-search now uses AI planner output only.")
    def test_ai_search_frame_urgent_nearest_sorts_by_distance(self):
        near_toilet = self._create_place(
            name="테스트 가까운 공중화장실",
            category="toilet",
            external_id="frame-urgent-near-toilet",
            lat=35.1557,
            lng=129.0642,
            data_quality_score=40,
        )
        far_toilet = self._create_place(
            name="테스트 먼 고품질 공중화장실",
            category="toilet",
            external_id="frame-urgent-far-toilet",
            lat=35.1587,
            lng=129.0672,
            data_quality_score=99,
        )
        frame = {
            "user_goal": "가장 가까운 화장실 찾기",
            "anchor_location": "",
            "location_mode": "current_context",
            "situation": "toilet",
            "display_label": "가까운 화장실",
            "target_objects": ["화장실"],
            "candidate_category_codes": ["toilet"],
            "candidate_place_types": ["공중화장실", "개방화장실", "화장실"],
            "search_queries": ["공중화장실", "개방화장실"],
            "result_match_terms": ["화장실", "공중화장실", "개방화장실"],
            "constraints": ["가까운 곳", "긴급", "개방 여부 확인 필요"],
            "exclusions": [],
            "preferred_place_natures": ["ordinary_public_access"],
            "excluded_place_natures": [],
            "ranking_policy": "urgent_nearest",
            "missing_info": ["운영/개방 여부"],
            "confidence": 0.9,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                self._frame_search_payload(frame, query="진짜 지금 싸기 직전인데 근처에 제일 가까운 곳"),
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["results"][0]["id"], near_toilet.id)
        self.assertLess(data["results"][0]["distance_m"], data["results"][1]["distance_m"])
        self.assertEqual(data["results"][1]["id"], far_toilet.id)

    def test_authenticated_user_can_save_search_log(self):
        response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "소금빵 맛집 찾아줘",
                "search_mode": "recommendation_query",
                "scenario": "restaurant",
                "location_hint": "부산 강서구",
                "lat": 35.123456,
                "lng": 129.123456,
                "target_query": "소금빵 맛집",
                "category_hint": "cafe",
                "requested_conditions": ["디저트"],
                "menu_keywords": ["소금빵"],
                "place_type_keywords": ["베이커리", "카페"],
                "preferred_tags": ["조용함"],
                "negative_tags": ["혼잡"],
                "result_count": 10,
                "db_result_count": 2,
                "kakao_result_count": 8,
                "ai_web_result_count": 0,
                "search_plan_snapshot": {
                    "targetQuery": "소금빵 맛집",
                    "categoryHint": "cafe",
                    "recommendationIntent": True,
                },
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["message"], "search log saved")
        self.assertEqual(UserSearchLog.objects.count(), 1)

        search_log = UserSearchLog.objects.get(id=data["id"])
        self.assertEqual(search_log.user, self.user)
        self.assertEqual(search_log.query, "소금빵 맛집 찾아줘")
        self.assertEqual(search_log.search_mode, "recommendation_query")
        self.assertEqual(search_log.scenario, "restaurant")
        self.assertEqual(search_log.location_hint, "부산 강서구")
        self.assertEqual(search_log.target_query, "소금빵 맛집")
        self.assertEqual(search_log.category_hint, "cafe")
        self.assertEqual(search_log.requested_conditions, ["디저트"])
        self.assertEqual(search_log.menu_keywords, ["소금빵"])
        self.assertEqual(search_log.place_type_keywords, ["베이커리", "카페"])
        self.assertEqual(search_log.preferred_tags, ["조용함"])
        self.assertEqual(search_log.negative_tags, ["혼잡"])
        self.assertEqual(search_log.result_count, 10)
        self.assertEqual(search_log.db_result_count, 2)
        self.assertEqual(search_log.kakao_result_count, 8)
        self.assertEqual(search_log.ai_web_result_count, 0)
        self.assertEqual(search_log.search_plan_snapshot["targetQuery"], "소금빵 맛집")

    def test_search_log_accepts_frontend_payload_edge_values(self):
        response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "긴 검색어" * 100,
                "search_mode": "recommendation_query_with_extra_context_that_is_too_long" * 2,
                "scenario": "restaurant_with_extra_context_that_is_too_long" * 2,
                "location_hint": "부산 강서구" * 20,
                "lat": 35.123456789,
                "lng": 129.123456789,
                "target_query": "",
                "category_hint": "category" * 20,
                "requested_conditions": "콘센트, 조용함",
                "menu_keywords": {"label": "소금빵"},
                "place_type_keywords": None,
                "preferred_tags": [{"displayName": "실내쉼터"}],
                "negative_tags": "[\"혼잡\"]",
                "result_count": "5.8",
                "db_result_count": -1,
                "kakao_result_count": None,
                "ai_web_result_count": "bad-count",
                "search_plan_snapshot": ["invalid"],
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(UserSearchLog.objects.count(), 1)

        search_log = UserSearchLog.objects.get(id=response.json()["id"])
        self.assertEqual(len(search_log.query), 255)
        self.assertEqual(len(search_log.search_mode), 50)
        self.assertEqual(len(search_log.scenario), 50)
        self.assertEqual(len(search_log.location_hint), 100)
        self.assertEqual(search_log.target_query, "")
        self.assertEqual(len(search_log.category_hint), 50)
        self.assertEqual(str(search_log.lat), "35.123457")
        self.assertEqual(str(search_log.lng), "129.123457")
        self.assertEqual(search_log.requested_conditions, ["콘센트", "조용함"])
        self.assertEqual(search_log.menu_keywords, ["소금빵"])
        self.assertEqual(search_log.place_type_keywords, [])
        self.assertEqual(search_log.preferred_tags, ["실내쉼터"])
        self.assertEqual(search_log.negative_tags, ["혼잡"])
        self.assertEqual(search_log.result_count, 5)
        self.assertEqual(search_log.db_result_count, 0)
        self.assertEqual(search_log.kakao_result_count, 0)
        self.assertEqual(search_log.ai_web_result_count, 0)
        self.assertEqual(search_log.search_plan_snapshot, {})

    def test_search_log_requires_authenticated_user(self):
        response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "소금빵 맛집 찾아줘",
                "result_count": 1,
            }, ensure_ascii=False),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        self.assertIn(response.status_code, [401, 403])
        self.assertEqual(UserSearchLog.objects.count(), 0)

    def test_search_log_ignores_disallowed_result_payload_fields(self):
        response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "조용히 작업할 곳",
                "search_mode": "recommendation_query",
                "result_count": 1,
                "results": [{"name": "전체 결과를 저장하면 안 됨"}],
                "places": [{"name": "장소 목록"}],
                "raw_response": {"items": [{"title": "외부 API 전문"}]},
                "source_urls": ["https://example.com/place"],
                "user": 9999,
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        search_log = UserSearchLog.objects.get()
        self.assertEqual(search_log.user, self.user)
        self.assertEqual(search_log.result_count, 1)
        self.assertNotIn(
            "results",
            UserSearchLog.objects.values().get(id=search_log.id),
        )
        self.assertEqual(search_log.search_plan_snapshot, {})

    def test_authenticated_user_can_list_own_search_logs(self):
        other_user = get_user_model().objects.create_user(
            username="other-searcher",
            password="pass",
        )
        older_time = timezone.now() - timedelta(hours=1)
        newer_time = timezone.now()
        older_log = self._create_search_log(
            query="쌀국수 먹고 싶어",
            search_mode="recommendation_query",
            scenario="restaurant",
            location_hint="부산 강서구",
            category_hint="food",
            menu_keywords=["쌀국수"],
            result_count=8,
            db_result_count=1,
            kakao_result_count=7,
            ai_web_result_count=0,
            search_plan_snapshot={"targetQuery": "쌀국수"},
            created_at=older_time,
        )
        newer_log = self._create_search_log(
            query="소금빵 맛집 찾아줘",
            search_mode="recommendation_query",
            scenario="restaurant",
            location_hint="부산 강서구",
            target_query="소금빵 맛집",
            category_hint="cafe",
            requested_conditions=["디저트"],
            menu_keywords=["소금빵"],
            place_type_keywords=["베이커리", "카페"],
            preferred_tags=["조용함"],
            negative_tags=["혼잡"],
            result_count=10,
            db_result_count=2,
            kakao_result_count=8,
            ai_web_result_count=3,
            search_plan_snapshot={"targetQuery": "소금빵 맛집"},
            created_at=newer_time,
        )
        self._create_search_log(
            user=other_user,
            query="다른 사용자 검색어",
            result_count=99,
            created_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(
            "/api/recommendations/search-logs/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([item["id"] for item in data["results"]], [newer_log.id, older_log.id])
        self.assertEqual(data["results"][0]["query"], "소금빵 맛집 찾아줘")
        self.assertEqual(data["results"][0]["menu_keywords"], ["소금빵"])
        self.assertEqual(data["results"][0]["place_type_keywords"], ["베이커리", "카페"])
        self.assertEqual(data["results"][0]["preferred_tags"], ["조용함"])
        self.assertEqual(data["results"][0]["negative_tags"], ["혼잡"])
        self.assertEqual(data["results"][0]["result_count"], 10)
        self.assertEqual(data["results"][0]["ai_web_result_count"], 3)
        self.assertNotIn("search_plan_snapshot", data["results"][0])

    def test_search_log_list_requires_authenticated_user(self):
        self._create_search_log(query="소금빵 맛집 찾아줘")

        response = self.client.get(
            "/api/recommendations/search-logs/",
            HTTP_HOST="localhost",
        )

        self.assertIn(response.status_code, [401, 403])

    def test_search_log_list_limit_parameter_and_max_limit(self):
        now = timezone.now()
        for index in range(60):
            self._create_search_log(
                query=f"검색어 {index}",
                created_at=now + timedelta(minutes=index),
            )

        limited_response = self.client.get(
            "/api/recommendations/search-logs/",
            {"limit": 10},
            **self._auth_headers(),
        )
        max_limited_response = self.client.get(
            "/api/recommendations/search-logs/",
            {"limit": 100},
            **self._auth_headers(),
        )

        self.assertEqual(limited_response.status_code, 200)
        self.assertEqual(len(limited_response.json()["results"]), 10)
        self.assertEqual(limited_response.json()["results"][0]["query"], "검색어 59")
        self.assertEqual(max_limited_response.status_code, 200)
        self.assertEqual(len(max_limited_response.json()["results"]), 50)

    def test_search_log_list_supports_page_and_page_size(self):
        now = timezone.now()
        for index in range(12):
            self._create_search_log(
                query=f"페이지 검색어 {index}",
                created_at=now + timedelta(minutes=index),
            )

        response = self.client.get(
            "/api/recommendations/search-logs/",
            {"page": 2, "page_size": 5},
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 12)
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["page_size"], 5)
        self.assertEqual(data["total_pages"], 3)
        self.assertEqual(len(data["results"]), 5)
        self.assertEqual(data["results"][0]["query"], "페이지 검색어 6")

    def test_search_log_page_size_is_limited(self):
        now = timezone.now()
        for index in range(30):
            self._create_search_log(
                query=f"제한 검색어 {index}",
                created_at=now + timedelta(minutes=index),
            )

        response = self.client.get(
            "/api/recommendations/search-logs/",
            {"page": 1, "page_size": 100},
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["page_size"], 20)
        self.assertEqual(len(data["results"]), 20)

    def test_user_can_delete_own_search_log(self):
        search_log = self._create_search_log(query="삭제할 검색")

        response = self.client.delete(
            f"/api/recommendations/search-logs/{search_log.id}/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(UserSearchLog.objects.filter(id=search_log.id).exists())

    def test_user_cannot_delete_another_users_search_log(self):
        other_user = get_user_model().objects.create_user(
            username="other-log-owner",
            password="pass",
        )
        search_log = self._create_search_log(user=other_user, query="다른 사용자 검색")

        response = self.client.delete(
            f"/api/recommendations/search-logs/{search_log.id}/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(UserSearchLog.objects.filter(id=search_log.id).exists())

    def test_deleting_search_log_recalculates_search_log_preferences(self):
        delete_response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "소금빵 맛집",
                "menu_keywords": ["소금빵"],
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )
        keep_response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "쌀국수 맛집",
                "menu_keywords": ["쌀국수"],
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(delete_response.status_code, 201)
        self.assertEqual(keep_response.status_code, 201)
        self.assertTrue(
            UserPreference.objects.filter(
                user=self.user,
                source="search_log",
                preference_type="menu",
                key="소금빵",
            ).exists()
        )

        response = self.client.delete(
            f"/api/recommendations/search-logs/{delete_response.json()['id']}/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            UserPreference.objects.filter(
                user=self.user,
                source="search_log",
                preference_type="menu",
                key="소금빵",
            ).exists()
        )
        self.assertTrue(
            UserPreference.objects.filter(
                user=self.user,
                source="search_log",
                preference_type="menu",
                key="쌀국수",
            ).exists()
        )

    def test_deleting_search_log_keeps_user_selected_preferences(self):
        UserPreference.objects.create(
            user=self.user,
            preference_type="tag",
            key="와이파이",
            label="와이파이",
            score=10,
            source="user_selected",
        )
        response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "소금빵 맛집",
                "menu_keywords": ["소금빵"],
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        delete_response = self.client.delete(
            f"/api/recommendations/search-logs/{response.json()['id']}/",
            **self._auth_headers(),
        )

        self.assertEqual(delete_response.status_code, 204)
        self.assertTrue(
            UserPreference.objects.filter(
                user=self.user,
                source="user_selected",
                preference_type="tag",
                key="와이파이",
            ).exists()
        )

    def test_search_log_save_updates_user_preferences(self):
        response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "소금빵 맛집 찾아줘",
                "scenario": "restaurant",
                "category_hint": "cafe",
                "preferred_tags": ["조용함"],
                "requested_conditions": ["노트북 작업 가능"],
                "menu_keywords": ["소금빵"],
                "place_type_keywords": ["베이커리", "카페"],
                "target_query": "소금빵 맛집",
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        preferences = {
            (preference.preference_type, preference.key): preference
            for preference in UserPreference.objects.filter(user=self.user)
        }

        self.assertIn(("tag", "조용함"), preferences)
        self.assertIn(("condition", "노트북 작업 가능"), preferences)
        self.assertIn(("menu", "소금빵"), preferences)
        self.assertIn(("place_type", "베이커리"), preferences)
        self.assertIn(("category", "cafe"), preferences)
        self.assertIn(("scenario", "restaurant"), preferences)
        self.assertIn(("keyword", "소금빵 맛집"), preferences)
        self.assertEqual(preferences[("menu", "소금빵")].score, 1.5)
        self.assertEqual(preferences[("menu", "소금빵")].search_count, 1)

    def test_repeated_search_log_increases_preference_score_and_count(self):
        payload = {
            "query": "소금빵 맛집 찾아줘",
            "menu_keywords": ["소금빵"],
        }

        for _ in range(2):
            response = self.client.post(
                "/api/recommendations/search-logs/",
                data=json.dumps(payload, ensure_ascii=False),
                content_type="application/json",
                **self._auth_headers(),
            )
            self.assertEqual(response.status_code, 201)

        preference = UserPreference.objects.get(
            user=self.user,
            preference_type="menu",
            key="소금빵",
        )
        self.assertEqual(preference.search_count, 2)
        self.assertEqual(preference.score, 3.0)

    def test_search_log_preferences_ignore_empty_duplicate_and_too_long_values(self):
        too_long_value = "x" * 101
        too_long_target = "y" * 61
        response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "조건 검색",
                "preferred_tags": ["조용함", "조용함", " ", too_long_value],
                "target_query": too_long_target,
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        preferences = UserPreference.objects.filter(user=self.user)
        self.assertEqual(preferences.count(), 1)
        self.assertEqual(preferences.get().label, "조용함")

    def test_search_log_normalizes_condition_object_labels(self):
        response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "조건 검색",
                "requested_conditions": [
                    {"label": "식사가능"},
                    {"name": "조용함"},
                ],
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        search_log = UserSearchLog.objects.get()
        self.assertEqual(search_log.requested_conditions, ["식사가능", "조용함"])
        self.assertTrue(
            UserPreference.objects.filter(
                user=self.user,
                preference_type="condition",
                key="식사가능",
                label="식사가능",
            ).exists()
        )
        self.assertTrue(
            UserPreference.objects.filter(
                user=self.user,
                preference_type="condition",
                key="조용함",
                label="조용함",
            ).exists()
        )

    def test_search_log_preferences_ignore_unknown_objects_and_object_object_text(self):
        response = self.client.post(
            "/api/recommendations/search-logs/",
            data=json.dumps({
                "query": "조건 검색",
                "requested_conditions": [
                    {},
                    {"unknown": "무시"},
                    "[object Object]",
                ],
                "preferred_tags": [
                    {"displayName": "실내쉼터"},
                ],
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        search_log = UserSearchLog.objects.get()
        self.assertEqual(search_log.requested_conditions, [])
        self.assertEqual(search_log.preferred_tags, ["실내쉼터"])
        self.assertFalse(
            UserPreference.objects.filter(
                user=self.user,
                key__iexact="[object object]",
            ).exists()
        )
        self.assertTrue(
            UserPreference.objects.filter(
                user=self.user,
                preference_type="tag",
                key="실내쉼터",
            ).exists()
        )

    def test_rebuild_preferences_removes_object_object_pollution(self):
        UserPreference.objects.create(
            user=self.user,
            preference_type="condition",
            key="[object Object]",
            label="[object Object]",
            score=20,
            search_count=3,
        )
        self._create_search_log(
            query="조건 검색",
            requested_conditions=[
                "[object Object]",
                {"label": "식사가능"},
                {},
            ],
        )

        response = self.client.post(
            "/api/recommendations/preferences/rebuild/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            UserPreference.objects.filter(
                user=self.user,
                key__iexact="[object object]",
            ).exists()
        )
        self.assertTrue(
            UserPreference.objects.filter(
                user=self.user,
                preference_type="condition",
                key="식사가능",
            ).exists()
        )

    def test_search_log_and_preference_responses_do_not_include_object_object(self):
        self._create_search_log(
            query="조건 검색",
            requested_conditions=[
                {"label": "식사가능"},
                "[object Object]",
                {},
            ],
            preferred_tags=[
                {"name": "조용함"},
            ],
        )
        UserPreference.objects.create(
            user=self.user,
            preference_type="condition",
            key="[object Object]",
            label="[object Object]",
            score=20,
            search_count=3,
        )
        UserPreference.objects.create(
            user=self.user,
            preference_type="condition",
            key="식사가능",
            label="식사가능",
            score=2,
            search_count=1,
        )

        search_logs_response = self.client.get(
            "/api/recommendations/search-logs/",
            **self._auth_headers(),
        )
        preferences_response = self.client.get(
            "/api/recommendations/preferences/",
            **self._auth_headers(),
        )

        self.assertEqual(search_logs_response.status_code, 200)
        self.assertEqual(preferences_response.status_code, 200)
        serialized_payload = json.dumps(
            {
                "search_logs": search_logs_response.json(),
                "preferences": preferences_response.json(),
            },
            ensure_ascii=False,
        )
        self.assertNotIn("[object Object]", serialized_payload)
        self.assertEqual(
            search_logs_response.json()["results"][0]["requested_conditions"],
            ["식사가능"],
        )
        self.assertEqual(
            search_logs_response.json()["results"][0]["preferred_tags"],
            ["조용함"],
        )

    def test_authenticated_user_can_list_own_preferences(self):
        other_user = get_user_model().objects.create_user(
            username="other-preference-user",
            password="pass",
        )
        UserPreference.objects.create(
            user=self.user,
            preference_type="menu",
            key="소금빵",
            label="소금빵",
            score=6.0,
            search_count=4,
        )
        UserPreference.objects.create(
            user=other_user,
            preference_type="menu",
            key="쌀국수",
            label="쌀국수",
            score=9.0,
            search_count=5,
        )

        response = self.client.get(
            "/api/recommendations/preferences/",
            {"limit": 10, "type": "menu"},
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["label"], "소금빵")
        self.assertNotIn("쌀국수", [item["label"] for item in data["results"]])

    def test_preferences_support_source_filter_and_pagination(self):
        for index in range(7):
            UserPreference.objects.create(
                user=self.user,
                preference_type="keyword",
                key=f"자동{index}",
                label=f"자동{index}",
                score=10 - index,
                search_count=1,
                source="search_log",
            )
        for index in range(2):
            UserPreference.objects.create(
                user=self.user,
                preference_type="tag",
                key=f"직접{index}",
                label=f"직접{index}",
                score=10,
                source="user_selected",
            )

        search_log_response = self.client.get(
            "/api/recommendations/preferences/",
            {"source": "search_log", "page": 1, "page_size": 5},
            **self._auth_headers(),
        )
        user_selected_response = self.client.get(
            "/api/recommendations/preferences/",
            {"source": "user_selected", "page": 1, "page_size": 5},
            **self._auth_headers(),
        )

        self.assertEqual(search_log_response.status_code, 200)
        self.assertEqual(search_log_response.json()["count"], 7)
        self.assertEqual(search_log_response.json()["page_size"], 5)
        self.assertEqual(len(search_log_response.json()["results"]), 5)
        self.assertTrue(
            all(item["source"] == "search_log" for item in search_log_response.json()["results"])
        )
        self.assertEqual(user_selected_response.status_code, 200)
        self.assertEqual(user_selected_response.json()["count"], 2)
        self.assertTrue(
            all(item["source"] == "user_selected" for item in user_selected_response.json()["results"])
        )

    def test_preference_tags_api_returns_existing_tags(self):
        response = self.client.get(
            "/api/recommendations/preference-tags/",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertTrue(any(item["name"] == "와이파이" for item in results))
        wifi_tag = next(item for item in results if item["name"] == "와이파이")
        self.assertEqual(wifi_tag["display_name"], "와이파이")
        self.assertIn("group", wifi_tag)

    def test_preferences_require_authenticated_user(self):
        response = self.client.get(
            "/api/recommendations/preferences/",
            HTTP_HOST="localhost",
        )

        self.assertIn(response.status_code, [401, 403])

    def test_authenticated_user_can_create_user_selected_preference(self):
        response = self.client.post(
            "/api/recommendations/preferences/",
            data=json.dumps({
                "preference_type": "tag",
                "label": "노트북 작업 가능",
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        preference = UserPreference.objects.get(user=self.user)
        self.assertEqual(preference.preference_type, "tag")
        self.assertEqual(preference.label, "노트북 작업 가능")
        self.assertEqual(preference.source, "user_selected")
        self.assertGreaterEqual(preference.score, 10)

    def test_authenticated_user_can_create_user_selected_preference_by_tag_id(self):
        tag = Tag.objects.get(name="와이파이")
        response = self.client.post(
            "/api/recommendations/preferences/",
            data=json.dumps({
                "preference_type": "tag",
                "tag_id": tag.id,
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        preference = UserPreference.objects.get(user=self.user)
        self.assertEqual(preference.preference_type, "tag")
        self.assertEqual(preference.key, "와이파이")
        self.assertEqual(preference.label, "와이파이")
        self.assertEqual(preference.source, "user_selected")

    def test_user_selected_preference_by_tag_id_rejects_unknown_tag(self):
        response = self.client.post(
            "/api/recommendations/preferences/",
            data=json.dumps({
                "preference_type": "tag",
                "tag_id": 999999,
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())

    def test_user_selected_preference_by_tag_id_deduplicates(self):
        tag = Tag.objects.get(name="와이파이")

        for expected_status in [201, 200]:
            response = self.client.post(
                "/api/recommendations/preferences/",
                data=json.dumps({
                    "preference_type": "tag",
                    "tag_id": tag.id,
                }, ensure_ascii=False),
                content_type="application/json",
                **self._auth_headers(),
            )
            self.assertEqual(response.status_code, expected_status)

        self.assertEqual(
            UserPreference.objects.filter(
                user=self.user,
                preference_type="tag",
                key="와이파이",
            ).count(),
            1,
        )

    def test_user_selected_tag_preference_is_returned_with_source(self):
        tag = Tag.objects.get(name="와이파이")
        self.client.post(
            "/api/recommendations/preferences/",
            data=json.dumps({
                "preference_type": "tag",
                "tag_id": tag.id,
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        response = self.client.get(
            "/api/recommendations/preferences/",
            {"type": "tag"},
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["label"], "와이파이")
        self.assertEqual(response.json()["results"][0]["source"], "user_selected")

    def test_anonymous_user_cannot_create_user_selected_preference(self):
        response = self.client.post(
            "/api/recommendations/preferences/",
            data=json.dumps({
                "preference_type": "tag",
                "label": "조용함",
            }, ensure_ascii=False),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        self.assertIn(response.status_code, [401, 403])
        self.assertFalse(UserPreference.objects.exists())

    def test_user_selected_preference_deduplicates_same_type_and_key(self):
        UserPreference.objects.create(
            user=self.user,
            preference_type="tag",
            key="조용함",
            label="조용함",
            score=2,
            search_count=3,
            source="search_log",
        )

        response = self.client.post(
            "/api/recommendations/preferences/",
            data=json.dumps({
                "preference_type": "tag",
                "label": "조용함",
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UserPreference.objects.filter(user=self.user).count(), 1)
        preference = UserPreference.objects.get(user=self.user, key="조용함")
        self.assertEqual(preference.source, "user_selected")
        self.assertEqual(preference.search_count, 3)
        self.assertGreaterEqual(preference.score, 10)

    def test_user_selected_preference_rejects_object_object_label(self):
        response = self.client.post(
            "/api/recommendations/preferences/",
            data=json.dumps({
                "preference_type": "tag",
                "label": "[object Object]",
            }, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            UserPreference.objects.filter(
                user=self.user,
                key__iexact="[object object]",
            ).exists()
        )

    def test_user_cannot_delete_another_users_preference(self):
        other_user = get_user_model().objects.create_user(
            username="other-direct-preference-user",
            password="pass",
        )
        preference = UserPreference.objects.create(
            user=other_user,
            preference_type="tag",
            key="조용함",
            label="조용함",
            score=10,
            source="user_selected",
        )

        response = self.client.delete(
            f"/api/recommendations/preferences/{preference.id}/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(UserPreference.objects.filter(id=preference.id).exists())

    def test_user_cannot_delete_search_log_preference(self):
        preference = UserPreference.objects.create(
            user=self.user,
            preference_type="tag",
            key="조용함",
            label="조용함",
            score=4,
            search_count=2,
            source="search_log",
        )

        response = self.client.delete(
            f"/api/recommendations/preferences/{preference.id}/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(UserPreference.objects.filter(id=preference.id).exists())

    def test_user_can_delete_user_selected_preference(self):
        preference = UserPreference.objects.create(
            user=self.user,
            preference_type="tag",
            key="조용함",
            label="조용함",
            score=10,
            source="user_selected",
        )

        response = self.client.delete(
            f"/api/recommendations/preferences/{preference.id}/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(UserPreference.objects.filter(id=preference.id).exists())

    def test_rebuild_preferences_deletes_existing_and_recalculates_from_logs(self):
        UserPreference.objects.create(
            user=self.user,
            preference_type="menu",
            key="삭제될값",
            label="삭제될값",
            score=30,
            search_count=10,
        )
        self._create_search_log(
            query="소금빵 맛집 찾아줘",
            menu_keywords=["소금빵"],
            preferred_tags=["조용함"],
        )
        self._create_search_log(
            query="소금빵 카페",
            menu_keywords=["소금빵"],
            category_hint="cafe",
        )

        response = self.client.post(
            "/api/recommendations/preferences/rebuild/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "preferences rebuilt")
        self.assertFalse(
            UserPreference.objects.filter(user=self.user, key="삭제될값").exists()
        )
        menu_preference = UserPreference.objects.get(
            user=self.user,
            preference_type="menu",
            key="소금빵",
        )
        self.assertEqual(menu_preference.search_count, 2)
        self.assertEqual(menu_preference.score, 3.0)

    def test_recommendation_search_applies_limited_personalization_for_authenticated_user(self):
        UserPreference.objects.create(
            user=self.user,
            preference_type="tag",
            key="와이파이",
            label="와이파이",
            score=80,
            search_count=20,
        )

        response = self.client.get(
            "/api/recommendations/search/",
            {
                "scenario": "work_cafe",
                "lat": 35.1556,
                "lng": 129.0641,
                "limit": 3,
            },
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        first_result = response.json()["results"][0]
        self.assertGreater(first_result["personalization_boost"], 0)
        self.assertLessEqual(first_result["personalization_boost"], 5)
        self.assertIn("personalization_reasons", first_result)

    def test_user_selected_preference_is_distinguished_in_personalization_reasons(self):
        UserPreference.objects.create(
            user=self.user,
            preference_type="tag",
            key="와이파이",
            label="와이파이",
            score=80,
            search_count=0,
            source="user_selected",
        )

        response = self.client.get(
            "/api/recommendations/search/",
            {
                "scenario": "work_cafe",
                "lat": 35.1556,
                "lng": 129.0641,
                "limit": 3,
            },
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        first_result = response.json()["results"][0]
        self.assertLessEqual(first_result["personalization_boost"], 5)
        self.assertIn(
            "직접 선택한 선호 태그와 일치: 와이파이",
            first_result["personalization_reasons"],
        )

    def test_authenticated_user_can_create_place_report(self):
        response = self.client.post(
            "/api/recommendations/place-reports/",
            {
                "report_type": "tag_suggestion",
                "place": self.place.id,
                "suggested_tags": json.dumps(["와이파이"], ensure_ascii=False),
                "description": "태그가 맞는지 확인해 주세요.",
            },
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        report = PlaceReport.objects.get()
        self.assertEqual(report.user, self.user)
        self.assertEqual(report.status, "pending")
        self.assertEqual(report.place, self.place)
        self.assertEqual(report.suggested_tags, ["와이파이"])

    def test_anonymous_user_cannot_create_place_report(self):
        response = self.client.post(
            "/api/recommendations/place-reports/",
            {
                "report_type": "wrong_info",
                "description": "정보가 달라요.",
            },
            HTTP_HOST="localhost",
        )

        self.assertIn(response.status_code, [401, 403])
        self.assertFalse(PlaceReport.objects.exists())

    def test_place_report_can_save_images(self):
        image = SimpleUploadedFile(
            "evidence.jpg",
            b"fake-image",
            content_type="image/jpeg",
        )

        response = self.client.post(
            "/api/recommendations/place-reports/",
            {
                "report_type": "wrong_info",
                "place": self.place.id,
                "description": "사진을 첨부합니다.",
                "images": [image],
            },
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(PlaceReportImage.objects.count(), 1)
        self.assertEqual(PlaceReportImage.objects.get().original_name, "evidence.jpg")

    def test_place_report_rejects_unsupported_image_extension(self):
        image = SimpleUploadedFile(
            "evidence.gif",
            b"fake-image",
            content_type="image/gif",
        )

        response = self.client.post(
            "/api/recommendations/place-reports/",
            {
                "report_type": "wrong_info",
                "description": "gif는 안 됩니다.",
                "images": [image],
            },
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PlaceReport.objects.exists())

    def test_place_report_rejects_more_than_three_images(self):
        files = [
            SimpleUploadedFile(
                f"evidence-{index}.jpg",
                b"fake-image",
                content_type="image/jpeg",
            )
            for index in range(4)
        ]

        response = self.client.post(
            "/api/recommendations/place-reports/",
            {
                "report_type": "wrong_info",
                "description": "이미지가 너무 많습니다.",
                "images": files,
            },
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PlaceReport.objects.exists())

    def test_place_report_list_returns_only_own_reports(self):
        other_user = get_user_model().objects.create_user(
            username="other-report-user",
            password="pass",
        )
        PlaceReport.objects.create(
            user=self.user,
            place=self.place,
            report_type="wrong_info",
            description="내 제보",
        )
        PlaceReport.objects.create(
            user=other_user,
            place=self.place,
            report_type="wrong_info",
            description="다른 사용자 제보",
        )

        response = self.client.get(
            "/api/recommendations/place-reports/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["place_name"], self.place.name)

    def test_normal_user_cannot_access_admin_place_report_list(self):
        response = self.client.get(
            "/api/recommendations/admin/place-reports/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_access_admin_place_report_list(self):
        PlaceReport.objects.create(
            user=self.user,
            place=self.place,
            report_type="wrong_info",
            description="검토 필요",
        )

        response = self.client.get(
            "/api/recommendations/admin/place-reports/",
            **self._staff_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_staff_user_can_approve_place_report(self):
        report = PlaceReport.objects.create(
            user=self.user,
            place=self.place,
            report_type="wrong_info",
            description="승인 테스트",
        )

        response = self.client.post(
            f"/api/recommendations/admin/place-reports/{report.id}/approve/",
            data=json.dumps({"admin_note": "확인했습니다."}, ensure_ascii=False),
            content_type="application/json",
            **self._staff_headers(),
        )

        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, "approved")
        self.assertEqual(report.admin_note, "확인했습니다.")
        self.assertIsNotNone(report.reviewed_by)

    def test_staff_user_can_reject_place_report(self):
        report = PlaceReport.objects.create(
            user=self.user,
            place=self.place,
            report_type="wrong_info",
            description="반려 테스트",
        )

        response = self.client.post(
            f"/api/recommendations/admin/place-reports/{report.id}/reject/",
            data=json.dumps({"admin_note": "근거가 부족합니다."}, ensure_ascii=False),
            content_type="application/json",
            **self._staff_headers(),
        )

        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, "rejected")
        self.assertEqual(report.admin_note, "근거가 부족합니다.")
        self.assertIsNotNone(report.reviewed_at)

    def test_tag_suggestion_approval_creates_existing_tag_place_tag(self):
        tag = Tag.objects.create(name="조용함", tag_type="recommendation")
        report = PlaceReport.objects.create(
            user=self.user,
            place=self.place,
            report_type="tag_suggestion",
            suggested_tags=["조용함", "없는태그"],
            description="태그 제안",
        )

        response = self.client.post(
            f"/api/recommendations/admin/place-reports/{report.id}/approve/",
            data=json.dumps({"admin_note": "태그 확인"}, ensure_ascii=False),
            content_type="application/json",
            **self._staff_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created_place_tags"], 1)
        self.assertEqual(response.json()["skipped_tags"], ["없는태그"])
        self.assertTrue(
            PlaceTag.objects.filter(
                place=self.place,
                tag=tag,
                source="user_verified",
                status="confirmed",
                is_verified=True,
            ).exists()
        )

    @patch("recommendations.views.search_places_by_keyword", return_value={"documents": []})
    def test_tag_suggestion_approval_makes_tag_searchable_on_general_map(self, mock_kakao):
        tag = Tag.objects.create(name="조용함", tag_type="recommendation")
        report = PlaceReport.objects.create(
            user=self.user,
            place=self.place,
            report_type="tag_suggestion",
            suggested_tags=["조용함"],
            description="지도 검색에 쓰일 태그",
        )

        approve_response = self.client.post(
            f"/api/recommendations/admin/place-reports/{report.id}/approve/",
            data=json.dumps({"admin_note": "태그 확인"}, ensure_ascii=False),
            content_type="application/json",
            **self._staff_headers(),
        )
        search_response = self.client.get(
            "/api/recommendations/map-search/",
            {"q": "조용함", "source": "db", "limit": 10},
            HTTP_HOST="localhost",
        )

        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(search_response.status_code, 200)
        result_names = [item["name"] for item in search_response.json()["results"]]
        self.assertIn(self.place.name, result_names)
        self.assertTrue(
            PlaceTag.objects.filter(
                place=self.place,
                tag=tag,
                source="user_verified",
                status="confirmed",
            ).exists()
        )

    def test_tag_suggestion_approval_does_not_duplicate_place_tag(self):
        report = PlaceReport.objects.create(
            user=self.user,
            place=self.place,
            report_type="tag_suggestion",
            suggested_tags=["와이파이"],
            description="이미 있는 태그",
        )
        before_count = PlaceTag.objects.filter(place=self.place, tag__name="와이파이").count()

        response = self.client.post(
            f"/api/recommendations/admin/place-reports/{report.id}/approve/",
            data=json.dumps({"admin_note": "중복 확인"}, ensure_ascii=False),
            content_type="application/json",
            **self._staff_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created_place_tags"], 0)
        self.assertEqual(
            PlaceTag.objects.filter(place=self.place, tag__name="와이파이").count(),
            before_count,
        )

    def test_non_db_linking_report_approval_only_updates_status_and_note(self):
        for report_type in ["wrong_info"]:
            report = PlaceReport.objects.create(
                user=self.user,
                report_type=report_type,
                suggested_name=f"{report_type} 장소",
                description="상태만 변경",
            )

            response = self.client.post(
                f"/api/recommendations/admin/place-reports/{report.id}/approve/",
                data=json.dumps({"admin_note": "후속 처리 예정"}, ensure_ascii=False),
                content_type="application/json",
                **self._staff_headers(),
            )

            self.assertEqual(response.status_code, 200)
            report.refresh_from_db()
            self.assertEqual(report.status, "approved")
            self.assertEqual(report.admin_note, "후속 처리 예정")

    def test_new_place_report_approval_requires_place_fields(self):
        report = PlaceReport.objects.create(
            user=self.user,
            report_type="new_place",
            suggested_name="좌표 없는 장소",
            description="좌표 누락",
        )

        response = self.client.post(
            f"/api/recommendations/admin/place-reports/{report.id}/approve/",
            data=json.dumps({"admin_note": "확인"}, ensure_ascii=False),
            content_type="application/json",
            **self._staff_headers(),
        )

        self.assertEqual(response.status_code, 400)
        report.refresh_from_db()
        self.assertEqual(report.status, "pending")

    @patch("recommendations.views.search_places_by_keyword", return_value={"documents": []})
    def test_new_place_report_approval_creates_searchable_place(self, mock_kakao):
        report = PlaceReport.objects.create(
            user=self.user,
            report_type="new_place",
            suggested_name="새 지도 쉼터",
            suggested_category="쉼터",
            suggested_address="부산 테스트구 새길 10",
            suggested_lat=35.155800,
            suggested_lng=129.064300,
            suggested_tags=["새태그"],
            description="새 장소 제보",
        )

        approve_response = self.client.post(
            f"/api/recommendations/admin/place-reports/{report.id}/approve/",
            data=json.dumps({"admin_note": "새 장소 확인"}, ensure_ascii=False),
            content_type="application/json",
            **self._staff_headers(),
        )
        report.refresh_from_db()
        search_response = self.client.get(
            "/api/recommendations/map-search/",
            {"q": "새 지도 쉼터", "source": "db", "limit": 10},
            HTTP_HOST="localhost",
        )

        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["created_places"], 1)
        self.assertIsNotNone(report.place)
        self.assertEqual(report.place.name, "새 지도 쉼터")
        self.assertTrue(
            PlaceTag.objects.filter(place=report.place, tag__name="새태그", source="user_verified").exists()
        )
        self.assertEqual(search_response.status_code, 200)
        result = search_response.json()["results"][0]
        self.assertEqual(result["name"], "새 지도 쉼터")
        self.assertEqual(result["result_source"], "db")

    @patch("recommendations.views.search_places_by_keyword")
    def test_general_map_search_combines_db_and_kakao_places(self, mock_kakao):
        mock_kakao.return_value = {
            "documents": [
                {
                    "id": "987654321",
                    "place_name": "카카오 테스트 카페",
                    "category_name": "음식점 > 카페",
                    "road_address_name": "부산 테스트구 카카오로 1",
                    "address_name": "부산 테스트동",
                    "x": "129.064500",
                    "y": "35.155900",
                    "phone": "051-000-0000",
                    "place_url": "https://place.map.kakao.com/987654321",
                    "distance": "120",
                }
            ]
        }

        response = self.client.get(
            "/api/recommendations/map-search/",
            {"q": "카페", "lat": 35.1556, "lng": 129.0641, "radius": 1000, "limit": 10},
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        sources = {item["result_source"] for item in data["results"]}
        self.assertIn("db", sources)
        self.assertIn("kakao", sources)
        self.assertEqual(data["candidate_counts"]["kakao"], 1)

    def test_recommendation_search_does_not_apply_personalization_for_anonymous_user(self):
        UserPreference.objects.create(
            user=self.user,
            preference_type="tag",
            key="와이파이",
            label="와이파이",
            score=80,
            search_count=20,
        )

        response = self.client.get(
            "/api/recommendations/search/",
            {
                "scenario": "work_cafe",
                "lat": 35.1556,
                "lng": 129.0641,
                "limit": 3,
            },
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        first_result = response.json()["results"][0]
        self.assertEqual(first_result["personalization_boost"], 0)

    def test_db_recommendation_search_returns_saved_place(self):
        response = self.client.get(
            "/api/recommendations/search/",
            {
                "scenario": "work_cafe",
                "lat": 35.1556,
                "lng": 129.0641,
                "limit": 3,
            },
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scenario"], "work_cafe")
        self.assertEqual(data["conditions"]["radius"], 1500)
        self.assertEqual(data["results"][0]["id"], self.place.id)
        self.assertIn("와이파이", data["results"][0]["verified_tags"])
        self.assertEqual(data["results"][0]["match_level"], "tag_matched")
        self.assertIn("matched_tags", data["results"][0])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_WEB_SEARCH_AUTO_MERGE_ENABLED=False,
    )
    @patch("recommendations.views.search_db_recommendations", side_effect=AssertionError("legacy DB recommender must not run"))
    @patch("recommendations.views.build_conversational_search_plan", side_effect=AssertionError("legacy conversational planner must not run"))
    @patch("recommendations.views.parse_situation", side_effect=AssertionError("parse_situation must not reroute /ai-search"))
    @patch("recommendations.services.ai_search_orchestrator.search_places_by_keyword", return_value={"documents": []})
    @patch("recommendations.services.ai_search_orchestrator.semantic_rerank_candidates")
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_recommendation_search_uses_unified_pipeline_for_frame_results(
        self,
        mock_intent,
        mock_rerank,
        mock_kakao,
        mock_parse,
        mock_legacy_plan,
        mock_legacy_db,
    ):
        mock_intent.return_value = {
            "action": "search",
            "decision_action": "search",
            "normalized_query": "와이파이 되는 조용한 작업 카페",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": ["작업 카페"],
                "candidate_place_types": ["카페"],
                "result_match_terms": ["작업", "카페"],
                "constraints": ["와이파이", "조용한"],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": ["작업 카페"],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.9,
            "ai_retry_count": 0,
        }

        def fake_rerank(frame, candidates, **kwargs):
            self.assertEqual(frame["target_objects"], ["작업 카페"])
            self.assertTrue(candidates)
            return [
                {
                    **candidates[0],
                    "semantic_score": 92,
                    "evidence_level": "strong",
                    "semantic_reason": "verified DB evidence matches frame",
                    "backend_rank": 1,
                    "unified_rank": 1,
                    "unified_ranker_applied": True,
                }
            ], {
                "status": "executed",
                "input_count": len(candidates),
                "included_count": 1,
                "excluded_count": max(len(candidates) - 1, 0),
                "excluded_candidates": [],
            }

        mock_rerank.side_effect = fake_rerank
        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps(
                {"query": "와이파이 되는 조용한 작업 카페", "lat": 35.1556, "lng": 129.0641, "limit": 3},
                ensure_ascii=False,
            ),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["unified_candidate_pipeline"])
        self.assertTrue(data["frontend_should_preserve_order"])
        self.assertTrue(data["frontend_should_skip_kakao_fallback"])
        self.assertEqual(data["debug_pipeline"]["used_path"], "ai_first_orchestrator")
        self.assertFalse(data["debug_pipeline"]["legacy_path_used"])
        self.assertEqual(data["ai_parse"]["scenario"], "ai_place_search")
        self.assertEqual(data["results"][0]["place_id"], self.place.id)
        self.assertEqual(data["candidate_pipeline"], "ai_first_unified_evidence")
        self.assertIn("ai_web_search", data)
        self.assertIn("candidates", data["ai_web_search"])
        self.assertFalse(data["ai_web_search"]["executed"])
        mock_kakao.assert_called()
        mock_rerank.assert_called_once()

    @override_settings(
        AI_PROVIDER="rule",
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_recommendation_search_does_not_auto_run_web_search(self, mock_post):
        response = self.client.post(
            "/api/recommendations/ai-search/",
            {
                "query": "브런치 먹기 좋은 조용한 카페 추천",
                "lat": 35.1556,
                "lng": 129.0641,
                "limit": 3,
            },
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["ai_web_search"]["reason"], "manual_required")
        self.assertFalse(data["ai_web_search"]["executed"])
        mock_post.assert_not_called()

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=False,
    )
    def test_ai_web_search_returns_unsupported_without_grounding_support(self):
        result = get_ai_web_search_result(
            query="혼자 밥 먹기 좋은 식당 추천",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "restaurant", "keywords": ["혼밥", "식당"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertTrue(result["enabled"])
        self.assertFalse(result["executed"])
        self.assertFalse(result["supported"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "unsupported_web_search")

    @override_settings(
        AI_WEB_SEARCH_ENABLED=False,
        AI_WEB_SEARCH_AVAILABLE=False,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=False,
    )
    def test_ai_web_search_returns_disabled_when_feature_is_off(self):
        result = get_ai_web_search_result(
            query="브런치 먹기 좋은 카페 추천",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertFalse(result["enabled"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["reason"], "disabled")

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="",
        NAVER_SEARCH_CLIENT_SECRET="",
    )
    def test_naver_search_returns_missing_credentials(self):
        result = get_ai_web_search_result(
            query="소금빵 맛집 찾아줘",
            manual=True,
        )

        self.assertTrue(result["enabled"])
        self.assertTrue(result["supported"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["provider"], "naver_search")
        self.assertEqual(result["error"], "missing_credentials")
        self.assertEqual(result["reason"], "missing_naver_search_credentials")

    @override_settings(
        DEBUG=True,
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        NAVER_SEARCH_DISPLAY=5,
        NAVER_SEARCH_SORT="sim",
        GMS_API_KEY="",
        GMS_API_URL="",
    )
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_uses_local_result_first(self, mock_get):
        mock_get.return_value = self._make_naver_response([
            {
                "title": "<b>서면 소금빵</b> 카페",
                "link": "https://example.com/local",
                "description": "소금빵을 소개하는 검색 결과",
                "category": "카페",
                "address": "부산 부산진구 테스트동",
                "roadAddress": "부산 부산진구 테스트로 1",
            }
        ])

        result = get_ai_web_search_result(
            query="서면 소금빵 맛집",
            location_hint="서면",
            search_plan={"targetQuery": "소금빵 맛집"},
            manual=True,
        )

        self.assertEqual(result["provider"], "naver_search")
        self.assertTrue(result["executed"])
        self.assertEqual(result["reason"], "search_api_reference")
        self.assertEqual(result["candidates"][0]["candidate_type"], "web_source_reference")
        self.assertEqual(result["candidates"][0]["source_channel"], "local")
        self.assertEqual(result["candidates"][0]["source_url"], "https://example.com/local")
        self.assertEqual(mock_get.call_count, 1)

    @override_settings(
        DEBUG=True,
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="",
        GMS_API_URL="",
    )
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_falls_back_to_blog_when_local_empty(self, mock_get):
        mock_get.side_effect = [
            self._make_naver_response([]),
            self._make_naver_response([
                {
                    "title": "부산 사상구 소금빵 후기",
                    "link": "https://example.com/blog",
                    "description": "부산 사상구 블로그 검색 결과입니다.",
                }
            ]),
        ]

        result = get_ai_web_search_result(
            query="서면 소금빵 맛집",
            location_hint="부산 사상구",
            search_plan={"targetQuery": "소금빵 맛집"},
            manual=True,
        )

        self.assertEqual(result["reason"], "search_api_reference")
        self.assertEqual(result["candidates"][0]["source_channel"], "blog")
        self.assertEqual(result["candidates"][0]["source_url"], "https://example.com/blog")
        self.assertEqual(mock_get.call_count, 2)

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="",
        GMS_API_URL="",
    )
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_returns_no_result_when_all_channels_empty(self, mock_get):
        mock_get.side_effect = [
            self._make_naver_response([]),
            self._make_naver_response([]),
            self._make_naver_response([]),
        ]

        result = get_ai_web_search_result(
            query="결과 없는 검색어",
            location_hint="부산 사상구",
            manual=True,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["reason"], "no_search_result")
        self.assertEqual(mock_get.call_count, 3)

    @override_settings(
        DEBUG=True,
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="",
        GMS_API_URL="",
    )
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_filters_blog_results_that_do_not_match_location(self, mock_get):
        mock_get.side_effect = [
            self._make_naver_response([]),
            self._make_naver_response([
                {
                    "title": "김포 소금빵 맛집",
                    "link": "https://example.com/gimpo",
                    "description": "김포 베이커리 후기입니다.",
                },
                {
                    "title": "청주빵집",
                    "link": "https://example.com/cheongju",
                    "description": "청주 소금빵 후기입니다.",
                },
                {
                    "title": "담양 소금빵",
                    "link": "https://example.com/damyang",
                    "description": "담양 카페 후기입니다.",
                },
            ]),
            self._make_naver_response([]),
        ]

        result = get_ai_web_search_result(
            query="소금빵 맛집",
            location_hint="부산 사상구",
            search_plan={"targetQuery": "소금빵 맛집"},
            manual=True,
        )

        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["reason"], "no_location_matched_search_result")
        self.assertEqual(result["debug_summary"]["query"], "부산 사상구 소금빵 맛집")
        self.assertEqual(result["debug_summary"]["source_channel"], "blog")
        self.assertEqual(result["debug_summary"]["raw_result_count"], 3)
        self.assertEqual(result["debug_summary"]["location_matched_count"], 0)
        self.assertEqual(result["debug_summary"]["filtered_out_count"], 3)
        self.assertIn("부산", result["debug_summary"]["location_terms"])
        self.assertIn("사상", result["debug_summary"]["location_terms"])
        self.assertIn("사상구", result["debug_summary"]["location_terms"])

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="",
        GMS_API_URL="",
    )
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_builds_blog_candidate_when_location_matches(self, mock_get):
        mock_get.side_effect = [
            self._make_naver_response([]),
            self._make_naver_response([
                {
                    "title": "부산 사상구 소금빵 후기",
                    "link": "https://example.com/sasang",
                    "description": "부산 사상구 소금빵 카페 후기입니다.",
                },
            ]),
        ]

        result = get_ai_web_search_result(
            query="소금빵 맛집",
            location_hint="부산 사상구",
            search_plan={"targetQuery": "소금빵 맛집"},
            manual=True,
        )

        self.assertEqual(result["reason"], "search_api_reference")
        self.assertEqual(result["candidates"][0]["source_channel"], "blog")
        self.assertEqual(result["candidates"][0]["source_url"], "https://example.com/sasang")

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="",
        GMS_API_URL="",
    )
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_limits_blog_fallback_without_location_hint(self, mock_get):
        mock_get.return_value = self._make_naver_response([])

        result = get_ai_web_search_result(
            query="소금빵 맛집",
            manual=True,
        )

        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["reason"], "missing_location_hint_for_broad_search")
        self.assertEqual(mock_get.call_count, 1)

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="",
        GMS_API_URL="",
    )
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_returns_sanitized_api_error(self, mock_get):
        response = Mock()
        response.status_code = 400
        response.json.return_value = {"errorMessage": "Bad <b>request</b>"}
        error = requests.HTTPError("bad request")
        error.response = response
        response.raise_for_status.side_effect = error
        mock_get.return_value = response

        result = get_ai_web_search_result(
            query="소금빵 맛집",
            manual=True,
        )

        self.assertEqual(result["error"], "api_error")
        self.assertEqual(result["reason"], "request_failed")
        self.assertEqual(result["error_detail"]["status_code"], 400)
        self.assertEqual(result["error_detail"]["type"], "bad_request")
        self.assertEqual(result["error_detail"]["message"], "Bad request")

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="",
        GMS_API_URL="",
    )
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_strips_html_tags(self, mock_get):
        mock_get.return_value = self._make_naver_response([
            {
                "title": "<b>태그</b> 제거 카페",
                "link": "https://example.com/local",
                "description": "<b>설명</b> 요약",
                "roadAddress": "부산 테스트로 1",
            }
        ])

        result = get_ai_web_search_result(
            query="태그 제거 카페",
            manual=True,
        )

        candidate = result["candidates"][0]
        self.assertEqual(candidate["name"], "태그 제거 카페")
        self.assertEqual(candidate["source_title"], "태그 제거 카페")
        self.assertEqual(candidate["evidence_summary"], "설명 요약")

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="",
        GMS_API_URL="",
    )
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_target_condition_query_uses_target_not_condition_fallback(self, mock_get):
        mock_get.return_value = self._make_naver_response([
            {
                "title": "맥도날드 서면점",
                "link": "https://example.com/mcdonalds",
                "description": "검색 API 참고 결과입니다.",
                "roadAddress": "부산 부산진구 테스트로 2",
            }
        ])

        search_plan = {
            "targetQuery": "맥도날드",
            "requestedConditions": ["흡연 가능 여부"],
        }
        self.assertEqual(
            build_naver_search_query(
                "흡연 가능한 맥도날드",
                location_hint="부산 사상구",
                search_plan=search_plan,
            ),
            "부산 사상구 맥도날드",
        )

        result = get_ai_web_search_result(
            query="흡연 가능한 맥도날드",
            location_hint="부산 사상구",
            search_plan=search_plan,
            manual=True,
        )

        request_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(request_params["query"], "부산 사상구 맥도날드")
        self.assertNotIn("흡연", request_params["query"])
        self.assertEqual(result["candidates"][0]["requested_conditions"], ["흡연 가능 여부"])
        self.assertIn("확인", result["candidates"][0]["condition_notice"])

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        NAVER_SEARCH_DISPLAY=7,
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/summary",
        AI_INTENT_MODEL="gpt-5-nano",
    )
    @patch("recommendations.services.naver_search_provider.requests.post")
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_adds_ai_summary_from_search_candidates(self, mock_get, mock_post):
        mock_get.return_value = self._make_naver_response([
            {
                "title": f"부산 강서구 소금빵 카페 {index}",
                "link": f"https://example.com/local-{index}",
                "description": "부산 강서구 소금빵 관련 검색 결과입니다.",
                "category": "카페",
                "roadAddress": f"부산 강서구 테스트로 {index}",
            }
            for index in range(6)
        ])
        post_response = Mock()
        post_response.raise_for_status.return_value = None
        post_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": {
                                    "title": "AI 웹 검색 요약",
                                    "main_text": "웹 검색 결과에서 부산 강서구의 소금빵 관련 글이 확인됩니다.",
                                    "keywords": ["부산 강서구", "소금빵", "카페"],
                                    "caution": "웹 검색 출처 기반 참고 정보이며, 실제 메뉴와 운영 정보는 방문 전 확인이 필요합니다.",
                                }
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        mock_post.return_value = post_response

        result = get_ai_web_search_result(
            query="소금빵 맛집 찾아줘",
            location_hint="부산 강서구",
            search_plan={"targetQuery": "소금빵 맛집"},
            manual=True,
        )

        self.assertEqual(result["reason"], "search_api_reference")
        self.assertEqual(len(result["candidates"]), 5)
        self.assertEqual(result["summary"]["summary_source"], "ai")
        self.assertEqual(
            result["summary"]["main_text"],
            "웹 검색 결과에서 부산 강서구의 소금빵 관련 글이 확인됩니다.",
        )
        self.assertEqual(result["summary"]["keywords"], ["부산 강서구", "소금빵", "카페"])

        mock_post.assert_called_once()
        post_payload = mock_post.call_args.kwargs["json"]
        user_payload = json.loads(post_payload["messages"][1]["content"])
        self.assertEqual(len(user_payload["candidates"]), 5)
        self.assertEqual(user_payload["candidates"][0]["source_title"], "부산 강서구 소금빵 카페 0")
        self.assertNotIn("fake-secret", post_payload["messages"][1]["content"])
        self.assertNotIn("X-Naver", post_payload["messages"][1]["content"])

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/summary",
    )
    @patch("recommendations.services.naver_search_provider.requests.post")
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_keeps_candidates_when_ai_summary_fails(self, mock_get, mock_post):
        mock_get.return_value = self._make_naver_response([
            {
                "title": "부산 강서구 브런치 카페",
                "link": "https://example.com/brunch",
                "description": "부산 강서구 브런치 관련 검색 결과입니다.",
                "category": "카페",
                "roadAddress": "부산 강서구 테스트로 1",
            }
        ])
        mock_post.side_effect = requests.Timeout("summary timeout")

        result = get_ai_web_search_result(
            query="브런치 카페 추천해줘",
            location_hint="부산 강서구",
            search_plan={"targetQuery": "브런치 카페"},
            manual=True,
        )

        self.assertEqual(result["reason"], "search_api_reference")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["summary"]["summary_source"], "fallback")
        self.assertEqual(
            result["summary"]["main_text"],
            "웹 검색 결과에서 요청과 관련된 참고 링크가 확인되었습니다.",
        )

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_PROVIDER="naver_search",
        NAVER_SEARCH_CLIENT_ID="fake-id",
        NAVER_SEARCH_CLIENT_SECRET="fake-secret",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/summary",
    )
    @patch("recommendations.services.naver_search_provider.requests.post")
    @patch("recommendations.services.naver_search_provider.requests.get")
    def test_naver_search_sanitizes_assertive_ai_summary(self, mock_get, mock_post):
        mock_get.return_value = self._make_naver_response([
            {
                "title": "부산 강서구 쌀국수 식당",
                "link": "https://example.com/pho",
                "description": "부산 강서구 쌀국수 관련 검색 결과입니다.",
                "category": "음식점",
                "roadAddress": "부산 강서구 테스트로 2",
            }
        ])
        post_response = Mock()
        post_response.raise_for_status.return_value = None
        post_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": {
                                    "title": "AI 웹 검색 요약",
                                    "main_text": "이곳은 맛집입니다. 쌀국수를 판매합니다.",
                                    "keywords": ["부산 강서구", "쌀국수"],
                                    "caution": "",
                                }
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        mock_post.return_value = post_response

        result = get_ai_web_search_result(
            query="쌀국수 먹고 싶어",
            location_hint="부산 강서구",
            search_plan={"targetQuery": "쌀국수"},
            manual=True,
        )

        self.assertEqual(result["summary"]["summary_source"], "ai")
        self.assertEqual(
            result["summary"]["main_text"],
            "웹 검색 결과에서 요청과 관련된 참고 링크가 확인되었습니다.",
        )
        self.assertNotIn("판매합니다", result["summary"]["main_text"])
        self.assertNotIn("맛집입니다", result["summary"]["main_text"])

    def test_naver_search_query_uses_location_hint_and_target_query(self):
        self.assertEqual(
            build_naver_search_query(
                "소금빵 맛집 찾아줘",
                location_hint="부산 사상구",
                search_plan={"targetQuery": "소금빵 맛집"},
            ),
            "부산 사상구 소금빵 맛집",
        )

    def test_naver_search_query_prefers_search_plan_location_query(self):
        self.assertEqual(
            build_naver_search_query(
                "서면역 소금빵 맛집",
                location_hint="부산 사상구",
                search_plan={
                    "locationQuery": "서면역",
                    "targetQuery": "소금빵 맛집",
                },
            ),
            "서면역 소금빵 맛집",
        )

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
        AI_WEB_SEARCH_MODEL="gpt-5-nano",
        AI_WEB_SEARCH_REASONING_EFFORT="minimal",
        AI_WEB_SEARCH_MAX_OUTPUT_TOKENS=1200,
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_normalizes_gms_candidates(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({
                                "candidates": [
                                    {
                                        "name": "테스트 혼밥 식당",
                                        "address_hint": "부산 테스트동",
                                        "category_hint": "식당",
                                        "matched_conditions": ["혼밥", "식당"],
                                        "evidence_summary": "웹 검색 결과에서 조건과 관련된 후보로 확인되었습니다.",
                                        "source_url": "https://example.com/place",
                                        "confidence": "low",
                                    }
                                ],
                                "search_queries": ["혼밥 식당"],
                                "summary": "테스트 요약",
                            }, ensure_ascii=False),
                        }
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="혼자 밥 먹기 좋은 식당 추천",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "restaurant", "keywords": ["혼밥", "식당"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["candidates"][0]["source_type"], "ai_search_candidate")
        self.assertEqual(result["candidates"][0]["fallback_level"], 6)
        self.assertEqual(result["candidates"][0]["confidence"], "low")
        self.assertNotIn("lat", result["candidates"][0])
        self.assertEqual(mock_post.call_args.kwargs["json"]["model"], "gpt-5-nano")
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["tools"],
            [{"type": "web_search"}],
        )
        self.assertNotIn("reasoning", mock_post.call_args.kwargs["json"])
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://example.invalid/gmsapi/api.openai.com/v1/responses",
        )
        self.assertEqual(mock_post.call_args.kwargs["json"]["max_output_tokens"], 800)
        self.assertEqual(
            result["candidates"][0]["evidence_sources"],
            [{"title": "web search source", "url": "https://example.com/place"}],
        )
        prompt_input = mock_post.call_args.kwargs["json"]["input"]
        self.assertIn("source_url", prompt_input)
        self.assertNotIn("evidence_sources", prompt_input)
        self.assertNotIn("existing_results_summary", prompt_input)
        self.assertNotIn("category_hint", prompt_input)
        self.assertNotIn("address_hint", prompt_input)
        self.assertNotIn("evidence_summary", prompt_input)
        self.assertNotIn("https://...", prompt_input)

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
        AI_WEB_SEARCH_MAX_CANDIDATES=5,
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_limits_candidates_to_one(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "output_text": json.dumps({
                "candidates": [
                    {
                        "name": "first candidate",
                        "category_hint": "cafe",
                        "address_hint": "Busan",
                        "evidence_summary": "First source matched the query.",
                        "source_url": "https://example.com/first",
                    },
                    {
                        "name": "second candidate",
                        "category_hint": "cafe",
                        "address_hint": "Busan",
                        "evidence_summary": "Second source matched the query.",
                        "source_url": "https://example.com/second",
                    },
                ]
            })
        }
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="quiet brunch cafe",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "work_cafe", "keywords": ["brunch", "cafe"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["error"], "")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["name"], "first candidate")

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_endpoint_runs_only_manual_request(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({
                                "candidates": [
                                    {
                                        "name": "테스트 웹 후보",
                                        "source_url": "https://example.com/web-place",
                                    }
                                ]
                            }, ensure_ascii=False),
                        }
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        response = self.client.post(
            "/api/recommendations/ai-web-search/",
            {
                "query": "브런치 먹기 좋은 조용한 카페 추천",
                "lat": 35.1556,
                "lng": 129.0641,
                "condition": {"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
                "existing_results_summary": {"db_count": 0, "kakao_fallback_count": 0},
            },
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["ai_web_search"]
        self.assertTrue(data["executed"])
        self.assertEqual(data["candidates"][0]["name"], "테스트 웹 후보")
        self.assertEqual(mock_post.call_count, 1)

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_endpoint_manual_request_bypasses_enough_results(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({
                                "candidates": [
                                    {
                                        "name": "충분 결과 수동 후보",
                                        "source_url": "https://example.com/manual",
                                    }
                                ]
                            }, ensure_ascii=False),
                        }
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        response = self.client.post(
            "/api/recommendations/ai-web-search/",
            {
                "query": "브런치 먹기 좋은 조용한 카페 추천",
                "lat": 35.1556,
                "lng": 129.0641,
                "condition": {"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
                "existing_results_summary": {
                    "db_count": 10,
                    "kakao_fallback_count": 5,
                    "total_count": 15,
                    "weak_match_count": 0,
                },
            },
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["ai_web_search"]
        self.assertTrue(data["executed"])
        self.assertNotEqual(data["reason"], "enough_existing_results")
        self.assertEqual(data["candidates"][0]["name"], "충분 결과 수동 후보")
        self.assertEqual(mock_post.call_count, 1)

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_requires_strict_execution_conditions(self, mock_post):
        result = get_ai_web_search_result(
            query="가까운 카페",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "work_cafe", "keywords": ["카페"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
        )

        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "enough_existing_results")
        mock_post.assert_not_called()

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_auto_request_still_blocks_enough_results(self, mock_post):
        result = get_ai_web_search_result(
            query="브런치 먹기 좋은 조용한 카페 추천",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
            existing_results_summary={
                "db_count": 10,
                "kakao_fallback_count": 5,
                "total_count": 15,
                "weak_match_count": 0,
            },
        )

        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "enough_existing_results")
        mock_post.assert_not_called()

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_uses_cache_for_duplicate_request(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({
                                "candidates": [
                                    {
                                        "name": "테스트 브런치 카페",
                                        "source_url": "https://example.com/cafe",
                                    }
                                ]
                            }, ensure_ascii=False),
                        }
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        kwargs = {
            "query": "브런치 먹기 좋은 조용한 카페 추천",
            "lat": 35.1556,
            "lng": 129.0641,
            "condition": {"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
            "existing_results_summary": {"db_count": 0, "kakao_fallback_count": 0},
            "manual": True,
        }
        first = get_ai_web_search_result(**kwargs)
        second = get_ai_web_search_result(**kwargs)

        self.assertTrue(first["executed"])
        self.assertFalse(second["executed"])
        self.assertTrue(second["cached"])
        self.assertEqual(mock_post.call_count, 1)

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_parses_valid_candidate_from_incomplete_response(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({
                                "candidates": [
                                    {
                                        "name": "살리면 안 되는 후보",
                                        "source_url": "https://example.com/partial",
                                    }
                                ]
                            }, ensure_ascii=False),
                        }
                    ],
                }
            ],
        }
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="브런치 먹기 좋은 조용한 카페 추천",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["warning"], "incomplete_response")
        self.assertEqual(result["reason"], "completed_with_incomplete_response")
        self.assertEqual(result["candidates"][0]["name"], "살리면 안 되는 후보")

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_builds_source_reference_from_incomplete_sources(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "query": "salt bread cafe",
                        "sources": [
                            {
                                "title": "Salt bread cafe result",
                                "url": "https://example.com/source",
                            }
                        ],
                    },
                },
                {
                    "type": "message",
                    "content": [{
                        "type": "output_text",
                        "text": "Sources were found, but no JSON candidate was completed.",
                    }],
                },
            ],
        }
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="salt bread cafe",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "restaurant", "menu_keywords": ["salt bread"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["reason"], "source_reference_fallback")
        self.assertEqual(result["warning"], "incomplete_response")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["candidate_type"], "web_source_reference")
        self.assertEqual(result["candidates"][0]["name"], "웹 검색 참고 결과")
        self.assertEqual(result["candidates"][0]["source_url"], "https://example.com/source")
        self.assertEqual(result["candidates"][0]["source_title"], "Salt bread cafe result")
        self.assertEqual(result["candidates"][0]["source_query"], "salt bread cafe")
        self.assertGreater(result["debug_summary"]["source_count"], 0)
        self.assertIn("web_search_call", result["debug_summary"]["output_types"])
        self.assertEqual(result["debug_summary"]["web_search_source_count"], 1)

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_builds_source_reference_from_message_citation(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Search completed.",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "title": "Citation source",
                                    "url": "https://example.com/citation",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="salt bread cafe",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "restaurant", "menu_keywords": ["salt bread"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertEqual(result["error"], "")
        self.assertEqual(result["reason"], "source_reference_fallback")
        self.assertEqual(result["candidates"][0]["candidate_type"], "web_source_reference")
        self.assertEqual(result["candidates"][0]["source_url"], "https://example.com/citation")
        self.assertEqual(result["debug_summary"]["message_count"], 1)
        self.assertEqual(result["debug_summary"]["url_citation_count"], 1)

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_incomplete_without_source_returns_detail(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "reasoning",
                    "status": "completed",
                },
                {
                    "type": "web_search_call",
                    "status": "incomplete",
                    "action": {
                        "type": "search",
                        "query": "salt bread cafe",
                        "sources": [],
                    },
                },
            ],
        }
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="salt bread cafe",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "restaurant", "menu_keywords": ["salt bread"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "incomplete_response")
        self.assertEqual(result["reason"], "reasoning_output_exhausted")
        self.assertEqual(result["error_detail"]["status"], "incomplete")
        self.assertEqual(
            result["error_detail"]["message"],
            "AI web search stopped before generating a final message.",
        )
        debug_summary = result["error_detail"]["debug_summary"]
        self.assertEqual(debug_summary["source_count"], 0)
        self.assertEqual(debug_summary["output_url_count"], 0)
        self.assertEqual(debug_summary["instruction_url_count"], 0)
        self.assertIn("web_search_call", debug_summary["output_types"])
        self.assertEqual(debug_summary["reasoning_count"], 1)
        self.assertEqual(debug_summary["message_count"], 0)
        self.assertEqual(debug_summary["web_search_call_count"], 1)
        self.assertEqual(debug_summary["web_search_source_count"], 0)
        self.assertEqual(debug_summary["first_output_preview"]["type"], "reasoning")
        self.assertEqual(debug_summary["web_search_action_keys"], ["type", "query", "sources"])

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_rejects_bad_source_url_reference(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "query": "salt bread cafe",
                        "sources": [
                            {
                                "title": "Bad source",
                                "url": "not-a-url",
                            }
                        ],
                    },
                }
            ],
        }
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="salt bread cafe",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "restaurant", "menu_keywords": ["salt bread"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "incomplete_response")

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_builds_candidate_from_text_and_source(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                "Name: Salt Bread Cafe\n"
                                "Category: cafe\n"
                                "Address: Busan\n"
                                "Evidence: Web search result mentions this place.\n"
                                "Source: https://example.com/salt-bread"
                            ),
                        }
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="salt bread cafe",
            lat=35.1556,
            lng=129.0641,
            condition={
                "scenario": "restaurant",
                "menu_keywords": ["salt bread"],
                "place_type_keywords": ["bakery"],
            },
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["candidates"][0]["name"], "Salt Bread Cafe")
        self.assertEqual(
            result["candidates"][0]["evidence_sources"][0]["url"],
            "https://example.com/salt-bread",
        )

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_prompt_includes_menu_condition(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "output_text": json.dumps({
                "candidates": [
                    {
                        "name": "Salt Bread Cafe",
                        "source_url": "https://example.com/salt-bread",
                    }
                ]
            })
        }
        mock_post.return_value = mock_response

        get_ai_web_search_result(
            query="salt bread cafe",
            lat=35.1556,
            lng=129.0641,
            condition={
                "scenario": "restaurant",
                "menu_keywords": ["salt bread"],
                "place_type_keywords": ["bakery"],
            },
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        payload = mock_post.call_args.kwargs["json"]
        prompt_input = payload["input"]
        self.assertIn('query: "salt bread cafe"', prompt_input)
        self.assertIn("menu_keywords: salt bread", prompt_input)
        self.assertIn("place_type_keywords: bakery", prompt_input)
        self.assertIn(
            '{"candidates":[{"name":"place name","source_url":"<source_url>"}]}',
            prompt_input,
        )
        self.assertNotIn("reasoning", payload)
        self.assertNotIn("existing_results_summary", prompt_input)
        self.assertNotIn("category_hint", prompt_input)
        self.assertNotIn("address_hint", prompt_input)
        self.assertNotIn("evidence_summary", prompt_input)
        self.assertNotIn("https://...", prompt_input)

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.logger.exception")
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_handles_api_error_safely(self, mock_post, mock_log_exception):
        mock_post.side_effect = requests.Timeout("timeout")

        result = get_ai_web_search_result(
            query="브런치 먹기 좋은 카페 추천",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "api_error")
        self.assertEqual(result["error_detail"]["type"], "timeout")
        self.assertIn("message", result["error_detail"])
        mock_log_exception.assert_called_once()

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.logger.exception")
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_returns_sanitized_error_detail_for_http_error(self, mock_post, mock_log_exception):
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {
                "type": "invalid_request_error",
                "message": "Bad request with Authorization: Bearer fake-key and too much input",
            }
        }
        mock_response.text = "fallback text with fake-key"
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "400 Client Error",
            response=mock_response,
        )
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="쌀국수 먹고 싶어",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "restaurant", "keywords": ["쌀국수", "식당"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["error"], "api_error")
        self.assertEqual(result["error_detail"]["status_code"], 400)
        self.assertEqual(result["error_detail"]["type"], "bad_request")
        self.assertNotIn("fake-key", result["error_detail"]["message"])
        self.assertLessEqual(len(result["error_detail"]["message"]), 300)
        self.assertEqual(mock_post.call_count, 1)
        mock_log_exception.assert_called_once()

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.logger.exception")
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_returns_invalid_request_for_reasoning_tool_conflict(
        self,
        mock_post,
        mock_log_exception,
    ):
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {
                "type": "invalid_request_error",
                "message": (
                    "The following tools cannot be used with reasoning.effort "
                    "'minimal': web_search."
                ),
            }
        }
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "400 Client Error",
            response=mock_response,
        )
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="salt bread cafe",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "restaurant", "menu_keywords": ["salt bread"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "api_error")
        self.assertEqual(result["reason"], "invalid_request")
        self.assertEqual(result["error_detail"]["status_code"], 400)
        self.assertEqual(result["error_detail"]["type"], "bad_request")
        self.assertEqual(
            result["error_detail"]["message"],
            "web_search cannot be used with reasoning.effort minimal.",
        )
        mock_log_exception.assert_called_once()

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
        DEBUG=True,
    )
    @patch("recommendations.services.ai_web_search_provider.logger.info")
    @patch("recommendations.services.ai_web_search_provider.logger.exception")
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_retries_and_returns_temporary_server_error(
        self,
        mock_post,
        mock_log_exception,
        mock_log_info,
    ):
        responses = []
        for _index in range(2):
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.json.return_value = {
                "error": {
                    "type": "server_error",
                    "message": "raw server error with request id abc-123",
                }
            }
            mock_response.text = "raw server error with request id abc-123"
            mock_response.raise_for_status.side_effect = requests.HTTPError(
                "500 Server Error",
                response=mock_response,
            )
            responses.append(mock_response)
        mock_post.side_effect = responses

        result = get_ai_web_search_result(
            query="salt bread cafe",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "restaurant", "menu_keywords": ["salt bread"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
            manual=True,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "temporary_server_error")
        self.assertEqual(result["reason"], "server_error")
        self.assertEqual(result["error_detail"]["status_code"], 500)
        self.assertEqual(result["error_detail"]["type"], "server_error")
        self.assertEqual(
            result["error_detail"]["message"],
            "AI web search server response failed temporarily.",
        )
        self.assertEqual(mock_post.call_count, 2)
        self.assertTrue(
            any(
                call.args and "[AI_WEB_SEARCH_RETRY]" in str(call.args[0])
                for call in mock_log_info.call_args_list
            )
        )
        mock_log_exception.assert_called_once()

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.logger.exception")
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_handles_invalid_json_safely(self, mock_post, mock_log_exception):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("invalid json")
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="브런치 먹기 좋은 카페 추천",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "invalid_json")
        mock_log_exception.assert_called_once()

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
    )
    @patch("recommendations.services.ai_web_search_provider.requests.post")
    def test_ai_web_search_rejects_candidates_without_source_url(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({
                                "candidates": [
                                    {
                                        "name": "출처 없는 후보",
                                        "evidence_sources": [
                                            {"title": "URL 없음", "url": ""}
                                        ],
                                    }
                                ]
                            }, ensure_ascii=False),
                        }
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        result = get_ai_web_search_result(
            query="브런치 먹기 좋은 카페 추천",
            lat=35.1556,
            lng=129.0641,
            condition={"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
            existing_results_summary={"db_count": 0, "kakao_fallback_count": 0},
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "empty_candidates")

    def test_category_distance_fallback_marks_insufficient_tags(self):
        response = self.client.get(
            "/api/recommendations/search/",
            {
                "scenario": "work_cafe",
                "lat": 35.1557,
                "lng": 129.0642,
                "limit": 10,
            },
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        fallback_result = next(
            result for result in response.json()["results"]
            if result["id"] == self.fallback_place.id
        )
        self.assertEqual(
            fallback_result["match_level"],
            "category_distance_fallback",
        )
        self.assertIn("세부 태그 정보가 부족", fallback_result["recommend_reason"])

    def test_work_cafe_condition_removes_broad_categories_and_non_work_tags(self):
        condition = build_recommendation_condition(
            scenario="work_cafe",
            condition={
                "scenario": "work_cafe",
                "categories": [
                    "cafe",
                    "restaurant",
                    "city_park",
                    "beach",
                    "shelter",
                    "smoking_area",
                    "tourism",
                ],
                "preferred_tags": [
                    "노트북작업",
                    "조용한",
                    "와이파이",
                    "콘센트있음",
                    "실내쉼터",
                    "편의시설",
                    "실외흡연구역",
                ],
            },
        )

        self.assertEqual(condition["categories"], ["cafe"])
        self.assertEqual(
            condition["preferred_tags"],
            ["노트북작업", "조용한", "와이파이", "콘센트있음"],
        )
        self.assertIn("shelter", condition["exclude_categories"])
        self.assertIn("restaurant", condition["exclude_categories"])

    def test_work_cafe_excludes_shelter_center_and_elderly_hall_candidates(self):
        blocked_places = [
            self._create_place("창날경로당", "shelter", "work-elderly-hall"),
            self._create_place("괘법동주민센터", "cafe", "work-community-center"),
            self._create_place("괘내마을행복센터", "cafe", "work-happy-center"),
            self._create_place("무더위쉼터", "shelter", "work-heat-shelter"),
        ]
        self._add_tag(blocked_places[3], "실내쉼터")
        tagged_cafe = self._create_place("노트북 작업 카페", "cafe", "work-tagged-cafe")
        self._add_tag(tagged_cafe, "노트북작업")

        result = search_db_recommendations(
            scenario="work_cafe",
            condition={
                "scenario": "work_cafe",
                "categories": ["cafe", "shelter", "city_park", "tourism"],
                "preferred_tags": ["노트북작업", "조용한", "와이파이", "콘센트있음", "실내쉼터"],
            },
            lat=35.1556,
            lng=129.0641,
            limit=20,
        )

        result_ids = {item["id"] for item in result["results"]}
        self.assertIn(tagged_cafe.id, result_ids)
        for place in blocked_places:
            self.assertNotIn(place.id, result_ids)

    def test_work_cafe_caps_cafe_without_core_work_evidence(self):
        result = search_db_recommendations(
            scenario="work_cafe",
            condition={
                "scenario": "work_cafe",
                "preferred_tags": ["노트북작업", "조용한", "와이파이", "콘센트있음"],
            },
            lat=35.1557,
            lng=129.0642,
            limit=10,
        )

        fallback_result = next(
            item for item in result["results"]
            if item["id"] == self.fallback_place.id
        )
        self.assertEqual(
            fallback_result["match_level"],
            "category_distance_fallback",
        )
        self.assertLessEqual(fallback_result["score"], 40)
        self.assertIn(
            "work_cafe_category_only_without_core",
            fallback_result["score_breakdown"]["score_cap_reasons"],
        )
        self.assertIn(
            "작업 장소로 보기에는",
            fallback_result["recommendation_reason"],
        )

    def test_work_cafe_keeps_cafe_with_notebook_tag(self):
        tagged_cafe = self._create_place("노트북 작업 카페", "cafe", "work-notebook-cafe")
        self._add_tag(tagged_cafe, "노트북작업")

        result = search_db_recommendations(
            scenario="work_cafe",
            condition={"scenario": "work_cafe"},
            lat=35.1556,
            lng=129.0641,
            limit=10,
        )

        result_by_id = {item["id"]: item for item in result["results"]}
        self.assertIn(tagged_cafe.id, result_by_id)
        self.assertEqual(result_by_id[tagged_cafe.id]["match_level"], "tag_matched")

    def test_waiting_place_excludes_limited_access_shelters_and_centers(self):
        blocked_places = [
            self._create_place("창날경로당", "shelter", "wait-elderly-hall"),
            self._create_place("괘법동주민센터", "shelter", "wait-community-center"),
            self._create_place("괘내마을행복센터", "shelter", "wait-happy-center"),
            self._create_place("복지시설쉼터", "shelter", "wait-welfare-shelter"),
            self._create_place("새마을금고 쉼터", "shelter", "wait-bank-shelter"),
        ]
        library = self._create_place("부산도서관", "shelter", "wait-public-library")

        result = search_db_recommendations(
            scenario="waiting_place",
            condition={
                "scenario": "waiting_place",
                "categories": ["cafe", "shelter", "city_park"],
                "preferred_tags": ["잠깐쉬기좋음", "실내쉼터", "조용한", "혼자이용좋음", "편의시설"],
            },
            lat=35.1556,
            lng=129.0641,
            limit=20,
        )

        result_ids = {item["id"] for item in result["results"]}
        self.assertIn(library.id, result_ids)
        for place in blocked_places:
            self.assertNotIn(place.id, result_ids)

    def test_waiting_place_condition_removes_unmentioned_work_smoking_food_tags(self):
        condition = build_recommendation_condition(
            scenario="waiting_place",
            condition={
                "scenario": "waiting_place",
                "keyword": "잠깐 쉴 곳",
                "categories": ["cafe", "shelter", "restaurant", "tourism", "smoking_area"],
                "preferred_tags": [
                    "잠깐쉬기좋음",
                    "실내쉼터",
                    "조용한",
                    "혼자이용좋음",
                    "편의시설",
                    "노트북작업",
                    "와이파이",
                    "콘센트있음",
                    "실외흡연구역",
                    "식사가능",
                    "야경",
                    "벚꽃",
                    "호수",
                    "힐링",
                    "사진찍기좋음",
                ],
            },
        )

        self.assertEqual(condition["categories"], ["cafe", "shelter"])
        self.assertEqual(
            condition["preferred_tags"],
            ["잠깐쉬기좋음", "실내쉼터", "조용한", "혼자이용좋음", "편의시설"],
        )

    def test_walk_healing_disables_category_fallback_when_required_tags_are_missing(self):
        tagged_place = self._create_place("에덴공원 산책로", "city_park", "walk-eden")
        category_only_place = self._create_place("태그 없는 근린공원", "city_park", "walk-no-tag")
        self._add_tag(tagged_place, "산책좋음")

        result = search_db_recommendations(
            scenario="walk_healing",
            condition={
                "scenario": "walk_healing",
                "required_tags": ["산책좋음"],
                "preferred_tags": ["조용한"],
                "fallback_enabled": False,
            },
            lat=35.1556,
            lng=129.0641,
            limit=10,
        )

        result_ids = {item["id"] for item in result["results"]}
        self.assertIn(tagged_place.id, result_ids)
        self.assertNotIn(category_only_place.id, result_ids)
        self.assertTrue(
            all(
                item["match_level"] != "category_distance_fallback"
                for item in result["results"]
            )
        )

    def test_walk_healing_excludes_commercial_market_and_parking_candidates(self):
        blocked_places = [
            self._create_place("뉴발란스 하단동점", "tourism", "walk-newbalance"),
            self._create_place("신평종합시장", "tourism", "walk-market"),
            self._create_place("홈플러스 장림점", "tourism", "walk-homeplus"),
            self._create_place("당리동 샛별공원 지하공영주차장", "city_park", "walk-parking"),
        ]
        kept_place = self._create_place("에덴공원 산책로", "city_park", "walk-kept")
        self._add_tag(kept_place, "산책좋음")

        result = search_db_recommendations(
            scenario="walk_healing",
            condition={
                "scenario": "walk_healing",
                "required_tags": ["산책좋음"],
                "fallback_enabled": True,
            },
            lat=35.1556,
            lng=129.0641,
            limit=10,
        )

        result_ids = {item["id"] for item in result["results"]}
        self.assertIn(kept_place.id, result_ids)
        for place in blocked_places:
            self.assertNotIn(place.id, result_ids)

    def test_walk_healing_keeps_tagged_park_and_galmaetgil_candidates(self):
        eden = self._create_place("에덴공원", "city_park", "walk-tagged-eden")
        galmaetgil = self._create_place("부산 갈맷길 산책 코스", "tourism", "walk-galmaetgil")
        self._add_tag(eden, "산책좋음")

        result = search_db_recommendations(
            scenario="walk_healing",
            condition={
                "scenario": "walk_healing",
                "required_tags": ["산책좋음"],
                "preferred_tags": ["조용한"],
                "fallback_enabled": True,
            },
            lat=35.1556,
            lng=129.0641,
            limit=10,
        )

        result_by_id = {item["id"]: item for item in result["results"]}
        self.assertIn(eden.id, result_by_id)
        self.assertEqual(result_by_id[eden.id]["match_level"], "tag_matched")
        self.assertGreaterEqual(result_by_id[eden.id]["score"], 75)
        self.assertIn(galmaetgil.id, result_by_id)
        self.assertLessEqual(result_by_id[galmaetgil.id]["score"], 40)

    def test_walk_healing_demotes_small_parks_without_walk_tags(self):
        small_park = self._create_place("하단 어린이공원", "city_park", "walk-small-park")

        result = search_db_recommendations(
            scenario="walk_healing",
            condition={
                "scenario": "walk_healing",
                "required_tags": [],
                "preferred_tags": ["조용한"],
                "fallback_enabled": True,
            },
            lat=35.1556,
            lng=129.0641,
            limit=10,
        )

        small_park_result = next(
            item for item in result["results"]
            if item["id"] == small_park.id
        )
        self.assertEqual(
            small_park_result["match_level"],
            "category_distance_fallback",
        )
        self.assertLessEqual(small_park_result["score"], 35)
        self.assertIn(
            "walk_healing_small_park_without_walk_tag",
            small_park_result["score_breakdown"]["score_cap_reasons"],
        )

    def test_walk_healing_allows_tourism_only_with_walk_evidence(self):
        river = self._create_place("낙동강하구 생태 전망대", "tourism", "walk-river")
        generic = self._create_place("부산관광안내 전시관", "tourism", "walk-generic-tour")

        result = search_db_recommendations(
            scenario="walk_healing",
            condition={
                "scenario": "walk_healing",
                "required_tags": [],
                "preferred_tags": ["조용한"],
                "fallback_enabled": True,
            },
            lat=35.1556,
            lng=129.0641,
            limit=10,
        )

        result_by_id = {item["id"]: item for item in result["results"]}
        self.assertIn(river.id, result_by_id)
        self.assertNotIn(generic.id, result_by_id)
        self.assertLessEqual(result_by_id[river.id]["score"], 40)

    def test_walk_healing_category_fallback_reason_marks_missing_direct_basis(self):
        fallback_place = self._create_place("갈맷길 전망대", "tourism", "walk-reason")

        result = search_db_recommendations(
            scenario="walk_healing",
            condition={
                "scenario": "walk_healing",
                "required_tags": ["산책좋음"],
                "fallback_enabled": True,
            },
            lat=35.1556,
            lng=129.0641,
            limit=10,
        )

        fallback_result = next(
            item for item in result["results"]
            if item["id"] == fallback_place.id
        )
        self.assertEqual(
            fallback_result["match_level"],
            "category_distance_fallback",
        )
        self.assertIn(
            "산책 조건과 직접 일치하는 근거가 부족합니다",
            fallback_result["recommendation_reason"],
        )
        self.assertIn(
            "기본 산책 추천이 아니라 카테고리 기반 fallback 후보",
            fallback_result["recommendation_reason"],
        )

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_conversational_search_planner_keeps_station_for_walk_queries(self):
        for query in ["하단역 산책할 곳 추천해줘", "하단역 근처 산책할 곳 추천해줘"]:
            with self.subTest(query=query):
                plan = build_conversational_search_plan(query)

                self.assertEqual(plan["action"], "search")
                self.assertFalse(plan["needs_clarification"])
                self.assertEqual(plan["search_plan"]["locationQuery"], "하단역")
                self.assertEqual(plan["search_plan"]["scenario"], "walk_healing")
                self.assertTrue(plan["execution_policy"]["preserve_explicit_location"])

    @patch("recommendations.services.ai_situation_parser._call_ai_parser")
    def test_ai_parser_removes_unrequested_cafe_restaurant_wifi_for_walk_healing(self, mock_call_ai_parser):
        mock_call_ai_parser.return_value = (
            "gms",
            json.dumps({
                "is_searchable": True,
                "scenario": "walk_healing",
                "categories": ["city_park", "beach", "cafe", "restaurant"],
                "required_tags": ["산책좋음"],
                "preferred_tags": ["산책좋음", "전망좋음", "조용한", "와이파이", "힐링"],
                "keywords": ["산책", "공원"],
                "fallback_enabled": False,
                "situation_summary": "하단역 산책할 곳 추천해줘",
                "reason_hint": "산책 의도",
            }, ensure_ascii=False),
        )

        parsed = parse_situation("하단역 산책할 곳 추천해줘")

        self.assertEqual(parsed["scenario"], "walk_healing")
        self.assertNotIn("cafe", parsed["categories"])
        self.assertNotIn("restaurant", parsed["categories"])
        self.assertNotIn("와이파이", parsed["preferred_tags"])
        self.assertNotIn("힐링", parsed["preferred_tags"])
        self.assertIn("산책좋음", parsed["required_tags"])

    @patch("recommendations.services.ai_situation_parser._call_ai_parser")
    def test_ai_parser_keeps_walk_healing_radius_at_least_3000(self, mock_call_ai_parser):
        mock_call_ai_parser.return_value = (
            "gms",
            json.dumps({
                "is_searchable": True,
                "scenario": "walk_healing",
                "categories": ["city_park", "beach", "tourism"],
                "required_tags": ["산책좋음"],
                "preferred_tags": ["산책좋음"],
                "keywords": ["산책", "공원"],
                "radius": 300,
                "fallback_enabled": False,
                "situation_summary": "하단역 산책할 곳 추천해줘",
                "reason_hint": "산책 의도",
            }, ensure_ascii=False),
        )

        parsed = parse_situation("하단역 산책할 곳 추천해줘")

        self.assertEqual(parsed["scenario"], "walk_healing")
        self.assertGreaterEqual(parsed["radius"], 3000)

    def test_db_walk_healing_radius_request_is_at_least_3000(self):
        result = search_db_recommendations(
            scenario="walk_healing",
            condition={
                "scenario": "walk_healing",
                "required_tags": ["산책좋음"],
                "radius": 300,
            },
            lat=35.106,
            lng=128.966,
            radius=300,
            limit=10,
        )

        self.assertEqual(result["condition"]["radius"], 3000)
        self.assertEqual(result["conditions"]["radius"], 3000)

    @patch("recommendations.services.ai_situation_parser._call_ai_parser")
    def test_ai_parser_keeps_explicit_cafe_and_wifi_for_walk_healing(self, mock_call_ai_parser):
        mock_call_ai_parser.return_value = (
            "gms",
            json.dumps({
                "is_searchable": True,
                "scenario": "walk_healing",
                "categories": ["city_park", "cafe", "restaurant"],
                "required_tags": ["산책좋음"],
                "preferred_tags": ["산책좋음", "와이파이"],
                "keywords": ["산책", "카페", "와이파이"],
                "fallback_enabled": True,
                "situation_summary": "와이파이 되는 산책 카페",
                "reason_hint": "산책 가능한 카페 의도",
            }, ensure_ascii=False),
        )

        parsed = parse_situation("와이파이 되는 산책 카페")

        self.assertEqual(parsed["scenario"], "walk_healing")
        self.assertIn("cafe", parsed["categories"])
        self.assertNotIn("restaurant", parsed["categories"])
        self.assertIn("와이파이", parsed["preferred_tags"])
        self.assertIn("산책좋음", parsed["required_tags"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_conversational_search_planner_extracts_menu_targets(self):
        brunch_plan = build_conversational_search_plan("서면역 브런치 카페")
        self.assertEqual(brunch_plan["search_plan"]["locationQuery"], "서면역")
        self.assertEqual(brunch_plan["search_plan"]["targetQuery"], "브런치 카페")
        self.assertIn("브런치", brunch_plan["search_plan"]["menu_keywords"])

        salt_bread_plan = build_conversational_search_plan("사상역 소금빵 맛집 찾아줘")
        self.assertEqual(salt_bread_plan["search_plan"]["locationQuery"], "사상역")
        self.assertEqual(salt_bread_plan["search_plan"]["targetQuery"], "소금빵 맛집")
        self.assertIn("소금빵", salt_bread_plan["search_plan"]["menu_keywords"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_searches_work_cafe_query(self):
        plan = build_conversational_search_plan("서면역 근처 조용히 작업할 카페 찾아줘")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["intent_type"], "place_recommendation")
        self.assertFalse(plan["needs_clarification"])
        self.assertEqual(plan["search_plan"]["scenario"], "work_cafe")
        self.assertEqual(plan["search_plan"]["locationQuery"], "서면역")
        self.assertEqual(plan["search_plan"]["targetQuery"], "카페")
        self.assertIn("조용함", plan["conditions"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_normalizes_location_suffix_for_work_cafe_query(self):
        plan = build_conversational_search_plan("하단 쪽에서 노트북 펴도 눈치 안 보이는 곳")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "work_cafe")
        self.assertEqual(plan["search_plan"]["locationQuery"], "하단")
        self.assertEqual(plan["search_plan"]["targetQuery"], "카페")
        self.assertNotIn("카페", plan["conditions"])
        self.assertIn("노트북 작업 가능", plan["conditions"])
        self.assertIn("혼자 이용하기 좋음", plan["conditions"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_normalizes_location_suffix_for_walk_healing_query(self):
        plan = build_conversational_search_plan("광안리 쪽에서 바람 쐬면서 걷기 좋은 곳")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "walk_healing")
        self.assertEqual(plan["search_plan"]["locationQuery"], "광안리")
        self.assertEqual(plan["search_plan"]["targetQuery"], "산책할 곳")
        self.assertNotEqual(plan["search_plan"]["targetQuery"], "공원")
        self.assertIn("산책하기 좋음", plan["conditions"])
        self.assertIn("걷기 좋음", plan["conditions"])
        self.assertIn("바람 쐬기 좋음", plan["conditions"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_treats_outside_negative_as_waiting_place_not_refinement(self):
        plan = build_conversational_search_plan("비 와서 밖 말고 앉아있을 데")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertNotEqual(plan["action"], "refine_previous_search")
        self.assertEqual(plan["search_plan"]["scenario"], "waiting_place")
        self.assertEqual(plan["search_plan"]["locationQuery"], "")
        self.assertFalse(plan["search_plan"]["location_resolution_required"])
        self.assertNotEqual(plan["search_plan"]["scenario"], "work_cafe")
        self.assertIn("비를 피하면서", plan["clarification_question"])
        self.assertNotIn("이전 검색 결과가 없어서", f"{plan['message']} {plan['clarification_question']}")
        self.assertIn("실내", plan["conditions"])
        self.assertIn("비 피하기 좋음", plan["conditions"])
        self.assertIn("앉을 수 있음", plan["conditions"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_treats_crowd_negative_as_waiting_place_not_refinement(self):
        plan = build_conversational_search_plan("사람 너무 많은 데 말고 혼자 좀 쉬고 싶다")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertNotEqual(plan["action"], "refine_previous_search")
        self.assertEqual(plan["search_plan"]["scenario"], "waiting_place")
        self.assertEqual(plan["search_plan"]["locationQuery"], "")
        self.assertFalse(plan["search_plan"]["location_resolution_required"])
        self.assertNotEqual(plan["search_plan"]["targetQuery"], "카페")
        self.assertIn("혼자 조용히 쉴 곳", plan["clarification_question"])
        self.assertIn("혼자 이용하기 좋음", plan["conditions"])
        self.assertIn("붐비지 않음", plan["conditions"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_uses_current_context_without_location_resolution_for_crowd_negative(self):
        plan = build_conversational_search_plan(
            "사람 너무 많은 데 말고 혼자 좀 쉬고 싶다",
            lat=35.1,
            lng=129.0,
        )

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "waiting_place")
        self.assertEqual(plan["search_plan"]["locationQuery"], "")
        self.assertFalse(plan["search_plan"]["has_explicit_location"])
        self.assertFalse(plan["search_plan"]["location_resolution_required"])
        self.assertEqual(plan["search_plan"]["targetQuery"], "쉴 곳")
        self.assertIn("혼자 이용하기 좋음", plan["conditions"])
        self.assertIn("붐비지 않음", plan["conditions"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_treats_cafe_negative_as_waiting_place(self):
        plan = build_conversational_search_plan("서면에서 조용히 있고 싶은데 너무 카페 느낌은 아니었으면 좋겠어")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "waiting_place")
        self.assertEqual(plan["search_plan"]["locationQuery"], "서면")
        self.assertEqual(plan["search_plan"]["targetQuery"], "쉴 곳")
        self.assertNotEqual(plan["search_plan"]["targetQuery"], "카페")
        self.assertTrue(plan["search_plan"]["location_resolution_required"])
        self.assertIn("조용함", plan["conditions"])
        self.assertTrue(
            "카페 느낌 아님" in plan["conditions"]
            or "카페 제외" in plan["conditions"]
        )
        self.assertIn("카페", plan["search_plan"].get("excluded_categories", []))

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_group_quiet_rest_place_keeps_broad_candidates(self):
        plan = build_conversational_search_plan("서면에서 조용히 쉴 곳")
        search_plan = plan["search_plan"]
        candidate_names = {
            candidate["name"]
            for candidate in search_plan.get("category_candidates", [])
        }

        self.assertEqual(plan["action"], "search")
        self.assertEqual(search_plan["scenario"], "waiting_place")
        self.assertEqual(search_plan["intent_group"], "quiet_rest_place")
        self.assertEqual(search_plan["locationQuery"], "서면")
        self.assertNotEqual(search_plan["targetQuery"], "카페")
        self.assertIn("도서관", candidate_names)
        self.assertIn("쉼터", candidate_names)
        self.assertIn("공원", candidate_names)
        self.assertIn("카페", candidate_names)

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_group_quiet_rest_place_preserves_cafe_exclusion(self):
        plan = build_conversational_search_plan("카페 말고 조용히 쉴 곳")
        search_plan = plan["search_plan"]
        candidate_names = [
            candidate["name"]
            for candidate in search_plan.get("category_candidates", [])
        ]

        self.assertEqual(search_plan["intent_group"], "quiet_rest_place")
        self.assertIn("카페", search_plan.get("excluded_categories", []))
        self.assertNotIn("카페", candidate_names)
        self.assertTrue(
            all("카페" not in query for query in search_plan.get("web_search_queries", []))
        )

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_group_work_place_adds_work_candidates(self):
        plan = build_conversational_search_plan("하단에서 노트북 펴도 눈치 안 보이는 곳")
        search_plan = plan["search_plan"]
        candidate_names = {
            candidate["name"]
            for candidate in search_plan.get("category_candidates", [])
        }

        self.assertEqual(plan["action"], "search")
        self.assertEqual(search_plan["scenario"], "work_cafe")
        self.assertEqual(search_plan["intent_group"], "work_place")
        self.assertEqual(search_plan["locationQuery"], "하단")
        self.assertIn("카페", candidate_names)
        self.assertIn("도서관", candidate_names)
        self.assertIn("스터디카페", candidate_names)
        self.assertTrue(
            "노트북 작업 가능" in plan["conditions"]
            or "혼자 이용하기 좋음" in plan["conditions"]
        )

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_group_urgent_toilet_is_place_search(self):
        for query in ["화장실 급해", "똥 마려워"]:
            with self.subTest(query=query):
                plan = build_conversational_search_plan(query)
                search_plan = plan["search_plan"]

                self.assertNotIn(plan["action"], {"blocked", "out_of_scope"})
                self.assertEqual(search_plan["intent_group"], "urgent_toilet")
                self.assertTrue(
                    "화장실" in search_plan["targetQuery"]
                    or "공중화장실" in search_plan["targetQuery"]
                )

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_group_health_nearby_is_place_guidance_only(self):
        plan = build_conversational_search_plan("머리 아프다")
        search_plan = plan["search_plan"]
        candidate_names = {
            candidate["name"]
            for candidate in search_plan.get("category_candidates", [])
        }

        self.assertNotIn(plan["action"], {"blocked", "out_of_scope"})
        self.assertEqual(search_plan["intent_group"], "health_nearby")
        self.assertTrue({"약국", "병원"} & candidate_names)
        self.assertIn("가까운 약국이나 병원", plan["message"])
        self.assertNotIn("복용", plan["message"])
        self.assertNotIn("진단", plan["message"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_group_weather_shelter_adds_indoor_conditions(self):
        plan = build_conversational_search_plan("비 피할 곳")
        search_plan = plan["search_plan"]

        self.assertEqual(search_plan["intent_group"], "weather_shelter")
        self.assertTrue(
            "비 피하기 좋음" in plan["conditions"]
            or "실내" in plan["conditions"]
        )

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_group_web_search_queries_are_contextual(self):
        quiet_plan = build_conversational_search_plan("서면에서 조용히 쉴 곳")
        quiet_search_plan = quiet_plan["search_plan"]
        walk_plan = build_conversational_search_plan("광안리 쪽에서 바람 쐬면서 걷기 좋은 곳")
        walk_search_plan = walk_plan["search_plan"]

        self.assertTrue(quiet_search_plan["web_search_recommended"])
        self.assertIn("서면 조용한 공간", quiet_search_plan["web_search_queries"])
        self.assertIn("서면 도서관", quiet_search_plan["web_search_queries"])
        self.assertIn("광안리 산책로", walk_search_plan["web_search_queries"])
        self.assertIn("광안리 해변 산책", walk_search_plan["web_search_queries"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_place_intent_frame_quiet_rest_keeps_semantic_candidates(self):
        plan = build_conversational_search_plan("서면에서 조용히 쉴 곳")
        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]

        self.assertEqual(plan["action"], "search")
        self.assertEqual(frame["situation"], "quiet_rest")
        self.assertEqual(frame["anchor_location"], "서면")
        self.assertNotEqual(search_plan["targetQuery"], "카페")
        self.assertIn("도서관", frame["candidate_place_types"])
        self.assertIn("공원", frame["candidate_place_types"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_place_intent_frame_preserves_complex_anchor_location(self):
        plan = build_conversational_search_plan("서면역 롯데백화점 근처 쉴 곳")
        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]

        self.assertEqual(plan["action"], "search")
        self.assertEqual(search_plan["locationQuery"], "서면역 롯데백화점")
        self.assertEqual(frame["anchor_location"], "서면역 롯데백화점")
        self.assertEqual(frame["situation"], "rest")
        self.assertNotIn("쉼터", frame["candidate_place_types"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_place_intent_frame_handles_colloquial_toilet_query(self):
        plan = build_conversational_search_plan("똥 마려운데 우야노")
        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]

        self.assertNotIn(plan["action"], {"blocked", "out_of_scope"})
        self.assertEqual(search_plan["intent_group"], "urgent_toilet")
        self.assertEqual(frame["situation"], "toilet")
        self.assertNotEqual(frame["situation"], "waiting_place")

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_place_intent_frame_handles_colloquial_work_query(self):
        plan = build_conversational_search_plan("놋북 펼 데 없나")
        frame = plan["search_plan"]["place_intent_frame"]

        self.assertEqual(frame["situation"], "work")
        self.assertIn("카페", frame["candidate_place_types"])
        self.assertIn("도서관", frame["candidate_place_types"])
        self.assertIn("스터디카페", frame["candidate_place_types"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_place_intent_frame_handles_colloquial_quiet_rest_query(self):
        plan = build_conversational_search_plan("사람 없는 데서 좀 멍때리고 싶다")
        frame = plan["search_plan"]["place_intent_frame"]

        self.assertEqual(frame["situation"], "quiet_rest")
        self.assertTrue(
            "조용함" in frame["constraints"]
            or "혼자 이용하기 좋음" in frame["constraints"]
        )

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_place_intent_frame_health_query_keeps_trailing_location(self):
        plan = build_conversational_search_plan("머리 아프다 하단역")
        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]

        self.assertEqual(search_plan["intent_group"], "health_nearby")
        self.assertEqual(search_plan["locationQuery"], "하단역")
        self.assertEqual(frame["anchor_location"], "하단역")
        self.assertEqual(frame["situation"], "health_nearby")
        self.assertIn("약국", frame["candidate_place_types"])
        self.assertIn("병원", frame["candidate_place_types"])
        self.assertNotEqual(frame["situation"], "waiting_place")

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_place_intent_frame_cafe_exclusion_removes_cafe_queries(self):
        plan = build_conversational_search_plan("서면에서 카페 말고 조용히 쉴 곳")
        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]

        self.assertIn("카페 제외", frame["exclusions"])
        self.assertNotIn("카페", frame["candidate_place_types"])
        self.assertTrue(all("카페" not in query for query in search_plan["web_search_queries"]))
        self.assertTrue(all("카페" not in keyword for keyword in search_plan["kakaoKeywordCandidates"]))

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_search_regression_cases(self):
        cases = [
            {
                "query": "카공하기 좋은 곳",
                "scenario": "work_cafe",
                "location": "",
                "target_contains": "카페",
            },
            {
                "query": "광안리 근처 잠깐 쉴 곳",
                "scenario": "waiting_place",
                "location": "광안리",
                "target_contains": "쉴 곳",
            },
            {
                "query": "부산대 혼자 밥 먹을 곳",
                "scenario": "restaurant",
                "location": "부산대",
                "target_contains": "밥",
            },
            {
                "query": "사상역 소금빵 맛집 찾아줘",
                "scenario": "restaurant",
                "location": "사상역",
                "target_contains": "소금빵",
            },
        ]

        for case in cases:
            with self.subTest(query=case["query"]):
                plan = build_conversational_search_plan(case["query"])

                self.assertEqual(plan["action"], "search")
                self.assertEqual(plan["search_plan"]["scenario"], case["scenario"])
                self.assertEqual(plan["search_plan"]["locationQuery"], case["location"])
                self.assertIn(case["target_contains"], plan["search_plan"]["targetQuery"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_searches_menu_matjip_query(self):
        plan = build_conversational_search_plan("사상역 소금빵 맛집 찾아줘")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["locationQuery"], "사상역")
        self.assertEqual(plan["search_plan"]["scenario"], "restaurant")
        self.assertIn("소금빵", plan["search_plan"]["menu_keywords"])
        self.assertIn("소금빵 맛집", plan["search_plan"]["targetQuery"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_searches_walk_healing_query(self):
        plan = build_conversational_search_plan("하단역 산책할 곳 추천해줘")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "walk_healing")
        self.assertEqual(plan["search_plan"]["locationQuery"], "하단역")

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_asks_for_vague_place_recommendation(self):
        plan = build_conversational_search_plan("좋은 곳 추천해줘")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertTrue(plan["needs_clarification"])
        self.assertIn("어떤 상황", plan["clarification_question"])
        self.assertIn("지역과 목적", plan["clarification_question"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_asks_for_ambiguous_place_queries(self):
        cases = [
            "괜찮은 데 알려줘",
            "어디 갈까?",
        ]

        for query in cases:
            with self.subTest(query=query):
                plan = build_conversational_search_plan(query)

                self.assertEqual(plan["action"], "ask_clarification")
                self.assertTrue(plan["needs_clarification"])
                self.assertIn("지역과 목적", plan["clarification_question"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_handles_short_food_question_without_weird_category(self):
        plan = build_conversational_search_plan("뭐 먹지?")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "restaurant")
        self.assertNotIn(plan["action"], ["out_of_scope", "blocked"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_asks_for_refinement_without_previous_context(self):
        plan = build_conversational_search_plan("거기 말고 더 조용한 데")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertTrue(plan["needs_clarification"])
        self.assertIn("이전 검색 결과가 없어서", plan["clarification_question"])
        self.assertIn("지역과 원하는 장소 종류", plan["message"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_prioritizes_smoking_area_for_smoking_zone_query(self):
        plan = build_conversational_search_plan("흡연구역 찾아줘")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "smoking_area")
        self.assertEqual(plan["search_plan"]["targetQuery"], "흡연구역")
        self.assertEqual(plan["search_plan"]["requestedConditions"], [])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_prioritizes_smoking_area_for_cigarette_place_query(self):
        plan = build_conversational_search_plan("담배 필 곳 찾아줘")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "smoking_area")
        self.assertEqual(plan["search_plan"]["targetQuery"], "흡연구역")

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_smoking_area_regression_cases(self):
        cases = [
            "흡연구역 찾아줘",
            "담배 필 곳 찾아줘",
        ]

        for query in cases:
            with self.subTest(query=query):
                plan = build_conversational_search_plan(query)

                self.assertEqual(plan["action"], "search")
                self.assertEqual(plan["search_plan"]["scenario"], "smoking_area")
                self.assertEqual(plan["search_plan"]["targetQuery"], "흡연구역")
                self.assertNotEqual(plan["search_plan"]["locationQuery"], "흡연구역")

        near_plan = build_conversational_search_plan("근처 흡연장 어디 있어?")
        self.assertIn(near_plan["action"], ["search", "ask_clarification"])
        self.assertNotIn(near_plan["action"], ["out_of_scope", "blocked"])
        if near_plan["action"] == "search":
            self.assertEqual(near_plan["search_plan"]["scenario"], "smoking_area")

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_out_of_scope_queries_do_not_search(self):
        for query in [
            "비트코인 지금 살까?",
            "파이썬 숙제 풀어줘",
            "오늘 정치 뉴스 알려줘",
            "감기약 뭐 먹어야 돼?",
            "계약서 법적으로 문제 있는지 봐줘",
        ]:
            with self.subTest(query=query):
                plan = build_conversational_search_plan(query)

                self.assertEqual(plan["action"], "out_of_scope")
                self.assertEqual(plan["out_of_scope_reason"], "not_place_recommendation")
                self.assertFalse(plan["execution_policy"]["run_search"])
                self.assertEqual(plan["search_plan"], {})

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_blocks_unsafe_query(self):
        for query in [
            "불법적인 장소 알려줘",
            "위험한 행동을 할 수 있는 장소 알려줘",
        ]:
            with self.subTest(query=query):
                plan = build_conversational_search_plan(query)

                self.assertEqual(plan["action"], "blocked")
                self.assertEqual(plan["blocked_reason"], "unsafe_request")
                self.assertFalse(plan["execution_policy"]["run_search"])
                self.assertEqual(plan["search_plan"], {})

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_does_not_block_smoking_area_queries(self):
        for query in ["흡연구역 찾아줘", "담배 필 곳 찾아줘", "근처 흡연장 어디 있어?"]:
            with self.subTest(query=query):
                plan = build_conversational_search_plan(query)

                self.assertNotEqual(plan["action"], "blocked")
                self.assertNotEqual(plan["action"], "out_of_scope")

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_refines_previous_search_with_context(self):
        previous_context = {
            "search_plan": {
                "locationQuery": "서면역",
                "targetQuery": "카페",
                "scenario": "work_cafe",
                "categories": ["cafe"],
                "preferred_tags": ["와이파이"],
            },
            "result_count": 3,
        }

        plan = build_conversational_search_plan(
            "거기 말고 더 조용한 데",
            previous_context=previous_context,
        )

        self.assertEqual(plan["action"], "refine_previous_search")
        self.assertEqual(plan["search_plan"]["locationQuery"], "서면역")
        self.assertIn("조용함", plan["search_plan"]["additional_conditions"])
        self.assertFalse(plan["execution_policy"]["run_search"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_intent_router_response_shape_is_stable_for_all_actions(self):
        previous_context = {
            "search_plan": {
                "locationQuery": "서면역",
                "targetQuery": "카페",
                "scenario": "work_cafe",
                "categories": ["cafe"],
            },
            "result_count": 3,
        }
        cases = [
            build_conversational_search_plan("서면역 조용한 카페"),
            build_conversational_search_plan("좋은 곳 추천해줘"),
            build_conversational_search_plan("비트코인 지금 살까?"),
            build_conversational_search_plan("불법적인 장소 알려줘"),
            build_conversational_search_plan(
                "거기 말고 더 조용한 데",
                previous_context=previous_context,
            ),
        ]
        required_keys = {
            "action",
            "intent_type",
            "user_intent_summary",
            "message",
            "needs_clarification",
            "clarification_question",
            "search_plan",
            "blocked_reason",
            "out_of_scope_reason",
            "confidence",
        }
        allowed_actions = {
            "search",
            "ask_clarification",
            "out_of_scope",
            "blocked",
            "refine_previous_search",
        }

        self.assertEqual(
            [plan["action"] for plan in cases],
            ["search", "ask_clarification", "out_of_scope", "blocked", "refine_previous_search"],
        )
        for plan in cases:
            with self.subTest(action=plan["action"]):
                self.assertTrue(required_keys.issubset(plan.keys()))
                self.assertIn(plan["action"], allowed_actions)

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_fallback_interprets_work_cafe_query(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "scenario": "work_cafe",
            "locationQuery": "하단",
            "targetQuery": "카페",
            "conditions": ["노트북 작업 가능", "혼자 이용하기 좋음"],
            "confidence": 0.88,
        }

        plan = build_conversational_search_plan("하단 쪽에서 노트북 펴도 눈치 안 보이는 곳")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "work_cafe")
        self.assertEqual(plan["search_plan"]["locationQuery"], "하단")
        self.assertEqual(plan["search_plan"]["targetQuery"], "카페")
        self.assertIn("노트북 작업 가능", plan["conditions"])
        mock_ai.assert_called_once()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_fallback_interprets_walk_healing_query(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "walk_healing",
                "locationQuery": "광안리",
                "targetQuery": "걷기 좋은 곳",
                "conditions": ["산책하기 좋음", "힐링하기 좋음"],
            },
            "confidence": 0.86,
        }

        plan = build_conversational_search_plan("광안리 쪽에서 바람 쐬면서 걷기 좋은 곳")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "walk_healing")
        self.assertEqual(plan["search_plan"]["locationQuery"], "광안리")
        self.assertEqual(plan["search_plan"]["targetQuery"], "걷기 좋은 곳")
        self.assertIn("산책하기 좋음", plan["conditions"])
        mock_ai.assert_called_once()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_validator_normalizes_location_suffix_and_walk_target(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "walk_healing",
                "locationQuery": "광안리 쪽",
                "targetQuery": "공원",
                "conditions": ["걷기 좋음"],
            },
            "confidence": 0.84,
        }

        plan = build_conversational_search_plan("광안리 쪽에서 바람 쐬면서 걷기 좋은 곳")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "walk_healing")
        self.assertEqual(plan["search_plan"]["locationQuery"], "광안리")
        self.assertEqual(plan["search_plan"]["targetQuery"], "공원")
        self.assertEqual(plan["search_plan"]["execution_mode"], "frame")
        self.assertEqual(plan["search_plan"]["plan_source"], "ai")
        self.assertIn("걷기 좋음", plan["conditions"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_validator_does_not_turn_cafe_negative_into_cafe_search(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "waiting_place",
                "locationQuery": "서면",
                "targetQuery": "조용히 쉴 곳",
                "place_intent_frame": {
                    "user_goal": "카페가 아닌 조용히 쉴 곳 찾기",
                    "anchor_location": "서면",
                    "location_mode": "explicit",
                    "situation": "quiet_rest",
                    "display_label": "조용히 쉴 곳",
                    "candidate_category_codes": ["library", "shelter"],
                    "candidate_place_types": ["도서관", "쉼터"],
                    "search_queries": ["서면 도서관", "서면 쉼터"],
                    "result_match_terms": ["도서관", "쉼터"],
                    "constraints": ["조용함"],
                    "exclusions": ["카페 제외"],
                    "confidence": 0.82,
                },
            },
            "confidence": 0.82,
        }

        plan = build_conversational_search_plan("서면에서 조용히 있고 싶은데 너무 카페 느낌은 아니었으면 좋겠어")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "waiting_place")
        self.assertEqual(plan["search_plan"]["locationQuery"], "서면")
        self.assertEqual(plan["search_plan"]["targetQuery"], "조용히 쉴 곳")
        self.assertNotEqual(plan["search_plan"]["targetQuery"], "카페")
        self.assertNotIn("카페", plan["conditions"])
        self.assertIn("카페 제외", plan["conditions"])
        self.assertIn("카페 제외", plan["search_plan"]["place_intent_frame"].get("exclusions", []))

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_validator_corrects_disallowed_scenario(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "study_room",
                "locationQuery": "서면",
                "targetQuery": "스터디룸",
                "conditions": ["조용함"],
            },
            "confidence": 0.8,
        }

        plan = build_conversational_search_plan("서면 스터디룸 조용하게 쓰고 싶다")

        self.assertEqual(plan["action"], "search")
        self.assertNotEqual(plan["search_plan"]["scenario"], "study_room")
        self.assertEqual(plan["search_plan"]["scenario"], "work_cafe")
        self.assertEqual(plan["search_plan"]["targetQuery"], "스터디룸")
        self.assertEqual(plan["search_plan"]["execution_mode"], "frame")

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_validator_unknown_action_asks_clarification(self, mock_ai):
        mock_ai.return_value = {
            "action": "unknown",
            "search_plan": {},
        }

        plan = build_conversational_search_plan("서면에서 오래 머물 곳 느낌 봐줘")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertTrue(plan["needs_clarification"])

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_uses_ai_first_for_clear_search_cases(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "smoking_area",
                "targetQuery": "흡연구역",
                "place_intent_frame": {
                    "user_goal": "가까운 흡연구역 찾기",
                    "anchor_location": "",
                    "location_mode": "current_context",
                    "situation": "smoking",
                    "display_label": "흡연구역",
                    "candidate_category_codes": ["smoking_area"],
                    "candidate_place_types": ["흡연구역", "흡연실"],
                    "search_queries": ["흡연구역", "흡연실"],
                    "result_match_terms": ["흡연구역", "흡연실"],
                    "constraints": [],
                    "exclusions": [],
                    "confidence": 0.8,
                },
            },
        }

        plan = build_conversational_search_plan("흡연구역 찾아줘")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["parser_provider"], "gms")
        self.assertFalse(plan["parser_fallback"])
        self.assertEqual(plan["plan_source"], "ai")
        self.assertEqual(plan["execution_mode"], "frame")
        self.assertEqual(plan["search_plan"]["scenario"], "smoking_area")
        self.assertEqual(mock_ai.call_count, 2)

        mock_ai.reset_mock()
        blocked_plan = build_conversational_search_plan("불법적인 장소 알려줘")
        self.assertEqual(blocked_plan["action"], "blocked")
        mock_ai.assert_not_called()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_uses_ai_frame_for_hadan_toilet_query(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "waiting_place",
                "locationQuery": "하단역",
                "targetQuery": "공중화장실",
                "place_intent_frame": {
                    "user_goal": "하단역 근처 화장실 찾기",
                    "anchor_location": "하단역",
                    "location_mode": "explicit",
                    "situation": "toilet",
                    "display_label": "화장실",
                    "candidate_category_codes": ["toilet"],
                    "candidate_place_types": ["공중화장실", "개방화장실"],
                    "search_queries": ["하단역 공중화장실", "하단역 개방화장실"],
                    "result_match_terms": ["화장실", "공중화장실", "개방화장실"],
                    "constraints": ["가까운 곳"],
                    "exclusions": [],
                    "preferred_place_natures": ["ordinary_public_access"],
                    "excluded_place_natures": [],
                    "confidence": 0.91,
                },
            },
            "confidence": 0.91,
        }

        plan = build_conversational_search_plan("하단역인데 화장실 급해")
        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]

        self.assertEqual(plan["parser_provider"], "gms")
        self.assertFalse(plan["parser_fallback"])
        self.assertEqual(plan["plan_source"], "ai")
        self.assertEqual(plan["execution_mode"], "frame")
        self.assertEqual(search_plan["plan_source"], "ai")
        self.assertEqual(search_plan["execution_mode"], "frame")
        self.assertEqual(search_plan["locationQuery"], "하단역")
        self.assertEqual(frame["location_mode"], "explicit")
        self.assertEqual(frame["anchor_location"], "하단역")
        self.assertIn(search_plan["targetQuery"], ["공중화장실", "화장실"])
        self.assertEqual(frame["candidate_category_codes"], ["toilet"])
        mock_ai.assert_called_once()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_repairs_missing_location_with_ai(self, mock_ai):
        mock_ai.side_effect = [
            {
                "action": "search",
                "search_plan": {
                    "scenario": "waiting_place",
                    "locationQuery": "",
                    "targetQuery": "공중화장실",
                    "place_intent_frame": {
                        "user_goal": "현재 위치 기반으로 가까운 공중화장실을 찾는 요청",
                        "anchor_location": "",
                        "location_mode": "current_context",
                        "situation": "toilet",
                        "display_label": "화장실",
                        "candidate_category_codes": ["toilet"],
                        "candidate_place_types": ["공중화장실"],
                        "search_queries": ["공중화장실"],
                        "result_match_terms": ["화장실", "공중화장실"],
                        "constraints": ["가까운 곳"],
                        "exclusions": [],
                        "preferred_place_natures": ["ordinary_public_access"],
                        "excluded_place_natures": [],
                        "confidence": 0.86,
                    },
                },
                "confidence": 0.86,
            },
            {
                "explicit_anchor_location": "하단역",
            },
        ]

        plan = build_conversational_search_plan("하단역인데 화장실 급해")
        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]

        self.assertEqual(plan["parser_provider"], "gms")
        self.assertFalse(plan["parser_fallback"])
        self.assertEqual(plan["plan_source"], "ai")
        self.assertEqual(plan["execution_mode"], "frame")
        self.assertEqual(search_plan["plan_source"], "ai")
        self.assertEqual(search_plan["execution_mode"], "frame")
        self.assertEqual(search_plan["locationQuery"], "하단역")
        self.assertEqual(frame["location_mode"], "explicit")
        self.assertEqual(frame["anchor_location"], "하단역")
        self.assertEqual(frame["candidate_category_codes"], ["toilet"])
        self.assertIn("하단역 공중화장실", search_plan["kakaoKeywordCandidates"])
        self.assertTrue(any(
            keyword in search_plan["kakaoKeywordCandidates"]
            for keyword in ["하단역 공중화장실", "하단역 화장실"]
        ))
        self.assertNotEqual(search_plan["kakaoKeywordCandidates"], ["공중화장실"])
        self.assertEqual(plan["ai_debug"]["location_repair"]["checked_location_mode"], "current_context")
        self.assertEqual(plan["ai_debug"]["location_repair"]["checked_anchor_location"], "")
        self.assertEqual(plan["ai_debug"]["location_repair"]["frame_location_mode"], "current_context")
        self.assertEqual(plan["ai_debug"]["location_repair"]["frame_anchor_location"], "")
        self.assertEqual(plan["ai_debug"]["location_repair"]["status"], "repaired")
        self.assertEqual(plan["ai_debug"]["location_repair"]["explicit_anchor_location"], "하단역")
        self.assertEqual(mock_ai.call_count, 2)

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_search_plan_api_uses_ai_frame_for_hadan_toilet_query(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "waiting_place",
                "locationQuery": "하단역",
                "targetQuery": "공중화장실",
                "place_intent_frame": {
                    "user_goal": "하단역 근처 화장실 찾기",
                    "anchor_location": "하단역",
                    "location_mode": "explicit",
                    "situation": "toilet",
                    "display_label": "화장실",
                    "candidate_category_codes": ["toilet"],
                    "candidate_place_types": ["공중화장실", "개방화장실"],
                    "search_queries": ["하단역 공중화장실", "하단역 개방화장실"],
                    "result_match_terms": ["화장실", "공중화장실", "개방화장실"],
                    "constraints": ["가까운 곳"],
                    "exclusions": [],
                    "preferred_place_natures": ["ordinary_public_access"],
                    "excluded_place_natures": [],
                    "confidence": 0.91,
                },
            },
            "confidence": 0.91,
        }

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": "하단역인데 화장실 급해"}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        search_plan = data["search_plan"]
        frame = search_plan["place_intent_frame"]
        self.assertEqual(data["parser_provider"], "gms")
        self.assertFalse(data["parser_fallback"])
        self.assertEqual(data["plan_source"], "ai")
        self.assertEqual(data["execution_mode"], "frame")
        self.assertEqual(search_plan["locationQuery"], "하단역")
        self.assertIn(search_plan["targetQuery"], ["공중화장실", "화장실"])
        self.assertEqual(frame["location_mode"], "explicit")
        self.assertEqual(frame["anchor_location"], "하단역")
        self.assertEqual(frame["candidate_category_codes"], ["toilet"])
        mock_ai.assert_called_once()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_frame_anchor_promotes_to_search_plan_location_fields(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "waiting_place",
                "locationQuery": "",
                "baseLocationQuery": "",
                "targetQuery": "공중화장실",
                "place_intent_frame": {
                    "user_goal": "하단역에서 화장실 급함으로 가까운 공중화장실 찾기",
                    "anchor_location": "하단역",
                    "location_mode": "explicit",
                    "situation": "toilet",
                    "display_label": "화장실",
                    "candidate_category_codes": ["toilet"],
                    "candidate_place_types": ["공중화장실"],
                    "search_queries": ["공중화장실"],
                    "result_match_terms": ["화장실", "공중화장실"],
                    "constraints": ["가까운 곳"],
                    "exclusions": [],
                    "preferred_place_natures": ["ordinary_public_access"],
                    "excluded_place_natures": [],
                    "confidence": 0.9,
                },
            },
            "confidence": 0.9,
        }

        plan = build_conversational_search_plan("하단역인데 화장실 급해")
        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]

        self.assertEqual(plan["plan_source"], "ai")
        self.assertEqual(plan["execution_mode"], "frame")
        self.assertEqual(search_plan["locationQuery"], "하단역")
        self.assertEqual(search_plan["baseLocationQuery"], "하단역")
        self.assertEqual(search_plan["anchorLocation"], "하단역")
        self.assertEqual(search_plan["anchor_location"], "하단역")
        self.assertTrue(search_plan["has_explicit_location"])
        self.assertTrue(search_plan["location_resolution_required"])
        self.assertEqual(frame["anchor_location"], "하단역")
        self.assertEqual(frame["location_mode"], "explicit")
        self.assertIn("하단역 공중화장실", search_plan["kakaoKeywordCandidates"])
        self.assertEqual(plan["ai_debug"]["location_repair"]["status"], "skipped")
        self.assertEqual(plan["ai_debug"]["location_repair"]["checked_location_mode"], "explicit")
        self.assertEqual(plan["ai_debug"]["location_repair"]["checked_anchor_location"], "하단역")
        mock_ai.assert_called_once()

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_search_plan_api_promotes_frame_anchor_to_location_fields(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "waiting_place",
                "locationQuery": "",
                "baseLocationQuery": "",
                "targetQuery": "공중화장실",
                "place_intent_frame": {
                    "user_goal": "하단역에서 화장실 급함으로 가까운 공중화장실 찾기",
                    "anchor_location": "하단역",
                    "location_mode": "explicit",
                    "situation": "toilet",
                    "display_label": "화장실",
                    "candidate_category_codes": ["toilet"],
                    "candidate_place_types": ["공중화장실"],
                    "search_queries": ["공중화장실"],
                    "result_match_terms": ["화장실", "공중화장실"],
                    "constraints": ["가까운 곳"],
                    "exclusions": [],
                    "preferred_place_natures": ["ordinary_public_access"],
                    "excluded_place_natures": [],
                    "confidence": 0.9,
                },
            },
            "confidence": 0.9,
        }

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": "하단역인데 화장실 급해"}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        search_plan = data["search_plan"]
        frame = search_plan["place_intent_frame"]
        self.assertEqual(search_plan["locationQuery"], "하단역")
        self.assertEqual(search_plan["location_query"], "하단역")
        self.assertEqual(search_plan["baseLocationQuery"], "하단역")
        self.assertEqual(search_plan["base_location_query"], "하단역")
        self.assertEqual(search_plan["anchorLocation"], "하단역")
        self.assertEqual(search_plan["anchor_location"], "하단역")
        self.assertEqual(search_plan["locationMode"], "explicit")
        self.assertEqual(search_plan["location_mode"], "explicit")
        self.assertTrue(search_plan["has_explicit_location"])
        self.assertTrue(search_plan["location_resolution_required"])
        self.assertEqual(frame["anchor_location"], "하단역")
        self.assertEqual(frame["location_mode"], "explicit")
        self.assertIn("하단역 공중화장실", search_plan["kakaoKeywordCandidates"])
        mock_ai.assert_called_once()

    @patch("recommendations.views.build_conversational_search_plan")
    def test_conversational_search_plan_api_syncs_final_response_from_ai_debug_frame_anchor(self, mock_builder):
        mock_builder.return_value = {
            "action": "search",
            "intent_type": "place_recommendation",
            "search_plan": {
                "scenario": "waiting_place",
                "locationQuery": "",
                "baseLocationQuery": "",
                "anchorLocation": "",
                "locationMode": "current_context",
                "targetQuery": "공중화장실",
                "kakaoKeywordCandidates": ["공중화장실"],
                "place_intent_frame": {
                    "user_goal": "현재 위치 기반으로 가까운 공중화장실을 찾는 요청",
                    "anchor_location": "",
                    "location_mode": "current_context",
                    "situation": "toilet",
                    "display_label": "화장실",
                    "candidate_category_codes": ["toilet"],
                    "candidate_place_types": ["공중화장실", "화장실"],
                    "search_queries": ["공중화장실"],
                    "result_match_terms": ["화장실", "공중화장실"],
                    "constraints": ["가까운 곳"],
                    "exclusions": [],
                    "preferred_place_natures": ["ordinary_public_access"],
                    "excluded_place_natures": [],
                    "confidence": 0.9,
                },
            },
            "location": {
                "text": "",
                "is_explicit": False,
                "fallback": "current_location",
            },
            "execution_policy": {
                "run_search": True,
                "preserve_explicit_location": False,
            },
            "parser_provider": "gms",
            "parser_fallback": False,
            "plan_source": "ai",
            "execution_mode": "frame",
            "ai_debug": {
                "location_repair": {
                    "status": "skipped",
                    "reason": "not_current_context_without_anchor",
                    "checked_location_mode": "explicit",
                    "checked_anchor_location": "하단역",
                    "frame_location_mode": "explicit",
                    "frame_anchor_location": "하단역",
                    "plan_location_mode": "",
                    "plan_anchor_location": "",
                    "plan_location_query": "",
                },
            },
        }

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": "하단역인데 화장실 급해"}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        search_plan = data["search_plan"]
        frame = search_plan["place_intent_frame"]
        self.assertEqual(frame["anchor_location"], "하단역")
        self.assertEqual(frame["location_mode"], "explicit")
        self.assertEqual(search_plan["locationQuery"], "하단역")
        self.assertEqual(search_plan["baseLocationQuery"], "하단역")
        self.assertEqual(search_plan["anchorLocation"], "하단역")
        self.assertEqual(search_plan["locationMode"], "explicit")
        self.assertTrue(search_plan["has_explicit_location"])
        self.assertTrue(search_plan["location_resolution_required"])
        self.assertEqual(data["location"]["text"], "하단역")
        self.assertTrue(data["location"]["is_explicit"])
        self.assertTrue(data["execution_policy"]["preserve_explicit_location"])
        self.assertIn("하단역 공중화장실", search_plan["kakaoKeywordCandidates"])
        self.assertIn("하단역 화장실", search_plan["kakaoKeywordCandidates"])
        self.assertEqual(
            data["ai_debug"]["final_search_plan"]["final_search_plan_anchor_location"],
            "하단역",
        )
        self.assertEqual(
            data["ai_debug"]["final_search_plan"]["final_search_plan_locationQuery"],
            "하단역",
        )
        self.assertEqual(
            data["ai_debug"]["final_search_plan"]["final_frame_anchor_location"],
            "하단역",
        )
        self.assertEqual(
            data["ai_debug"]["final_search_plan"]["final_frame_location_mode"],
            "explicit",
        )

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_search_plan_api_repairs_missing_location_with_ai(self, mock_ai):
        mock_ai.side_effect = [
            {
                "action": "search",
                "search_plan": {
                    "scenario": "waiting_place",
                    "locationQuery": "",
                    "targetQuery": "공중화장실",
                    "place_intent_frame": {
                        "user_goal": "현재 위치 기반으로 가까운 공중화장실을 찾는 요청",
                        "anchor_location": "",
                        "location_mode": "current_context",
                        "situation": "toilet",
                        "display_label": "화장실",
                        "candidate_category_codes": ["toilet"],
                        "candidate_place_types": ["공중화장실"],
                        "search_queries": ["공중화장실"],
                        "result_match_terms": ["화장실", "공중화장실"],
                        "constraints": ["가까운 곳"],
                        "exclusions": [],
                        "preferred_place_natures": ["ordinary_public_access"],
                        "excluded_place_natures": [],
                        "confidence": 0.86,
                    },
                },
                "confidence": 0.86,
            },
            {
                "explicit_anchor_location": "하단역",
            },
        ]

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": "하단역인데 화장실 급해"}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        search_plan = data["search_plan"]
        frame = search_plan["place_intent_frame"]
        self.assertEqual(data["parser_provider"], "gms")
        self.assertFalse(data["parser_fallback"])
        self.assertEqual(data["plan_source"], "ai")
        self.assertEqual(data["execution_mode"], "frame")
        self.assertEqual(search_plan["locationQuery"], "하단역")
        self.assertEqual(frame["location_mode"], "explicit")
        self.assertEqual(frame["anchor_location"], "하단역")
        self.assertIn("하단역 공중화장실", search_plan["kakaoKeywordCandidates"])
        self.assertNotEqual(search_plan["kakaoKeywordCandidates"], ["공중화장실"])
        self.assertEqual(data["ai_debug"]["location_repair"]["checked_location_mode"], "current_context")
        self.assertEqual(data["ai_debug"]["location_repair"]["checked_anchor_location"], "")
        self.assertEqual(data["ai_debug"]["location_repair"]["frame_location_mode"], "current_context")
        self.assertEqual(data["ai_debug"]["location_repair"]["frame_anchor_location"], "")
        self.assertEqual(data["ai_debug"]["location_repair"]["status"], "repaired")
        self.assertEqual(data["ai_debug"]["location_repair"]["explicit_anchor_location"], "하단역")
        self.assertEqual(mock_ai.call_count, 2)

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_uses_ai_frame_for_colloquial_toilet_query(self, mock_ai):
        mock_ai.side_effect = [
            {
                "action": "search",
                "search_plan": {
                    "scenario": "waiting_place",
                    "locationQuery": "",
                    "targetQuery": "화장실",
                    "place_intent_frame": {
                        "user_goal": "가까운 화장실 찾기",
                        "anchor_location": "",
                        "location_mode": "current_context",
                        "situation": "toilet",
                        "display_label": "화장실",
                        "candidate_category_codes": ["toilet"],
                        "candidate_place_types": ["공중화장실", "개방화장실"],
                        "search_queries": ["공중화장실", "개방화장실"],
                        "result_match_terms": ["화장실", "공중화장실", "개방화장실"],
                        "constraints": ["가까운 곳"],
                        "exclusions": [],
                        "preferred_place_natures": ["ordinary_public_access"],
                        "excluded_place_natures": [],
                        "confidence": 0.9,
                    },
                },
                "confidence": 0.9,
            },
            {
                "explicit_anchor_location": "",
            },
        ]

        plan = build_conversational_search_plan("똥 마려운데 우야노")
        search_plan = plan["search_plan"]
        frame = search_plan["place_intent_frame"]

        self.assertEqual(plan["parser_provider"], "gms")
        self.assertFalse(plan["parser_fallback"])
        self.assertEqual(plan["plan_source"], "ai")
        self.assertEqual(plan["execution_mode"], "frame")
        self.assertEqual(frame["location_mode"], "current_context")
        self.assertEqual(frame["anchor_location"], "")
        self.assertEqual(frame["candidate_category_codes"], ["toilet"])
        self.assertIn("공중화장실", frame["candidate_place_types"])
        self.assertEqual(plan["ai_debug"]["location_repair"]["status"], "executed")
        self.assertEqual(plan["ai_debug"]["location_repair"]["reason"], "no_explicit_location_found")
        self.assertEqual(plan["ai_debug"]["location_repair"]["checked_location_mode"], "current_context")
        self.assertEqual(plan["ai_debug"]["location_repair"]["checked_anchor_location"], "")
        self.assertEqual(mock_ai.call_count, 2)

    @override_settings(
        CONVERSATIONAL_SEARCH_AI_ENABLED=True,
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-gms",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_conversational_search_plan_api_uses_ai_frame_for_colloquial_toilet_query(self, mock_ai):
        mock_ai.side_effect = [
            {
                "action": "search",
                "search_plan": {
                    "scenario": "waiting_place",
                    "locationQuery": "",
                    "targetQuery": "화장실",
                    "place_intent_frame": {
                        "user_goal": "가까운 화장실 찾기",
                        "anchor_location": "",
                        "location_mode": "current_context",
                        "situation": "toilet",
                        "display_label": "화장실",
                        "candidate_category_codes": ["toilet"],
                        "candidate_place_types": ["공중화장실", "개방화장실"],
                        "search_queries": ["공중화장실", "개방화장실"],
                        "result_match_terms": ["화장실", "공중화장실", "개방화장실"],
                        "constraints": ["가까운 곳"],
                        "exclusions": [],
                        "preferred_place_natures": ["ordinary_public_access"],
                        "excluded_place_natures": [],
                        "confidence": 0.9,
                    },
                },
                "confidence": 0.9,
            },
            {
                "explicit_anchor_location": "",
            },
        ]

        response = self.client.post(
            "/api/recommendations/conversational-search-plan/",
            data=json.dumps({"query": "똥 마려운데 우야노"}, ensure_ascii=False),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        frame = data["search_plan"]["place_intent_frame"]
        self.assertEqual(data["parser_provider"], "gms")
        self.assertFalse(data["parser_fallback"])
        self.assertEqual(data["plan_source"], "ai")
        self.assertEqual(data["execution_mode"], "frame")
        self.assertEqual(frame["location_mode"], "current_context")
        self.assertEqual(frame["anchor_location"], "")
        self.assertEqual(frame["candidate_category_codes"], ["toilet"])
        self.assertIn("공중화장실", frame["candidate_place_types"])
        self.assertEqual(data["ai_debug"]["location_repair"]["status"], "executed")
        self.assertEqual(data["ai_debug"]["location_repair"]["reason"], "no_explicit_location_found")
        self.assertEqual(data["ai_debug"]["location_repair"]["checked_location_mode"], "current_context")
        self.assertEqual(data["ai_debug"]["location_repair"]["checked_anchor_location"], "")
        self.assertEqual(mock_ai.call_count, 2)

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_conversational_search_planner_uses_current_location_when_location_missing(self):
        plan = build_conversational_search_plan("배고픈데 혼자 먹기 편한 데")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["location"]["text"], "")
        self.assertEqual(plan["location"]["fallback"], "current_location")
        self.assertEqual(plan["search_plan"]["scenario"], "restaurant")
        self.assertIn("혼자 이용하기 좋음", plan["conditions"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
    def test_conversational_search_planner_asks_for_ambiguous_reference_without_context(self):
        plan = build_conversational_search_plan("거기 말고 좀 조용한 데")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertTrue(plan["needs_clarification"])
        self.assertIn("이전 검색 결과가 없어서", plan["clarification_question"])

    @override_settings(AI_PROVIDER="rule")
    def test_ai_parser_routes_menu_matjip_queries_to_food_intent(self):
        cases = [
            ("소금빵 맛집 찾아줘", "소금빵", ["베이커리", "빵집", "카페"]),
            ("디저트 맛집 찾아줘", "디저트", ["베이커리", "빵집", "카페"]),
            ("브런치 맛집 찾아줘", "브런치", ["카페"]),
            ("쌀국수 먹고 싶어", "쌀국수", ["식당", "음식점"]),
            ("혼자 밥 먹기 좋은 식당 추천해줘", "밥", ["식당", "음식점"]),
        ]

        for query, expected_menu, expected_place_types in cases:
            with self.subTest(query=query):
                parsed = parse_situation(query)

                self.assertEqual(parsed["scenario"], "restaurant")
                self.assertIn(expected_menu, parsed.get("menu_keywords", []))
                self.assertTrue(
                    any(
                        keyword in parsed.get("place_type_keywords", [])
                        for keyword in expected_place_types
                    )
                )
                self.assertNotEqual(parsed["scenario"], "waiting_place")

    @override_settings(AI_PROVIDER="rule")
    def test_ai_parser_keeps_explicit_waiting_place_intent(self):
        parsed = parse_situation("잠깐 쉴 곳 추천해줘")

        self.assertEqual(parsed["scenario"], "waiting_place")
        self.assertIn("잠깐쉬기좋음", parsed["preferred_tags"])

    @patch("recommendations.services.ai_situation_parser._call_ai_parser")
    def test_ai_parser_normalizes_work_cafe_categories_and_tags(self, mock_call_ai_parser):
        mock_call_ai_parser.return_value = (
            "gms",
            json.dumps({
                "is_searchable": True,
                "scenario": "work_cafe",
                "categories": [
                    "cafe",
                    "restaurant",
                    "city_park",
                    "beach",
                    "shelter",
                    "smoking_area",
                    "tourism",
                ],
                "preferred_tags": [
                    "노트북작업",
                    "조용한",
                    "와이파이",
                    "콘센트있음",
                    "실내쉼터",
                    "편의시설",
                    "실외흡연구역",
                ],
                "keywords": ["작업", "카페"],
                "situation_summary": "조용히 작업할 곳",
                "reason_hint": "작업 장소 의도",
            }, ensure_ascii=False),
        )

        parsed = parse_situation("조용히 작업할 곳")

        self.assertEqual(parsed["scenario"], "work_cafe")
        self.assertEqual(parsed["categories"], ["cafe"])
        self.assertEqual(
            parsed["preferred_tags"],
            ["노트북작업", "조용한", "와이파이", "콘센트있음"],
        )

    @patch("recommendations.services.ai_situation_parser._call_ai_parser")
    def test_ai_parser_normalizes_waiting_place_preferred_tags(self, mock_call_ai_parser):
        mock_call_ai_parser.return_value = (
            "gms",
            json.dumps({
                "is_searchable": True,
                "scenario": "waiting_place",
                "categories": ["cafe", "shelter", "restaurant", "tourism", "smoking_area"],
                "preferred_tags": [
                    "잠깐쉬기좋음",
                    "실내쉼터",
                    "조용한",
                    "혼자이용좋음",
                    "편의시설",
                    "노트북작업",
                    "와이파이",
                    "콘센트있음",
                    "실외흡연구역",
                    "식사가능",
                    "힐링",
                ],
                "keywords": ["잠깐", "쉴 곳"],
                "situation_summary": "잠깐 쉴 곳 추천해줘",
                "reason_hint": "짧게 쉬는 장소",
            }, ensure_ascii=False),
        )

        parsed = parse_situation("잠깐 쉴 곳 추천해줘")

        self.assertEqual(parsed["scenario"], "waiting_place")
        self.assertEqual(parsed["categories"], ["cafe", "shelter"])
        self.assertEqual(
            parsed["preferred_tags"],
            ["잠깐쉬기좋음", "실내쉼터", "조용한", "혼자이용좋음", "편의시설"],
        )

    @override_settings(
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_situation_parser.requests.post")
    def test_ai_parser_corrects_food_query_misclassified_as_waiting_place(self, mock_post):
        safety_response = Mock()
        safety_response.raise_for_status.return_value = None
        safety_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "is_searchable": True,
                            "safety_reason": "",
                            "user_message": "",
                        }, ensure_ascii=False)
                    }
                }
            ]
        }
        parser_response = Mock()
        parser_response.raise_for_status.return_value = None
        parser_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "scenario": "waiting_place",
                            "categories": ["shelter", "city_park"],
                            "preferred_tags": ["잠깐쉬기좋음"],
                            "keywords": ["쉼터", "공원"],
                            "situation_summary": "소금빵 맛집 찾아줘",
                            "reason_hint": "잘못된 대기 장소 해석",
                        }, ensure_ascii=False)
                    }
                }
            ]
        }
        mock_post.side_effect = [safety_response, parser_response]

        parsed = parse_situation("소금빵 맛집 찾아줘")

        self.assertEqual(parsed["scenario"], "restaurant")
        self.assertIn("소금빵", parsed.get("menu_keywords", []))
        self.assertIn("베이커리", parsed.get("place_type_keywords", []))
        self.assertIn("cafe", parsed.get("categories", []))
        self.assertNotIn("city_park", parsed.get("categories", []))
        self.assertEqual(mock_post.call_count, 2)

    @override_settings(
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_situation_parser.requests.post")
    def test_ai_parser_can_block_inappropriate_place_use(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "is_searchable": False,
                            "safety_reason": "영업장과 공공장소의 비정상적 이용 목적입니다.",
                            "user_message": "요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.",
                        }, ensure_ascii=False)
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        parsed = parse_situation("영업장을 더럽히는 장소를 찾아줘")

        self.assertFalse(parsed["is_searchable"])
        self.assertTrue(parsed["blocked"])
        self.assertEqual(parsed["block_reason"], "inappropriate_place_use")
        self.assertFalse(parsed["fallback_enabled"])
        self.assertEqual(mock_post.call_count, 1)

    @patch("recommendations.views.parse_situation", side_effect=AssertionError("parse_situation must not reroute /ai-search"))
    @patch("recommendations.services.ai_search_orchestrator.build_ai_intent_plan")
    def test_ai_search_returns_empty_when_parser_blocks_query(self, mock_intent, mock_parse):
        mock_intent.return_value = {
            "action": "blocked",
            "decision_action": "blocked",
            "normalized_query": "부적절한 장소 이용 요청",
            "frame": {
                "location_mode": "current_context",
                "anchor_location": "",
                "target_objects": [],
                "candidate_place_types": [],
                "result_match_terms": [],
                "constraints": [],
                "exclusions": [],
                "ranking_policy": "evidence_first",
                "primary_search_queries": [],
                "secondary_search_queries": [],
            },
            "clarification": {},
            "confidence": 0.95,
            "ai_retry_count": 0,
        }

        response = self.client.post(
            "/api/recommendations/ai-search/",
            data=json.dumps({
                "query": "부적절한 장소 이용 요청",
                "lat": 35.1556,
                "lng": 129.0641,
                "limit": 10,
            }),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["blocked"])
        self.assertEqual(data["results"], [])
        self.assertEqual(data["decision_action"], "blocked")
        self.assertFalse(data["ai_parse"]["is_searchable"])
        mock_parse.assert_not_called()

    @patch("recommendations.views.parse_situation")
    def test_search_safety_endpoint_blocks_without_running_search(self, mock_parse):
        mock_parse.return_value = {
            "scenario": "restaurant",
            "situation_summary": "부적절한 장소 이용 요청",
            "is_searchable": False,
            "blocked": True,
            "block_reason": "inappropriate_place_use",
            "user_message": "요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.",
        }

        response = self.client.post(
            "/api/recommendations/search-safety/",
            data=json.dumps({
                "query": "부적절한 장소 이용 요청",
            }),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["blocked"])
        self.assertFalse(data["is_searchable"])
        self.assertEqual(data["reason"], "inappropriate_place_use")
        self.assertEqual(
            data["message"],
            "요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.",
        )

    @override_settings(
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_situation_parser.requests.post")
    def test_ai_parser_falls_back_when_gms_fails(self, mock_post):
        safety_response = Mock()
        safety_response.raise_for_status.return_value = None
        safety_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "is_searchable": True,
                            "safety_reason": "",
                            "user_message": "",
                        }, ensure_ascii=False)
                    }
                }
            ]
        }
        mock_post.side_effect = [safety_response, RuntimeError("network unavailable")]

        parsed = parse_situation("비 오는데 잠깐 실내에서 쉴 곳")

        self.assertEqual(parsed["scenario"], "waiting_place")
        self.assertEqual(parsed["parser_provider"], "rule")
        self.assertTrue(parsed["parser_fallback"])

    @override_settings(
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_situation_parser.requests.post")
    def test_ai_parser_blocks_when_gms_safety_check_fails(self, mock_post):
        mock_post.side_effect = RuntimeError("safety unavailable")

        parsed = parse_situation("정상 이용 범위를 벗어난 장소 요청")

        self.assertFalse(parsed["is_searchable"])
        self.assertTrue(parsed["blocked"])
        self.assertEqual(parsed["block_reason"], "safety_check_unavailable")
        self.assertEqual(parsed["parser_provider"], "gms")
        self.assertFalse(parsed["parser_fallback"])
