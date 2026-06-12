import json
from collections import Counter
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent

SEED_PATH = SCRIPT_DIR / "toilet_place_tag_seed.json"
SUMMARY_PATH = SCRIPT_DIR / "toilet_place_tag_seed_summary.json"


NOISY_TAGS = {
    "오물처리방식정보있음",
    "남녀화장실정보있음",
    "연락처있음",
    "개방시간정보있음",
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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def rebuild_summary(old_summary, rows, removed_rows):
    tag_counter = Counter()
    source_counter = Counter()
    status_counter = Counter()
    tag_type_counter = Counter()
    place_keys = set()

    removed_tag_counter = Counter()

    for row in rows:
        place_keys.add((row.get("place_source"), row.get("place_external_id")))
        tag_counter[row.get("tag_name", "")] += 1
        source_counter[row.get("source", "")] += 1
        status_counter[row.get("status", "")] += 1
        tag_type_counter[row.get("tag_type", "")] += 1

    for row in removed_rows:
        removed_tag_counter[row.get("tag_name", "")] += 1

    summary = dict(old_summary)

    summary["output"] = dict(summary.get("output", {}))
    summary["output"]["place_tag_seed_place_count"] = len(place_keys)
    summary["output"]["place_tag_seed_row_count"] = len(rows)
    summary["output"]["removed_noisy_tag_count"] = len(removed_rows)

    summary["tag_counts"] = dict(tag_counter.most_common())
    summary["source_counts"] = dict(source_counter.most_common())
    summary["status_counts"] = dict(status_counter.most_common())
    summary["tag_type_counts"] = dict(tag_type_counter.most_common())

    summary["cleanup_noisy_tags"] = {
        "removed_tag_counts": dict(removed_tag_counter.most_common()),
        "rule": (
            "추천/필터에 직접 활용하기 어려운 정보 존재 여부 태그를 제거했습니다. "
            "오물처리방식정보있음, 남녀화장실정보있음, 연락처있음, 개방시간정보있음은 "
            "장소 상세 raw 정보로는 유지하지만 PlaceTag로는 저장하지 않습니다."
        ),
    }

    return summary


def main():
    rows = load_json(SEED_PATH, [])
    old_summary = load_json(SUMMARY_PATH, {})

    if not rows:
        print("화장실 PlaceTag seed 데이터가 없습니다.")
        return

    kept_rows = []
    removed_rows = []

    for row in rows:
        tag_name = row.get("tag_name", "")

        if tag_name in NOISY_TAGS:
            removed_rows.append(row)
        else:
            kept_rows.append(row)

    summary = rebuild_summary(old_summary, kept_rows, removed_rows)

    save_json(SEED_PATH, kept_rows)
    save_json(SUMMARY_PATH, summary)

    print("화장실 노이즈 태그 제거 완료")
    print(f"기존 row 수: {len(rows)}")
    print(f"제거 row 수: {len(removed_rows)}")
    print(f"최종 row 수: {len(kept_rows)}")
    print()
    print("제거 태그")
    for tag, count in summary["cleanup_noisy_tags"]["removed_tag_counts"].items():
        print(f"- {tag}: {count}")
    print()
    print("상위 태그")
    for tag, count in list(summary["tag_counts"].items())[:30]:
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()