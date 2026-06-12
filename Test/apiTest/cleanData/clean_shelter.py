import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]

INPUT_PATH = BASE_DIR / "ExData" / "JsonData" / "shelter" / "shelter_api_items.json"
OUTPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "shelter_places.json"
SKIPPED_PATH = BASE_DIR / "ExData" / "Cleaned" / "skipped" / "shelter_skipped.json"


def is_blank(value):
    return value is None or str(value).strip() == ""


def get_value(item, *keys):
    for key in keys:
        value = item.get(key)

        if not is_blank(value):
            return str(value).strip()

    return ""


def to_float(value):
    try:
        if is_blank(value):
            return None

        return float(str(value).replace(",", "").strip())

    except ValueError:
        return None


def to_int(value):
    try:
        if is_blank(value):
            return 0

        return int(float(str(value).replace(",", "").strip()))

    except ValueError:
        return 0


def is_yes(value):
    text = str(value or "").strip().upper()

    return text in [
        "Y",
        "YES",
        "예",
        "있음",
        "가능",
        "유",
        "TRUE",
        "1",
        "O",
    ]


def contains_any(text, keywords):
    text = text or ""

    return any(keyword in text for keyword in keywords)


def normalize_time(value):
    if is_blank(value):
        return ""

    value = str(value).strip()

    # 900, 0900, 09:00 모두 대응
    if ":" in value:
        parts = value.split(":")

        if len(parts) >= 2:
            hour = parts[0].zfill(2)
            minute = parts[1].zfill(2)
            return f"{hour}:{minute}"

    if value.isdigit():
        if len(value) == 4:
            return f"{value[:2]}:{value[2:]}"
        if len(value) == 3:
            return f"0{value[0]}:{value[1:]}"
        if len(value) == 2:
            return f"{value}:00"

    return value


def is_24_hours(start_time, end_time):
    start_time = normalize_time(start_time)
    end_time = normalize_time(end_time)

    return start_time == "00:00" and end_time in ["23:59", "24:00", "00:00"]


def is_night_open(end_time):
    end_time = normalize_time(end_time)

    if not end_time or ":" not in end_time:
        return False

    try:
        hour = int(end_time.split(":")[0])
        return hour >= 21 or end_time == "00:00"

    except ValueError:
        return False


def make_address(item):
    return (
        get_value(item, "RN_DTL_ADRES")
        or get_value(item, "DTL_ADRES")
        or get_value(item, "DTL_POSITION")
    )


def make_opening_hours(item):
    return {
        "weekday": {
            "open": normalize_time(get_value(item, "WKDAY_OPER_BEGIN_TIME")),
            "close": normalize_time(get_value(item, "WKDAY_OPER_END_TIME")),
        },
        "weekend_holiday": {
            "open": normalize_time(get_value(item, "WKEND_HDAY_OPER_BEGIN_TIME")),
            "close": normalize_time(get_value(item, "WKEND_HDAY_OPER_END_TIME")),
        },
    }


def make_tags(item):
    default_tags = ["쉼터"]
    candidate_tags = []
    warning_tags = []

    name = get_value(item, "RSTR_NM")
    facility_type = get_value(item, "FCLTY_TY")
    facility_subtype = get_value(item, "FCLTY_SCLAS")
    remark = get_value(item, "RM")

    weekday_start = get_value(item, "WKDAY_OPER_BEGIN_TIME")
    weekday_end = get_value(item, "WKDAY_OPER_END_TIME")
    weekend_start = get_value(item, "WKEND_HDAY_OPER_BEGIN_TIME")
    weekend_end = get_value(item, "WKEND_HDAY_OPER_END_TIME")

    night_open = get_value(item, "CHCK_MATTER_NIGHT_OPN_AT")
    weekend_open = get_value(item, "CHCK_MATTER_WKEND_HDAY_OPN_AT")
    stay_available = get_value(item, "CHCK_MATTER_STAYNG_PSBL_AT")

    fan = get_value(item, "COLR_HOLD_ELEFN")
    air_conditioner = get_value(item, "COLR_HOLD_ARCNDTN")

    area = to_float(get_value(item, "AR"))
    capacity = to_int(get_value(item, "USE_PSBL_NMPR"))

    type_text = f"{name} {facility_type} {facility_subtype} {remark}"

    # 쉼터 성격
    candidate_tags.append("무더위쉼터")

    if contains_any(type_text, ["한파", "추위"]):
        candidate_tags.append("한파쉼터후보")

    # 시설 유형
    if contains_any(type_text, ["경로당", "노인", "복지"]):
        candidate_tags.append("복지시설쉼터")

    if contains_any(type_text, ["주민센터", "행정복지센터", "구청", "시청", "군청", "청사"]):
        candidate_tags.append("공공시설쉼터")

    if contains_any(type_text, ["공원", "정자", "파고라", "그늘막", "야외"]):
        candidate_tags.append("야외쉼터")

    if contains_any(type_text, ["도서관", "센터", "회관", "복지관", "경로당", "은행", "마트", "건물"]):
        candidate_tags.append("실내쉼터")

    # 운영 시간
    if is_24_hours(weekday_start, weekday_end) or is_24_hours(weekend_start, weekend_end):
        candidate_tags.append("24시간운영후보")

    if is_night_open(weekday_end) or is_night_open(weekend_end) or is_yes(night_open):
        candidate_tags.append("야간운영후보")

    if is_yes(weekend_open):
        candidate_tags.append("주말휴일개방")

    if weekday_start or weekday_end or weekend_start or weekend_end:
        candidate_tags.append("운영시간정보있음")
    else:
        warning_tags.append("운영시간확인필요")

    # 숙박 가능
    if is_yes(stay_available):
        candidate_tags.append("숙박가능후보")

    # 냉방 시설
    if to_int(fan) > 0 or is_yes(fan):
        candidate_tags.append("선풍기있음")

    if to_int(air_conditioner) > 0 or is_yes(air_conditioner):
        candidate_tags.append("냉방시설있음")

    # 규모/수용 인원
    if capacity >= 50:
        candidate_tags.append("수용인원많음")
    elif capacity > 0:
        candidate_tags.append("수용인원정보있음")

    if area is not None:
        if area >= 100:
            candidate_tags.append("규모큰쉼터후보")
        elif area > 0:
            candidate_tags.append("면적정보있음")

    return (
        list(dict.fromkeys(default_tags)),
        list(dict.fromkeys(candidate_tags)),
        list(dict.fromkeys(warning_tags)),
    )


def clean_shelter_item(item):
    name = get_value(item, "RSTR_NM")
    address = make_address(item)

    lat = to_float(get_value(item, "LA"))
    lng = to_float(get_value(item, "LO"))

    shelter_no = get_value(item, "RSTR_FCLTY_NO")
    year = get_value(item, "YEAR")
    area_code = get_value(item, "ARCD")
    source_updated_at = get_value(item, "MODF_TIME") or get_value(item, "INPT_TIME")

    if is_blank(name) or lat is None or lng is None:
        return None, "name_or_coordinate_missing"

    default_tags, candidate_tags, warning_tags = make_tags(item)
    opening_hours = make_opening_hours(item)

    if shelter_no:
        external_id = f"shelter_{shelter_no}"
    else:
        external_id = f"shelter_{name}_{lat}_{lng}"

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

    if area_code:
        data_quality_score += 3

    if "운영시간확인필요" in warning_tags:
        data_quality_score -= 5

    data_quality_score = max(0, min(100, data_quality_score))

    raw = dict(item)
    raw["opening_hours"] = opening_hours

    return {
        "name": name,
        "category": "shelter",
        "address": address,
        "lat": lat,
        "lng": lng,
        "source": "heat_shelter_api",
        "external_id": external_id,
        "source_name": "행정안전부_무더위쉼터",
        "source_updated_at": source_updated_at,
        "detail_location": get_value(item, "DTL_POSITION") or address,
        "data_quality_status": "usable",
        "data_quality_score": data_quality_score,
        "default_tags": list(dict.fromkeys(default_tags)),
        "candidate_tags": list(dict.fromkeys(candidate_tags)),
        "warning_tags": list(dict.fromkeys(warning_tags)),
        "raw": raw,
    }, None


def main():
    if not INPUT_PATH.exists():
        print("입력 파일을 찾을 수 없습니다.")
        print(f"경로 확인: {INPUT_PATH}")
        print("먼저 fetch_shelter_api.py를 실행해서 shelter_api_items.json을 생성해주세요.")
        return

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    cleaned = []
    skipped = []
    seen_external_ids = set()

    for item in raw_items:
        place, reason = clean_shelter_item(item)

        if place is None:
            skipped.append({
                "reason": reason,
                "raw": item,
            })
            continue

        if place["external_id"] in seen_external_ids:
            skipped.append({
                "reason": "duplicated_external_id",
                "raw": item,
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

    print("쉼터 API 데이터 정제 완료")
    print(f"원본 개수: {len(raw_items)}개")
    print(f"정제 성공: {len(cleaned)}개")
    print(f"제외: {len(skipped)}개")
    print(f"저장 위치: {OUTPUT_PATH}")
    print(f"스킵 위치: {SKIPPED_PATH}")


if __name__ == "__main__":
    main()