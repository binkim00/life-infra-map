import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]

INPUT_PATH = BASE_DIR / "ExData" / "CSVData" / "citypark" / "전국도시공원정보표준데이터.csv"
OUTPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "citypark_places.json"
SKIPPED_PATH = BASE_DIR / "ExData" / "Cleaned" / "skipped" / "citypark_skipped.json"


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


def parse_area(value):
    try:
        if is_blank(value):
            return None
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def contains_any(text, keywords):
    text = text or ""
    return any(keyword in text for keyword in keywords)


def make_tags(row):
    default_tags = ["공원", "야외"]
    candidate_tags = ["산책후보", "휴식후보"]
    warning_tags = []

    park_type = get_value(row, "공원구분")
    park_name = get_value(row, "공원명")

    exercise_facility = get_value(row, "운동시설")
    play_facility = get_value(row, "유희시설")
    convenience_facility = get_value(row, "편익시설")
    culture_facility = get_value(row, "교양시설")
    etc_facility = get_value(row, "기타시설")

    park_area = parse_area(get_value(row, "공원면적"))

    all_facilities = " ".join([
        exercise_facility,
        play_facility,
        convenience_facility,
        culture_facility,
        etc_facility,
    ])

    # 공원 구분 기반 태그
    if park_type:
        default_tags.append(park_type)

        if "어린이" in park_type:
            candidate_tags.append("아이와가기좋음후보")
        if "근린" in park_type:
            candidate_tags.append("동네산책후보")
        if "수변" in park_type:
            candidate_tags.append("수변산책후보")
        if "체육" in park_type:
            candidate_tags.append("운동후보")
        if "문화" in park_type:
            candidate_tags.append("문화공원후보")
    else:
        warning_tags.append("공원구분확인필요")

    # 공원명 기반 태그
    if contains_any(park_name, ["수변", "강변", "호수", "해변", "해안"]):
        candidate_tags.append("수변산책후보")

    if contains_any(park_name, ["숲", "산", "둘레길", "산책로"]):
        candidate_tags.append("숲길산책후보")
        candidate_tags.append("힐링후보")

    if contains_any(park_name, ["전망", "야경"]):
        candidate_tags.append("전망좋음후보")
        candidate_tags.append("야경후보")

    # 운동시설 기반 태그
    if exercise_facility:
        candidate_tags.append("운동시설있음")
        candidate_tags.append("운동후보")

        if contains_any(exercise_facility, ["축구", "농구", "배드민턴", "테니스", "족구"]):
            candidate_tags.append("구기운동시설있음")

        if contains_any(exercise_facility, ["체력", "헬스", "운동기구"]):
            candidate_tags.append("체력단련시설있음")

        if contains_any(exercise_facility, ["트랙", "조깅", "러닝"]):
            candidate_tags.append("러닝후보")

    # 유희시설 기반 태그
    if play_facility:
        candidate_tags.append("놀이시설있음")

        if contains_any(play_facility, ["어린이", "놀이터", "놀이"]):
            candidate_tags.append("어린이놀이터있음")
            candidate_tags.append("아이와가기좋음후보")

    # 편익시설 기반 태그
    if convenience_facility:
        candidate_tags.append("편의시설있음")

        if contains_any(convenience_facility, ["화장실"]):
            candidate_tags.append("화장실있음")

        if contains_any(convenience_facility, ["주차", "주차장"]):
            candidate_tags.append("주차장있음")

        if contains_any(convenience_facility, ["음수", "식수"]):
            candidate_tags.append("음수대있음")

        if contains_any(convenience_facility, ["벤치", "의자", "쉼터", "정자", "파고라"]):
            candidate_tags.append("쉴곳있음")

        if contains_any(convenience_facility, ["매점", "카페", "편의점"]):
            candidate_tags.append("매점있음")

    # 교양시설 기반 태그
    if culture_facility:
        candidate_tags.append("문화시설있음")

        if contains_any(culture_facility, ["도서관", "전시", "박물관", "기념관"]):
            candidate_tags.append("문화체험후보")

    # 공원 면적 기반 태그
    if park_area is not None:
        if park_area >= 50000:
            candidate_tags.append("대형공원후보")
            candidate_tags.append("러닝후보")
            candidate_tags.append("긴산책후보")
        elif park_area >= 10000:
            candidate_tags.append("넓은공원후보")
            candidate_tags.append("산책후보")
    else:
        warning_tags.append("공원면적확인필요")

    if not all_facilities.strip():
        warning_tags.append("시설정보확인필요")

    return (
        list(dict.fromkeys(default_tags)),
        list(dict.fromkeys(candidate_tags)),
        list(dict.fromkeys(warning_tags)),
    )


def clean_citypark_item(row):
    name = get_value(row, "공원명")
    address = get_value(row, "소재지도로명주소", "소재지지번주소")

    lat = to_float(get_value(row, "위도"))
    lng = to_float(get_value(row, "경도"))

    manage_no = get_value(row, "관리번호")
    provider_code = get_value(row, "제공기관코드")
    source_updated_at = get_value(row, "데이터기준일자")

    if is_blank(name) or lat is None or lng is None:
        return None, "name_or_coordinate_missing"

    default_tags, candidate_tags, warning_tags = make_tags(row)

    if provider_code or manage_no:
        external_id = f"citypark_{provider_code}_{manage_no}"
    else:
        external_id = f"citypark_{name}_{lat}_{lng}"

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

    if "시설정보확인필요" in warning_tags:
        data_quality_score -= 5

    if "공원면적확인필요" in warning_tags:
        data_quality_score -= 3

    data_quality_score = max(0, min(100, data_quality_score))

    return {
        "name": name,
        "category": "city_park",
        "address": address,
        "lat": lat,
        "lng": lng,
        "source": "citypark_standard",
        "external_id": external_id,
        "source_name": "전국도시공원정보표준데이터",
        "source_updated_at": source_updated_at,
        "detail_location": address,
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
        place, reason = clean_citypark_item(row)

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

    print("도시공원 데이터 정제 완료")
    print(f"원본 개수: {len(raw_items)}개")
    print(f"정제 성공: {len(cleaned)}개")
    print(f"제외: {len(skipped)}개")
    print(f"저장 위치: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
