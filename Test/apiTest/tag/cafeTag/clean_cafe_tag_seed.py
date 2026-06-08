# clean_cafe_tag_seed.py
# 실행 위치:
#   cd Test/apiTest/tag/cafeTag
#   python clean_cafe_tag_seed.py

import json
import math
from collections import Counter, defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_RESULTS_PATH = BASE_DIR / "results" / "cafe_all_results.json"
INPUT_SKIPPED_PATH = BASE_DIR / "results" / "cafe_all_skipped_results.json"

OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_SERVICE_SEED_PATH = OUTPUT_DIR / "cafe_tag_service_seed.json"
OUTPUT_DJANGO_FIXTURE_PATH = OUTPUT_DIR / "cafe_tag_django_fixture.json"
OUTPUT_SUMMARY_PATH = OUTPUT_DIR / "cafe_tag_seed_summary.json"


# Django app/model 이름
PLACE_MODEL = "recommendations.place"
TAG_MODEL = "recommendations.tag"
PLACE_TAG_MODEL = "recommendations.placetag"


# 실제 추천에서 핵심으로 쓸 태그
CORE_TAGS = {
    "조용한",
    "노트북작업",
    "콘센트있음",
    "와이파이",
    "혼자이용좋음",
    "전망좋음",
    "야경",
    "루프탑",
    "야외자리",
    "대형카페",
    "주차가능",
    "드라이브목적지",
}

# 추천 보조 태그
SUB_TAGS = {
    "디저트",
    "분위기좋음",
    "데이트좋음",
    "커피맛집",
    "핫플",
    "사진맛집",
}

# 추천 태그라기보다는 주의 정보로 볼 태그
WARNING_TAGS = {
    "웨이팅주의",
}

# 정의되지 않은 태그도 버리지 않고 보조 태그로 살릴지 여부
KEEP_UNKNOWN_TAGS = True

# display_tags를 너무 길게 보이고 싶지 않을 때 숫자로 제한
# None이면 전부 유지
DISPLAY_TAG_LIMIT = None


def read_json(path):
    if not path.exists():
        print(f"파일 없음: {path}")
        return []

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clamp(value, min_value=0, max_value=100):
    return max(min_value, min(max_value, value))


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def get_tag_group(tag_name):
    if tag_name in CORE_TAGS:
        return "core"
    if tag_name in WARNING_TAGS:
        return "warning"
    if tag_name in SUB_TAGS:
        return "sub"
    return "unknown"


def get_django_tag_type(tag_name):
    if tag_name in WARNING_TAGS:
        return "warning"
    return "recommendation"


def should_keep_tag(tag):
    name = tag.get("name")

    if not name:
        return False

    if name in CORE_TAGS:
        return True

    if name in SUB_TAGS:
        return True

    if name in WARNING_TAGS:
        return True

    return KEEP_UNKNOWN_TAGS


def calculate_tag_strength(tag):
    """
    태그 하나의 근거 강도 계산.
    원본 confidence만 쓰지 않고 evidence_count / required_count도 반영합니다.
    """
    confidence = safe_int(tag.get("confidence"), 50)
    evidence_count = safe_int(tag.get("evidence_count"), 0)
    required_count = safe_int(tag.get("required_count"), 1)

    if required_count <= 0:
        required_count = 1

    # required_count보다 얼마나 많이 근거가 나왔는지
    # 3배 이상이면 evidence 쪽은 만점 처리
    evidence_ratio = evidence_count / required_count
    evidence_score = clamp((min(evidence_ratio, 3) / 3) * 100)

    # confidence 비중을 더 크게 둠
    strength = (confidence * 0.7) + (evidence_score * 0.3)

    return round(clamp(strength), 2)


def clean_tag(tag):
    name = tag.get("name")
    group = get_tag_group(name)

    cleaned = {
        "name": name,
        "tag_group": group,
        "confidence": safe_int(tag.get("confidence"), 50),
        "status": tag.get("status", "suggested"),
        "status_label": tag.get("status_label", "추천 태그 후보"),
        "evidence_count": safe_int(tag.get("evidence_count"), 0),
        "required_count": safe_int(tag.get("required_count"), 0),
        "evidence": tag.get("evidence", ""),
        "source": tag.get("source", "naver_blog_title_description"),
        "is_ai_generated": bool(tag.get("is_ai_generated", False)),
        "is_verified": bool(tag.get("is_verified", False)),
    }

    cleaned["tag_strength"] = calculate_tag_strength(cleaned)

    return cleaned


def tag_sort_key(tag):
    """
    화면/추천에서 보기 좋은 순서:
    core → sub → warning → unknown
    그 안에서는 tag_strength, evidence_count, confidence 높은 순
    """
    group_order = {
        "core": 0,
        "sub": 1,
        "warning": 2,
        "unknown": 3,
    }

    return (
        group_order.get(tag["tag_group"], 9),
        -tag.get("tag_strength", 0),
        -tag.get("evidence_count", 0),
        -tag.get("confidence", 0),
        tag.get("name", ""),
    )


def calculate_place_scores(place, tag_details):
    """
    장소 단위 점수.
    지금은 머신러닝이 아니라 규칙 기반 점수입니다.
    """
    blog_evidence_count = safe_int(place.get("blog_evidence_count"), 0)

    if tag_details:
        avg_tag_strength = sum(tag["tag_strength"] for tag in tag_details) / len(tag_details)
        avg_confidence = sum(tag["confidence"] for tag in tag_details) / len(tag_details)
    else:
        avg_tag_strength = 0
        avg_confidence = 0

    core_count = sum(1 for tag in tag_details if tag["tag_group"] == "core")
    sub_count = sum(1 for tag in tag_details if tag["tag_group"] == "sub")
    warning_count = sum(1 for tag in tag_details if tag["tag_group"] == "warning")

    # 블로그 근거 수는 50건 이상이면 충분하다고 보고 만점 처리
    blog_score = clamp((min(blog_evidence_count, 50) / 50) * 100)

    # 핵심 태그가 많을수록 추천 준비도가 올라감
    core_bonus = min(core_count * 8, 32)
    sub_bonus = min(sub_count * 3, 12)
    warning_penalty = min(warning_count * 4, 12)

    tag_score = round(clamp(avg_tag_strength), 2)

    data_confidence_score = round(
        clamp((blog_score * 0.55) + (avg_confidence * 0.45)),
        2,
    )

    recommendation_ready_score = round(
        clamp(
            (tag_score * 0.45)
            + (data_confidence_score * 0.35)
            + core_bonus
            + sub_bonus
            - warning_penalty
        ),
        2,
    )

    return {
        "tag_score": tag_score,
        "data_confidence_score": data_confidence_score,
        "recommendation_ready_score": recommendation_ready_score,
        "blog_evidence_score": round(blog_score, 2),
        "core_tag_count": core_count,
        "sub_tag_count": sub_count,
        "warning_tag_count": warning_count,
    }


def clean_place(place):
    external_id = str(place.get("external_id", "")).strip()
    name = str(place.get("name", "")).strip()
    lat = safe_float(place.get("lat"))
    lng = safe_float(place.get("lng"))

    if not external_id or not name:
        return None, "external_id 또는 name 없음"

    if lat is None or lng is None:
        return None, "좌표 없음"

    raw_tags = place.get("tags", [])
    tag_details = []

    for raw_tag in raw_tags:
        if should_keep_tag(raw_tag):
            tag_details.append(clean_tag(raw_tag))

    if not tag_details:
        return None, "사용 가능한 태그 없음"

    tag_details.sort(key=tag_sort_key)

    suggested_tags = [
        tag["name"]
        for tag in tag_details
        if tag["tag_group"] != "warning"
    ]

    warning_tags = [
        tag["name"]
        for tag in tag_details
        if tag["tag_group"] == "warning"
    ]

    display_tags = [tag["name"] for tag in tag_details]

    if DISPLAY_TAG_LIMIT is not None:
        display_tags = display_tags[:DISPLAY_TAG_LIMIT]

    scores = calculate_place_scores(place, tag_details)

    cleaned = {
        "source": place.get("source", "kakao_local"),
        "external_id": external_id,
        "name": name,
        "category": "cafe",
        "original_category": place.get("category", ""),
        "address": place.get("address", ""),
        "lat": lat,
        "lng": lng,
        "phone": place.get("phone", ""),
        "place_url": place.get("place_url", ""),
        "area_key": place.get("area_key", ""),
        "area_name": place.get("area_name", ""),
        "source_query": place.get("source_query", ""),
        "sub_area_key": place.get("sub_area_key", ""),
        "sub_area_name": place.get("sub_area_name", ""),
        "blog_evidence_count": safe_int(place.get("blog_evidence_count"), 0),
        "suggested_tags": suggested_tags,
        "display_tags": display_tags,
        "warning_tags": warning_tags,
        "tag_details": tag_details,
        "scores": scores,
        "tag_source": "naver_blog_title_description",
        "data_status": "candidate",
        "is_verified": False,
    }

    return cleaned, None


def data_quality_status_from_score(score):
    if score >= 85:
        return "candidate"
    if score >= 70:
        return "candidate"
    return "needs_review"


def build_service_seed(cleaned_places):
    return cleaned_places


def build_django_fixture(cleaned_places):
    """
    현재 백엔드 모델 기준:
    - recommendations.Place
    - recommendations.Tag
    - recommendations.PlaceTag
    """
    fixture = []

    # 태그 목록 만들기
    tag_names = set()

    for place in cleaned_places:
        for tag in place["tag_details"]:
            tag_names.add(tag["name"])

    sorted_tag_names = sorted(
        tag_names,
        key=lambda name: (
            {"core": 0, "sub": 1, "warning": 2, "unknown": 3}.get(get_tag_group(name), 9),
            name,
        ),
    )

    tag_pk_map = {}
    place_pk_map = {}

    # Tag fixture
    for idx, tag_name in enumerate(sorted_tag_names, start=1):
        tag_pk_map[tag_name] = idx

        fixture.append(
            {
                "model": TAG_MODEL,
                "pk": idx,
                "fields": {
                    "name": tag_name,
                    "tag_type": get_django_tag_type(tag_name),
                    "description": build_tag_description(tag_name),
                },
            }
        )

    # Place fixture
    for idx, place in enumerate(cleaned_places, start=1):
        place_pk_map[place["external_id"]] = idx

        scores = place["scores"]
        data_quality_score = round(scores["data_confidence_score"])

        fixture.append(
            {
                "model": PLACE_MODEL,
                "pk": idx,
                "fields": {
                    "name": place["name"],
                    "category": place["category"],
                    "address": place["address"],
                    "lat": place["lat"],
                    "lng": place["lng"],
                    "source": place["source"],
                    "external_id": place["external_id"],
                    "source_name": "kakao_local + naver_blog_search",
                    "source_updated_at": None,
                    "detail_location": place.get("area_name", ""),
                    "data_quality_status": data_quality_status_from_score(
                        scores["data_confidence_score"]
                    ),
                    "data_quality_score": data_quality_score,
                    "raw": {
                        "original_category": place["original_category"],
                        "phone": place["phone"],
                        "place_url": place["place_url"],
                        "area_key": place["area_key"],
                        "area_name": place["area_name"],
                        "source_query": place["source_query"],
                        "sub_area_key": place["sub_area_key"],
                        "sub_area_name": place["sub_area_name"],
                        "blog_evidence_count": place["blog_evidence_count"],
                        "suggested_tags": place["suggested_tags"],
                        "display_tags": place["display_tags"],
                        "warning_tags": place["warning_tags"],
                        "tag_details": place["tag_details"],
                        "scores": place["scores"],
                        "data_status": place["data_status"],
                        "is_verified": place["is_verified"],
                    },
                },
            }
        )

    # PlaceTag fixture
    place_tag_pk = 1

    for place in cleaned_places:
        place_pk = place_pk_map[place["external_id"]]

        for tag in place["tag_details"]:
            tag_pk = tag_pk_map[tag["name"]]

            fixture.append(
                {
                    "model": PLACE_TAG_MODEL,
                    "pk": place_tag_pk,
                    "fields": {
                        "place": place_pk,
                        "tag": tag_pk,
                        "source": "external_data",
                        "status": "candidate",
                        "confidence": tag["confidence"],
                        "evidence": tag["evidence"],
                        "is_verified": False,
                        "verified_at": None,
                    },
                }
            )

            place_tag_pk += 1

    return fixture


def build_tag_description(tag_name):
    group = get_tag_group(tag_name)

    if group == "core":
        return "카페 추천에 직접 활용하는 핵심 태그 후보입니다."
    if group == "sub":
        return "카페의 분위기나 특징을 보조적으로 설명하는 태그 후보입니다."
    if group == "warning":
        return "추천 시 주의 정보로 함께 표시할 태그 후보입니다."

    return "외부 검색 결과에서 추출된 기타 태그 후보입니다."


def build_summary(original_places, cleaned_places, skipped_places, exclude_reasons):
    area_counter = Counter()
    sub_area_counter = Counter()
    tag_counter = Counter()
    tag_group_counter = Counter()
    source_query_counter = Counter()
    skipped_reason_counter = Counter()

    score_buckets = {
        "recommendation_ready_90_100": 0,
        "recommendation_ready_80_89": 0,
        "recommendation_ready_70_79": 0,
        "recommendation_ready_under_70": 0,
    }

    for place in cleaned_places:
        area_counter[place["area_name"] or place["area_key"] or "미상"] += 1

        if place.get("sub_area_name"):
            sub_area_counter[place["sub_area_name"]] += 1

        if place.get("source_query"):
            source_query_counter[place["source_query"]] += 1

        for tag in place["tag_details"]:
            tag_counter[tag["name"]] += 1
            tag_group_counter[tag["tag_group"]] += 1

        ready_score = place["scores"]["recommendation_ready_score"]

        if ready_score >= 90:
            score_buckets["recommendation_ready_90_100"] += 1
        elif ready_score >= 80:
            score_buckets["recommendation_ready_80_89"] += 1
        elif ready_score >= 70:
            score_buckets["recommendation_ready_70_79"] += 1
        else:
            score_buckets["recommendation_ready_under_70"] += 1

    for skipped in skipped_places:
        reason = skipped.get("skip_reason", "미상")
        skipped_reason_counter[reason] += 1

    return {
        "input": {
            "results_path": str(INPUT_RESULTS_PATH),
            "skipped_path": str(INPUT_SKIPPED_PATH),
            "original_place_count": len(original_places),
            "original_skipped_count": len(skipped_places),
        },
        "output": {
            "cleaned_place_count": len(cleaned_places),
            "service_seed_path": str(OUTPUT_SERVICE_SEED_PATH),
            "django_fixture_path": str(OUTPUT_DJANGO_FIXTURE_PATH),
            "summary_path": str(OUTPUT_SUMMARY_PATH),
        },
        "excluded_during_cleaning": {
            "count": sum(exclude_reasons.values()),
            "reasons": dict(sorted(exclude_reasons.items())),
        },
        "area_counts": dict(area_counter.most_common()),
        "sub_area_counts": dict(sub_area_counter.most_common()),
        "source_query_counts": dict(source_query_counter.most_common()),
        "tag_counts": dict(tag_counter.most_common()),
        "tag_group_counts": dict(tag_group_counter.most_common()),
        "score_buckets": score_buckets,
        "skipped_reason_counts_from_original_skipped_file": dict(
            skipped_reason_counter.most_common()
        ),
        "tag_policy": {
            "core_tags": sorted(CORE_TAGS),
            "sub_tags": sorted(SUB_TAGS),
            "warning_tags": sorted(WARNING_TAGS),
            "keep_unknown_tags": KEEP_UNKNOWN_TAGS,
            "display_tag_limit": DISPLAY_TAG_LIMIT,
        },
        "data_note": (
            "이 데이터는 카카오 로컬 API 장소 후보와 네이버 블로그 검색 결과의 "
            "제목/요약 문구를 기반으로 생성한 카페 추천 태그 후보 데이터입니다. "
            "시설 여부를 확정한 검증 데이터가 아니라 candidate 상태로 사용합니다."
        ),
    }


def main():
    original_places = read_json(INPUT_RESULTS_PATH)
    skipped_places = read_json(INPUT_SKIPPED_PATH)

    cleaned_places = []
    seen_external_ids = set()
    exclude_reasons = Counter()

    for place in original_places:
        external_id = str(place.get("external_id", "")).strip()

        if external_id in seen_external_ids:
            exclude_reasons["external_id 중복"] += 1
            continue

        cleaned, reason = clean_place(place)

        if cleaned is None:
            exclude_reasons[reason] += 1
            continue

        seen_external_ids.add(external_id)
        cleaned_places.append(cleaned)

    # 정렬: 지역 → sub_area → 이름 → external_id
    cleaned_places.sort(
        key=lambda place: (
            place.get("area_key", ""),
            place.get("sub_area_key", ""),
            place.get("name", ""),
            place.get("external_id", ""),
        )
    )

    service_seed = build_service_seed(cleaned_places)
    django_fixture = build_django_fixture(cleaned_places)
    summary = build_summary(
        original_places=original_places,
        cleaned_places=cleaned_places,
        skipped_places=skipped_places,
        exclude_reasons=exclude_reasons,
    )

    write_json(OUTPUT_SERVICE_SEED_PATH, service_seed)
    write_json(OUTPUT_DJANGO_FIXTURE_PATH, django_fixture)
    write_json(OUTPUT_SUMMARY_PATH, summary)

    print("==============================")
    print("카페 태그 정제 완료")
    print("==============================")
    print(f"원본 results 장소 수: {len(original_places)}")
    print(f"정제 후 서비스 장소 수: {len(cleaned_places)}")
    print(f"정제 중 제외 수: {sum(exclude_reasons.values())}")
    print(f"Django fixture 객체 수: {len(django_fixture)}")
    print()
    print(f"서비스 seed: {OUTPUT_SERVICE_SEED_PATH}")
    print(f"Django fixture: {OUTPUT_DJANGO_FIXTURE_PATH}")
    print(f"요약 파일: {OUTPUT_SUMMARY_PATH}")

    if exclude_reasons:
        print()
        print("정제 중 제외 사유:")
        for reason, count in exclude_reasons.most_common():
            print(f"- {reason}: {count}")


if __name__ == "__main__":
    main()