import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]

# backend/.env 읽기
load_dotenv(BASE_DIR / "backend" / ".env")

SERVICE_KEY = os.getenv("TOUR_API_KEY")

if not SERVICE_KEY:
    print("TOUR_API_KEY가 설정되지 않았습니다.")
    print("backend/.env 파일에 TOUR_API_KEY=공공데이터_일반인증키 를 추가하세요.")
    exit()


OUTPUT_DIR = BASE_DIR / "ExData" / "JsonData" / "tourism"
OUTPUT_PATH = OUTPUT_DIR / "korea_tourist_spots.json"

BASE_URL = "https://apis.data.go.kr/B551011/KorService2/areaBasedList2"

all_items = []

page_no = 1
num_of_rows = 100

while True:
    params = {
        "MobileOS": "ETC",
        "MobileApp": "life-infra-map",
        "_type": "json",
        "numOfRows": num_of_rows,
        "pageNo": page_no,
        "contentTypeId": 12,
    }

    url = f"{BASE_URL}?serviceKey={SERVICE_KEY}"

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()
    body = data["response"]["body"]

    total_count = body["totalCount"]
    items = body["items"]

    if not items:
        break

    item_list = items["item"]

    if isinstance(item_list, dict):
        item_list = [item_list]

    all_items.extend(item_list)

    print(f"{page_no}페이지 수집 완료 / 현재 {len(all_items)}개 / 전체 {total_count}개")

    if len(all_items) >= total_count:
        break

    page_no += 1
    time.sleep(0.2)


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(all_items, f, ensure_ascii=False, indent=2)

print("전국 관광명소 수집 완료")
print(f"저장 위치: {OUTPUT_PATH}")
print(f"총 수집 개수: {len(all_items)}개")