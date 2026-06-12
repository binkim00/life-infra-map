import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "shelter_places.json"
SKIPPED_INPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "skipped" / "shelter_skipped.json"

OUTPUT_PLACE_TAG_SEED_PATH = SCRIPT_DIR / "shelter_place_tag_seed.json"
OUTPUT_SUMMARY_PATH = SCRIPT_DIR / "shelter_place_tag_seed_summary.json"


BASIC_TAGS = {
    "쉼터",
    "생활쉼터",
    "생활편의",
}


NOISY_TAGS = {
    "운영시간정보있음",
    "관리기관정보있음",
    "연락처있음",
    "수용인원정보있음",
    "면적정보있음",
}


def load_json(path, default):
    if not path.exists():
        print(f"파일 없음: {path}")
        return default

    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print(f"빈 파일: {path}")
        return default

    return json.loads(content)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def normalize_tag_name(tag_name):
    tag_name = safe_str(tag_name)

    tag_map = {
        "무더위쉼터": "무더위쉼터",
        "한파쉼터": "한파쉼터",
        "한파쉼터후보": "한파쉼터후보",

        "실내쉼터": "실내쉼터",
        "야외쉼터": "야외쉼터",
        "공공시설쉼터": "공공시설쉼터",
        "복지시설쉼터": "복지시설쉼터",

        "운영중후보": "운영중후보",
        "24시간운영후보": "24시간운영후보",
        "야간운영후보": "야간운영후보",
        "숙박가능후보": "숙박가능후보",

        "냉방시설있음": "냉방시설있음",
        "선풍기있음": "선풍기있음",
        "난방시설있음": "난방시설있음",
        "수용인원많음": "수용인원많음",
        "규모큰쉼터후보": "규모큰쉼터후보",

        "운영여부확인필요": "운영여부확인필요",
        "운영시간확인필요": "운영시간확인필요",
        "관리기관확인필요": "관리기관확인필요",
        "연락처확인필요": "연락처확인필요",
        "주소확인필요": "주소확인필요",
        "기준일확인필요": "기준일확인필요",
    }

    return tag_map.get(tag_name, tag_name)


def should_remove_tag(tag_name):
    tag_name = normalize_tag_name(tag_name)
    return tag_name in BASIC_TAGS or tag_name in NOISY_TAGS


def get_remove_reason(tag_name):
    tag_name = normalize_tag_name(tag_name)

    if tag_name in BASIC_TAGS:
        return "basic_category_tag"

    if tag_name in NOISY_TAGS:
        return "noisy_information_existence_tag"

    return ""


def get_tag_type(tag_name, group_name):
    tag_name = normalize_tag_name(tag_name)

    type_tags = {
        "무더위쉼터",
        "한파쉼터",
        "실내쉼터",
        "야외쉼터",
        "공공시설쉼터",
        "복지시설쉼터",
    }

    if group_name == "warning_tags":
        return "warning"

    if tag_name in type_tags:
        return "category"

    return "recommendation"


def make_evidence(tag_name, item):
    raw = item.get("raw", {})

    facility_type = (
        safe_str(raw.get("시설유형"))
        or safe_str(raw.get("쉼터유형"))
        or safe_str(raw.get("시설구분"))
        or safe_str(raw.get("구분"))
    )

    name = safe_str(item.get("name"))
    manager = safe_str(item.get("raw", {}).get("관리기관명"))
    source_updated_at = safe_str(item.get("source_updated_at"))

    opening_hours = raw.get("opening_hours", {})

    parts = ["쉼터 원본 필드 기반 태그"]

    if name:
        parts.append(f"쉼터명: {name}")

    if facility_type:
        parts.append(f"시설유형: {facility_type}")

    if opening_hours:
        parts.append(f"운영시간: {opening_hours}")

    if manager:
        parts.append(f"관리기관: {manager}")

    if source_updated_at:
        parts.append(f"데이터기준일자: {source_updated_at}")

    return " / ".join(parts)


def make_seed_row(item, tag_name, group_name, status, confidence):
    normalized_tag_name = normalize_tag_name(tag_name)

    return {
        # Place 매칭용
        "place_source": safe_str(item.get("source"), "heat_shelter_standard"),
        "place_external_id": safe_str(item.get("external_id")),
        "place_name": safe_str(item.get("name")),
        "category": "shelter",
        "address": safe_str(item.get("address")),
        "lat": safe_float(item.get("lat")),
        "lng": safe_float(item.get("lng")),

        # Tag 생성용
        "tag_name": normalized_tag_name,
        "tag_type": get_tag_type(normalized_tag_name, group_name),

        # PlaceTag 생성용
        "source": "field_rule",
        "status": status,
        "confidence": confidence,
        "evidence": make_evidence(tag_name, item),
        "is_verified": status == "confirmed",

        # 추적용
        "raw": {
            "original_tag_name": tag_name,
            "normalized_tag_name": normalized_tag_name,
            "tag_group": group_name,
            "place_source": item.get("source"),
            "place_external_id": item.get("external_id"),
            "source_name": item.get("source_name"),
            "source_updated_at": item.get("source_updated_at"),
            "data_quality_status": item.get("data_quality_status"),
            "data_quality_score": item.get("data_quality_score"),
            "raw_opening_hours": item.get("raw", {}).get("opening_hours", {}),
            "data_note": (
                "쉼터 정제 결과의 후보/확인필요 태그를 PlaceTag seed로 변환한 데이터입니다. "
                "쉼터 같은 기본 카테고리 태그와 정보 존재 여부 태그는 저장하지 않고, "
                "무더위/한파/실내/야외/운영/시설 관련 세부 속성만 저장합니다."
            ),
        },
    }


def build_seed_rows(items):
    rows = []
    skipped = []
    removed_tags = []
    seen = set()

    for item in items:
        place_source = safe_str(item.get("source"), "heat_shelter_standard")
        place_external_id = safe_str(item.get("external_id"))
        place_name = safe_str(item.get("name"))
        lat = safe_float(item.get("lat"))
        lng = safe_float(item.get("lng"))

        if not place_source or not place_external_id or not place_name or lat is None or lng is None:
            skipped.append({
                "reason": "place_required_field_missing",
                "place_source": place_source,
                "place_external_id": place_external_id,
                "place_name": place_name,
                "lat": lat,
                "lng": lng,
            })
            continue

        tag_groups = [
            {
                "group_name": "default_tags",
                "tags": item.get("default_tags", []),
                "status": "candidate",
                "confidence": 70,
            },
            {
                "group_name": "candidate_tags",
                "tags": item.get("candidate_tags", []),
                "status": "candidate",
                "confidence": 70,
            },
            {
                "group_name": "warning_tags",
                "tags": item.get("warning_tags", []),
                "status": "needs_verification",
                "confidence": 40,
            },
        ]

        for group in tag_groups:
            for tag_name in group["tags"]:
                tag_name = safe_str(tag_name)

                if not tag_name:
                    continue

                if should_remove_tag(tag_name):
                    removed_tags.append({
                        "place_external_id": place_external_id,
                        "place_name": place_name,
                        "tag_name": normalize_tag_name(tag_name),
                        "reason": get_remove_reason(tag_name),
                    })
                    continue

                normalized_tag_name = normalize_tag_name(tag_name)

                key = (
                    place_source,
                    place_external_id,
                    normalized_tag_name,
                    "field_rule",
                )

                if key in seen:
                    continue

                seen.add(key)

                rows.append(
                    make_seed_row(
                        item=item,
                        tag_name=tag_name,
                        group_name=group["group_name"],
                        status=group["status"],
                        confidence=group["confidence"],
                    )
                )

    return rows, skipped, removed_tags


def build_summary(items, skipped_input_items, seed_rows, skipped, removed_tags):
    tag_counter = Counter()
    source_counter = Counter()
    status_counter = Counter()
    tag_type_counter = Counter()
    removed_tag_counter = Counter()
    removed_reason_counter = Counter()
    place_keys = set()

    for row in seed_rows:
        place_keys.add((row["place_source"], row["place_external_id"]))
        tag_counter[row["tag_name"]] += 1
        source_counter[row["source"]] += 1
        status_counter[row["status"]] += 1
        tag_type_counter[row["tag_type"]] += 1

    for row in removed_tags:
        removed_tag_counter[row["tag_name"]] += 1
        removed_reason_counter[row["reason"]] += 1

    return {
        "input": {
            "input_path": str(INPUT_PATH),
            "skipped_input_path": str(SKIPPED_INPUT_PATH),
            "input_shelter_count": len(items),
            "input_skipped_count": len(skipped_input_items),
        },
        "output": {
            "place_tag_seed_place_count": len(place_keys),
            "place_tag_seed_row_count": len(seed_rows),
            "skipped_count": len(skipped),
            "removed_tag_count": len(removed_tags),
            "place_tag_seed_path": str(OUTPUT_PLACE_TAG_SEED_PATH),
            "summary_path": str(OUTPUT_SUMMARY_PATH),
        },
        "tag_counts": dict(tag_counter.most_common()),
        "source_counts": dict(source_counter.most_common()),
        "status_counts": dict(status_counter.most_common()),
        "tag_type_counts": dict(tag_type_counter.most_common()),
        "removed_tag_counts": dict(removed_tag_counter.most_common()),
        "removed_reason_counts": dict(removed_reason_counter.most_common()),
        "skipped": skipped,
        "data_note": (
            "이 파일은 쉼터 Place에 붙일 PlaceTag seed입니다. "
            "쉼터 같은 기본 태그와 운영시간정보있음/연락처있음 같은 정보 존재 여부 태그는 제거하고, "
            "추천/필터에 활용 가능한 세부 속성 태그만 저장합니다."
        ),
    }


def main():
    items = load_json(INPUT_PATH, [])
    skipped_input_items = load_json(SKIPPED_INPUT_PATH, [])

    if not items:
        print("쉼터 정제 데이터가 없습니다.")
        print("먼저 Test/apiTest/cleanData/clean_shelter.py를 실행해주세요.")
        return

    seed_rows, skipped, removed_tags = build_seed_rows(items)

    summary = build_summary(
        items=items,
        skipped_input_items=skipped_input_items,
        seed_rows=seed_rows,
        skipped=skipped,
        removed_tags=removed_tags,
    )

    save_json(OUTPUT_PLACE_TAG_SEED_PATH, seed_rows)
    save_json(OUTPUT_SUMMARY_PATH, summary)

    print("쉼터 PlaceTag seed 생성 완료")
    print(f"입력 쉼터 수: {summary['input']['input_shelter_count']}")
    print(f"입력 스킵 수: {summary['input']['input_skipped_count']}")
    print(f"PlaceTag seed 장소 수: {summary['output']['place_tag_seed_place_count']}")
    print(f"PlaceTag seed row 수: {summary['output']['place_tag_seed_row_count']}")
    print(f"스킵 수: {summary['output']['skipped_count']}")
    print(f"기본/노이즈 태그 제거 수: {summary['output']['removed_tag_count']}")
    print()
    print(f"PlaceTag seed 파일: {OUTPUT_PLACE_TAG_SEED_PATH}")
    print(f"요약 파일: {OUTPUT_SUMMARY_PATH}")
    print()
    print("source별 개수")
    for source, count in summary["source_counts"].items():
        print(f"- {source}: {count}")

    print()
    print("status별 개수")
    for status, count in summary["status_counts"].items():
        print(f"- {status}: {count}")

    print()
    print("제거 태그")
    for tag, count in summary["removed_tag_counts"].items():
        print(f"- {tag}: {count}")

    print()
    print("상위 태그")
    for tag, count in list(summary["tag_counts"].items())[:30]:
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()