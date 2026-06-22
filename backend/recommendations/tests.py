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
        AI_WEB_SEARCH_AVAILABLE=True,
        AI_WEB_SEARCH_PROVIDER="gms",
        AI_WEB_SEARCH_GROUNDING_SUPPORTED=True,
        GMS_API_KEY="fake-key",
        GMS_API_URL="https://example.invalid/web-search",
        GMS_API_BASE_URL="https://example.invalid/gmsapi",
        GMS_OPENAI_RESPONSES_PATH="api.openai.com/v1/responses",
        AI_WEB_SEARCH_MODEL="gpt-5-nano",
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
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://example.invalid/gmsapi/api.openai.com/v1/responses",
        )
        self.assertEqual(mock_post.call_args.kwargs["json"]["max_output_tokens"], 800)
        self.assertEqual(
            result["candidates"][0]["evidence_sources"],
            [{"title": "web search source", "url": "https://example.com/place"}],
        )
        self.assertIn("source_url", mock_post.call_args.kwargs["json"]["input"])
        self.assertNotIn("evidence_sources", mock_post.call_args.kwargs["json"]["input"])

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

        self.assertFalse(result["executed"])
        self.assertEqual(result["error"], "api_error")
        self.assertEqual(result["error_detail"]["status_code"], 400)
        self.assertEqual(result["error_detail"]["type"], "bad_request")
        self.assertNotIn("fake-key", result["error_detail"]["message"])
        self.assertLessEqual(len(result["error_detail"]["message"]), 300)
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
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
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
        mock_post.return_value = mock_response

        parsed = parse_situation("소금빵 맛집 찾아줘")

        self.assertEqual(parsed["scenario"], "restaurant")
        self.assertIn("소금빵", parsed.get("menu_keywords", []))
        self.assertIn("베이커리", parsed.get("place_type_keywords", []))
        self.assertIn("cafe", parsed.get("categories", []))
        self.assertNotIn("city_park", parsed.get("categories", []))

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
