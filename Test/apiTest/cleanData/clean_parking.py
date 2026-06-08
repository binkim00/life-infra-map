import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]

INPUT_PATH = BASE_DIR / "ExData" / "CSVData" / "parking" / "전국주차장정보표준데이터.csv"
OUTPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "parking_places.json"
SKIPPED_PATH = BASE_DIR / "ExData" / "Cleaned" / "skipped" / "parking_skipped.json"


def is_blank(value):
    return value is None or str(value).strip() == ""


def get_value(row, *keys):
    """
    CSV 컬럼명이 조금 다를 수 있어서 여러 후보 컬럼명을 순서대로 확인합니다.
    """
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


def normalize_time(value):
    """
    9:00, 09:00, 0900 같은 값을 가능한 한 HH:MM 형태로 정리합니다.
    """
    if is_blank(value):
        return ""

    value = str(value).strip()

    if ":" in value:
        parts = value.split(":")
        if len(parts) >= 2:
            hour = parts[0].zfill(2)
            minute = parts[1].zfill(2)
            return f"{hour}:{minute}"

    if value.isdigit() and len(value) == 4:
        return f"{value[:2]}:{value[2:]}"

    return value


def is_24_hours(start_time, end_time):
    start_time = normalize_time(start_time)
    end_time = normalize_time(end_time)

    return start_time == "00:00" and end_time in ["23:59", "24:00", "00:00"]


def is_night_open(end_time):
    """
    종료 시간이 21:00 이후면 야간 운영 후보로 봅니다.
    """
    end_time = normalize_time(end_time)

    if not end_time or ":" not in end_time:
        return False

    try:
        hour = int(end_time.split(":")[0])
        return hour >= 21 or end_time == "00:00"
    except ValueError:
        return False


def make_opening_hours(row):
    """
    운영시간은 raw 안에 정리된 형태로 같이 넣어둡니다.
    나중에 '지금 문 연 주차장' 추천에 활용할 수 있습니다.
    """
    return {
        "weekday": {
            "open": normalize_time(get_value(row, "평일운영시작시각")),
            "close": normalize_time(get_value(row, "평일운영종료시각")),
        },
        "saturday": {
            "open": normalize_time(get_value(row, "토요일운영시작시각")),
            "close": normalize_time(get_value(row, "토요일운영종료시각")),
        },
        "holiday": {
            "open": normalize_time(get_value(row, "공휴일운영시작시각")),
            "close": normalize_time(get_value(row, "공휴일운영종료시각")),
        },
    }


def make_tags(row):
    default_tags = ["주차장"]
    candidate_tags = []
    warning_tags = []

    parking_group = get_value(row, "주차장구분")
    parking_type = get_value(row, "주차장유형")
    fee_info = get_value(row, "요금정보")
    operation_days = get_value(row, "운영요일")
    disabled_parking = get_value(row, "장애인전용주차구역보유여부")

    weekday_start = get_value(row, "평일운영시작시각")
    weekday_end = get_value(row, "평일운영종료시각")
    saturday_start = get_value(row, "토요일운영시작시각")
    saturday_end = get_value(row, "토요일운영종료시각")
    holiday_start = get_value(row, "공휴일운영시작시각")
    holiday_end = get_value(row, "공휴일운영종료시각")

    # 주차장 구분
    if "공영" in parking_group:
        default_tags.append("공영주차장")
    elif "민영" in parking_group:
        default_tags.append("민영주차장")

    # 주차장 유형
    if "노외" in parking_type:
        default_tags.append("노외주차장")
    elif "노상" in parking_type:
        default_tags.append("노상주차장")
    elif "부설" in parking_type:
        default_tags.append("부설주차장")

    # 요금 정보
    if "무료" in fee_info:
        candidate_tags.append("무료주차")
    elif "유료" in fee_info:
        candidate_tags.append("유료주차")
    else:
        warning_tags.append("요금정보확인필요")

    # 운영요일
    if operation_days:
        if "평일" in operation_days:
            candidate_tags.append("평일운영")

        if "토요일" in operation_days or "토" in operation_days:
            candidate_tags.append("토요일운영")

        if "공휴일" in operation_days or "휴일" in operation_days:
            candidate_tags.append("공휴일운영")

        if (
            "토요일" in operation_days
            or "토" in operation_days
            or "공휴일" in operation_days
            or "휴일" in operation_days
        ):
            candidate_tags.append("주말운영")
    else:
        warning_tags.append("운영요일확인필요")

    # 24시간 운영 후보
    if (
        is_24_hours(weekday_start, weekday_end)
        or is_24_hours(saturday_start, saturday_end)
        or is_24_hours(holiday_start, holiday_end)
    ):
        candidate_tags.append("24시간운영후보")

    # 야간 운영 후보
    if (
        is_night_open(weekday_end)
        or is_night_open(saturday_end)
        or is_night_open(holiday_end)
    ):
        candidate_tags.append("야간운영후보")

    # 장애인 주차구역
    if disabled_parking in ["Y", "y", "예", "있음", "1"]:
        candidate_tags.append("장애인주차구역있음")

    # 운영시간 누락
    if is_blank(weekday_start) or is_blank(weekday_end):
        warning_tags.append("운영시간확인필요")

    return (
        list(dict.fromkeys(default_tags)),
        list(dict.fromkeys(candidate_tags)),
        list(dict.fromkeys(warning_tags)),
    )


def clean_parking_item(row):
    name = get_value(row, "주차장명")
    address = get_value(row, "소재지도로명주소", "소재지지번주소")

    lat = to_float(get_value(row, "위도"))
    lng = to_float(get_value(row, "경도"))

    management_no = get_value(row, "주차장관리번호", "관리번호")
    provider_code = get_value(row, "제공기관코드")
    source_updated_at = get_value(row, "데이터기준일자")

    if is_blank(name) or lat is None or lng is None:
        return None, "name_or_coordinate_missing"

    default_tags, candidate_tags, warning_tags = make_tags(row)
    opening_hours = make_opening_hours(row)

    if provider_code or management_no:
        external_id = f"parking_{provider_code}_{management_no}"
    else:
        external_id = f"parking_{name}_{lat}_{lng}"

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

    if "요금정보확인필요" in warning_tags:
        data_quality_score -= 3

    if "운영시간확인필요" in warning_tags:
        data_quality_score -= 3

    data_quality_score = max(0, min(100, data_quality_score))

    raw = dict(row)
    raw["opening_hours"] = opening_hours

    return {
        "name": name,
        "category": "parking",
        "address": address,
        "lat": lat,
        "lng": lng,
        "source": "public_parking_standard",
        "external_id": external_id,
        "source_name": "전국주차장정보표준데이터",
        "source_updated_at": source_updated_at,
        "detail_location": address,
        "data_quality_status": "usable",
        "data_quality_score": data_quality_score,
        "default_tags": default_tags,
        "candidate_tags": candidate_tags,
        "warning_tags": list(dict.fromkeys(warning_tags)),
        "raw": raw,
    }, None


def read_csv_file(path):
    """
    공공데이터 CSV 인코딩이 환경마다 다를 수 있어서 여러 인코딩을 순서대로 시도합니다.
    """
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
        place, reason = clean_parking_item(row)

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

    print("주차장 데이터 정제 완료")
    print(f"원본 개수: {len(raw_items)}개")
    print(f"정제 성공: {len(cleaned)}개")
    print(f"제외: {len(skipped)}개")
    print(f"저장 위치: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()