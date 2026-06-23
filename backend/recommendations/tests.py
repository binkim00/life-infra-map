from datetime import timedelta
import json
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from recommendations.models import Place, PlaceTag, Tag, UserPreference, UserSearchLog
from recommendations.services.ai_situation_parser import parse_situation
from recommendations.services.ai_web_search_provider import (
    clear_ai_web_search_cache,
    get_ai_web_search_result,
)
from recommendations.services.naver_search_provider import build_naver_search_query


@override_settings(ALLOWED_HOSTS=["localhost", "testserver"])
class RecommendationSearchTests(TestCase):
    def setUp(self):
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
