import json
from datetime import datetime
from pathlib import Path


MATCHED_PATH = Path("ExData/ImportPlan/map_checked/beach_matched.json")
UNMATCHED_PATH = Path("ExData/ImportPlan/map_checked/beach_unmatched.json")
REVIEW_PATH = Path("ExData/ImportPlan/map_checked/beach_review.json")

OUTPUT_PATH = Path("ExData/ImportPlan/final/beach_db_ready.json")


VALID_BEACH_KEYWORDS = ["해수욕장", "해변", "비치"]


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_valid_beach_match(kakao):
    place_name = kakao.get("place_name") or ""
    category_name = kakao.get("category_name") or ""

    text = f"{place_name} {category_name}"

    if "폐쇄" in text:
        return False

    return any(keyword in text for keyword in VALID_BEACH_KEYWORDS)


def build_external_place(item):
    source = item.get("source", {})
    best_candidate = item.get("best_candidate", {})
    kakao = best_candidate.get("kakao", {})
    score = best_candidate.get("score", {})

    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("name"),
        "category": "beach",
        "provider": "kakao",
        "external_place_id": kakao.get("kakao_place_id"),
        "external_place_name": kakao.get("place_name"),
        "match_score": score.get("total_score"),
    }


def build_place_candidate(item):
    source = item.get("source", {})

    return {
        "source_id": source.get("source_id"),
        "name": source.get("name"),
        "category": "beach",
        "lat": source.get("lat"),
        "lng": source.get("lng"),
    }


def main():
    matched = load_json(MATCHED_PATH)
    unmatched = load_json(UNMATCHED_PATH)
    review = load_json(REVIEW_PATH)

    external_places = []
    filtered_review_count = 0
    seen_external_ids = set()

    for item in matched:
        best_candidate = item.get("best_candidate", {})
        kakao = best_candidate.get("kakao", {})

        external_place_id = kakao.get("kakao_place_id")

        if not external_place_id:
            filtered_review_count += 1
            continue

        if external_place_id in seen_external_ids:
            continue

        if not is_valid_beach_match(kakao):
            filtered_review_count += 1
            continue

        external_places.append(build_external_place(item))
        seen_external_ids.add(external_place_id)

    place_candidates = [build_place_candidate(item) for item in unmatched]

    result = {
        "dataset": "beach",
        "category": "beach",
        "purpose": "db_ready",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "source_total": len(matched) + len(unmatched) + len(review),
            "matched_input_count": len(matched),
            "external_place_count": len(external_places),
            "place_candidate_count": len(place_candidates),
            "manual_review_count": len(review),
            "filtered_matched_review_count": filtered_review_count,
            "db_ready_count": len(external_places) + len(place_candidates),
        },
        "external_places": external_places,
        "place_candidates": place_candidates,
    }

    save_json(OUTPUT_PATH, result)

    print("완료")
    print(f"출력 파일: {OUTPUT_PATH}")
    print(f"external_places: {len(external_places)}")
    print(f"place_candidates: {len(place_candidates)}")
    print(f"manual_review 제외: {len(review)}")
    print(f"오매칭 의심 제외: {filtered_review_count}")


if __name__ == "__main__":
    main()