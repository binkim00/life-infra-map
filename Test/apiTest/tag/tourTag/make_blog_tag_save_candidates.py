import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "tourist_spot_busan_all_blog_verified_tags.json"
OUTPUT_PATH = BASE_DIR / "tourist_spot_busan_blog_tag_save_candidates.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def filter_tag_sources(tag_sources, min_confidence=0.6):
    filtered = []

    for source in tag_sources:
        confidence = source.get("confidence", 0)

        if confidence < min_confidence:
            continue

        filtered.append({
            "tag": source.get("tag", ""),
            "source": source.get("source", "blog_search"),
            "matched_keywords": source.get("matched_keywords", []),
            "related_blog_count": source.get("related_blog_count", 0),
            "confidence": confidence,
            "is_verified": source.get("is_verified", False),
        })

    return filtered


def make_save_candidate(place):
    filtered_sources = filter_tag_sources(place.get("verified_tag_sources", []))
    filtered_tags = []

    for source in filtered_sources:
        tag = source.get("tag", "")
        if tag and tag not in filtered_tags:
            filtered_tags.append(tag)

    return {
        "contentid": place.get("contentid", ""),
        "title": place.get("title", ""),
        "addr1": place.get("addr1", ""),
        "mapx": place.get("mapx", ""),
        "mapy": place.get("mapy", ""),
        "priority": place.get("priority", ""),
        "verified_tags": filtered_tags,
        "verified_tag_sources": filtered_sources,
        "related_blog_count": place.get("related_blog_count", 0),
        "original_blog_evidence_count": place.get("original_blog_evidence_count", 0),
    }


def main():
    data = load_json(INPUT_PATH)

    save_candidates = []
    skipped_candidates = []

    for place in data.get("places", []):
        candidate = make_save_candidate(place)

        if candidate["verified_tags"]:
            save_candidates.append(candidate)
        else:
            skipped_candidates.append({
                "contentid": place.get("contentid", ""),
                "title": place.get("title", ""),
                "reason": "no_verified_tag_after_confidence_filter",
                "related_blog_count": place.get("related_blog_count", 0),
                "original_blog_evidence_count": place.get("original_blog_evidence_count", 0),
            })

    tag_counts = {}

    for place in save_candidates:
        for tag in place["verified_tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    result = {
        "save_candidates": save_candidates,
        "skipped_candidates": skipped_candidates,
        "summary": {
            "input_count": len(data.get("places", [])),
            "save_candidate_count": len(save_candidates),
            "skipped_candidate_count": len(skipped_candidates),
            "min_confidence": 0.6,
            "tag_counts": tag_counts,
        }
    }

    save_json(OUTPUT_PATH, result)

    print("블로그 기반 저장 후보 태그 생성 완료")
    print(f"입력 장소 수: {result['summary']['input_count']}")
    print(f"저장 후보 장소 수: {result['summary']['save_candidate_count']}")
    print(f"제외 후보 장소 수: {result['summary']['skipped_candidate_count']}")
    print()
    print("태그별 개수")
    for tag, count in tag_counts.items():
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()