import json
import re
import time
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://smokearea.kr"
START_URL = f"{BASE_URL}/ko"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"


HEADERS = {
    "User-Agent": "Mozilla/5.0",
}


def get_soup(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def extract_coordinates_from_url(url: str):
    if not url:
        return None, None

    decoded_url = unquote(url)

    kakao_match = re.search(r"/link/map/.*?,([0-9.-]+),([0-9.-]+)", decoded_url)
    if kakao_match:
        return float(kakao_match.group(1)), float(kakao_match.group(2))

    google_match = re.search(r"[?&]q=([0-9.-]+),([0-9.-]+)", decoded_url)
    if google_match:
        return float(google_match.group(1)), float(google_match.group(2))

    return None, None


def collect_region_urls_from_sitemap():
    region_urls = []

    try:
        response = requests.get(SITEMAP_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return []

    text = response.text

    matches = re.findall(r"https?://[^<\s]+/ko/region/[^<\s]+", text)
    for url in matches:
        region_urls.append(url.strip())

    return sorted(set(region_urls))


def collect_region_urls_from_home():
    soup = get_soup(START_URL)

    region_urls = []

    for a in soup.select('a[href*="/ko/region/"]'):
        href = a.get("href", "")
        region_urls.append(urljoin(BASE_URL, href))

    return sorted(set(region_urls))


def find_cards(soup):
    cards = []

    for detail_link in soup.select('a[href^="/ko/area/"], a[href*="/ko/area/"]'):
        current = detail_link

        for _ in range(10):
            current = current.find_parent("div")
            if current is None:
                break

            has_map_link = current.select_one('a[href*="map.kakao.com/link/map"], a[href*="google.com/maps"]')
            has_title = current.select_one("h3")

            if has_map_link and has_title:
                cards.append(current)
                break

    return cards


def parse_card(card, region_url=""):
    facility_tag = card.select_one("span")
    name_tag = card.select_one("h3")
    desc_tag = card.select_one("p")

    detail_tag = card.select_one('a[href^="/ko/area/"], a[href*="/ko/area/"]')
    kakao_tag = card.select_one('a[href*="map.kakao.com/link/map"]')
    google_tag = card.select_one('a[href*="google.com/maps"]')

    facility_type = facility_tag.get_text(strip=True) if facility_tag else ""
    name = name_tag.get_text(strip=True) if name_tag else ""
    location_detail = desc_tag.get_text(strip=True) if desc_tag else ""

    detail_url = urljoin(BASE_URL, detail_tag.get("href", "")) if detail_tag else ""
    kakao_url = kakao_tag.get("href", "") if kakao_tag else ""
    google_url = google_tag.get("href", "") if google_tag else ""

    latitude, longitude = extract_coordinates_from_url(kakao_url)

    if latitude is None or longitude is None:
        latitude, longitude = extract_coordinates_from_url(google_url)

    return {
        "name": name,
        "category": "smoking_area",
        "facility_type": facility_type,
        "address": "",
        "location_detail": location_detail,
        "latitude": latitude,
        "longitude": longitude,
        "detail_url": detail_url,
        "kakao_url": kakao_url,
        "google_url": google_url,
        "region_url": region_url,
        "source_type": "crawled",
        "source_name": "smokearea.kr",
    }


def parse_region_page(region_url):
    soup = get_soup(region_url)
    cards = find_cards(soup)

    places = []
    for card in cards:
        place = parse_card(card, region_url=region_url)
        places.append(place)

    return places


def remove_duplicates(places):
    seen = set()
    result = []

    for place in places:
        if not place.get("name"):
            continue

        if place.get("latitude") is None or place.get("longitude") is None:
            continue

        key = (
            place["name"].strip(),
            round(float(place["latitude"]), 6),
            round(float(place["longitude"]), 6),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(place)

    return result


def main():
    region_urls = collect_region_urls_from_sitemap()

    if not region_urls:
        region_urls = collect_region_urls_from_home()

    print(f"수집한 지역 URL 수: {len(region_urls)}")

    if not region_urls:
        print("지역 URL을 자동으로 찾지 못했습니다.")
        print("우선 REGION_URL을 직접 넣는 방식으로 테스트해야 합니다.")
        return

    all_places = []

    for index, region_url in enumerate(region_urls, start=1):
        print(f"[{index}/{len(region_urls)}] {region_url}")

        try:
            places = parse_region_page(region_url)
            print(f"  - 수집 후보: {len(places)}개")
            all_places.extend(places)
        except Exception as error:
            print(f"  - 실패: {error}")

        time.sleep(0.5)

    cleaned_places = remove_duplicates(all_places)

    print(f"전체 후보 수: {len(all_places)}")
    print(f"중복 제거 후: {len(cleaned_places)}")

    with open("smoking_places_all_raw.json", "w", encoding="utf-8") as f:
        json.dump(all_places, f, ensure_ascii=False, indent=2)

    with open("smoking_places_all_cleaned.json", "w", encoding="utf-8") as f:
        json.dump(cleaned_places, f, ensure_ascii=False, indent=2)

    print("저장 완료:")
    print("- smoking_places_all_raw.json")
    print("- smoking_places_all_cleaned.json")


if __name__ == "__main__":
    main()