# clean_cafe_tag_seed.py
# 실행 위치:
#   cd Test/apiTest/tag/cafeTag
#   python clean_cafe_tag_seed.py

import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_RESULTS_PATH = BASE_DIR / "results" / "cafe_all_results.json"
INPUT_SKIPPED_PATH = BASE_DIR / "results" / "cafe_all_skipped_results.json"

OUTPUT_DIR = BASE_DIR / "outputs"

# ExternalPlaceTag import용 seed
OUTPUT_EXTERNAL_TAG_SEED_PATH = OUTPUT_DIR / "cafe_external_place_tags_seed.json"

# 확인용 요약 파일
OUTPUT_SUMMARY_PATH = OUTPUT_DIR / "cafe_external_place_tags_summary.json"


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

SUB_TAGS = {
    "디저트",
    "분위기좋음",
    "데이트좋음",
    "커피맛집",
    "핫플",
    "사진맛집",
}

WARNING_TAGS = {
    "웨이팅주의",
}

KEEP_UNKNOWN_TAGS = True


def read_json(path):
    if not path.exists():
        print(f"파일 없음: {path}")
        return []

    with path.open("r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print(f"빈 파일: {path}")
        return []

    return json.loads(content)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (ValueError, TypeError):
        return default


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def get_place_external_id(place):
    """
    카카오 장소 ID를 ExternalPlaceTag.external_id로 사용합니다.
    수집 단계 파일마다 키 이름이 다를 수 있어서 후보를 여러 개 봅니다.
    """
    candidates = [
        place.get("external_id"),
        place.get("place_id"),
        place.get("kakao_place_id"),
        place.get("id"),
    ]

    for value in candidates:
        text = safe_str(value)
        if text:
            return text

    return ""


def get_place_name(place):
    candidates = [
        place.get("name"),
        place.get("place_name"),
    ]

    for value in candidates:
        text = safe_str(value)
        if text:
            return text

    return ""


def get_place_address(place):
    candidates = [
        place.get("address"),
        place.get("road_address_name"),
        place.get("address_name"),
    ]

    for value in candidates:
        text = safe_str(value)
        if text:
            return text

    return ""


def get_place_lat(place):
    """
    카카오 API는 y가 위도, x가 경도입니다.
    기존 정제 파일은 lat/lng일 수도 있습니다.
    """
    return safe_float(place.get("lat"), safe_float(place.get("y")))


def get_place_lng(place):
    return safe_float(place.get("lng"), safe_float(place.get("x")))


def get_tag_group(tag_name):
    if tag_name in CORE_TAGS:
        return "core"

    if tag_name in SUB_TAGS:
        return "sub"

    if tag_name in WARNING_TAGS:
        return "warning"

    return "unknown"


def get_tag_type(tag_name):
    if tag_name in WARNING_TAGS:
        return "warning"

    return "recommendation"


def get_tag_status(tag_name):
    if tag_name in WARNING_TAGS:
        return "needs_verification"

    return "candidate"


def should_keep_tag(tag_name):
    if not tag_name:
        return False

    if tag_name in CORE_TAGS:
        return True

    if tag_name in SUB_TAGS:
        return True

    if tag_name in WARNING_TAGS:
        return True

    return KEEP_UNKNOWN_TAGS


def normalize_tag(raw_tag):
    """
    raw_tag가 문자열일 수도 있고, dict일 수도 있어서 둘 다 처리합니다.
    """
    if isinstance(raw_tag, str):
        name = safe_str(raw_tag)

        return {
            "name": name,
            "confidence": 50,
            "evidence": "",
            "evidence_count": 0,
            "required_count": 0,
            "raw": raw_tag,
        }

    if isinstance(raw_tag, dict):
        name = safe_str(raw_tag.get("name"))

        return {
            "name": name,
            "confidence": safe_int(raw_tag.get("confidence"), 50),
            "evidence": safe_str(raw_tag.get("evidence")),
            "evidence_count": safe_int(raw_tag.get("evidence_count"), 0),
            "required_count": safe_int(raw_tag.get("required_count"), 0),
            "raw": raw_tag,
        }

    return {
        "name": "",
        "confidence": 50,
        "evidence": "",
        "evidence_count": 0,
        "required_count": 0,
        "raw": raw_tag,
    }


def build_evidence(place, tag):
    evidence = tag.get("evidence", "")

    if evidence:
        return evidence

    source_query = safe_str(place.get("source_query"))
    blog_count = safe_int(place.get("blog_evidence_count"), 0)
    evidence_count = safe_int(tag.get("evidence_count"), 0)

    parts = []

    if source_query:
        parts.append(f"검색어: {source_query}")

    if blog_count:
        parts.append(f"블로그 근거 수: {blog_count}")

    if evidence_count:
        parts.append(f"태그 근거 수: {evidence_count}")

    if not parts:
        return "네이버 블로그 검색 결과 기반 후보 태그"

    return " / ".join(parts)


def build_raw(place, tag):
    """
    ExternalPlaceTag.raw에 넣을 보조 정보입니다.
    실제 추천 점수 계산이나 검수 화면에서 참고할 수 있습니다.
    """
    return {
        "original_category": place.get("category", ""),
        "phone": place.get("phone", ""),
        "place_url": place.get("place_url", ""),
        "area_key": place.get("area_key", ""),
        "area_name": place.get("area_name", ""),
        "sub_area_key": place.get("sub_area_key", ""),
        "sub_area_name": place.get("sub_area_name", ""),
        "source_query": place.get("source_query", ""),
        "blog_evidence_count": place.get("blog_evidence_count", 0),
        "tag_group": get_tag_group(tag["name"]),
        "tag_type": get_tag_type(tag["name"]),
        "tag_raw": tag.get("raw", {}),
        "data_note": (
            "카카오 로컬 API 장소 후보와 네이버 블로그 검색 결과의 제목/요약 문구를 "
            "기반으로 생성한 카페 추천 태그 후보입니다. 실제 시설 여부를 확정한 "
            "검증 데이터가 아니므로 candidate 상태로 사용합니다."
        ),
    }


def clean_place_to_external_tag_rows(place):
    external_id = get_place_external_id(place)
    place_name = get_place_name(place)
    address = get_place_address(place)
    lat = get_place_lat(place)
    lng = get_place_lng(place)

    if not external_id:
        return [], "external_id 없음"

    if not place_name:
        return [], "place_name 없음"

    if lat is None or lng is None:
        return [], "좌표 없음"

    raw_tags = place.get("tags", [])

    if not raw_tags:
        return [], "tags 없음"

    rows = []
    seen_tag_names = set()

    for raw_tag in raw_tags:
        tag = normalize_tag(raw_tag)
        tag_name = tag["name"]

        if not should_keep_tag(tag_name):
            continue

        if tag_name in seen_tag_names:
            continue

        seen_tag_names.add(tag_name)

        row = {
            "external_source": "kakao_local",
            "external_id": external_id,
            "place_name": place_name,
            "category": "cafe",
            "address": address,
            "lat": lat,
            "lng": lng,

            # import_external_place_tags.py에서 Tag get_or_create에 사용
            "tag_name": tag_name,
            "tag_type": get_tag_type(tag_name),

            # ExternalPlaceTag 필드
            "tag_source": "blog_search",
            "status": get_tag_status(tag_name),
            "confidence": tag["confidence"],
            "evidence": build_evidence(place, tag),
            "raw": build_raw(place, tag),
        }

        rows.append(row)

    if not rows:
        return [], "사용 가능한 태그 없음"

    return rows, None


def build_summary(original_places, skipped_places, external_tag_rows, exclude_reasons):
    place_ids = set()
    place_counter = Counter()
    tag_counter = Counter()
    tag_type_counter = Counter()
    tag_status_counter = Counter()
    area_counter = Counter()

    for row in external_tag_rows:
        place_key = (row["external_source"], row["external_id"])
        place_ids.add(place_key)

        place_counter[row["place_name"]] += 1
        tag_counter[row["tag_name"]] += 1
        tag_type_counter[row["tag_type"]] += 1
        tag_status_counter[row["status"]] += 1

        area_name = row["raw"].get("area_name") or "미상"
        area_counter[area_name] += 1

    skipped_reason_counter = Counter()

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
            "external_place_count": len(place_ids),
            "external_tag_row_count": len(external_tag_rows),
            "external_tag_seed_path": str(OUTPUT_EXTERNAL_TAG_SEED_PATH),
            "summary_path": str(OUTPUT_SUMMARY_PATH),
        },
        "excluded_during_cleaning": {
            "count": sum(exclude_reasons.values()),
            "reasons": dict(exclude_reasons.most_common()),
        },
        "tag_counts": dict(tag_counter.most_common()),
        "tag_type_counts": dict(tag_type_counter.most_common()),
        "tag_status_counts": dict(tag_status_counter.most_common()),
        "area_counts": dict(area_counter.most_common()),
        "place_tag_row_counts_top_20": dict(place_counter.most_common(20)),
        "skipped_reason_counts_from_original_skipped_file": dict(
            skipped_reason_counter.most_common()
        ),
        "tag_policy": {
            "core_tags": sorted(CORE_TAGS),
            "sub_tags": sorted(SUB_TAGS),
            "warning_tags": sorted(WARNING_TAGS),
            "keep_unknown_tags": KEEP_UNKNOWN_TAGS,
        },
        "data_note": (
            "이 파일은 카페 장소를 Place DB에 저장하기 위한 데이터가 아닙니다. "
            "카카오 Local API 검색 결과의 place id와 매칭하기 위한 "
            "ExternalPlaceTag seed 데이터입니다."
        ),
    }


def main():
    original_places = read_json(INPUT_RESULTS_PATH)
    skipped_places = read_json(INPUT_SKIPPED_PATH)

    external_tag_rows = []
    exclude_reasons = Counter()
    seen_row_keys = set()

    for place in original_places:
        rows, reason = clean_place_to_external_tag_rows(place)

        if reason:
            exclude_reasons[reason] += 1
            continue

        for row in rows:
            key = (
                row["external_source"],
                row["external_id"],
                row["tag_name"],
                row["tag_source"],
            )

            if key in seen_row_keys:
                exclude_reasons["external_id_tag 중복"] += 1
                continue

            seen_row_keys.add(key)
            external_tag_rows.append(row)

    external_tag_rows.sort(
        key=lambda row: (
            row["place_name"],
            row["external_id"],
            row["tag_name"],
        )
    )

    summary = build_summary(
        original_places=original_places,
        skipped_places=skipped_places,
        external_tag_rows=external_tag_rows,
        exclude_reasons=exclude_reasons,
    )

    write_json(OUTPUT_EXTERNAL_TAG_SEED_PATH, external_tag_rows)
    write_json(OUTPUT_SUMMARY_PATH, summary)

    print("==============================")
    print("카페 ExternalPlaceTag seed 생성 완료")
    print("==============================")
    print(f"원본 results 장소 수: {len(original_places)}")
    print(f"ExternalPlaceTag row 수: {len(external_tag_rows)}")
    print(f"정제 중 제외 수: {sum(exclude_reasons.values())}")
    print()
    print(f"seed 파일: {OUTPUT_EXTERNAL_TAG_SEED_PATH}")
    print(f"요약 파일: {OUTPUT_SUMMARY_PATH}")

    if exclude_reasons:
        print()
        print("정제 중 제외 사유:")
        for reason, count in exclude_reasons.most_common():
            print(f"- {reason}: {count}")


if __name__ == "__main__":
    main()