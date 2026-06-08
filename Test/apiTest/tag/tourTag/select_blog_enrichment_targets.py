import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "tourist_spot_busan_review_candidates.json"
OUTPUT_PATH = BASE_DIR / "tourist_spot_busan_blog_targets.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def contains_any(text, keywords):
    matched = []

    for keyword in keywords:
        if keyword in text:
            matched.append(keyword)

    return matched


def make_target_item(item, priority, reason, suggested_search_keywords):
    return {
        "priority": priority,
        "reason": reason,
        "suggested_search_keywords": suggested_search_keywords,
        "contentid": item.get("contentid", ""),
        "title": item.get("title", ""),
        "addr1": item.get("addr1", ""),
        "addr2": item.get("addr2", ""),
        "mapx": item.get("mapx", ""),
        "mapy": item.get("mapy", ""),
        "cat1": item.get("cat1", ""),
        "cat2": item.get("cat2", ""),
        "cat3": item.get("cat3", ""),
        "contenttypeid": item.get("contenttypeid", ""),
        "firstimage": item.get("firstimage", ""),
        "firstimage2": item.get("firstimage2", ""),
        "suggested_tags": item.get("suggested_tags", []),
        "review_reason": item.get("review_reason", ""),
    }


def classify_blog_priority(item):
    title = item.get("title", "")

    high_priority_rules = [
        {
            "keywords": ["감만시민부두", "두루팜", "라보드 우든보트", "망산도", "유주암", "북맛골", "빵천동", "스포원파크", "외양포 포진지", "월전장어구이촌", "카덴96", "커넥트현대", "테이블플라워", "플루니티", "하버요가"],
            "reason": "장소 성격이 불명확하지만 실제 방문/추천 장소일 가능성이 있어 보강 우선",
            "priority": "high",
        },
        {
            "keywords": ["경상좌수영성지", "관수옥", "초량왜관", "율리 바위그늘유적", "기장향교", "남선창고터", "동래읍성지", "동래향교", "복천동 고분군", "연산동 고분군", "부산진성", "충렬사", "충렬탑", "25의용단"],
            "reason": "역사/문화 장소로 보이며 추천 태그 확정을 위해 설명 보강 필요",
            "priority": "medium",
        },
    ]

    low_priority_rules = [
        {
            "keywords": ["남부산교회", "초량교회", "부산동명불원"],
            "reason": "종교 시설 성격이 강해 서비스 추천 장소로 쓸지 낮은 우선순위 검토",
            "priority": "low",
        },
        {
            "keywords": ["전포동 구상반려암", "온정개건비"],
            "reason": "특수 지질/기념물 성격이라 일반 추천 장소로 쓸지 낮은 우선순위 검토",
            "priority": "low",
        },
        {
            "keywords": ["남도해양열차", "S-train"],
            "reason": "장소보다는 교통/상품 성격이 강해 낮은 우선순위 검토",
            "priority": "low",
        },
    ]

    for rule in high_priority_rules:
        if contains_any(title, rule["keywords"]):
            return rule["priority"], rule["reason"]

    for rule in low_priority_rules:
        if contains_any(title, rule["keywords"]):
            return rule["priority"], rule["reason"]

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    for rule in high_priority_rules:
        pass

    return "medium", "기본 보강 후보"


def build_search_keywords(item):
    title = item.get("title", "")
    addr1 = item.get("addr1", "")

    keywords = []

    if title:
        keywords.append(f"{title} 부산")
        keywords.append(f"{title} 후기")
        keywords.append(f"{title} 가볼만한곳")

    if addr1:
        # 너무 길어지지 않게 구 단위 정도만 보조 키워드로 사용
        parts = addr1.split()
        if len(parts) >= 2:
            keywords.append(f"{parts[0]} {parts[1]} {title}")

    return keywords


def main():
    review_data = load_json(INPUT_PATH)

    result = {
        "high_priority": [],
        "medium_priority": [],
        "low_priority": [],
        "summary": {},
    }

    for item in review_data.get("review_needs_blog", []):
        priority, reason = classify_blog_priority(item)
        search_keywords = build_search_keywords(item)

        target = make_target_item(
            item=item,
            priority=priority,
            reason=reason,
            suggested_search_keywords=search_keywords,
        )

        if priority == "high":
            result["high_priority"].append(target)
        elif priority == "low":
            result["low_priority"].append(target)
        else:
            result["medium_priority"].append(target)

    result["summary"] = {
        "high_priority_count": len(result["high_priority"]),
        "medium_priority_count": len(result["medium_priority"]),
        "low_priority_count": len(result["low_priority"]),
        "total_count": (
            len(result["high_priority"])
            + len(result["medium_priority"])
            + len(result["low_priority"])
        ),
    }

    save_json(OUTPUT_PATH, result)

    print("블로그/API 보강 대상 선정 완료")
    print(f"높은 우선순위: {result['summary']['high_priority_count']}")
    print(f"중간 우선순위: {result['summary']['medium_priority_count']}")
    print(f"낮은 우선순위: {result['summary']['low_priority_count']}")
    print(f"전체 보강 후보: {result['summary']['total_count']}")


if __name__ == "__main__":
    main()