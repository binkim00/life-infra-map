# crawl_region_naver_cafe_keywords_test.py

import csv
import re
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


BASE_DIR = Path(__file__).resolve().parent

SEARCH_KEYWORD = "부산 전포 카페"
MAX_PLACES = 3

PLACE_URL_CSV = BASE_DIR / "naver_place_urls.csv"
KEYWORD_RESULT_CSV = BASE_DIR / "naver_region_cafe_keywords.csv"


KEYWORD_PATTERNS = [
    "좋아요",
    "맛있어요",
    "친절해요",
    "청결해요",
    "넓어요",
    "편해요",
    "멋져요",
    "잘 나와요",
    "대화하기",
    "혼밥",
    "혼자",
    "모임",
    "데이트",
    "사진",
    "인테리어",
    "분위기",
    "좌석",
    "공간",
    "뷰",
    "특별한 날",
]


def make_search_url(keyword: str) -> str:
    encoded = quote(keyword)
    return f"https://m.map.naver.com/search2/search.naver?query={encoded}"


def normalize_place_url(url: str) -> str:
    """
    검색 결과에서 잡힌 여러 링크 중 place ID만 추출해서
    방문자 리뷰 페이지 URL로 통일합니다.

    예:
    https://m.place.naver.com/place/2057510640/home
    https://m.place.naver.com/place/2057510640/menu/list
    → https://m.place.naver.com/place/2057510640/review/visitor
    """
    if not url:
        return ""

    match = re.search(r"m\.place\.naver\.com/(?:place|restaurant|cafe)/(\d+)", url)

    if not match:
        return ""

    place_id = match.group(1)

    return f"https://m.place.naver.com/place/{place_id}/review/visitor"


def extract_place_urls(page):
    """
    검색 페이지에서 네이버 플레이스 링크를 수집하되,
    같은 place_id는 한 번만 저장합니다.
    """
    urls = page.locator("a").evaluate_all(
        """
        anchors => anchors
          .map(a => a.href)
          .filter(href => href && href.includes('m.place.naver.com'))
        """
    )

    normalized_urls = []
    seen_place_ids = set()

    for url in urls:
        match = re.search(r"m\.place\.naver\.com/(?:place|restaurant|cafe)/(\d+)", url)

        if not match:
            continue

        place_id = match.group(1)

        if place_id in seen_place_ids:
            continue

        seen_place_ids.add(place_id)

        review_url = f"https://m.place.naver.com/place/{place_id}/review/visitor"
        normalized_urls.append(review_url)

    return normalized_urls


def extract_candidate_keywords(text: str):
    """
    페이지 전체 텍스트에서 방문자 리뷰 키워드만 추출합니다.

    네이버 방문자 키워드는 보통 다음처럼 따옴표로 노출됩니다.
    "인테리어가 멋져요"
    "디저트가 맛있어요"
    "가성비가 좋아요"

    따라서 일반 문장은 제외하고 따옴표 안의 짧은 문장만 추출합니다.
    """
    candidates = []

    quoted_keywords = re.findall(r'"([^"]{2,40})"', text)

    for keyword in quoted_keywords:
        keyword = keyword.strip()

        if not keyword:
            continue

        # 방문자 리뷰 키워드 느낌이 아닌 것은 제외
        if not keyword.endswith("요"):
            continue

        candidates.append(keyword)

    return candidates


def normalize_keyword(line: str):
    """
    예:
    '인테리어가 멋져요 12' -> ('인테리어가 멋져요', 12)
    '대화하기 좋아요' -> ('대화하기 좋아요', 1)
    """
    line = line.strip()

    match = re.match(r"^(.*?)[\s]*([0-9,]+)$", line)

    if match:
        keyword = match.group(1).strip()
        count = int(match.group(2).replace(",", ""))
        return keyword, count

    return line, 1


def save_place_urls(place_urls):
    with PLACE_URL_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["place_url"])
        writer.writeheader()

        for url in place_urls:
            writer.writerow({"place_url": url})


def save_keyword_results(rows):
    with KEYWORD_RESULT_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        fieldnames = ["search_keyword", "place_url", "keyword", "count"]

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow(row)


def main():
    search_url = make_search_url(SEARCH_KEYWORD)

    all_keyword_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=100,
        )

        page = browser.new_page(
            viewport={"width": 390, "height": 900},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            ),
        )

        try:
            print(f"[1] 지역 검색 접속: {search_url}")
            page.goto(search_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            for _ in range(5):
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(1000)

            place_urls = extract_place_urls(page)
            place_urls = place_urls[:MAX_PLACES]

            save_place_urls(place_urls)

            print(f"[2] 수집된 장소 URL 수: {len(place_urls)}")
            print(f"장소 URL 저장: {PLACE_URL_CSV}")

            if not place_urls:
                print("장소 URL을 찾지 못했습니다.")
                print("네이버 지도 검색 페이지 구조가 바뀌었거나, 링크가 숨겨져 있을 수 있습니다.")
                browser.close()
                return

            for index, place_url in enumerate(place_urls, start=1):
                print(f"\n[3-{index}] 방문자 리뷰 페이지 접속: {place_url}")

                try:
                    page.goto(place_url, wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(3000)

                    for _ in range(5):
                        page.mouse.wheel(0, 800)
                        page.wait_for_timeout(1000)

                    body_text = page.locator("body").inner_text(timeout=10000)

                    candidate_lines = extract_candidate_keywords(body_text)

                    keyword_count_map = {}

                    for line in candidate_lines:
                        keyword, count = normalize_keyword(line)
                        keyword_count_map[keyword] = keyword_count_map.get(keyword, 0) + count

                    for keyword, count in keyword_count_map.items():
                        all_keyword_rows.append(
                            {
                                "search_keyword": SEARCH_KEYWORD,
                                "place_url": place_url,
                                "keyword": keyword,
                                "count": count,
                            }
                        )

                    print(f"추출 키워드 후보 수: {len(keyword_count_map)}")

                    for keyword, count in list(keyword_count_map.items())[:10]:
                        print(f"- {keyword}: {count}")

                except PlaywrightTimeoutError:
                    print("방문자 리뷰 페이지 로딩 시간 초과")
                    continue
                except Exception as error:
                    print(f"장소 처리 중 오류: {error}")
                    continue

            save_keyword_results(all_keyword_rows)

            print(f"\n[4] 키워드 결과 저장 완료: {KEYWORD_RESULT_CSV}")

        finally:
            browser.close()


if __name__ == "__main__":
    main()