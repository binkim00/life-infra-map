import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]

INPUT_PATH = BASE_DIR / "ExData" / "CSVData" / "freewifi" / "무료와이파이정보.csv"
OUTPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "freewifi_places.json"
SKIPPED_PATH = BASE_DIR / "ExData" / "Cleaned" / "skipped" / "freewifi_skipped.json"


def is_blank(value):
    return value is None or str(value).strip() == ""


def get_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if not is_blank(value):
            return str(value).strip()
    return ""


def to_float(value):
    try:
        if is_blank(value):
            return None
        return float(str(value).strip())
    except ValueError:
        return None


def contains_any(text, keywords):
    text = text or ""
    return any(keyword in text for keyword in keywords)


def make_address(row):
    road_address = get_value(row, "소재지도로명주소")
    jibun_address = get_value(row, "소재지지번주소")
    sido = get_value(row, "설치시도명")
    sigungu = get_value(row, "설치시군구명")

    address = road_address or jibun_address

    if address:
        # 주소가 너무 짧으면 시도/시군구를 앞에 보강합니다.
        if sido and sido not in address:
            address = f"{sido} {address}"
        if sigungu and sigungu not in address:
            address = f"{sido} {sigungu} {address}".strip()
        return " ".join(address.split())

    return " ".join([part for part in [sido, sigungu] if part])


def make_tags(row):
    default_tags = ["공공와이파이", "무료와이파이"]
    candidate_tags = ["인터넷사용"]
    warning_tags = []

    name = get_value(row, "설치장소명")
    detail = get_value(row, "설치장소상세")
    facility_type = get_value(row, "설치시설구분명")
    provider = get_value(row, "서비스제공사명")
    ssid = get_value(row, "와이파이SSID")

    search_text = " ".join([name, detail, facility_type])

    if facility_type:
        candidate_tags.append(facility_type)
    else:
        warning_tags.append("시설구분확인필요")

    if contains_any(search_text, ["공원", "광장", "산책로"]):
        candidate_tags.append("공원와이파이")
        candidate_tags.append("야외와이파이")

    if contains_any(search_text, ["관광", "해수욕장", "해변", "전망", "문화", "유적", "명소"]):
        candidate_tags.append("관광지와이파이")

    if contains_any(search_text, ["버스", "정류장", "역", "터미널", "공항", "지하철"]):
        candidate_tags.append("교통시설와이파이")

    if contains_any(search_text, ["도서관", "청사", "주민센터", "행정복지센터", "구청", "시청"]):
        candidate_tags.append("공공시설와이파이")
        candidate_tags.append("실내후보")

    if contains_any(search_text, ["시장", "상가", "쇼핑"]):
        candidate_tags.append("시장와이파이")
        candidate_tags.append("쇼핑시설와이파이")

    if contains_any(search_text, ["복지", "경로당", "노인", "장애인"]):
        candidate_tags.append("복지시설와이파이")

    if contains_any(search_text, ["병원", "보건소", "의료"]):
        candidate_tags.append("의료시설와이파이")

    if contains_any(search_text, ["학교", "대학교", "교육"]):
        candidate_tags.append("교육시설와이파이")

    if provider:
        candidate_tags.append("제공사정보있음")
    else:
        warning_tags.append("제공사확인필요")

    if ssid:
        candidate_tags.append("SSID정보있음")
    else:
        warning_tags.append("SSID확인필요")

    return (
        list(dict.fromkeys(default_tags)),
        list(dict.fromkeys(candidate_tags)),
        list(dict.fromkeys(warning_tags)),
    )


def clean_freewifi_item(row):
    name = get_value(row, "설치장소명")
    detail_location = get_value(row, "설치장소상세")
    address = make_address(row)

    lat = to_float(get_value(row, "WGS84위도", "위도"))
    lng = to_float(get_value(row, "WGS84경도", "경도"))

    manage_no = get_value(row, "관리번호")
    source_updated_at = get_value(row, "데이터기준일자")

    if is_blank(name) or lat is None or lng is None:
        return None, "name_or_coordinate_missing"

    default_tags, candidate_tags, warning_tags = make_tags(row)

    if manage_no:
        external_id = f"freewifi_{manage_no}"
    else:
        external_id = f"freewifi_{name}_{lat}_{lng}"

    data_quality_score = 80

    if address:
        data_quality_score += 5
    else:
        warning_tags.append("주소확인필요")
        data_quality_score -= 10

    if source_updated_at:
        data_quality_score += 5
    else:
        warning_tags.append("기준일확인필요")
        data_quality_score -= 5

    if "SSID확인필요" in warning_tags:
        data_quality_score -= 3

    if "시설구분확인필요" in warning_tags:
        data_quality_score -= 3

    data_quality_score = max(0, min(100, data_quality_score))

    return {
        "name": name,
        "category": "free_wifi",
        "address": address,
        "lat": lat,
        "lng": lng,
        "source": "free_wifi_standard",
        "external_id": external_id,
        "source_name": "무료와이파이정보",
        "source_updated_at": source_updated_at,
        "detail_location": detail_location,
        "data_quality_status": "usable",
        "data_quality_score": data_quality_score,
        "default_tags": default_tags,
        "candidate_tags": candidate_tags,
        "warning_tags": list(dict.fromkeys(warning_tags)),
        "raw": dict(row),
    }, None


def read_csv_file(path):
    encodings = ["utf-8-sig", "cp949", "euc-kr"]

    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except UnicodeDecodeError:
            continue

    raise ValueError("지원하는 인코딩으로 CSV 파일을 읽지 못했습니다.")


def main():
    if not INPUT_PATH.exists():
        print("입력 파일을 찾을 수 없습니다.")
        print(f"경로 확인: {INPUT_PATH}")
        return

    raw_items = read_csv_file(INPUT_PATH)

    cleaned = []
    skipped = []
    seen_external_ids = set()

    for row in raw_items:
        place, reason = clean_freewifi_item(row)

        if place is None:
            skipped.append({
                "reason": reason,
                "raw": row,
            })
            continue

        if place["external_id"] in seen_external_ids:
            skipped.append({
                "reason": "duplicated_external_id",
                "raw": row,
            })
            continue

        seen_external_ids.add(place["external_id"])
        cleaned.append(place)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SKIPPED_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    with open(SKIPPED_PATH, "w", encoding="utf-8") as f:
        json.dump(skipped, f, ensure_ascii=False, indent=2)

    print("공공와이파이 데이터 정제 완료")
    print(f"원본 개수: {len(raw_items)}개")
    print(f"정제 성공: {len(cleaned)}개")
    print(f"제외: {len(skipped)}개")
    print(f"저장 위치: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
