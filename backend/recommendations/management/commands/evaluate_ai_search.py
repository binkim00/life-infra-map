import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.services.ai_search_orchestrator import run_ai_search
from recommendations.services.tag_utils import get_category_display_name


LOG_DIR = Path("docs/01_progress/search_quality_logs")
LATEST_JSON = LOG_DIR / "search_quality_latest.json"
JSONL_LOG = LOG_DIR / "search_quality_runs.jsonl"
MARKDOWN_LOG = LOG_DIR / "search_quality_log.md"

CATEGORY_ALIASES = {
    "cafe": ["카페", "커피", "음료"],
    "restaurant": ["식당", "음식점", "맛집", "밥"],
    "toilet": ["화장실", "공중화장실", "개방화장실"],
    "smoking_area": ["흡연구역", "흡연실", "담배"],
    "shopping": ["쇼핑몰", "백화점", "아울렛", "쇼핑"],
    "city_park": ["공원", "산책"],
    "beach": ["해변", "산책"],
    "tourism": ["관광", "명소", "전망"],
    "shelter": ["쉼터", "쉴 곳", "실내"],
    "freewifi": ["와이파이", "무료 와이파이"],
    "parking": ["주차장"],
    "pharmacy": ["약국", "약"],
    "karaoke": ["노래방", "코인노래방"],
}

DEFAULT_CASES = [
    {
        "id": "drink_thirst_sasang",
        "area": "사상",
        "query": "목마름",
        "lat": 35.1629,
        "lng": 128.9846,
    },
    {
        "id": "drink_water_sasang",
        "area": "사상",
        "query": "물 마실 곳",
        "lat": 35.1629,
        "lng": 128.9846,
    },
    {
        "id": "cafe_outlet_seomyeon",
        "area": "서면",
        "query": "서면 근처 콘센트 있는 카페",
        "lat": 35.1579,
        "lng": 129.0592,
    },
    {
        "id": "shopping_seomyeon",
        "area": "서면",
        "query": "서면에서 쇼핑할 곳",
        "lat": 35.1579,
        "lng": 129.0592,
    },
    {
        "id": "shopping_sasang",
        "area": "사상",
        "query": "사상 근처 쇼핑몰 찾아줘",
        "lat": 35.1629,
        "lng": 128.9846,
    },
    {
        "id": "indoor_activity_seomyeon",
        "area": "서면",
        "query": "서면 근처 실내체험",
        "lat": 35.1579,
        "lng": 129.0592,
    },
    {
        "id": "activity_broad_hadan",
        "area": "하단",
        "query": "놀거리 액티비티",
        "lat": 35.1062,
        "lng": 128.9667,
    },
    {
        "id": "pho_hadan",
        "area": "하단",
        "query": "하단역 근처 쌀국수 맛집",
        "lat": 35.1062,
        "lng": 128.9667,
    },
    {
        "id": "toilet_seomyeon",
        "area": "서면",
        "query": "서면역 화장실 급해",
        "lat": 35.1579,
        "lng": 129.0592,
    },
    {
        "id": "smoking_yeonsan_outdoor",
        "area": "연산",
        "query": "연산동 실외 흡연구역",
        "lat": 35.1865,
        "lng": 129.0815,
    },
    {
        "id": "negative_toilet_parking",
        "area": "서면",
        "query": "서면역 근처 화장실 찾아줘 근데 주차장은 빼줘",
        "lat": 35.1579,
        "lng": 129.0592,
    },
    {
        "id": "nonsense",
        "area": "사상",
        "query": "asdf qwer 오늘 주식 알려줘",
        "lat": 35.1629,
        "lng": 128.9846,
    },
]


def _compact(value):
    return str(value or "").strip().lower().replace(" ", "")


def _as_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return [value]


def _frame_values(frame, key):
    values = []
    for item in _as_list(frame.get(key)):
        if isinstance(item, dict):
            item = item.get("value") or item.get("label") or item.get("text")
        if item:
            values.append(str(item))
    return values


def _option_label(option):
    if isinstance(option, dict):
        return str(option.get("value") or option.get("label") or option.get("text") or "")
    return str(option or "")


def _top_results(data, top_n):
    rows = []
    for index, result in enumerate((data.get("results") or [])[:top_n], start=1):
        category = result.get("category") or ""
        rows.append({
            "rank": index,
            "name": result.get("name") or "",
            "category": category,
            "category_display": get_category_display_name(category) or "",
            "address": result.get("address") or result.get("detail_location") or "",
            "source": result.get("candidate_source") or result.get("source") or "",
            "distance_m": result.get("distance_m") or result.get("distance"),
            "reason": (
                result.get("recommendation_reason")
                or result.get("recommend_reason")
                or result.get("semantic_reason")
                or ""
            ),
            "matched_tags": result.get("matched_tags") or result.get("matched_tag_labels") or [],
            "verified_tags": result.get("verified_tags") or result.get("verified_tag_labels") or [],
            "suggested_tags": result.get("suggested_tags") or result.get("suggested_tag_labels") or [],
            "candidate_tags": result.get("candidate_tags") or result.get("candidate_tag_labels") or [],
            "policy_matched_constraints": result.get("policy_matched_constraints") or [],
            "unmet_constraints": result.get("unmet_constraints") or result.get("pre_ai_unmet_constraints") or [],
        })
    return rows


def _category_alias_text(row):
    category = str(row.get("category") or "")
    category_key = _compact(category)
    aliases = []
    if category in CATEGORY_ALIASES:
        aliases.extend(CATEGORY_ALIASES[category])
    if category_key in CATEGORY_ALIASES:
        aliases.extend(CATEGORY_ALIASES[category_key])
    for key, values in CATEGORY_ALIASES.items():
        if _compact(key) and _compact(key) in category_key:
            aliases.extend(values)
    return " ".join(dict.fromkeys(aliases))


def _row_terms(row, *, include_reason=False, include_address=True):
    tag_fields = [
        "matched_tags",
        "verified_tags",
        "suggested_tags",
        "candidate_tags",
        "policy_matched_constraints",
    ]
    pieces = [
        row.get("name") or "",
        row.get("category") or "",
        row.get("category_display") or "",
        _category_alias_text(row),
    ]
    if include_address:
        pieces.append(row.get("address") or "")
    for field in tag_fields:
        pieces.extend(str(item) for item in _as_list(row.get(field)) if item)
    if include_reason:
        pieces.append(row.get("reason") or "")
    return pieces


def _result_text(row, *, include_reason=False, include_address=True):
    return _compact(" ".join(_row_terms(row, include_reason=include_reason, include_address=include_address)))


CASUAL_VISITOR_INTENT_TERMS = tuple(_compact(term) for term in [
    "\uce74\ud398",
    "\ucee4\ud53c",
    "\uc74c\ub8cc",
    "\uc2dd\uc0ac",
    "\uc74c\uc2dd",
    "\ub9db\uc9d1",
    "\uc1fc\ud551",
    "\ubc31\ud654\uc810",
    "\uc544\uc6b8\ub81b",
    "\uc804\uc2dc",
    "\ubc15\ubb3c\uad00",
    "\ubbf8\uc220\uad00",
    "\uac24\ub7ec\ub9ac",
    "\uc2e4\ub0b4\uccb4\ud5d8",
    "\uccb4\ud5d8",
    "\uc561\ud2f0\ube44\ud2f0",
    "\ub180\uac70\ub9ac",
    "\uc0b0\ucc45",
    "\uc270\uacf3",
    "\uc26c",
    "\uae30\ub2e4",
    "\ub370\uc774\ud2b8",
    "\ube44\ud53c",
    "\ub354\uc6cc",
    "\uc88b\uc740\uacf3",
    "\uc2dc\uac04\ubcf4\ub0bc",
    "\ucd94\ucc9c",
])

CASUAL_VISITOR_UNFRIENDLY_TERMS = tuple(_compact(term) for term in [
    "\uacbd\ub85c\ub2f9",
    "\ub178\uc778\uc815",
    "\ub178\uc778\ud68c",
    "\ub178\uc778\ud68c\uad00",
    "\ub178\uc778\ubcf5\uc9c0",
    "\ub9c8\uc744\ud68c\uad00",
    "\ud589\uc815\ubcf5\uc9c0\uc13c\ud130",
    "\uc8fc\ubbfc\uc13c\ud130",
    "\ub3d9\uc8fc\ubbfc\uc13c\ud130",
    "\uad6c\uccad",
    "\uc2dc\uccad",
    "\uc0c1\ub2f4\uc13c\ud130",
    "\uccad\uc18c\ub144\uc0c1\ub2f4",
    "\uc815\uc2e0\uac74\uac15\ubcf5\uc9c0\uc13c\ud130",
    "\ub9c8\uc74c\uc270\ud130",
    "\ub9c8\uc74c\uac74\uac15",
    "\uac74\uac15\uac00\uc815\uc9c0\uc6d0\uc13c\ud130",
    "\uac00\uc871\uc13c\ud130",
    "\uace0\uc6a9\ubcf5\uc9c0\uc13c\ud130",
    "\uc790\ud65c\uc13c\ud130",
    "\uc9c0\uc5ed\uc544\ub3d9\uc13c\ud130",
    "\uc885\ud569\uc0ac\ud68c\ubcf5\uc9c0\uad00",
    "\ubcf5\uc9c0\uad00",
    "\uce58\ub9e4\uc548\uc2ec\uc13c\ud130",
])

CASUAL_VISITOR_UNFRIENDLY_EXEMPT_TERMS = tuple(_compact(term) for term in [
    "\uacbd\ub85c\ub2f9",
    "\uc8fc\ubbfc\uc13c\ud130",
    "\ud589\uc815\ubcf5\uc9c0\uc13c\ud130",
    "\ubcf5\uc9c0\uad00",
    "\uc0c1\ub2f4",
    "\ub9c8\uc74c",
    "\uacf5\uacf5\uae30\uad00",
    "\ubbfc\uc6d0",
    "\ubb34\ub354\uc704\uc270\ud130",
    "\ud55c\ud30c\uc270\ud130",
    "\ud654\uc7a5\uc2e4",
    "\ud761\uc5f0",
    "\uc57d\uad6d",
    "\ubcd1\uc6d0",
    "\uc8fc\ucc28",
    "\uacbd\ucc30",
    "\uc18c\ubc29",
    "\ubcf4\uac74\uc18c",
])


def _contextual_unfriendly_terms(case, frame):
    context_text = _compact(" ".join([
        case.get("query") or "",
        *_frame_values(frame, "target_objects"),
        *_frame_values(frame, "candidate_place_types"),
        *_frame_values(frame, "result_match_terms"),
        *_frame_values(frame, "constraints"),
    ]))
    if not any(term and term in context_text for term in CASUAL_VISITOR_INTENT_TERMS):
        return []
    if any(term and term in context_text for term in CASUAL_VISITOR_UNFRIENDLY_EXEMPT_TERMS):
        return []
    return list(CASUAL_VISITOR_UNFRIENDLY_TERMS)


def _row_core_text(row):
    return _result_text(row, include_reason=True, include_address=False)


def _strict_context_issues(case, frame, top_results):
    query_text = _compact(case.get("query"))
    frame_text = _compact(" ".join([
        *_frame_values(frame, "target_objects"),
        *_frame_values(frame, "candidate_place_types"),
        *_frame_values(frame, "result_match_terms"),
        *_frame_values(frame, "constraints"),
    ]))
    intent_text = _compact(" ".join([
        case.get("query") or "",
        *_frame_values(frame, "target_objects"),
    ]))
    intent_result_text = _compact(" ".join([
        case.get("query") or "",
        *_frame_values(frame, "target_objects"),
        *_frame_values(frame, "result_match_terms"),
    ]))
    context_text = f"{query_text} {frame_text}"
    top3 = top_results[:3]
    issues = []

    if any(term in intent_text for term in ["보드게임", "보드카페"]):
        if top3 and not all("보드게임" in _row_core_text(row) or "보드카페" in _row_core_text(row) for row in top3):
            issues.append("보드게임카페 요청인데 상위 결과가 보드게임카페로 확인되지 않음")

    if any(term in context_text for term in ["콘센트", "배터리", "휴대폰충전", "충전가능", "노트북"]):
        allowed = ["카페", "커피", "도서관", "코워킹", "스터디카페"]
        forbidden = ["충전소", "전기차", "lpg", "주유소", "주차장", "freewifi", "와이파이존", "버스정류장", "초등학교"]
        if top3 and not any(any(term in _row_core_text(row) for term in allowed) for row in top3):
            issues.append("콘센트/충전 요청인데 상위 결과가 카페/도서관류 장소가 아님")
        if any(any(term in _row_core_text(row) for term in forbidden) for row in top_results[:5]):
            issues.append("콘센트/충전 요청에 차량 충전소/와이파이 지점류 후보가 섞임")

    cafe_positive_request = (
        (
            "카페" in intent_text
            or "커피" in intent_result_text
            or "음료" in intent_result_text
        )
        and not any(term in context_text for term in ["카페말고", "커피말고", "카페디저트제외", "카페제외"])
    )
    if cafe_positive_request:
        cafe_forbidden = [
            "카페거리",
            "카페골목",
            "freewifi",
            "공공와이파이",
            "와이파이존",
            "버스정류장",
            "초등학교",
            "중학교",
            "고등학교",
            "인터넷쇼핑몰",
            "통신판매",
            "공간대여",
            "스터디룸",
        ]
        if any(any(term in _row_core_text(row) for term in cafe_forbidden) for row in top_results[:5]):
            issues.append("카페 요청에 카페가 아닌 거리/와이파이/온라인/공간대여 후보가 섞임")

    if any(term in context_text for term in ["쉴곳", "쉬어갈", "잠깐쉴", "비피", "더워", "더운", "실내에서잠깐"]):
        bad_shelter = ["노인", "경로", "마을회관", "복지관", "상담센터", "마음쉼터", "주민센터", "행정복지"]
        if any(any(term in _row_core_text(row) for term in bad_shelter) for row in top_results[:5]):
            issues.append("일반적으로 잠깐 쉬러 가기 어려운 공공/복지/상담 후보가 섞임")

    if any(term in intent_text for term in ["쇼핑몰", "백화점", "아울렛", "쇼핑할곳", "쇼핑"]):
        if "시장" not in intent_text:
            positive = ["복합쇼핑몰", "쇼핑몰", "백화점", "아울렛", "쇼핑센터", "몰"]
            tenant = ["의류판매", "스포츠용품", "생활용품점", "주방용품", "패션잡화점", "음식점", "카페", "약국"]
            if top3 and not any(any(term in _row_core_text(row) for term in positive) for row in top3):
                issues.append("쇼핑 요청인데 상위 결과에 쇼핑몰/백화점/아울렛급 장소가 없음")
            if any(any(term in _row_core_text(row) for term in tenant) and not any(term in _row_core_text(row) for term in positive) for row in top3):
                issues.append("쇼핑 요청에 쇼핑몰 내부 매장/단일 점포 후보가 상위에 섞임")

    if any(term in intent_text for term in ["전시", "박물관", "미술관", "갤러리"]):
        positive = ["전시관", "전시장", "박물관", "미술관", "갤러리", "문화시설", "아트센터"]
        forbidden = ["패션잡화점", "구두", "신발", "의류판매", "생활용품점", "상설할인매장", "도매", "시장"]
        if any(any(term in _row_core_text(row) for term in forbidden) for row in top_results[:5]):
            issues.append("전시/박물관 요청에 판매점/시장 후보가 섞임")
        if top3 and any(not any(term in _row_core_text(row) for term in positive) for row in top3):
            issues.append("전시/박물관 요청에 전시 단어만 포함된 비전시 후보가 섞임")

    if any(term in context_text for term in ["와이파이", "wifi"]):
        visitable = ["카페", "커피", "도서관", "터미널", "역", "쇼핑몰"]
        bad_wifi = ["초등학교", "중학교", "고등학교", "버스정류장"]
        if any(any(term in _row_core_text(row) for term in bad_wifi) for row in top_results[:5]):
            issues.append("와이파이 요청에 일반 방문 장소가 아닌 학교/정류장 지점이 섞임")
        if top3 and not any(any(term in _row_core_text(row) for term in visitable) for row in top3):
            issues.append("와이파이 요청인데 상위 결과가 방문 가능한 장소로 보기 어려움")

    if any("??" in str(row.get("name") or "") or "??" in str(row.get("address") or "") for row in top_results[:5]):
        issues.append("표시명이 깨진 후보가 상위 결과에 포함됨")

    return issues


def _issues_for_case(case, data, frame, top_results):
    query_key = _compact(case.get("query"))
    action = data.get("decision_action") or data.get("decisionAction") or data.get("type") or ""
    count = int(data.get("result_count") or data.get("count") or 0)
    debug = data.get("debug_pipeline") or {}
    location_resolution = debug.get("location_resolution") or {}
    issues = []
    expected_action = case.get("expected_action")
    allow_empty = bool(case.get("allow_empty"))
    min_results = int(case.get("min_results") or 0)
    expected_any_terms = [_compact(term) for term in case.get("expected_any_terms") or [] if _compact(term)]
    blocked_terms = [
        _compact(term)
        for term in case.get("blocked_terms") or []
        if len(_compact(term)) >= 2
    ]
    contextual_unfriendly_terms = _contextual_unfriendly_terms(case, frame)
    expected_options = [_compact(term) for term in case.get("expected_options") or [] if _compact(term)]

    if expected_action and action != expected_action:
        issues.append(f"기대 action={expected_action}, 실제 action={action}")
    if action in {"search", "success"} and count <= 0 and not allow_empty:
        issues.append("검색 실행됐지만 결과 0개")
    if action in {"search", "success"} and min_results and count < min_results and not allow_empty:
        issues.append(f"결과 수가 기대보다 적음: 기대 {min_results}개 이상, 실제 {count}개")
    if action == "ai_unavailable":
        issues.append("AI/local rule이 실행 가능한 의도로 처리하지 못함")
    if action == "ask_clarification" and not data.get("clarification_question"):
        issues.append("되묻기인데 질문 문구 없음")
    if action == "search" and any(row.get("unmet_constraints") for row in top_results[:5]):
        issues.append("상위 결과에 미충족 조건이 남아 있음")
    if action == "search" and (frame.get("location_mode") or frame.get("locationMode")) == "explicit":
        anchor = str(frame.get("anchor_location") or frame.get("anchorLocation") or "")
        anchor_key = _compact(anchor)
        resolution_source = str(location_resolution.get("source") or "")
        resolution_label = str(location_resolution.get("label") or "")
        resolution_address = str(location_resolution.get("address") or "")
        if location_resolution and location_resolution.get("status") != "resolved":
            issues.append("명시 위치를 지도 기준점으로 확정하지 못함")
        if (
            anchor_key
            and resolution_source == "kakao_keyword_nearby"
            and anchor_key not in _compact(resolution_label)
            and anchor_key in _compact(resolution_address)
        ):
            issues.append("명시 위치가 주변 주소의 임의 사업장으로 해석됨")
        expected_address_terms = [_compact(term) for term in case.get("expected_address_terms") or [] if _compact(term)]
        if expected_address_terms:
            top_address_text = _compact(" ".join([
                str(location_resolution.get("address") or ""),
                str(location_resolution.get("label") or ""),
                *(str(row.get("address") or "") for row in top_results[:5]),
            ]))
            missing_terms = [term for term in expected_address_terms if term not in top_address_text]
            if missing_terms:
                issues.append(f"상위 결과 주소가 기대 지역과 맞지 않음: {', '.join(missing_terms)}")
    if expected_options and action == "ask_clarification":
        option_text = _compact(" ".join(
            _option_label(option)
            for option in _as_list(data.get("clarification_options"))
        ))
        missing_options = [term for term in expected_options if term not in option_text]
        if missing_options:
            issues.append(f"되묻기 선택지 누락: {', '.join(missing_options)}")
    if "놀거리" in query_key and "액티비티" in query_key and action != "ask_clarification":
        issues.append("넓은 놀거리 요청이 되묻기로 멈추지 않음")
    if "목마" in query_key and action == "search":
        first_three = top_results[:3]
        if first_three and all("편의점" in _result_text(row) for row in first_three):
            issues.append("목마름 상위 결과가 편의점으로만 쏠림")
    if "쇼핑" in query_key and action == "search":
        blocked = ["인터넷쇼핑몰", "온라인쇼핑", "전자상거래", "통신판매", "쇼핑몰제작"]
        if any(any(term in _result_text(row, include_address=False) for term in blocked) for row in top_results):
            issues.append("온라인 쇼핑/비장소 후보가 상위 결과에 포함됨")
    if ("실내체험" in query_key or ("실내" in query_key and "체험" in query_key)) and action == "search":
        positive = ["보드게임", "만화카페", "방탈출", "공방", "vr", "브이알", "클라이밍", "도예", "공예", "체험"]
        if top_results and not any(any(term in _result_text(row, include_reason=True) for term in positive) for row in top_results[:3]):
            issues.append("실내체험 상위 결과에 체험 시설 근거가 약함")
    if "화장실" in query_key and action == "search":
        if top_results and not any("화장실" in _result_text(row, include_reason=True) for row in top_results[:3]):
            issues.append("화장실 검색 상위 결과에 화장실 근거가 약함")
    if "주차장" in query_key and "빼" in query_key:
        exclusion_text = _compact(" ".join(_frame_values(frame, "exclusions")))
        if "주차장" not in exclusion_text:
            issues.append("주차장 제외 조건이 frame에 반영되지 않음")
    if expected_any_terms and action == "search" and top_results:
        matched_count = sum(
            1
            for row in top_results[:3]
            if any(term in _result_text(row, include_reason=True) for term in expected_any_terms)
        )
        if matched_count == 0:
            issues.append("상위 3개 결과가 기대 목적어와 매칭되지 않음")
    if blocked_terms and action == "search":
        if any(any(term in _result_text(row, include_address=False) for term in blocked_terms) for row in top_results):
            issues.append("차단해야 할 후보가 상위 결과에 포함됨")

    if contextual_unfriendly_terms and action == "search":
        if any(any(term in _result_text(row, include_address=False) for term in contextual_unfriendly_terms) for row in top_results):
            issues.append(
                "\ubb38\ub9e5\uc0c1 \uc77c\ubc18 \ubc29\ubb38 \ucd94\ucc9c\uc5d0 "
                "\ubd80\uc801\uc808\ud55c \ud6c4\ubcf4\uac00 \uc0c1\uc704 \uacb0\uacfc\uc5d0 \ud3ec\ud568\ub428"
            )
    if action == "search":
        issues.extend(_strict_context_issues(case, frame, top_results))

    return issues


def _quality_for_case(case, action, top_results, frame=None):
    expected_any_terms = [_compact(term) for term in case.get("expected_any_terms") or [] if _compact(term)]
    blocked_terms = [
        _compact(term)
        for term in case.get("blocked_terms") or []
        if len(_compact(term)) >= 2
    ]
    if frame is not None:
        blocked_terms = list(dict.fromkeys([*blocked_terms, *_contextual_unfriendly_terms(case, frame)]))
    if action == "search" and not top_results and case.get("allow_empty"):
        return {
            "label": "empty_allowed",
            "top3_expected_match_count": 0,
            "top5_blocked_count": 0,
        }
    if action == "ask_clarification":
        return {
            "label": "clarification",
            "top3_expected_match_count": 0,
            "top5_blocked_count": 0,
        }
    top3 = top_results[:3]
    top5 = top_results[:5]
    expected_match_count = (
        sum(1 for row in top3 if any(term in _result_text(row, include_reason=True) for term in expected_any_terms))
        if expected_any_terms
        else None
    )
    blocked_count = (
        sum(1 for row in top5 if any(term in _result_text(row, include_address=False) for term in blocked_terms))
        if blocked_terms
        else 0
    )
    if blocked_count:
        label = "bad_blocked_candidate"
    elif expected_match_count is None:
        label = "unchecked"
    elif expected_match_count >= 2:
        label = "good"
    elif expected_match_count == 1:
        label = "weak"
    else:
        label = "bad"
    return {
        "label": label,
        "top3_expected_match_count": expected_match_count,
        "top5_blocked_count": blocked_count,
    }


def _case_summary(case, data, elapsed_ms, top_n):
    frame = data.get("place_intent_frame") or {}
    debug = data.get("debug_pipeline") or {}
    query_generation = data.get("query_generation") or debug.get("query_generation") or {}
    counts = data.get("candidate_source_counts") or debug.get("candidate_counts") or {}
    top_results = _top_results(data, top_n)
    issues = _issues_for_case(case, data, frame, top_results)
    action = data.get("decision_action") or data.get("decisionAction") or data.get("type") or ""
    quality = _quality_for_case(case, action, top_results, frame)

    return {
        "id": case.get("id") or "",
        "case_id": case.get("case_id") or case.get("id") or "",
        "case_label": case.get("case_label") or case.get("label") or "",
        "demo_note": case.get("demo_note") or "",
        "variant_index": case.get("variant_index"),
        "variant_count": case.get("variant_count"),
        "step_index": case.get("step_index"),
        "step_count": case.get("step_count"),
        "area": case.get("area") or "",
        "raw_query": case.get("query") or "",
        "request": {
            "lat": case.get("lat"),
            "lng": case.get("lng"),
            "limit": case.get("limit", 15),
        },
        "action": action,
        "status": "needs_review" if issues else "ok",
        "issues": issues,
        "quality": quality,
        "clarification_question": data.get("clarification_question") or "",
        "clarification_options": data.get("clarification_options") or [],
        "frame": {
            "location_mode": frame.get("location_mode") or frame.get("locationMode") or "",
            "anchor_location": frame.get("anchor_location") or frame.get("anchorLocation") or "",
            "target_objects": _frame_values(frame, "target_objects"),
            "candidate_place_types": _frame_values(frame, "candidate_place_types"),
            "result_match_terms": _frame_values(frame, "result_match_terms"),
            "constraints": _frame_values(frame, "constraints"),
            "exclusions": _frame_values(frame, "exclusions"),
            "ranking_policy": frame.get("ranking_policy") or frame.get("rankingPolicy") or "",
            "candidate_category_codes": _frame_values(frame, "candidate_category_codes"),
        },
        "search": {
            "primary_queries": query_generation.get("primary_queries") or data.get("external_queries") or [],
            "fallback_queries": query_generation.get("fallback_queries") or [],
            "db_search_terms": (debug.get("evidence_terms") or {}).get("db_search_terms") or [],
            "kakao_query_result_counts": (
                (debug.get("reranker") or {}).get("kakao_query_result_counts")
                or data.get("external_query_result_counts")
                or []
            ),
        },
        "location_resolution": debug.get("location_resolution") or {},
        "counts": {
            "db": counts.get("db", 0),
            "kakao": counts.get("kakao", 0),
            "web": counts.get("web", 0),
            "top_results": data.get("result_count") or data.get("count") or 0,
        },
        "top_results": top_results,
        "timing_ms": {
            "total_observed": elapsed_ms,
            "pipeline_total": debug.get("total_latency_ms"),
            "planner": debug.get("planner_latency_ms"),
            "retrieval": debug.get("retrieval_latency_ms"),
            "reranker": debug.get("reranker_latency_ms"),
        },
    }


def _case_steps(case):
    steps = case.get("steps")
    if not isinstance(steps, list) or not steps:
        return [case]
    step_count = len([step for step in steps if isinstance(step, dict) and step.get("query")])
    result = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or not step.get("query"):
            continue
        result.append({
            **case,
            **step,
            "id": f"{case.get('id') or 'case'}#{index}",
            "case_id": case.get("id") or "",
            "case_label": case.get("label") or case.get("case_label") or "",
            "step_index": index,
            "step_count": step_count,
        })
    return result


AUTO_VARIANT_REPLACEMENTS = [
    [
        ("근처", "주변"),
        ("찾아줘", "알려줘"),
        ("추천해줘", "추천해줄래"),
        ("어디 있어", "어디 있을까"),
        ("먹고 싶어", "먹고 싶은데"),
        ("할 곳", "할 만한 곳"),
        ("갈만한", "가기 괜찮은"),
    ],
    [
        ("역 근처", "역 주변"),
        ("말고", "제외하고"),
        ("빼줘", "제외해줘"),
        ("급해", "급해요"),
        ("찾아줘", "찾아줄래"),
        ("추천해줘", "골라줘"),
        ("어디 가지", "어디 가면 좋을까"),
        ("좋은 곳", "괜찮은 곳"),
    ],
]


def _auto_variant_query(query, round_index):
    text = str(query or "")
    if round_index <= 0 or not text:
        return text
    replacements = AUTO_VARIANT_REPLACEMENTS[(round_index - 1) % len(AUTO_VARIANT_REPLACEMENTS)]
    changed = text
    for source, target in replacements:
        changed = changed.replace(source, target)
    if changed != text:
        return changed
    suffixes = [" 좀", " 부탁해"]
    return f"{text}{suffixes[(round_index - 1) % len(suffixes)]}"


def _case_for_round(case, round_index):
    variants = case.get("variants")
    if not isinstance(variants, list) or not variants:
        query = _auto_variant_query(case.get("query"), round_index)
        if query == case.get("query") and round_index <= 0:
            return case
        return {
            **case,
            "id": f"{case.get('id') or 'case'}#v{round_index + 1}",
            "case_id": case.get("case_id") or case.get("id") or "",
            "original_query": case.get("original_query") or case.get("query") or "",
            "query": query,
            "variant_index": round_index + 1,
            "variant_count": 0,
        }
    variant = variants[round_index % len(variants)]
    if isinstance(variant, str):
        variant = {"query": variant}
    if not isinstance(variant, dict) or not variant.get("query"):
        return case
    return {
        **case,
        **variant,
        "id": f"{case.get('id') or 'case'}#v{(round_index % len(variants)) + 1}",
        "case_id": case.get("id") or "",
        "case_label": case.get("label") or case.get("case_label") or "",
        "variant_index": (round_index % len(variants)) + 1,
        "variant_count": len(variants),
    }


def _followup_payload(previous_data, *, current_query, previous_query):
    if not isinstance(previous_data, dict):
        return {}
    previous_search_plan = previous_data.get("search_plan") or {}
    pending_frame = (
        previous_search_plan.get("place_intent_frame")
        or previous_search_plan.get("placeIntentFrame")
        or previous_data.get("place_intent_frame")
        or {}
    )
    previous_context = {
        "search_plan": previous_search_plan,
        "pending_clarification_frame": pending_frame,
        "is_clarification_followup": previous_data.get("decision_action") == "ask_clarification",
        "clarification_answer": current_query,
        "pending_clarification_question": previous_data.get("clarification_question") or "",
        "previous_user_query": previous_query,
    }
    return {
        "previousContext": previous_context,
        "previous_context": previous_context,
        "previous_search_context": previous_context,
        "previous_search_plan": previous_search_plan,
        "pending_clarification_frame": pending_frame,
        "pending_clarification_question": previous_context["pending_clarification_question"],
        "is_clarification_followup": previous_context["is_clarification_followup"],
        "clarification_answer": current_query,
        "previous_user_query": previous_query,
    }


def _case_success_rates(rows):
    grouped = {}
    for row in rows:
        key = row.get("case_id") or row.get("id") or row.get("raw_query") or ""
        round_index = row.get("round") or 1
        grouped.setdefault(key, {}).setdefault(round_index, []).append(row)

    rates = []
    for key, rounds in grouped.items():
        attempts = len(rounds)
        success = sum(
            1
            for step_rows in rounds.values()
            if step_rows and all(row.get("status") == "ok" for row in step_rows)
        )
        first_row = next((items[0] for items in rounds.values() if items), {})
        rates.append({
            "case_id": key,
            "label": first_row.get("case_label") or first_row.get("raw_query") or key,
            "demo_note": first_row.get("demo_note") or "",
            "success_count": success,
            "attempt_count": attempts,
            "success_rate": round(success / attempts, 4) if attempts else 0,
        })
    return sorted(rates, key=lambda item: (item["success_rate"], item["case_id"]), reverse=True)


def _load_cases(path, inline_queries, options):
    if inline_queries:
        return [
            {
                "id": f"inline_{index}",
                "area": "manual",
                "query": query,
                "lat": options["lat"],
                "lng": options["lng"],
            }
            for index, query in enumerate(inline_queries, start=1)
        ]
    if path:
        raw = Path(path).read_text(encoding="utf-8")
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            loaded = loaded.get("cases") or []
        return [
            case
            for case in loaded
            if isinstance(case, dict) and (case.get("query") or case.get("steps"))
        ]
    return list(DEFAULT_CASES)


def _markdown_for_run(payload):
    lines = [
        f"## {payload['created_at']} 검색 품질 로그",
        "",
        f"- 실행 케이스: {payload['count']}개",
        f"- 점검 필요: {payload['needs_review_count']}개",
        "",
        "| 상태 | 품질 | 지역 | 문장 | 해석 | 검색어 | 후보수 | 상위 결과 | 이슈 |",
        "|---|---|---|---|---|---|---:|---|---|",
    ]
    for row in payload["results"]:
        frame = row.get("frame") or {}
        top_results = row.get("top_results") or []
        top = top_results[0] if top_results else {}
        interpreted = ", ".join(frame.get("target_objects") or frame.get("candidate_place_types") or ["-"])
        queries = ", ".join((row.get("search") or {}).get("primary_queries") or ["-"])
        top_label = " / ".join(
            item for item in [top.get("name"), top.get("category"), str(top.get("distance_m") or "")]
            if item
        ) or "-"
        issues = "<br>".join(row.get("issues") or []) if row.get("issues") else "-"
        lines.append(
            "| {status} | {quality} | {area} | `{query}` | {interpreted} | {queries} | {count} | {top} | {issues} |".format(
                status=row.get("status", "-"),
                quality=(row.get("quality") or {}).get("label", "-"),
                area=row.get("area") or "-",
                query=(row.get("raw_query") or "").replace("|", "\\|"),
                interpreted=interpreted.replace("|", "\\|"),
                queries=queries.replace("|", "\\|"),
                count=(row.get("counts") or {}).get("top_results", 0),
                top=top_label.replace("|", "\\|"),
                issues=issues.replace("|", "\\|"),
            )
        )
    if payload.get("case_success_rates"):
        lines.extend([
            "",
            "### 케이스별 성공률",
            "",
            "| 케이스 | 성공 | 비고 |",
            "|---|---:|---|",
        ])
        for item in payload["case_success_rates"]:
            lines.append(
                "| {label} | {success}/{attempts} | {note} |".format(
                    label=(item.get("label") or item.get("case_id") or "-").replace("|", "\\|"),
                    success=item.get("success_count", 0),
                    attempts=item.get("attempt_count", 0),
                    note=(item.get("demo_note") or "").replace("|", "\\|") or "-",
                )
            )
    lines.append("")
    return "\n".join(lines)


class Command(BaseCommand):
    help = "Run live /ai-search/ search quality smoke cases and save JSON/Markdown diagnostics."

    def add_arguments(self, parser):
        parser.add_argument("--repeat", type=int, default=1)
        parser.add_argument("--query", action="append", default=[])
        parser.add_argument("--case-file", default="")
        parser.add_argument("--lat", type=float, default=35.1556)
        parser.add_argument("--lng", type=float, default=129.0641)
        parser.add_argument("--limit", type=int, default=15)
        parser.add_argument("--top", type=int, default=5)
        parser.add_argument("--output", default="")
        parser.add_argument("--no-log", action="store_true")
        parser.add_argument("--case-offset", type=int, default=0)
        parser.add_argument("--case-count", type=int, default=0)

    def handle(self, *args, **options):
        repeat = max(1, min(int(options["repeat"] or 1), 20))
        top_n = max(1, min(int(options["top"] or 5), 10))
        cases = _load_cases(options["case_file"], options["query"], options)
        case_offset = max(0, int(options["case_offset"] or 0))
        case_count = max(0, int(options["case_count"] or 0))
        if case_offset or case_count:
            case_end = case_offset + case_count if case_count else None
            cases = cases[case_offset:case_end]
        output_path = Path(options["output"]) if options["output"] else LATEST_JSON
        run_started_at = timezone.localtime()

        rows = []
        for round_index in range(repeat):
            for case_index, case in enumerate(cases, start=1):
                case = _case_for_round(case, round_index)
                previous_data = None
                previous_query = ""
                for step_case in _case_steps(case):
                    request_case = {
                        **step_case,
                        "limit": int(step_case.get("limit") or case.get("limit") or options["limit"] or 15),
                        "lat": float(step_case.get("lat", case.get("lat", options["lat"]))),
                        "lng": float(step_case.get("lng", case.get("lng", options["lng"]))),
                    }
                    started = time.perf_counter()
                    try:
                        payload = {
                            "query": request_case["query"],
                            "originalQuery": request_case.get("original_query") or request_case["query"],
                            "lat": request_case["lat"],
                            "lng": request_case["lng"],
                            "limit": request_case["limit"],
                        }
                        if previous_data is not None and request_case.get("use_previous_context", True):
                            payload.update(_followup_payload(
                                previous_data,
                                current_query=request_case["query"],
                                previous_query=previous_query,
                            ))
                        data = run_ai_search(payload)
                        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                        row = _case_summary(request_case, data, elapsed_ms, top_n)
                        previous_data = data
                        previous_query = request_case["query"]
                    except Exception as exc:
                        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                        row = {
                            "id": request_case.get("id") or f"case_{case_index}",
                            "case_id": request_case.get("case_id") or request_case.get("id") or "",
                            "case_label": request_case.get("case_label") or request_case.get("label") or "",
                            "demo_note": request_case.get("demo_note") or "",
                            "variant_index": request_case.get("variant_index"),
                            "variant_count": request_case.get("variant_count"),
                            "step_index": request_case.get("step_index"),
                            "step_count": request_case.get("step_count"),
                            "area": request_case.get("area") or "",
                            "raw_query": request_case["query"],
                            "request": {
                                "lat": request_case["lat"],
                                "lng": request_case["lng"],
                                "limit": request_case["limit"],
                            },
                            "action": "exception",
                            "status": "needs_review",
                            "issues": [f"{exc.__class__.__name__}: {exc}"],
                            "frame": {},
                            "search": {},
                            "counts": {"db": 0, "kakao": 0, "web": 0, "top_results": 0},
                            "top_results": [],
                            "timing_ms": {"total_observed": elapsed_ms},
                        }
                    row["round"] = round_index + 1
                    rows.append(row)
                    status_label = "OK" if row["status"] == "ok" else "REVIEW"
                    step_label = (
                        f" ({row.get('step_index')}/{row.get('step_count')})"
                        if row.get("step_index")
                        else ""
                    )
                    self.stdout.write(
                        f"[{status_label}] {row['area'] or '-'}{step_label} | {row['raw_query']} | "
                        f"{row['action']} | top={row['counts'].get('top_results', 0)} | "
                        f"{', '.join(row.get('issues') or [])}"
                    )

        payload = {
            "created_at": run_started_at.isoformat(),
            "repeat": repeat,
            "count": len(rows),
            "needs_review_count": sum(1 for row in rows if row["status"] != "ok"),
            "case_success_rates": _case_success_rates(rows),
            "results": rows,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if not options["no_log"]:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with JSONL_LOG.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
            markdown = _markdown_for_run(payload)
            if MARKDOWN_LOG.exists():
                previous = MARKDOWN_LOG.read_text(encoding="utf-8")
                MARKDOWN_LOG.write_text(markdown + "\n" + previous, encoding="utf-8")
            else:
                MARKDOWN_LOG.write_text("# 검색 품질 누적 로그\n\n" + markdown, encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Saved latest search quality evaluation to {output_path}"))
        if not options["no_log"]:
            self.stdout.write(self.style.SUCCESS(f"Appended logs to {JSONL_LOG} and {MARKDOWN_LOG}"))
