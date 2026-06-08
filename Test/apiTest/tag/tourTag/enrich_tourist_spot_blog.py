import json
import os
import time
import requests
from pathlib import Path
from html import unescape
import re
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")

INPUT_PATH = BASE_DIR / "tourist_spot_busan_all_blog_targets.json"
OUTPUT_PATH = BASE_DIR / "tourist_spot_busan_all_blog_enriched.json"

NAVER_BLOG_SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_html(text):
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def search_naver_blog(query, display=5):
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 환경변수가 없습니다.")

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    params = {
        "query": query,
        "display": display,
        "start": 1,
        "sort": "sim",
    }

    response = requests.get(
        NAVER_BLOG_SEARCH_URL,
        headers=headers,
        params=params,
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    return data.get("items", [])


def infer_tags_from_blog_text(text):
    """
    블로그 제목/요약 기반 보강 태그 후보.
    확정 태그가 아니라 blog_search 기반 후보 태그임.
    """
    tag_rules = [
        {
            "tag": "photo_good",
            "keywords": [
                "사진", "포토", "인생샷", "뷰", "전망", "풍경", "감성",
                "예쁜", "예쁘", "촬영", "스팟", "핫플"
            ],
        },
        {
            "tag": "date_good",
            "keywords": [
                "데이트", "커플", "연인", "가볼만한곳", "나들이", "코스"
            ],
        },
        {
            "tag": "walk_good",
            "keywords": [
                "산책", "걷기", "트레킹", "길", "둘레길", "코스", "걷기좋은"
            ],
        },
        {
            "tag": "healing",
            "keywords": [
                "힐링", "조용", "한적", "여유", "쉼", "휴식", "자연", "편안"
            ],
        },
        {
            "tag": "night_view",
            "keywords": [
                "야경", "밤", "노을", "일몰", "선셋", "불빛"
            ],
        },
        {
            "tag": "drive_good",
            "keywords": [
                "드라이브", "차로", "주차", "근교", "코스"
            ],
        },
        {
            "tag": "solo_good",
            "keywords": [
                "혼자", "혼놀", "혼자서", "혼자 가기", "조용", "전시", "문화"
            ],
        },
    ]

    matched_tags = []
    matched_details = []

    for rule in tag_rules:
        matched_keywords = []

        for keyword in rule["keywords"]:
            if keyword in text:
                matched_keywords.append(keyword)

        if matched_keywords:
            matched_tags.append(rule["tag"])
            matched_details.append({
                "tag": rule["tag"],
                "matched_keywords": matched_keywords,
                "source": "blog_search",
            })

    return matched_tags, matched_details


def enrich_place_with_blog(place):
    title = place.get("title", "")
    search_keywords = place.get("suggested_search_keywords", [])

    blog_items = []
    evidence_texts = []

    for query in search_keywords[:2]:
        try:
            items = search_naver_blog(query, display=5)

            for item in items:
                cleaned_item = {
                    "query": query,
                    "title": clean_html(item.get("title", "")),
                    "description": clean_html(item.get("description", "")),
                    "bloggername": item.get("bloggername", ""),
                    "link": item.get("link", ""),
                    "postdate": item.get("postdate", ""),
                }

                blog_items.append(cleaned_item)
                evidence_texts.append(
                    cleaned_item["title"] + " " + cleaned_item["description"]
                )

            time.sleep(0.2)

        except Exception as e:
            blog_items.append({
                "query": query,
                "error": str(e),
            })

    combined_text = " ".join(evidence_texts)
    blog_tags, blog_tag_sources = infer_tags_from_blog_text(combined_text)

    return {
        "contentid": place.get("contentid", ""),
        "title": title,
        "addr1": place.get("addr1", ""),
        "mapx": place.get("mapx", ""),
        "mapy": place.get("mapy", ""),
        "priority": place.get("priority", ""),
        "review_reason": place.get("review_reason", ""),
        "blog_evidence_count": len(evidence_texts),
        "blog_tags": blog_tags,
        "blog_tag_sources": blog_tag_sources,
        "blog_items": blog_items,
    }


def main():
    data = load_json(INPUT_PATH)

    target_places = data.get("targets", [])

    result = {
        "enriched_places": [],
        "summary": {},
    }

    for index, place in enumerate(target_places, start=1):
        print(f"[{index}/{len(target_places)}] 블로그 보강 중: {place.get('title', '')}")

        enriched = enrich_place_with_blog(place)
        result["enriched_places"].append(enriched)

    tag_counts = {}

    for place in result["enriched_places"]:
        for tag in place["blog_tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    result["summary"] = {
        "target_count": len(target_places),
        "enriched_count": len(result["enriched_places"]),
        "tag_counts": tag_counts,
        "input_file": str(INPUT_PATH),
    }

    save_json(OUTPUT_PATH, result)

    print()
    print("전체 블로그 보강 완료")
    print(f"대상 개수: {result['summary']['target_count']}")
    print(f"보강 결과 개수: {result['summary']['enriched_count']}")
    print("태그별 개수:")
    for tag, count in tag_counts.items():
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()