import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]

INPUT_PATH = BASE_DIR / "ExData" / "JsonData" / "beach" / "beaches_korea.json"
OUTPUT_PATH = BASE_DIR / "ExData" / "Cleaned" / "beach_places.json"
SKIPPED_PATH = BASE_DIR / "ExData" / "Cleaned" / "skipped" / "beach_skipped.json"


def is_blank(value):
    return value is None or str(value).strip() == ""


def to_float(value):
    try:
        if is_blank(value):
            return None
        return float(value)
    except ValueError:
        return None


def make_tags(item):
    default_tags = ["해수욕장", "바다", "야외"]
    candidate_tags = ["산책후보", "휴식후보", "사진찍기좋음후보"]
    warning_tags = []

    beach_knd = str(item.get("beach_knd") or "").strip()
    beach_len = to_float(item.get("beach_len"))
    link_tel = item.get("link_tel")

    if "모래" in beach_knd:
        candidate_tags.append("모래해변")

    if "몽돌" in beach_knd:
        candidate_tags.append("몽돌해변")

    if beach_len and beach_len >= 1000:
        candidate_tags.append("긴해변후보")

    if link_tel:
        candidate_tags.append("연락처있음")
    else:
        warning_tags.append("연락처없음")

    if is_blank(beach_knd):
        warning_tags.append("해변종류확인필요")

    return default_tags, candidate_tags, warning_tags


def clean_beach(item):
    name = str(item.get("sta_nm") or "").strip()
    sido = str(item.get("sido_nm") or "").strip()
    gugun = str(item.get("gugun_nm") or "").strip()

    lat = to_float(item.get("lat"))
    lng = to_float(item.get("lon"))

    if is_blank(name) or lat is None or lng is None:
        return None

    address = " ".join([part for part in [sido, gugun] if part])

    default_tags, candidate_tags, warning_tags = make_tags(item)

    data_quality_score = 80
    if not address:
        data_quality_score -= 10
    if "해변종류확인필요" in warning_tags:
        data_quality_score -= 5
    if "연락처없음" in warning_tags:
        data_quality_score -= 3

    external_id = f"beach_{sido}_{gugun}_{name}"

    return {
        "name": name,
        "category": "beach",
        "address": address,
        "lat": lat,
        "lng": lng,
        "source": "beach_api",
        "external_id": external_id,
        "source_name": "해양수산부_해수욕장정보서비스",
        "source_updated_at": "",
        "detail_location": address,
        "data_quality_status": "usable",
        "data_quality_score": data_quality_score,
        "default_tags": default_tags,
        "candidate_tags": list(dict.fromkeys(candidate_tags)),
        "warning_tags": list(dict.fromkeys(warning_tags)),
        "raw": item,
    }


def main():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    cleaned = []
    skipped = []

    for item in raw_items:
        place = clean_beach(item)

        if place is None:
            skipped.append({
                "reason": "name_or_coordinate_missing",
                "raw": item,
            })
        else:
            cleaned.append(place)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SKIPPED_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    with open(SKIPPED_PATH, "w", encoding="utf-8") as f:
        json.dump(skipped, f, ensure_ascii=False, indent=2)

    print("해수욕장 정제 완료")
    print(f"정제 성공: {len(cleaned)}개")
    print(f"제외: {len(skipped)}개")
    print(f"저장 위치: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()