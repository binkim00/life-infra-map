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

INPUT_PATH = BASE_DIR / "ExData" / "JsonData" / "beach" / "beaches_korea.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "beach_tag_results.json"
SKIPPED_PATH = Path(__file__).resolve().parent / "beach_tag_skipped_results.json"

BLOG_API_URL = "https://openapi.naver.com/v1/search/blog.json"

BEACH_TAG_KEYWORDS = {
    "산책": [
        "산책",
        "걷기",
        "해변길",
        "바닷길",
        "해안길",
        "둘레길",
        "트레킹",
    ],
    "힐링": [
        "힐링",
        "휴식",
        "여유",
        "쉬기",
        "바다멍",
        "멍때리기",
        "조용한",
        "한적한",
    ],
    "드라이브": [
        "드라이브",
        "해안도로",
        "바닷길 드라이브",
        "차박",
        "차 타고",
    ],
    "사진명소": [
        "사진",
        "포토존",
        "인생샷",
        "풍경",
        "뷰",
        "오션뷰",
        "감성",
        "출사",
    ],
    "데이트": [
        "데이트",
        "커플",
        "연인",
        "분위기 좋은",
    ],
    "가족방문": [
        "가족",
        "아이",
        "아이랑",
        "어린이",
        "아기",
        "가족여행",
    ],
    "야경": [
        "야경",
        "밤바다",
        "노을",
        "일몰",
        "석양",
        "해넘이",
    ],
    # "해수욕"은 검색어/장소명 때문에 거의 모든 데이터에 걸려서 제외
    "물놀이": [
        "물놀이",
        "수영",
        "피서",
        "여름휴가",
        "바다수영",
        "물에 들어가",
    ],
    "반려동물": [
        "강아지",
        "반려견",
        "애견",
        "반려동물",
        "댕댕이",
    ],
    "캠핑": [
        "캠핑",
        "야영",
        "캠핑장",
        "오토캠핑",
        "차박",
    ],
    "서핑": [
        "서핑",
        "서퍼",
        "서프",
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


def extract_default_tags():
    # 해수욕장 데이터 공통 기본 태그
    # 추천 필터용 세부 태그라기보다 카테고리 성격의 태그
    return ["해수욕장", "바다", "물놀이"]


def extract_blog_tags(blog_items):
    tags = set()
    matched_keywords = {}

    combined_text = ""

    for item in blog_items:
        title = clean_html(item.get("title", ""))
        description = clean_html(item.get("description", ""))
        combined_text += " " + title + " " + description

    for tag, keywords in BEACH_TAG_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined_text:
                tags.add(tag)
                matched_keywords.setdefault(tag, set()).add(keyword)

    return sorted(tags), {
        tag: sorted(list(words))
        for tag, words in matched_keywords.items()
    }


def extract_original_tags(beach):
    tags = []

    beach_knd = beach.get("beach_knd")
    beach_len = beach.get("beach_len")
    beach_wid = beach.get("beach_wid")

    if beach_knd:
        if "모래" in beach_knd or "패사" in beach_knd:
            tags.append("모래해변")
        if "자갈" in beach_knd:
            tags.append("자갈해변")
        if "몽돌" in beach_knd:
            tags.append("몽돌해변")

    if isinstance(beach_len, (int, float)):
        if beach_len >= 1000:
            tags.append("긴해변")

    if isinstance(beach_wid, (int, float)):
        if beach_wid >= 100:
            tags.append("넓은해변")

    return sorted(set(tags))


def make_search_query(beach):
    sido = beach.get("sido_nm", "")
    gugun = beach.get("gugun_nm", "")
    name = beach.get("sta_nm", "")

    return f"{sido} {gugun} {name} 해수욕장"


def make_result(beach, query, blog_items):
    default_tags = extract_default_tags()
    blog_tags, matched_keywords = extract_blog_tags(blog_items)
    original_tags = extract_original_tags(beach)

    all_tags = sorted(set(default_tags + blog_tags + original_tags))

    return {
        "num": beach.get("num"),
        "sido_nm": beach.get("sido_nm"),
        "gugun_nm": beach.get("gugun_nm"),
        "sta_nm": beach.get("sta_nm"),
        "lat": beach.get("lat"),
        "lon": beach.get("lon"),
        "beach_knd": beach.get("beach_knd"),
        "beach_len": beach.get("beach_len"),
        "beach_wid": beach.get("beach_wid"),
        "tags": all_tags,
        "default_tags": default_tags,
        "blog_tags": blog_tags,
        "original_tags": original_tags,
        "matched_keywords": matched_keywords,
        "blog_count": len(blog_items),
        "search_query": query,
    }


def main():
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 .env에 없습니다.")
        return

    if not INPUT_PATH.exists():
        print(f"입력 파일이 없습니다: {INPUT_PATH}")
        return

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        beaches = json.load(f)

    results = []
    skipped = []

    print(f"전체 해수욕장 데이터 수: {len(beaches)}")
    print(f"입력 파일: {INPUT_PATH}")
    print(f"결과 파일: {OUTPUT_PATH}")
    print(f"스킵 파일: {SKIPPED_PATH}")

    for index, beach in enumerate(beaches, start=1):
        name = beach.get("sta_nm")
        query = make_search_query(beach)

        print(f"[{index}/{len(beaches)}] 검색: {query}")

        try:
            blog_items = search_blog(query, display=10)
            result = make_result(beach, query, blog_items)

            if result["tags"]:
                results.append(result)
            else:
                skipped.append(result)

            time.sleep(0.2)

        except Exception as e:
            print(f"검색 실패: {query} / {e}")

            skipped.append({
                "num": beach.get("num"),
                "sido_nm": beach.get("sido_nm"),
                "gugun_nm": beach.get("gugun_nm"),
                "sta_nm": name,
                "lat": beach.get("lat"),
                "lon": beach.get("lon"),
                "beach_knd": beach.get("beach_knd"),
                "beach_len": beach.get("beach_len"),
                "beach_wid": beach.get("beach_wid"),
                "search_query": query,
                "error": str(e),
            })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    with open(SKIPPED_PATH, "w", encoding="utf-8") as f:
        json.dump(skipped, f, ensure_ascii=False, indent=2)

    print("작업 완료")
    print(f"태그 생성 결과: {OUTPUT_PATH}")
    print(f"스킵 결과: {SKIPPED_PATH}")
    print(f"태그 있음: {len(results)}개")
    print(f"태그 없음/실패: {len(skipped)}개")


if __name__ == "__main__":
    main()