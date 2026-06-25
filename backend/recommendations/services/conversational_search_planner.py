import json
import logging
import re

from django.conf import settings

from recommendations.services.ai_situation_parser import (
    ALLOWED_CATEGORIES,
    ALLOWED_SCENARIOS,
    ALLOWED_TAGS,
    _call_gms_chat_json,
)


logger = logging.getLogger(__name__)

CLARIFICATION_MESSAGE = "어느 지역이나 기준 위치에서 찾을지 알려주시면 더 정확히 찾아드릴게요."
PURPOSE_CLARIFICATION_MESSAGE = (
    "어떤 상황의 장소를 찾으시나요? 지역과 목적을 함께 입력해 주세요. "
    "예: 서면역 조용한 카페, 하단역 산책할 곳, 광안리 잠깐 쉴 곳"
)
REFINEMENT_CLARIFICATION_MESSAGE = (
    "이전 검색 결과가 없어서 어떤 장소를 다시 찾으려는지 알 수 없습니다. "
    "지역과 원하는 장소 종류를 함께 입력해 주세요. 예: 서면역 조용한 카페, 하단역 산책할 곳"
)
OUT_OF_SCOPE_MESSAGE = "이 서비스는 생활 장소 추천을 위한 서비스라 해당 질문은 도와드리기 어렵습니다."
BLOCKED_MESSAGE = "해당 요청은 안전상 안내하기 어렵습니다."
QUIET_PURPOSE_CLARIFICATION_MESSAGE = (
    "조용한 장소를 어떤 목적으로 찾으시나요? "
    "예: 쉬기, 공부/작업, 산책, 식사"
)
HEALTH_NEARBY_MESSAGE = (
    "증상에 대한 의학적 판단은 어렵지만, 가까운 약국이나 병원을 찾아드릴 수 있어요. "
    "증상이 심하거나 갑작스럽다면 응급 진료를 우선 고려해 주세요."
)

ROUTER_ACTIONS = {
    "search",
    "ask_clarification",
    "out_of_scope",
    "blocked",
    "refine_previous_search",
}

BROAD_FRAME_TERMS = {
    "장소",
    "추천장소",
    "추천장소",
    "추천 장소",
    "갈만한곳",
    "갈만한데",
    "갈곳",
    "갈데",
    "어디",
    "어디갈만한데",
    "어디갈만한곳",
    "할것",
    "할일",
    "뭐하지",
    "뭐할까",
    "심심",
    "심심함",
    "심심함해소",
    "좋은곳",
    "괜찮은곳",
    "무난한곳",
}

BROAD_FALLBACK_PLACE_TERMS = {
    "장소",
    "추천장소",
    "추천 장소",
    "공간",
    "갈만한곳",
    "갈만한 곳",
    "갈만한데",
    "갈만한 데",
    "카페",
    "쉼터",
    "cafe",
    "shelter",
}

BROAD_DEFAULT_PLACE_TERMS = {
    "카페",
    "쉼터",
    "cafe",
    "shelter",
    "restaurant",
    "식당",
    "음식점",
    "장소",
    "추천장소",
    "추천 장소",
    "갈만한곳",
    "갈만한 곳",
    "쉴곳",
    "쉴 곳",
}

BROAD_FRAME_CONFIDENCE_THRESHOLD = 0.58
BROAD_FRAME_LOW_CONFIDENCE_THRESHOLD = 0.5
BROAD_FRAME_CLARIFICATION_MESSAGE = "어떤 목적의 장소를 찾으시나요?"
BROAD_FRAME_CLARIFICATION_OPTIONS = ["쉬기", "먹기", "산책", "작업", "조용한 곳"]
DEFAULT_CLARIFICATION_OPTIONS = [
    "쉬는 곳",
    "식당/맛집",
    "산책/공원",
    "작업/공부 카페",
    "영화관/공연장",
    "쇼핑몰/백화점",
    "술집/바",
]

AI_SCENARIO_ALIASES = {
    "study_room": "work_cafe",
    "study_cafe": "work_cafe",
    "workspace": "work_cafe",
    "work_space": "work_cafe",
    "cafe_work": "work_cafe",
    "rest": "waiting_place",
    "rest_place": "waiting_place",
    "walking": "walk_healing",
    "walk": "walk_healing",
    "smoking": "smoking_area",
    "smoking_zone": "smoking_area",
}

LOCATION_SUFFIXES = (
    "특별자치시",
    "특별자치도",
    "광역시",
    "특별시",
    "해수욕장",
    "대학교",
    "공항",
    "터미널",
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

COMMAND_PATTERNS = [
    r"추천\s*해\s*줘",
    r"추천해줘",
    r"추천",
    r"찾아\s*줘",
    r"찾아줘",
    r"찾아",
    r"알려\s*줘",
    r"알려줘",
    r"좀",
]

MENU_KEYWORDS = [
    "소금빵",
    "브런치",
    "디저트",
    "쌀국수",
    "파스타",
    "돈까스",
    "돈가스",
    "커피",
    "빵",
]

PLACE_TYPE_KEYWORDS = {
    "소금빵": ["베이커리", "빵집", "카페"],
    "브런치": ["카페"],
    "디저트": ["카페", "베이커리", "빵집"],
    "쌀국수": ["식당", "음식점"],
    "파스타": ["식당", "음식점"],
    "돈까스": ["식당", "음식점"],
    "돈가스": ["식당", "음식점"],
    "커피": ["카페"],
    "빵": ["베이커리", "빵집", "카페"],
}

SCENARIO_RULES = [
    (
        "smoking_area",
        ["흡연구역", "흡연장", "흡연", "담배필", "담배 필", "담배피", "담배 피", "담배", "피울 수 있는 곳", "피울수있는곳"],
        ["smoking_area"],
        ["흡연구역"],
        ["실외흡연구역"],
    ),
    (
        "walk_healing",
        ["산책", "힐링", "걷", "야경", "전망", "공원", "바다", "해변"],
        ["city_park", "tourism", "beach"],
        ["공원", "산책로", "전망대"],
        ["산책좋음", "힐링"],
    ),
    (
        "work_cafe",
        ["작업", "노트북", "공부", "조용", "콘센트", "와이파이", "카페", "카공"],
        ["cafe"],
        ["카페", "작업 카페", "스터디카페"],
        ["조용한", "노트북작업", "콘센트있음", "와이파이"],
    ),
    (
        "waiting_place",
        ["잠깐", "잠시", "쉬", "쉴", "앉", "대기", "기다", "실내", "쉼터"],
        ["cafe", "shelter"],
        ["카페", "쉼터", "실내 쉼터"],
        ["잠깐쉬기좋음", "실내쉼터"],
    ),
    (
        "restaurant",
        ["맛집", "먹", "밥", "식사", "식당", "음식점", "브런치", "소금빵", "쌀국수", "디저트", "빵"],
        ["restaurant", "cafe"],
        ["식당", "카페"],
        ["식사가능"],
    ),
]

INTENT_GROUP_CONFIGS = {
    "quiet_rest_place": {
        "scenario": "waiting_place",
        "target_query": "조용히 쉴 곳",
        "categories": ["library", "public_library", "shelter", "city_park", "cafe"],
        "category_candidates": [
            {"name": "도서관", "weight": 0.9},
            {"name": "쉼터", "weight": 0.8},
            {"name": "공원", "weight": 0.7},
            {"name": "카페", "weight": 0.5},
        ],
        "conditions": ["조용함", "혼자 이용하기 좋음", "잠깐 쉬기 좋음"],
        "preferred_tags": ["조용한", "혼자이용좋음", "잠깐쉬기좋음"],
        "kakao_keywords": ["도서관", "쉼터", "공원", "조용한 공간", "카페"],
        "web_search_recommended": True,
    },
    "work_place": {
        "scenario": "work_cafe",
        "target_query": "카페",
        "categories": ["cafe", "library", "public_library", "study_cafe"],
        "category_candidates": [
            {"name": "카페", "weight": 0.9},
            {"name": "도서관", "weight": 0.8},
            {"name": "스터디카페", "weight": 0.7},
        ],
        "conditions": ["조용함", "노트북 작업 가능", "콘센트 있음", "혼자 이용하기 좋음"],
        "preferred_tags": ["조용한", "노트북작업", "콘센트있음", "와이파이", "혼자이용좋음"],
        "kakao_keywords": ["카페", "작업 카페", "스터디카페", "도서관"],
        "web_search_recommended": True,
    },
    "urgent_toilet": {
        "scenario": "waiting_place",
        "target_query": "공중화장실",
        "categories": [],
        "category_candidates": [
            {"name": "공중화장실", "weight": 1.0},
            {"name": "개방화장실", "weight": 0.8},
        ],
        "conditions": ["가까운 곳"],
        "preferred_tags": ["편의시설"],
        "kakao_keywords": ["공중화장실", "개방화장실", "화장실"],
        "web_search_recommended": False,
    },
    "health_nearby": {
        "scenario": "waiting_place",
        "target_query": "약국 또는 병원",
        "categories": [],
        "category_candidates": [
            {"name": "약국", "weight": 0.9},
            {"name": "병원", "weight": 0.8},
            {"name": "응급실", "weight": 0.4},
        ],
        "conditions": ["가까운 곳"],
        "preferred_tags": ["편의시설"],
        "kakao_keywords": ["약국", "병원", "내과", "응급실"],
        "web_search_recommended": True,
    },
    "parking_place": {
        "scenario": "waiting_place",
        "target_query": "주차장",
        "categories": [],
        "category_candidates": [
            {"name": "주차장", "weight": 1.0},
        ],
        "conditions": ["가까운 곳"],
        "preferred_tags": ["편의시설"],
        "kakao_keywords": ["주차장", "공영주차장"],
        "web_search_recommended": False,
    },
    "wifi_place": {
        "scenario": "work_cafe",
        "target_query": "무료 와이파이",
        "categories": ["cafe", "library", "public_library"],
        "category_candidates": [
            {"name": "공공 와이파이", "weight": 1.0},
            {"name": "카페", "weight": 0.5},
        ],
        "conditions": ["와이파이 있음"],
        "preferred_tags": ["와이파이"],
        "kakao_keywords": ["공공 와이파이", "무료 와이파이", "와이파이 카페", "도서관"],
        "web_search_recommended": False,
    },
    "weather_shelter": {
        "scenario": "waiting_place",
        "target_query": "쉴 곳",
        "categories": ["shelter", "library", "public_library", "cafe"],
        "category_candidates": [
            {"name": "쉼터", "weight": 0.9},
            {"name": "도서관", "weight": 0.7},
            {"name": "공공시설", "weight": 0.7},
            {"name": "카페", "weight": 0.4},
        ],
        "conditions": ["실내", "비 피하기 좋음", "더위 피하기 좋음", "잠깐 쉬기 좋음"],
        "preferred_tags": ["실내쉼터", "잠깐쉬기좋음"],
        "kakao_keywords": ["실내 쉼터", "무더위쉼터", "도서관", "공공시설", "카페"],
        "web_search_recommended": True,
    },
    "walk_healing": {
        "scenario": "walk_healing",
        "target_query": "산책할 곳",
        "categories": ["city_park", "beach", "tourism"],
        "category_candidates": [
            {"name": "산책로", "weight": 0.9},
            {"name": "공원", "weight": 0.8},
            {"name": "해변", "weight": 0.8},
            {"name": "광장", "weight": 0.6},
            {"name": "관광명소", "weight": 0.5},
        ],
        "conditions": ["산책하기 좋음", "걷기 좋음", "힐링하기 좋음"],
        "preferred_tags": ["산책좋음", "힐링"],
        "kakao_keywords": ["산책로", "공원", "해변", "전망대"],
        "web_search_recommended": True,
    },
    "smoking_area": {
        "scenario": "smoking_area",
        "target_query": "흡연구역",
        "categories": ["smoking_area"],
        "category_candidates": [
            {"name": "흡연구역", "weight": 1.0},
            {"name": "흡연실", "weight": 0.8},
        ],
        "conditions": [],
        "preferred_tags": ["실외흡연구역"],
        "kakao_keywords": ["흡연구역", "흡연실"],
        "web_search_recommended": False,
    },
    "entertainment_place": {
        "scenario": "waiting_place",
        "target_query": "영화관",
        "categories": [],
        "category_candidates": [
            {"name": "영화관", "weight": 1.0},
            {"name": "공연장", "weight": 0.85},
            {"name": "문화공간", "weight": 0.55},
        ],
        "conditions": [],
        "preferred_tags": [],
        "kakao_keywords": ["영화관", "공연장", "문화공간"],
        "web_search_recommended": False,
    },
    "shopping_place": {
        "scenario": "waiting_place",
        "target_query": "쇼핑몰",
        "categories": [],
        "category_candidates": [
            {"name": "쇼핑몰", "weight": 1.0},
            {"name": "백화점", "weight": 0.9},
            {"name": "아울렛", "weight": 0.65},
        ],
        "conditions": [],
        "preferred_tags": [],
        "kakao_keywords": ["쇼핑몰", "백화점", "아울렛"],
        "web_search_recommended": False,
    },
    "bar_place": {
        "scenario": "restaurant",
        "target_query": "술집",
        "categories": [],
        "category_candidates": [
            {"name": "술집", "weight": 1.0},
            {"name": "바", "weight": 0.85},
            {"name": "펍", "weight": 0.75},
        ],
        "conditions": [],
        "preferred_tags": [],
        "kakao_keywords": ["술집", "바", "펍", "와인바", "칵테일바"],
        "web_search_recommended": False,
    },
    "food_place": {
        "scenario": "restaurant",
        "target_query": "식당",
        "categories": ["restaurant", "cafe"],
        "category_candidates": [
            {"name": "식당", "weight": 0.9},
            {"name": "음식점", "weight": 0.8},
            {"name": "카페", "weight": 0.4},
        ],
        "conditions": ["식사가능"],
        "preferred_tags": ["식사가능"],
        "kakao_keywords": ["식당", "음식점", "맛집"],
        "web_search_recommended": True,
    },
    "general_place_search": {
        "scenario": "waiting_place",
        "target_query": "장소",
        "categories": ["cafe", "shelter", "city_park"],
        "category_candidates": [
            {"name": "장소", "weight": 1.0},
        ],
        "conditions": [],
        "preferred_tags": [],
        "kakao_keywords": [],
        "web_search_recommended": False,
    },
}

INTENT_GROUP_TO_SITUATION = {
    "quiet_rest_place": "quiet_rest",
    "work_place": "work",
    "urgent_toilet": "toilet",
    "health_nearby": "health_nearby",
    "parking_place": "parking",
    "wifi_place": "wifi",
    "weather_shelter": "weather_shelter",
    "walk_healing": "walk",
    "smoking_area": "smoking",
    "food_place": "food",
    "entertainment_place": "general_place",
    "shopping_place": "general_place",
    "bar_place": "general_place",
    "general_place_search": "general_place",
}

SITUATION_TO_INTENT_GROUP = {
    "quiet_rest": "quiet_rest_place",
    "rest": "general_place_search",
    "work": "work_place",
    "toilet": "urgent_toilet",
    "health_nearby": "health_nearby",
    "parking": "parking_place",
    "wifi": "wifi_place",
    "weather_shelter": "weather_shelter",
    "walk": "walk_healing",
    "food": "food_place",
    "smoking": "smoking_area",
    "general_place": "general_place_search",
}

SITUATION_ALIASES = {
    "quiet": "quiet_rest",
    "quiet_rest_place": "quiet_rest",
    "rest_place": "rest",
    "waiting_place": "rest",
    "workspace": "work",
    "work_place": "work",
    "work_cafe": "work",
    "urgent_toilet": "toilet",
    "bathroom": "toilet",
    "restroom": "toilet",
    "health": "health_nearby",
    "pharmacy": "health_nearby",
    "hospital": "health_nearby",
    "parking_place": "parking",
    "wifi_place": "wifi",
    "shelter": "weather_shelter",
    "walk_healing": "walk",
    "walking": "walk",
    "restaurant": "food",
    "food_place": "food",
    "smoking_area": "smoking",
}

REST_FRAME_PLACE_TYPES = ["쉼터", "카페", "백화점 휴게공간", "공원", "도서관"]
REST_FRAME_CONSTRAINTS = ["가까운 곳", "잠깐 쉬기 좋음"]
PLACE_INTENT_FRAME_LIST_FIELDS = {
    "target_objects",
    "candidate_place_types",
    "candidate_category_codes",
    "result_match_terms",
    "search_queries",
    "constraints",
    "exclusions",
    "preferred_place_natures",
    "excluded_place_natures",
    "missing_info",
    "ambiguity",
}

CONDITION_RULES = [
    ("혼자", "혼자 이용하기 좋음", "혼자이용좋음"),
    ("혼밥", "혼자 이용하기 좋음", "혼자이용좋음"),
    ("눈치", "혼자 이용하기 좋음", "혼자이용좋음"),
    ("조용", "조용함", "조용한"),
    ("노트북", "노트북 작업 가능", "노트북작업"),
    ("놋북", "노트북 작업 가능", "노트북작업"),
    ("작업", "노트북 작업 가능", "노트북작업"),
    ("카공", "노트북 작업 가능", "노트북작업"),
    ("사람", "붐비지 않음", "조용한"),
    ("사람 없는", "혼자 이용하기 좋음", "혼자이용좋음"),
    ("붐비", "붐비지 않음", "조용한"),
    ("콘센트", "콘센트 있음", "콘센트있음"),
    ("와이파이", "와이파이 있음", "와이파이"),
    ("wifi", "와이파이 있음", "와이파이"),
    ("비", "비 피하기 좋음", "실내쉼터"),
    ("밖 말고", "실내", "실내쉼터"),
    ("실외 말고", "실내", "실내쉼터"),
    ("앉", "앉을 수 있음", "잠깐쉬기좋음"),
    ("쉬", "잠깐 쉬기 좋음", "잠깐쉬기좋음"),
    ("실내", "실내 이용 가능", "실내쉼터"),
    ("산책", "산책하기 좋음", "산책좋음"),
    ("걷", "걷기 좋음", "산책좋음"),
    ("바람", "바람 쐬기 좋음", "힐링"),
    ("힐링", "힐링하기 좋음", "힐링"),
    ("카페 말고", "카페 제외", ""),
    ("카페 느낌", "카페 느낌 아님", ""),
    ("야경", "야경 보기 좋음", "야경"),
    ("흡연", "흡연 가능", "실외흡연구역"),
]

AMBIGUOUS_REFERENCE_KEYWORDS = [
    "거기",
    "그곳",
    "아까",
    "방금",
    "그중",
    "저기",
]

REFINEMENT_KEYWORDS = [
    "대신",
    "더",
    "다른",
    "가까운",
    "가까이",
    "만",
    "빼",
    "제외",
    "보여줘",
]

REFINEMENT_CONTEXT_PHRASES = [
    "거기 말고",
    "아까 거 말고",
    "아까거 말고",
    "이전 결과 말고",
    "그중에서",
    "다른 데",
    "다른데",
    "다른 곳",
    "다른곳",
    "좀 더 가까운 데",
    "더 가까운 데",
    "더 조용한 데",
    "카페만",
    "공원은 빼",
    "와이파이 되는 곳만",
]

NEGATIVE_PREFERENCE_PHRASES = [
    "밖 말고",
    "실외 말고",
    "사람 많은 데 말고",
    "사람 너무 많은 데 말고",
    "붐비는 데 말고",
    "붐비지 않는",
    "카페 말고",
    "카페 느낌은 아니",
    "카페 같지 않은",
    "카페느낌은아니",
    "카페는 싫",
    "카페 싫",
    "카페 빼고",
]

CATEGORY_LIKE_CONDITION_VALUES = {
    "카페",
    "공원",
    "맛집",
    "쉴 곳",
    "쉴곳",
    "산책할 곳",
    "산책할곳",
    "흡연구역",
    "식당",
    "음식점",
    "쉼터",
}

FRAME_CATEGORY_ALIASES = {
    "park": "city_park",
    "tourist_spot": "tourism",
    "bathroom": "toilet",
    "restroom": "toilet",
    "public_toilet": "toilet",
    "wifi": "freewifi",
    "public_wifi": "freewifi",
    "medical": "hospital",
}

OUT_OF_SCOPE_KEYWORDS = [
    "비트코인",
    "주식",
    "코인",
    "투자",
    "매수",
    "매도",
    "숙제",
    "과제",
    "파이썬",
    "정치",
    "뉴스",
    "연애",
    "의료",
    "감기약",
    "법률",
    "법적",
    "계약서",
    "소송",
    "진단",
]

BLOCKED_KEYWORDS = [
    "불법",
    "위험한 요청",
    "위험한 행동",
    "마약",
    "도박",
    "폭탄",
    "무기",
    "해킹",
    "몰래",
    "스토킹",
    "침입",
    "방화",
    "범죄",
]

PLACE_RECOMMENDATION_HINTS = [
    "장소",
    "곳",
    "데",
    "근처",
    "주변",
    "카페",
    "맛집",
    "산책",
    "쉴",
    "쉬",
    "작업",
    "공부",
    "노트북",
    "놋북",
    "카공",
    "공원",
    "화장실",
    "주차장",
    "주차",
    "와이파이",
    "약국",
    "병원",
    "응급실",
    "약",
    "흡연",
    "쉼터",
    "식당",
    "영화관",
    "공연장",
    "공연",
    "쇼핑몰",
    "백화점",
    "아울렛",
    "술집",
    "주점",
    "와인바",
    "칵테일바",
    "펍",
    "bar",
    "밥",
    "먹",
    "역",
]

AI_INTENT_FALLBACK_HINTS = [
    "눈치",
    "바람쐬",
    "바람 쐬",
    "펴도",
    "많은 데 말고",
    "많은데 말고",
    "카페 느낌",
    "밖 말고",
    "앉아있",
    "있고 싶은데",
    "카페 말고",
    "실외 말고",
    "붐비지",
]

SEARCH_COMMAND_HINTS = [
    "추천",
    "찾아",
    "알려",
    "어디",
]


def build_conversational_search_plan(
    query,
    user=None,
    lat=None,
    lng=None,
    map_center=None,
    previous_context=None,
):
    normalized_query = _clean_text(query)
    if not normalized_query:
        return _finalize_router_plan(_empty_plan(query))

    if _is_clarification_followup_context(previous_context):
        return _finalize_router_plan(
            _build_clarification_followup_search_plan(
                normalized_query,
                previous_context,
                lat=lat,
                lng=lng,
                map_center=map_center,
            )
        )

    rule_plan = _build_rule_plan(
        normalized_query,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )
    if rule_plan.get("action") in {"blocked", "refine_previous_search"}:
        return _finalize_router_plan(rule_plan)

    ai_unavailable_reason = _get_ai_intent_unavailable_reason()
    if rule_plan.get("action") == "out_of_scope" and ai_unavailable_reason:
        return _finalize_router_plan(rule_plan)

    if ai_unavailable_reason:
        return _finalize_router_plan(
            _mark_legacy_fallback(rule_plan, ai_reason=ai_unavailable_reason)
        )

    ai_plan, ai_error_reason = _build_ai_plan(normalized_query, rule_plan)

    if not ai_plan:
        return _finalize_router_plan(
            _mark_legacy_fallback(
                rule_plan,
                ai_reason=ai_error_reason or "empty_ai_response",
            )
        )

    normalized_ai_plan = _normalize_ai_plan(
        ai_plan,
        query=normalized_query,
        fallback_plan=rule_plan,
        lat=lat,
        lng=lng,
        map_center=map_center,
        previous_context=previous_context,
    )
    return _finalize_router_plan(
        normalized_ai_plan
        or _mark_legacy_fallback(rule_plan, ai_reason="ai_invalid_response")
    )


def _empty_plan(query):
    return {
        "action": "ask_clarification",
        "decision_action": "ask_clarification",
        "type": "clarification",
        "user_intent_summary": "검색어를 입력해 주세요.",
        "location": _location_payload("", False, "current_location"),
        "targets": [],
        "conditions": [],
        "preferences": [],
        "avoid": [],
        "search_plan": _search_plan_payload(
            original_query=query or "",
            location_query="",
            target_query="",
            scenario="waiting_place",
            categories=["cafe", "shelter"],
            menu_keywords=[],
            place_type_keywords=[],
            required_tags=[],
            preferred_tags=[],
            requested_conditions=[],
        ),
        "execution_policy": _execution_policy(False, False),
        "needs_clarification": True,
        "clarification_question": "어떤 장소를 찾고 싶은지 알려주세요.",
        "clarification_options": _default_clarification_options(),
        "can_search_now": False,
        "results": [],
        "confidence": 0,
        "fallback_reason": "empty_query",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _build_rule_plan(query, lat=None, lng=None, map_center=None, previous_context=None):
    if _is_blocked_query(query):
        return _blocked_plan(query)

    if _is_out_of_scope_query(query):
        return _out_of_scope_plan(query)

    location_query, target_query = _extract_location_and_target(query)
    has_explicit_location = bool(location_query)
    fallback_location = "" if has_explicit_location else "current_location"
    has_previous_context = bool(previous_context)
    has_ambiguous_reference = _has_any(query, AMBIGUOUS_REFERENCE_KEYWORDS)
    has_refinement = _is_refinement_request(query)
    has_location_context = has_explicit_location or _has_coordinate_context(lat, lng, map_center)

    if not has_previous_context and not has_refinement and _is_ambiguous_quiet_place_request(query, target_query):
        return _clarification_plan(
            query,
            question=QUIET_PURPOSE_CLARIFICATION_MESSAGE,
            reason="missing_quiet_purpose",
            target_query=target_query,
            fallback_location=fallback_location,
        )

    if has_refinement and not has_previous_context and not has_explicit_location:
        return _clarification_plan(
            query,
            question=REFINEMENT_CLARIFICATION_MESSAGE,
            reason="refinement_without_context",
            target_query=target_query,
            fallback_location=fallback_location,
        )

    if has_ambiguous_reference and not has_previous_context and not has_explicit_location:
        return _clarification_plan(
            query,
            question=CLARIFICATION_MESSAGE,
            reason="ambiguous_reference_without_context",
            target_query=target_query,
            fallback_location=fallback_location,
        )

    scenario, categories, kakao_keywords, preferred_tags = _pick_scenario(query, target_query)
    scenario, categories, kakao_keywords, preferred_tags = _apply_query_intent_overrides(
        query,
        scenario,
        categories,
        kakao_keywords,
        preferred_tags,
    )
    intent_group = _classify_intent_group(query, target_query, scenario)
    intent_config = INTENT_GROUP_CONFIGS.get(intent_group)
    if intent_config and intent_group != "general_place_search":
        scenario = intent_config["scenario"]
        categories = list(intent_config["categories"])
        kakao_keywords = list(intent_config["kakao_keywords"])
        preferred_tags = list(intent_config["preferred_tags"])

    if _is_vague_place_request(query, scenario, target_query):
        return _clarification_plan(
            query,
            question=PURPOSE_CLARIFICATION_MESSAGE,
            reason="missing_purpose",
            target_query=target_query,
            fallback_location=fallback_location,
        )

    if not has_location_context and _requires_location_before_search(query, scenario, target_query):
        return _clarification_plan(
            query,
            question=_missing_location_question(query, scenario),
            reason="missing_location_context",
            target_query=_target_query_for_scenario(scenario),
            fallback_location=fallback_location,
        )

    if has_previous_context and has_refinement:
        return _refine_previous_search_plan(query, previous_context)

    conditions = [] if scenario == "smoking_area" else _extract_conditions(query)
    if intent_config:
        conditions = _sanitize_requested_conditions([
            *intent_config.get("conditions", []),
            *conditions,
        ])
    menu_keywords = _extract_menu_keywords(query)
    place_type_keywords = _extract_place_type_keywords(query, menu_keywords, scenario)
    if intent_group in {
        "quiet_rest_place",
        "urgent_toilet",
        "health_nearby",
        "parking_place",
        "wifi_place",
        "weather_shelter",
    }:
        place_type_keywords = []
    if _has_cafe_negative_preference(query):
        place_type_keywords = [
            keyword
            for keyword in place_type_keywords
            if "카페" not in keyword
        ]
    target_query = _clean_target_query(target_query or _derive_target_query(query, scenario, menu_keywords))
    target_query = _fallback_target_query(target_query, scenario, menu_keywords)
    if scenario == "smoking_area":
        target_query = "흡연구역"
    elif scenario == "walk_healing" and _has_any(query, ["바람", "걷", "산책", "힐링"]):
        target_query = "산책할 곳"
    elif scenario == "waiting_place" and _has_waiting_place_natural_intent(query):
        target_query = "쉴 곳"
    elif scenario == "work_cafe" and _has_any(
        query,
        ["작업", "노트북", "공부", "카공", "콘센트", "와이파이", "조용"],
    ):
        target_query = "카페"
    target_query = _target_query_for_intent_group(intent_group, query, target_query, scenario, menu_keywords)

    preferred_tags = _unique([
        *preferred_tags,
        *[tag for _, _, tag in _matched_condition_rules(query) if tag],
    ])
    preferred_tags = [tag for tag in preferred_tags if tag in ALLOWED_TAGS or tag]
    conditions = _sanitize_requested_conditions(conditions)

    return {
        "action": "search",
        "user_intent_summary": _build_intent_summary(location_query, target_query, scenario, conditions),
        "location": _location_payload(location_query, has_explicit_location, fallback_location),
        "targets": _unique([target_query, *menu_keywords, *place_type_keywords]),
        "conditions": conditions,
        "preferences": preferred_tags,
        "avoid": _extract_avoid_terms(query),
        "message": HEALTH_NEARBY_MESSAGE if intent_group == "health_nearby" else "",
        "search_plan": {
            **_search_plan_payload(
            original_query=query,
            location_query=location_query,
            target_query=target_query,
            scenario=scenario,
            categories=categories,
            menu_keywords=menu_keywords,
            place_type_keywords=place_type_keywords,
            required_tags=[],
            preferred_tags=preferred_tags,
            requested_conditions=conditions,
            kakao_keyword_candidates=_unique([*kakao_keywords, target_query, *place_type_keywords]),
            ),
            "excluded_categories": _extract_excluded_categories(query),
            "intent_group": intent_group,
        },
        "execution_policy": _execution_policy(True, has_explicit_location),
        "needs_clarification": False,
        "clarification_question": "",
        "confidence": 82 if has_explicit_location else 72,
        "fallback_reason": "rule_based_planner",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _clarification_plan(
    query,
    question,
    reason,
    target_query="",
    fallback_location="current_location",
):
    conditions = _extract_conditions(query)
    return {
        "action": "ask_clarification",
        "user_intent_summary": question,
        "message": question,
        "location": _location_payload("", False, fallback_location),
        "targets": [],
        "conditions": _sanitize_requested_conditions(conditions),
        "preferences": [],
        "avoid": [],
        "search_plan": _search_plan_payload(
            original_query=query,
            location_query="",
            target_query=_clean_target_query(target_query or query),
            scenario="waiting_place",
            categories=["cafe", "shelter"],
            menu_keywords=[],
            place_type_keywords=[],
            required_tags=[],
            preferred_tags=[],
            requested_conditions=_sanitize_requested_conditions(conditions),
        ),
        "execution_policy": _execution_policy(False, False),
        "needs_clarification": True,
        "clarification_question": question,
        "confidence": 45,
        "fallback_reason": reason,
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _out_of_scope_plan(query):
    return {
        "action": "out_of_scope",
        "intent_type": "out_of_scope",
        "user_intent_summary": "장소 추천 범위 밖 요청입니다.",
        "message": OUT_OF_SCOPE_MESSAGE,
        "location": _location_payload("", False, ""),
        "targets": [],
        "conditions": [],
        "preferences": [],
        "avoid": [],
        "search_plan": {},
        "execution_policy": _execution_policy(False, False),
        "needs_clarification": False,
        "clarification_question": "",
        "blocked_reason": "",
        "out_of_scope_reason": "not_place_recommendation",
        "confidence": 90,
        "fallback_reason": "out_of_scope_rule",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _blocked_plan(query):
    return {
        "action": "blocked",
        "intent_type": "unsafe_request",
        "user_intent_summary": "안전상 처리할 수 없는 요청입니다.",
        "message": BLOCKED_MESSAGE,
        "location": _location_payload("", False, ""),
        "targets": [],
        "conditions": [],
        "preferences": [],
        "avoid": [],
        "search_plan": {},
        "execution_policy": _execution_policy(False, False),
        "needs_clarification": False,
        "clarification_question": "",
        "blocked_reason": "unsafe_request",
        "out_of_scope_reason": "",
        "confidence": 95,
        "fallback_reason": "blocked_rule",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _refine_previous_search_plan(query, previous_context):
    previous_context = previous_context or {}
    previous_search_plan = previous_context.get("search_plan") or {}
    if not isinstance(previous_search_plan, dict):
        previous_search_plan = {}

    additional_conditions = _sanitize_requested_conditions(_extract_conditions(query))
    location_query = _clean_text(
        previous_search_plan.get("locationQuery")
        or previous_search_plan.get("location_query")
        or previous_search_plan.get("baseLocationQuery")
        or previous_search_plan.get("base_location_query")
    )
    target_query = _clean_target_query(
        previous_search_plan.get("targetQuery")
        or previous_search_plan.get("target_query")
        or previous_search_plan.get("targetKeyword")
        or previous_search_plan.get("target_keyword")
        or _derive_target_query(query, "waiting_place", [])
    )
    scenario = _normalize_scenario(previous_search_plan.get("scenario"))
    categories = _normalize_categories(previous_search_plan.get("categories") or [])
    if not categories:
        categories = ["cafe", "shelter"] if scenario == "waiting_place" else ["cafe"]

    search_plan = _search_plan_payload(
        original_query=query,
        location_query=location_query,
        target_query=target_query,
        scenario=scenario,
        categories=categories,
        menu_keywords=_normalize_text_list(previous_search_plan.get("menu_keywords") or []),
        place_type_keywords=_normalize_text_list(previous_search_plan.get("place_type_keywords") or []),
        required_tags=_normalize_tags(previous_search_plan.get("required_tags") or []),
        preferred_tags=_unique([
            *_normalize_tags(previous_search_plan.get("preferred_tags") or []),
            *[tag for _, _, tag in _matched_condition_rules(query) if tag],
        ]),
        requested_conditions=_unique([
            *_normalize_text_list(
                previous_search_plan.get("requestedConditions")
                or previous_search_plan.get("requested_conditions")
                or []
            ),
            *additional_conditions,
        ]),
        kakao_keyword_candidates=_normalize_text_list(
            previous_search_plan.get("kakaoKeywordCandidates")
            or previous_search_plan.get("kakao_keyword_candidates")
            or [target_query]
        ),
    )
    search_plan["additional_conditions"] = additional_conditions
    search_plan["sort_hint"] = "distance" if _has_any(query, ["가까운", "가까이"]) else ""
    search_plan["category_filter"] = _extract_category_filter(query)
    search_plan["exclude_terms"] = _extract_avoid_terms(query)

    return {
        "action": "refine_previous_search",
        "intent_type": "place_recommendation",
        "user_intent_summary": "이전 검색 결과를 더 좁히는 요청입니다.",
        "message": "",
        "location": _location_payload(location_query, bool(location_query), "current_location"),
        "targets": _normalize_text_list([target_query]),
        "conditions": additional_conditions,
        "preferences": search_plan["preferred_tags"],
        "avoid": search_plan["exclude_terms"],
        "search_plan": search_plan,
        "execution_policy": _execution_policy(False, bool(location_query)),
        "needs_clarification": False,
        "clarification_question": "",
        "confidence": 78,
        "fallback_reason": "refine_previous_search_rule",
        "parser_provider": "rule",
        "parser_fallback": True,
    }


def _is_clarification_followup_context(previous_context):
    if not isinstance(previous_context, dict):
        return False
    if not previous_context.get("is_clarification_followup"):
        return False
    return any(
        isinstance(previous_context.get(key), dict)
        for key in ("search_plan", "pending_clarification_frame")
    )


def _rule_plan_has_searchable_evidence(rule_plan, lat=None, lng=None, map_center=None):
    if not isinstance(rule_plan, dict) or rule_plan.get("action") != "search":
        return False

    execution_policy = rule_plan.get("execution_policy")
    if isinstance(execution_policy, dict) and execution_policy.get("run_search") is False:
        return False

    search_plan = rule_plan.get("search_plan")
    if not isinstance(search_plan, dict):
        return False
    intent_group = _clean_text(search_plan.get("intent_group") or search_plan.get("intentGroup"))
    if not intent_group or intent_group == "general_place_search":
        return False

    target_terms = _sanitize_frame_list([
        search_plan.get("targetQuery"),
        search_plan.get("target_query"),
        *(_normalize_text_list(search_plan.get("menu_keywords") or [])),
        *(_normalize_text_list(search_plan.get("place_type_keywords") or [])),
        *(_normalize_text_list(search_plan.get("kakaoKeywordCandidates") or [])),
    ])
    has_target_evidence = bool(target_terms and not _all_terms_are_broad(target_terms))
    location = rule_plan.get("location") if isinstance(rule_plan.get("location"), dict) else {}
    has_location_context = bool(
        location.get("is_explicit")
        or _has_coordinate_context(lat, lng, map_center)
    )
    return has_target_evidence and has_location_context


def _get_context_location_value(context, *keys):
    if not isinstance(context, dict):
        return ""
    return _clean_text(_first_text(*(context.get(key) for key in keys)))


def _get_context_float(context, *keys):
    if not isinstance(context, dict):
        return None
    for key in keys:
        try:
            value = float(context.get(key))
        except (TypeError, ValueError):
            continue
        return value
    return None


def _usable_followup_frame_terms(values, original_query):
    terms = _sanitize_frame_list(values or [])
    if not terms or _all_terms_are_broad(terms, query=original_query):
        return []
    return terms


def _merge_followup_location(query, previous_search_plan, frame, previous_context, lat=None, lng=None, map_center=None):
    last_location_context = previous_context.get("last_resolved_location_context")
    if not isinstance(last_location_context, dict):
        last_location_context = {}

    explicit_location, explicit_target = _extract_location_and_target(query)
    explicit_location = _sanitize_ai_location_query(explicit_location)
    answer_text = _clean_target_query(explicit_target or query)

    preserved_anchor = _sanitize_ai_location_query(
        _first_text(
            frame.get("anchor_location"),
            frame.get("anchorLocation"),
            previous_search_plan.get("locationQuery"),
            previous_search_plan.get("location_query"),
            previous_search_plan.get("baseLocationQuery"),
            previous_search_plan.get("base_location_query"),
            last_location_context.get("locationQuery"),
            last_location_context.get("anchorLocation"),
            last_location_context.get("anchor_location"),
        )
    )
    anchor_location = explicit_location or preserved_anchor

    location_mode = _normalize_frame_location_mode(
        _first_text(
            ("explicit" if explicit_location else ""),
            frame.get("location_mode"),
            frame.get("locationMode"),
            previous_search_plan.get("location_mode"),
            previous_search_plan.get("locationMode"),
            last_location_context.get("locationMode"),
            last_location_context.get("location_mode"),
        ),
        anchor_location=anchor_location,
    )
    has_coordinate_context = (
        _has_coordinate_context(lat, lng, map_center)
        or _get_context_float(last_location_context, "lat", "latitude") is not None
        or _get_context_float(last_location_context, "lng", "longitude") is not None
    )
    if not anchor_location and location_mode == "clarification_required" and has_coordinate_context:
        location_mode = "current_context"

    return anchor_location, location_mode, answer_text


def _build_clarification_followup_search_plan(query, previous_context, lat=None, lng=None, map_center=None):
    previous_context = previous_context if isinstance(previous_context, dict) else {}
    previous_search_plan = previous_context.get("search_plan")
    if not isinstance(previous_search_plan, dict):
        previous_search_plan = {}

    pending_frame = previous_context.get("pending_clarification_frame")
    if not isinstance(pending_frame, dict):
        pending_frame = (
            previous_search_plan.get("place_intent_frame")
            or previous_search_plan.get("placeIntentFrame")
            or {}
        )
    if not isinstance(pending_frame, dict):
        pending_frame = {}

    original_query = _clean_text(
        previous_context.get("previous_user_query")
        or previous_context.get("original_query")
        or previous_context.get("query")
        or previous_search_plan.get("originalQuery")
        or previous_search_plan.get("original_query")
        or ""
    )
    answer = _clean_target_query(previous_context.get("clarification_answer") or query)
    anchor_location, location_mode, answer_text = _merge_followup_location(
        answer,
        previous_search_plan,
        pending_frame,
        previous_context,
        lat=lat,
        lng=lng,
        map_center=map_center,
    )
    answer_terms = _sanitize_frame_list([answer_text or answer])
    if not answer_terms or _all_terms_are_broad(answer_terms, query=answer):
        plan = _ai_frame_post_validation_clarification_plan(
            query=original_query or query,
            raw_plan={"confidence": previous_context.get("confidence", 0)},
            search_plan=previous_search_plan,
            frame=pending_frame,
            reasons=["followup_answer_still_broad"],
        )
        plan["fallback_reason"] = "clarification_follow_up_still_broad"
        return plan

    combined_query = " ".join([original_query, answer]).strip() or query
    if _can_use_ai_intent_interpreter():
        ai_fallback_plan = _build_rule_plan(
            combined_query,
            lat=lat,
            lng=lng,
            map_center=map_center,
            previous_context=None,
        )
        ai_plan, ai_error_reason = _build_ai_plan(combined_query, ai_fallback_plan)
        if ai_plan:
            normalized_ai_plan = _normalize_ai_plan(
                ai_plan,
                query=combined_query,
                fallback_plan=ai_fallback_plan,
                lat=lat,
                lng=lng,
                map_center=map_center,
                previous_context=previous_context,
            )
            if normalized_ai_plan:
                normalized_ai_plan["fallback_reason"] = "clarification_follow_up_ai_merge"
                normalized_ai_plan["plan_source"] = normalized_ai_plan.get("plan_source") or "ai"
                normalized_ai_plan["execution_mode"] = normalized_ai_plan.get("execution_mode") or "frame"
                search_plan = normalized_ai_plan.get("search_plan")
                if isinstance(search_plan, dict):
                    search_plan["plan_source"] = search_plan.get("plan_source") or normalized_ai_plan["plan_source"]
                    search_plan["execution_mode"] = search_plan.get("execution_mode") or normalized_ai_plan["execution_mode"]
                normalized_ai_plan.setdefault("ai_debug", {})
                normalized_ai_plan["ai_debug"]["clarification_follow_up_ai_merge"] = {
                    "status": "used",
                    "original_query": original_query,
                    "answer": answer,
                }
                return normalized_ai_plan

        plan = _ai_frame_post_validation_clarification_plan(
            query=combined_query,
            raw_plan={"confidence": previous_context.get("confidence", 0), "ai_fallback_reason": ai_error_reason},
            search_plan=previous_search_plan,
            frame=pending_frame,
            reasons=["clarification_follow_up_ai_merge_failed"],
        )
        plan["fallback_reason"] = "clarification_follow_up_ai_merge_failed"
        plan["ai_fallback_reason"] = ai_error_reason
        return plan

    existing_frame = (
        _normalize_place_intent_frame(pending_frame, user_query=original_query or query)
        if pending_frame
        else {}
    )
    scenario, categories, kakao_keywords, preferred_tags = _pick_scenario(answer, answer_text or answer)
    scenario, categories, kakao_keywords, preferred_tags = _apply_query_intent_overrides(
        answer,
        scenario,
        categories,
        kakao_keywords,
        preferred_tags,
    )
    previous_categories = _normalize_categories(
        existing_frame.get("candidate_category_codes")
        or previous_search_plan.get("candidate_category_codes")
        or previous_search_plan.get("categories")
        or []
    )
    categories = categories or previous_categories
    scenario = _normalize_scenario(
        scenario
        or previous_search_plan.get("scenario")
        or "waiting_place"
    )

    existing_targets = _usable_followup_frame_terms(
        existing_frame.get("target_objects") or existing_frame.get("targetObjects") or [],
        original_query,
    )
    existing_result_terms = _usable_followup_frame_terms(
        existing_frame.get("result_match_terms") or existing_frame.get("resultMatchTerms") or [],
        original_query,
    )
    existing_place_types = _usable_followup_frame_terms(
        existing_frame.get("candidate_place_types") or existing_frame.get("candidatePlaceTypes") or [],
        original_query,
    )
    existing_search_queries = _usable_followup_frame_terms(
        existing_frame.get("search_queries") or existing_frame.get("searchQueries") or [],
        original_query,
    )

    target_objects = _unique([*existing_targets, *answer_terms])
    result_match_terms = _unique([*existing_result_terms, *answer_terms])
    candidate_place_types = _unique([*existing_place_types, *answer_terms])
    search_query_terms = _unique([
        *existing_search_queries,
        *kakao_keywords,
        *target_objects,
        *result_match_terms,
        *candidate_place_types,
    ])
    search_queries = _apply_anchor_location_to_keywords(anchor_location, search_query_terms)

    constraints = _unique([
        *_sanitize_frame_list(existing_frame.get("constraints") or []),
        *_sanitize_requested_conditions(_extract_conditions(answer)),
    ])
    exclusions = _unique([
        *_sanitize_frame_list(existing_frame.get("exclusions") or []),
        *_extract_avoid_terms(answer),
    ])
    display_label = _clean_target_query(
        _first_text(answer_text, *target_objects, existing_frame.get("display_label"))
    )
    ranking_policy = _normalize_ranking_policy(
        existing_frame.get("ranking_policy")
        or existing_frame.get("rankingPolicy")
        or previous_search_plan.get("ranking_policy")
        or previous_search_plan.get("rankingPolicy")
    )

    frame = {
        **existing_frame,
        "decision_action": "search",
        "decisionAction": "search",
        "can_search_now": True,
        "canSearchNow": True,
        "user_goal": _clean_text(existing_frame.get("user_goal")) or f"{display_label} 장소 찾기",
        "anchor_location": anchor_location,
        "anchorLocation": anchor_location,
        "location_mode": location_mode,
        "locationMode": location_mode,
        "situation": existing_frame.get("situation") or _situation_for_intent_group(
            _classify_intent_group(combined_query, display_label, scenario),
            combined_query,
            display_label,
            scenario,
        ),
        "display_label": display_label,
        "displayLabel": display_label,
        "target_objects": target_objects,
        "targetObjects": target_objects,
        "candidate_category_codes": categories,
        "candidateCategoryCodes": categories,
        "candidate_place_types": candidate_place_types,
        "candidatePlaceTypes": candidate_place_types,
        "search_queries": search_queries,
        "searchQueries": search_queries,
        "result_match_terms": result_match_terms,
        "resultMatchTerms": result_match_terms,
        "constraints": constraints,
        "exclusions": exclusions,
        "preferred_place_natures": existing_frame.get("preferred_place_natures") or [],
        "excluded_place_natures": existing_frame.get("excluded_place_natures") or [],
        "ranking_policy": ranking_policy,
        "rankingPolicy": ranking_policy,
        "evidence": [
            *(
                existing_frame.get("evidence")
                if isinstance(existing_frame.get("evidence"), list)
                else []
            ),
            {"type": "clarification_answer", "value": answer},
        ],
        "missing_info": [],
        "missingInfo": [],
        "confidence": max(_normalize_frame_confidence(existing_frame.get("confidence"), 0.72), 0.72),
    }
    frame = _normalize_place_intent_frame(frame, user_query=combined_query)

    post_validation_reasons = _get_ai_frame_post_validation_reasons(frame, combined_query)
    if post_validation_reasons:
        plan = _ai_frame_post_validation_clarification_plan(
            query=combined_query,
            raw_plan={"confidence": frame.get("confidence", 0)},
            search_plan=previous_search_plan,
            frame=frame,
            reasons=post_validation_reasons,
        )
        plan["fallback_reason"] = "clarification_follow_up_post_validation"
        return plan

    search_plan = _search_plan_payload(
        original_query=combined_query,
        location_query=anchor_location,
        target_query=display_label,
        scenario=scenario,
        categories=categories,
        menu_keywords=_normalize_text_list(previous_search_plan.get("menu_keywords") or []),
        place_type_keywords=candidate_place_types,
        required_tags=_normalize_tags(previous_search_plan.get("required_tags") or []),
        preferred_tags=_unique([
            *_normalize_tags(previous_search_plan.get("preferred_tags") or []),
            *preferred_tags,
            *[tag for _, _, tag in _matched_condition_rules(answer) if tag],
        ]),
        requested_conditions=constraints,
        kakao_keyword_candidates=search_queries,
    )
    search_plan.update({
        "place_intent_frame": frame,
        "placeIntentFrame": frame,
        "location_mode": location_mode,
        "locationMode": location_mode,
        "anchor_location": anchor_location,
        "anchorLocation": anchor_location,
        "target_objects": target_objects,
        "candidate_place_types": candidate_place_types,
        "search_queries": search_queries,
        "result_match_terms": result_match_terms,
        "constraints": constraints,
        "exclusions": exclusions,
        "ranking_policy": ranking_policy,
        "intent_group": _classify_intent_group(combined_query, display_label, scenario),
        "execution_mode": "frame",
        "plan_source": "clarification_follow_up",
    })

    return {
        "action": "search",
        "intent_type": "place_recommendation",
        "user_intent_summary": f"{display_label} 장소를 찾습니다.",
        "message": f"{display_label} 조건으로 이어서 찾아볼게요.",
        "location": _location_payload(
            anchor_location,
            bool(anchor_location),
            "" if anchor_location else "current_location",
        ),
        "targets": target_objects,
        "conditions": constraints,
        "preferences": search_plan["preferred_tags"],
        "avoid": exclusions,
        "search_plan": search_plan,
        "execution_policy": _execution_policy(True, bool(anchor_location)),
        "needs_clarification": False,
        "clarification_question": "",
        "clarification_options": [],
        "confidence": 78,
        "fallback_reason": "clarification_follow_up_merge",
        "parser_provider": "rule",
        "parser_fallback": True,
        "plan_source": "clarification_follow_up",
        "execution_mode": "frame",
        "clarification_follow_up": {
            "original_query": original_query,
            "answer": answer,
            "preserved_anchor_location": anchor_location,
            "location_mode": location_mode,
        },
    }


def _finalize_router_plan(plan):
    plan = plan or _empty_plan("")
    action = plan.get("action")
    if action not in ROUTER_ACTIONS:
        action = "ask_clarification"
    plan["action"] = action
    plan["decision_action"] = action
    plan["decisionAction"] = action

    if "intent_type" not in plan:
        if action == "blocked":
            plan["intent_type"] = "unsafe_request"
        elif action == "out_of_scope":
            plan["intent_type"] = "out_of_scope"
        else:
            plan["intent_type"] = "place_recommendation"

    plan.setdefault("user_intent_summary", "")
    plan.setdefault("message", "")
    plan.setdefault("search_plan", {} if action in {"blocked", "out_of_scope"} else _empty_plan("")["search_plan"])
    plan.setdefault("blocked_reason", "unsafe_request" if action == "blocked" else "")
    plan.setdefault("out_of_scope_reason", "not_place_recommendation" if action == "out_of_scope" else "")
    plan.setdefault("confidence", 0.0)
    plan.setdefault("clarification_question", "")
    plan.setdefault("clarification_options", [])
    plan.setdefault("results", [])

    if action == "ask_clarification":
        plan["needs_clarification"] = True
        search_plan = plan.get("search_plan") if isinstance(plan.get("search_plan"), dict) else {}
        frame = search_plan.get("place_intent_frame") if isinstance(search_plan.get("place_intent_frame"), dict) else {}
        is_ai_plan = plan.get("parser_fallback") is False or plan.get("plan_source") == "ai"
        question = plan.get("clarification_question") or plan.get("message") or ""
        if is_ai_plan and _is_generic_clarification_text(question):
            question = _contextual_ai_clarification_question(
                search_plan.get("originalQuery") or search_plan.get("original_query") or "",
                frame,
            )
        plan["clarification_question"] = question or CLARIFICATION_MESSAGE
        plan["message"] = plan.get("message") or plan["clarification_question"]
        raw_options = _normalize_text_list(
            plan.get("clarification_options")
            or plan.get("clarificationOptions")
            or []
        )
        if _should_use_default_purpose_options(question, frame, raw_options, is_ai_plan=is_ai_plan):
            plan["clarification_options"] = _default_clarification_options()
        else:
            plan["clarification_options"] = raw_options if raw_options else ([] if is_ai_plan else _default_clarification_options())
        plan["execution_policy"] = _execution_policy(False, False)
        plan["type"] = "clarification"
        plan["can_search_now"] = False
        plan["results"] = []
    elif action in {"blocked", "out_of_scope"}:
        plan["needs_clarification"] = False
        plan["message"] = plan.get("message") or (BLOCKED_MESSAGE if action == "blocked" else OUT_OF_SCOPE_MESSAGE)
        plan["search_plan"] = {}
        plan["execution_policy"] = _execution_policy(False, False)
        plan["type"] = action
        plan["can_search_now"] = False
        plan["results"] = []
    else:
        plan["needs_clarification"] = False
        plan.setdefault("execution_policy", _execution_policy(action == "search", False))
        plan["type"] = "search" if action == "search" else action
        plan["can_search_now"] = action == "search"

    if action not in {"blocked", "out_of_scope"}:
        search_plan = plan.get("search_plan") if isinstance(plan.get("search_plan"), dict) else {}
        search_plan["decision_action"] = action
        search_plan["decisionAction"] = action
        search_plan["can_search_now"] = action == "search"
        if action == "ask_clarification":
            search_plan["clarification_question"] = plan["clarification_question"]
            search_plan["clarification_options"] = plan["clarification_options"]
        if action == "search" and _is_ai_frame_execution_plan(plan):
            search_plan["execution_mode"] = "frame"
            search_plan["plan_source"] = plan.get("plan_source") or "ai"
            plan["search_plan"] = search_plan
            plan["execution_mode"] = "frame"
            plan["plan_source"] = plan.get("plan_source") or "ai"
        elif action in {"ask_clarification", "refine_previous_search"} and plan.get("parser_fallback") is False:
            search_plan["execution_mode"] = "decision_gate"
            search_plan["plan_source"] = plan.get("plan_source") or "ai"
            plan["execution_mode"] = "decision_gate"
            plan["plan_source"] = plan.get("plan_source") or "ai"
        else:
            _enrich_plan_with_intent_group(plan)
            search_plan = plan.get("search_plan") if isinstance(plan.get("search_plan"), dict) else {}
        if action == "search" and search_plan.get("web_search_recommended"):
            execution_policy = plan.get("execution_policy") if isinstance(plan.get("execution_policy"), dict) else {}
            execution_policy["allow_ai_web_search_auto"] = True
            execution_policy["merge_ai_web_results"] = False
            plan["execution_policy"] = execution_policy
        synced_anchor_location = sync_frame_location_to_search_plan(search_plan)
        _sync_decision_to_frame(search_plan, plan)
        plan["search_plan"] = search_plan
        if action == "search" and synced_anchor_location:
            plan["location"] = _location_payload(synced_anchor_location, True, "")
            execution_policy = plan.get("execution_policy") if isinstance(plan.get("execution_policy"), dict) else {}
            execution_policy["preserve_explicit_location"] = True
            plan["execution_policy"] = execution_policy

    return plan


def _default_clarification_options():
    return list(DEFAULT_CLARIFICATION_OPTIONS)


def _looks_like_location_clarification(question):
    compact = _compact(question)
    if not compact:
        return False
    has_location = any(term in compact for term in ["지역", "위치", "기준위치", "어디에서", "어느지역"])
    has_purpose = any(term in compact for term in ["목적", "상황", "어떤장소", "장소방향", "찾고싶은장소"])
    return has_location and not has_purpose


def _should_use_default_purpose_options(question, frame, options, is_ai_plan=False):
    if _looks_like_location_clarification(question):
        return False
    if not is_ai_plan:
        return not options

    compact_question = _compact(question)
    if (
        _is_generic_clarification_text(question)
        or any(term in compact_question for term in ["목적", "상황", "어떤장소", "장소방향", "찾고싶은장소"])
    ):
        return True

    frame = frame if isinstance(frame, dict) else {}
    frame_terms = _sanitize_frame_list([
        frame.get("display_label"),
        frame.get("displayLabel"),
        frame.get("user_goal"),
        frame.get("userGoal"),
        *(_sanitize_frame_list(frame.get("target_objects") or frame.get("targetObjects") or [])),
        *(_sanitize_frame_list(frame.get("candidate_place_types") or frame.get("candidatePlaceTypes") or [])),
        *(_sanitize_frame_list(frame.get("result_match_terms") or frame.get("resultMatchTerms") or [])),
    ])
    if frame_terms and _all_terms_are_broad(frame_terms):
        return True

    broad_options = {_compact(option) for option in BROAD_FRAME_CLARIFICATION_OPTIONS}
    option_terms = {_compact(option) for option in options or [] if _compact(option)}
    return bool(option_terms and option_terms.issubset(broad_options))


def _is_generic_clarification_text(value):
    compact = _compact(value)
    generic_patterns = {
        _compact(BROAD_FRAME_CLARIFICATION_MESSAGE),
        _compact(CLARIFICATION_MESSAGE),
        _compact(PURPOSE_CLARIFICATION_MESSAGE),
        _compact("어떤 장소를 원하시나요?"),
        _compact("좀 더 자세히 알려주세요."),
    }
    return not compact or compact in generic_patterns


def _contextual_ai_clarification_question(query, frame):
    frame = frame if isinstance(frame, dict) else {}
    existing = _clean_text(
        frame.get("clarification_question")
        or frame.get("clarificationQuestion")
        or ""
    )
    if existing and not _is_generic_clarification_text(existing):
        return existing

    intent_text = _clean_text(
        frame.get("normalized_user_intent")
        or frame.get("normalizedUserIntent")
        or frame.get("user_goal")
        or frame.get("userGoal")
        or frame.get("display_label")
        or frame.get("displayLabel")
        or query
    )
    if intent_text:
        return f'"{intent_text}" 상황에서 어떤 장소를 찾아야 할지 아직 확정하기 어렵습니다. 찾고 싶은 장소 방향을 조금 더 구체적으로 알려주세요.'
    return "현재 문장만으로는 검색할 장소 방향을 확정하기 어렵습니다. 찾고 싶은 장소 방향을 조금 더 구체적으로 알려주세요."


def _contextual_ai_clarification_options(frame):
    frame = frame if isinstance(frame, dict) else {}
    broad_options = {_compact(option) for option in BROAD_FRAME_CLARIFICATION_OPTIONS}
    return [
        option
        for option in _normalize_text_list(
            frame.get("clarification_options")
            or frame.get("clarificationOptions")
            or []
        )
        if _compact(option) and _compact(option) not in broad_options
    ]


def _sync_decision_to_frame(search_plan, plan):
    if not isinstance(search_plan, dict) or not isinstance(plan, dict):
        return

    frame = search_plan.get("place_intent_frame") or search_plan.get("placeIntentFrame")
    if not isinstance(frame, dict):
        return

    action = plan.get("decision_action") or plan.get("action") or ""
    can_search_now = action == "search"
    clarification_question = plan.get("clarification_question") or ""
    clarification_options = _normalize_text_list(plan.get("clarification_options") or [])

    frame["decision_action"] = action
    frame["decisionAction"] = action
    frame["can_search_now"] = can_search_now
    frame["canSearchNow"] = can_search_now
    frame["normalized_user_intent"] = (
        frame.get("normalized_user_intent")
        or frame.get("normalizedUserIntent")
        or plan.get("user_intent_summary")
        or frame.get("user_goal")
        or ""
    )
    frame["normalizedUserIntent"] = frame["normalized_user_intent"]
    frame["clarification_question"] = (
        frame.get("clarification_question")
        or frame.get("clarificationQuestion")
        or clarification_question
    )
    frame["clarificationQuestion"] = frame["clarification_question"]
    frame["clarification_options"] = _normalize_text_list(
        frame.get("clarification_options")
        or frame.get("clarificationOptions")
        or clarification_options
    )
    frame["clarificationOptions"] = frame["clarification_options"]
    frame["assumptions"] = _sanitize_frame_list(frame.get("assumptions") or [])
    search_plan["place_intent_frame"] = frame


def sync_frame_location_to_search_plan(search_plan):
    if not isinstance(search_plan, dict):
        return ""

    frame = search_plan.get("place_intent_frame") or search_plan.get("placeIntentFrame")
    if not isinstance(frame, dict):
        return ""

    anchor = _sanitize_ai_location_query(
        frame.get("anchor_location")
        or frame.get("anchorLocation")
        or ""
    )
    if not anchor:
        return ""

    frame["anchor_location"] = anchor
    frame["anchorLocation"] = anchor
    frame["location_mode"] = "explicit"
    frame["locationMode"] = "explicit"

    search_plan["place_intent_frame"] = frame
    search_plan["locationQuery"] = anchor
    search_plan["location_query"] = anchor
    search_plan["baseLocationQuery"] = anchor
    search_plan["base_location_query"] = anchor
    search_plan["anchorLocation"] = anchor
    search_plan["anchor_location"] = anchor
    search_plan["locationMode"] = "explicit"
    search_plan["location_mode"] = "explicit"
    search_plan["has_explicit_location"] = True
    search_plan["location_resolution_required"] = True
    search_plan["kakaoKeywordCandidates"] = _apply_anchor_location_to_keywords(
        anchor,
        [
            *search_plan.get("kakaoKeywordCandidates", []),
            *search_plan.get("kakao_keyword_candidates", []),
            *frame.get("search_queries", []),
            *frame.get("target_objects", []),
            *frame.get("result_match_terms", []),
            *frame.get("candidate_place_types", []),
            frame.get("display_label"),
        ],
    )
    search_plan["kakao_keyword_candidates"] = search_plan["kakaoKeywordCandidates"]
    frame["search_queries"] = _apply_anchor_location_to_keywords(
        anchor,
        [
            *frame.get("search_queries", []),
            *frame.get("target_objects", []),
            *frame.get("result_match_terms", []),
            *frame.get("candidate_place_types", []),
            frame.get("display_label"),
        ],
    )
    search_plan["search_queries"] = frame["search_queries"]
    search_plan["target_objects"] = frame.get("target_objects", [])
    search_plan["result_match_terms"] = frame.get("result_match_terms", [])
    search_plan["ranking_policy"] = frame.get("ranking_policy", "")

    return anchor


def _can_use_ai_intent_interpreter():
    return _get_ai_intent_unavailable_reason() == ""


def _get_ai_intent_unavailable_reason():
    if getattr(settings, "CONVERSATIONAL_SEARCH_AI_ENABLED", False) is not True:
        return "conversational_search_ai_disabled"

    provider = getattr(settings, "AI_PROVIDER", "gms").lower()
    if provider != "gms":
        return f"unsupported_ai_provider:{provider}"

    if not getattr(settings, "GMS_API_KEY", ""):
        return "missing_gms_api_key"

    if not (
        getattr(settings, "GMS_API_URL", "")
        or getattr(settings, "GMS_API_BASE_URL", "")
    ):
        return "missing_gms_api_url"

    return ""


def _mark_legacy_fallback(plan, ai_reason=""):
    plan = plan or _empty_plan("")
    search_plan = plan.get("search_plan") if isinstance(plan.get("search_plan"), dict) else {}
    search_plan["execution_mode"] = "legacy"
    search_plan["plan_source"] = "legacy_fallback"
    if ai_reason:
        search_plan["ai_fallback_reason"] = ai_reason
    plan["search_plan"] = search_plan
    plan["execution_mode"] = "legacy"
    plan["plan_source"] = "legacy_fallback"
    plan["parser_provider"] = plan.get("parser_provider") or "rule"
    plan["parser_fallback"] = True
    if ai_reason:
        plan["ai_fallback_reason"] = ai_reason
        plan["ai_debug"] = {
            "status": "fallback",
            "reason": ai_reason,
        }
    return plan


def _is_ai_frame_execution_plan(plan):
    if not isinstance(plan, dict):
        return False
    if plan.get("parser_fallback") is True:
        return False
    if plan.get("plan_source") == "legacy_fallback":
        return False
    search_plan = plan.get("search_plan") if isinstance(plan.get("search_plan"), dict) else {}
    frame = search_plan.get("place_intent_frame") if isinstance(search_plan.get("place_intent_frame"), dict) else {}
    return _is_valid_place_intent_frame(frame)


def _should_use_ai_intent_fallback(query, rule_plan, lat=None, lng=None, map_center=None, previous_context=None):
    if getattr(settings, "CONVERSATIONAL_SEARCH_AI_ENABLED", False) is not True:
        return False

    if getattr(settings, "AI_PROVIDER", "gms").lower() != "gms":
        return False

    action = rule_plan.get("action")
    search_plan = rule_plan.get("search_plan") if isinstance(rule_plan.get("search_plan"), dict) else {}
    scenario = search_plan.get("scenario")

    if action in {"blocked", "out_of_scope", "refine_previous_search"}:
        return False

    if action == "ask_clarification" and rule_plan.get("fallback_reason") in {
        "missing_purpose",
        "refinement_without_context",
        "ambiguous_reference_without_context",
    }:
        return False

    if scenario == "smoking_area":
        return False

    if _has_any(query, AI_INTENT_FALLBACK_HINTS):
        return True

    if action == "search" and not _has_any(query, SEARCH_COMMAND_HINTS):
        return True

    return False


def _categories_for_scenario(scenario):
    for rule_scenario, _, categories, _, _ in SCENARIO_RULES:
        if rule_scenario == scenario:
            return list(categories)
    return ["cafe", "shelter"] if scenario == "waiting_place" else ["cafe"]


def _normalize_ai_scenario(value, target_query="", fallback="waiting_place"):
    scenario = _clean_text(value)
    if scenario in ALLOWED_SCENARIOS:
        return scenario

    scenario = AI_SCENARIO_ALIASES.get(scenario, scenario)
    if scenario in ALLOWED_SCENARIOS:
        return scenario

    target_text = _compact(target_query)
    if any(keyword in target_text for keyword in ["스터디", "작업", "노트북", "카페"]):
        return "work_cafe"
    if any(keyword in target_text for keyword in ["산책", "걷", "바람", "공원"]):
        return "walk_healing"
    if any(keyword in target_text for keyword in ["흡연", "담배"]):
        return "smoking_area"

    return fallback if fallback in ALLOWED_SCENARIOS else "waiting_place"


def _looks_like_ai_generated_address_or_coordinate(value):
    text = _clean_text(value)
    if not text:
        return False
    if re.search(r"\d+\.\d+\s*,\s*\d+\.\d+", text):
        return True
    if re.search(r"\d{2,}\s*(?:번길|길|로|번지)", text):
        return True
    return any(keyword in text for keyword in ["위도", "경도", "주소:", "도로명"])


def _sanitize_ai_location_query(value):
    text = _clean_location_text(value)
    if not text or _looks_like_ai_generated_address_or_coordinate(text):
        return ""
    if len(text) > 60:
        return ""
    return text


def _sanitize_ai_target_query(value, scenario, fallback_target=""):
    text = _clean_target_query(value)
    if _looks_like_ai_generated_address_or_coordinate(text):
        text = ""

    if scenario == "work_cafe":
        if not text or any(keyword in _compact(text) for keyword in ["스터디", "작업", "노트북", "카페"]):
            return "카페"
    if scenario == "walk_healing":
        if not text or any(keyword in _compact(text) for keyword in ["산책", "걷", "바람", "공원"]):
            return "산책할 곳"
    if scenario == "waiting_place":
        if not text or any(keyword in _compact(text) for keyword in ["쉬", "쉴", "앉", "쉼"]):
            return "쉴 곳"
    if scenario == "smoking_area":
        return "흡연구역"

    return text or fallback_target or _derive_target_query("", scenario, [])


def _build_ai_plan(query, fallback_plan):
    if getattr(settings, "CONVERSATIONAL_SEARCH_AI_ENABLED", False) is not True:
        return None, "conversational_search_ai_disabled"

    provider = getattr(settings, "AI_PROVIDER", "gms").lower()
    if provider != "gms":
        return None, f"unsupported_ai_provider:{provider}"

    if not getattr(settings, "GMS_API_KEY", ""):
        return None, "missing_gms_api_key"

    if not (
        getattr(settings, "GMS_API_URL", "")
        or getattr(settings, "GMS_API_BASE_URL", "")
    ):
        return None, "missing_gms_api_url"

    try:
        max_attempts = int(getattr(settings, "CONVERSATIONAL_SEARCH_AI_MAX_ATTEMPTS", 2) or 2)
    except (TypeError, ValueError):
        max_attempts = 2
    max_attempts = max(1, max_attempts)
    last_error_reason = ""
    for attempt_index in range(max_attempts):
        try:
            plan = _call_gms_chat_json(
                query=json.dumps(
                    {
                        "query": query,
                        "fallback_plan": fallback_plan,
                    },
                    ensure_ascii=False,
                ),
                system_prompt=CONVERSATIONAL_SEARCH_SYSTEM_PROMPT,
                max_completion_tokens=900,
            )
            if isinstance(plan, dict):
                plan["ai_retry_count"] = attempt_index
            return plan, ""
        except Exception as exc:
            logger.debug("Conversational search planner AI call failed.", exc_info=True)
            last_error_reason = f"ai_call_failed:{exc.__class__.__name__}"
    return None, last_error_reason or "ai_call_failed"


def _repair_ai_frame_location(query, frame, search_plan=None):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    debug = {
        "status": "skipped",
        "reason": "",
        "checked_location_mode": "",
        "checked_anchor_location": "",
        "frame_location_mode": "",
        "frame_anchor_location": "",
        "plan_location_mode": "",
        "plan_anchor_location": "",
        "plan_location_query": "",
    }

    if not isinstance(frame, dict):
        debug["reason"] = "missing_frame"
        return "", debug

    frame_location_mode = _clean_text(
        frame.get("location_mode")
        or frame.get("locationMode")
        or ""
    )
    frame_anchor_location = _sanitize_ai_location_query(
        frame.get("anchor_location")
        or frame.get("anchorLocation")
        or ""
    )
    plan_location_mode = _clean_text(
        search_plan.get("location_mode")
        or search_plan.get("locationMode")
        or ""
    )
    plan_anchor_location = _sanitize_ai_location_query(
        search_plan.get("anchor_location")
        or search_plan.get("anchorLocation")
        or ""
    )
    plan_location_query = _sanitize_ai_location_query(
        search_plan.get("locationQuery")
        or search_plan.get("location_query")
        or search_plan.get("baseLocationQuery")
        or search_plan.get("base_location_query")
        or ""
    )
    checked_location_mode = frame_location_mode or plan_location_mode
    checked_anchor_location = frame_anchor_location or plan_anchor_location

    debug.update({
        "checked_location_mode": checked_location_mode,
        "checked_anchor_location": checked_anchor_location,
        "frame_location_mode": frame_location_mode,
        "frame_anchor_location": frame_anchor_location,
        "plan_location_mode": plan_location_mode,
        "plan_anchor_location": plan_anchor_location,
        "plan_location_query": plan_location_query,
    })

    if not _clean_text(query):
        debug["reason"] = "missing_query"
        return "", debug

    if checked_location_mode != "current_context" or checked_anchor_location:
        debug["reason"] = "not_current_context_without_anchor"
        return "", debug

    try:
        response = _call_gms_chat_json(
            query=json.dumps(
                {
                    "query": query,
                    "place_intent_frame": frame,
                },
                ensure_ascii=False,
            ),
            system_prompt=LOCATION_REPAIR_SYSTEM_PROMPT,
            max_completion_tokens=180,
        )
    except Exception as exc:
        logger.debug("Conversational search location repair failed.", exc_info=True)
        debug["status"] = "failed"
        debug["reason"] = f"location_repair_failed:{exc.__class__.__name__}"
        return "", {
            **debug,
        }

    anchor = ""
    if isinstance(response, dict):
        anchor = _sanitize_ai_location_query(
            response.get("explicit_anchor_location")
            or response.get("anchor_location")
            or response.get("location")
            or ""
        )

    debug.update({
        "status": "repaired" if anchor else "executed",
        "reason": "explicit_anchor_location_found" if anchor else "no_explicit_location_found",
        "explicit_anchor_location": anchor,
    })
    return anchor, debug


def _apply_ai_location_repair(frame, anchor_location):
    anchor_location = _sanitize_ai_location_query(anchor_location)
    if not anchor_location:
        return frame

    repaired_frame = {
        **frame,
        "anchor_location": anchor_location,
        "location_mode": "explicit",
    }
    search_keywords = _sanitize_frame_list([
        *repaired_frame.get("search_queries", []),
        *repaired_frame.get("candidate_place_types", []),
        repaired_frame.get("display_label"),
    ])
    repaired_frame["search_queries"] = _unique([
        *[
            keyword
            for keyword in search_keywords
            if _compact(anchor_location) in _compact(keyword)
        ],
        *[
            f"{anchor_location} {keyword}".strip()
            for keyword in search_keywords
            if _compact(anchor_location) not in _compact(keyword)
        ],
    ])
    return repaired_frame


def _apply_anchor_location_to_keywords(anchor_location, keywords):
    anchor_location = _sanitize_ai_location_query(anchor_location)
    safe_keywords = _sanitize_frame_list(keywords)
    if not anchor_location:
        return safe_keywords

    anchor_text = _compact(anchor_location)
    location_keywords = [
        keyword
        if anchor_text and anchor_text in _compact(keyword)
        else f"{anchor_location} {keyword}".strip()
        for keyword in safe_keywords
    ]
    return _unique([*location_keywords, *safe_keywords])


CONVERSATIONAL_SEARCH_SYSTEM_PROMPT = """
너는 장소 추천 서비스의 AI Intent Interpreter다. 실제 장소 추천 결과를 만들지 말고 사용자의 장소 검색 의도를 의미 단위로 구조화한 검색 계획만 JSON으로 반환한다.

반드시 지킬 규칙:
- JSON object만 반환한다.
- 장소명, 주소, 좌표, 영업 여부, 시설 여부, 메뉴 제공 여부를 새로 만들거나 단정하지 않는다.
- 사용자가 명시한 지역/역/복합 기준 위치는 현재 위치나 지도 중심으로 덮어쓰지 않는다. 예: "서면역 롯데백화점", "광안리 해수욕장"은 가능한 한 전체를 유지한다.
- 사용자가 텍스트로 위치를 말했으면 절대 current_context로 덮지 않는다. 현재 좌표/mapCenter는 사용자가 위치를 말하지 않았을 때만 사용한다.
- "하단역인데"의 "하단역"은 현재 위치 설명이 아니라 검색 기준 위치다.
- 위치가 명시되지 않으면 location.fallback에 current_location 또는 map_center를 넣고 location.text는 비워둔다.
- "거기", "아까", "그곳"처럼 이전 맥락이 필요한 표현인데 previous_context가 없으면 action은 ask_clarification으로 둔다.
- "밖 말고", "실외 말고", "사람 많은 데 말고", "붐비는 데 말고"는 이전 결과 refine이 아니라 신규 검색의 부정/선호 조건으로 본다.
- "카페 말고", "카페 느낌은 아니었으면", "카페 같지 않은"은 exclusions에 "카페 제외"를 넣고 candidate_place_types에서 카페를 제외한다.
- "쪽에서", "쪽", "근처", "주변", "앞" 같은 위치 접미사는 locationQuery에서 제거한다.
- 구어체, 사투리, 은어도 의미로 해석한다. 예: "똥 마려운데 우야노"는 toilet, "놋북 펼 데"는 work, "멍때리고 싶다"는 quiet_rest, "약 살 데"는 health_nearby다.
- 의료/건강 표현은 진단이나 복용 안내가 아니라 가까운 약국/병원 장소 찾기로만 해석한다.
- 하나의 scenario로 의도를 과도하게 압축하지 말고 search_plan.place_intent_frame을 반드시 채운다.
- 장소 추천과 무관한 일반 질문은 out_of_scope로 둔다.
- 불법적이거나 위험한 장소 이용 요청은 blocked로 둔다.
- scenario, intent_group, targetQuery는 기존 호환용 fallback이다. 의미 정보는 place_intent_frame에 보존한다.

place_intent_frame 규칙:
- situation 허용값: quiet_rest, rest, work, toilet, health_nearby, parking, wifi, weather_shelter, walk, food, smoking, general_place
- decision_action은 search, ask_clarification, out_of_scope, blocked, refine_previous_search 중 하나다. 실행 전 최상위 판단으로 action과 일치해야 한다.
- can_search_now는 지금 추천 실행에 충분하면 true, 되묻기/범위 밖/차단이면 false다.
- normalized_user_intent는 오타, 비속어, 사투리를 의미 중심으로 정리한 짧은 의도 요약이다.
- ask_clarification이면 clarification_question과 clarification_options를 채우고 검색 조건을 억지로 만들지 않는다.
- target_objects는 사용자가 실제로 찾는 대상/목적어다. 예: "쌀국수", "소금빵", "축구 연습", "무료로 시간 보내기", "작업할 공간".
- candidate_place_types는 여러 개 가능하다. 실제 장소명이나 브랜드명이 아니라 장소 유형만 넣는다.
- result_match_terms는 결과가 의도와 직접 맞는지 판단할 evidence 용어다. target_objects와 장소 유형을 모두 고려하되 실제 운영 여부는 단정하지 않는다.
- search_queries는 검색 실행용 문구다. 명시 위치가 있으면 위치를 포함한 query를 우선한다.
- 카페/쉼터/restaurant/식당/음식점처럼 넓은 기본 장소 유형은 사용자가 직접 말했거나 target_objects/result_match_terms/constraints/evidence와 직접 연결될 때만 넣는다. 확신할 수 없으면 기본 장소 유형을 채우지 말고 ask_clarification/out_of_scope로 둔다.
- ranking_policy는 evidence_first, urgent_nearest, cost_sensitive, distance_first 중 하나를 사용한다. 긴급 생활 인프라는 urgent_nearest로 둔다.
- anchor_location은 사용자가 말한 기준 위치다. 복합 위치를 임의로 잘라내지 않는다.
- "하단역인데 화장실 급해"는 anchor_location "하단역", location_mode "explicit", target_objects ["화장실"], candidate_place_types ["공중화장실", "화장실"], ranking_policy "urgent_nearest"다.
- "서면역 롯데백화점 근처 쉴 곳"은 anchor_location "서면역 롯데백화점", location_mode "explicit"이다.
- "똥 마려운데 우야노"는 명시 위치가 없으므로 location_mode "current_context" 또는 "clarification_required"이고 anchor_location은 빈 문자열이다.
- 모호하면 missing_info와 ambiguity를 채우고 clarification_question을 만든다.
- safety_note는 의료/위험 관련 장소 안내 수준의 짧은 문구만 허용한다.

반환 스키마:
{
  "action": "search | ask_clarification | out_of_scope | blocked | refine_previous_search",
  "intent_type": "place_recommendation | out_of_scope | unsafe_request",
  "user_intent_summary": "짧은 한국어 요약",
  "message": "",
  "location": {"text": "", "is_explicit": false, "fallback": "current_location"},
  "targets": [],
  "conditions": [],
  "preferences": [],
  "avoid": [],
  "search_plan": {
    "locationQuery": "",
    "baseLocationQuery": "",
    "targetQuery": "",
    "targetType": "",
    "scenario": "",
    "categories": [],
    "categoryHint": "",
    "menu_keywords": [],
    "place_type_keywords": [],
    "required_tags": [],
    "preferred_tags": [],
    "requestedConditions": [],
    "place_intent_frame": {
      "decision_action": "search | ask_clarification | out_of_scope | blocked | refine_previous_search",
      "user_goal": "",
      "normalized_user_intent": "",
      "anchor_location": "",
      "location_mode": "explicit | current_context | clarification_required",
      "situation": "general_place",
      "display_label": "",
      "target_objects": [],
      "candidate_category_codes": [],
      "candidate_place_types": [],
      "search_queries": [],
      "result_match_terms": [],
      "constraints": [],
      "exclusions": [],
      "preferred_place_natures": [],
      "excluded_place_natures": [],
      "ranking_policy": "",
      "missing_info": [],
      "assumptions": [],
      "clarification_question": "",
      "clarification_options": [],
      "can_search_now": true,
      "ambiguity": [],
      "safety_note": "",
      "confidence": 0.0
    }
  },
  "execution_policy": {
    "run_search": true,
    "preserve_explicit_location": false,
    "allow_kakao_fallback": true,
    "allow_ai_web_search_auto": false,
    "merge_ai_web_results": false
  },
  "needs_clarification": false,
  "clarification_question": "",
  "blocked_reason": "",
  "out_of_scope_reason": "",
  "confidence": 0,
  "fallback_reason": ""
}
""".strip()


LOCATION_REPAIR_SYSTEM_PROMPT = """
너는 장소 검색 계획의 위치만 검수하는 AI Location Repair다. JSON object만 반환한다.

목표:
- original query 안에 사용자가 말한 기준 위치, 지역, 역, 건물, 상권, 랜드마크가 있으면 exact text에 가깝게 explicit_anchor_location에 넣는다.
- 현재 위치, mapCenter, 좌표는 사용자가 텍스트로 위치를 말하지 않았을 때만 쓴다. 이 경우 explicit_anchor_location은 빈 문자열이다.
- 장소 유형, 후보, 조건은 판단하지 않는다. 위치만 판단한다.
- 주소나 좌표를 새로 만들지 않는다.
- "하단역인데"의 "하단역"은 검색 기준 위치다.

예시:
- query: "하단역인데 화장실 급해" -> {"explicit_anchor_location": "하단역"}
- query: "서면역 롯데백화점 근처 쉴 곳" -> {"explicit_anchor_location": "서면역 롯데백화점"}
- query: "똥 마려운데 우야노" -> {"explicit_anchor_location": ""}

반환 스키마:
{"explicit_anchor_location": ""}
""".strip()


def _normalize_ai_plan(raw_plan, query, fallback_plan, lat=None, lng=None, map_center=None, previous_context=None):
    if not isinstance(raw_plan, dict):
        return None

    action = raw_plan.get("action")
    if action not in ROUTER_ACTIONS:
        return _clarification_plan(
            query,
            question=PURPOSE_CLARIFICATION_MESSAGE,
            reason="invalid_ai_action",
            target_query="",
            fallback_location="current_location",
        )

    if action == "blocked":
        plan = _blocked_plan(query)
        plan["message"] = _clean_text(raw_plan.get("message")) or plan["message"]
        plan["blocked_reason"] = _clean_text(raw_plan.get("blocked_reason")) or plan["blocked_reason"]
        plan["confidence"] = _normalize_confidence(raw_plan.get("confidence"), plan["confidence"])
        plan["parser_provider"] = "gms"
        plan["parser_fallback"] = False
        plan["plan_source"] = "ai"
        plan["execution_mode"] = "decision_gate"
        return plan

    if action == "out_of_scope":
        plan = _out_of_scope_plan(query)
        plan["message"] = _clean_text(raw_plan.get("message")) or plan["message"]
        plan["out_of_scope_reason"] = _clean_text(raw_plan.get("out_of_scope_reason")) or plan["out_of_scope_reason"]
        plan["confidence"] = _normalize_confidence(raw_plan.get("confidence"), plan["confidence"])
        plan["parser_provider"] = "gms"
        plan["parser_fallback"] = False
        plan["plan_source"] = "ai"
        plan["execution_mode"] = "decision_gate"
        return plan

    search_plan = raw_plan.get("search_plan") or {}
    if not isinstance(search_plan, dict):
        search_plan = {}

    top_level_plan_keys = {
        "scenario": "scenario",
        "locationQuery": "locationQuery",
        "location_query": "locationQuery",
        "targetQuery": "targetQuery",
        "target_query": "targetQuery",
        "conditions": "requestedConditions",
    }
    search_plan = {
        **search_plan,
        **{
            target_key: raw_plan.get(source_key)
            for source_key, target_key in top_level_plan_keys.items()
            if raw_plan.get(source_key) not in (None, "", [])
        },
    }
    raw_place_frame = search_plan.get("place_intent_frame") or search_plan.get("placeIntentFrame") or raw_plan.get("place_intent_frame")
    normalized_place_frame = (
        _normalize_place_intent_frame(raw_place_frame, user_query=query)
        if isinstance(raw_place_frame, dict)
        else {}
    )
    fallback_search_plan = fallback_plan["search_plan"]
    frame_intent_group = _intent_group_for_situation(normalized_place_frame.get("situation"))
    location_repair_debug = {"status": "skipped", "reason": "not_attempted"}
    if action == "search" and normalized_place_frame:
        repaired_anchor, location_repair_debug = _repair_ai_frame_location(
            query,
            normalized_place_frame,
            search_plan=search_plan,
        )
        if repaired_anchor:
            normalized_place_frame = _apply_ai_location_repair(normalized_place_frame, repaired_anchor)
            search_plan["locationQuery"] = repaired_anchor
            search_plan["baseLocationQuery"] = repaired_anchor
            frame_intent_group = _intent_group_for_situation(normalized_place_frame.get("situation"))
    has_valid_frame = _is_valid_place_intent_frame(normalized_place_frame)

    if action == "search" and not has_valid_frame:
        normalized_place_frame = _repair_ai_place_intent_frame(
            search_plan=search_plan,
            raw_plan=raw_plan,
            user_query=query,
            fallback_search_plan=fallback_search_plan,
        )
        frame_intent_group = _intent_group_for_situation(normalized_place_frame.get("situation"))
        has_valid_frame = _is_valid_place_intent_frame(normalized_place_frame)

    if action == "search" and not has_valid_frame:
        return _clarification_plan(
            query,
            question=_clean_text(raw_plan.get("clarification_question")) or PURPOSE_CLARIFICATION_MESSAGE,
            reason="ai_invalid_place_intent_frame",
            target_query=_first_text(search_plan.get("targetQuery"), search_plan.get("target_query")),
            fallback_location="current_location",
        )

    post_validation_reasons = (
        _get_ai_frame_post_validation_reasons(normalized_place_frame, query)
        if action == "search" and has_valid_frame
        else []
    )
    if post_validation_reasons:
        plan = _ai_frame_post_validation_clarification_plan(
            query=query,
            raw_plan=raw_plan,
            search_plan=search_plan,
            frame=normalized_place_frame,
            reasons=post_validation_reasons,
        )
        plan.setdefault("ai_debug", {})
        plan["ai_debug"]["location_repair"] = location_repair_debug
        return plan

    location_text = _sanitize_ai_location_query(
        _first_text(
            normalized_place_frame.get("anchor_location"),
            search_plan.get("locationQuery"),
            search_plan.get("location_query"),
            raw_plan.get("location", {}).get("text") if isinstance(raw_plan.get("location"), dict) else "",
            fallback_search_plan.get("locationQuery"),
        )
    )
    raw_target_query = _clean_target_query(
        _first_text(
            normalized_place_frame.get("display_label"),
            search_plan.get("targetQuery"),
            search_plan.get("target_query"),
            fallback_search_plan.get("targetQuery"),
        )
    )
    fallback_scenario = _normalize_scenario(fallback_search_plan.get("scenario"))
    scenario = _normalize_ai_scenario(
        _first_text(search_plan.get("scenario"), raw_plan.get("scenario")),
        target_query=raw_target_query,
        fallback=(
            INTENT_GROUP_CONFIGS.get(frame_intent_group, {}).get("scenario")
            or fallback_scenario
        ),
    )
    force_query_policy = False if has_valid_frame else _should_force_query_intent_policy(query)
    if has_valid_frame:
        policy_categories, policy_kakao_keywords, policy_preferred_tags = [], [], []
    else:
        scenario, policy_categories, policy_kakao_keywords, policy_preferred_tags = _apply_query_intent_overrides(
            query,
            scenario,
            _categories_for_scenario(scenario),
            [],
            [],
        )
    target_query = (
        raw_target_query
        if has_valid_frame
        else _sanitize_ai_target_query(
            raw_target_query,
            scenario,
            fallback_target=fallback_search_plan.get("targetQuery"),
        )
    )
    if not has_valid_frame and scenario == "waiting_place" and _has_waiting_place_natural_intent(query):
        target_query = "쉴 곳"
    elif not has_valid_frame and scenario == "walk_healing" and _has_walk_healing_natural_intent(query):
        target_query = "산책할 곳"
    elif not has_valid_frame and scenario == "work_cafe" and not _has_cafe_negative_preference(query):
        target_query = "카페"

    categories = (
        normalized_place_frame.get("candidate_category_codes") or []
        if has_valid_frame
        else _normalize_categories(search_plan.get("categories") or [])
    )
    if not has_valid_frame and (
        force_query_policy or not categories or any(category not in ALLOWED_CATEGORIES for category in categories)
    ):
        categories = policy_categories or _categories_for_scenario(scenario)
    menu_keywords = [] if has_valid_frame else _normalize_text_list(search_plan.get("menu_keywords") or fallback_search_plan.get("menu_keywords") or [])
    place_type_keywords = (
        normalized_place_frame.get("candidate_place_types") or []
        if has_valid_frame
        else _normalize_text_list(search_plan.get("place_type_keywords") or fallback_search_plan.get("place_type_keywords") or [])
    )
    if has_valid_frame:
        conditions = _sanitize_requested_conditions([
            *_sanitize_frame_list(normalized_place_frame.get("constraints") or []),
            *_sanitize_frame_list(normalized_place_frame.get("exclusions") or []),
        ])
        preferred_tags = []
        required_tags = []
    else:
        conditions = _normalize_text_list(
            raw_plan.get("conditions")
            or search_plan.get("conditions")
            or search_plan.get("requestedConditions")
            or search_plan.get("requested_conditions")
            or []
        )
        conditions = _sanitize_requested_conditions([
            *conditions,
            *_sanitize_frame_list(normalized_place_frame.get("constraints") or []),
            *_sanitize_frame_list(normalized_place_frame.get("exclusions") or []),
            *_extract_conditions(query),
        ])
        preferred_tags = _normalize_tags(search_plan.get("preferred_tags") or raw_plan.get("preferences") or fallback_search_plan.get("preferred_tags") or [])
        preferred_tags = _unique([
            *preferred_tags,
            *policy_preferred_tags,
            *[tag for _, _, tag in _matched_condition_rules(query) if tag],
        ])
        required_tags = _normalize_tags(search_plan.get("required_tags") or fallback_search_plan.get("required_tags") or [])

    if action == "search" and not target_query:
        return _clarification_plan(
            query,
            question=PURPOSE_CLARIFICATION_MESSAGE,
            reason="ai_missing_target",
            target_query="",
            fallback_location="current_location",
        )

    if (
        action == "search"
        and not has_valid_frame
        and not location_text
        and not _has_coordinate_context(lat, lng, map_center)
        and _requires_location_before_search(query, scenario, target_query)
    ):
        return _clarification_plan(
            query,
            question=_missing_location_question(query, scenario),
            reason="ai_missing_location_context",
            target_query=target_query,
            fallback_location="current_location",
        )

    normalized_search_plan = _search_plan_payload(
        original_query=query,
        location_query=location_text,
        target_query=target_query,
        scenario=scenario,
        categories=categories,
        menu_keywords=menu_keywords,
        place_type_keywords=place_type_keywords,
        required_tags=required_tags,
        preferred_tags=preferred_tags,
        requested_conditions=conditions,
        kakao_keyword_candidates=_normalize_text_list(
            (
                [
                    *normalized_place_frame.get("search_queries", []),
                    *normalized_place_frame.get("candidate_place_types", []),
                ]
                if has_valid_frame
                else (
                    [*policy_kakao_keywords, target_query]
                    if force_query_policy
                    else search_plan.get("kakaoKeywordCandidates")
                )
            )
            or search_plan.get("kakao_keyword_candidates")
            or fallback_search_plan.get("kakaoKeywordCandidates")
            or []
        ),
    )
    excluded_categories = [] if has_valid_frame else _extract_excluded_categories(query)
    if excluded_categories:
        normalized_search_plan["excluded_categories"] = excluded_categories
    if normalized_place_frame:
        frame_anchor_location = _sanitize_ai_location_query(
            normalized_place_frame.get("anchor_location")
            or normalized_place_frame.get("anchorLocation")
            or ""
        )
        if frame_anchor_location:
            normalized_search_plan["locationQuery"] = frame_anchor_location
            normalized_search_plan["baseLocationQuery"] = frame_anchor_location
            normalized_search_plan["anchorLocation"] = frame_anchor_location
            normalized_search_plan["anchor_location"] = frame_anchor_location
            normalized_search_plan["has_explicit_location"] = True
            normalized_search_plan["location_resolution_required"] = True
            normalized_place_frame["search_queries"] = _apply_anchor_location_to_keywords(
                frame_anchor_location,
                [
                    *normalized_place_frame.get("search_queries", []),
                    *normalized_place_frame.get("target_objects", []),
                    *normalized_place_frame.get("result_match_terms", []),
                    *normalized_place_frame.get("candidate_place_types", []),
                    normalized_place_frame.get("display_label"),
                ],
            )
            normalized_search_plan["kakaoKeywordCandidates"] = _apply_anchor_location_to_keywords(
                frame_anchor_location,
                [
                    *normalized_search_plan.get("kakaoKeywordCandidates", []),
                    *normalized_place_frame.get("target_objects", []),
                    *normalized_place_frame.get("result_match_terms", []),
                    *normalized_place_frame.get("candidate_place_types", []),
                    normalized_place_frame.get("display_label"),
                ],
            )
        normalized_search_plan["place_intent_frame"] = normalized_place_frame
        normalized_search_plan["location_mode"] = normalized_place_frame.get("location_mode")
        normalized_search_plan["candidate_category_codes"] = normalized_place_frame.get("candidate_category_codes", [])
        normalized_search_plan["target_objects"] = normalized_place_frame.get("target_objects", [])
        normalized_search_plan["candidate_place_types"] = normalized_place_frame.get("candidate_place_types", [])
        normalized_search_plan["search_queries"] = normalized_place_frame.get("search_queries", [])
        normalized_search_plan["result_match_terms"] = normalized_place_frame.get("result_match_terms", [])
        normalized_search_plan["constraints"] = normalized_place_frame.get("constraints", [])
        normalized_search_plan["exclusions"] = normalized_place_frame.get("exclusions", [])
        normalized_search_plan["preferred_place_natures"] = normalized_place_frame.get("preferred_place_natures", [])
        normalized_search_plan["excluded_place_natures"] = normalized_place_frame.get("excluded_place_natures", [])
        normalized_search_plan["ranking_policy"] = normalized_place_frame.get("ranking_policy", "")
    if frame_intent_group:
        normalized_search_plan["intent_group"] = frame_intent_group
    if action == "search":
        normalized_search_plan["execution_mode"] = "frame" if has_valid_frame else "legacy"
        normalized_search_plan["plan_source"] = "ai" if has_valid_frame else "legacy_fallback"
    else:
        normalized_search_plan["execution_mode"] = "decision_gate"
        normalized_search_plan["plan_source"] = "ai"
    normalized_search_plan["decision_action"] = action
    normalized_search_plan["decisionAction"] = action
    normalized_search_plan["can_search_now"] = action == "search" and not bool(raw_plan.get("needs_clarification"))
    normalized_search_plan["ai_retry_count"] = int(raw_plan.get("ai_retry_count") or 0)
    normalized_search_plan["aiRetryCount"] = normalized_search_plan["ai_retry_count"]

    needs_clarification = bool(raw_plan.get("needs_clarification")) or action == "ask_clarification"
    clarification_options = _normalize_text_list(
        raw_plan.get("clarification_options")
        or raw_plan.get("clarificationOptions")
        or []
    )
    return {
        "action": action,
        "decision_action": action,
        "intent_type": "place_recommendation",
        "user_intent_summary": _clean_text(raw_plan.get("user_intent_summary")) or fallback_plan["user_intent_summary"],
        "message": _clean_text(raw_plan.get("message")),
        "location": _location_payload(
            location_text,
            bool(location_text),
            "" if location_text else fallback_plan["location"].get("fallback", "current_location"),
        ),
        "targets": _normalize_text_list(raw_plan.get("targets") or fallback_plan.get("targets") or []),
        "conditions": conditions,
        "preferences": preferred_tags,
        "avoid": _normalize_text_list(raw_plan.get("avoid") or fallback_plan.get("avoid") or []),
        "search_plan": normalized_search_plan,
        "execution_policy": _execution_policy(action == "search" and not needs_clarification, bool(location_text)),
        "needs_clarification": needs_clarification,
        "clarification_question": _clean_text(raw_plan.get("clarification_question")) if needs_clarification else "",
        "clarification_options": clarification_options,
        "can_search_now": action == "search" and not needs_clarification,
        "results": [],
        "blocked_reason": "",
        "out_of_scope_reason": "",
        "confidence": _normalize_confidence(raw_plan.get("confidence"), fallback_plan["confidence"]),
        "fallback_reason": "ai_planner",
        "parser_provider": "gms",
        "parser_fallback": False,
        "ai_retry_count": int(raw_plan.get("ai_retry_count") or 0),
        "execution_mode": (
            "frame"
            if action == "search" and has_valid_frame
            else ("legacy" if action == "search" else "decision_gate")
        ),
        "plan_source": "ai" if (has_valid_frame or action != "search") else "legacy_fallback",
        "ai_debug": {
            "location_repair": location_repair_debug,
        },
    }


def _extract_location_and_target(query):
    text = _clean_text(query)
    explicit_patterns = [
        rf"^(.+?)\s*(?:근처에서|주변에서|인근에서|앞에서|근처|주변|인근|앞)(?:에서|의)?\s+(.+)$",
        rf"^(.+?({'|'.join(LOCATION_SUFFIXES)}))\s*(?:근처에서|주변에서|인근에서|앞에서|쪽에서|근처|주변|인근|에서|쪽|앞|일대|지역)?\s+(.+)$",
        rf"^(.+?)에서\s+(.+)$",
    ]

    for pattern in explicit_patterns:
        match = re.match(pattern, text)
        if not match:
            continue

        location_query = _clean_location_text(match.group(1))
        target_query = _clean_target_query(match.group(3) if len(match.groups()) >= 3 else match.group(2))
        if location_query and target_query and not _looks_like_non_location(location_query):
            return location_query, target_query

    trailing_patterns = [
        rf"^(.+?)\s+([^\s]+(?:{'|'.join(LOCATION_SUFFIXES)}))$",
        rf"^(.+?)\s+(.+?({'|'.join(LOCATION_SUFFIXES)}))$",
    ]
    for trailing_pattern in trailing_patterns:
        trailing_match = re.match(trailing_pattern, text)
        if not trailing_match:
            continue
        target_query = _clean_target_query(trailing_match.group(1))
        location_query = _clean_location_text(trailing_match.group(2))
        if location_query and target_query and not _looks_like_non_location(location_query):
            return location_query, target_query

    return "", _clean_target_query(text)


def _clean_location_text(value):
    return _normalize_location_query(value)


def _normalize_location_query(value):
    text = _clean_text(value)
    text = re.sub(r"\s+", " ", text).strip(" ,.?!")
    if not text:
        return ""

    suffix_pattern = (
        r"(?:근처에서|주변에서|인근에서|앞에서|쪽에서|"
        r"근처|주변|인근|앞|쪽|에서|일대|지역)$"
    )
    previous_text = None
    while text and previous_text != text:
        previous_text = text
        text = re.sub(suffix_pattern, "", text).strip(" ,.?!")

    if _looks_like_non_location(text):
        return ""

    return text


def _clean_target_query(value):
    text = _clean_text(value)
    for pattern in COMMAND_PATTERNS:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.?!")
    return text


def _clean_text(value):
    return str(value or "").replace("\u200b", "").strip()


def _compact(value):
    return _clean_text(value).lower().replace(" ", "")


def _has_any(query, keywords):
    compact = _compact(query)
    return any(_compact(keyword) in compact for keyword in keywords)


def _has_coordinate_context(lat=None, lng=None, map_center=None):
    if lat not in (None, "") and lng not in (None, ""):
        return True

    if isinstance(map_center, dict):
        return map_center.get("lat") not in (None, "") and map_center.get("lng") not in (None, "")

    return False


def _is_broad_default_place_term(value):
    compact = _compact(value)
    if not compact:
        return False
    return compact in {_compact(term) for term in BROAD_DEFAULT_PLACE_TERMS}


def _remove_anchor_prefix(value, anchor_location=""):
    text = _clean_text(value)
    anchor = _clean_text(anchor_location)
    if not text or not anchor:
        return text
    compact_text = _compact(text)
    compact_anchor = _compact(anchor)
    if compact_anchor and compact_text.startswith(compact_anchor):
        return text[len(anchor):].strip()
    return text


def _has_direct_support_for_broad_default(term, *, query="", support_terms=None):
    compact = _compact(term)
    if not compact:
        return False
    if compact and compact in _compact(query):
        return True
    for support_term in support_terms or []:
        support_compact = _compact(support_term)
        if not support_compact:
            continue
        if compact == support_compact or compact in support_compact:
            return True
    return False


def _strip_broad_default_terms(values, *, query="", support_terms=None, anchor_location=""):
    kept = []
    for value in _sanitize_frame_list(values or []):
        core_value = _remove_anchor_prefix(value, anchor_location=anchor_location)
        if (
            _is_broad_default_place_term(core_value)
            and not _has_direct_support_for_broad_default(
                core_value,
                query=query,
                support_terms=support_terms,
            )
        ):
            continue
        kept.append(value)
    return _unique(kept)


def _strip_broad_default_frame_terms(frame, query=""):
    if not isinstance(frame, dict):
        return frame

    evidence_terms = _frame_evidence_terms(frame)
    direct_support_terms = _sanitize_frame_list([
        *(_sanitize_frame_list(frame.get("target_objects") or frame.get("targetObjects") or [])),
        *evidence_terms,
        *(_sanitize_frame_list(frame.get("constraints") or [])),
        frame.get("display_label"),
        frame.get("displayLabel"),
    ])
    anchor_location = frame.get("anchor_location") or frame.get("anchorLocation") or ""
    for key in (
        "candidate_category_codes",
        "candidateCategoryCodes",
        "candidate_place_types",
        "candidatePlaceTypes",
        "search_queries",
        "searchQueries",
        "result_match_terms",
        "resultMatchTerms",
    ):
        if key not in frame:
            continue
        frame[key] = _strip_broad_default_terms(
            frame.get(key) or [],
            query=query,
            support_terms=direct_support_terms,
            anchor_location=anchor_location,
        )
    return frame


def _is_blocked_query(query):
    return _has_any(query, BLOCKED_KEYWORDS)


def _has_place_recommendation_hint(query):
    return _has_any(query, PLACE_RECOMMENDATION_HINTS)


def _normalize_situation(value):
    situation = _clean_text(value)
    situation = SITUATION_ALIASES.get(situation, situation)
    if situation in SITUATION_TO_INTENT_GROUP:
        return situation
    return ""


def _intent_group_for_situation(situation):
    return SITUATION_TO_INTENT_GROUP.get(_normalize_situation(situation), "")


def _situation_for_intent_group(intent_group, query="", target_query="", scenario=""):
    if intent_group == "general_place_search" and _is_plain_rest_intent(query, target_query, scenario):
        return "rest"
    return INTENT_GROUP_TO_SITUATION.get(intent_group, "general_place")


def _is_plain_rest_intent(query="", target_query="", scenario=""):
    text = f"{query or ''} {target_query or ''}"
    if _has_quiet_rest_intent(text) or _has_work_place_intent(text):
        return False
    if scenario != "waiting_place":
        return False
    return _has_any(text, ["쉴 곳", "쉴곳", "쉴 데", "쉴데", "쉬고 싶", "잠깐 쉬", "잠깐쉬", "앉을 곳"])


def _normalize_place_intent_frame(raw_frame, user_query="", fallback=None):
    fallback = fallback or {}
    if not isinstance(raw_frame, dict):
        raw_frame = {}

    decision_action = _normalize_decision_action(
        raw_frame.get("decision_action")
        or raw_frame.get("decisionAction")
        or fallback.get("decision_action")
        or "search"
    )
    situation = _normalize_situation(raw_frame.get("situation")) or fallback.get("situation") or "general_place"
    anchor_location = _sanitize_frame_location(
        raw_frame.get("anchor_location")
        or raw_frame.get("anchorLocation")
        or fallback.get("anchor_location")
        or ""
    )
    location_mode = _normalize_frame_location_mode(
        raw_frame.get("location_mode")
        or raw_frame.get("locationMode")
        or fallback.get("location_mode"),
        anchor_location=anchor_location,
    )
    display_label = _safe_frame_text(raw_frame.get("display_label") or raw_frame.get("displayLabel") or fallback.get("display_label"))
    user_goal = _safe_frame_text(raw_frame.get("user_goal") or raw_frame.get("userGoal") or fallback.get("user_goal"))
    normalized_user_intent = _safe_frame_text(
        raw_frame.get("normalized_user_intent")
        or raw_frame.get("normalizedUserIntent")
        or fallback.get("normalized_user_intent")
        or user_goal
    )
    safety_note = _sanitize_safety_note(raw_frame.get("safety_note") or raw_frame.get("safetyNote") or fallback.get("safety_note"))
    confidence = _normalize_frame_confidence(raw_frame.get("confidence"), fallback.get("confidence", 0.0))
    target_objects = _sanitize_frame_list(
        raw_frame.get("target_objects")
        or raw_frame.get("targetObjects")
        or fallback.get("target_objects")
        or []
    )
    ranking_policy = _normalize_ranking_policy(
        raw_frame.get("ranking_policy")
        or raw_frame.get("rankingPolicy")
        or fallback.get("ranking_policy")
        or ""
    )

    frame = {
        "decision_action": decision_action,
        "decisionAction": decision_action,
        "user_goal": user_goal,
        "normalized_user_intent": normalized_user_intent,
        "normalizedUserIntent": normalized_user_intent,
        "anchor_location": anchor_location,
        "location_mode": location_mode,
        "situation": situation,
        "display_label": display_label,
        "target_objects": target_objects,
        "candidate_category_codes": _normalize_categories(
            raw_frame.get("candidate_category_codes")
            or raw_frame.get("candidateCategoryCodes")
            or fallback.get("candidate_category_codes")
            or []
        ),
        "candidate_place_types": _sanitize_frame_list(
            raw_frame.get("candidate_place_types")
            or raw_frame.get("candidatePlaceTypes")
            or fallback.get("candidate_place_types")
            or []
        ),
        "search_queries": _sanitize_frame_list(
            raw_frame.get("search_queries")
            or raw_frame.get("searchQueries")
            or fallback.get("search_queries")
            or []
        ),
        "result_match_terms": _sanitize_frame_list(
            raw_frame.get("result_match_terms")
            or raw_frame.get("resultMatchTerms")
            or fallback.get("result_match_terms")
            or []
        ),
        "constraints": _sanitize_frame_list(raw_frame.get("constraints") or fallback.get("constraints") or []),
        "exclusions": _sanitize_frame_list(raw_frame.get("exclusions") or fallback.get("exclusions") or []),
        "preferred_place_natures": _sanitize_frame_list(
            raw_frame.get("preferred_place_natures")
            or raw_frame.get("preferredPlaceNatures")
            or fallback.get("preferred_place_natures")
            or []
        ),
        "excluded_place_natures": _sanitize_frame_list(
            raw_frame.get("excluded_place_natures")
            or raw_frame.get("excludedPlaceNatures")
            or fallback.get("excluded_place_natures")
            or []
        ),
        "ranking_policy": ranking_policy,
        "evidence": raw_frame.get("evidence") or fallback.get("evidence") or [],
        "missing_info": _sanitize_frame_list(raw_frame.get("missing_info") or raw_frame.get("missingInfo") or fallback.get("missing_info") or []),
        "assumptions": _sanitize_frame_list(raw_frame.get("assumptions") or fallback.get("assumptions") or []),
        "clarification_question": _safe_frame_text(
            raw_frame.get("clarification_question")
            or raw_frame.get("clarificationQuestion")
            or fallback.get("clarification_question")
        ),
        "clarification_options": _sanitize_frame_list(
            raw_frame.get("clarification_options")
            or raw_frame.get("clarificationOptions")
            or fallback.get("clarification_options")
            or []
        ),
        "can_search_now": _normalize_frame_can_search(
            raw_frame.get("can_search_now")
            if "can_search_now" in raw_frame
            else raw_frame.get("canSearchNow"),
            decision_action,
        ),
        "ambiguity": _sanitize_frame_list(raw_frame.get("ambiguity") or fallback.get("ambiguity") or []),
        "safety_note": safety_note,
        "confidence": confidence,
    }
    if frame["target_objects"]:
        frame["result_match_terms"] = _unique([
            *frame["target_objects"],
            *frame["result_match_terms"],
        ])
    frame = _strip_broad_default_frame_terms(frame, query=user_query)
    if frame["situation"] == "health_nearby":
        frame["safety_note"] = _sanitize_safety_note(frame["safety_note"] or HEALTH_NEARBY_MESSAGE)
    return frame


def _build_place_intent_frame(
    search_plan,
    user_query,
    intent_group,
    config,
    requested_conditions,
    excluded_categories,
    existing_frame=None,
):
    existing_frame = existing_frame if isinstance(existing_frame, dict) else {}
    target_query = _first_text(search_plan.get("targetQuery"), search_plan.get("target_query"))
    scenario = _normalize_scenario(search_plan.get("scenario"))
    situation = (
        _normalize_situation(existing_frame.get("situation"))
        or _situation_for_intent_group(intent_group, user_query, target_query, scenario)
    )
    anchor_location = _first_text(
        existing_frame.get("anchor_location"),
        search_plan.get("locationQuery"),
        search_plan.get("location_query"),
        search_plan.get("baseLocationQuery"),
        search_plan.get("base_location_query"),
    )
    display_label = _first_text(existing_frame.get("display_label"), _display_label_for_frame(situation, target_query, config))
    target_objects = _unique([
        *_sanitize_frame_list(existing_frame.get("target_objects") or existing_frame.get("targetObjects") or []),
        *([target_query] if target_query else []),
    ])
    candidate_place_types = _unique([
        *_sanitize_frame_list(existing_frame.get("candidate_place_types") or []),
        *_candidate_place_types_for_frame(situation, config, excluded_categories),
    ])
    search_queries = _unique([
        *_sanitize_frame_list(existing_frame.get("search_queries") or []),
        *candidate_place_types,
    ])
    result_match_terms = _unique([
        *target_objects,
        *_sanitize_frame_list(existing_frame.get("result_match_terms") or []),
        *_normalize_categories(existing_frame.get("candidate_category_codes") or []),
        *candidate_place_types,
    ])
    constraints = _unique([
        *_sanitize_frame_list(existing_frame.get("constraints") or []),
        *(REST_FRAME_CONSTRAINTS if situation == "rest" else []),
        *requested_conditions,
    ])
    exclusions = _unique([
        *_sanitize_frame_list(existing_frame.get("exclusions") or []),
        *_exclusions_for_frame(excluded_categories, requested_conditions),
    ])
    if exclusions:
        candidate_place_types = [
            place_type
            for place_type in candidate_place_types
            if not _mentions_excluded_category(place_type, exclusions)
        ]
    fallback = {
        "user_goal": existing_frame.get("user_goal") or _user_goal_for_frame(situation, display_label),
        "anchor_location": anchor_location,
        "location_mode": existing_frame.get("location_mode") or ("explicit" if anchor_location else "current_context"),
        "situation": situation,
        "display_label": display_label,
        "target_objects": target_objects,
        "candidate_category_codes": _normalize_categories(
            existing_frame.get("candidate_category_codes")
            or search_plan.get("categories")
            or []
        ),
        "candidate_place_types": candidate_place_types,
        "search_queries": search_queries,
        "result_match_terms": result_match_terms,
        "constraints": constraints,
        "exclusions": exclusions,
        "preferred_place_natures": existing_frame.get("preferred_place_natures") or [],
        "excluded_place_natures": existing_frame.get("excluded_place_natures") or [],
        "ranking_policy": existing_frame.get("ranking_policy") or existing_frame.get("rankingPolicy") or "",
        "missing_info": existing_frame.get("missing_info") or [],
        "ambiguity": existing_frame.get("ambiguity") or [],
        "safety_note": existing_frame.get("safety_note") or (HEALTH_NEARBY_MESSAGE if situation == "health_nearby" else ""),
        "confidence": existing_frame.get("confidence", 0.82),
    }
    return _normalize_place_intent_frame(existing_frame, user_query=user_query, fallback=fallback)


def _display_label_for_frame(situation, target_query, config):
    labels = {
        "quiet_rest": "조용히 쉴 곳",
        "rest": "쉴 곳",
        "work": "작업할 곳",
        "toilet": "화장실",
        "health_nearby": "약국/병원",
        "parking": "주차장",
        "wifi": "무료 와이파이",
        "weather_shelter": "비 피할 곳",
        "walk": "산책할 곳",
        "food": "식당",
        "smoking": "흡연구역",
    }
    return labels.get(situation) or target_query or config.get("target_query") or "장소"


def _user_goal_for_frame(situation, display_label):
    goals = {
        "quiet_rest": "조용히 쉴 수 있는 장소 찾기",
        "rest": "잠깐 쉴 수 있는 장소 찾기",
        "work": "노트북 작업이나 공부를 할 수 있는 장소 찾기",
        "toilet": "가까운 화장실 찾기",
        "health_nearby": "가까운 약국이나 병원 찾기",
        "parking": "가까운 주차장 찾기",
        "wifi": "와이파이를 사용할 수 있는 장소 찾기",
        "weather_shelter": "날씨를 피하며 잠깐 머물 수 있는 장소 찾기",
        "walk": "걷거나 바람 쐴 수 있는 장소 찾기",
        "food": "식사할 수 있는 장소 찾기",
        "smoking": "흡연 가능한 장소 찾기",
    }
    return goals.get(situation) or f"{display_label or '장소'} 찾기"


def _candidate_place_types_for_frame(situation, config, excluded_categories=None):
    if situation == "rest":
        candidates = REST_FRAME_PLACE_TYPES
    else:
        candidates = [
            candidate.get("name")
            for candidate in config.get("category_candidates", [])
            if isinstance(candidate, dict)
        ]
    return [
        candidate
        for candidate in _sanitize_frame_list(candidates)
        if not _mentions_excluded_category(candidate, excluded_categories or [])
    ]


def _exclusions_for_frame(excluded_categories, requested_conditions):
    exclusions = []
    for category in excluded_categories or []:
        text = _clean_text(category)
        if text:
            exclusions.append(f"{text} 제외")
    for condition in requested_conditions or []:
        if "제외" in _clean_text(condition) and condition not in exclusions:
            exclusions.append(condition)
    return _unique(exclusions)


def _safe_frame_text(value, max_length=80):
    text = _clean_text(value)
    if not text or _looks_like_ai_generated_address_or_coordinate(text):
        return ""
    return text[:max_length]


def _sanitize_frame_location(value):
    text = _clean_location_text(value)
    if not text or _looks_like_ai_generated_address_or_coordinate(text):
        return ""
    return text[:60]


def _sanitize_frame_list(items):
    values = []
    for item in _normalize_text_list(items):
        if _looks_like_ai_generated_address_or_coordinate(item):
            continue
        values.append(item[:60])
    return _unique(values)


def _sanitize_safety_note(value):
    text = _safe_frame_text(value, max_length=160)
    if not text:
        return ""
    if _has_any(text, ["복용", "진단", "치료", "처방"]):
        return HEALTH_NEARBY_MESSAGE
    return text


def _normalize_frame_confidence(value, fallback=0.0):
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        try:
            confidence = float(fallback)
        except (TypeError, ValueError):
            confidence = 0.0
    if confidence > 1:
        confidence = confidence / 100
    return min(max(confidence, 0.0), 1.0)


def _normalize_decision_action(value):
    action = _safe_frame_text(value)
    return action if action in ROUTER_ACTIONS else "ask_clarification"


def _normalize_frame_can_search(value, decision_action):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return decision_action == "search"


def _normalize_ranking_policy(value):
    policy = _safe_frame_text(value).lower()
    aliases = {
        "urgent": "urgent_nearest",
        "nearest": "urgent_nearest",
        "urgent_nearest": "urgent_nearest",
        "distance": "distance_first",
        "distance_first": "distance_first",
        "evidence": "evidence_first",
        "evidence_first": "evidence_first",
        "cost": "cost_sensitive",
        "cost_sensitive": "cost_sensitive",
    }
    return aliases.get(policy, policy if policy in set(aliases.values()) else "")


def _normalize_frame_location_mode(value, anchor_location=""):
    mode = _clean_text(value)
    if mode in {"explicit", "current_context", "clarification_required"}:
        return mode
    return "explicit" if anchor_location else "current_context"


def _is_valid_place_intent_frame(frame):
    if not isinstance(frame, dict):
        return False

    location_mode = _clean_text(frame.get("location_mode"))
    if location_mode not in {"explicit", "current_context", "clarification_required"}:
        return False

    if location_mode == "explicit" and not _clean_text(frame.get("anchor_location")):
        return False

    return all([
        _clean_text(frame.get("user_goal")),
        _clean_text(frame.get("display_label")),
        bool(
            _sanitize_frame_list(frame.get("candidate_place_types") or [])
            or _sanitize_frame_list(frame.get("search_queries") or [])
        ),
        isinstance(frame.get("constraints", []), list),
        isinstance(frame.get("exclusions", []), list),
        0 <= _normalize_frame_confidence(frame.get("confidence")) <= 1,
    ])


def _is_term_explicitly_requested(value, query):
    compact_value = _compact(value)
    compact_query = _compact(query)
    if not compact_value or not compact_query:
        return False
    return compact_value in compact_query


def _is_broad_frame_term(value, query=""):
    compact = _compact(value)
    if not compact:
        return True

    compact_broad_terms = {_compact(term) for term in BROAD_FRAME_TERMS}
    compact_fallback_terms = {_compact(term) for term in BROAD_FALLBACK_PLACE_TERMS}

    if compact in compact_broad_terms:
        return True

    if compact in compact_fallback_terms:
        return not _is_term_explicitly_requested(value, query)

    return any(
        term in compact
        for term in compact_broad_terms
        if len(term) >= 3
    ) and len(compact) <= 12


def _all_terms_are_broad(values, query=""):
    terms = _sanitize_frame_list(values or [])
    return bool(terms) and all(_is_broad_frame_term(term, query=query) for term in terms)


def _frame_target_repeats_query(target_objects, query):
    query_text = _compact(query)
    if not query_text:
        return False

    targets = _sanitize_frame_list(target_objects or [])
    if not targets:
        return False

    return all(
        _compact(target) == query_text or _compact(target) in query_text or query_text in _compact(target)
        for target in targets
    )


def _has_urgent_search_evidence(frame, query=""):
    if not isinstance(frame, dict):
        return False

    ranking_policy = _normalize_ranking_policy(
        frame.get("ranking_policy") or frame.get("rankingPolicy") or ""
    )
    if ranking_policy != "urgent_nearest":
        return False

    evidence_terms = _sanitize_frame_list([
        *(_sanitize_frame_list(frame.get("target_objects") or frame.get("targetObjects") or [])),
        *(_sanitize_frame_list(frame.get("result_match_terms") or frame.get("resultMatchTerms") or [])),
        *(_sanitize_frame_list(frame.get("candidate_place_types") or frame.get("candidatePlaceTypes") or [])),
        *(_sanitize_frame_list(frame.get("constraints") or [])),
    ])
    return bool(evidence_terms and not _all_terms_are_broad(evidence_terms, query=query))


def _frame_evidence_terms(frame):
    if not isinstance(frame, dict):
        return []

    values = []
    raw_evidence = frame.get("evidence") or frame.get("evidences") or []
    if not isinstance(raw_evidence, list):
        raw_evidence = [raw_evidence]

    for item in raw_evidence:
        if isinstance(item, dict):
            values.extend([
                item.get("value"),
                item.get("text"),
                item.get("term"),
                item.get("label"),
            ])
        else:
            values.append(item)

    return _sanitize_frame_list(values)


def _get_ai_frame_post_validation_reasons(frame, query):
    if not isinstance(frame, dict):
        return ["missing_frame"]

    target_objects = _sanitize_frame_list(frame.get("target_objects") or frame.get("targetObjects") or [])
    result_match_terms = _sanitize_frame_list(frame.get("result_match_terms") or frame.get("resultMatchTerms") or [])
    candidate_place_types = _sanitize_frame_list(frame.get("candidate_place_types") or frame.get("candidatePlaceTypes") or [])
    constraints = _sanitize_frame_list(frame.get("constraints") or [])
    exclusions = _sanitize_frame_list(frame.get("exclusions") or [])
    evidence_terms = _frame_evidence_terms(frame)
    confidence = _normalize_frame_confidence(frame.get("confidence"))
    broad_context_terms = [
        frame.get("normalized_user_intent"),
        frame.get("normalizedUserIntent"),
        frame.get("display_label"),
        frame.get("displayLabel"),
        frame.get("user_goal"),
        frame.get("userGoal"),
    ]
    has_specific_basis = bool(
        (result_match_terms and not _all_terms_are_broad(result_match_terms, query=query))
        or (evidence_terms and not _all_terms_are_broad(evidence_terms, query=query))
    )
    has_constraints = bool(constraints or exclusions)
    has_target_or_result_basis = bool(
        has_specific_basis
        or (
            target_objects
            and not _all_terms_are_broad(target_objects, query=query)
            and candidate_place_types
            and not _all_terms_are_broad(candidate_place_types, query=query)
        )
    )
    reasons = []

    if (
        not target_objects
        and (
            not has_specific_basis
            or _all_terms_are_broad(candidate_place_types, query=query)
        )
    ):
        reasons.append("missing_target_objects")

    if (
        not result_match_terms
        or (
            result_match_terms == target_objects
            and _frame_target_repeats_query(target_objects, query)
        )
    ) and not (has_constraints or evidence_terms):
        reasons.append("missing_result_match_terms")

    if (
        candidate_place_types
        and _all_terms_are_broad(candidate_place_types, query=query)
        and not has_specific_basis
        and not has_constraints
    ):
        reasons.append("broad_candidate_place_types")

    if (
        any(_is_broad_frame_term(term, query=query) for term in broad_context_terms if _clean_text(term))
        and not has_constraints
        and not has_target_or_result_basis
    ):
        reasons.append("broad_normalized_intent_without_criteria")

    if (
        confidence < BROAD_FRAME_CONFIDENCE_THRESHOLD
        and not has_constraints
        and (
            not result_match_terms
            or _all_terms_are_broad(result_match_terms, query=query)
        )
    ):
        reasons.append("low_confidence_broad_frame")

    if confidence <= BROAD_FRAME_LOW_CONFIDENCE_THRESHOLD and not _has_urgent_search_evidence(frame, query=query):
        reasons.append("low_confidence_without_urgent_evidence")

    if (
        _frame_target_repeats_query(target_objects, query)
        and not has_constraints
        and (
            not result_match_terms
            or _all_terms_are_broad(result_match_terms, query=query)
            or _all_terms_are_broad(candidate_place_types, query=query)
        )
    ):
        reasons.append("target_repeats_raw_query_without_evidence")

    return _unique(reasons)


def get_ai_frame_post_validation_reasons(frame, query):
    return _get_ai_frame_post_validation_reasons(frame, query)


def _ai_frame_post_validation_clarification_plan(query, raw_plan, search_plan, frame, reasons):
    question = _contextual_ai_clarification_question(query, frame)
    options = _contextual_ai_clarification_options(frame)
    if _should_use_default_purpose_options(question, frame, options, is_ai_plan=True):
        options = _default_clarification_options()
    display_label = _clean_target_query(
        _first_text(
            frame.get("display_label"),
            frame.get("displayLabel"),
            search_plan.get("targetQuery"),
            search_plan.get("target_query"),
            query,
        )
    )
    clarified_frame = {
        **frame,
        "decision_action": "ask_clarification",
        "decisionAction": "ask_clarification",
        "can_search_now": False,
        "canSearchNow": False,
        "location_mode": frame.get("location_mode") or frame.get("locationMode") or "clarification_required",
        "locationMode": frame.get("location_mode") or frame.get("locationMode") or "clarification_required",
        "clarification_question": question,
        "clarificationQuestion": question,
        "clarification_options": options,
        "clarificationOptions": options,
        "missing_info": _unique([
            *_sanitize_frame_list(frame.get("missing_info") or frame.get("missingInfo") or []),
            "목적",
        ]),
    }
    if not _clean_text(clarified_frame.get("anchor_location") or clarified_frame.get("anchorLocation")):
        clarified_frame["location_mode"] = "clarification_required"
        clarified_frame["locationMode"] = "clarification_required"

    plan = _clarification_plan(
        query,
        question=question,
        reason="ai_broad_frame_post_validation",
        target_query=display_label,
        fallback_location="current_location",
    )
    plan["parser_provider"] = "gms"
    plan["parser_fallback"] = False
    plan["plan_source"] = "ai"
    plan["execution_mode"] = "decision_gate"
    plan["confidence"] = _normalize_confidence(raw_plan.get("confidence"), 45)
    plan["clarification_options"] = options
    plan["search_plan"] = {
        **plan["search_plan"],
        "targetQuery": display_label,
        "target_query": display_label,
        "place_intent_frame": clarified_frame,
        "placeIntentFrame": clarified_frame,
        "execution_mode": "decision_gate",
        "plan_source": "ai",
        "decision_action": "ask_clarification",
        "decisionAction": "ask_clarification",
        "can_search_now": False,
        "clarification_question": question,
        "clarification_options": options,
        "target_objects": _sanitize_frame_list(frame.get("target_objects") or frame.get("targetObjects") or []),
        "candidate_place_types": _sanitize_frame_list(frame.get("candidate_place_types") or frame.get("candidatePlaceTypes") or []),
        "result_match_terms": _sanitize_frame_list(frame.get("result_match_terms") or frame.get("resultMatchTerms") or []),
    }
    plan["ai_debug"] = {
        "post_validation": {
            "status": "forced_clarification",
            "reasons": reasons,
            "target_objects": plan["search_plan"]["target_objects"],
            "candidate_place_types": plan["search_plan"]["candidate_place_types"],
            "result_match_terms": plan["search_plan"]["result_match_terms"],
            "confidence": _normalize_frame_confidence(frame.get("confidence")),
        },
    }
    return plan


def _repair_ai_place_intent_frame(search_plan, raw_plan, user_query, fallback_search_plan):
    search_plan = search_plan if isinstance(search_plan, dict) else {}
    fallback_search_plan = fallback_search_plan if isinstance(fallback_search_plan, dict) else {}
    target_query = _clean_target_query(
        _first_text(
            search_plan.get("targetQuery"),
            search_plan.get("target_query"),
            *(_normalize_text_list(raw_plan.get("targets") or [])[:1]),
            fallback_search_plan.get("targetQuery"),
            user_query,
        )
    )
    anchor_location = _sanitize_ai_location_query(
        _first_text(
            search_plan.get("locationQuery"),
            search_plan.get("location_query"),
            search_plan.get("baseLocationQuery"),
            search_plan.get("base_location_query"),
        )
    )
    categories = _normalize_categories(
        search_plan.get("candidate_category_codes")
        or search_plan.get("candidateCategoryCodes")
        or search_plan.get("categories")
        or []
    )
    place_types = _unique([
        *_normalize_text_list(search_plan.get("candidate_place_types") or []),
        *_normalize_text_list(search_plan.get("candidatePlaceTypes") or []),
        *_normalize_text_list(search_plan.get("place_type_keywords") or []),
        *_normalize_text_list(raw_plan.get("targets") or []),
        target_query,
    ])
    search_queries = _unique([
        *_normalize_text_list(search_plan.get("search_queries") or []),
        *_normalize_text_list(search_plan.get("searchQueries") or []),
        *_normalize_text_list(search_plan.get("kakaoKeywordCandidates") or []),
        *_normalize_text_list(search_plan.get("kakao_keyword_candidates") or []),
        *place_types,
    ])
    frame = {
        "user_goal": _clean_text(raw_plan.get("user_intent_summary")) or f"{target_query or '장소'} 찾기",
        "anchor_location": anchor_location,
        "location_mode": "explicit" if anchor_location else "current_context",
        "situation": _situation_for_intent_group(
            _intent_group_for_situation(search_plan.get("scenario")),
            user_query,
            target_query,
            _normalize_scenario(search_plan.get("scenario")),
        ),
        "display_label": target_query or "장소",
        "candidate_category_codes": categories,
        "target_objects": _unique([target_query] if target_query else []),
        "candidate_place_types": place_types,
        "search_queries": search_queries,
        "result_match_terms": _unique([target_query, *categories, *place_types]),
        "constraints": _normalize_text_list(
            raw_plan.get("conditions")
            or search_plan.get("conditions")
            or search_plan.get("requestedConditions")
            or search_plan.get("requested_conditions")
            or []
        ),
        "exclusions": _normalize_text_list(raw_plan.get("avoid") or search_plan.get("exclusions") or []),
        "preferred_place_natures": [],
        "excluded_place_natures": [],
        "ranking_policy": _normalize_ranking_policy(search_plan.get("ranking_policy") or search_plan.get("rankingPolicy")),
        "missing_info": [],
        "confidence": _normalize_frame_confidence(raw_plan.get("confidence"), 0.6),
    }
    return _normalize_place_intent_frame(frame, user_query=user_query)


def _frame_location(search_plan):
    frame = search_plan.get("place_intent_frame")
    if not isinstance(frame, dict):
        return ""
    return _clean_text(frame.get("anchor_location"))


def _enrich_plan_with_intent_group(plan):
    search_plan = plan.get("search_plan") if isinstance(plan.get("search_plan"), dict) else {}
    if not search_plan:
        return

    user_query = _first_text(search_plan.get("originalQuery"), search_plan.get("original_query"))
    target_query = _first_text(search_plan.get("targetQuery"), search_plan.get("target_query"))
    scenario = _normalize_scenario(search_plan.get("scenario"))
    raw_place_frame = search_plan.get("place_intent_frame") or search_plan.get("placeIntentFrame")
    existing_frame = (
        _normalize_place_intent_frame(raw_place_frame, user_query=user_query)
        if isinstance(raw_place_frame, dict)
        else {}
    )
    intent_group = _clean_text(
        search_plan.get("intent_group")
        or search_plan.get("intentGroup")
        or plan.get("intent_group")
    )
    frame_intent_group = _intent_group_for_situation(existing_frame.get("situation"))
    if frame_intent_group and frame_intent_group != "general_place_search":
        intent_group = frame_intent_group
    if intent_group not in INTENT_GROUP_CONFIGS:
        intent_group = _classify_intent_group(user_query, target_query, scenario)
    if intent_group not in INTENT_GROUP_CONFIGS:
        return

    config = INTENT_GROUP_CONFIGS[intent_group]
    avoid_terms = _normalize_text_list(
        plan.get("avoid")
        or search_plan.get("avoid")
        or search_plan.get("exclusions")
        or []
    )
    excluded_categories = _unique([
        *_normalize_text_list(
            search_plan.get("excluded_categories")
            or search_plan.get("exclude_categories")
            or []
        ),
        *_extract_excluded_categories(user_query),
        *avoid_terms,
    ])
    if excluded_categories:
        search_plan["excluded_categories"] = excluded_categories
    if avoid_terms:
        search_plan["exclusions"] = _unique([
            *_normalize_text_list(search_plan.get("exclusions") or []),
            *avoid_terms,
        ])

    if intent_group != "general_place_search":
        scenario = config["scenario"]
        target_query = _target_query_for_intent_group(
            intent_group,
            user_query,
            target_query,
            scenario,
            _normalize_text_list(search_plan.get("menu_keywords") or []),
        )
        categories = _normalize_categories(config.get("categories") or [])
        search_plan["scenario"] = scenario
        search_plan["categories"] = categories
        search_plan["categoryHint"] = categories[0] if categories else ""
        search_plan["targetType"] = "category" if categories else ""
        search_plan["targetQuery"] = target_query

    requested_conditions = _sanitize_requested_conditions([
        *config.get("conditions", []),
        *_normalize_text_list(
            search_plan.get("requestedConditions")
            or search_plan.get("requested_conditions")
            or search_plan.get("conditions")
            or []
        ),
    ])
    search_plan["requestedConditions"] = requested_conditions
    search_plan["conditions"] = requested_conditions
    search_plan["preferred_tags"] = _unique([
        *_normalize_tags(search_plan.get("preferred_tags") or []),
        *_normalize_tags(config.get("preferred_tags") or []),
    ])
    search_plan["category_candidates"] = _filter_category_candidates(
        config.get("category_candidates", []),
        excluded_categories,
    )
    frame = _build_place_intent_frame(
        search_plan,
        user_query,
        intent_group,
        config,
        requested_conditions,
        excluded_categories,
        existing_frame=existing_frame,
    )
    if frame.get("anchor_location"):
        current_location = _first_text(search_plan.get("locationQuery"), search_plan.get("location_query"))
        if not current_location or len(frame["anchor_location"]) > len(current_location):
            search_plan["locationQuery"] = frame["anchor_location"]
            search_plan["baseLocationQuery"] = frame["anchor_location"]
            search_plan["has_explicit_location"] = True
            search_plan["location_resolution_required"] = True

    search_plan["place_intent_frame"] = frame
    search_plan["intent_group"] = intent_group
    search_plan["kakaoKeywordCandidates"] = _build_kakao_keyword_candidates(
        search_plan,
        config,
        target_query,
        excluded_categories,
    )
    search_plan["web_search_queries"] = build_web_search_queries(search_plan, user_query)
    search_plan["web_search_recommended"] = bool(
        config.get("web_search_recommended")
        and search_plan["web_search_queries"]
    )

    plan["search_plan"] = search_plan
    plan["intent_group"] = intent_group
    plan["conditions"] = requested_conditions
    plan["preferences"] = search_plan["preferred_tags"]
    plan["targets"] = _unique([target_query, *_normalize_text_list(plan.get("targets") or [])])
    if frame.get("anchor_location"):
        plan["location"] = _location_payload(frame["anchor_location"], True, "")
    if intent_group == "health_nearby":
        plan["message"] = plan.get("message") or HEALTH_NEARBY_MESSAGE


def _classify_intent_group(query, target_query="", scenario=""):
    text = f"{query or ''} {target_query or ''}"
    if _has_any(text, ["흡연구역", "흡연장", "흡연", "담배필", "담배 필", "담배피", "담배 피", "담배"]):
        return "smoking_area"
    if _has_urgent_toilet_intent(text):
        return "urgent_toilet"
    if _has_health_nearby_intent(text):
        return "health_nearby"
    if _has_parking_intent(text):
        return "parking_place"
    if _has_wifi_intent(text):
        return "wifi_place"
    if _has_weather_shelter_intent(text):
        return "weather_shelter"
    if _has_entertainment_place_intent(text):
        return "entertainment_place"
    if _has_shopping_place_intent(text):
        return "shopping_place"
    if _has_bar_place_intent(text):
        return "bar_place"
    if _has_walk_healing_natural_intent(text) or scenario == "walk_healing":
        return "walk_healing"
    if _has_food_place_intent(text) or scenario == "restaurant":
        return "food_place"
    if _has_work_place_intent(text):
        return "work_place"
    if _has_quiet_rest_intent(text):
        return "quiet_rest_place"
    if scenario == "work_cafe":
        return "work_place"
    if scenario == "smoking_area":
        return "smoking_area"
    if _has_place_recommendation_hint(text):
        return "general_place_search"
    return ""


def _has_urgent_toilet_intent(query):
    return _has_any(query, [
        "화장실",
        "공중화장실",
        "개방화장실",
        "똥",
        "대변",
        "소변",
        "마려워",
        "마려움",
    ])


def _has_health_nearby_intent(query):
    return _has_any(query, [
        "머리 아프",
        "머리아프",
        "머리 깨질",
        "머리깨질",
        "두통",
        "몸이 안 좋",
        "몸 안 좋",
        "몸이안좋",
        "아픈데 갈 곳",
        "아픈데 갈곳",
        "배 아픈데 갈",
        "배아픈데갈",
        "약국",
        "병원",
        "내과",
        "응급실",
        "약 살",
        "약살",
    ])


def _has_parking_intent(query):
    return _has_any(query, ["주차", "차 댈", "차댈", "차 세울", "차세울", "공영주차"])


def _has_wifi_intent(query):
    return _has_any(query, ["와이파이", "wifi", "wi-fi", "인터넷", "공공 와이파이", "공공와이파이"])


def _has_weather_shelter_intent(query):
    return _has_any(query, [
        "비 피",
        "비피",
        "비 와서",
        "비와서",
        "비 오",
        "비오",
        "들어가자",
        "들어갈 곳",
        "들어갈곳",
        "더워서",
        "더위",
        "무더위",
        "폭염",
        "추위",
        "한파",
        "잠깐 앉아",
        "잠깐앉아",
    ])


def _has_entertainment_place_intent(query):
    return _has_any(query, [
        "영화관",
        "영화 볼",
        "영화볼",
        "영화 보",
        "영화보",
        "극장",
        "공연장",
        "공연 볼",
        "공연볼",
        "공연 보",
        "공연보",
        "문화공간",
    ])


def _has_shopping_place_intent(query):
    return _has_any(query, [
        "쇼핑몰",
        "쇼핑할",
        "쇼핑 할",
        "쇼핑",
        "백화점",
        "아울렛",
    ])


def _has_bar_place_intent(query):
    return _has_any(query, [
        "술집",
        "술 마",
        "술마",
        "주점",
        "와인바",
        "칵테일바",
        "펍",
        "호프",
        "bar",
    ])


def _has_food_place_intent(query):
    return _has_any(query, [
        "맛집",
        "먹",
        "밥",
        "식사",
        "식당",
        "음식점",
        "브런치",
        "소금빵",
        "쌀국수",
        "파스타",
        "돈까스",
        "돈가스",
        "디저트",
        "빵집",
    ])


def _has_work_place_intent(query):
    return _has_any(query, [
        "작업",
        "노트북",
        "놋북",
        "펼 데",
        "펼데",
        "공부",
        "카공",
        "콘센트",
        "스터디카페",
        "스터디룸",
        "일할",
        "업무",
    ])


def _has_quiet_rest_intent(query):
    if _has_cafe_negative_preference(query) or _has_crowd_solo_waiting_intent(query):
        return True
    return _has_any(query, ["조용"]) and _has_any(query, [
        "쉬",
        "쉴",
        "있고 싶",
        "있을 곳",
        "있을 데",
        "혼자",
        "사람 없는",
        "사람없는",
    ]) or _has_any(query, ["멍때리", "멍 때리", "사람 없는 데", "사람없는데"])


def _is_ambiguous_quiet_place_request(query, target_query=""):
    text = _compact(f"{query or ''} {target_query or ''}")
    ambiguous_values = {
        "조용한곳",
        "조용한데",
        "조용한장소",
        "조용한곳추천",
        "조용한데추천",
        "조용한장소추천",
    }
    if text in ambiguous_values:
        return True
    if "조용한곳" not in text and "조용한데" not in text and "조용한장소" not in text:
        return False
    return not _has_any(query, [
        "쉬",
        "쉴",
        "노트북",
        "작업",
        "공부",
        "산책",
        "먹",
        "밥",
        "식사",
        "카페",
    ])


def _target_query_for_intent_group(intent_group, query, current_target, scenario, menu_keywords):
    config = INTENT_GROUP_CONFIGS.get(intent_group) or {}
    current_target = _clean_target_query(current_target)
    if intent_group == "quiet_rest_place":
        if _has_cafe_negative_preference(query) or _has_crowd_solo_waiting_intent(query):
            return "쉴 곳"
        return "조용히 쉴 곳"
    if intent_group == "work_place":
        return "카페"
    if intent_group == "food_place":
        return current_target or _derive_target_query(query, scenario, menu_keywords)
    if intent_group in {"entertainment_place", "shopping_place", "bar_place"}:
        return current_target or config.get("target_query")
    if intent_group in {
        "urgent_toilet",
        "health_nearby",
        "parking_place",
        "wifi_place",
        "weather_shelter",
        "walk_healing",
        "smoking_area",
    }:
        return config.get("target_query") or current_target
    return current_target or config.get("target_query") or _derive_target_query(query, scenario, menu_keywords)


def _filter_category_candidates(candidates, excluded_categories):
    excluded_compact = {_compact_exclusion_term(value) for value in excluded_categories or []}
    filtered = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        name = _clean_text(candidate.get("name"))
        if not name or _compact(name) in excluded_compact:
            continue
        try:
            weight = float(candidate.get("weight"))
        except (TypeError, ValueError):
            weight = 0
        filtered.append({"name": name, "weight": weight})
    return filtered


def _build_kakao_keyword_candidates(search_plan, config, target_query, excluded_categories):
    frame = search_plan.get("place_intent_frame") if isinstance(search_plan.get("place_intent_frame"), dict) else {}
    frame_place_types = _sanitize_frame_list(frame.get("candidate_place_types") or [])
    keywords = _unique([
        *frame_place_types,
        *config.get("kakao_keywords", []),
        target_query,
        *_normalize_text_list(search_plan.get("place_type_keywords") or []),
    ])
    return [
        keyword
        for keyword in keywords
        if not _mentions_excluded_category(keyword, excluded_categories or [])
    ]


def build_web_search_queries(search_plan: dict, user_query: str) -> list[str]:
    if not isinstance(search_plan, dict):
        return []

    frame = search_plan.get("place_intent_frame") if isinstance(search_plan.get("place_intent_frame"), dict) else {}
    location_query = _first_text(
        frame.get("anchor_location"),
        search_plan.get("locationQuery"),
        search_plan.get("location_query"),
        search_plan.get("baseLocationQuery"),
        search_plan.get("base_location_query"),
    )
    if not location_query or location_query == "current_location":
        return []

    target_query = _first_text(search_plan.get("targetQuery"), search_plan.get("target_query"))
    scenario = _normalize_scenario(search_plan.get("scenario"))
    intent_group = _clean_text(
        search_plan.get("intent_group")
        or search_plan.get("intentGroup")
        or _classify_intent_group(user_query, target_query, scenario)
    )
    excluded_categories = _normalize_text_list(
        search_plan.get("excluded_categories")
        or search_plan.get("exclude_categories")
        or []
    )
    excluded_categories = _unique([
        *excluded_categories,
        *_normalize_text_list(frame.get("exclusions") or []),
    ])
    templates_by_intent = {
        "quiet_rest_place": ["조용한 공간", "도서관", "혼자 쉬기 좋은 곳", "실내 쉼터", "조용한 카페"],
        "work_place": ["노트북 카페", "콘센트 카페", "작업하기 좋은 카페", "스터디카페", "도서관"],
        "health_nearby": ["약국", "병원", "내과", "응급실"],
        "urgent_toilet": ["공중화장실", "개방화장실", "화장실"],
        "parking_place": ["주차장", "공영주차장"],
        "wifi_place": ["공공 와이파이", "무료 와이파이", "와이파이 되는 곳"],
        "weather_shelter": ["실내 쉼터", "무더위쉼터", "도서관", "공공시설", "비 피할 곳"],
        "walk_healing": ["산책로", "해변 산책", "걷기 좋은 곳", "바람 쐴 곳", "전망 좋은 곳"],
        "smoking_area": ["흡연구역", "흡연실"],
        "entertainment_place": ["영화관", "공연장", "문화공간"],
        "shopping_place": ["쇼핑몰", "백화점", "아울렛"],
        "bar_place": ["술집", "바", "펍", "와인바", "칵테일바"],
        "food_place": ["맛집", "식당", "음식점"],
    }
    frame_templates = _web_templates_from_frame(frame)
    templates = _unique([
        *frame_templates,
        *(templates_by_intent.get(intent_group) or []),
    ]) or [
        candidate.get("name")
        for candidate in search_plan.get("category_candidates", [])
        if isinstance(candidate, dict)
    ] or [target_query]

    queries = []
    for template in templates:
        template = _clean_text(template)
        if not template or _mentions_excluded_category(template, excluded_categories):
            continue
        search_query = _clean_text(f"{location_query} {template}")
        if _is_generic_web_search_query(search_query, location_query):
            continue
        queries.append(search_query)
    return _unique(queries)[:5]


def _web_templates_from_frame(frame):
    if not isinstance(frame, dict):
        return []
    situation = _normalize_situation(frame.get("situation"))
    candidate_place_types = _sanitize_frame_list(frame.get("candidate_place_types") or [])
    templates = list(candidate_place_types)
    constraints = " ".join(_sanitize_frame_list(frame.get("constraints") or []))
    if situation == "quiet_rest" or (situation not in {"work", "weather_shelter"} and "조용" in constraints):
        templates.insert(0, "조용한 공간")
    if situation == "work":
        templates = _unique(["노트북 카페", "콘센트 카페", *templates])
    if situation == "weather_shelter":
        templates = _unique(["실내 쉼터", "비 피할 곳", *templates])
    if situation == "walk":
        templates = _unique(["산책로", "해변 산책", *templates])
    return _unique(templates)


def _mentions_excluded_category(text, excluded_categories):
    compact_text = _compact(text)
    return any(
        _compact_exclusion_term(category) in compact_text
        for category in excluded_categories or []
        if _compact_exclusion_term(category)
    )


def _compact_exclusion_term(value):
    compact = _compact(value)
    for suffix in ["제외", "빼고", "말고", "아님", "아니"]:
        compact = compact.replace(suffix, "")
    return compact


def _is_generic_web_search_query(search_query, location_query):
    compact_query = _compact(search_query)
    compact_location = _compact(location_query)
    if not compact_query or compact_query == compact_location:
        return True
    generic_targets = {"장소", "곳", "데", "추천", "근처"}
    without_location = compact_query.replace(compact_location, "", 1)
    return without_location in {_compact(value) for value in generic_targets}


def _is_out_of_scope_query(query):
    if not _has_any(query, OUT_OF_SCOPE_KEYWORDS):
        return False

    if _has_any(query, [
        "숙제",
        "과제",
        "비트코인",
        "주식",
        "코인",
        "투자",
        "정치",
        "뉴스",
        "의료",
        "감기약",
        "법률",
        "법적",
        "계약서",
        "연애",
    ]):
        return True

    return not _has_place_recommendation_hint(query)


def _is_refinement_request(query):
    if _is_negative_preference(query):
        return False
    return _has_any(query, REFINEMENT_CONTEXT_PHRASES)


def _scenario_keyword_score(query):
    combined = _compact(query)
    return max(
        sum(1 for keyword in keywords if _compact(keyword) in combined)
        for _, keywords, _, _, _ in SCENARIO_RULES
    )


def _is_vague_place_request(query, scenario, target_query):
    compact = _compact(query)
    has_vague_phrase = any(
        phrase in compact
        for phrase in [
            "좋은곳",
            "좋은데",
            "괜찮은곳",
            "괜찮은데",
            "어디좋",
            "어디갈까",
            "어디가",
        ]
    )
    return has_vague_phrase and _scenario_keyword_score(query) <= 0 and not _extract_menu_keywords(query)


def _requires_location_before_search(query, scenario, target_query):
    if scenario == "waiting_place" and _has_waiting_place_natural_intent(query):
        return True
    return _has_any(query, ["근처", "주변", "가까운", "가까이", "인근"])


def _extract_category_filter(query):
    if _has_any(query, ["카페만"]):
        return "cafe"
    if _has_any(query, ["공원만"]):
        return "city_park"
    if _has_any(query, ["식당만", "맛집만"]):
        return "restaurant"
    return ""


def _looks_like_non_location(text):
    compact = _compact(text)
    if compact in {"비", "비와서", "쉴곳", "쉴데", "산책할곳", "머리", "몸", "배"}:
        return True
    return any(keyword in compact for keyword in [
        "조용",
        "혼자",
        "잠깐",
        "추천",
        "산책",
        "먹고",
        "맛집",
        "흡연",
        "담배",
        "카페",
        "공원",
        "쉴곳",
        "쉴데",
        "산책할곳",
        "밖말고",
        "아프",
        "두통",
        "마려",
    ])


def _scenario_rule_payload(scenario):
    for rule_scenario, _, categories, kakao_keywords, preferred_tags in SCENARIO_RULES:
        if rule_scenario == scenario:
            return (
                rule_scenario,
                list(categories),
                list(kakao_keywords),
                list(preferred_tags),
            )
    return (
        scenario,
        _categories_for_scenario(scenario),
        [_derive_target_query("", scenario, [])],
        [],
    )


def _apply_query_intent_overrides(query, scenario, categories, kakao_keywords, preferred_tags):
    if _has_cafe_negative_preference(query):
        rule_scenario, rule_categories, rule_kakao_keywords, rule_preferred_tags = _scenario_rule_payload("waiting_place")
        return (
            rule_scenario,
            rule_categories,
            [keyword for keyword in rule_kakao_keywords if "카페" not in keyword],
            rule_preferred_tags,
        )

    if _has_rain_indoor_intent(query) or _has_crowd_solo_waiting_intent(query):
        return _scenario_rule_payload("waiting_place")

    if _has_walk_healing_natural_intent(query):
        return _scenario_rule_payload("walk_healing")

    return (
        scenario,
        list(categories or []),
        list(kakao_keywords or []),
        list(preferred_tags or []),
    )


def _should_force_query_intent_policy(query):
    return (
        _has_cafe_negative_preference(query)
        or _has_rain_indoor_intent(query)
        or _has_crowd_solo_waiting_intent(query)
        or _has_walk_healing_natural_intent(query)
    )


def _is_negative_preference(query):
    return _has_any(query, NEGATIVE_PREFERENCE_PHRASES)


def _has_rain_indoor_intent(query):
    return (
        _has_any(query, ["밖 말고", "실외 말고", "비 피", "비피", "비 와서", "비와서"])
        or (_has_any(query, ["비"]) and _has_any(query, ["앉", "쉬", "쉴", "있을 데", "있을 곳"]))
    )


def _has_crowd_solo_waiting_intent(query):
    if _has_any(query, ["혼밥", "밥", "먹", "식사", "맛집"]):
        return False

    has_crowd_negative = _has_any(query, [
        "사람 많은 데 말고",
        "사람 너무 많은 데 말고",
        "사람많은데말고",
        "붐비는 데 말고",
        "붐비지",
    ])
    has_solo_rest = _has_any(query, ["혼자"]) and _has_any(query, ["쉬", "쉴", "있고 싶", "있을 곳", "있을 데"])
    return has_crowd_negative or has_solo_rest


def _has_cafe_negative_preference(query):
    return _has_any(query, [
        "카페 말고",
        "카페 느낌은 아니",
        "카페 느낌 아니",
        "카페느낌은아니",
        "카페 같지 않은",
        "카페는 아니",
        "카페는 싫",
        "카페 싫",
        "카페 빼고",
    ])


def _has_walk_healing_natural_intent(query):
    return _has_any(query, [
        "바람 쐬",
        "바람쐬",
        "걷기 좋은",
        "걷기좋은",
        "산책하면서",
        "산책할 곳",
        "힐링할 곳",
    ])


def _has_waiting_place_natural_intent(query):
    return (
        _has_rain_indoor_intent(query)
        or _has_crowd_solo_waiting_intent(query)
        or _has_cafe_negative_preference(query)
        or _has_any(query, ["잠깐", "잠시", "앉", "쉴 곳", "쉴곳", "쉬고 싶", "있고 싶"])
    )


def _missing_location_question(query, scenario):
    if scenario == "waiting_place":
        if _has_rain_indoor_intent(query):
            return "어느 지역에서 비를 피하면서 앉아 있을 곳을 찾아드릴까요? 예: 서면, 하단역, 광안리"
        if _has_crowd_solo_waiting_intent(query):
            return "어느 지역에서 혼자 조용히 쉴 곳을 찾아드릴까요? 예: 서면, 하단역, 광안리"
        if _has_cafe_negative_preference(query):
            return "어느 지역에서 조용히 쉴 곳을 찾아드릴까요? 예: 서면, 하단역, 광안리"
    return CLARIFICATION_MESSAGE


def _target_query_for_scenario(scenario):
    return _derive_target_query("", scenario, [])


def _extract_excluded_categories(query):
    if _has_cafe_negative_preference(query):
        return ["카페"]
    return []


def _pick_scenario(query, target_query):
    combined = _compact(f"{query} {target_query}")
    scores = []
    for scenario, keywords, categories, kakao_keywords, preferred_tags in SCENARIO_RULES:
        score = sum(1 for keyword in keywords if _compact(keyword) in combined)
        scores.append((score, scenario, categories, kakao_keywords, preferred_tags))

    best_score, scenario, categories, kakao_keywords, preferred_tags = max(scores, key=lambda item: item[0])
    if best_score <= 0:
        return "waiting_place", ["cafe", "shelter"], ["카페", "쉼터"], ["잠깐쉬기좋음"]

    return scenario, categories, kakao_keywords, preferred_tags


def _matched_condition_rules(query):
    compact = _compact(query)
    return [
        (keyword, label, tag)
        for keyword, label, tag in CONDITION_RULES
        if _compact(keyword) in compact
    ]


def _extract_conditions(query):
    return _sanitize_requested_conditions([
        *[label for _, label, _ in _matched_condition_rules(query)],
        *_inferred_natural_conditions(query),
    ])


def _sanitize_requested_conditions(items):
    sanitized = []
    for item in _normalize_text_list(items):
        compact = _compact(item)
        if not compact:
            continue
        if compact in {_compact(value) for value in CATEGORY_LIKE_CONDITION_VALUES}:
            continue
        sanitized.append(item)
    return _unique(sanitized)


def _inferred_natural_conditions(query):
    conditions = []

    if _has_rain_indoor_intent(query):
        conditions.extend(["실내", "앉을 수 있음", "비 피하기 좋음", "잠깐 쉬기 좋음"])

    if _has_crowd_solo_waiting_intent(query):
        conditions.extend(["혼자 이용하기 좋음", "조용함", "붐비지 않음", "잠깐 쉬기 좋음"])

    if _has_cafe_negative_preference(query):
        if _has_any(query, ["조용"]):
            conditions.append("조용함")
        if _has_any(query, ["앉", "쉬", "쉴", "있고 싶"]):
            conditions.append("잠깐 쉬기 좋음")
        conditions.append("카페 제외")

    if _has_walk_healing_natural_intent(query):
        conditions.append("산책하기 좋음")
        if _has_any(query, ["걷"]):
            conditions.append("걷기 좋음")
        if _has_any(query, ["바람"]):
            conditions.append("바람 쐬기 좋음")
        if _has_any(query, ["힐링"]):
            conditions.append("힐링하기 좋음")

    return conditions


def _extract_menu_keywords(query):
    compact = _compact(query)
    return _unique([keyword for keyword in MENU_KEYWORDS if _compact(keyword) in compact])


def _extract_place_type_keywords(query, menu_keywords, scenario):
    keywords = []
    compact = _compact(query)
    for menu_keyword in menu_keywords:
        keywords.extend(PLACE_TYPE_KEYWORDS.get(menu_keyword, []))

    if "카페" in compact:
        keywords.append("카페")
    if any(keyword in compact for keyword in ["맛집", "식당", "음식점", "먹"]):
        keywords.extend(["식당", "음식점"])
    if scenario == "walk_healing":
        keywords.extend(["공원", "산책로"])
    if scenario == "waiting_place":
        keywords.extend(["카페", "쉼터"])

    return _unique(keywords)


def _derive_target_query(query, scenario, menu_keywords):
    if menu_keywords:
        if "브런치" in menu_keywords and "카페" in query:
            return "브런치 카페"
        if any(keyword in query for keyword in ["맛집", "빵집", "카페"]):
            suffix = "맛집" if "맛집" in query else ("카페" if "카페" in query else "빵집")
            return f"{menu_keywords[0]} {suffix}"
        return menu_keywords[0]

    fallback_by_scenario = {
        "restaurant": "식당",
        "walk_healing": "산책할 곳",
        "work_cafe": "카페",
        "waiting_place": "쉴 곳",
        "smoking_area": "흡연구역",
    }
    return fallback_by_scenario.get(scenario, query)


def _fallback_target_query(target_query, scenario, menu_keywords):
    if target_query:
        return target_query
    return _derive_target_query("", scenario, menu_keywords)


def _extract_avoid_terms(query):
    text = _clean_text(query)
    if "말고" not in text and "제외" not in text:
        if "빼" not in text:
            return []

    avoid_terms = []
    for keyword in [
        "공원",
        "카페",
        "디저트",
        "식당",
        "음식점",
        "맛집",
        "쉼터",
        "흡연구역",
        "관광지",
        "주차장",
        "주차",
        "웹",
        "web",
    ]:
        if keyword in text:
            avoid_terms.append(keyword)
    return _unique(avoid_terms)


def _build_intent_summary(location_query, target_query, scenario, conditions):
    location_label = location_query or "현재 위치 기준"
    condition_label = f" · 조건: {', '.join(conditions[:2])}" if conditions else ""
    target_label = target_query or {
        "restaurant": "식당/맛집",
        "walk_healing": "산책/힐링 장소",
        "work_cafe": "작업하기 좋은 카페",
        "waiting_place": "잠깐 쉴 곳",
        "smoking_area": "흡연구역",
    }.get(scenario, "장소")
    return f"{location_label}에서 {target_label}을 찾는 요청으로 이해했어요{condition_label}."


def _location_payload(text, is_explicit, fallback):
    return {
        "text": text or "",
        "is_explicit": bool(is_explicit),
        "fallback": fallback or "",
    }


def _search_plan_payload(
    original_query,
    location_query,
    target_query,
    scenario,
    categories,
    menu_keywords,
    place_type_keywords,
    required_tags,
    preferred_tags,
    requested_conditions,
    kakao_keyword_candidates=None,
):
    category_hint = categories[0] if categories else ""
    return {
        "originalQuery": original_query,
        "locationQuery": location_query or "",
        "baseLocationQuery": location_query or "",
        "has_explicit_location": bool(location_query),
        "location_resolution_required": bool(location_query),
        "targetQuery": target_query or "",
        "targetType": "category" if category_hint else "",
        "scenario": scenario,
        "categories": categories,
        "categoryHint": category_hint,
        "menu_keywords": menu_keywords,
        "place_type_keywords": place_type_keywords,
        "required_tags": required_tags,
        "preferred_tags": preferred_tags,
        "requestedConditions": requested_conditions,
        "conditions": requested_conditions,
        "kakaoKeywordCandidates": _unique(kakao_keyword_candidates or [target_query]),
    }


def _execution_policy(run_search, preserve_explicit_location):
    return {
        "run_search": bool(run_search),
        "preserve_explicit_location": bool(preserve_explicit_location),
        "allow_kakao_fallback": True,
        "allow_ai_web_search_auto": False,
        "merge_ai_web_results": False,
    }


def _normalize_text_list(items):
    if not isinstance(items, list):
        items = [items] if items else []
    return _unique([
        _clean_text(item)
        for item in items
        if _clean_text(item) and _clean_text(item) != "[object Object]"
    ])


def _normalize_tags(items):
    return [
        item
        for item in _normalize_text_list(items)
        if item in ALLOWED_TAGS or item
    ]


def _normalize_categories(items):
    categories = []
    for item in _normalize_text_list(items):
        item = FRAME_CATEGORY_ALIASES.get(item, item)
        if item in ALLOWED_CATEGORIES:
            categories.append(item)
    return _unique(categories)


def _normalize_scenario(value):
    scenario = _clean_text(value)
    return scenario if scenario in ALLOWED_SCENARIOS else "waiting_place"


def _normalize_confidence(value, fallback):
    try:
        confidence = int(float(value))
    except (TypeError, ValueError):
        confidence = fallback
    return min(max(confidence, 0), 100)


def _first_text(*values):
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _unique(items):
    seen = set()
    result = []
    for item in items:
        text = _clean_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
