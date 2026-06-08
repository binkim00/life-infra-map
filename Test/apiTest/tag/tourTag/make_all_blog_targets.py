import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

TAGGED_PATH = BASE_DIR / "tourist_spot_busan_tagged.json"
REVIEW_CANDIDATES_PATH = BASE_DIR / "tourist_spot_busan_review_candidates.json"
BLOG_TARGETS_PATH = BASE_DIR / "tourist_spot_busan_blog_targets.json"

OUTPUT_PATH = BASE_DIR / "tourist_spot_busan_all_blog_targets.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_search_keywords(title, addr1):
    keywords = []

    if title:
        keywords.append(f"{title} 부산")
        keywords.append(f"{title} 후기")
        keywords.append(f"{title} 가볼만한곳")

    if addr1:
        parts = addr1.split()
        if len(parts) >= 2:
            keywords.append(f"{parts[0]} {parts[1]} {title}")

    return keywords


def make_target_from_tagged(place):
    title = place.get("title", "")
    addr1 = place.get("addr1", "")

    return {
        "priority": "auto_tagged",
        "reason": "이름 기반 자동 태그가 붙은 장소이므로 블로그 검색으로 근거 보강 필요",
        "suggested_search_keywords": build_search_keywords(title, addr1),
        "contentid": place.get("contentid", ""),
        "title": title,
        "addr1": addr1,
        "addr2": place.get("addr2", ""),
        "mapx": place.get("mapx", ""),
        "mapy": place.get("mapy", ""),
        "cat1": place.get("cat1", ""),
        "cat2": place.get("cat2", ""),
        "cat3": place.get("cat3", ""),
        "contenttypeid": place.get("contenttypeid", ""),
        "firstimage": place.get("firstimage", ""),
        "firstimage2": place.get("firstimage2", ""),
        "name_rule_tags": place.get("tags", []),
        "name_rule_tag_sources": place.get("tag_sources", []),
        "suggested_tags": place.get("tags", []),
        "review_reason": "name_rule 자동 태그 검증 대상",
    }


def make_target_from_review(item, priority):
    title = item.get("title", "")
    addr1 = item.get("addr1", "")

    return {
        "priority": priority,
        "reason": item.get("review_reason", ""),
        "suggested_search_keywords": item.get("suggested_search_keywords") or build_search_keywords(title, addr1),
        "contentid": item.get("contentid", ""),
        "title": title,
        "addr1": addr1,
        "addr2": item.get("addr2", ""),
        "mapx": item.get("mapx", ""),
        "mapy": item.get("mapy", ""),
        "cat1": item.get("cat1", ""),
        "cat2": item.get("cat2", ""),
        "cat3": item.get("cat3", ""),
        "contenttypeid": item.get("contenttypeid", ""),
        "firstimage": item.get("firstimage", ""),
        "firstimage2": item.get("firstimage2", ""),
        "name_rule_tags": [],
        "name_rule_tag_sources": [],
        "suggested_tags": item.get("suggested_tags", []),
        "review_reason": item.get("review_reason", ""),
    }


def add_unique(targets, seen_contentids, target):
    contentid = target.get("contentid", "")

    if not contentid:
        return

    if contentid in seen_contentids:
        return

    seen_contentids.add(contentid)
    targets.append(target)


def main():
    tagged_places = load_json(TAGGED_PATH)
    review_candidates = load_json(REVIEW_CANDIDATES_PATH)
    blog_targets = load_json(BLOG_TARGETS_PATH)

    targets = []
    seen_contentids = set()

    # 1. 이름 기반 자동 태그가 붙은 289개
    for place in tagged_places:
        target = make_target_from_tagged(place)
        add_unique(targets, seen_contentids, target)

    # 2. skipped 중 사용 후보 9개
    for item in review_candidates.get("review_usable", []):
        target = make_target_from_review(item, "review_usable")
        add_unique(targets, seen_contentids, target)

    # 3. skipped 중 블로그 보강 후보 37개
    for item in blog_targets.get("high_priority", []):
        target = make_target_from_review(item, "high")
        add_unique(targets, seen_contentids, target)

    for item in blog_targets.get("medium_priority", []):
        target = make_target_from_review(item, "medium")
        add_unique(targets, seen_contentids, target)

    for item in blog_targets.get("low_priority", []):
        target = make_target_from_review(item, "low")
        add_unique(targets, seen_contentids, target)

    result = {
        "targets": targets,
        "summary": {
            "target_count": len(targets),
            "source_counts": {
                "auto_tagged": len(tagged_places),
                "review_usable": len(review_candidates.get("review_usable", [])),
                "blog_high": len(blog_targets.get("high_priority", [])),
                "blog_medium": len(blog_targets.get("medium_priority", [])),
                "blog_low": len(blog_targets.get("low_priority", [])),
            }
        }
    }

    save_json(OUTPUT_PATH, result)

    print("전체 블로그 보강 대상 생성 완료")
    print(f"전체 대상 수: {result['summary']['target_count']}")
    print(result["summary"]["source_counts"])


if __name__ == "__main__":
    main()