import os
import json
import re
import time
import requests
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

BASE_DIR = Path(__file__).resolve().parents[4]

INPUT_PATH = BASE_DIR / "Test" / "apiTest" / "tag" / "parkTag" / "park_original_tag_results.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "park_blog_tag_results.json"
SKIPPED_PATH = Path(__file__).resolve().parent / "park_blog_tag_skipped_results.json"

BLOG_API_URL = "https://openapi.naver.com/v1/search/blog.json"


PARK_BLOG_TAG_KEYWORDS = {
    "피크닉": [
        "피크닉",
        "돗자리",
        "도시락",
        "나들이",
        "잔디밭",
        "잔디광장",
    ],
    "야경": [
        "야경",
        "밤산책",
        "밤 산책",
        "조명",
        "불빛",
        "노을",
        "일몰",
    ],
    "사진명소": [
        "사진",
        "포토존",
        "인생샷",
        "풍경",
        "뷰",
        "감성",
        "출사",
        "예쁜",
    ],
    "데이트": [
        "데이트",
        "커플",
        "연인",
        "분위기",
        "분위기 좋은",
    ],
    "가족방문": [
        "가족",
        "가족나들이",
        "가족 나들이",
        "아이랑",
        "아이와",
        "어린이",
        "아기",
    ],
    "아이동반": [
        "아이랑",
        "아이와",
        "어린이",
        "놀이터",
        "키즈",
        "유아",
        "아기",
    ],
    "산책": [
        "산책",
        "걷기",
        "산책로",
        "둘레길",
        "걷기 좋은",
        "길이 좋",
    ],
    "힐링": [
        "힐링",
        "휴식",
        "여유",
        "쉬기",
        "조용한",
        "한적한",
        "멍때리기",
    ],
    "운동": [
        "운동",
        "러닝",
        "조깅",
        "걷기운동",
        "자전거",
        "농구",
        "축구",
        "테니스",
        "배드민턴",
    ],
    "반려동물": [
        "강아지",
        "반려견",
        "애견",
        "반려동물",
        "댕댕이",
        "산책하기 좋은 강아지",
    ],
    "벚꽃": [
        "벚꽃",
        "벚꽃길",
        "봄꽃",
        "꽃구경",
    ],
    "단풍": [
        "단풍",
        "가을",
        "가을산책",
        "단풍길",
    ],
    "호수": [
        "호수",
        "저수지",
        "수변",
        "물가",
        "호수공원",
    ],
}


def clean_html(text):
    if not text:
        return ""

    text = re.sub(r"<.*?>", "", text)
    text = text.replace("&quot;", '"')
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")

    return text


def search_blog(query, display=10):
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    params = {
        "query": query,
        "display": display,
        "sort": "sim",
    }

    response = requests.get(
        BLOG_API_URL,
        headers=headers,
        params=params,
        timeout=10,
    )
    response.raise_for_status()

    return response.json().get("items", [])


def extract_blog_tags(blog_items):
    tags = set()
    matched_keywords = {}

    combined_text = ""

    for item in blog_items:
        title = clean_html(item.get("title", ""))
        description = clean_html(item.get("description", ""))
        combined_text += " " + title + " " + description

    for tag, keywords in PARK_BLOG_TAG_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined_text:
                tags.add(tag)
                matched_keywords.setdefault(tag, set()).add(keyword)

    return sorted(tags), {
        tag: sorted(list(words))
        for tag, words in matched_keywords.items()
    }


def make_search_query(park):
    name = park.get("name", "")
    road_address = park.get("road_address", "")
    lot_address = park.get("lot_address", "")

    address = road_address or lot_address

    sido_gugun = ""

    if address:
        address_parts = address.split()
        if len(address_parts) >= 2:
            sido_gugun = f"{address_parts[0]} {address_parts[1]}"
        elif len(address_parts) == 1:
            sido_gugun = address_parts[0]

    if sido_gugun:
        return f"{sido_gugun} {name}"
    return name


def make_result(park, query, blog_items):
    blog_tags, matched_keywords = extract_blog_tags(blog_items)

    default_tags = park.get("default_tags", [])
    original_tags = park.get("original_tags", [])

    all_tags = sorted(set(default_tags + original_tags + blog_tags))

    result = dict(park)
    result["tags"] = all_tags
    result["blog_tags"] = blog_tags
    result["matched_keywords"] = matched_keywords
    result["blog_count"] = len(blog_items)
    result["search_query"] = query

    return result


def main():
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 .env에 없습니다.")
        return

    if not INPUT_PATH.exists():
        print(f"입력 파일이 없습니다: {INPUT_PATH}")
        return

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        parks = json.load(f)

    blog_targets = [
        park for park in parks
        if park.get("blog_candidate") is True
    ]

    results = []
    skipped = []

    print(f"전체 공원 데이터 수: {len(parks)}")
    print(f"블로그 태그 대상 수: {len(blog_targets)}")
    print(f"입력 파일: {INPUT_PATH}")
    print(f"결과 파일: {OUTPUT_PATH}")
    print(f"스킵 파일: {SKIPPED_PATH}")

    for index, park in enumerate(blog_targets, start=1):
        name = park.get("name", "")
        query = make_search_query(park)

        print(f"[{index}/{len(blog_targets)}] 검색: {query}")

        try:
            blog_items = search_blog(query, display=10)
            result = make_result(park, query, blog_items)

            results.append(result)

            time.sleep(0.2)

        except Exception as e:
            print(f"검색 실패: {query} / {e}")

            skipped.append({
                "management_no": park.get("management_no"),
                "name": name,
                "park_type": park.get("park_type"),
                "lat": park.get("lat"),
                "lon": park.get("lon"),
                "area": park.get("area"),
                "search_query": query,
                "error": str(e),
            })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    with open(SKIPPED_PATH, "w", encoding="utf-8") as f:
        json.dump(skipped, f, ensure_ascii=False, indent=2)

    tag_count = {}
    empty_blog_tag_count = 0

    for item in results:
        blog_tags = item.get("blog_tags", [])

        if not blog_tags:
            empty_blog_tag_count += 1

        for tag in blog_tags:
            tag_count[tag] = tag_count.get(tag, 0) + 1

    print("작업 완료")
    print(f"블로그 태그 결과: {len(results)}개")
    print(f"검색 실패: {len(skipped)}개")
    print(f"블로그 태그 없음: {empty_blog_tag_count}개")
    print("블로그 태그 분포")

    for tag, count in sorted(tag_count.items(), key=lambda x: x[1], reverse=True):
        print(f"- {tag}: {count}개")

    print(f"결과 저장: {OUTPUT_PATH}")
    print(f"스킵 저장: {SKIPPED_PATH}")


if __name__ == "__main__":
    main()