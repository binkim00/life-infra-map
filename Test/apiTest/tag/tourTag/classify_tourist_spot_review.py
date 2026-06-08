import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

SKIPPED_PATH = BASE_DIR / "tourist_spot_busan_skipped.json"
OUTPUT_PATH = BASE_DIR / "tourist_spot_busan_review_candidates.json"


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


def make_review_item(item, review_reason, suggested_tags=None):
    if suggested_tags is None:
        suggested_tags = []

    return {
        "review_reason": review_reason,
        "suggested_tags": suggested_tags,
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
    }


def classify_no_matched_item(item):
    title = item.get("title", "")

    exclude_keywords = [
        "주식회사", "성형외과", "의원", "병원",
        "키즈", "키자니아", "몬스터파크", "히어로테마파크",
        "롯데월드", "렛츠런파크", "노리클럽"
    ]

    if contains_any(title, exclude_keywords):
        return "review_exclude", make_review_item(
            item,
            "서비스 추천 태그와 맞지 않거나 업체/시설 성격이 강함",
            []
        )

    # 역사/문화재/기념 성격: 좋은 데이터일 수 있지만 추천 태그 판단은 보강 필요
    history_keywords = [
        "성지", "성", "터", "유적", "향교", "고분군", "기념",
        "충렬", "탑", "의용단", "디오라마", "창고"
    ]

    if contains_any(title, history_keywords):
        return "review_needs_blog", make_review_item(
            item,
            "역사/문화 장소로 보이나 이름만으로 상황 태그 판단이 어려움",
            ["solo_good", "photo_good"]
        )

    # 이름만 봐도 살릴 가능성이 있는 장소
    usable_rules = [
        {
            "keywords": ["신선대", "두도"],
            "reason": "전망/자연 장소 후보로 보이나 태그 확정 전 검토 필요",
            "suggested_tags": ["walk_good", "healing", "photo_good"],
        },
        {
            "keywords": ["장미원"],
            "reason": "정원/꽃 구경 장소 후보",
            "suggested_tags": ["healing", "photo_good", "date_good"],
        },
        {
            "keywords": ["해운대 관광특구", "용두산 자갈치 관광특구", "서면1번가"],
            "reason": "넓은 지역 단위라 개별 장소 추천에 적합한지 검토 필요",
            "suggested_tags": ["photo_good", "date_good"],
        },
        {
            "keywords": ["아쿠아리움"],
            "reason": "실내 관광지 후보이나 상황 태그 기준 검토 필요",
            "suggested_tags": ["date_good", "photo_good"],
        },
        {
            "keywords": ["문화공감"],
            "reason": "문화 공간 후보이나 세부 성격 확인 필요",
            "suggested_tags": ["solo_good", "photo_good"],
        },
        {
            "keywords": ["들락날락"],
            "reason": "공간 성격 확인 필요",
            "suggested_tags": ["solo_good"],
        },
    ]

    for rule in usable_rules:
        if contains_any(title, rule["keywords"]):
            return "review_usable", make_review_item(
                item,
                rule["reason"],
                rule["suggested_tags"]
            )

    # 기타는 블로그/API 보강 후보
    return "review_needs_blog", make_review_item(
        item,
        "이름만으로 추천 태그 판단이 어려워 추가 정보 확인 필요",
        []
    )


def main():
    skipped_data = load_json(SKIPPED_PATH)

    result = {
        "coordinate_fix_needed": [],
        "review_usable": [],
        "review_needs_blog": [],
        "review_exclude": [],
        "summary": {},
    }

    for item in skipped_data.get("invalid_coordinate", []):
        result["coordinate_fix_needed"].append(
            make_review_item(
                item,
                "부산 장소로 보이지만 좌표가 부산 범위 밖이라 좌표 보정 필요",
                []
            )
        )

    for item in skipped_data.get("no_matched_tag", []):
        category, review_item = classify_no_matched_item(item)
        result[category].append(review_item)

    result["summary"] = {
        "coordinate_fix_needed_count": len(result["coordinate_fix_needed"]),
        "review_usable_count": len(result["review_usable"]),
        "review_needs_blog_count": len(result["review_needs_blog"]),
        "review_exclude_count": len(result["review_exclude"]),
        "total_review_count": (
            len(result["coordinate_fix_needed"])
            + len(result["review_usable"])
            + len(result["review_needs_blog"])
            + len(result["review_exclude"])
        ),
    }

    save_json(OUTPUT_PATH, result)

    print("관광지 skipped 검토 분류 완료")
    print(f"좌표 보정 필요: {result['summary']['coordinate_fix_needed_count']}")
    print(f"사용 후보: {result['summary']['review_usable_count']}")
    print(f"블로그/API 보강 후보: {result['summary']['review_needs_blog_count']}")
    print(f"제외 후보: {result['summary']['review_exclude_count']}")
    print(f"전체 검토 대상: {result['summary']['total_review_count']}")


if __name__ == "__main__":
    main()