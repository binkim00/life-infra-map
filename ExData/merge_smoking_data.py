import csv
import json
import re
from difflib import SequenceMatcher
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CSV_DIR = BASE_DIR / "CSVData" / "smokearea"
JSON_DIR = BASE_DIR / "JsonData"

OUTPUT_PATH = JSON_DIR / "smoking_places_merged_normalized.json"
DUPLICATE_OUTPUT_PATH = JSON_DIR / "smoking_places_duplicate_candidates.json"
DEDUPLICATED_OUTPUT_PATH = JSON_DIR / "smoking_places_merged_deduplicated.json"
REMOVED_DUPLICATES_OUTPUT_PATH = JSON_DIR / "smoking_places_removed_duplicates.json"

EXCLUDED_FILES = {
    "서울특별시 강서구_흡연정보_20190812..csv",
}


def clean(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in ["nan", "none", "null"]:
        return ""

    return value


def get_ko(value):
    if isinstance(value, dict):
        return clean(value.get("ko") or value.get("en") or "")

    return clean(value)


def to_float(value):
    value = clean(value)

    if not value:
        return None

    try:
        return float(value)
    except ValueError:
        return None


def get_first(row, keys):
    for key in keys:
        if key in row:
            value = clean(row.get(key))
            if value:
                return value

    return ""


def get_date_from_filename(filename):
    match = re.search(r"(20\d{6})", filename)

    if not match:
        return None

    value = match.group(1)
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def build_quality(lat, lng, address, detail_location):
    warning_tags = []

    if lat is not None and lng is not None:
        status = "usable"
        score = 80
    else:
        status = "candidate"
        score = 50
        warning_tags.append("좌표 확인 필요")

    if not address and not detail_location:
        status = "needs_review"
        score = 30
        warning_tags.append("주소 확인 필요")

    return status, score, warning_tags


def normalize_common(
    external_id,
    name,
    address,
    detail_location,
    lat,
    lng,
    source,
    source_name,
    source_updated_at=None,
    facility_type="",
    raw=None,
):
    name = get_ko(name)
    address = get_ko(address)
    detail_location = get_ko(detail_location)
    facility_type = get_ko(facility_type)

    if not name:
        name = detail_location or address or "흡연구역"

    if not address:
        address = detail_location

    if not detail_location:
        detail_location = address

    status, score, warning_tags = build_quality(
        lat,
        lng,
        address,
        detail_location,
    )

    candidate_tags = []

    if facility_type:
        candidate_tags.append(facility_type)

    return {
        "external_id": clean(external_id),
        "name": name,
        "category": "smoking_area",
        "address": address,
        "detail_location": detail_location,
        "lat": lat,
        "lng": lng,
        "source": source,
        "source_name": source_name,
        "source_updated_at": source_updated_at,
        "data_quality_status": status,
        "data_quality_score": score,
        "default_tags": ["흡연구역"],
        "candidate_tags": candidate_tags,
        "warning_tags": warning_tags,
        "raw": raw or {},
    }


def normalize_smoking_places_normalized(path):
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    results = []

    for index, item in enumerate(data, start=1):
        normalized = normalize_common(
            external_id=item.get("external_id") or f"{path.stem}_{index}",
            name=item.get("name"),
            address=item.get("address"),
            detail_location=item.get("location_detail"),
            lat=to_float(item.get("latitude")),
            lng=to_float(item.get("longitude")),
            source="smokearea_kr_supabase",
            source_name=item.get("source_name") or path.stem,
            source_updated_at=item.get("last_updated"),
            facility_type=item.get("facility_type") or item.get("indoor_outdoor"),
            raw=item,
        )

        results.append(normalized)

    return results


def normalize_busan_gangseo(path):
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    results = []

    for index, item in enumerate(data, start=1):
        normalized = normalize_common(
            external_id=item.get("detail_url") or f"{path.stem}_{index}",
            name=item.get("name"),
            address=item.get("address"),
            detail_location=item.get("location_detail"),
            lat=to_float(item.get("latitude")),
            lng=to_float(item.get("longitude")),
            source="smokearea_kr_busan_gangseo",
            source_name=item.get("source_name") or path.stem,
            source_updated_at=None,
            facility_type=item.get("facility_type"),
            raw=item,
        )

        results.append(normalized)

    return results


def normalize_site_reports(path):
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    results = []

    for index, item in enumerate(data, start=1):
        raw = item.get("raw") or {}

        normalized = normalize_common(
            external_id=item.get("external_id") or f"{path.stem}_{index}",
            name=item.get("name"),
            address=item.get("address"),
            detail_location=item.get("location_detail"),
            lat=to_float(item.get("latitude")),
            lng=to_float(item.get("longitude")),
            source="smokingarea_site_reports",
            source_name=item.get("source_name") or path.stem,
            source_updated_at=raw.get("source_updated_at"),
            facility_type=raw.get("type"),
            raw=item,
        )

        status = clean(item.get("status"))
        report_type = clean(item.get("report_type"))

        if status:
            normalized["candidate_tags"].append(f"상태:{status}")

        if report_type:
            normalized["candidate_tags"].append(f"제보유형:{report_type}")

        results.append(normalized)

    return results


def read_csv_with_fallback(path):
    encodings = ["utf-8-sig", "cp949", "euc-kr"]

    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding, newline="") as file:
                return list(csv.DictReader(file))
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "unknown",
        b"",
        0,
        1,
        f"{path.name} 파일 인코딩을 읽지 못했습니다.",
    )


def normalize_csv(path):
    rows = read_csv_with_fallback(path)
    results = []

    for index, row in enumerate(rows, start=1):
        name = get_first(row, [
            "시설명",
            "시설명(업소)",
            "건물명",
            "흡연구역명",
            "흡연시설명",
            "시설 구분",
            "시설구분",
            "구분",
            "명칭",
            "상호명",
        ])

        address = get_first(row, [
            "주소",
            "도로명주소",
            "소재지도로명주소",
            "설치도로명주소",
            "지번주소",
            "소재지지번주소",
            "설치 주소",
            "설치주소",
            "위치",
            "설치 위치",
            "설치위치",
            "서울특별시 용산구 설치 위치",
        ])

        detail_location = get_first(row, [
            "상세위치",
            "설치위치 상세",
            "흡연구역범위상세",
            "설치 위치",
            "설치위치",
            "위치",
            "서울특별시 용산구 설치 위치",
            "주소",
            "비고",
        ])

        lat = to_float(get_first(row, [
            "위도",
            "latitude",
            "lat",
            "Y좌표",
            "y",
        ]))

        lng = to_float(get_first(row, [
            "경도",
            "longitude",
            "lng",
            "X좌표",
            "x",
        ]))

        facility_type = get_first(row, [
            "시설형태",
            "시설유형",
            "흡연실 형태",
            "흡연실여부",
            "실내외구분",
            "실내실외",
            "구분",
            "type",
        ])

        manager = get_first(row, [
            "관리기관",
            "관리기관명",
            "관리부서",
            "설치기관",
            "설치 주체",
            "설치주체",
            "운영관리",
        ])

        source_updated_at = (
            get_first(row, ["데이터기준일자", "기준일자", "기준일"])
            or get_date_from_filename(path.name)
        )

        external_id = f"{path.stem}_{index}"

        normalized = normalize_common(
            external_id=external_id,
            name=name,
            address=address,
            detail_location=detail_location,
            lat=lat,
            lng=lng,
            source=path.stem,
            source_name=path.stem,
            source_updated_at=source_updated_at,
            facility_type=facility_type,
            raw=row,
        )

        if manager:
            normalized["candidate_tags"].append(f"관리:{clean(manager)}")

        results.append(normalized)

    return results


def merge_and_deduplicate_by_source_id(items):
    merged = []
    seen = set()

    for item in items:
        key = (item["source"], item["external_id"])

        if key in seen:
            continue

        seen.add(key)
        merged.append(item)

    return merged


def get_similarity(a, b):
    a = clean(a)
    b = clean(b)

    if not a or not b:
        return 0

    return SequenceMatcher(None, a, b).ratio()


def calculate_distance_m(lat1, lng1, lat2, lng2):
    if None in [lat1, lng1, lat2, lng2]:
        return None

    earth_radius_m = 6371000

    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)

    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(d_lng / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return earth_radius_m * c


def is_duplicate_candidate(item1, item2):
    if item1["source"] == item2["source"]:
        return False

    distance = calculate_distance_m(
        item1.get("lat"),
        item1.get("lng"),
        item2.get("lat"),
        item2.get("lng"),
    )

    if distance is None:
        return False

    if distance > 30:
        return False

    name_similarity = get_similarity(item1.get("name"), item2.get("name"))
    address_similarity = get_similarity(item1.get("address"), item2.get("address"))
    detail_similarity = get_similarity(
        item1.get("detail_location"),
        item2.get("detail_location"),
    )

    max_similarity = max(
        name_similarity,
        address_similarity,
        detail_similarity,
    )

    return max_similarity >= 0.6


def find_duplicate_candidates(items):
    usable_items = [
        item for item in items
        if item.get("lat") is not None and item.get("lng") is not None
    ]

    duplicate_candidates = []

    for i in range(len(usable_items)):
        for j in range(i + 1, len(usable_items)):
            item1 = usable_items[i]
            item2 = usable_items[j]

            if not is_duplicate_candidate(item1, item2):
                continue

            distance = calculate_distance_m(
                item1.get("lat"),
                item1.get("lng"),
                item2.get("lat"),
                item2.get("lng"),
            )

            duplicate_candidates.append({
                "distance_m": round(distance, 2),
                "similarity": {
                    "name": round(
                        get_similarity(item1.get("name"), item2.get("name")),
                        3,
                    ),
                    "address": round(
                        get_similarity(item1.get("address"), item2.get("address")),
                        3,
                    ),
                    "detail_location": round(
                        get_similarity(
                            item1.get("detail_location"),
                            item2.get("detail_location"),
                        ),
                        3,
                    ),
                },
                "item1": {
                    "external_id": item1.get("external_id"),
                    "name": item1.get("name"),
                    "address": item1.get("address"),
                    "detail_location": item1.get("detail_location"),
                    "lat": item1.get("lat"),
                    "lng": item1.get("lng"),
                    "source": item1.get("source"),
                },
                "item2": {
                    "external_id": item2.get("external_id"),
                    "name": item2.get("name"),
                    "address": item2.get("address"),
                    "detail_location": item2.get("detail_location"),
                    "lat": item2.get("lat"),
                    "lng": item2.get("lng"),
                    "source": item2.get("source"),
                },
            })

    return duplicate_candidates


def is_generic_detail(value):
    value = clean(value)

    generic_keywords = [
        "지역 페이지의",
        "실외 흡연구역 항목",
        "흡연부스 항목",
    ]

    return any(keyword in value for keyword in generic_keywords)


def is_safe_duplicate(candidate):
    distance = candidate.get("distance_m")
    similarity = candidate.get("similarity", {})

    name_similarity = similarity.get("name", 0)
    address_similarity = similarity.get("address", 0)
    detail_similarity = similarity.get("detail_location", 0)

    item1 = candidate.get("item1", {})
    item2 = candidate.get("item2", {})

    detail1 = clean(item1.get("detail_location"))
    detail2 = clean(item2.get("detail_location"))

    if distance is None:
        return False

    # 완전 같은 좌표 수준만 자동 제거 대상으로 봅니다.
    if distance > 1:
        return False

    # 이름, 주소, 상세위치가 거의 같은 경우
    if (
        name_similarity >= 0.95
        and address_similarity >= 0.95
        and detail_similarity >= 0.95
    ):
        return True

    # 주소가 같고 이름도 충분히 비슷한데,
    # 한쪽 상세 설명이 "지역 페이지의 ..." 같은 일반 설명이면 중복으로 봅니다.
    if (
        address_similarity >= 0.95
        and name_similarity >= 0.6
        and (is_generic_detail(detail1) or is_generic_detail(detail2))
    ):
        return True

    return False


def choose_duplicate_to_remove(candidate):
    item1 = candidate["item1"]
    item2 = candidate["item2"]

    source1 = item1.get("source")
    source2 = item2.get("source")

    detail1 = clean(item1.get("detail_location"))
    detail2 = clean(item2.get("detail_location"))

    # 일반 설명인 쪽을 우선 제거합니다.
    if is_generic_detail(detail1) and not is_generic_detail(detail2):
        return item1

    if is_generic_detail(detail2) and not is_generic_detail(detail1):
        return item2

    # smokingarea_site_reports는 다른 출처와 완전히 겹치면 후순위로 제거합니다.
    if source1 == "smokingarea_site_reports" and source2 != "smokingarea_site_reports":
        return item1

    if source2 == "smokingarea_site_reports" and source1 != "smokingarea_site_reports":
        return item2

    # 둘 다 비슷하면 뒤쪽 항목을 제거합니다.
    return item2


def make_deduplicated_items(items, duplicate_candidates):
    remove_keys = set()
    removed_duplicates = []

    for candidate in duplicate_candidates:
        if not is_safe_duplicate(candidate):
            continue

        remove_item = choose_duplicate_to_remove(candidate)

        key = (
            remove_item.get("source"),
            remove_item.get("external_id"),
        )

        if key in remove_keys:
            continue

        remove_keys.add(key)

        removed_duplicates.append({
            "remove_key": {
                "source": remove_item.get("source"),
                "external_id": remove_item.get("external_id"),
            },
            "reason": "safe_duplicate",
            "candidate": candidate,
        })

    deduplicated = []

    for item in items:
        key = (
            item.get("source"),
            item.get("external_id"),
        )

        if key in remove_keys:
            continue

        deduplicated.append(item)

    return deduplicated, removed_duplicates


def print_summary(items, deduplicated, duplicate_candidates, removed_duplicates):
    total = len(items)
    usable_count = sum(
        1 for item in items
        if item["data_quality_status"] == "usable"
    )
    candidate_count = sum(
        1 for item in items
        if item["data_quality_status"] == "candidate"
    )
    review_count = sum(
        1 for item in items
        if item["data_quality_status"] == "needs_review"
    )

    dedup_usable_count = sum(
        1 for item in deduplicated
        if item["data_quality_status"] == "usable"
    )
    dedup_candidate_count = sum(
        1 for item in deduplicated
        if item["data_quality_status"] == "candidate"
    )
    dedup_review_count = sum(
        1 for item in deduplicated
        if item["data_quality_status"] == "needs_review"
    )

    print("흡연구역 병합 정규화 완료")
    print(f"전체 병합본: {total}개")
    print(f"  usable: {usable_count}개")
    print(f"  candidate: {candidate_count}개")
    print(f"  needs_review: {review_count}개")
    print(f"중복 후보: {len(duplicate_candidates)}쌍")
    print(f"제거된 중복: {len(removed_duplicates)}개")
    print(f"중복 제거본: {len(deduplicated)}개")
    print(f"  usable: {dedup_usable_count}개")
    print(f"  candidate: {dedup_candidate_count}개")
    print(f"  needs_review: {dedup_review_count}개")
    print(f"전체 병합본 저장 위치: {OUTPUT_PATH}")
    print(f"중복 후보 저장 위치: {DUPLICATE_OUTPUT_PATH}")
    print(f"중복 제거본 저장 위치: {DEDUPLICATED_OUTPUT_PATH}")
    print(f"제거 로그 저장 위치: {REMOVED_DUPLICATES_OUTPUT_PATH}")


def main():
    all_items = []

    json_files = [
        JSON_DIR / "smoking_places_normalized.json",
        JSON_DIR / "smoking_places_busan_gangseo.json",
        JSON_DIR / "smokingarea_site_reports_normalized.json",
    ]

    for path in json_files:
        if not path.exists():
            print(f"JSON 없음: {path.name}")
            continue

        if path.name == "smoking_places_normalized.json":
            all_items.extend(normalize_smoking_places_normalized(path))

        elif path.name == "smoking_places_busan_gangseo.json":
            all_items.extend(normalize_busan_gangseo(path))

        elif path.name == "smokingarea_site_reports_normalized.json":
            all_items.extend(normalize_site_reports(path))

    print(f"CSV 폴더: {CSV_DIR}")
    print(f"CSV 파일 개수: {len(list(CSV_DIR.rglob('*.csv')))}")

    for path in CSV_DIR.rglob("*.csv"):
        if path.name in EXCLUDED_FILES:
            print(f"제외: {path.name}")
            continue

        print(f"CSV 처리: {path.name}")
        all_items.extend(normalize_csv(path))

    merged = merge_and_deduplicate_by_source_id(all_items)
    duplicate_candidates = find_duplicate_candidates(merged)
    deduplicated, removed_duplicates = make_deduplicated_items(
        merged,
        duplicate_candidates,
    )

    JSON_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(merged, file, ensure_ascii=False, indent=2)

    with open(DUPLICATE_OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(duplicate_candidates, file, ensure_ascii=False, indent=2)

    with open(DEDUPLICATED_OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(deduplicated, file, ensure_ascii=False, indent=2)

    with open(REMOVED_DUPLICATES_OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(removed_duplicates, file, ensure_ascii=False, indent=2)

    print_summary(
        merged,
        deduplicated,
        duplicate_candidates,
        removed_duplicates,
    )


if __name__ == "__main__":
    main()