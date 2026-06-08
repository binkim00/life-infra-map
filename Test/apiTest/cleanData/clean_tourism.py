import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]

INPUT_PATH = BASE_DIR / "ExData" / "JsonData" / "tourism" / "tourism_all_except_food_korea.json"
OUTPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "tourism_places.json"
SKIPPED_PATH = BASE_DIR / "ExData" / "Cleaned" / "skipped" / "tourism_skipped.json"


CONTENT_TYPE_MAP = {
    "12": {
        "category": "tourist_spot",
        "default_tags": ["관광명소"],
        "candidate_tags": ["사진찍기좋음후보", "나들이후보"],
        "warning_tags": [],
    },
    "14": {
        "category": "culture",
        "default_tags": ["문화시설"],
        "candidate_tags": ["실내후보", "전시관람후보"],
        "warning_tags": [],
    },
    "15": {
        "category": "festival_event",
        "default_tags": ["행사축제"],
        "candidate_tags": ["볼거리후보"],
        "warning_tags": ["행사기간확인필요"],
    },
    "25": {
        "category": "travel_course",
        "default_tags": ["여행코스"],
        "candidate_tags": ["산책후보", "데이트코스후보", "나들이후보"],
        "warning_tags": [],
    },
    "28": {
        "category": "leports",
        "default_tags": ["레포츠"],
        "candidate_tags": ["야외활동후보", "운동후보"],
        "warning_tags": [],
    },
    "32": {
        "category": "accommodation",
        "default_tags": ["숙박"],
        "candidate_tags": ["숙소후보"],
        "warning_tags": [],
    },
    "38": {
        "category": "shopping",
        "default_tags": ["쇼핑"],
        "candidate_tags": ["구경하기좋음후보"],
        "warning_tags": [],
    },
}


def is_blank(value):
    return value is None or str(value).strip() == ""


def to_float(value):
    try:
        if is_blank(value):
            return None
        return float(value)
    except ValueError:
        return None


def parse_date(value):
    """
    관광공사 modifiedtime 예시: 20240530123456
    정제 결과: 2024-05-30
    """
    if is_blank(value):
        return ""

    value = str(value).strip()

    if len(value) >= 8:
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"

    return ""


def add_keyword_tags(name, candidate_tags):
    """
    장소명에 들어간 단어를 보고 후보 태그 추가
    """
    name = name or ""

    if any(word in name for word in ["공원", "숲", "숲길", "둘레길", "산책로", "탐방로"]):
        candidate_tags.append("산책후보")
        candidate_tags.append("야외후보")
        candidate_tags.append("휴식후보")

    if any(word in name for word in ["해변", "해수욕장", "바다", "해안"]):
        candidate_tags.append("바다")
        candidate_tags.append("해변산책후보")
        candidate_tags.append("사진찍기좋음후보")

    if any(word in name for word in ["전망", "전망대", "야경"]):
        candidate_tags.append("전망좋음후보")
        candidate_tags.append("야경후보")

    if any(word in name for word in ["박물관", "미술관", "전시", "기념관"]):
        candidate_tags.append("실내후보")
        candidate_tags.append("전시관람후보")

    if any(word in name for word in ["시장", "상가", "쇼핑"]):
        candidate_tags.append("시장후보")
        candidate_tags.append("구경하기좋음후보")

    if any(word in name for word in ["온천", "스파"]):
        candidate_tags.append("휴식후보")
        candidate_tags.append("힐링후보")

    return candidate_tags


def clean_tourism_item(item):
    name = str(item.get("title") or "").strip()
    content_type_id = str(item.get("contenttypeid") or "").strip()
    content_id = str(item.get("contentid") or "").strip()

    lng = to_float(item.get("mapx"))
    lat = to_float(item.get("mapy"))

    addr1 = str(item.get("addr1") or "").strip()
    addr2 = str(item.get("addr2") or "").strip()
    address = " ".join([part for part in [addr1, addr2] if part])

    if is_blank(name) or lat is None or lng is None:
        return None, "name_or_coordinate_missing"

    if content_type_id not in CONTENT_TYPE_MAP:
        return None, "unsupported_content_type"

    type_info = CONTENT_TYPE_MAP[content_type_id]

    default_tags = list(type_info["default_tags"])
    candidate_tags = list(type_info["candidate_tags"])
    warning_tags = list(type_info["warning_tags"])

    candidate_tags = add_keyword_tags(name, candidate_tags)

    if item.get("firstimage"):
        candidate_tags.append("사진정보있음")

    if not address:
        warning_tags.append("주소확인필요")

    source_updated_at = parse_date(item.get("modifiedtime"))

    if not source_updated_at:
        warning_tags.append("기준일확인필요")

    data_quality_score = 80

    if address:
        data_quality_score += 5
    else:
        data_quality_score -= 10

    if item.get("firstimage"):
        data_quality_score += 3

    if source_updated_at:
        data_quality_score += 5
    else:
        data_quality_score -= 5

    data_quality_score = max(0, min(100, data_quality_score))

    external_id = f"tourism_{content_type_id}_{content_id}"

    return {
        "name": name,
        "category": type_info["category"],
        "address": address,
        "lat": lat,
        "lng": lng,
        "source": "tour_api",
        "external_id": external_id,
        "source_name": "한국관광공사_국문관광정보서비스",
        "source_updated_at": source_updated_at,
        "detail_location": address,
        "data_quality_status": "usable",
        "data_quality_score": data_quality_score,
        "default_tags": list(dict.fromkeys(default_tags)),
        "candidate_tags": list(dict.fromkeys(candidate_tags)),
        "warning_tags": list(dict.fromkeys(warning_tags)),
        "raw": item,
    }, None


def main():
    if not INPUT_PATH.exists():
        print("입력 파일을 찾을 수 없습니다.")
        print(f"경로 확인: {INPUT_PATH}")
        return

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    cleaned = []
    skipped = []
    seen_external_ids = set()

    for item in raw_items:
        place, reason = clean_tourism_item(item)

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

    print("관광 데이터 정제 완료")
    print(f"원본 개수: {len(raw_items)}개")
    print(f"정제 성공: {len(cleaned)}개")
    print(f"제외: {len(skipped)}개")
    print(f"저장 위치: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()