import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


# 프로젝트 루트 경로
BASE_DIR = Path(__file__).resolve().parents[2]

# backend/.env 읽기
load_dotenv(BASE_DIR / "backend" / ".env")

SERVICE_KEY = os.getenv("BEACH_API_KEY")

if not SERVICE_KEY:
    print("BEACH_API_KEY가 설정되지 않았습니다.")
    print("backend/.env 파일에 BEACH_API_KEY=해수욕장_API_일반인증키 를 추가하세요.")
    exit()


BASE_URL = "https://apis.data.go.kr/1192000/service/OceansBeachInfoService1/getOceansBeachInfo1"

OUTPUT_DIR = BASE_DIR / "ExData" / "JsonData" / "beach"
OUTPUT_PATH = OUTPUT_DIR / "beaches_korea.json"

# 해수욕장이 있는 주요 시도명
SIDO_NAMES = [
    "인천",
    "울산",
    "부산",
    "경기",
    "강원",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
]

all_items = []
seen_keys = set()

for sido_name in SIDO_NAMES:
    print("=" * 60)
    print(f"{sido_name} 해수욕장 수집 시작")

    page_no = 1
    num_of_rows = 100

    while True:
        params = {
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "SIDO_NM": sido_name,
            "resultType": "json",
        }

        # 인증키 인코딩 문제를 줄이려고 ServiceKey는 URL에 직접 붙임
        url = f"{BASE_URL}?ServiceKey={SERVICE_KEY}"

        response = requests.get(url, params=params)

        if response.status_code != 200:
            print("요청 실패")
            print("상태 코드:", response.status_code)
            print("요청 URL:", response.url.split("ServiceKey=")[0] + "ServiceKey=***")
            print("응답 내용:")
            print(response.text[:1000])
            exit()

        data = response.json()

        if "getOceansBeachInfo" not in data:
            print("예상과 다른 응답입니다.")
            print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
            exit()

        beach_info = data["getOceansBeachInfo"]

        header = beach_info.get("header", {})
        if header.get("code") != "00":
            print("API 응답 오류")
            print("code:", header.get("code"))
            print("message:", header.get("message"))
            exit()

        item_list = beach_info.get("item", [])

        if isinstance(item_list, dict):
            item_list = [item_list]

        # 이 API는 응답에 totalCount가 없을 수 있어서, 받은 개수 기준으로 종료 처리
        total_count = len(item_list)

        if isinstance(item_list, dict):
            item_list = [item_list]

        if not item_list:
            break

        for item in item_list:
            key = (
                item.get("sidoNm"),
                item.get("gugunNm"),
                item.get("staNm"),
                item.get("lat"),
                item.get("lon"),
            )

            if key in seen_keys:
                continue

            seen_keys.add(key)
            all_items.append(item)

        print(
            f"{sido_name} {page_no}페이지 수집 완료 "
            f"/ 현재 전체 {len(all_items)}개 / {sido_name} 총 {total_count}개"
        )

        if len(item_list) < num_of_rows:
            break

        page_no += 1
        time.sleep(0.2)


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(all_items, f, ensure_ascii=False, indent=2)

print("=" * 60)
print("전국 해수욕장 데이터 수집 완료")
print(f"저장 위치: {OUTPUT_PATH}")
print(f"총 수집 개수: {len(all_items)}개")