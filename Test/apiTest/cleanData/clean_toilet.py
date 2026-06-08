import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]

INPUT_PATH = BASE_DIR / "ExData" / "CSVData" / "toilet" / "공중화장실정보.csv"
OUTPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "toilet_places.json"
SKIPPED_PATH = BASE_DIR / "ExData" / "Cleaned" / "skipped" / "toilet_skipped.json"


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


def to_int(value):
    try:
        if is_blank(value):
            return 0
        text = str(value).replace(",", "").strip()
        return int(float(text))
    except ValueError:
        return 0


def is_yes(value):
    text = str(value or "").strip().upper()
    return text in ["Y", "YES", "예", "있음", "설치", "유", "TRUE", "1"]


def contains_any(text, keywords):
    text = text or ""
    return any(keyword in text for keyword in keywords)


def make_address(row):
    road_address = get_value(row, "소재지도로명주소")
    jibun_address = get_value(row, "소재지지번주소")
    return road_address or jibun_address


def get_total_count(row, keys):
    return sum(to_int(get_value(row, key)) for key in keys)


def make_tags(row):
    default_tags = ["공중화장실", "생활편의"]
    candidate_tags = []
    warning_tags = []

    toilet_type = get_value(row, "구분", "구분명", "화장실구분")
    toilet_name = get_value(row, "화장실명")
    open_time = get_value(row, "개방시간")
    open_time_detail = get_value(row, "개방시간상세")

    owner_type = get_value(row, "화장실소유구분")
    disposal_type = get_value(row, "오물처리방식")

    emergency_bell = get_value(row, "비상벨설치여부")
    emergency_bell_place = get_value(row, "비상벨설치장소")
    cctv = get_value(row, "화장실입구CCTV설치유무", "화장실입구CCTV설치여부")
    diaper_table = get_value(row, "기저귀교환대유무", "기저귀교환대여부")
    diaper_place = get_value(row, "기저귀교환대장소")

    # 기본 구분 태그
    if toilet_type:
        if "개방" in toilet_type:
            default_tags.append("개방화장실")
        elif "공중" in toilet_type:
            default_tags.append("공중화장실")
        elif "간이" in toilet_type:
            default_tags.append("간이화장실")
        else:
            default_tags.append(toilet_type)
    else:
        warning_tags.append("화장실구분확인필요")

    # 이름 기반 태그
    if contains_any(toilet_name, ["공원", "근린공원", "어린이공원"]):
        candidate_tags.append("공원화장실")
    if contains_any(toilet_name, ["역", "터미널", "정류장", "지하철"]):
        candidate_tags.append("교통시설화장실")
    if contains_any(toilet_name, ["시장", "상가"]):
        candidate_tags.append("시장화장실")
    if contains_any(toilet_name, ["해수욕장", "해변", "관광", "전망", "문화"]):
        candidate_tags.append("관광지화장실")
    if contains_any(toilet_name, ["주민센터", "행정복지센터", "구청", "시청", "청사"]):
        candidate_tags.append("공공시설화장실")

    # 개방시간 태그
    open_text = f"{open_time} {open_time_detail}"

    if contains_any(open_text, ["24", "상시", "연중", "종일"]):
        candidate_tags.append("24시간개방후보")
    elif open_text.strip():
        candidate_tags.append("개방시간정보있음")
    else:
        warning_tags.append("개방시간확인필요")

    # 대변기/소변기 수 기반 태그
    male_toilets = get_total_count(row, [
        "남성용-대변기수",
        "남성용대변기수",
        "남성용_대변기수",
    ])
    male_urinals = get_total_count(row, [
        "남성용-소변기수",
        "남성용소변기수",
        "남성용_소변기수",
    ])
    female_toilets = get_total_count(row, [
        "여성용-대변기수",
        "여성용대변기수",
        "여성용_대변기수",
    ])

    disabled_count = get_total_count(row, [
        "남성용-장애인용대변기수",
        "남성용-장애인용소변기수",
        "여성용-장애인용대변기수",
        "남성용장애인용대변기수",
        "남성용장애인용소변기수",
        "여성용장애인용대변기수",
    ])

    child_count = get_total_count(row, [
        "남성용-어린이용대변기수",
        "남성용-어린이용소변기수",
        "여성용-어린이용대변기수",
        "남성용어린이용대변기수",
        "남성용어린이용소변기수",
        "여성용어린이용대변기수",
    ])

    total_basic = male_toilets + male_urinals + female_toilets

    if total_basic > 0:
        candidate_tags.append("남녀화장실정보있음")

    if disabled_count > 0:
        candidate_tags.append("장애인화장실있음")

    if child_count > 0:
        candidate_tags.append("어린이화장실있음")

    if total_basic >= 10:
        candidate_tags.append("규모큰화장실후보")

    # 안전/편의시설 태그
    if is_yes(emergency_bell) or emergency_bell_place:
        candidate_tags.append("비상벨있음")
    else:
        warning_tags.append("비상벨확인필요")

    if is_yes(cctv):
        candidate_tags.append("CCTV있음")

    if is_yes(diaper_table) or diaper_place:
        candidate_tags.append("기저귀교환대있음")
        candidate_tags.append("아이와가기좋음후보")

    # 소유/처리 방식
    if owner_type:
        if "공공" in owner_type or "공용" in owner_type or "공중" in owner_type:
            candidate_tags.append("공공관리후보")

    if disposal_type:
        candidate_tags.append("오물처리방식정보있음")

    return (
        list(dict.fromkeys(default_tags)),
        list(dict.fromkeys(candidate_tags)),
        list(dict.fromkeys(warning_tags)),
    )


def clean_toilet_item(row):
    name = get_value(row, "화장실명")
    address = make_address(row)

    lat = to_float(get_value(row, "WGS84위도", "위도"))
    lng = to_float(get_value(row, "WGS84경도", "경도"))

    manage_no = get_value(row, "관리번호")
    source_updated_at = get_value(row, "데이터기준일자")
    manager = get_value(row, "관리기관명")
    phone = get_value(row, "전화번호")

    if is_blank(name) or lat is None or lng is None:
        return None, "name_or_coordinate_missing"

    default_tags, candidate_tags, warning_tags = make_tags(row)

    if manage_no:
        external_id = f"toilet_{manage_no}"
    else:
        external_id = f"toilet_{name}_{lat}_{lng}"

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

    if manager:
        data_quality_score += 3
    else:
        warning_tags.append("관리기관확인필요")
        data_quality_score -= 3

    if phone:
        candidate_tags.append("연락처있음")
    else:
        warning_tags.append("연락처확인필요")
        data_quality_score -= 2

    if "개방시간확인필요" in warning_tags:
        data_quality_score -= 5

    data_quality_score = max(0, min(100, data_quality_score))

    return {
        "name": name,
        "category": "toilet",
        "address": address,
        "lat": lat,
        "lng": lng,
        "source": "public_toilet_standard",
        "external_id": external_id,
        "source_name": "공중화장실정보",
        "source_updated_at": source_updated_at,
        "detail_location": address,
        "data_quality_status": "usable",
        "data_quality_score": data_quality_score,
        "default_tags": list(dict.fromkeys(default_tags)),
        "candidate_tags": list(dict.fromkeys(candidate_tags)),
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
        place, reason = clean_toilet_item(row)

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

    print("공중화장실 데이터 정제 완료")
    print(f"원본 개수: {len(raw_items)}개")
    print(f"정제 성공: {len(cleaned)}개")
    print(f"제외: {len(skipped)}개")
    print(f"저장 위치: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
