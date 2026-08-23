from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from recommendations.models import ConversationSession, ConversationTurn
from recommendations.services.ai_search_orchestrator import run_ai_search
from recommendations.services.conversation_sessions import resolve_previous_result_action


class ConversationSessionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _create_anonymous_session(self):
        response = self.client.post("/api/recommendations/conversation-sessions/", {}, format="json")
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_previous_result_compare_select_and_reset_are_deterministic(self):
        context = {
            "previous_results": [
                {"id": "db:1", "name": "첫 식당"},
                {"id": "db:2", "name": "둘째 식당"},
                {"id": "db:3", "name": "셋째 식당"},
            ],
            "search_plan": {"scenario": "ai_place_search"},
            "place_intent_frame": {"target_objects": ["식당"]},
        }

        compare = resolve_previous_result_action("첫 번째랑 세 번째 비교해줘", context)
        select = resolve_previous_result_action("두 번째가 좋아", context)
        reset = resolve_previous_result_action("처음부터 다시 찾자", context)

        self.assertEqual(compare["action"], "compare_previous_results")
        self.assertEqual([item["id"] for item in compare["results"]], ["db:1", "db:3"])
        self.assertEqual(select["action"], "select_previous_result")
        self.assertEqual(select["results"][0]["id"], "db:2")
        self.assertEqual(reset["action"], "reset_conversation")

        empty_compare = resolve_previous_result_action(
            "첫 번째랑 세 번째 비교해줘",
            {"previous_results": []},
        )
        self.assertEqual(empty_compare["action"], "compare_previous_results")
        self.assertEqual(empty_compare["results"], [])

    def test_ai_search_returns_previous_result_action_without_new_retrieval(self):
        response = run_ai_search({
            "query": "두 번째가 좋아",
            "previous_context": {
                "previous_results": [
                    {"id": "db:1", "name": "첫 식당"},
                    {"id": "db:2", "name": "둘째 식당"},
                ],
                "search_plan": {"scenario": "ai_place_search"},
                "place_intent_frame": {"target_objects": ["식당"]},
            },
        })

        self.assertEqual(response["decision_action"], "select_previous_result")
        self.assertEqual(response["results"][0]["id"], "db:2")

    def test_anonymous_session_requires_returned_secret_token(self):
        created = self._create_anonymous_session()
        url = f"/api/recommendations/conversation-sessions/{created['id']}/"

        denied = self.client.get(url)
        allowed = self.client.get(url, HTTP_X_CONVERSATION_TOKEN=created["conversation_token"])

        self.assertEqual(denied.status_code, 404)
        self.assertEqual(allowed.status_code, 200)
        self.assertNotIn("anonymous_token_hash", allowed.json())

    @patch("recommendations.views.run_ai_search")
    def test_turn_persists_state_and_supplies_it_to_next_search(self, mock_search):
        mock_search.side_effect = [
            {
                "decision_action": "search",
                "message": "식당을 찾았어요.",
                "search_plan": {"scenario": "ai_place_search"},
                "place_intent_frame": {
                    "anchor_location": "서면",
                    "target_objects": ["식당"],
                    "constraints": ["가족 식사"],
                },
                "results": [{"id": "db:1", "name": "가족식당", "category": "restaurant"}],
                "debug_pipeline": {"location_resolution": {"label": "서면", "lat": 35.15, "lng": 129.05}},
            },
            {
                "decision_action": "search",
                "message": "주차 조건을 추가했어요.",
                "search_plan": {"scenario": "ai_place_search"},
                "place_intent_frame": {
                    "anchor_location": "서면",
                    "target_objects": ["식당"],
                    "constraints": ["가족 식사", "주차 가능"],
                },
                "results": [],
                "debug_pipeline": {},
            },
        ]
        created = self._create_anonymous_session()
        headers = {"HTTP_X_CONVERSATION_TOKEN": created["conversation_token"]}
        url = f"/api/recommendations/conversation-sessions/{created['id']}/turns/"

        first = self.client.post(url, {"query": "서면에서 가족 식사할 곳"}, format="json", **headers)
        second = self.client.post(url, {"query": "주차되는 곳만"}, format="json", **headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        second_payload = mock_search.call_args_list[1].args[0]
        previous = second_payload["previous_context"]
        self.assertEqual(previous["place_intent_frame"]["anchor_location"], "서면")
        self.assertEqual(previous["previous_results"][0]["name"], "가족식당")
        session = ConversationSession.objects.get(pk=created["id"])
        self.assertEqual(session.turn_count, 2)
        self.assertEqual(session.version, 2)
        self.assertEqual(ConversationTurn.objects.filter(session=session).count(), 2)

    def test_closed_session_rejects_new_turns(self):
        created = self._create_anonymous_session()
        headers = {"HTTP_X_CONVERSATION_TOKEN": created["conversation_token"]}
        detail_url = f"/api/recommendations/conversation-sessions/{created['id']}/"
        turn_url = f"/api/recommendations/conversation-sessions/{created['id']}/turns/"

        closed = self.client.delete(detail_url, **headers)
        turn = self.client.post(turn_url, {"query": "다시 검색"}, format="json", **headers)

        self.assertEqual(closed.status_code, 204)
        self.assertEqual(turn.status_code, 409)
