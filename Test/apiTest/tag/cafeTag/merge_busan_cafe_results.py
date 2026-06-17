import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

PART1_DIR = BASE_DIR / "results_busan" / "part_01_west_central"
PART2_DIR = BASE_DIR / "results_busan" / "part_02_east_west"

OUTPUT_DIR = BASE_DIR / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESULT_OUTPUT = OUTPUT_DIR / "cafe_all_results.json"
SKIPPED_OUTPUT = OUTPUT_DIR / "cafe_all_skipped_results.json"


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"파일 없음: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def merge_by_external_id(items):
    merged = {}

    for item in items:
        external_id = str(item.get("external_id", "")).strip()

        if not external_id:
            continue

        # 이미 있으면 태그가 더 많은 쪽을 우선 사용
        if external_id in merged:
            old_tags = merged[external_id].get("tags", [])
            new_tags = item.get("tags", [])

            if len(new_tags) > len(old_tags):
                merged[external_id] = item
        else:
            merged[external_id] = item

    return list(merged.values())


def main():
    part1_results = load_json(PART1_DIR / "cafe_all_results.json")
    part2_results = load_json(PART2_DIR / "cafe_all_results.json")

    part1_skipped = load_json(PART1_DIR / "cafe_all_skipped_results.json")
    part2_skipped = load_json(PART2_DIR / "cafe_all_skipped_results.json")

    merged_results = merge_by_external_id(part1_results + part2_results)

    result_ids = {str(item.get("external_id", "")).strip() for item in merged_results}

    # results에 들어간 장소는 skipped에서 제거
    skipped_candidates = []
    for item in part1_skipped + part2_skipped:
        external_id = str(item.get("external_id", "")).strip()
        if external_id and external_id not in result_ids:
            skipped_candidates.append(item)

    merged_skipped = merge_by_external_id(skipped_candidates)

    save_json(RESULT_OUTPUT, merged_results)
    save_json(SKIPPED_OUTPUT, merged_skipped)

    tag_row_count = sum(len(item.get("tags", [])) for item in merged_results)

    print("==============================")
    print("부산 카페 part1 + part2 병합 완료")
    print("==============================")
    print(f"part1 results: {len(part1_results)}")
    print(f"part2 results: {len(part2_results)}")
    print(f"merged results: {len(merged_results)}")
    print(f"part1 skipped: {len(part1_skipped)}")
    print(f"part2 skipped: {len(part2_skipped)}")
    print(f"merged skipped: {len(merged_skipped)}")
    print(f"merged tag row: {tag_row_count}")
    print()
    print(f"results 저장: {RESULT_OUTPUT}")
    print(f"skipped 저장: {SKIPPED_OUTPUT}")


if __name__ == "__main__":
    main()