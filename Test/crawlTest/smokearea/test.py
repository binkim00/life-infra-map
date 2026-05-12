from playwright.sync_api import sync_playwright

START_URL = "https://smokingarea.site/"


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
                "supabase",
                "firebase",
                "areas",
                "markers",
                "places",
                "smoking",
                "locations",
                "_next",
                "assets",
            ]

            if any(t in content_type for t in targets) or any(t in url.lower() for t in targets):
                print("[응답]", response.status, content_type, url)

        page.on("response", handle_response)

        page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)

        print("현재 URL:", page.url)
        print("페이지 제목:", page.title())

        browser.close()


if __name__ == "__main__":
    main()