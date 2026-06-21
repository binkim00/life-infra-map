import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path.cwd()

INPUT_PATH = PROJECT_ROOT / "backend/recommendations/fixtures/places/smoking_places_merged_deduplicated.json"
BACKUP_PATH = PROJECT_ROOT / "backend/recommendations/fixtures/places/smoking_places_merged_deduplicated.before_geocode.json"
PREVIEW_PATH = PROJECT_ROOT / "backend/recommendations/fixtures/places/smoking_places_merged_deduplicated.geocoded_preview.json"
SUCCESS_PATH = PROJECT_ROOT / "backend/recommendations/fixtures/places/smoking_geocode_success.json"
FAILED_PATH = PROJECT_ROOT / "backend/recommendations/fixtures/places/smoking_geocode_failed.json"

ENV_PATHS = [
    PROJECT_ROOT / "Test/apiTest/mapCheck/.env",
    PROJECT_ROOT / "Test/apiTest/collectData/.env",
    PROJECT_ROOT / ".env",
]


def load_env_value(key_names):
    for env_path in ENV_PATHS:
        if not env_path.exists():
            continue

        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key in key_names:
                return value

    return ""


KAKAO_REST_API_KEY = load_env_value([
    "KAKAO_REST_API_KEY",
    "KAKAO_REST_KEY",
    "KAKAO_API_KEY",
    "REST_API_KEY",
])


def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, dict):
        for key in ["ko", "address_name", "name", "title", "value"]:
            if value.get(key):
                return clean_text(value.get(key))
        return ""

    value = str(value).strip()

    if value.lower() in ["nan", "none", "null"]:
        return ""

    return value


def to_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except:
        return None


def has_valid_coord(item):
    lat = to_float(item.get("lat"))
    lng = to_float(item.get("lng"))

    if lat is None or lng is None:
        return False

    return -90 <= lat <= 90 and -180 <= lng <= 180


def request_kakao(url, params):
    query = urllib.parse.urlencode(params)
    request_url = f"{url}?{query}"

    req = urllib.request.Request(request_url)
    req.add_header("Authorization", f"KakaoAK {KAKAO_REST_API_KEY}")

    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def kakao_address_search(query):
    data = request_kakao(
        "https://dapi.kakao.com/v2/local/search/address.json",
        {"query": query},
    )
    docs = data.get("documents", [])
    return docs[0] if docs else None


def kakao_keyword_search(query):
    data = request_kakao(
        "https://dapi.kakao.com/v2/local/search/keyword.json",
        {"query": query, "size": 1},
    )
    docs = data.get("documents", [])
    return docs[0] if docs else None


def build_queries(item):
    name = clean_text(item.get("name"))
    address = clean_text(item.get("address"))
    detail_location = clean_text(item.get("detail_location"))

    raw = item.get("raw") or {}
    raw_address = ""
    raw_detail = ""

    if isinstance(raw, dict):
        raw_address = clean_text(raw.get("address"))
        raw_detail = clean_text(raw.get("location_detail"))

    queries = []

    for q in [
        address,
        detail_location,
        raw_address,
        raw_detail,
        f"{address} {name}",
        f"{detail_location} {name}",
        name,
    ]:
        q = clean_text(q)
        if q and q not in queries:
            queries.append(q)

    return queries


def apply_geocode(item, doc, method, query):
    lat = to_float(doc.get("y"))
    lng = to_float(doc.get("x"))

    if lat is None or lng is None:
        return False

    item["lat"] = lat
    item["lng"] = lng

    if not clean_text(item.get("address")):
        item["address"] = clean_text(doc.get("address_name"))

    if not clean_text(item.get("detail_location")):
        item["detail_location"] = clean_text(doc.get("address_name"))

    item["data_quality_status"] = "needs_review"
    item["data_quality_score"] = min(int(item.get("data_quality_score") or 50), 60)

    warning_tags = item.get("warning_tags") or []
    if "좌표 보정 필요" not in warning_tags:
        warning_tags.append("좌표 보정 필요")
    item["warning_tags"] = warning_tags

    raw = item.get("raw")
    if not isinstance(raw, dict):
        raw = {}

    raw["geocode_result"] = {
        "provider": "kakao",
        "method": method,
        "query": query,
        "lat": lat,
        "lng": lng,
        "address_name": clean_text(doc.get("address_name")),
        "place_name": clean_text(doc.get("place_name")),
        "status": "needs_review",
    }

    item["raw"] = raw

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="원본 fixture 파일에 보정 결과를 반영합니다.")
    parser.add_argument("--sleep", type=float, default=0.15, help="카카오 API 요청 간 대기 시간")
    parser.add_argument("--limit", type=int, default=None, help="테스트용 처리 개수 제한")
    args = parser.parse_args()

    if not KAKAO_REST_API_KEY:
        raise SystemExit("카카오 REST API 키를 찾지 못했습니다. Test/apiTest/mapCheck/.env 확인하세요.")

    items = json.load(open(INPUT_PATH, encoding="utf-8"))

    targets = [item for item in items if item.get("lat") is None or item.get("lng") is None]

    if args.limit:
        targets = targets[:args.limit]

    success = []
    failed = []

    print("좌표 보정 대상:", len(targets))

    for idx, item in enumerate(targets, start=1):
        queries = build_queries(item)

        matched = False
        last_error = ""

        for query in queries:
            try:
                doc = kakao_address_search(query)
                time.sleep(args.sleep)

                if doc and apply_geocode(item, doc, "address", query):
                    success.append(item)
                    matched = True
                    break

                doc = kakao_keyword_search(query)
                time.sleep(args.sleep)

                if doc and apply_geocode(item, doc, "keyword", query):
                    success.append(item)
                    matched = True
                    break

            except Exception as e:
                last_error = str(e)
                time.sleep(args.sleep)

        if not matched:
            copied = dict(item)
            copied["geocode_failed_reason"] = last_error or "검색 결과 없음"
            copied["geocode_queries"] = queries
            failed.append(copied)

        if idx % 50 == 0:
            print(f"진행: {idx}/{len(targets)} | 성공 {len(success)} | 실패 {len(failed)}")

    with open(PREVIEW_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    with open(SUCCESS_PATH, "w", encoding="utf-8") as f:
        json.dump(success, f, ensure_ascii=False, indent=2)

    with open(FAILED_PATH, "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)

    print()
    print("보정 성공:", len(success))
    print("보정 실패:", len(failed))
    print("미리보기 저장:", PREVIEW_PATH)
    print("성공 목록:", SUCCESS_PATH)
    print("실패 목록:", FAILED_PATH)

    if args.apply:
        if not BACKUP_PATH.exists():
            with open(BACKUP_PATH, "w", encoding="utf-8") as f:
                json.dump(json.load(open(INPUT_PATH, encoding="utf-8")), f, ensure_ascii=False, indent=2)

        with open(INPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        print("원본 반영 완료:", INPUT_PATH)
        print("백업 저장:", BACKUP_PATH)
    else:
        print()
        print("아직 원본에는 반영하지 않았습니다.")
        print("결과 확인 후 --apply 옵션으로 다시 실행하세요.")


if __name__ == "__main__":
    main()
