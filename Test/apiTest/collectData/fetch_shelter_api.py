import os
import json
import time
import math
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[3]

API_KEY = os.getenv("SHELTER_API_KEY")

BASE_URL = "https://www.safetydata.go.kr/V2/api/DSSP-IF-10942"

OUTPUT_DIR = BASE_DIR / "ExData" / "JsonData" / "shelter"
RAW_OUTPUT_PATH = OUTPUT_DIR / "shelter_api_raw.json"
ITEMS_OUTPUT_PATH = OUTPUT_DIR / "shelter_api_items.json"
SUMMARY_OUTPUT_PATH = OUTPUT_DIR / "shelter_api_summary.json"

MAX_REQUEST_COUNT = 95

NUM_OF_ROWS_CANDIDATES = [
    50000,
    30000,
    20000,
    10000,
    5000,
    3000,
    1000,
    500,
    100,
]


class ApiResponseError(Exception):
    def __init__(self, result_code, result_msg, error_msg):
        self.result_code = str(result_code or "").strip()
        self.result_msg = str(result_msg or "").strip()
        self.error_msg = str(error_msg or "").strip()

        message = (
            f"API 오류 발생: "
            f"resultCode={self.result_code}, "
            f"resultMsg={self.result_msg}, "
            f"errorMsg={self.error_msg}"
        )

        super().__init__(message)


def mask_url(url):
    parts = urlsplit(url)
    query_items = []

    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() == "servicekey":
            query_items.append((key, "***"))
        else:
            query_items.append((key, value))

    masked_query = urlencode(query_items)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            masked_query,
            parts.fragment,
        )
    )


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_nested_value(data, keys):
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def check_api_error(data):
    if not isinstance(data, dict):
        return

    header = data.get("header")

    if not isinstance(header, dict):
        return

    result_code = str(header.get("resultCode", "")).strip()
    result_msg = str(header.get("resultMsg", "")).strip()
    error_msg = str(header.get("errorMsg", "")).strip()

    success_codes = {"", "0", "00", "0000", "NORMAL_CODE"}

    if result_code not in success_codes:
        raise ApiResponseError(
            result_code=result_code,
            result_msg=result_msg,
            error_msg=error_msg,
        )


def find_total_count(data):
    candidates = [
        ["totalCount"],
        ["total_count"],
        ["totalCnt"],
        ["body", "totalCount"],
        ["body", "total_count"],
        ["body", "totalCnt"],
        ["header", "totalCount"],
        ["header", "total_count"],
        ["header", "totalCnt"],
        ["response", "body", "totalCount"],
        ["response", "body", "totalCnt"],
        ["result", "totalCount"],
        ["result", "totalCnt"],
        ["data", "totalCount"],
        ["data", "totalCnt"],
    ]

    for keys in candidates:
        value = get_nested_value(data, keys)

        if value is None:
            continue

        try:
            return int(value)
        except (ValueError, TypeError):
            continue

    return None


def find_items(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    body = data.get("body")

    if isinstance(body, list):
        return body

    if isinstance(body, dict):
        body_candidates = [
            body.get("items"),
            body.get("item"),
            body.get("data"),
            body.get("list"),
            body.get("rows"),
        ]

        for value in body_candidates:
            if isinstance(value, list):
                return value

            if isinstance(value, dict):
                return [value]

    candidates = [
        ["items"],
        ["item"],
        ["data"],
        ["result"],
        ["list"],
        ["rows"],
        ["response", "body", "items"],
        ["response", "body", "items", "item"],
        ["response", "body", "item"],
        ["response", "body", "data"],
        ["response", "body", "list"],
    ]

    for keys in candidates:
        value = get_nested_value(data, keys)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            return [value]

    return []


def print_response_debug(data):
    if isinstance(data, dict):
        print("응답 최상위 키:", list(data.keys()))

        header = data.get("header")
        body = data.get("body")

        print("header 타입:", type(header).__name__)
        print("body 타입:", type(body).__name__)

        if isinstance(header, dict):
            print("header 내용:", json.dumps(header, ensure_ascii=False)[:1000])

        if isinstance(body, list):
            print("body 리스트 길이:", len(body))

            if body:
                first_item = body[0]

                if isinstance(first_item, dict):
                    print("body 첫 item 키:", list(first_item.keys()))
                    print("body 첫 item 미리보기:", json.dumps(first_item, ensure_ascii=False)[:1000])
                else:
                    print("body 첫 item 타입:", type(first_item).__name__)
                    print("body 첫 item 미리보기:", str(first_item)[:1000])

        elif isinstance(body, dict):
            print("body 키:", list(body.keys()))
            print("body 미리보기:", json.dumps(body, ensure_ascii=False)[:1000])

        else:
            print("body 미리보기:", str(body)[:1000])

    else:
        print("응답 타입:", type(data).__name__)
        print("응답 미리보기:", str(data)[:1000])


def request_page(page_no, num_of_rows):
    params = {
        "serviceKey": API_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "returnType": "json",
    }

    response = requests.get(BASE_URL, params=params, timeout=30)

    print(f"요청 URL: {mask_url(response.url)}")
    print(f"상태 코드: {response.status_code}")

    response.raise_for_status()

    text = response.text.strip()

    try:
        return response.json()
    except json.JSONDecodeError:
        print("JSON 파싱 실패. 응답 앞부분:")
        print(text[:1000])
        raise


def test_num_of_rows(num_of_rows):
    print()
    print(f"numOfRows 테스트: {num_of_rows}")

    data = request_page(page_no=1, num_of_rows=num_of_rows)

    print_response_debug(data)

    check_api_error(data)

    total_count = find_total_count(data)
    items = find_items(data)

    print(f"totalCount: {total_count}")
    print(f"items 수: {len(items)}")

    return {
        "num_of_rows": num_of_rows,
        "total_count": total_count,
        "item_count": len(items),
        "data": data,
    }


def choose_num_of_rows():
    test_results = []

    for num_of_rows in NUM_OF_ROWS_CANDIDATES:
        try:
            result = test_num_of_rows(num_of_rows)

            test_results.append(
                {
                    "requested_num_of_rows": result["num_of_rows"],
                    "total_count": result["total_count"],
                    "actual_item_count": result["item_count"],
                }
            )

            if result["item_count"] > 0:
                return (
                    result["num_of_rows"],
                    result["total_count"],
                    result["item_count"],
                    test_results,
                )

        except ApiResponseError:
            raise

        except Exception as e:
            print(f"numOfRows={num_of_rows} 실패: {e}")

        time.sleep(0.2)

    return None, None, 0, test_results


def make_item_key(item):
    if isinstance(item, dict):
        return (
            item.get("RSTR_FCLTY_NO"),
            item.get("YEAR"),
            item.get("RSTR_NM"),
            item.get("LA"),
            item.get("LO"),
        )

    return str(item)


def fetch_all(requested_num_of_rows, total_count, actual_page_size):
    all_raw_pages = []
    all_items = []
    seen_item_keys = set()

    if total_count is None:
        page_count = MAX_REQUEST_COUNT
    else:
        page_count = math.ceil(total_count / actual_page_size)

    if page_count > MAX_REQUEST_COUNT:
        raise ValueError(
            f"요청 필요 횟수 {page_count}회입니다. "
            f"일일 제한을 고려한 최대 요청 수 {MAX_REQUEST_COUNT}회를 넘어서 전체 수집을 중단합니다."
        )

    print()
    print("전체 수집 시작")
    print(f"totalCount: {total_count}")
    print(f"요청 numOfRows: {requested_num_of_rows}")
    print(f"실제 페이지당 반환 수: {actual_page_size}")
    print(f"page_count: {page_count}")

    for page_no in range(1, page_count + 1):
        print()
        print(f"[{page_no}/{page_count}] 페이지 수집")

        data = request_page(page_no=page_no, num_of_rows=requested_num_of_rows)

        check_api_error(data)

        items = find_items(data)

        print(f"수집 item 수: {len(items)}")

        if not items:
            print("item이 없어서 수집 종료")
            break

        all_raw_pages.append(data)

        new_count = 0

        for item in items:
            item_key = make_item_key(item)

            if item_key in seen_item_keys:
                continue

            seen_item_keys.add(item_key)
            all_items.append(item)
            new_count += 1

        print(f"신규 item 수: {new_count}")
        print(f"누적 item 수: {len(all_items)}")

        if total_count is None and len(items) < actual_page_size:
            print("마지막 페이지로 판단되어 수집 종료")
            break

        time.sleep(0.2)

    return all_raw_pages, all_items


def save_failure_summary(reason, extra=None):
    summary = {
        "status": "failed",
        "reason": reason,
        "base_url": BASE_URL,
        "raw_output_path": str(RAW_OUTPUT_PATH),
        "items_output_path": str(ITEMS_OUTPUT_PATH),
    }

    if extra:
        summary.update(extra)

    save_json(SUMMARY_OUTPUT_PATH, summary)


def main():
    if not API_KEY:
        print("SHELTER_API_KEY가 .env에 없습니다.")
        return

    try:
        requested_num_of_rows, total_count, actual_page_size, test_results = choose_num_of_rows()

        if requested_num_of_rows is None:
            print()
            print("사용 가능한 numOfRows를 찾지 못했습니다.")

            save_failure_summary(
                reason="no_available_num_of_rows",
                extra={
                    "test_results": test_results,
                },
            )
            return

        print()
        print("선택된 요청 numOfRows:", requested_num_of_rows)
        print("실제 페이지당 반환 수:", actual_page_size)
        print("totalCount:", total_count)

        raw_pages, items = fetch_all(
            requested_num_of_rows=requested_num_of_rows,
            total_count=total_count,
            actual_page_size=actual_page_size,
        )

        summary = {
            "status": "success",
            "base_url": BASE_URL,
            "requested_num_of_rows": requested_num_of_rows,
            "actual_page_size": actual_page_size,
            "total_count": total_count,
            "raw_page_count": len(raw_pages),
            "item_count": len(items),
            "test_results": test_results,
            "raw_output_path": str(RAW_OUTPUT_PATH),
            "items_output_path": str(ITEMS_OUTPUT_PATH),
            "note": (
                "API에 큰 numOfRows를 요청해도 실제 body는 1000건 단위로 반환됩니다. "
                "따라서 totalCount / 실제 반환 수 기준으로 페이지 수를 계산합니다."
            ),
        }

        save_json(RAW_OUTPUT_PATH, raw_pages)
        save_json(ITEMS_OUTPUT_PATH, items)
        save_json(SUMMARY_OUTPUT_PATH, summary)

        print()
        print("쉼터 API 수집 완료")
        print(f"raw 저장: {RAW_OUTPUT_PATH}")
        print(f"items 저장: {ITEMS_OUTPUT_PATH}")
        print(f"summary 저장: {SUMMARY_OUTPUT_PATH}")
        print(f"최종 item 수: {len(items)}")

    except ApiResponseError as e:
        print()
        print("API 오류로 수집을 중단했습니다.")
        print(e)

        save_failure_summary(
            reason="api_response_error",
            extra={
                "result_code": e.result_code,
                "result_msg": e.result_msg,
                "error_msg": e.error_msg,
            },
        )

    except Exception as e:
        print()
        print("예상하지 못한 오류로 수집을 중단했습니다.")
        print(e)

        save_failure_summary(
            reason="unexpected_error",
            extra={
                "error": str(e),
            },
        )


if __name__ == "__main__":
    main()