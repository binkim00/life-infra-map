TAG_DISPLAY_NAMES = {
    "노트북작업": "노트북 작업 가능",
    "작업가능후보": "작업 가능 후보",
    "와이파이": "와이파이 있음",
    "콘센트있음": "콘센트 있음",
    "조용한": "조용함",
    "혼자이용좋음": "혼자 이용하기 좋음",
    "잠깐쉬기좋음": "잠깐 쉬기 좋음",
    "실내쉼터": "실내 쉼터",
    "편의시설": "편의시설 있음",
    "산책좋음": "산책하기 좋음",
    "힐링": "힐링하기 좋음",
    "전망좋음": "전망 좋음",
    "야경": "야경 보기 좋음",
    "사진찍기좋음": "사진 찍기 좋음",
    "호수": "호수 주변",
    "벚꽃": "벚꽃 보기 좋음",
    "개방형흡연구역": "개방형 흡연구역",
    "부스형흡연구역": "부스형 흡연구역",
    "실내흡연실": "실내 흡연실",
    "실외흡연구역": "실외 흡연구역",
    "식사가능": "식사 가능",
    "주차가능": "주차 가능",
    "디저트": "디저트 있음",
    "분위기좋음": "분위기 좋음",
    "대형카페": "대형 카페",
    "커피맛집": "커피 맛집",
    "야외자리": "야외 자리 있음",
}

HIDDEN_TAG_NAMES = {
    "필수태그없음",
    "필수태그누락",
    "없는태그테스트",
}

CATEGORY_DISPLAY_NAMES = {
    "cafe": "카페",
    "shelter": "쉼터",
    "city_park": "공원",
    "beach": "해수욕장",
    "tourism": "관광지",
    "smoking_area": "흡연구역",
    "restaurant": "식당",
    "toilet": "화장실",
    "freewifi": "무료 와이파이",
    "parking": "주차장",
}

SOURCE_TYPE_LABELS = {
    "db_verified": "DB 검증 태그 기반",
    "db_candidate": "DB 후보 태그 기반",
    "db_category_fallback": "DB 카테고리 기반",
    "kakao_with_db_tags": "카카오+DB 태그 보강",
    "kakao_candidate": "카카오 검색 후보",
}

CONFIDENCE_LABELS = {
    "high": "높은 신뢰도",
    "medium": "중간 신뢰도",
    "low": "낮은 신뢰도",
}

FALLBACK_LEVEL_LABELS = {
    1: "검증 태그 기반 추천",
    2: "후보 태그 기반 추천",
    3: "카테고리 기반 fallback",
    4: "외부 후보 + DB 태그 보강",
    5: "외부/카테고리 후보",
}

FALLBACK_LEVEL_DESCRIPTIONS = {
    1: "DB 검증 태그가 사용자 조건과 일치한 추천입니다.",
    2: "DB 후보 태그 또는 일반 태그가 일부 일치한 추천입니다.",
    3: "세부 태그 근거가 부족해 DB 카테고리와 거리 기준으로 제공하는 fallback 후보입니다.",
    4: "카카오 또는 외부 검색 후보에 DB 태그를 보강한 후보입니다.",
    5: "카카오 또는 외부 검색의 카테고리 기반 후보입니다.",
}


def normalize_tag_name(tag_name):
    if tag_name in (None, ""):
        return ""

    return str(tag_name).strip().replace(" ", "")


def is_hidden_tag_name(tag_name):
    normalized = normalize_tag_name(tag_name)
    if normalized in HIDDEN_TAG_NAMES:
        return True

    if "테스트" in normalized:
        return True

    if normalized.startswith("필수태그") and ("없음" in normalized or "누락" in normalized):
        return True

    if normalized.startswith("없는태그"):
        return True

    return False


def get_visible_tag_names(tag_names):
    return [
        tag_name
        for tag_name in tag_names or []
        if normalize_tag_name(tag_name) and not is_hidden_tag_name(tag_name)
    ]


def get_tag_display_name(tag_name):
    normalized = normalize_tag_name(tag_name)
    if not normalized:
        return ""

    if is_hidden_tag_name(normalized):
        return "요청한 조건"

    return TAG_DISPLAY_NAMES.get(normalized, str(tag_name or "").strip())


def get_tag_display_names(tag_names, hidden_label="요청한 조건"):
    labels = []
    hidden_count = 0

    for tag_name in tag_names or []:
        normalized = normalize_tag_name(tag_name)
        if not normalized:
            continue

        if is_hidden_tag_name(normalized):
            hidden_count += 1
            continue

        labels.append(get_tag_display_name(tag_name))

    if hidden_count and hidden_label and hidden_label not in labels:
        labels.append(hidden_label)

    return labels


def get_category_display_name(category):
    return CATEGORY_DISPLAY_NAMES.get(category, category or "")


def get_source_label(source_type):
    return SOURCE_TYPE_LABELS.get(source_type, source_type or "")


def get_confidence_label(confidence):
    return CONFIDENCE_LABELS.get(confidence, confidence or "")


def get_fallback_label(fallback_level):
    return FALLBACK_LEVEL_LABELS.get(fallback_level, "")


def get_fallback_description(fallback_level):
    return FALLBACK_LEVEL_DESCRIPTIONS.get(fallback_level, "")
