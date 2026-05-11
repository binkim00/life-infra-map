import json
from playwright.sync_api import sync_playwright


START_URL = "https://smokearea.kr/ko"


def normalize_place(item):
    return {
        "external_id": item.get("id"),
        "slug": item.get("slug"),
        "name": item.get("name"),
        "category": "smoking_area",
        "address": item.get("road_address") or item.get("address") or "",
        "location_detail": item.get("address") or "",
        "latitude": float(item["latitude"]) if item.get("latitude") is not None else None,
        "longitude": float(item["longitude"]) if item.get("longitude") is not None else None,
        "region": item.get("region") or "",
        "region_slug": item.get("region_slug") or "",
        "parent_region": item.get("parent_region") or "",
        "parent_region_slug": item.get("parent_region_slug") or "",
        "indoor_outdoor": item.get("indoor_outdoor") or "",
        "facility_type": item.get("facility_type") or "",
        "manager": item.get("manager") or "",
        "is_operating": item.get("is_operating"),
        "source": item.get("source") or "",
        "last_updated": item.get("last_updated"),
        "photo_urls": item.get("photo_urls") or [],
        "source_type": "crawled_api",
        "source_name": "smokearea.kr_supabase",
    }


def main():
    captured_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        def handle_response(response):
            nonlocal captured_items

            url = response.url

            if "supabase.co/rest/v1/smoking_areas" not in url:
                return

            print("smoking_areas API 발견:")
            print(url)

            try:
                data = response.json()
            except Exception as error:
                print("JSON 파싱 실패:", error)
                return

            print("원본 데이터 수:", len(data))
            captured_items = data

        page.on("response", handle_response)

        page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        browser.close()

    if not captured_items:
        print("smoking_areas 데이터를 찾지 못했습니다.")
        return

    normalized = []

    for item in captured_items:
        place = normalize_place(item)

        if not place["name"]:
            continue
        if place["latitude"] is None or place["longitude"] is None:
            continue

        normalized.append(place)

    with open("smoking_areas_raw.json", "w", encoding="utf-8") as f:
        json.dump(captured_items, f, ensure_ascii=False, indent=2)

    with open("smoking_places_normalized.json", "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print("저장 완료")
    print("원본:", len(captured_items), "개")
    print("정규화:", len(normalized), "개")
    print("- smoking_areas_raw.json")
    print("- smoking_places_normalized.json")


if __name__ == "__main__":
    main()