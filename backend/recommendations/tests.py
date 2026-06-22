import json
from unittest.mock import Mock, patch

import requests
from django.test import Client, TestCase, override_settings

from recommendations.models import Place, PlaceTag, Tag
from recommendations.services.ai_situation_parser import parse_situation
from recommendations.services.ai_web_search_provider import (
    clear_ai_web_search_cache,
    get_ai_web_search_result,
)


@override_settings(ALLOWED_HOSTS=["localhost", "testserver"])
class RecommendationSearchTests(TestCase):
    def setUp(self):
        clear_ai_web_search_cache()
        self.client = Client(HTTP_HOST="localhost")
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
        )

        self.assertFalse(result["enabled"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["reason"], "disabled")

    @override_settings(
        AI_WEB_SEARCH_ENABLED=True,
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
        AI_WEB_SEARCH_MODEL="gpt-5-mini",
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
                                        "evidence_sources": [
                                            {
                                                "title": "테스트 출처",
                                                "url": "https://example.com/place",
                                            }
                                        ],
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
        self.assertEqual(mock_post.call_args.kwargs["json"]["model"], "gpt-5-mini")
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["tools"],
            [{"type": "web_search"}],
        )
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://example.invalid/gmsapi/api.openai.com/v1/responses",
        )
        self.assertEqual(mock_post.call_args.kwargs["json"]["max_output_tokens"], 800)

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
                                        "evidence_sources": [
                                            {
                                                "title": "테스트 출처",
                                                "url": "https://example.com/cafe",
                                            }
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

        kwargs = {
            "query": "브런치 먹기 좋은 조용한 카페 추천",
            "lat": 35.1556,
            "lng": 129.0641,
            "condition": {"scenario": "work_cafe", "keywords": ["브런치", "카페"]},
            "existing_results_summary": {"db_count": 0, "kakao_fallback_count": 0},
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
    def test_ai_web_search_discards_incomplete_response(self, mock_post):
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
                                        "evidence_sources": [
                                            {
                                                "title": "테스트 출처",
                                                "url": "https://example.com/partial",
                                            }
                                        ],
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

        self.assertFalse(result["executed"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"], "api_error")
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

    @override_settings(
        AI_PROVIDER="gms",
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/parser",
    )
    @patch("recommendations.services.ai_situation_parser.requests.post")
    def test_ai_parser_falls_back_when_gms_fails(self, mock_post):
        mock_post.side_effect = RuntimeError("network unavailable")

        parsed = parse_situation("비 오는데 잠깐 실내에서 쉴 곳")

        self.assertEqual(parsed["scenario"], "waiting_place")
        self.assertEqual(parsed["parser_provider"], "rule")
        self.assertTrue(parsed["parser_fallback"])
