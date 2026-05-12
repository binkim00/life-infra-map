import json
from playwright.sync_api import sync_playwright


START_URL = "https://smokingarea.site/"


def normalize_report(item):
    """
    실제 필드명은 저장된 raw JSON을 보고 한 번 더 맞추면 됩니다.
    일단 흔히 쓰는 필드명 후보를 넓게 잡아둡니다.
    """
    lat = (
        item.get("latitude")
        or item.get("lat")
        or item.get("y")
    )
    lng = (
        item.get("longitude")
        or item.get("lng")
        or item.get("x")
    )

    name = (
        item.get("place_name")
        or item.get("name")
        or item.get("title")
        or item.get("location_name")
        or "흡연구역"
    )

    address = (
        item.get("address")
        or item.get("road_address")
        or item.get("location")
        or item.get("description")
        or ""
    )

    return {
        "external_id": item.get("id"),
        "name": name,
        "category": "smoking_area",
        "address": address,
        "location_detail": item.get("description") or item.get("memo") or "",
        "latitude": float(lat) if lat is not None else None,
        "longitude": float(lng) if lng is not None else None,
        "report_type": item.get("report_type"),
        "status": item.get("status"),
        "source_type": "crawled_api",
        "source_name": "smokingarea.site_supabase",
        "raw": item,
    }


def main():
    captured_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        def handle_response(response):
            nonlocal captured_items

            url = response.url

            if "supabase.co/rest/v1/reports" not in url:
                return

            print("reports API 발견:")
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
        print("reports 데이터를 찾지 못했습니다.")
        return

    normalized = []

    for item in captured_items:
        place = normalize_report(item)

        if place["latitude"] is None or place["longitude"] is None:
            continue

        normalized.append(place)

    with open("smokingarea_site_reports_raw.json", "w", encoding="utf-8") as f:
        json.dump(captured_items, f, ensure_ascii=False, indent=2)

    with open("smokingarea_site_reports_normalized.json", "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print("저장 완료")
    print("원본:", len(captured_items), "개")
    print("정규화:", len(normalized), "개")
    print("- smokingarea_site_reports_raw.json")
    print("- smokingarea_site_reports_normalized.json")


if __name__ == "__main__":
    main()