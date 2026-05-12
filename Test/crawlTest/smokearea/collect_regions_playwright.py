# pip install playwright beautifulsoup4
# playwright install chromium
from playwright.sync_api import sync_playwright

START_URL = "https://smokearea.kr/ko"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        def handle_response(response):
            url = response.url
            content_type = response.headers.get("content-type", "")

            targets = [
                "application/json",
                "text/json",
                "/api/",
                "_next",
                "region",
                "area",
                "smoking",
                "map",
            ]

            if any(t in content_type for t in targets) or any(t in url for t in targets):
                print("[응답]", response.status, content_type, url)

        page.on("response", handle_response)

        page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        page.get_by_text("지역별").click(timeout=5000)
        page.wait_for_timeout(1000)

        page.get_by_text("부산", exact=True).click(timeout=5000)
        page.wait_for_timeout(1000)

        page.get_by_text("부산 강서구", exact=True).click(timeout=5000)
        page.wait_for_timeout(5000)

        print("최종 URL:", page.url)

        browser.close()


if __name__ == "__main__":
    main()