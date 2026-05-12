# pip install requests beautifulsoup4
import json
import re
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://smokearea.kr"
REGION_URL = "https://smokearea.kr/ko/region/busan-gangseo-gu"


def extract_coordinates_from_url(url: str):
    """
    카카오맵 또는 구글맵 URL에서 위도/경도를 추출합니다.
    """
    if not url:
        return None, None

    decoded_url = unquote(url)

    # Kakao: /link/map/장소명,35.1796,128.9382
    kakao_match = re.search(r"/link/map/.*?,([0-9.]+),([0-9.]+)", decoded_url)
    if kakao_match:
        return float(kakao_match.group(1)), float(kakao_match.group(2))

    # Google: maps?q=35.1796,128.9382
    google_match = re.search(r"[?&]q=([0-9.]+),([0-9.]+)", decoded_url)
    if google_match:
        return float(google_match.group(1)), float(google_match.group(2))

    return None, None


def parse_card(card):
    """
    목록 카드 1개를 Place 형태로 변환합니다.
    """
    facility_tag = card.select_one("span")
    name_tag = card.select_one("h3")
    desc_tag = card.select_one("p")

    detail_tag = card.select_one('a[href^="/ko/area/"]')
    kakao_tag = card.select_one('a[href*="map.kakao.com/link/map"]')
    google_tag = card.select_one('a[href*="google.com/maps"]')

    facility_type = facility_tag.get_text(strip=True) if facility_tag else ""
    name = name_tag.get_text(strip=True) if name_tag else ""
    location_detail = desc_tag.get_text(strip=True) if desc_tag else ""

    detail_url = urljoin(BASE_URL, detail_tag["href"]) if detail_tag else ""
    kakao_url = kakao_tag["href"] if kakao_tag else ""
    google_url = google_tag["href"] if google_tag else ""

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
        "source_type": "crawled",
        "source_name": "smokearea.kr",
    }


def find_cards(soup):
    """
    /ko/area/ 상세 링크를 기준으로 목록 카드를 찾습니다.
    """
    cards = []

    for detail_link in soup.select('a[href^="/ko/area/"]'):
        current = detail_link

        # 상위 div를 타고 올라가면서 카카오맵 링크가 포함된 카드 div를 찾음
        for _ in range(8):
            current = current.find_parent("div")
            if current is None:
                break

            if current.select_one('a[href*="map.kakao.com/link/map"]') and current.select_one("h3"):
                cards.append(current)
                break

    return cards


def remove_duplicates(places):
    seen = set()
    result = []

    for place in places:
        if not place["name"]:
            continue

        if place["latitude"] is None or place["longitude"] is None:
            continue

        key = (
            place["name"],
            round(place["latitude"], 6),
            round(place["longitude"], 6),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(place)

    return result


def main():
    headers = {
        "User-Agent": "Mozilla/5.0",
    }

    response = requests.get(REGION_URL, headers=headers, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    cards = find_cards(soup)
    print(f"찾은 카드 수: {len(cards)}")

    places = [parse_card(card) for card in cards]
    places = remove_duplicates(places)

    print(f"정리된 장소 수: {len(places)}")

    for place in places:
        print(place["name"], place["latitude"], place["longitude"])

    with open("smoking_places_busan_gangseo.json", "w", encoding="utf-8") as f:
        json.dump(places, f, ensure_ascii=False, indent=2)

    print("저장 완료: smoking_places_busan_gangseo.json")


if __name__ == "__main__":
    main()