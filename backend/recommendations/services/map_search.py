"""
일반 지도 검색(`/map`)의 DB 장소 검색 로직.

AI 해석 없이 입력한 검색어를 그대로 쓰되, 아래 세 가지를 서비스 레벨에서 처리한다.

1. 검색어를 토큰 단위로 나눠 AND 매칭한다. (`서면 카페` 같은 복합 검색어 지원)
2. 이름/카테고리/태그/주소 중 어디서 맞았는지에 따라 관련도 점수를 매긴다.
3. 좌표가 있으면 bounding box로 먼저 좁힌 뒤 필요한 만큼만 반경을 넓힌다.
"""

import math
import re

from django.db import connection
from django.db.models import BooleanField, Exists, OuterRef, Q, Value
from django.db.models.expressions import RawSQL

from recommendations.models import Place, PlaceTag, Tag


# 검색어에서 카테고리를 유추할 때 쓰는 별칭 목록입니다.
# `Place.category` 값과 사용자가 실제로 입력하는 표현을 연결합니다.
PLACE_CATEGORY_ALIASES = {
    "toilet": ["toilet", "화장실", "공중화장실", "공용화장실", "변소"],
    "freewifi": ["freewifi", "wifi", "wi-fi", "와이파이", "무료와이파이", "무선인터넷"],
    "smoking_area": ["smoking", "smoking_area", "흡연", "흡연구역", "흡연실"],
    "beach": ["beach", "해수욕장", "해변", "바다"],
    "parking": ["parking", "주차", "주차장"],
    "city_park": ["city_park", "citypark", "공원", "도시공원"],
    "tourism": ["tourism", "관광", "관광지", "여행", "명소"],
    "cafe": ["cafe", "카페", "커피", "커피숍", "카페테리아"],
    "shelter": ["shelter", "쉼터", "무더위쉼터", "한파쉼터"],
}

PLACE_CATEGORY_ALIASES["restaurant"] = [
    "restaurant",
    "\uc2dd\ub2f9",
    "\uc74c\uc2dd\uc810",
    "\ub9db\uc9d1",
    "\ubc25\uc9d1",
]

LOCATION_TOKEN_SUFFIXES = (
    "\uc2dc",
    "\ub3c4",
    "\uad6c",
    "\uad70",
    "\ub3d9",
    "\uc74d",
    "\uba74",
    "\ub9ac",
    "\uc5ed",
)

SOFT_PREFERENCE_TOKENS = frozenset({
    "\ubd84\uc704\uae30",
    "\uc88b\uc740",
    "\uc88b\uc740\uacf3",
    "\uc870\uc6a9\ud55c",
    "\uc608\uc05c",
    "\uad1c\ucc2e\uc740",
    "\ub9db\uc788\ub294",
    "\ucd94\ucc9c",
})

# `주차장 말고 화장실`처럼 바로 앞 단어를 제외 조건으로 바꾸는 표현입니다.
NEGATION_MARKERS = (
    "말고",
    "말구",
    "빼고",
    "제외하고",
    "제외한",
    "제외",
    "아니고",
    "아닌",
    "이외",
    "외에",
)

# 장소 데이터에는 거의 등장하지 않고 검색어만 좁히는 표현입니다.
STOPWORD_TOKENS = frozenset({
    "근처",
    "주변",
    "가까운",
    "가까이",
    "여기",
    "저기",
    "이곳",
    "그곳",
    "어디",
    "좀",
    "제일",
    "가장",
    "추천",
    "추천해줘",
    "알려줘",
    "찾아줘",
    "보여줘",
    "해줘",
    "있는",
    "있나",
    "있을까",
    "인",
    "의",
})

TOKEN_SPLIT_PATTERN = re.compile(r"[^0-9A-Za-z가-힣]+")

# 관련도 점수. 값 자체보다 순서가 중요합니다.
SCORE_NAME_EXACT = 100
SCORE_NAME_PREFIX = 70
SCORE_NAME_PHRASE = 55
# 저장된 태그는 이 서비스가 직접 검수/보강하는 정보이므로, 상호명에 우연히 단어가
# 들어간 경우보다 강한 근거로 본다.
# 예: `장애인 화장실`은 이름에 `장애인`이 들어간 건물의 화장실보다
#     `장애인화장실있음` 태그가 붙은 화장실이 먼저 나와야 한다.
SCORE_TAG_MATCH = 45
SCORE_NAME_ALL_TOKENS = 40
SCORE_CATEGORY = 25
SCORE_ADDRESS = 12
SCORE_NO_EVIDENCE = 10

# 이름이 같은 후보가 여러 건일 때 검색어의 업종과 맞는 쪽을 위로 올립니다.
# 예: `해운대 해수욕장`은 같은 이름의 와이파이 AP보다 해수욕장 장소가 먼저 나와야 합니다.
SCORE_CATEGORY_BONUS = 5

# 좌표가 있을 때 결과가 부족하면 이 순서로 반경을 넓힙니다.
RADIUS_EXPANSION_STEPS_M = (1000, 3000, 10000, 50000)

# 같은 장소로 묶을 때 쓰는 좌표 반올림 자릿수입니다. (소수점 3자리 ≈ 100m 격자)
DUPLICATE_COORD_PRECISION = 3

# 같은 이름이 서로 떨어진 좌표에 수십 건 저장된 경우(예: 해수욕장 구간별 와이파이 AP)
# 결과 목록을 한 이름이 다 차지하지 않도록 상위 몇 건만 남깁니다.
MAX_RESULTS_PER_NAME = 3

EARTH_RADIUS_M = 6371000
METERS_PER_LAT_DEGREE = 111320.0


def normalize_compact(value):
    """비교용으로 공백을 없애고 소문자로 맞춘 문자열을 만든다."""
    return (value or "").replace(" ", "").lower()


def tokenize_query(keyword):
    """
    검색어를 포함 토큰과 제외 토큰으로 나눈다.

    `주차장 말고 화장실` -> (["화장실"], ["주차장"])
    """
    raw_tokens = [token for token in TOKEN_SPLIT_PATTERN.split(keyword or "") if token]

    include_tokens = []
    exclude_tokens = []

    for token in raw_tokens:
        if token in NEGATION_MARKERS:
            # 제외 표현 바로 앞 단어를 제외 조건으로 옮깁니다.
            if include_tokens:
                exclude_tokens.append(include_tokens.pop())
            continue

        include_tokens.append(token)

    meaningful_tokens = [
        token for token in include_tokens
        if token not in STOPWORD_TOKENS
    ]

    # 검색어가 불용어뿐이면 원래 토큰을 그대로 씁니다.
    if meaningful_tokens:
        include_tokens = meaningful_tokens

    return include_tokens, exclude_tokens


def get_matching_categories(keyword):
    """검색어에 별칭이 포함된 `Place.category` 목록을 돌려준다."""
    normalized_keyword = normalize_compact(keyword)

    if not normalized_keyword:
        return []

    return [
        category
        for category, aliases in PLACE_CATEGORY_ALIASES.items()
        if any(normalize_compact(alias) in normalized_keyword for alias in aliases)
    ]


def build_token_filter(token):
    """
    토큰 하나가 장소의 어느 필드에든 맞으면 통과하는 조건을 만든다.

    `source`, `external_id` 같은 내부 필드는 사용자 검색 대상이 아니므로 제외한다.
    """
    token_filter = (
        Q(name__icontains=token)
        | Q(address__icontains=token)
        | Q(detail_location__icontains=token)
        | Q(place_tags__tag__name__icontains=token)
    )

    matched_categories = get_matching_categories(token)
    if matched_categories:
        token_filter |= Q(category__in=matched_categories)

    return token_filter


def apply_keyword_filter(queryset, include_tokens, exclude_tokens):
    """
    포함 토큰은 AND, 제외 토큰은 NOT으로 적용한다.

    다중 값 관계(`place_tags`)에서 토큰마다 다른 태그로 매칭될 수 있어야 하므로
    하나의 `filter()`에 묶지 않고 토큰별로 `filter()`를 이어 붙인다.
    """
    for token in include_tokens:
        queryset = queryset.filter(build_token_filter(token))

    for token in exclude_tokens:
        excluded_categories = get_matching_categories(token)
        exclude_filter = Q(name__icontains=token)

        if excluded_categories:
            exclude_filter |= Q(category__in=excluded_categories)

        queryset = queryset.exclude(exclude_filter)

    if include_tokens or exclude_tokens:
        # `place_tags` 조인 때문에 생기는 중복을 걷어낸다.
        # `.distinct()`를 그대로 쓰면 `raw`(JSONField)까지 포함한 전체 행을 정렬해야 해서
        # Postgres가 디스크로 스필한다. id만 추려서 다시 조회하면 정렬 대상이 정수 하나로 줄어든다.
        queryset = queryset.model.objects.filter(pk__in=queryset.values("pk"))

    return queryset


def calculate_distance_m(lat1, lng1, lat2, lng2):
    """두 좌표 사이의 거리를 미터 단위로 계산한다."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )

    return int(EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def supports_postgis():
    """PostGIS 를 쓸 수 있는 DB 인지 확인한다. SQLite 로 되돌려도 동작해야 하므로 매번 확인한다."""
    return connection.vendor == "postgresql"


def _geography_point(lat, lng):
    """`ST_MakePoint` 는 (경도, 위도) 순서다."""
    return "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography", [lng, lat]


def apply_radius_filter(queryset, lat, lng, radius_m):
    """
    반경 조건을 걸고, 가능하면 거리도 DB 에서 함께 계산한다.

    PostGIS 가 있으면 `ST_DWithin` 이 GiST 인덱스로 정확한 반경을 처리하므로
    파이썬에서 행마다 하버사인을 돌 필요가 없다.
    없으면 기존대로 bounding box 로 좁히고 거리는 파이썬에서 계산한다.

    (쿼리셋, DB 가 거리를 계산했는지 여부) 를 돌려준다.
    """
    if lat is None or lng is None:
        return queryset, False

    if not supports_postgis():
        if radius_m:
            queryset = queryset.filter(**build_bounding_box(lat, lng, radius_m))
        return queryset, False

    point_sql, point_params = _geography_point(lat, lng)
    queryset = queryset.annotate(
        db_distance=RawSQL(f"ST_Distance(geog, {point_sql})", point_params),
    )
    if radius_m:
        queryset = queryset.annotate(
            within_radius=RawSQL(
                f"ST_DWithin(geog, {point_sql}, %s)",
                [*point_params, radius_m],
            ),
        ).filter(within_radius=True)
    return queryset, True


def build_bounding_box(lat, lng, radius_m):
    """반경을 감싸는 위경도 범위를 만든다. SQL에서 먼저 후보를 줄이는 용도다."""
    lat_delta = radius_m / METERS_PER_LAT_DEGREE
    cos_lat = math.cos(math.radians(lat))
    lng_delta = radius_m / (METERS_PER_LAT_DEGREE * max(abs(cos_lat), 0.01))

    return {
        "lat__gte": lat - lat_delta,
        "lat__lte": lat + lat_delta,
        "lng__gte": lng - lng_delta,
        "lng__lte": lng + lng_delta,
    }


def split_discriminating_tokens(include_tokens):
    """
    업종을 가리키는 토큰과 그 안에서 후보를 갈라주는 토큰을 나눈다.

    `화장실`처럼 토큰이 곧 업종인 경우, 이름에 `화장실`이 들어갔다는 사실은
    추가 정보가 아니다. 이때 이름 매칭으로 순위를 올리면 훨씬 가까운 화장실이
    이름만 맞는 먼 화장실에 밀리므로, 업종 토큰은 이름 점수에서 제외한다.
    """
    discriminating_tokens = []

    for token in include_tokens:
        if not get_matching_categories(token):
            discriminating_tokens.append(token)

    return discriminating_tokens


def calculate_relevance_score(*, name, address, detail_location, category,
                              include_tokens, normalized_query, matched_categories,
                              has_tag_match=False, attribute_query=False):
    """
    검색어가 장소의 어느 부분에 맞았는지로 관련도를 매긴다.

    저장된 태그로 맞은 후보는 이름에 단어가 우연히 들어간 후보보다 높게 본다.
    """
    category_bonus = SCORE_CATEGORY_BONUS if category in matched_categories else 0

    if not include_tokens:
        return SCORE_CATEGORY + category_bonus

    normalized_name = normalize_compact(name)

    if normalized_name and normalized_name == normalized_query:
        return SCORE_NAME_EXACT + category_bonus

    if attribute_query:
        # 속성 검색에서는 태그가 근거이고, 상호명에 그 단어가 들어간 것은 근거가 아닙니다.
        if has_tag_match:
            return SCORE_TAG_MATCH + category_bonus

        if category_bonus:
            return SCORE_CATEGORY + category_bonus
    else:
        if normalized_query and normalized_name.startswith(normalized_query):
            return SCORE_NAME_PREFIX + category_bonus

        if normalized_query and normalized_query in normalized_name:
            return SCORE_NAME_PHRASE + category_bonus

        if has_tag_match:
            return SCORE_TAG_MATCH + category_bonus

        if normalized_name and all(
            normalize_compact(token) in normalized_name for token in include_tokens
        ):
            return SCORE_NAME_ALL_TOKENS + category_bonus

        if category_bonus:
            return SCORE_CATEGORY + category_bonus

    normalized_location = normalize_compact(f"{address} {detail_location}")
    if normalized_location and any(
        normalize_compact(token) in normalized_location for token in include_tokens
    ):
        return SCORE_ADDRESS

    return SCORE_NO_EVIDENCE


def is_attribute_query(tokens):
    """
    검색 토큰이 전부 장소의 속성(태그)을 가리키는지 판단한다.

    `장애인`, `조용한`, `콘센트`처럼 저장된 태그명에 해당하는 표현은 속성이고,
    `부산시청`, `해운대`처럼 태그에 없는 표현은 장소명으로 본다.
    속성 검색에서는 상호명에 그 단어가 우연히 들어간 것보다 태그가 강한 근거다.
    """
    if not tokens:
        return False

    tag_names = [
        normalize_compact(tag_name)
        for tag_name in Tag.objects.values_list("name", flat=True)
    ]

    return all(
        any(normalize_compact(token) in tag_name for tag_name in tag_names)
        for token in tokens
    )


def annotate_tag_match(queryset, tokens):
    """검색 토큰이 저장된 태그명에 맞는지를 `has_tag_match`로 표시한다."""
    if not tokens:
        return queryset.annotate(has_tag_match=Value(False, output_field=BooleanField()))

    tag_filter = Q()
    for token in tokens:
        tag_filter |= Q(tag__name__icontains=token)

    return queryset.annotate(
        has_tag_match=Exists(
            PlaceTag.objects.filter(place=OuterRef("pk")).filter(tag_filter)
        )
    )


def collect_scored_candidates(queryset, *, include_tokens, normalized_query,
                              matched_categories, attribute_query=False,
                              lat=None, lng=None, radius=0, db_distance=False):
    """
    후보의 관련도 점수와 거리를 계산해 정렬 가능한 목록으로 만든다.

    전체 모델 인스턴스를 만들지 않고 필요한 컬럼만 읽어 메모리와 시간을 줄인다.
    태그로 맞았는지 여부는 `Exists` 서브쿼리로 같은 쿼리 안에서 함께 읽는다.
    `db_distance` 가 참이면 거리는 PostGIS 가 이미 계산했으므로 그대로 쓴다.
    """
    fields = ["id", "name", "address", "detail_location", "category", "lat", "lng", "has_tag_match"]
    if db_distance:
        fields.append("db_distance")

    candidate_fields = annotate_tag_match(queryset, include_tokens).values_list(*fields)

    candidates = []

    for row in candidate_fields.iterator(chunk_size=2000):
        (place_id, name, address, detail_location, category,
         place_lat, place_lng, has_tag_match) = row[:8]
        distance = None

        if db_distance:
            distance = int(round(row[8]))
        elif lat is not None and lng is not None:
            distance = calculate_distance_m(lat, lng, place_lat, place_lng)

            if radius and distance > radius:
                continue

        candidates.append({
            "id": place_id,
            "name": name,
            "lat": place_lat,
            "lng": place_lng,
            "distance": distance,
            "score": calculate_relevance_score(
                name=name,
                address=address,
                detail_location=detail_location,
                category=category,
                include_tokens=include_tokens,
                normalized_query=normalized_query,
                matched_categories=matched_categories,
                has_tag_match=bool(has_tag_match),
                attribute_query=attribute_query,
            ),
        })

    return candidates


def sort_candidates(candidates, *, has_location):
    """관련도 높은 순, 같은 관련도면 가까운 순으로 정렬한다."""
    if has_location:
        return sorted(
            candidates,
            key=lambda candidate: (
                -candidate["score"],
                candidate["distance"] if candidate["distance"] is not None else math.inf,
                candidate["name"],
            ),
        )

    return sorted(
        candidates,
        key=lambda candidate: (-candidate["score"], candidate["name"]),
    )


def dedupe_candidates(candidates):
    """
    같은 이름이 같은 좌표에 여러 건 저장된 경우를 한 건으로 묶는다.

    공공데이터에는 `해운대 해수욕장` 무료와이파이처럼 같은 장소가 설비 단위로
    여러 row 저장된 경우가 있어, 검색 결과에서는 대표 한 건만 보여준다.
    좌표가 떨어져 있어 한 건으로 묶을 수 없는 같은 이름도 상위 몇 건만 남긴다.
    묶이거나 생략된 건수는 `duplicate_count`로 남긴다.
    """
    deduped = []
    index_by_key = {}
    first_index_by_name = {}
    count_by_name = {}

    for candidate in candidates:
        normalized_name = normalize_compact(candidate["name"])
        key = (
            normalized_name,
            round(candidate["lat"], DUPLICATE_COORD_PRECISION),
            round(candidate["lng"], DUPLICATE_COORD_PRECISION),
        )

        if key in index_by_key:
            deduped[index_by_key[key]]["duplicate_count"] += 1
            continue

        if count_by_name.get(normalized_name, 0) >= MAX_RESULTS_PER_NAME:
            # 같은 이름이 이미 충분히 있으면 대표 항목의 건수만 올립니다.
            deduped[first_index_by_name[normalized_name]]["duplicate_count"] += 1
            continue

        index_by_key[key] = len(deduped)
        first_index_by_name.setdefault(normalized_name, len(deduped))
        count_by_name[normalized_name] = count_by_name.get(normalized_name, 0) + 1
        deduped.append({**candidate, "duplicate_count": 1})

    return deduped


def drop_unmatched_tokens(tokens, queryset):
    """
    DB에 한 건도 맞지 않는 토큰을 빼고 남은 토큰을 돌려준다.

    `아이와 갈만한 공원`처럼 데이터에 없는 표현이 하나 섞이면 AND 조건 때문에
    결과가 전부 사라지므로, 결과가 없을 때만 이 완화 단계를 사용한다.
    """
    matched_tokens = []
    dropped_tokens = []

    for token in tokens:
        if queryset.filter(build_token_filter(token)).exists():
            matched_tokens.append(token)
        else:
            dropped_tokens.append(token)

    return matched_tokens, dropped_tokens


def relax_tokens_for_results(tokens, queryset):
    """Keep category/location constraints, then add only compatible preferences."""
    unique_tokens = list(dict.fromkeys(tokens))
    location_tokens = set()

    for token in unique_tokens:
        if not token.endswith(LOCATION_TOKEN_SUFFIXES):
            continue
        location_filter = (
            Q(name__icontains=token)
            | Q(address__icontains=token)
            | Q(detail_location__icontains=token)
        )
        if queryset.filter(location_filter).exists():
            location_tokens.add(token)

    def priority(token):
        if get_matching_categories(token):
            return 0
        if token in location_tokens:
            return 1
        if token not in SOFT_PREFERENCE_TOKENS:
            return 2
        return 3

    selected = set()
    current_queryset = queryset
    for token in sorted(unique_tokens, key=priority):
        candidate_queryset = current_queryset.filter(build_token_filter(token))
        if candidate_queryset.exists():
            selected.add(token)
            current_queryset = candidate_queryset

    relaxed_tokens = [token for token in unique_tokens if token in selected]
    dropped_tokens = [token for token in unique_tokens if token not in selected]
    return relaxed_tokens, dropped_tokens


def build_radius_attempts(*, lat, lng, radius, has_keyword):
    """
    시도할 반경 목록을 만든다.

    - 사용자가 반경을 지정하면 그 값만 사용한다.
    - 지정하지 않으면 가까운 곳부터 넓혀가며 필요한 만큼만 조회한다.
    - 검색어가 있으면 마지막에 반경 제한 없이 한 번 더 조회한다.
      (`부산에서 해운대 해수욕장` 처럼 멀리 있는 장소를 이름으로 찾는 경우)
    """
    if lat is None or lng is None:
        return [None]

    if radius:
        return [radius]

    attempts = list(RADIUS_EXPANSION_STEPS_M)

    if has_keyword:
        attempts.append(None)

    return attempts


def run_search_pass(*, source_queryset, include_tokens, exclude_tokens, matched_categories,
                    lat, lng, radius, limit):
    """주어진 토큰 조합으로 한 번 검색하고 정렬/중복 제거까지 마친 결과를 돌려준다."""
    base_queryset = apply_keyword_filter(source_queryset, include_tokens, exclude_tokens)

    # 이름 관련도는 업종을 가리키는 토큰을 뺀 나머지로만 판단합니다.
    scoring_tokens = split_discriminating_tokens(include_tokens)
    normalized_query = normalize_compact(" ".join(scoring_tokens))
    attribute_query = is_attribute_query(scoring_tokens)

    if lat is None or lng is None:
        # 좌표가 없으면 거리 정렬을 할 수 없으므로 관련도 순으로만 정렬합니다.
        candidates = collect_scored_candidates(
            base_queryset.order_by("-data_quality_score", "-updated_at", "-id"),
            include_tokens=scoring_tokens,
            normalized_query=normalized_query,
            matched_categories=matched_categories,
            attribute_query=attribute_query,
        )

        return dedupe_candidates(sort_candidates(candidates, has_location=False))

    # 좌표가 없는 장소는 거리 계산이 불가능하므로 제외합니다. (PostGIS 경로에서도 동일)

    deduped = []

    for attempt_radius in build_radius_attempts(
        lat=lat,
        lng=lng,
        radius=radius,
        has_keyword=bool(include_tokens or exclude_tokens),
    ):
        queryset, db_distance = apply_radius_filter(base_queryset, lat, lng, attempt_radius)

        candidates = collect_scored_candidates(
            queryset,
            include_tokens=scoring_tokens,
            normalized_query=normalized_query,
            matched_categories=matched_categories,
            attribute_query=attribute_query,
            lat=lat,
            lng=lng,
            radius=attempt_radius or 0,
            db_distance=db_distance,
        )
        deduped = dedupe_candidates(sort_candidates(candidates, has_location=True))

        if len(deduped) >= limit:
            break

    return deduped


def search_saved_places(*, keyword="", lat=None, lng=None, radius=0, limit=30, queryset=None):
    """
    DB에 저장된 장소를 검색해 (후보 목록, 전체 건수, 검색 메타) 를 돌려준다.

    후보 목록은 관련도/거리 순으로 정렬되고 중복이 제거된 dict 목록이며,
    각 항목은 `id`, `distance`, `score`, `duplicate_count`를 가진다.
    `queryset`으로 카테고리/출처 같은 추가 조건을 미리 걸어둔 쿼리셋을 넘길 수 있다.
    """
    include_tokens, exclude_tokens = tokenize_query(keyword)
    matched_categories = get_matching_categories(keyword)
    source_queryset = Place.objects.all() if queryset is None else queryset

    deduped = run_search_pass(
        source_queryset=source_queryset,
        include_tokens=include_tokens,
        exclude_tokens=exclude_tokens,
        matched_categories=matched_categories,
        lat=lat,
        lng=lng,
        radius=radius,
        limit=limit,
    )

    dropped_tokens = []

    # 결과가 없고 토큰이 여러 개면, 데이터에 없는 표현만 빼고 한 번 더 시도합니다.
    if not deduped and len(include_tokens) > 1:
        relaxation_queryset = source_queryset
        if lat is not None and lng is not None and radius:
            relaxation_queryset, _ = apply_radius_filter(
                source_queryset,
                lat,
                lng,
                radius,
            )
        relaxed_tokens, dropped_tokens = relax_tokens_for_results(
            include_tokens,
            relaxation_queryset,
        )

        if relaxed_tokens and dropped_tokens:
            deduped = run_search_pass(
                source_queryset=source_queryset,
                include_tokens=relaxed_tokens,
                exclude_tokens=exclude_tokens,
                matched_categories=matched_categories,
                lat=lat,
                lng=lng,
                radius=radius,
                limit=limit,
            )
        else:
            dropped_tokens = []

    return deduped[:limit], len(deduped), {
        "include_tokens": include_tokens,
        "exclude_tokens": exclude_tokens,
        "dropped_tokens": dropped_tokens,
        "matched_categories": matched_categories,
    }


def load_places_by_ids(place_ids):
    """정렬 순서를 유지한 채 `Place` 인스턴스를 태그까지 함께 읽어온다."""
    places_by_id = {
        place.id: place
        for place in (
            Place.objects
            .filter(id__in=place_ids)
            .prefetch_related("place_tags__tag")
        )
    }

    return [places_by_id[place_id] for place_id in place_ids if place_id in places_by_id]
