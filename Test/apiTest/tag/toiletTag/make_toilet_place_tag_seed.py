import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "toilet_places.json"
SKIPPED_INPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "skipped" / "toilet_skipped.json"

OUTPUT_PLACE_TAG_SEED_PATH = SCRIPT_DIR / "toilet_place_tag_seed.json"
OUTPUT_SUMMARY_PATH = SCRIPT_DIR / "toilet_place_tag_seed_summary.json"


BASIC_TAGS = {
    "공중화장실",
    "화장실",
    "생활편의",
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
        # 화장실 구분/유형
        "개방화장실": "개방화장실",
        "간이화장실": "간이화장실",

        # 위치/용도 후보
        "공원화장실": "공원화장실",
        "교통시설화장실": "교통시설화장실",
        "시장화장실": "시장화장실",
        "관광지화장실": "관광지화장실",
        "공공시설화장실": "공공시설화장실",

        # 개방 시간
        "24시간개방후보": "24시간개방후보",
        "개방시간정보있음": "개방시간정보있음",

        # 시설/편의
        "남녀화장실정보있음": "남녀화장실정보있음",
        "장애인화장실있음": "장애인화장실있음",
        "어린이화장실있음": "어린이화장실있음",
        "규모큰화장실후보": "규모큰화장실후보",
        "비상벨있음": "비상벨있음",
        "CCTV있음": "CCTV있음",
        "기저귀교환대있음": "기저귀교환대있음",
        "아이와가기좋음후보": "아이와가기좋음후보",
        "공공관리후보": "공공관리후보",
        "오물처리방식정보있음": "오물처리방식정보있음",
        "연락처있음": "연락처있음",

        # 확인 필요
        "화장실구분확인필요": "화장실구분확인필요",
        "개방시간확인필요": "개방시간확인필요",
        "비상벨확인필요": "비상벨확인필요",
        "주소확인필요": "주소확인필요",
        "기준일확인필요": "기준일확인필요",
        "관리기관확인필요": "관리기관확인필요",
        "연락처확인필요": "연락처확인필요",
    }

    return tag_map.get(tag_name, tag_name)


def is_basic_tag(tag_name):
    return normalize_tag_name(tag_name) in BASIC_TAGS


def get_tag_type(tag_name, group_name):
    tag_name = normalize_tag_name(tag_name)

    toilet_type_tags = {
        "개방화장실",
        "간이화장실",
    }

    if group_name == "warning_tags":
        return "warning"

    if tag_name in toilet_type_tags:
        return "category"

    return "recommendation"


def make_evidence(tag_name, source_type, item):
    raw = item.get("raw", {})

    toilet_type = (
        safe_str(raw.get("구분"))
        or safe_str(raw.get("구분명"))
        or safe_str(raw.get("화장실구분"))
    )

    toilet_name = safe_str(raw.get("화장실명"))
    open_time = safe_str(raw.get("개방시간"))
    open_time_detail = safe_str(raw.get("개방시간상세"))

    owner_type = safe_str(raw.get("화장실소유구분"))
    disposal_type = safe_str(raw.get("오물처리방식"))

    emergency_bell = safe_str(raw.get("비상벨설치여부"))
    emergency_bell_place = safe_str(raw.get("비상벨설치장소"))
    cctv = (
        safe_str(raw.get("화장실입구CCTV설치유무"))
        or safe_str(raw.get("화장실입구CCTV설치여부"))
    )
    diaper_table = (
        safe_str(raw.get("기저귀교환대유무"))
        or safe_str(raw.get("기저귀교환대여부"))
    )
    diaper_place = safe_str(raw.get("기저귀교환대장소"))

    if source_type == "field_rule":
        parts = ["공중화장실 원본 필드 기반 태그"]

        if toilet_type:
            parts.append(f"화장실구분: {toilet_type}")

        if toilet_name:
            parts.append(f"화장실명: {toilet_name}")

        if open_time or open_time_detail:
            parts.append(f"개방시간: {open_time} {open_time_detail}".strip())

        if emergency_bell or emergency_bell_place:
            parts.append(f"비상벨: {emergency_bell} {emergency_bell_place}".strip())

        if cctv:
            parts.append(f"CCTV: {cctv}")

        if diaper_table or diaper_place:
            parts.append(f"기저귀교환대: {diaper_table} {diaper_place}".strip())

        if owner_type:
            parts.append(f"소유구분: {owner_type}")

        if disposal_type:
            parts.append(f"오물처리방식: {disposal_type}")

        return " / ".join(parts)

    return f"공중화장실 원본 필드 확인 필요: {tag_name}"


def make_seed_row(item, tag_name, group_name, status, confidence):
    normalized_tag_name = normalize_tag_name(tag_name)

    return {
        # Place 매칭용
        "place_source": safe_str(item.get("source"), "public_toilet_standard"),
        "place_external_id": safe_str(item.get("external_id")),
        "place_name": safe_str(item.get("name")),
        "category": "toilet",
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
        "evidence": make_evidence(tag_name, "field_rule", item),
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
            "data_note": (
                "공중화장실 정제 결과의 후보/확인필요 태그를 PlaceTag seed로 변환한 데이터입니다. "
                "공중화장실, 화장실, 생활편의처럼 Place.category로 표현 가능한 기본 태그는 저장하지 않습니다."
            ),
        },
    }


def build_seed_rows(items):
    rows = []
    skipped = []
    removed_basic_tags = []
    seen = set()

    for item in items:
        place_source = safe_str(item.get("source"), "public_toilet_standard")
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
            # default_tags 중에서도 공중화장실/생활편의 같은 기본 태그는 제거하고,
            # 개방화장실/간이화장실처럼 세부 구분으로 쓸 수 있는 것만 유지합니다.
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

                if is_basic_tag(tag_name):
                    removed_basic_tags.append({
                        "place_external_id": place_external_id,
                        "place_name": place_name,
                        "tag_name": tag_name,
                        "reason": "basic_category_tag",
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

    return rows, skipped, removed_basic_tags


def build_summary(items, skipped_input_items, seed_rows, skipped, removed_basic_tags):
    tag_counter = Counter()
    source_counter = Counter()
    status_counter = Counter()
    tag_type_counter = Counter()
    removed_basic_tag_counter = Counter()
    place_keys = set()

    for row in seed_rows:
        place_keys.add((row["place_source"], row["place_external_id"]))
        tag_counter[row["tag_name"]] += 1
        source_counter[row["source"]] += 1
        status_counter[row["status"]] += 1
        tag_type_counter[row["tag_type"]] += 1

    for row in removed_basic_tags:
        removed_basic_tag_counter[row["tag_name"]] += 1

    return {
        "input": {
            "input_path": str(INPUT_PATH),
            "skipped_input_path": str(SKIPPED_INPUT_PATH),
            "input_toilet_count": len(items),
            "input_skipped_count": len(skipped_input_items),
        },
        "output": {
            "place_tag_seed_place_count": len(place_keys),
            "place_tag_seed_row_count": len(seed_rows),
            "skipped_count": len(skipped),
            "removed_basic_tag_count": len(removed_basic_tags),
            "place_tag_seed_path": str(OUTPUT_PLACE_TAG_SEED_PATH),
            "summary_path": str(OUTPUT_SUMMARY_PATH),
        },
        "tag_counts": dict(tag_counter.most_common()),
        "source_counts": dict(source_counter.most_common()),
        "status_counts": dict(status_counter.most_common()),
        "tag_type_counts": dict(tag_type_counter.most_common()),
        "removed_basic_tag_counts": dict(removed_basic_tag_counter.most_common()),
        "skipped": skipped,
        "data_note": (
            "이 파일은 공중화장실 Place에 붙일 PlaceTag seed입니다. "
            "공중화장실, 화장실, 생활편의처럼 Place.category로 표현 가능한 기본 태그는 제거하고, "
            "개방시간, 장애인화장실, 어린이화장실, 비상벨, CCTV, 기저귀교환대, 확인필요 태그 등 "
            "추천/필터에 활용 가능한 세부 속성만 저장합니다."
        ),
    }


def main():
    items = load_json(INPUT_PATH, [])
    skipped_input_items = load_json(SKIPPED_INPUT_PATH, [])

    if not items:
        print("공중화장실 정제 데이터가 없습니다.")
        print("먼저 Test/apiTest/cleanData/clean_toilet.py를 실행해주세요.")
        return

    seed_rows, skipped, removed_basic_tags = build_seed_rows(items)

    summary = build_summary(
        items=items,
        skipped_input_items=skipped_input_items,
        seed_rows=seed_rows,
        skipped=skipped,
        removed_basic_tags=removed_basic_tags,
    )

    save_json(OUTPUT_PLACE_TAG_SEED_PATH, seed_rows)
    save_json(OUTPUT_SUMMARY_PATH, summary)

    print("공중화장실 PlaceTag seed 생성 완료")
    print(f"입력 공중화장실 수: {summary['input']['input_toilet_count']}")
    print(f"입력 스킵 수: {summary['input']['input_skipped_count']}")
    print(f"PlaceTag seed 장소 수: {summary['output']['place_tag_seed_place_count']}")
    print(f"PlaceTag seed row 수: {summary['output']['place_tag_seed_row_count']}")
    print(f"스킵 수: {summary['output']['skipped_count']}")
    print(f"기본 태그 제거 수: {summary['output']['removed_basic_tag_count']}")
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
    print("제거된 기본 태그")
    for tag, count in summary["removed_basic_tag_counts"].items():
        print(f"- {tag}: {count}")

    print()
    print("상위 태그")
    for tag, count in list(summary["tag_counts"].items())[:30]:
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()