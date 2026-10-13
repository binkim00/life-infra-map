import hashlib
import hmac
import re
import secrets
from copy import deepcopy

from django.db import transaction

from recommendations.models import ConversationSession, ConversationTurn
from recommendations.services.area_gazetteer import resolve_area_coordinates_by_token


TOKEN_HEADER = "HTTP_X_CONVERSATION_TOKEN"
RESULT_REF_FIELDS = (
    "place_key",
    "identity_aliases",
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
    "place_url",
    "kakao_place_url",
    "phone",
    "result_tier",
    "matched_conditions",
    "missing_conditions",
    "matched_evidence",
    "hard_gate_violations",
)


def place_identity(result):
    source = str(result.get("candidate_source") or result.get("result_source") or result.get("source") or "db").lower()
    if "kakao" in source or "kakao" in str(result.get("source") or "").lower():
        source = "kakao"
    external = result.get("external_id")
    internal = result.get("place_id") or result.get("id")
    if external:
        return f"{source}:{external}"
    if internal is not None:
        value = str(internal)
        return value if value.startswith(("db:", "kakao:", "web:")) else f"{source}:{value}"
    return f"{source}:{result.get('name', '')}:{result.get('address', '')}"


def identity_aliases(result):
    aliases = {place_identity(result), str(result.get("place_key") or "")}
    for key in ("place_id", "id"):
        value = result.get(key)
        if value is not None:
            aliases.add(str(value) if ":" in str(value) else f"db:{value}")
    for key in ("kakao_place_url", "place_url"):
        match = re.search(r"place\.map\.kakao\.com/(\d+)", str(result.get(key) or ""))
        if match:
            aliases.add(f"kakao:{match.group(1)}")
    return sorted(aliases - {""})


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
        } | {"place_key": place_identity(result), "identity_aliases": identity_aliases(result)})
    return refs


ORDINAL_PATTERNS = (
    (0, ("첫 번째", "첫번째", "1번", "1 번째")),
    (1, ("두 번째", "두번째", "2번", "2 번째")),
    (2, ("세 번째", "세번째", "3번", "3 번째")),
    (3, ("네 번째", "네번째", "4번", "4 번째")),
    (4, ("다섯 번째", "다섯번째", "5번", "5 번째")),
)


def _legacy_previous_result_action(query, previous_context):
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
        if any(re.search(r"(?<!\d)" + re.escape(pattern.replace(" ", "")), compact) for pattern in patterns):
            indexes.append(index)
    indexes = list(dict.fromkeys(indexes))
    selected = [
        previous_results[index]
        for index in indexes
        if index < len(previous_results) and isinstance(previous_results[index], dict)
    ]
    if "비교" in compact and len(indexes) >= 2:
        names = [str(item.get("name") or "후보") for item in selected[:2]]
        if len(names) >= 2:
            rows = []
            for position, item in enumerate(selected[:2], start=1):
                facts = []
                if item.get("category"):
                    facts.append(str(item["category"]))
                if item.get("distance") is not None:
                    facts.append(f"약 {int(round(float(item['distance'])))}m")
                if item.get("address"):
                    facts.append(str(item["address"]))
                matched = item.get("matched_conditions") or []
                missing = item.get("missing_conditions") or []
                if matched:
                    facts.append(f"확인된 조건: {', '.join(map(str, matched))}")
                if missing:
                    facts.append(f"확인 필요: {', '.join(map(str, missing))}")
                rows.append(f"{position}. {names[position - 1]} — " + (" · ".join(facts) or "비교할 상세 정보가 부족해요"))
            message = "\n".join([
                f"{names[0]}와 {names[1]}의 확인 가능한 정보를 비교했어요.",
                *rows,
                "표시되지 않은 조건은 확인된 사실이 없어 단정하지 않았어요.",
            ])
        else:
            message = "이전 결과에 비교할 후보가 충분하지 않아요. 먼저 장소를 다시 검색해 주세요."
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


def resolve_previous_result_action(query, previous_context):
    context = previous_context or {}
    results = context.get("previous_results") or []
    compact = re.sub(r"\s+", "", str(query or ""))
    if any(word in compact for word in ("되돌려", "되돌리", "이전조건으로")) or ("취소" in compact and any(word in compact for word in ("방금", "변경", "마지막"))):
        history = context.get("state_history") or []
        return {"action": "undo_last_change", "results": (history[-1].get("previous_results") or []) if history else results,
                "restored_state": history[-1] if history else None,
                "message": "마지막 조건 변경을 되돌렸어요." if history else "되돌릴 조건 변경이 없어요."}
    indexes = [index for index, patterns in ORDINAL_PATTERNS if any(re.search(r"(?<!\d)" + re.escape(pattern.replace(" ", "")), compact) for pattern in patterns)]
    # Numeric ordinals beyond the named first five must never become a new search.
    indexes += [int(number) - 1 for number in re.findall(r"(?<!\d)(\d+)번", compact) if 1 <= int(number) <= 100]
    indexes = list(dict.fromkeys(indexes))
    selected_key = context.get("selected_result_key")
    pronoun = any(word in compact for word in ("거기", "그곳", "이곳", "그장소"))
    bare_info = any(word in compact for word in ("몇m", "몇미터", "얼마나멀", "왜추천", "어떤조건"))
    if not indexes and (pronoun or bare_info):
        indexes = [i for i, item in enumerate(results) if selected_key in identity_aliases(item)] if selected_key else []
    selected = [results[index] for index in indexes if 0 <= index < len(results)]
    exclusions = any(word in compact for word in ("빼줘", "빼고", "제외", "말고다른", "다른곳", "다른데"))
    if exclusions and (indexes or any(word in compact for word in ("다른곳", "다른데", "이결과", "나온곳"))):
        removed = selected if indexes else results
        keys = sorted(set(context.get("excluded_place_keys") or []) | {key for item in removed for key in identity_aliases(item)})
        return {"action": "exclude_previous_results", "results": [], "excluded_place_keys": keys,
                "message": "제외한 장소를 빼고 다시 찾았어요.", "result_indexes": indexes}
    info = bare_info or any(word in compact for word in ("왜", "이유", "추천한", "추천했", "알려", "있어", "가능해", "주차", "콘센트", "와이파이", "조용"))
    if info and (indexes or pronoun or bare_info):
        messages = []
        for item in selected:
            facts = list(dict.fromkeys([*(item.get("verified_tags") or []), *(item.get("matched_conditions") or [])]))
            messages.append(f"{item.get('name') or '선택한 장소'}: 확인된 조건은 {', '.join(map(str, facts)) if facts else '없습니다'}. 그 밖의 조건은 확인되지 않았습니다.")
            if item.get("distance") is not None:
                messages.append(f"저장된 검색 위치에서 약 {int(round(float(item['distance'])))}m입니다.")
            if item.get("address"):
                messages.append(str(item["address"]))
        return {"action": "explain_previous_result", "results": selected, "result_indexes": indexes,
                "message": "\n".join(messages) or "어느 장소인지 선택해 주세요. 해당 순번의 결과가 없습니다."}
    legacy = _legacy_previous_result_action(query, context)
    if legacy:
        return legacy
    if indexes or any(word in compact for word in ("거기", "그곳", "그장소")):
        return {"action": "explain_previous_result", "results": selected, "result_indexes": indexes,
                "message": "확인된 장소를 선택해 주세요." if not selected else f"{selected[0].get('name')}의 확인된 정보만 안내할 수 있어요."}
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
        "selected_result_key": state.get("selected_result_key"),
        "excluded_place_keys": state.get("excluded_place_keys") or [],
        "state_history": state.get("state_history") or [],
        "turn_count": state.get("turn_count") or 0,
    }


def _nonempty_overlay(base, update):
    merged = dict(base or {})
    for key, value in (update or {}).items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def state_from_search_response(query, response, previous_state=None):
    debug = response.get("debug_pipeline") if isinstance(response.get("debug_pipeline"), dict) else {}
    previous_state = previous_state if isinstance(previous_state, dict) else {}
    action = response.get("decision_action") or response.get("decisionAction") or ""
    response_plan = response.get("search_plan") or {}
    response_frame = response.get("place_intent_frame") or {}
    previous_plan = previous_state.get("search_plan") or {}
    previous_frame = previous_state.get("place_intent_frame") or {}
    previous_results = previous_state.get("previous_results") or []
    previous_location = previous_state.get("last_resolved_location_context") or {}
    if action == "reset_conversation":
        return {"decision_action": action, "previous_results": [], "place_intent_frame": {}, "search_plan": {}, "turn_count": int(previous_state.get("turn_count") or 0) + 1}
    if action == "undo_last_change" and response.get("restored_state"):
        return {**deepcopy(response["restored_state"]), "decision_action": action,
                "state_history": (previous_state.get("state_history") or [])[:-1], "turn_count": int(previous_state.get("turn_count") or 0) + 1}
    informational = action in {"compare_previous_results", "select_previous_result", "explain_previous_result", "undo_last_change"}
    if informational:
        response_frame = previous_frame
        response_plan = previous_plan
    history = list(previous_state.get("state_history") or [])
    changed = response_frame != previous_frame or response.get("excluded_place_keys", previous_state.get("excluded_place_keys") or []) != (previous_state.get("excluded_place_keys") or [])
    if previous_frame and changed and action not in {"ai_unavailable", "ask_clarification"} and not informational:
        history.append(deepcopy({key: value for key, value in previous_state.items() if key != "state_history"}))
    selected_key = previous_state.get("selected_result_key")
    if action in {"select_previous_result", "explain_previous_result"} and response.get("results"):
        selected_key = place_identity(response["results"][0])

    # A provider outage must not erase the last usable conversation frame. If
    # the failed turn itself is a known locality answer, retain that deterministic
    # location patch as well so the following turn can continue from it.
    if action in {"ai_unavailable", "ask_clarification"}:
        response_frame = _nonempty_overlay(previous_frame, response_frame)
        response_plan = _nonempty_overlay(previous_plan, response_plan)
        resolved_area = resolve_area_coordinates_by_token(query) if action == "ai_unavailable" else None
        if resolved_area:
            area_lat, area_lng, area_label = resolved_area
            response_frame.update({
                "location_mode": "explicit",
                "locationMode": "explicit",
                "anchor_location": str(query or "").strip(),
                "anchorLocation": str(query or "").strip(),
            })
            previous_location = {
                "status": "resolved",
                "source": "area_gazetteer_token",
                "label": area_label,
                "lat": area_lat,
                "lng": area_lng,
            }
        response_plan["place_intent_frame"] = response_frame

    if action == "ai_unavailable" and previous_frame and response_frame != previous_frame:
        # A valid semantic patch is committed even when subsequent retrieval or
        # ranking fails, so undo restores precisely that patch.
        history.append(deepcopy({key: value for key, value in previous_state.items() if key != "state_history"}))

    return {
        "previous_user_query": str(query or "")[:500],
        "decision_action": action,
        "clarification_question": response.get("clarification_question") or "",
        "search_plan": response_plan,
        "place_intent_frame": response_frame,
        "previous_results": (
            previous_results
            if action in {"ai_unavailable", "ask_clarification"} or informational
            else result_references(response.get("results") or [])
        ),
        "last_resolved_location_context": debug.get("location_resolution") or previous_location,
        "selected_result_key": response.get("selected_result_key") or selected_key,
        "excluded_place_keys": response.get("excluded_place_keys", previous_state.get("excluded_place_keys") or []),
        "state_history": history[-10:],
        "turn_count": int(previous_state.get("turn_count") or 0) + 1,
    }


def persist_conversation_turn(session_id, *, query, response, expected_version):
    with transaction.atomic():
        session = ConversationSession.objects.select_for_update().get(pk=session_id)
        if session.status != "active":
            raise ValueError("conversation_closed")
        if session.version != expected_version:
            raise ValueError("conversation_version_conflict")
        next_state = state_from_search_response(query, response, session.state)
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
