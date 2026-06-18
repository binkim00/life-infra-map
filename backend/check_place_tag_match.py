import json
from pathlib import Path
from collections import Counter, defaultdict

BASE_DIR = Path(r"C:\Users\k0b03\Desktop\영빈\SSAFY\life-infra-map\backend")

PLACE_DIR = BASE_DIR / "recommendations" / "fixtures" / "places"
TAG_DIR = BASE_DIR / "recommendations" / "fixtures" / "tags"

OUTPUT_PATH = BASE_DIR / "recommendations" / "fixtures" / "_place_tag_match_summary.json"

# 파일명으로 source를 추정해야 하는 경우를 위한 힌트입니다.
# 실제 Place fixture 안에 source가 있으면 그 값을 우선 사용합니다.
SOURCE_HINTS = {
    "beach": "beach_api",
    "parking": "public_parking_standard",
    "park": "citypark_standard",
    "citypark": "citypark_standard",
    "shelter": "heat_shelter_api",
    "toilet": "public_toilet_standard",
    "tourism": "tour_api",
    "tourist": "tour_api",
    "cafe": "kakao_local",
    "freewifi": "freewifi",
    "wifi": "freewifi",
    "smoking": "smoking_area",
}

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def guess_source_from_filename(path):
    name = path.name.lower()
    for key, source in SOURCE_HINTS.items():
        if key in name:
            return source
    return None

def extract_place_items(data):
    """
    place fixture 구조가 list일 수도 있고,
    {"place_candidates": [...], "external_places": [...]} 형태일 수도 있어서
    최대한 안전하게 추출합니다.
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        items = []

        for key in [
            "place_candidates",
            "places",
            "items",
            "data",
            "results",
        ]:
            value = data.get(key)
            if isinstance(value, list):
                items.extend(value)

        # external_places는 기존 import에서 스킵하는 구조일 수 있지만,
        # 비교용으로는 따로 개수를 확인할 수 있게 포함하지 않습니다.
        return items

    return []

def get_value(row, keys):
    for key in keys:
        value = row.get(key)
        if value not in [None, ""]:
            return value
    return None

def build_place_key(row, default_source=None):
    source = get_value(row, [
        "source",
        "place_source",
        "external_source",
        "data_source",
    ]) or default_source

    external_id = get_value(row, [
        "external_id",
        "place_external_id",
        "source_id",
        "place_id",
        "contentid",
        "content_id",
        "id",
    ])

    # tourism contentid 보정
    if source == "tour_api" and external_id and not str(external_id).startswith("tourism_"):
        external_id = f"tourism_12_{external_id}"

    return source, str(external_id) if external_id is not None else None

def build_tag_key(row):
    source = get_value(row, [
        "place_source",
        "external_source",
    ])

    external_id = get_value(row, [
        "place_external_id",
        "external_id",
    ])

    return source, str(external_id) if external_id is not None else None

def summarize_places():
    place_keys = set()
    place_file_summary = {}

    for path in PLACE_DIR.glob("*.json"):
        if path.name.startswith("_"):
            continue

        data = load_json(path)
        items = extract_place_items(data)
        default_source = guess_source_from_filename(path)

        valid_count = 0
        missing_key_count = 0
        source_counter = Counter()

        for row in items:
            if not isinstance(row, dict):
                continue

            source, external_id = build_place_key(row, default_source)

            if source and external_id:
                place_keys.add((source, external_id))
                source_counter[source] += 1
                valid_count += 1
            else:
                missing_key_count += 1

        place_file_summary[path.name] = {
            "item_count": len(items),
            "valid_place_key_count": valid_count,
            "missing_key_count": missing_key_count,
            "source_counts": dict(source_counter),
        }

    return place_keys, place_file_summary

def summarize_tags():
    tag_place_keys = set()
    tag_file_summary = {}

    for path in TAG_DIR.glob("*.json"):
        if path.name.startswith("_"):
            continue

        # lean/evidence 결과물이 이미 있으면 제외
        if ".lean." in path.name or ".evidence." in path.name:
            continue

        data = load_json(path)

        if not isinstance(data, list):
            tag_file_summary[path.name] = {
                "error": "list 구조가 아님",
                "type": type(data).__name__,
            }
            continue

        valid_count = 0
        missing_key_count = 0
        source_counter = Counter()
        file_tag_place_keys = set()

        for row in data:
            if not isinstance(row, dict):
                continue

            source, external_id = build_tag_key(row)

            if source and external_id:
                key = (source, external_id)
                tag_place_keys.add(key)
                file_tag_place_keys.add(key)
                source_counter[source] += 1
                valid_count += 1
            else:
                missing_key_count += 1

        tag_file_summary[path.name] = {
            "row_count": len(data),
            "valid_tag_row_key_count": valid_count,
            "unique_tag_place_count": len(file_tag_place_keys),
            "missing_key_count": missing_key_count,
            "source_counts": dict(source_counter),
        }

    return tag_place_keys, tag_file_summary

def main():
    place_keys, place_file_summary = summarize_places()
    tag_place_keys, tag_file_summary = summarize_tags()

    tag_missing_place = sorted(tag_place_keys - place_keys)
    place_without_tag = sorted(place_keys - tag_place_keys)

    summary = {
        "place_total_unique_keys": len(place_keys),
        "tag_total_unique_place_keys": len(tag_place_keys),
        "tag_place_match_count": len(tag_place_keys & place_keys),
        "tag_missing_place_count": len(tag_missing_place),
        "place_without_tag_count": len(place_without_tag),
        "place_files": place_file_summary,
        "tag_files": tag_file_summary,
        "tag_missing_place_samples": [
            {"source": source, "external_id": external_id}
            for source, external_id in tag_missing_place[:100]
        ],
        "place_without_tag_samples": [
            {"source": source, "external_id": external_id}
            for source, external_id in place_without_tag[:100]
        ],
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"요약 저장 완료: {OUTPUT_PATH}")
    print(f"Place unique keys: {summary['place_total_unique_keys']:,}")
    print(f"Tag unique place keys: {summary['tag_total_unique_place_keys']:,}")
    print(f"Matched: {summary['tag_place_match_count']:,}")
    print(f"Tag missing Place: {summary['tag_missing_place_count']:,}")
    print(f"Place without Tag: {summary['place_without_tag_count']:,}")

if __name__ == "__main__":
    main()