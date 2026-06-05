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


BASE_URL = "https://apis.data.go.kr/B551011/KorService2/areaBasedList2"

OUTPUT_DIR = BASE_DIR / "ExData" / "JsonData" / "tourism"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 음식점 39 제외
CONTENT_TYPES = {
    12: "tourist_spot",      # 관광지
    14: "culture",          # 문화시설
    15: "festival_event",   # 행사/공연/축제
    25: "travel_course",    # 여행코스
    28: "leports",          # 레포츠
    32: "accommodation",    # 숙박
    38: "shopping",         # 쇼핑
}

all_items = []

for content_type_id, type_name in CONTENT_TYPES.items():
    print("=" * 60)
    print(f"{content_type_id} / {type_name} 수집 시작")

    type_items = []
    page_no = 1
    num_of_rows = 100

    while True:
        params = {
            "MobileOS": "ETC",
            "MobileApp": "life-infra-map",
            "_type": "json",
            "numOfRows": num_of_rows,
            "pageNo": page_no,
            "contentTypeId": content_type_id,
        }

        # serviceKey는 URL에 직접 붙여 인코딩 문제를 줄임
        url = f"{BASE_URL}?serviceKey={SERVICE_KEY}"

        response = requests.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        body = data["response"]["body"]

        total_count = body.get("totalCount", 0)
        items = body.get("items")

        if not items:
            break

        item_list = items.get("item", [])

        if isinstance(item_list, dict):
            item_list = [item_list]

        for item in item_list:
            item["contentTypeName"] = type_name

        type_items.extend(item_list)
        all_items.extend(item_list)

        print(
            f"{type_name} {page_no}페이지 수집 완료 "
            f"/ 현재 {len(type_items)}개 / 전체 {total_count}개"
        )

        if len(type_items) >= total_count:
            break

        page_no += 1
        time.sleep(0.2)

    # 타입별 개별 저장
    type_output_path = OUTPUT_DIR / f"{type_name}_korea.json"

    with open(type_output_path, "w", encoding="utf-8") as f:
        json.dump(type_items, f, ensure_ascii=False, indent=2)

    print(f"{type_name} 저장 완료: {type_output_path}")
    print(f"{type_name} 수집 개수: {len(type_items)}개")


# 전체 통합 파일 저장
all_output_path = OUTPUT_DIR / "tourism_all_except_food_korea.json"

with open(all_output_path, "w", encoding="utf-8") as f:
    json.dump(all_items, f, ensure_ascii=False, indent=2)

print("=" * 60)
print("음식점을 제외한 관광 데이터 전체 수집 완료")
print(f"통합 저장 위치: {all_output_path}")
print(f"총 수집 개수: {len(all_items)}개")