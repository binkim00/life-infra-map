from datetime import timedelta
import json
import shutil
import tempfile
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

    def test_non_tag_report_approval_only_updates_status_and_note(self):
        for report_type in ["new_place", "edit_place", "wrong_info"]:
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

    @override_settings(AI_PROVIDER="rule")
    def test_ai_recommendation_search_reuses_db_results(self):
        response = self.client.post(
            "/api/recommendations/ai-search/",
            {
                "query": "와이파이 되는 조용한 작업 카페",
                "lat": 35.1556,
                "lng": 129.0641,
                "limit": 3,
            },
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["ai_parse"]["scenario"], "work_cafe")
        self.assertEqual(data["results"][0]["id"], self.place.id)
        self.assertIn("ai_web_search", data)
        self.assertIn("candidates", data["ai_web_search"])
        self.assertFalse(data["ai_web_search"]["executed"])

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

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True, AI_PROVIDER="gms")
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

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True, AI_PROVIDER="gms")
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
        self.assertEqual(plan["search_plan"]["targetQuery"], "산책할 곳")
        self.assertIn("산책하기 좋음", plan["conditions"])
        mock_ai.assert_called_once()

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True, AI_PROVIDER="gms")
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
        self.assertEqual(plan["search_plan"]["targetQuery"], "산책할 곳")
        self.assertIn("바람 쐬기 좋음", plan["conditions"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True, AI_PROVIDER="gms")
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_validator_does_not_turn_cafe_negative_into_cafe_search(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "work_cafe",
                "locationQuery": "서면에서",
                "targetQuery": "카페",
                "categories": ["cafe"],
                "conditions": ["카페", "조용함"],
            },
            "confidence": 0.82,
        }

        plan = build_conversational_search_plan("서면에서 조용히 있고 싶은데 너무 카페 느낌은 아니었으면 좋겠어")

        self.assertEqual(plan["action"], "search")
        self.assertEqual(plan["search_plan"]["scenario"], "waiting_place")
        self.assertEqual(plan["search_plan"]["locationQuery"], "서면")
        self.assertEqual(plan["search_plan"]["targetQuery"], "쉴 곳")
        self.assertNotEqual(plan["search_plan"]["targetQuery"], "카페")
        self.assertNotIn("카페", plan["conditions"])
        self.assertIn("카페 제외", plan["conditions"])
        self.assertIn("카페", plan["search_plan"].get("excluded_categories", []))

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True, AI_PROVIDER="gms")
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
        self.assertEqual(plan["search_plan"]["targetQuery"], "카페")

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True, AI_PROVIDER="gms")
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_validator_unknown_action_asks_clarification(self, mock_ai):
        mock_ai.return_value = {
            "action": "unknown",
            "search_plan": {},
        }

        plan = build_conversational_search_plan("서면에서 오래 머물 곳 느낌 봐줘")

        self.assertEqual(plan["action"], "ask_clarification")
        self.assertTrue(plan["needs_clarification"])

    @override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=True, AI_PROVIDER="gms")
    @patch("recommendations.services.conversational_search_planner._call_gms_chat_json")
    def test_ai_intent_classifier_keeps_rule_priority_for_clear_cases(self, mock_ai):
        mock_ai.return_value = {
            "action": "search",
            "search_plan": {
                "scenario": "work_cafe",
                "targetQuery": "카페",
            },
        }

        cases = [
            ("흡연구역 찾아줘", "search", "smoking_area"),
            ("비트코인 지금 살까?", "out_of_scope", ""),
            ("불법적인 장소 알려줘", "blocked", ""),
            ("좋은 곳 추천해줘", "ask_clarification", ""),
        ]

        for query, expected_action, expected_scenario in cases:
            with self.subTest(query=query):
                plan = build_conversational_search_plan(query)

                self.assertEqual(plan["action"], expected_action)
                if expected_scenario:
                    self.assertEqual(plan["search_plan"]["scenario"], expected_scenario)

        mock_ai.assert_not_called()

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

    @patch("recommendations.views.parse_situation")
    def test_ai_search_returns_empty_when_parser_blocks_query(self, mock_parse):
        mock_parse.return_value = {
            "scenario": "restaurant",
            "situation_summary": "부적절한 장소 이용 요청",
            "is_searchable": False,
            "blocked": True,
            "block_reason": "inappropriate_place_use",
            "user_message": "요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.",
            "fallback_enabled": False,
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
        self.assertEqual(data["reason"], "inappropriate_place_use")
        self.assertFalse(data["ai_parse"]["is_searchable"])

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
