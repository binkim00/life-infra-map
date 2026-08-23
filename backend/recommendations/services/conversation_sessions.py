import hashlib
import hmac
import re
import secrets

from django.db import transaction

from recommendations.models import ConversationSession, ConversationTurn


TOKEN_HEADER = "HTTP_X_CONVERSATION_TOKEN"
RESULT_REF_FIELDS = (
    "id",
    "place_id",
    "external_id",
    "name",
    "category",
    "address",
    "lat",
    "lng",
    "distance",
    "candidate_source",
    "source",
    "verified_tags",
    "matched_tags",
)


def _token_digest(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def create_conversation_session(user=None):
    authenticated_user = user if getattr(user, "is_authenticated", False) else None
    token = "" if authenticated_user else secrets.token_urlsafe(32)
    session = ConversationSession.objects.create(
        user=authenticated_user,
        anonymous_token_hash=_token_digest(token) if token else "",
    )
    return session, token


def can_access_conversation_session(request, session):
    user = request.user if getattr(request.user, "is_authenticated", False) else None
    if session.user_id:
        return bool(user and user.pk == session.user_id)
    supplied_token = request.META.get(TOKEN_HEADER, "")
    if not supplied_token or not session.anonymous_token_hash:
        return False
    return hmac.compare_digest(_token_digest(supplied_token), session.anonymous_token_hash)


def result_references(results, limit=10):
    refs = []
    for result in (results or [])[:limit]:
        if not isinstance(result, dict):
            continue
        refs.append({
            key: result.get(key)
            for key in RESULT_REF_FIELDS
            if result.get(key) not in (None, "", [])
        })
    return refs


ORDINAL_PATTERNS = (
    (0, ("첫 번째", "첫번째", "1번", "1 번째")),
    (1, ("두 번째", "두번째", "2번", "2 번째")),
    (2, ("세 번째", "세번째", "3번", "3 번째")),
    (3, ("네 번째", "네번째", "4번", "4 번째")),
    (4, ("다섯 번째", "다섯번째", "5번", "5 번째")),
)


def resolve_previous_result_action(query, previous_context):
    text = re.sub(r"\s+", " ", str(query or "")).strip()
    compact = text.replace(" ", "")
    previous_context = previous_context if isinstance(previous_context, dict) else {}
    previous_results = previous_context.get("previous_results") or []

    if any(term in compact for term in ["처음부터다시", "새로검색", "대화초기화"]):
        return {
            "action": "reset_conversation",
            "results": [],
            "message": "이전 검색 조건을 지우고 새 검색을 시작할게요.",
        }

    indexes = []
    for index, patterns in ORDINAL_PATTERNS:
        if any(pattern.replace(" ", "") in compact for pattern in patterns):
            indexes.append(index)
    indexes = list(dict.fromkeys(indexes))
    selected = [
        previous_results[index]
        for index in indexes
        if index < len(previous_results) and isinstance(previous_results[index], dict)
    ]
    if "비교" in compact and len(indexes) >= 2:
        names = [str(item.get("name") or "후보") for item in selected[:2]]
        message = (
            f"{names[0]}와 {names[1]}를 조건별로 비교할게요."
            if len(names) >= 2
            else "이전 결과에 비교할 후보가 충분하지 않아요. 먼저 장소를 다시 검색해 주세요."
        )
        return {
            "action": "compare_previous_results",
            "results": selected,
            "result_indexes": indexes,
            "message": message,
        }
    if indexes and any(term in compact for term in ["좋아", "선택", "갈래", "고를게", "마음에들"]):
        message = (
            f"{selected[0].get('name') or '선택한 장소'}를 선택했어요."
            if selected
            else "해당 순번의 이전 결과가 없어요. 먼저 장소를 다시 검색해 주세요."
        )
        return {
            "action": "select_previous_result",
            "results": selected[:1],
            "result_indexes": indexes[:1],
            "message": message,
        }
    return None


def build_previous_context(state):
    state = state if isinstance(state, dict) else {}
    frame = state.get("place_intent_frame") or {}
    return {
        "search_plan": state.get("search_plan") or {},
        "place_intent_frame": frame,
        "pending_clarification_frame": frame,
        "is_clarification_followup": state.get("decision_action") == "ask_clarification",
        "clarification_answer": "",
        "pending_clarification_question": state.get("clarification_question") or "",
        "previous_user_query": state.get("previous_user_query") or "",
        "previous_results": state.get("previous_results") or [],
        "last_resolved_location_context": state.get("last_resolved_location_context") or {},
    }


def state_from_search_response(query, response):
    debug = response.get("debug_pipeline") if isinstance(response.get("debug_pipeline"), dict) else {}
    return {
        "previous_user_query": str(query or "")[:500],
        "decision_action": response.get("decision_action") or response.get("decisionAction") or "",
        "clarification_question": response.get("clarification_question") or "",
        "search_plan": response.get("search_plan") or {},
        "place_intent_frame": response.get("place_intent_frame") or {},
        "previous_results": result_references(response.get("results") or []),
        "last_resolved_location_context": debug.get("location_resolution") or {},
    }


def persist_conversation_turn(session_id, *, query, response, expected_version):
    next_state = state_from_search_response(query, response)
    with transaction.atomic():
        session = ConversationSession.objects.select_for_update().get(pk=session_id)
        if session.status != "active":
            raise ValueError("conversation_closed")
        if session.version != expected_version:
            raise ValueError("conversation_version_conflict")
        sequence = session.turn_count + 1
        ConversationTurn.objects.create(
            session=session,
            sequence=sequence,
            user_query=str(query or "")[:2000],
            action=next_state["decision_action"][:40],
            assistant_message=str(
                response.get("message")
                or response.get("clarification_question")
                or ""
            )[:4000],
            state_before=session.state,
            state_after=next_state,
            result_refs=next_state["previous_results"],
        )
        session.state = next_state
        session.version += 1
        session.turn_count = sequence
        if not session.title:
            session.title = str(query or "")[:200]
        session.save(update_fields=["state", "version", "turn_count", "title", "updated_at"])
    return session
