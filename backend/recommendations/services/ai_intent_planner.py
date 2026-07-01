import json
import logging
import re

from django.conf import settings
import requests

from recommendations.services.ai_situation_parser import _call_ai_chat_json as _shared_call_ai_chat_json
from recommendations.services.ai_json_client import get_ai_json_unavailable_reason


logger = logging.getLogger(__name__)

_call_gms_chat_json = _shared_call_ai_chat_json


def _call_ai_chat_json(*args, **kwargs):
    return _call_gms_chat_json(*args, **kwargs)


ALLOWED_ACTIONS = {"search", "ask_clarification", "out_of_scope", "blocked"}
ALLOWED_RANKING_POLICIES = {
    "evidence_first",
    "urgent_nearest",
    "cost_sensitive",
    "distance_first",
}

TRUSTED_FRAME_SOURCE = "ai_extracted"
CLARIFICATION_PATCH_SOURCE = "clarification_patch"

AI_INTENT_SYSTEM_PROMPT = """
You are the AI Intent Planner for a Korean situation-based place recommendation service.

Return only one JSON object. Do not write prose outside JSON.

Your job is to decide whether the user is asking for a place recommendation.
If yes, produce a structured place intent frame. If not, return out_of_scope.
If the user's situation is ambiguous, return ask_clarification with a concrete Korean question.

Hard rules:
- Do not use keyword rules or default place types.
- Do not invent real place names, addresses, coordinates, opening hours, facilities, or menu availability.
- Do not add cafe, shelter, restaurant, or any broad default unless the user's meaning specifically supports it.
- Profanity, slang, dialect, typo, and incomplete Korean should be normalized by meaning, not blocked by default.
- A general information question without an actionable place target is out_of_scope.
- A weather-related or health-related sentence can be search only when it clearly asks for a place to go.
- For medical symptoms, do not diagnose. If the target is unclear, ask whether the user wants medical/pharmacy help or a place to rest.
- For music/singing ambiguity, ask whether the user wants a place to sing or a place to listen.
- Follow-up answers are patches to the previous frame, not standalone raw queries.
- Preserve an earlier explicit location unless the current user message provides a new location.
- Search queries must be Korean keyword queries for place search.
- Long, noisy, vague, typo-heavy, slang, or dialect input must be normalized into the user's likely actionable place target.
- For activity phrasing, infer the place or facility that enables the activity when that is clear; do not search the raw verb phrase.
- Use canonical Korean place-search nouns rather than literal casual wording when building target_objects and primary_search_queries.
- When the request is searchable, produce 2 to 4 concise atomic primary_search_queries that preserve the same target from different search angles.
- Each primary_search_query must contain one place-search intent, not a list, not an explanation, and not a full natural-language sentence.
- If the user has a specific target, keep that target in the queries; do not replace it with a broad category.
- Do not put latitude/longitude, coordinate strings, "near 35.x,129.x", or radius text inside search queries.
- Put explicit location names only in anchor_location; current coordinates are supplied separately.

Schema:
{
  "action": "search | ask_clarification | out_of_scope | blocked",
  "normalized_query": "",
  "frame": {
    "location_mode": "explicit | current_context | clarification_required",
    "anchor_location": "",
    "target_objects": [],
    "candidate_place_types": [],
    "result_match_terms": [],
    "constraints": [],
    "exclusions": [],
    "ranking_policy": "evidence_first | urgent_nearest | cost_sensitive | distance_first",
    "primary_search_queries": [],
    "secondary_search_queries": []
  },
  "clarification": {
    "question": "",
    "options": [],
    "missing_fields": [],
    "expected_patch_fields": []
  },
  "confidence": 0.0
}

Validation expectations:
- search requires non-empty frame.target_objects and non-empty frame.primary_search_queries.
- explicit location_mode requires frame.anchor_location.
- ask_clarification requires clarification.question.
- out_of_scope and blocked must not include search queries.
""".strip()


AI_INTENT_REPAIR_SYSTEM_PROMPT = """
You repair one invalid AI Intent Planner JSON response.

Return only one valid JSON object that follows the schema exactly.
Do not add keyword-rule defaults. Do not invent place facts.
If the original answer cannot be repaired into a valid search frame, choose ask_clarification,
out_of_scope, or blocked as appropriate.
""".strip()


AI_QUERY_REPAIR_SYSTEM_PROMPT = """
You repair or expand search queries for an already valid place intent frame.

Return only JSON:
{"queries": [{"query": "", "relationship": "", "preserves_target": true}]}

Rules:
- Preserve the current target_objects and result_match_terms.
- Semantic expansions are allowed when they preserve the user's specific target.
- Do not replace a specific target with a generic category.
- Do not invent real place facts.
- Return at most 3 concise Korean search queries.
- Do not include latitude/longitude or radius text in the query string.
- Set preserves_target=false when the query only broadens to a generic category.
- Each query must be one atomic place-search keyword, not a list or explanatory sentence.
""".strip()


STRING_ARRAY_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
}

AI_INTENT_PLAN_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": sorted(ALLOWED_ACTIONS)},
        "normalized_query": {"type": "string"},
        "frame": {
            "type": "object",
            "properties": {
                "location_mode": {
                    "type": "string",
                    "enum": ["explicit", "current_context", "clarification_required"],
                },
                "anchor_location": {"type": "string"},
                "target_objects": STRING_ARRAY_SCHEMA,
                "candidate_place_types": STRING_ARRAY_SCHEMA,
                "result_match_terms": STRING_ARRAY_SCHEMA,
                "constraints": STRING_ARRAY_SCHEMA,
                "exclusions": STRING_ARRAY_SCHEMA,
                "ranking_policy": {"type": "string", "enum": sorted(ALLOWED_RANKING_POLICIES)},
                "primary_search_queries": STRING_ARRAY_SCHEMA,
                "secondary_search_queries": STRING_ARRAY_SCHEMA,
            },
            "required": [
                "location_mode",
                "anchor_location",
                "target_objects",
                "candidate_place_types",
                "result_match_terms",
                "constraints",
                "exclusions",
                "ranking_policy",
                "primary_search_queries",
                "secondary_search_queries",
            ],
            "additionalProperties": False,
        },
        "clarification": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["label", "value"],
                        "additionalProperties": False,
                    },
                },
                "missing_fields": STRING_ARRAY_SCHEMA,
                "expected_patch_fields": STRING_ARRAY_SCHEMA,
            },
            "required": ["question", "options", "missing_fields", "expected_patch_fields"],
            "additionalProperties": False,
        },
        "confidence": {"type": "number"},
    },
    "required": ["action", "normalized_query", "frame", "clarification", "confidence"],
    "additionalProperties": False,
}

AI_QUERY_REPAIR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "queries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "relationship": {"type": "string"},
                    "preserves_target": {"type": "boolean"},
                },
                "required": ["query", "relationship", "preserves_target"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["queries"],
    "additionalProperties": False,
}


QUERY_LIST_SEPARATOR_RE = re.compile(r"[,/;|]|(?:\s+or\s+)|(?:\s+and\s+)", re.IGNORECASE)


def _clean_text(value, max_length=240):
    text = str(value or "").strip()
    if max_length and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _compact(value):
    return _clean_text(value, max_length=300).lower().replace(" ", "")


def _as_list(value, max_items=12, max_length=80):
    if value in (None, ""):
        return []
    if isinstance(value, (str, int, float, bool)):
        value = [value]
    if not isinstance(value, list):
        return []

    result = []
    seen = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("value") or item.get("text") or item.get("label")
        text = _clean_text(item, max_length=max_length)
        key = _compact(text)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def _to_float(value, default=0.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(parsed, 1.0))


def _has_coordinates(lat=None, lng=None, map_center=None):
    if lat not in (None, "") and lng not in (None, ""):
        return True
    if isinstance(map_center, dict):
        return map_center.get("lat") not in (None, "") and map_center.get("lng") not in (None, "")
    return False


def _has_any(query, keywords):
    compact = _compact(query)
    return any(_compact(keyword) and _compact(keyword) in compact for keyword in keywords)


def _dedupe(values):
    result = []
    seen = set()
    for value in values or []:
        cleaned = _clean_text(value, 100)
        key = _compact(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _local_rule_exclusions(raw_query):
    text = _clean_text(raw_query, 500)
    compact = _compact(text)
    if not compact:
        return []
    markers = ["말고", "빼", "빼줘", "제외", "빼고", "아닌", "말아줘"]
    if not any(marker in compact for marker in markers):
        return []

    exclusions = []
    term_groups = [
        (["스터디카페", "스터디룸", "공간대여"], "스터디/공간대여 제외"),
        (["주차장", "주차"], "주차장 제외"),
        (["디저트", "케이크", "빵집", "베이커리"], "디저트 제외"),
        (["웹", "인터넷", "블로그", "후기"], "웹 근거 제외"),
    ]
    for terms, label in term_groups:
        if any(_compact(term) in compact for term in terms):
            exclusions.append(label)

    cafe_masked = compact.replace("스터디카페", "")
    cafe_exclusion_markers = [
        "카페말고",
        "카페는빼",
        "카페빼",
        "카페제외",
        "커피말고",
        "커피는빼",
        "커피빼",
        "커피제외",
    ]
    if any(marker in cafe_masked for marker in cafe_exclusion_markers):
        exclusions.append("카페 제외")
    return _dedupe(exclusions)


def _local_rule_anchor_location(raw_query):
    text = _clean_text(raw_query, 500)
    if not text:
        return ""
    current_context_markers = {"현재위치", "내위치", "여기", "지금위치", "currentlocation"}
    location_markers = (
        "근처에서",
        "주변에서",
        "인근에서",
        "앞에서",
        "쪽에서",
        "에서",
        "근처",
        "주변",
        "인근",
        "앞",
        "쪽",
        "일대",
    )
    marker_pattern = "|".join(re.escape(marker) for marker in location_markers)
    specific_location_match = re.search(
        rf"([\uac00-\ud7a3A-Za-z0-9·.-]{{2,24}}(?:\uc5ed|\ub3d9|\uad6c|\uc2dc|\ub300|\uc2dc\uc7a5|\ud574\uc218\uc695\uc7a5|\uacf5\ud56d|\ud130\ubbf8\ub110))\s*(?:{marker_pattern})(?:\s+|$)",
        text,
    )
    match = specific_location_match or re.match(rf"^(.{{1,40}}?)\s*(?:{marker_pattern})(?:\s+|$)", text)
    if not match:
        suffixes = (
            "특별자치시",
            "특별자치도",
            "광역시",
            "특별시",
            "해수욕장",
            "대학교",
            "터미널",
            "공항",
            "시장",
            "역",
            "구",
            "군",
            "시",
            "읍",
            "면",
            "동",
            "리",
            "대",
        )
        suffix_pattern = "|".join(re.escape(suffix) for suffix in suffixes)
        match = re.match(rf"^(.{{1,40}}?(?:{suffix_pattern}))\s+", text)
    if not match:
        intent_followers = (
            "밥",
            "식당",
            "맛집",
            "카페",
            "커피",
            "돈까스",
            "돈가스",
            "파스타",
            "쌀국수",
            "쇼핑",
            "백화점",
            "아울렛",
            "실내",
            "체험",
            "전시",
            "박물관",
            "화장실",
            "약국",
            "흡연",
            "담배",
            "노래",
            "주차장",
            "산책",
            "쉴",
        )
        follower_pattern = "|".join(re.escape(follower) for follower in intent_followers)
        match = re.match(rf"^([가-힣A-Za-z0-9·.-]{{2,20}})\s+(?=(?:근처\s+)?(?:{follower_pattern}))", text)
    if not match:
        return ""
    anchor = _clean_text(match.group(1), 80).strip(" \"'“”‘’.,")
    anchor = re.sub(r"^.+?(?:말고|제외하고|제외|빼고|빼)\s+", "", anchor).strip()
    if not anchor:
        return ""
    if _has_any(anchor, [
        "\ubc30\ud130\ub9ac",
        "\ucda9\uc804",
        "\ucf58\uc13c\ud2b8",
        "\ub354\uc6cc",
        "\ucd94\uc6cc",
        "\ube44 \uc624",
        "\ube44\uc624",
    ]):
        return ""
    if _compact(anchor) in current_context_markers:
        return ""
    if _has_any(anchor, ["쇼핑", "실내", "체험", "놀거리", "액티비티", "카페", "식당", "맛집"]):
        return ""
    if _has_any(anchor, ["머리", "아픈", "아파", "두통", "배고", "목마", "비오", "비 오", "더워", "추워"]):
        return ""
    return anchor


def _local_rule_search_plan(
    raw_query,
    *,
    normalized_query,
    target_objects,
    candidate_place_types,
    result_match_terms,
    primary_search_queries,
    constraints=None,
    exclusions=None,
    candidate_category_codes=None,
    ranking_policy="evidence_first",
):
    anchor_location = _local_rule_anchor_location(raw_query)
    location_mode = "explicit" if anchor_location else "current_context"
    combined_exclusions = _dedupe([*(exclusions or []), *_local_rule_exclusions(raw_query)])
    return {
        "action": "search",
        "decision_action": "search",
        "can_search_now": True,
        "normalized_query": normalized_query,
        "frame": {
            "location_mode": location_mode,
            "anchor_location": anchor_location,
            "target_objects": target_objects,
            "candidate_place_types": candidate_place_types,
            "result_match_terms": result_match_terms,
            "constraints": constraints or [],
            "exclusions": combined_exclusions,
            "candidate_category_codes": candidate_category_codes or [],
            "ranking_policy": ranking_policy,
            "primary_search_queries": primary_search_queries,
            "secondary_search_queries": [],
        },
        "clarification": {},
        "confidence": 0.86,
        "ai_retry_count": 0,
        "ai_debug": {
            "planner": {
                "status": "local_rule",
                "reason": "high_confidence_known_place_intent",
                "retry_count": 0,
                "call_count": 0,
                "validation_errors": [],
            },
        },
    }


def _local_rule_out_of_scope_plan(raw_query, *, reason="not_place_recommendation"):
    return {
        "action": "out_of_scope",
        "decision_action": "out_of_scope",
        "can_search_now": False,
        "normalized_query": _clean_text(raw_query, 500),
        "frame": {
            "location_mode": "current_context",
            "anchor_location": "",
            "target_objects": [],
            "candidate_place_types": [],
            "result_match_terms": [],
            "constraints": [],
            "exclusions": [],
            "candidate_category_codes": [],
            "ranking_policy": "evidence_first",
            "primary_search_queries": [],
            "secondary_search_queries": [],
        },
        "clarification": {},
        "confidence": 0.92,
        "ai_retry_count": 0,
        "ai_debug": {
            "planner": {
                "status": "local_rule",
                "reason": reason,
                "retry_count": 0,
                "call_count": 0,
                "validation_errors": [],
            },
        },
    }


def _local_rule_clarification_plan(raw_query, *, question, options, missing_fields, expected_patch_fields):
    anchor_location = _local_rule_anchor_location(raw_query)
    location_mode = "explicit" if anchor_location else "current_context"
    return {
        "action": "ask_clarification",
        "decision_action": "ask_clarification",
        "can_search_now": False,
        "normalized_query": _clean_text(raw_query, 500),
        "frame": {
            "location_mode": location_mode,
            "anchor_location": anchor_location,
            "target_objects": [],
            "candidate_place_types": [],
            "result_match_terms": [],
            "constraints": [],
            "exclusions": [],
            "candidate_category_codes": [],
            "ranking_policy": "evidence_first",
            "primary_search_queries": [],
            "secondary_search_queries": [],
        },
        "clarification": {
            "question": question,
            "options": options,
            "missing_fields": missing_fields,
            "expected_patch_fields": expected_patch_fields,
        },
        "confidence": 0.86,
        "ai_retry_count": 0,
        "ai_debug": {
            "planner": {
                "status": "local_rule",
                "reason": "high_confidence_known_place_intent_needs_clarification",
                "retry_count": 0,
                "call_count": 0,
                "validation_errors": [],
            },
        },
    }


def _local_rule_plan_for_known_intent(raw_query):
    text = _clean_text(raw_query, 500)
    if not text:
        return None

    if _has_any(text, [
        "\uc57d\uad6d",
        "\uc9c4\ud1b5\uc81c",
        "\uc18c\ud654\uc81c",
        "\uc57d \uc0b4",
        "\uc57d\uc0ac",
        "\ub450\ud1b5",
        "\uba38\ub9ac \uc544",
        "\uba38\ub9ac\uc544",
        "\uc18d\uc774 \uc548",
        "\uc18d \uc548",
        "\uc18d\uc548",
        "\ubc30 \uc544",
        "\ubc30\uc544",
        "\ubc30\ud0c8",
    ]):
        return _local_rule_search_plan(
            text,
            normalized_query="\uc57d\uad6d",
            target_objects=["\uc57d\uad6d"],
            candidate_place_types=["\uc57d\uad6d"],
            result_match_terms=["\uc57d\uad6d", "\uc57d", "\uc9c4\ud1b5\uc81c", "\uc18c\ud654\uc81c"],
            primary_search_queries=["\uc57d\uad6d", "\uc57c\uac04 \uc57d\uad6d", "24\uc2dc \uc57d\uad6d"],
            constraints=["\uac00\uae4c\uc6b4 \uacf3"],
            candidate_category_codes=["pharmacy"],
            ranking_policy="urgent_nearest",
        )

    broad_place_request = _has_any(text, [
        "\uc88b\uc740 \uacf3",
        "\uc88b\uc740\uacf3",
        "\uad1c\ucc2e\uc740 \uacf3",
        "\uad1c\ucc2e\uc740\uacf3",
        "\uac08\ub9cc\ud55c \uacf3",
        "\uac08\ub9cc\ud55c\uacf3",
        "\uac00\ubcfc\ub9cc\ud55c \uacf3",
        "\uc5b4\ub514 \uac00\uc9c0",
        "\uc5b4\ub514\uac00\uc9c0",
        "\uc5b4\ub514 \uac00\uba74 \uc88b",
        "\uc5b4\ub514\uac00\uba74\uc88b",
        "\uc544\ubb34\ub370\ub098",
    ])
    broad_place_has_specific_target = _has_any(text, [
        "\uce74\ud398",
        "\ucee4\ud53c",
        "\ubc25",
        "\uc2dd\ub2f9",
        "\ub9db\uc9d1",
        "\ud654\uc7a5\uc2e4",
        "\uc1fc\ud551",
        "\ubc31\ud654\uc810",
        "\uc544\uc6b8\ub81b",
        "\uc804\uc2dc",
        "\ubc15\ubb3c\uad00",
        "\ubbf8\uc220\uad00",
        "\uc2e4\ub0b4",
        "\uccb4\ud5d8",
        "\uc0b0\ucc45",
        "\uc57d\uad6d",
        "\ud761\uc5f0",
        "\uc8fc\ucc28",
        "\ub178\ub798",
    ])
    if broad_place_request and not broad_place_has_specific_target:
        return _local_rule_clarification_plan(
            text,
            question="\uc5b4\ub5a4 \ubaa9\uc801\uc758 \uc7a5\uc18c\ub97c \ucc3e\uc744\uae4c\uc694?",
            options=[
                {"label": "\uc2dd\uc0ac/\ub9db\uc9d1", "value": "\uc2dd\uc0ac"},
                {"label": "\uce74\ud398/\ud734\uc2dd", "value": "\uce74\ud398"},
                {"label": "\uc0b0\ucc45/\uacf5\uc6d0", "value": "\uc0b0\ucc45"},
                {"label": "\uc1fc\ud551/\ubc31\ud654\uc810", "value": "\uc1fc\ud551"},
                {"label": "\uc2e4\ub0b4 \uccb4\ud5d8/\uc804\uc2dc", "value": "\uc2e4\ub0b4 \uccb4\ud5d8"},
            ],
            missing_fields=["target_objects"],
            expected_patch_fields=["target_objects", "candidate_place_types", "primary_search_queries"],
        )

    if _has_any(text, ["\ubcf4\ub4dc\uac8c\uc784", "\ubcf4\ub4dc \uac8c\uc784"]):
        return _local_rule_search_plan(
            text,
            normalized_query="\ubcf4\ub4dc\uac8c\uc784\uce74\ud398",
            target_objects=["\ubcf4\ub4dc\uac8c\uc784\uce74\ud398"],
            candidate_place_types=["\ubcf4\ub4dc\uac8c\uc784\uce74\ud398", "\uc2e4\ub0b4 \ub180\uac70\ub9ac"],
            result_match_terms=["\ubcf4\ub4dc\uac8c\uc784", "\ubcf4\ub4dc\uce74\ud398", "\ubcf4\ub4dc\uac8c\uc784\uce74\ud398"],
            primary_search_queries=["\ubcf4\ub4dc\uac8c\uc784\uce74\ud398", "\ubcf4\ub4dc\uac8c\uc784 \uce74\ud398"],
            constraints=[],
            exclusions=[],
            ranking_policy="evidence_first",
        )

    if (
        _has_any(text, ["\uc2e4\ub0b4 \uccb4\ud5d8", "\uc2e4\ub0b4\uccb4\ud5d8"])
        or (
            _has_any(text, ["\uc2e4\ub0b4"])
            and _has_any(text, ["\uccb4\ud5d8", "\uc544\uc774\ub791", "\uc544\uc774\uc640", "\ub180", "\uc561\ud2f0\ube44\ud2f0"])
        )
    ):
        return _local_rule_search_plan(
            text,
            normalized_query="\uc2e4\ub0b4 \uccb4\ud5d8",
            target_objects=["\uc2e4\ub0b4 \uccb4\ud5d8"],
            candidate_place_types=[
                "\ud0a4\uc988\uce74\ud398",
                "\ubcf4\ub4dc\uac8c\uc784\uce74\ud398",
                "\ub9cc\ud654\uce74\ud398",
                "\ubc29\ud0c8\ucd9c",
                "\uacf5\ubc29",
                "VR \uccb4\ud5d8\uad00",
                "\ubc15\ubb3c\uad00",
                "\uc804\uc2dc\uad00",
            ],
            result_match_terms=[
                "\uc2e4\ub0b4 \uccb4\ud5d8",
                "\ud0a4\uc988",
                "\uccb4\ud5d8",
                "\ubc29\ud0c8\ucd9c",
                "\ubcf4\ub4dc\uac8c\uc784",
                "\ub9cc\ud654\uce74\ud398",
                "\uacf5\ubc29",
                "VR",
                "\ubc15\ubb3c\uad00",
                "\uc804\uc2dc",
            ],
            primary_search_queries=[
                "\ud0a4\uc988\uce74\ud398",
                "\uc2e4\ub0b4 \uccb4\ud5d8",
                "\ubc29\ud0c8\ucd9c",
                "\ubcf4\ub4dc\uac8c\uc784\uce74\ud398",
                "\ubc15\ubb3c\uad00",
                "\uc804\uc2dc\uad00",
            ],
            constraints=[],
            exclusions=["\uc57c\uc678 \uc0b0\ucc45 \uc81c\uc678", "\uacf5\uc6d0 \uc81c\uc678", "\uc2dc\uc7a5 \uc81c\uc678"],
            ranking_policy="evidence_first",
        )

    if _has_any(text, ["\ubc30\ud130\ub9ac", "\ucf58\uc13c\ud2b8", "\ud734\ub300\ud3f0 \ucda9\uc804", "\ucda9\uc804\ud558\uac70\ub098", "\ucda9\uc804\ud560"]):
        return _local_rule_search_plan(
            text,
            normalized_query="\ucf58\uc13c\ud2b8/\ucda9\uc804 \uac00\ub2a5\ud55c \uc7a5\uc18c",
            target_objects=["\ucf58\uc13c\ud2b8 \uc788\ub294 \uce74\ud398"],
            candidate_place_types=["\uce74\ud398", "\uacf5\uacf5\ub3c4\uc11c\uad00", "\ucf54\uc6cc\ud0b9\uc2a4\ud398\uc774\uc2a4"],
            result_match_terms=["\uce74\ud398", "\ucf58\uc13c\ud2b8", "\ub178\ud2b8\ubd81", "\uc640\uc774\ud30c\uc774", "\ub3c4\uc11c\uad00"],
            primary_search_queries=["\ucf58\uc13c\ud2b8 \uce74\ud398", "\ub178\ud2b8\ubd81 \uce74\ud398", "\uce74\ud398", "\uacf5\uacf5\ub3c4\uc11c\uad00"],
            constraints=[],
            exclusions=["\uc804\uae30\ucc28 \ucda9\uc804\uc18c \uc81c\uc678", "\uc8fc\uc720\uc18c/LPG \ucda9\uc804\uc18c \uc81c\uc678", "\uc8fc\ucc28\uc7a5 \uc81c\uc678"],
            candidate_category_codes=["cafe"],
            ranking_policy="evidence_first",
        )

    if (
        _has_any(text, ["\ube44", "\ube44 \uc624", "\ube44\uc624", "\ub354\uc6cc", "\ub354\uc6b4", "\ucd94\uc6cc", "\ucd94\uc6b4"])
        and _has_any(text, ["\uc26c", "\uc274", "\uc26c\uace0", "\uc26c\uc5b4", "\ud53c\ud560", "\ud53c\ud574", "\uc7a0\uae50"])
    ):
        return _local_rule_search_plan(
            text,
            normalized_query="\uc7a0\uae50 \uc26c\uc5b4\uac08 \uc2e4\ub0b4 \uc7a5\uc18c",
            target_objects=["\uc2e4\ub0b4 \uc26c\uc5b4\uac08 \uacf3"],
            candidate_place_types=["\uce74\ud398", "\uacf5\uacf5\ub3c4\uc11c\uad00", "\uc1fc\ud551\ubab0", "\uc9c0\ud558\uc0c1\uac00"],
            result_match_terms=["\uce74\ud398", "\ub3c4\uc11c\uad00", "\uc1fc\ud551\ubab0", "\uc9c0\ud558\uc0c1\uac00", "\uc2e4\ub0b4"],
            primary_search_queries=["\uce74\ud398", "\uacf5\uacf5\ub3c4\uc11c\uad00", "\uc1fc\ud551\ubab0", "\uc9c0\ud558\uc0c1\uac00"],
            constraints=[],
            exclusions=["\ub178\uc778\ud68c\uad00 \uc81c\uc678", "\uacbd\ub85c\ub2f9 \uc81c\uc678", "\uc0c1\ub2f4\uc13c\ud130 \uc81c\uc678", "\uc8fc\ucc28\uc7a5 \uc81c\uc678"],
            candidate_category_codes=["cafe", "shopping"],
            ranking_policy="evidence_first",
        )

    weather_info_request = (
        _has_any(text, ["날씨", "기온", "비 와", "비와", "눈 와", "눈와"])
        and _has_any(text, ["어때", "알려", "예보", "몇 도", "몇도"])
        and not _has_any(text, ["피할 곳", "피할곳", "쉴 곳", "쉴곳", "갈 곳", "갈곳", "장소", "추천"])
    )
    if weather_info_request:
        return _local_rule_out_of_scope_plan(text, reason="weather_information_question")

    toilet_request = _has_any(text, ["화장실", "화장싷", "공중화장실", "개방화장실", "똥", "소변", "마려"])
    if toilet_request:
        urgent = _has_any(text, ["급해", "급한", "바로", "마려", "똥", "소변"])
        return _local_rule_search_plan(
            text,
            normalized_query="공중화장실",
            target_objects=["화장실"],
            candidate_place_types=["공중화장실", "개방화장실", "화장실"],
            result_match_terms=["화장실", "공중화장실", "개방화장실"],
            primary_search_queries=["공중화장실", "개방화장실", "화장실"],
            constraints=["긴급", "가까운 곳"] if urgent else ["가까운 곳"],
            exclusions=[],
            candidate_category_codes=["toilet"],
            ranking_policy="urgent_nearest" if urgent else "distance_first",
        )

    parking_request = _has_any(text, ["차 세울", "차세울", "주차할", "주차장", "공영주차", "주차타워"])
    parking_excluded = any(
        marker in _compact(text)
        for marker in ["주차장빼", "주차장제외", "주차빼", "주차제외", "주차장은빼"]
    )
    if parking_request and not parking_excluded:
        return _local_rule_search_plan(
            text,
            normalized_query="주차장",
            target_objects=["주차장"],
            candidate_place_types=["공영주차장", "유료주차장", "주차타워"],
            result_match_terms=["주차장", "공영주차장", "유료주차장", "주차타워"],
            primary_search_queries=["주차장", "공영주차장", "주차타워"],
            candidate_category_codes=["parking"],
            ranking_policy="urgent_nearest",
        )

    if _has_any(text, ["비 오", "비오", "비 와", "비와", "더워", "덥", "추워", "춥", "쉴 곳", "쉴곳", "쉬어갈", "쉬어 갈", "잠깐 쉴"]):
        if _has_any(text, ["피할 곳", "피할곳", "쉴 곳", "쉴곳", "쉬어갈", "쉬어 갈", "잠깐 쉴", "실내"]):
            return _local_rule_search_plan(
                text,
                normalized_query="잠깐 쉴 실내 장소",
                target_objects=["쉴 곳"],
                candidate_place_types=["카페", "공공도서관", "실내 쉼터", "쇼핑몰", "지하철역"],
                result_match_terms=["카페", "도서관", "쉼터", "쇼핑몰", "지하철역", "실내"],
                primary_search_queries=["카페", "공공도서관", "실내 쉼터", "쇼핑몰"],
                constraints=["잠깐 쉬기", "실내 또는 비 피할 수 있음"],
                exclusions=["유료 주차장 제외", "사유지 접근 제한 제외"],
                candidate_category_codes=["cafe", "shelter", "shopping"],
            )

    if _has_any(text, ["흡연구역", "흡연장", "흡연실", "흡연", "담배필", "담배 필", "담배피", "담배 피", "담배"]):
        outdoor = _has_any(text, ["실외", "외부", "밖", "야외", "옥외"])
        indoor = _has_any(text, ["실내", "안", "내부", "건물"])
        constraints = ["가까운 곳"]
        exclusions = []
        if outdoor:
            constraints.append("실외")
            exclusions.append("실내 제외")
        elif indoor:
            constraints.append("실내")
            exclusions.append("실외 제외")
        return _local_rule_search_plan(
            text,
            normalized_query="흡연구역",
            target_objects=["흡연구역"],
            candidate_place_types=["흡연구역", "흡연실", "실외흡연구역", "실내흡연실"],
            result_match_terms=["흡연구역", "흡연실", "흡연"],
            primary_search_queries=["흡연구역", "흡연실"],
            constraints=constraints,
            exclusions=exclusions,
            candidate_category_codes=["smoking_area"],
            ranking_policy="distance_first",
        )

    if _has_any(text, ["노래방", "코인노래방", "노래 부를", "노래부를", "노래 부르", "노래부르", "노래 한 곡", "노래한곡"]):
        return _local_rule_search_plan(
            text,
            normalized_query="노래방",
            target_objects=["노래방"],
            candidate_place_types=["노래방", "코인노래방"],
            result_match_terms=["노래방", "코인노래방"],
            primary_search_queries=["노래방", "코인노래방"],
            candidate_category_codes=["karaoke"],
        )

    bar_or_pub_excluded = any(
        marker in _compact(text)
        for marker in ["술집말고", "술집제외", "주점말고", "주점제외", "바말고", "바제외"]
    )
    if bar_or_pub_excluded and _has_any(text, ["카페", "커피"]):
        return _local_rule_search_plan(
            text,
            normalized_query="조용히 대화하기 좋은 카페",
            target_objects=["카페"],
            candidate_place_types=["카페"],
            result_match_terms=["카페", "커피", "조용", "대화"],
            primary_search_queries=["조용한 카페", "카페"],
            constraints=["조용히 대화하기 좋음"],
            exclusions=["술집 제외", "시끄러운 장소 제외"],
            candidate_category_codes=["cafe"],
        )

    if _has_any(text, ["술집", "술 마", "술마", "주점", "와인바", "칵테일바", "펍", "호프", "bar"]):
        return _local_rule_search_plan(
            text,
            normalized_query="술집/바",
            target_objects=["술집"],
            candidate_place_types=["술집", "주점", "펍", "와인바", "칵테일바"],
            result_match_terms=["술집", "주점", "펍", "와인바", "칵테일바", "호프"],
            primary_search_queries=["술집", "주점", "펍", "와인바"],
        )

    if _has_any(text, ["회식", "단체 식사", "단체식사", "단체로 밥", "단체 밥", "모임 식사", "모임장소", "모임 장소"]):
        return _local_rule_search_plan(
            text,
            normalized_query="회식/단체 식사 장소",
            target_objects=["회식 장소"],
            candidate_place_types=["고기집", "삼겹살", "갈비", "횟집", "단체석 식당", "식당"],
            result_match_terms=["회식", "단체", "단체석", "식당", "음식점", "고기", "삼겹살", "갈비", "한우", "횟집"],
            primary_search_queries=["삼겹살", "고기집", "갈비", "횟집"],
            constraints=["단체 식사", "회식에 적합"],
            candidate_category_codes=["restaurant"],
        )

    if _has_any(text, ["쇼핑몰", "쇼핑할", "쇼핑 할", "쇼핑", "백화점", "아울렛", "복합쇼핑", "쇼핑센터", "상업시설"]):
        return _local_rule_search_plan(
            text,
            normalized_query="쇼핑몰/백화점",
            target_objects=["쇼핑몰"],
            candidate_place_types=["쇼핑몰", "백화점", "아울렛", "복합쇼핑몰", "쇼핑센터", "대형마트"],
            result_match_terms=["쇼핑몰", "백화점", "아울렛", "복합쇼핑몰", "쇼핑센터", "대형마트"],
            primary_search_queries=["쇼핑몰", "백화점", "아울렛", "복합쇼핑몰", "쇼핑센터"],
            candidate_category_codes=["shopping"],
        )

    if _has_any(text, ["쌀국수", "분짜", "반미", "베트남음식", "베트남 음식", "베트남식"]):
        return _local_rule_search_plan(
            text,
            normalized_query="쌀국수/베트남 음식점",
            target_objects=["쌀국수"],
            candidate_place_types=["쌀국수 전문점", "베트남 음식점", "아시아 음식점", "식당"],
            result_match_terms=["쌀국수", "베트남음식", "베트남 음식", "포"],
            primary_search_queries=["쌀국수", "베트남 음식점", "베트남음식"],
            constraints=["식사 가능"],
            candidate_category_codes=["restaurant"],
        )

    if _has_any(text, ["돈까스", "돈가스", "카츠", "카츠동"]):
        return _local_rule_search_plan(
            text,
            normalized_query="돈까스",
            target_objects=["돈까스"],
            candidate_place_types=["돈까스 전문점", "일식당", "식당"],
            result_match_terms=["돈까스", "돈가스", "카츠", "일식"],
            primary_search_queries=["돈까스", "돈가스", "일식 돈까스"],
            constraints=["식사 가능"],
            candidate_category_codes=["restaurant"],
        )

    if _has_any(text, ["파스타", "스파게티", "이탈리안", "이탈리아 음식", "이탈리"]):
        return _local_rule_search_plan(
            text,
            normalized_query="파스타",
            target_objects=["파스타"],
            candidate_place_types=["이탈리안 레스토랑", "양식당", "식당"],
            result_match_terms=["파스타", "스파게티", "이탈리안", "양식"],
            primary_search_queries=["파스타", "이탈리안 레스토랑", "양식"],
            constraints=["식사 가능"],
            candidate_category_codes=["restaurant"],
        )

    if _has_any(text, ["전시", "전시회", "전시관", "전시장", "박물관", "미술관", "갤러리"]):
        return _local_rule_search_plan(
            text,
            normalized_query="전시/박물관",
            target_objects=["전시관"],
            candidate_place_types=["전시관", "박물관", "미술관", "갤러리"],
            result_match_terms=["전시관", "전시장", "전시회", "박물관", "미술관", "갤러리"],
            primary_search_queries=["전시관", "박물관", "미술관", "갤러리"],
        )

    has_indoor = _has_any(text, ["실내", "실내체험", "실내 체험", "실내액티비티", "실내 액티비티", "indoor", "indoors"])
    has_experience = _has_any(text, [
        "체험",
        "액티비티",
        "놀거리",
        "놀 거리",
        "도예",
        "공예",
        "vr",
        "브이알",
        "방탈출",
        "보드게임",
        "클라이밍",
        "만화카페",
        "키즈카페",
    ])
    if has_indoor and has_experience:
        return _local_rule_search_plan(
            text,
            normalized_query="실내 체험",
            target_objects=["실내 체험"],
            candidate_place_types=[
                "보드게임카페",
                "만화카페",
                "방탈출카페",
                "공방",
                "VR 체험관",
                "도예 체험 스튜디오",
                "실내 클라이밍",
            ],
            result_match_terms=["실내 체험", "보드게임카페", "만화카페", "방탈출", "공방", "VR", "도예", "공예", "클라이밍"],
            primary_search_queries=["보드게임카페", "만화카페", "방탈출", "공방", "VR"],
            constraints=["실내", "체험 활동"],
            exclusions=["야외 산책 제외", "공원 제외", "시장 제외"],
        )

    if _has_any(text, ["놀거리", "놀 거리", "액티비티", "뭐하지", "뭐 하지", "심심"]):
        return _local_rule_clarification_plan(
            text,
            question="원하시는 놀거리 유형을 골라 주세요.",
            options=[
                {"label": "실내 체험", "value": "실내 체험"},
                {"label": "영화관/공연장", "value": "영화관/공연장"},
                {"label": "전시/박물관", "value": "전시/박물관"},
                {"label": "야외 산책", "value": "야외 산책"},
            ],
            missing_fields=["activity_type"],
            expected_patch_fields=["target_objects", "candidate_place_types", "primary_search_queries"],
        )

    if (
        _has_any(text, ["실내"])
        and _has_any(text, ["산책", "걷기", "걸을"])
        and _has_any(text, ["야외 말고", "야외말고", "야외 제외", "야외제외", "밖 말고", "밖말고"])
    ):
        return _local_rule_clarification_plan(
            text,
            question="실내에서 걷고 싶은 곳을 찾으시나요, 아니면 야외 산책을 제외한 실내 활동을 찾으시나요?",
            options=[
                {"label": "실내 걷기 좋은 곳", "value": "실내 걷기"},
                {"label": "실내 체험/전시", "value": "실내 체험"},
                {"label": "쇼핑몰/지하상가", "value": "쇼핑몰"},
            ],
            missing_fields=["indoor_walk_or_activity"],
            expected_patch_fields=["target_objects", "candidate_place_types", "primary_search_queries"],
        )

    if _has_any(text, ["산책", "걷기", "걸을", "머리 식힐", "머리식힐", "바람 쐴", "바람쐴"]):
        return _local_rule_search_plan(
            text,
            normalized_query="산책하기 좋은 곳",
            target_objects=["산책할 곳"],
            candidate_place_types=["공원", "산책로", "해변 산책로", "하천 산책로"],
            result_match_terms=["공원", "산책로", "해변", "강변", "하천", "둘레길"],
            primary_search_queries=["공원", "산책로", "해변 산책로"],
            constraints=["걷기 좋음"],
            candidate_category_codes=["city_park", "beach", "tourism"],
            ranking_policy="distance_first",
        )

    if _has_any(text, ["기다리", "기다림", "친구 기다", "시간 보낼", "시간보낼", "잠깐 앉", "앉아서", "시끄럽지 않"]):
        return _local_rule_search_plan(
            text,
            normalized_query="잠깐 앉아 쉴 곳",
            target_objects=["잠깐 앉아 쉴 곳"],
            candidate_place_types=["카페", "북카페", "공공도서관", "실내 쉼터"],
            result_match_terms=["카페", "북카페", "도서관", "쉼터", "조용", "좌석"],
            primary_search_queries=["조용한 카페", "북카페", "도서관"],
            constraints=["잠깐 앉기", "너무 시끄럽지 않음"],
            exclusions=["스터디/공간대여 제외", "예약 필수 장소 제외"],
            candidate_category_codes=["cafe", "shelter"],
        )

    if _has_any(text, ["무료 와이파이", "공공 와이파이", "와이파이 되는", "와이파이 쓸", "wifi", "wi-fi"]):
        return _local_rule_search_plan(
            text,
            normalized_query="와이파이 가능한 방문 장소",
            target_objects=["와이파이 가능한 방문 장소"],
            candidate_place_types=["카페", "공공도서관", "터미널", "쇼핑몰"],
            result_match_terms=["와이파이", "Wi-Fi", "카페", "도서관", "터미널", "쇼핑몰"],
            primary_search_queries=["카페", "공공도서관", "터미널", "쇼핑몰"],
            constraints=["와이파이 이용 가능"],
            candidate_category_codes=["cafe", "shopping"],
        )

    if _has_any(text, ["약국", "두통", "머리 아", "머리아", "진통제", "약 살", "약사"]):
        return _local_rule_search_plan(
            text,
            normalized_query="약국",
            target_objects=["약국"],
            candidate_place_types=["약국"],
            result_match_terms=["약국", "약", "진통제"],
            primary_search_queries=["약국", "야간 약국", "24시 약국"],
            constraints=["가까운 곳"],
            candidate_category_codes=["pharmacy"],
            ranking_policy="urgent_nearest",
        )

    if _has_any(text, ["배고파", "배고픈", "배고프", "출출", "허기", "뭐 먹", "뭐먹", "밥 먹", "밥먹", "밥 먹을", "밥먹을"]):
        return _local_rule_search_plan(
            text,
            normalized_query="식당/맛집",
            target_objects=["식당"],
            candidate_place_types=["식당", "음식점", "맛집"],
            result_match_terms=["식당", "음식점", "맛집", "밥"],
            primary_search_queries=["식당", "맛집", "음식점"],
            candidate_category_codes=["restaurant"],
        )

    compact_text = _compact(text)
    study_cafe_excluded = "스터디카페" in compact_text and any(
        marker in compact_text for marker in ["말고", "빼", "제외", "빼고"]
    )
    has_cafe = _has_any(text, ["카페", "커피"])
    has_drink = _has_any(text, ["음료", "커피", "차 마", "차마", "마실", "마시"])
    has_work = (
        _has_any(text, ["작업", "공부", "노트북", "놋북", "카공", "콘센트"])
        or (_has_any(text, ["스터디"]) and not study_cafe_excluded)
    )
    if has_cafe and has_work:
        return _local_rule_search_plan(
            text,
            normalized_query="작업/공부 카페",
            target_objects=["카페"],
            candidate_place_types=["카페", "작업 카페", "스터디카페"],
            result_match_terms=["카페", "노트북", "콘센트", "와이파이", "작업"],
            primary_search_queries=["작업 카페", "노트북 카페", "콘센트 카페", "카페"],
            constraints=[],
            candidate_category_codes=["cafe"],
        )
    if has_cafe and has_drink and not has_work:
        return _local_rule_search_plan(
            text,
            normalized_query="음료 마실 카페",
            target_objects=["카페"],
            candidate_place_types=["카페"],
            result_match_terms=["카페", "커피", "음료"],
            primary_search_queries=["카페", "커피", "음료 카페"],
            constraints=["음료 마실 수 있음"],
            exclusions=["스터디카페 제외", "스터디룸 제외", "공간대여 제외"],
        )
    if has_cafe and not has_work:
        return _local_rule_search_plan(
            text,
            normalized_query="카페",
            target_objects=["카페"],
            candidate_place_types=["카페"],
            result_match_terms=["카페", "커피", "음료"],
            primary_search_queries=["카페", "커피"],
            constraints=["가까운 곳"],
            candidate_category_codes=["cafe"],
        )

    if _has_any(text, ["목마", "목 마", "물 마", "물마", "음료수", "마실거", "마실 것"]):
        wants_water = _has_any(text, ["물 마", "물마", "물", "생수"])
        drink_queries = (
            ["편의점", "카페", "음료 카페"]
            if wants_water
            else ["카페", "음료 카페", "편의점"]
        )
        return _local_rule_search_plan(
            text,
            normalized_query="음료 살 곳",
            target_objects=["음료 살 곳"],
            candidate_place_types=["카페", "편의점", "음료 매장"],
            result_match_terms=["카페", "편의점", "커피", "음료", "물"],
            primary_search_queries=drink_queries,
            constraints=["음료 구매 가능", "가까운 곳"],
            candidate_category_codes=["cafe"],
            ranking_policy="evidence_first",
        )

    return None


def _broad_frame_terms():
    return {
        "place",
        "places",
        "somewhere",
        "recommendation",
        "spot",
        "place to go",
        "things to do",
        "\uc7a5\uc18c",
        "\ucd94\ucc9c\uc7a5\uc18c",
        "\uac08\ub9cc\ud55c\uacf3",
        "\uac08\ub9cc\ud55c\ub370",
        "\uac00\ubcfc\ub9cc\ud55c\uacf3",
        "\uc5b4\ub514",
        "\uc5b4\ub518\uac00",
        "\uacf3",
        "\uacf5\uac04",
        "장소",
        "추천장소",
        "어디",
        "어딘가",
        "갈만한곳",
        "갈만한데",
        "곳",
        "공간",
    }


def _is_broad_term(value):
    compact = _compact(value)
    if not compact:
        return False
    broad = {_compact(item) for item in _broad_frame_terms()}
    if compact in broad:
        return True
    return any(item and len(item) >= 4 and item in compact for item in broad)


def _normalize_frame(raw_frame):
    raw_frame = raw_frame if isinstance(raw_frame, dict) else {}
    ranking_policy = _clean_text(raw_frame.get("ranking_policy") or raw_frame.get("rankingPolicy"))
    if ranking_policy not in ALLOWED_RANKING_POLICIES:
        ranking_policy = "evidence_first"

    location_mode = _clean_text(raw_frame.get("location_mode") or raw_frame.get("locationMode"))
    if location_mode not in {"explicit", "current_context", "clarification_required"}:
        location_mode = "current_context"

    return {
        "location_mode": location_mode,
        "anchor_location": _clean_text(raw_frame.get("anchor_location") or raw_frame.get("anchorLocation"), 80),
        "target_objects": _as_list(raw_frame.get("target_objects") or raw_frame.get("targetObjects")),
        "candidate_place_types": _as_list(
            raw_frame.get("candidate_place_types") or raw_frame.get("candidatePlaceTypes")
        ),
        "result_match_terms": _as_list(
            raw_frame.get("result_match_terms") or raw_frame.get("resultMatchTerms")
        ),
        "constraints": _as_list(raw_frame.get("constraints")),
        "exclusions": _as_list(raw_frame.get("exclusions")),
        "ranking_policy": ranking_policy,
        "primary_search_queries": _as_list(
            raw_frame.get("primary_search_queries")
            or raw_frame.get("primarySearchQueries")
            or raw_frame.get("search_queries")
            or raw_frame.get("searchQueries"),
            max_items=6,
            max_length=100,
        ),
        "secondary_search_queries": _as_list(
            raw_frame.get("secondary_search_queries") or raw_frame.get("secondarySearchQueries"),
            max_items=6,
            max_length=100,
        ),
    }


def _normalize_clarification(raw):
    raw = raw if isinstance(raw, dict) else {}
    return {
        "question": _clean_text(raw.get("question") or raw.get("clarification_question"), 300),
        "options": _as_list(raw.get("options") or raw.get("clarification_options"), max_items=5, max_length=80),
        "missing_fields": _as_list(raw.get("missing_fields") or raw.get("missingFields"), max_items=8),
        "expected_patch_fields": _as_list(
            raw.get("expected_patch_fields") or raw.get("expectedPatchFields"),
            max_items=8,
        ),
    }


def _is_raw_repeat_only(raw_query, frame):
    query_compact = _compact(raw_query)
    primary = frame.get("primary_search_queries") or []
    if not query_compact or len(primary) != 1:
        return False
    if _compact(primary[0]) != query_compact:
        return False
    evidence_terms = [
        *frame.get("target_objects", []),
        *frame.get("result_match_terms", []),
        *frame.get("candidate_place_types", []),
    ]
    return not any(_compact(term) and _compact(term) != query_compact for term in evidence_terms)


def _clarification_requests_place_target(clarification):
    text = _compact(" ".join([
        clarification.get("question", ""),
        *clarification.get("options", []),
        *clarification.get("missing_fields", []),
        *clarification.get("expected_patch_fields", []),
    ]))
    place_target_markers = {
        "target_objects",
        "targetobjects",
        "result_match_terms",
        "resultmatchterms",
        "candidate_place_types",
        "candidateplacetypes",
        "user_goal",
        "usergoal",
        "place",
        "destination",
        "\uc7a5\uc18c",
        "\ubaa9\uc801",
    }
    return any(_compact(marker) in text for marker in place_target_markers)


def _validate_plan(plan, raw_query="", lat=None, lng=None, map_center=None):
    errors = []
    action = plan.get("action")
    frame = plan.get("frame") if isinstance(plan.get("frame"), dict) else {}
    clarification = plan.get("clarification") if isinstance(plan.get("clarification"), dict) else {}

    if action not in ALLOWED_ACTIONS:
        errors.append("invalid_action")
        return errors

    if action == "search":
        if not frame.get("target_objects"):
            errors.append("missing_target_objects")
        if not frame.get("primary_search_queries"):
            errors.append("missing_primary_search_queries")
        if frame.get("location_mode") == "explicit" and not frame.get("anchor_location"):
            errors.append("missing_anchor_location")
        if frame.get("location_mode") == "clarification_required":
            errors.append("search_requires_location_clarification")
        if _is_raw_repeat_only(raw_query, frame):
            errors.append("raw_query_repeat_only")
        if all(_is_broad_term(term) for term in frame.get("target_objects", [])):
            errors.append("broad_target_only")

    if action == "ask_clarification" and not clarification.get("question"):
        errors.append("missing_clarification_question")
    if action == "ask_clarification":
        frame_terms = [
            *frame.get("target_objects", []),
            *frame.get("result_match_terms", []),
            *frame.get("candidate_place_types", []),
        ]
        if not frame_terms and not _clarification_requests_place_target(clarification):
            errors.append("non_place_clarification")

    if action in {"out_of_scope", "blocked"}:
        if frame.get("primary_search_queries") or frame.get("secondary_search_queries"):
            errors.append("non_search_action_contains_queries")

    if action == "search" and frame.get("location_mode") == "current_context":
        plan["has_current_coordinates"] = _has_coordinates(lat=lat, lng=lng, map_center=map_center)

    return errors


def _canonicalize(raw_plan, raw_query="", lat=None, lng=None, map_center=None):
    raw_plan = raw_plan if isinstance(raw_plan, dict) else {}
    frame = _normalize_frame(raw_plan.get("frame") or raw_plan.get("place_intent_frame") or {})
    clarification = _normalize_clarification(raw_plan.get("clarification") or raw_plan)
    action = _clean_text(raw_plan.get("action") or raw_plan.get("decision_action"))
    plan = {
        "action": action,
        "normalized_query": _clean_text(raw_plan.get("normalized_query") or raw_plan.get("normalizedQuery") or raw_query),
        "frame": frame,
        "clarification": clarification,
        "confidence": _to_float(raw_plan.get("confidence"), 0.0),
    }
    errors = _validate_plan(plan, raw_query=raw_query, lat=lat, lng=lng, map_center=map_center)
    return plan, errors


def _planner_payload(query, lat=None, lng=None, map_center=None, previous_context=None):
    previous_context = previous_context if isinstance(previous_context, dict) else {}
    return {
        "query": query,
        "current_coordinates": {
            "lat": lat,
            "lng": lng,
        },
        "map_center": map_center if isinstance(map_center, dict) else None,
        "previous_frame": previous_context.get("pending_clarification_frame")
        or previous_context.get("place_intent_frame")
        or previous_context.get("search_plan", {}).get("place_intent_frame")
        or previous_context.get("search_plan", {}).get("placeIntentFrame")
        or {},
        "pending_clarification_question": previous_context.get("clarification_question")
        or previous_context.get("question")
        or "",
        "clarification_answer": previous_context.get("clarification_answer") or "",
        "previous_user_query": previous_context.get("previous_user_query") or previous_context.get("original_query") or "",
        "last_resolved_location_context": previous_context.get("last_resolved_location_context") or {},
        "is_clarification_followup": bool(previous_context.get("is_clarification_followup")),
    }


def _is_ai_enabled():
    if getattr(settings, "CONVERSATIONAL_SEARCH_AI_ENABLED", False) is not True:
        return False, "conversational_search_ai_disabled"
    reason = get_ai_json_unavailable_reason()
    if reason:
        return False, reason
    return True, ""


def _call_planner(payload, *, repair=False, max_completion_tokens=900):
    prompt = AI_INTENT_REPAIR_SYSTEM_PROMPT if repair else AI_INTENT_SYSTEM_PROMPT
    return _call_ai_chat_json(
        query=json.dumps(payload, ensure_ascii=False),
        system_prompt=prompt,
        max_completion_tokens=max_completion_tokens,
        model=getattr(settings, "AI_INTENT_MODEL", getattr(settings, "GMS_MODEL", "gpt-5-mini")),
        timeout=getattr(settings, "AI_INTENT_TIMEOUT", getattr(settings, "AI_REQUEST_TIMEOUT", 20)),
        response_schema=AI_INTENT_PLAN_RESPONSE_SCHEMA,
        schema_name="ai_intent_plan",
    )


def _is_retryable_ai_error(exc):
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return bool(status_code and 500 <= status_code < 600)


def _unavailable(reason, retry_count=0, validation_errors=None, call_count=0):
    return {
        "action": "ai_unavailable",
        "decision_action": "ai_unavailable",
        "can_search_now": False,
        "normalized_query": "",
        "frame": {},
        "clarification": {},
        "confidence": 0.0,
        "ai_retry_count": retry_count,
        "validation_errors": validation_errors or [],
        "ai_fallback_reason": reason,
        "ai_debug": {
            "planner": {
                "status": "unavailable",
                "reason": reason,
                "validation_errors": validation_errors or [],
                "retry_count": retry_count,
                "call_count": call_count,
            }
        },
    }


def build_ai_intent_plan(query, *, lat=None, lng=None, map_center=None, previous_context=None):
    raw_query = _clean_text(query, 500)
    if not raw_query:
        return {
            "action": "ask_clarification",
            "decision_action": "ask_clarification",
            "can_search_now": False,
            "normalized_query": "",
            "frame": {},
            "clarification": {
                "question": "찾고 싶은 장소 상황을 조금 더 알려주세요.",
                "options": [],
                "missing_fields": ["user_goal"],
                "expected_patch_fields": ["target_objects"],
            },
            "confidence": 0.0,
            "ai_retry_count": 0,
            "ai_debug": {"planner": {"status": "empty_query"}},
        }

    local_plan = _local_rule_plan_for_known_intent(raw_query)
    if local_plan:
        return local_plan

    enabled, reason = _is_ai_enabled()
    if not enabled:
        return _unavailable(reason)

    payload = _planner_payload(
        raw_query,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )

    try:
        max_attempts = int(getattr(settings, "AI_SEARCH_INTENT_MAX_ATTEMPTS", 2) or 2)
    except (TypeError, ValueError):
        max_attempts = 2
    max_attempts = max(1, min(max_attempts, 3))

    raw_plan = None
    last_error = ""
    retry_count = 0
    ai_call_count = 0
    for attempt_index in range(max_attempts + 1):
        try:
            ai_call_count += 1
            raw_plan = _call_planner(payload)
            retry_count = attempt_index
            break
        except Exception as exc:
            logger.info("AI intent planner call failed.", exc_info=True)
            last_error = f"ai_call_failed:{exc.__class__.__name__}"
            retry_count = attempt_index + 1
            if not _is_retryable_ai_error(exc) or attempt_index >= max_attempts:
                break

    if not isinstance(raw_plan, dict):
        if last_error:
            return _unavailable(last_error, retry_count=retry_count, call_count=ai_call_count)
        return _unavailable("empty_ai_response", retry_count=retry_count, call_count=ai_call_count)

    plan, errors = _canonicalize(raw_plan, raw_query=raw_query, lat=lat, lng=lng, map_center=map_center)
    if not errors:
        return {
            **plan,
            "decision_action": plan["action"],
            "can_search_now": plan["action"] == "search",
            "ai_retry_count": retry_count,
            "ai_debug": {
                "planner": {
                    "status": "ok",
                    "retry_count": retry_count,
                    "call_count": ai_call_count,
                    "validation_errors": [],
                }
            },
        }

    repair_payload = {
        "original_payload": payload,
        "invalid_response": raw_plan,
        "validation_errors": errors,
    }
    try:
        ai_call_count += 1
        repaired_raw = _call_planner(repair_payload, repair=True, max_completion_tokens=700)
    except Exception as exc:
        logger.info("AI intent planner repair failed.", exc_info=True)
        return _unavailable(
            f"ai_schema_repair_failed:{exc.__class__.__name__}",
            retry_count=retry_count,
            validation_errors=errors,
            call_count=ai_call_count,
        )

    repaired_plan, repair_errors = _canonicalize(
        repaired_raw,
        raw_query=raw_query,
        lat=lat,
        lng=lng,
        map_center=map_center,
    )
    if repair_errors:
        return _unavailable(
            "ai_schema_repair_invalid",
            retry_count=retry_count,
            validation_errors=[*errors, *repair_errors],
            call_count=ai_call_count,
        )

    return {
        **repaired_plan,
        "decision_action": repaired_plan["action"],
        "can_search_now": repaired_plan["action"] == "search",
        "ai_retry_count": retry_count,
        "ai_debug": {
            "planner": {
                "status": "repaired",
                "retry_count": retry_count,
                "call_count": ai_call_count,
                "validation_errors": errors,
            }
        },
    }


def frame_with_sources(frame, source=TRUSTED_FRAME_SOURCE):
    frame = frame if isinstance(frame, dict) else {}

    def sourced(values):
        return [
            {
                "value": value,
                "source": source,
                "evidence_source": source,
            }
            for value in values or []
        ]

    return {
        **frame,
        "target_objects": sourced(frame.get("target_objects")),
        "targetObjects": sourced(frame.get("target_objects")),
        "candidate_place_types": sourced(frame.get("candidate_place_types")),
        "candidatePlaceTypes": sourced(frame.get("candidate_place_types")),
        "result_match_terms": sourced(frame.get("result_match_terms")),
        "resultMatchTerms": sourced(frame.get("result_match_terms")),
        "constraints": sourced(frame.get("constraints")),
        "exclusions": sourced(frame.get("exclusions")),
        "search_queries": sourced(frame.get("primary_search_queries")),
        "searchQueries": sourced(frame.get("primary_search_queries")),
        "primary_search_queries": sourced(frame.get("primary_search_queries")),
        "primarySearchQueries": sourced(frame.get("primary_search_queries")),
        "secondary_search_queries": sourced(frame.get("secondary_search_queries")),
        "secondarySearchQueries": sourced(frame.get("secondary_search_queries")),
    }


def to_search_plan(intent_plan, raw_query=""):
    frame = intent_plan.get("frame") if isinstance(intent_plan.get("frame"), dict) else {}
    sourced_frame = frame_with_sources(frame)
    action = intent_plan.get("action") or intent_plan.get("decision_action") or ""
    display_label = (
        (frame.get("target_objects") or [""])[0]
        or intent_plan.get("normalized_query")
        or raw_query
    )
    search_plan = {
        "originalQuery": raw_query,
        "original_query": raw_query,
        "normalizedQuery": intent_plan.get("normalized_query") or raw_query,
        "normalized_query": intent_plan.get("normalized_query") or raw_query,
        "targetQuery": display_label,
        "target_query": display_label,
        "locationQuery": frame.get("anchor_location") if frame.get("location_mode") == "explicit" else "",
        "location_query": frame.get("anchor_location") if frame.get("location_mode") == "explicit" else "",
        "baseLocationQuery": frame.get("anchor_location") if frame.get("location_mode") == "explicit" else "",
        "base_location_query": frame.get("anchor_location") if frame.get("location_mode") == "explicit" else "",
        "has_explicit_location": frame.get("location_mode") == "explicit",
        "location_resolution_required": frame.get("location_mode") == "explicit",
        "scenario": "ai_place_search",
        "decision_action": action,
        "decisionAction": action,
        "can_search_now": action == "search",
        "canSearchNow": action == "search",
        "parser_provider": "ai_intent_planner",
        "parser_fallback": False,
        "plan_source": "ai",
        "execution_mode": "ai_first_orchestrator",
        "ranking_policy": frame.get("ranking_policy") or "evidence_first",
        "rankingPolicy": frame.get("ranking_policy") or "evidence_first",
        "place_intent_frame": sourced_frame,
        "placeIntentFrame": sourced_frame,
        "target_objects": sourced_frame.get("target_objects", []),
        "candidate_place_types": sourced_frame.get("candidate_place_types", []),
        "result_match_terms": sourced_frame.get("result_match_terms", []),
        "constraints": sourced_frame.get("constraints", []),
        "exclusions": sourced_frame.get("exclusions", []),
        "search_queries": sourced_frame.get("search_queries", []),
        "searchQueries": sourced_frame.get("searchQueries", []),
        "primary_search_queries": sourced_frame.get("primary_search_queries", []),
        "secondary_search_queries": sourced_frame.get("secondary_search_queries", []),
        "ai_retry_count": intent_plan.get("ai_retry_count", 0),
    }
    clarification = intent_plan.get("clarification") if isinstance(intent_plan.get("clarification"), dict) else {}
    if action == "ask_clarification":
        search_plan["clarification_question"] = clarification.get("question", "")
        search_plan["clarification_options"] = clarification.get("options", [])
    return search_plan


def repair_search_queries(query, frame, *, candidate_counts=None):
    enabled, reason = _is_ai_enabled()
    if not enabled:
        return [], {"status": "skipped", "reason": reason}
    payload = {
        "query": query,
        "frame": frame,
        "candidate_counts": candidate_counts or {},
    }
    try:
        raw = _call_ai_chat_json(
            query=json.dumps(payload, ensure_ascii=False),
            system_prompt=AI_QUERY_REPAIR_SYSTEM_PROMPT,
            max_completion_tokens=220,
            model=getattr(settings, "AI_QUERY_REPAIR_MODEL", "gpt-5-nano"),
            timeout=getattr(settings, "AI_QUERY_REPAIR_TIMEOUT", getattr(settings, "AI_REQUEST_TIMEOUT", 20)),
            response_schema=AI_QUERY_REPAIR_RESPONSE_SCHEMA,
            schema_name="ai_query_repair",
        )
    except Exception as exc:
        logger.info("AI query repair failed.", exc_info=True)
        return [], {"status": "failed", "reason": f"ai_query_repair_failed:{exc.__class__.__name__}"}

    raw_queries = (raw or {}).get("queries") if isinstance(raw, dict) else []
    raw_queries = raw_queries if isinstance(raw_queries, list) else []
    filtered = []
    blocked = []
    generated = []
    blocked_relationships = {
        "generic_category_replacement",
        "generic_category",
        "broad_category",
        "broad_default",
        "unsupported",
        "unrelated",
    }

    def is_atomic_query(value):
        text = _clean_text(value, 100)
        if not text or len(text) > 28:
            return False, "query_too_long_or_empty"
        if QUERY_LIST_SEPARATOR_RE.search(text):
            return False, "multi_candidate_separator"
        compact_text = _compact(text)
        if "또는" in compact_text or "혹은" in compact_text or "그리고" in compact_text:
            return False, "multi_candidate_conjunction"
        if any(mark in text for mark in (":", "：", "(", ")", "[", "]")):
            return False, "explanatory_query"
        if len(text.split()) > 5:
            return False, "explanatory_query"
        return True, ""

    for item in raw_queries[:3]:
        if not isinstance(item, dict):
            blocked.append({
                "query": _clean_text(item, 100),
                "relationship": "missing_structured_contract",
                "preserves_target": False,
            })
            continue
        query_text = _clean_text(item.get("query"), 100)
        relationship = _clean_text(item.get("relationship"), 80).lower()
        preserves_target = item.get("preserves_target")
        if isinstance(preserves_target, str):
            preserves_target = preserves_target.strip().lower() in {"1", "true", "yes"}
        else:
            preserves_target = bool(preserves_target)
        row = {
            "query": query_text,
            "relationship": relationship,
            "preserves_target": preserves_target,
        }
        generated.append(row)
        is_atomic, atomic_reason = is_atomic_query(query_text)
        if not query_text or not preserves_target or relationship in blocked_relationships or not is_atomic:
            blocked.append({**row, "blocked_reason": atomic_reason or relationship or "does_not_preserve_target"})
            continue
        filtered.append(query_text)
    return filtered, {
        "status": "executed",
        "generated": generated,
        "accepted": filtered,
        "blocked": blocked,
        "call_count": 1,
    }
