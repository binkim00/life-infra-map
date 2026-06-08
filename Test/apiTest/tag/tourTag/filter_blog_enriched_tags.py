import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "tourist_spot_busan_all_blog_enriched.json"
OUTPUT_PATH = BASE_DIR / "tourist_spot_busan_all_blog_verified_tags.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_title(title):
    return (
        title.replace("(부산)", "")
        .replace("부산", "")
        .replace("·", " ")
        .replace("&", " ")
        .strip()
    )


def contains_place_hint(place, blog_item):
    """
    블로그 검색 결과가 해당 장소와 관련 있는지 1차 확인.
    장소명 일부 또는 주소의 구/군 단위가 검색 결과에 있으면 관련 있음으로 판단.
    """
    place_title = place.get("title", "")
    addr1 = place.get("addr1", "")

    text = blog_item.get("title", "") + " " + blog_item.get("description", "")

    if place_title and place_title in text:
        return True

    short_title = normalize_title(place_title)

    for part in short_title.split():
        if len(part) >= 2 and part in text:
            return True

    addr_parts = addr1.split()

    for part in addr_parts:
        if part.endswith("구") or part.endswith("군"):
            if part in text:
                return True

    return False


def should_keep_keyword(tag, keyword):
    """
    너무 흔해서 태그 근거로 약한 키워드는 제외.
    """
    weak_keywords = [
        "코스", "길", "주차", "후기", "가볼만한곳"
    ]

    strong_keywords_by_tag = {
        "photo_good": [
            "사진", "포토", "인생샷", "뷰", "전망", "풍경",
            "예쁜", "예쁘", "촬영", "스팟", "핫플"
        ],
        "date_good": [
            "데이트", "커플", "연인", "나들이"
        ],
        "walk_good": [
            "산책", "걷기", "트레킹", "둘레길", "걷기좋은"
        ],
        "healing": [
            "힐링", "조용", "한적", "여유", "쉼", "휴식", "자연", "편안"
        ],
        "night_view": [
            "야경", "밤", "노을", "일몰", "선셋", "불빛"
        ],
        "drive_good": [
            "드라이브", "차박", "차크닉"
        ],
        "solo_good": [
            "혼자", "혼놀", "혼자서", "혼자 가기", "조용", "전시", "문화"
        ],
    }

    if keyword in weak_keywords:
        return False

    return keyword in strong_keywords_by_tag.get(tag, [])


def collect_verified_tag_sources(place, related_blog_count):
    """
    기존 blog_tag_sources에서 강한 키워드만 남김.
    """
    verified_sources = []
    verified_tags = []

    for source in place.get("blog_tag_sources", []):
        tag = source.get("tag", "")
        keywords = source.get("matched_keywords", [])

        kept_keywords = []

        for keyword in keywords:
            if should_keep_keyword(tag, keyword):
                kept_keywords.append(keyword)

        if kept_keywords:
            if tag not in verified_tags:
                verified_tags.append(tag)

            verified_sources.append({
                "tag": tag,
                "source": "blog_search",
                "matched_keywords": kept_keywords,
                "related_blog_count": related_blog_count,
                "confidence": min(1.0, related_blog_count / 5),
                "is_verified": False,
            })

    return verified_tags, verified_sources


def make_verified_place(place):
    related_blog_items = []

    for blog_item in place.get("blog_items", []):
        if "error" in blog_item:
            continue

        if contains_place_hint(place, blog_item):
            related_blog_items.append(blog_item)

    related_blog_count = len(related_blog_items)

    if related_blog_count < 2:
        verified_tags = []
        verified_tag_sources = []
    else:
        verified_tags, verified_tag_sources = collect_verified_tag_sources(
            place,
            related_blog_count,
        )

    return {
        "contentid": place.get("contentid", ""),
        "title": place.get("title", ""),
        "addr1": place.get("addr1", ""),
        "mapx": place.get("mapx", ""),
        "mapy": place.get("mapy", ""),
        "priority": place.get("priority", ""),
        "review_reason": place.get("review_reason", ""),
        "name_rule_tags": place.get("name_rule_tags", []),
        "related_blog_count": related_blog_count,
        "original_blog_evidence_count": place.get("blog_evidence_count", 0),
        "verified_tags": verified_tags,
        "verified_tag_sources": verified_tag_sources,
        "related_blog_items": related_blog_items,
    }


def main():
    data = load_json(INPUT_PATH)

    result = {
        "places": [],
        "summary": {},
    }

    for place in data.get("enriched_places", []):
        verified_place = make_verified_place(place)
        result["places"].append(verified_place)

    tag_counts = {}
    places_with_tags = []
    places_without_tags = []

    for place in result["places"]:
        if place["verified_tags"]:
            places_with_tags.append(place["title"])
        else:
            places_without_tags.append(place["title"])

        for tag in place["verified_tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    result["summary"] = {
        "input_count": len(data.get("enriched_places", [])),
        "output_count": len(result["places"]),
        "places_with_verified_tags_count": len(places_with_tags),
        "places_without_verified_tags_count": len(places_without_tags),
        "tag_counts": tag_counts,
        "places_without_verified_tags": places_without_tags,
    }

    save_json(OUTPUT_PATH, result)

    print("전체 블로그 보강 태그 필터링 완료")
    print(f"입력 장소 수: {result['summary']['input_count']}")
    print(f"태그 남은 장소 수: {result['summary']['places_with_verified_tags_count']}")
    print(f"태그 없는 장소 수: {result['summary']['places_without_verified_tags_count']}")
    print()
    print("태그별 개수")
    for tag, count in tag_counts.items():
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()