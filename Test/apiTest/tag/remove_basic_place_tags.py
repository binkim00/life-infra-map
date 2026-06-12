import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]

TARGET_FILES = [
    {
        "name": "도시공원",
        "seed_path": BASE_DIR / "Test" / "apiTest" / "tag" / "parkTag" / "park_place_tag_seed.json",
        "summary_path": BASE_DIR / "Test" / "apiTest" / "tag" / "parkTag" / "park_place_tag_seed_summary.json",
    },
    {
        "name": "해수욕장",
        "seed_path": BASE_DIR / "Test" / "apiTest" / "tag" / "beachTag" / "beach_place_tag_seed.json",
        "summary_path": BASE_DIR / "Test" / "apiTest" / "tag" / "beachTag" / "beach_place_tag_seed_summary.json",
    },
    {
        "name": "주차장",
        "seed_path": BASE_DIR / "Test" / "apiTest" / "tag" / "parkingTag" / "parking_place_tag_seed.json",
        "summary_path": BASE_DIR / "Test" / "apiTest" / "tag" / "parkingTag" / "parking_place_tag_seed_summary.json",
    },
]

GLOBAL_BASIC_TAGS = {
    "공원",
    "도시공원",
    "주차장",
    "해수욕장",
    "바다",
    "야외",
    "화장실",
    "공중화장실",
    "무료와이파이",
    "흡연구역",
    "쉼터",
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

    temp_path = path.with_suffix(path.suffix + ".tmp")

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    temp_path.replace(path)


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def get_remove_reason(row):
    category = safe_str(row.get("category"))
    tag_name = safe_str(row.get("tag_name"))
    source = safe_str(row.get("source"))

    # 1. 도시공원 기본 태그 제거
    # 기존 공원 category_rule은 모든 공원에 공원/산책좋음/잠깐쉬기좋음을 붙이는 구조라 제거합니다.
    # field_rule, blog_search에서 나온 산책좋음/잠깐쉬기좋음은 유지합니다.
    if category == "city_park" and source == "category_rule":
        return "city_park_category_rule_basic_tag"

    # 2. 해수욕장 기본 태그 제거
    # 기존 해수욕장 category_rule은 해수욕장/바다/물놀이 기본 태그라 제거합니다.
    # blog_search에서 나온 물놀이는 유지합니다.
    if category == "beach" and source == "category_rule":
        return "beach_category_rule_basic_tag"

    # 3. 주차장은 '주차장' 태그만 제거
    # 공영주차장/민영주차장/노외주차장/노상주차장/부설주차장은 세부 분류라 유지합니다.
    if category == "parking" and tag_name == "주차장":
        return "parking_basic_tag"

    # 4. 혹시 다른 파일에 섞인 너무 기본적인 태그 제거
    # 단, 물놀이는 해수욕장 블로그 태그로 의미가 있으므로 전역 제거 대상에 넣지 않습니다.
    if tag_name in GLOBAL_BASIC_TAGS:
        return "global_basic_tag"

    return ""


def rebuild_summary(old_summary, seed_rows, removed_rows, target_name, seed_path, summary_path):
    tag_counter = Counter()
    source_counter = Counter()
    status_counter = Counter()
    tag_type_counter = Counter()
    place_keys = set()

    removed_tag_counter = Counter()
    removed_reason_counter = Counter()

    for row in seed_rows:
        place_keys.add((row.get("place_source"), row.get("place_external_id")))
        tag_counter[safe_str(row.get("tag_name"))] += 1
        source_counter[safe_str(row.get("source"))] += 1
        status_counter[safe_str(row.get("status"))] += 1
        tag_type_counter[safe_str(row.get("tag_type"))] += 1

    for item in removed_rows:
        row = item["row"]
        removed_tag_counter[safe_str(row.get("tag_name"))] += 1
        removed_reason_counter[item["reason"]] += 1

    if isinstance(old_summary, dict):
        summary = dict(old_summary)
    else:
        summary = {}

    summary["output"] = dict(summary.get("output", {}))
    summary["output"]["place_tag_seed_place_count"] = len(place_keys)
    summary["output"]["place_tag_seed_row_count"] = len(seed_rows)
    summary["output"]["place_tag_seed_path"] = str(seed_path)
    summary["output"]["summary_path"] = str(summary_path)

    summary["tag_counts"] = dict(tag_counter.most_common())
    summary["source_counts"] = dict(source_counter.most_common())
    summary["status_counts"] = dict(status_counter.most_common())
    summary["tag_type_counts"] = dict(tag_type_counter.most_common())

    summary["cleanup"] = {
        "target_name": target_name,
        "removed_row_count": len(removed_rows),
        "removed_tag_counts": dict(removed_tag_counter.most_common()),
        "removed_reason_counts": dict(removed_reason_counter.most_common()),
        "rule": (
            "Place.category로 이미 표현 가능한 너무 기본적인 태그는 PlaceTag에서 제거했습니다. "
            "카테고리명 자체는 저장하지 않고, 추천/필터에 필요한 세부 속성 태그만 유지합니다."
        ),
    }

    return summary


def clean_one_target(target):
    name = target["name"]
    seed_path = target["seed_path"]
    summary_path = target["summary_path"]

    rows = load_json(seed_path, [])
    old_summary = load_json(summary_path, {})

    if not rows:
        print(f"[{name}] seed row 없음. 건너뜀")
        return

    kept_rows = []
    removed_rows = []

    for row in rows:
        reason = get_remove_reason(row)

        if reason:
            removed_rows.append({
                "reason": reason,
                "row": row,
            })
        else:
            kept_rows.append(row)

    new_summary = rebuild_summary(
        old_summary=old_summary,
        seed_rows=kept_rows,
        removed_rows=removed_rows,
        target_name=name,
        seed_path=seed_path,
        summary_path=summary_path,
    )

    save_json(seed_path, kept_rows)
    save_json(summary_path, new_summary)

    print(f"[{name}] 기본 태그 제거 완료")
    print(f"- 기존 row 수: {len(rows)}")
    print(f"- 제거 row 수: {len(removed_rows)}")
    print(f"- 최종 row 수: {len(kept_rows)}")
    print("- 제거 태그")
    for tag, count in new_summary["cleanup"]["removed_tag_counts"].items():
        print(f"  - {tag}: {count}")
    print()


def main():
    print("기본 카테고리 태그 제거 시작")
    print()

    for target in TARGET_FILES:
        clean_one_target(target)

    print("기본 카테고리 태그 제거 완료")


if __name__ == "__main__":
    main()