import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "tourist_spot_busan_blog_tag_save_candidates.json"
OUTPUT_PATH = BASE_DIR / "tourist_spot_busan_final_tag_candidates.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def should_exclude_place(place):
    priority = place.get("priority", "")

    if priority == "low":
        return True

    return False


def main():
    data = load_json(INPUT_PATH)

    final_candidates = []
    excluded_candidates = []

    for place in data.get("save_candidates", []):
        if should_exclude_place(place):
            excluded_candidates.append({
                "contentid": place.get("contentid", ""),
                "title": place.get("title", ""),
                "priority": place.get("priority", ""),
                "reason": "low_priority_excluded",
                "verified_tags": place.get("verified_tags", []),
            })
            continue

        final_candidates.append(place)

    tag_counts = {}

    for place in final_candidates:
        for tag in place.get("verified_tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    result = {
        "final_candidates": final_candidates,
        "excluded_candidates": excluded_candidates,
        "summary": {
            "input_save_candidate_count": len(data.get("save_candidates", [])),
            "final_candidate_count": len(final_candidates),
            "excluded_candidate_count": len(excluded_candidates),
            "tag_counts": tag_counts,
        }
    }

    save_json(OUTPUT_PATH, result)

    print("최종 블로그 기반 태그 후보 생성 완료")
    print(f"입력 저장 후보 수: {result['summary']['input_save_candidate_count']}")
    print(f"최종 저장 후보 수: {result['summary']['final_candidate_count']}")
    print(f"제외 후보 수: {result['summary']['excluded_candidate_count']}")
    print()
    print("태그별 개수")
    for tag, count in tag_counts.items():
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()