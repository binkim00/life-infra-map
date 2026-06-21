import json
from pathlib import Path
from collections import Counter

BASE_DIR = Path(r"C:\Users\k0b03\Desktop\영빈\SSAFY\life-infra-map\backend")
PLACE_DIR = BASE_DIR / "recommendations" / "fixtures" / "places"
TAG_DIR = BASE_DIR / "recommendations" / "fixtures" / "tags"
OUTPUT_PATH = BASE_DIR / "recommendations" / "fixtures" / "_place_tag_full_coverage_summary.json"

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

def guess_source(path):
    name = path.name.lower()
    for key, source in SOURCE_HINTS.items():
        if key in name:
            return source
    return None

def get(row, keys):
    for key in keys:
        value = row.get(key)
        if value not in [None, ""]:
            return value
    return None

def normalize_tourism_id(source, external_id):
    if source == "tour_api" and external_id and not str(external_id).startswith("tourism_"):
        return f"tourism_12_{external_id}"
    return external_id

def get_original_key(row, default_source=None):
    source = get(row, [
        "place_source",
        "original_source",
        "source",
        "external_source",
        "data_source",
    ]) or default_source

    external_id = get(row, [
        "place_external_id",
        "original_external_id",
        "external_id",
        "source_id",
        "place_id",
        "contentid",
        "content_id",
        "id",
    ])

    external_id = normalize_tourism_id(source, external_id)

    if source and external_id:
        return source, str(external_id)
    return None

def get_tag_key(row):
    source = get(row, ["place_source", "external_source"])
    external_id = get(row, ["place_external_id", "external_id"])
    if source and external_id:
        return source, str(external_id)
    return None

internal_place_keys = set()
external_match_original_keys = set()
place_file_summary = {}

for path in PLACE_DIR.glob("*.json"):
    if path.name.startswith("_"):
        continue

    data = load_json(path)
    default_source = guess_source(path)

    internal_count = 0
    external_count = 0

    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            key = get_original_key(row, default_source)
            if key:
                internal_place_keys.add(key)
                internal_count += 1

    elif isinstance(data, dict):
        # DB에 직접 넣을 장소
        for row in data.get("place_candidates", []):
            if not isinstance(row, dict):
                continue
            key = get_original_key(row, default_source)
            if key:
                internal_place_keys.add(key)
                internal_count += 1

        # 지도 API에 검색되어서 DB Place로 안 넣은 장소
        for row in data.get("external_places", []):
            if not isinstance(row, dict):
                continue
            key = get_original_key(row, default_source)
            if key:
                external_match_original_keys.add(key)
                external_count += 1

    place_file_summary[path.name] = {
        "internal_place_count": internal_count,
        "external_match_count": external_count,
    }

tag_keys_by_file = {}
tag_file_summary = {}

for path in TAG_DIR.glob("*.json"):
    if path.name.startswith("_"):
        continue
    if ".lean." in path.name or ".evidence." in path.name:
        continue

    data = load_json(path)

    if not isinstance(data, list):
        continue

    keys = set()
    missing_key_count = 0

    for row in data:
        if not isinstance(row, dict):
            continue

        key = get_tag_key(row)
        if key:
            keys.add(key)
        else:
            missing_key_count += 1

    tag_keys_by_file[path.name] = keys
    tag_file_summary[path.name] = {
        "unique_tag_place_count": len(keys),
        "missing_key_count": missing_key_count,
    }

result = {
    "total": {},
    "place_files": place_file_summary,
    "tag_files": {},
}

all_tag_keys = set()

for filename, tag_keys in tag_keys_by_file.items():
    all_tag_keys |= tag_keys

    internal_matched = tag_keys & internal_place_keys
    external_matched = tag_keys & external_match_original_keys
    unresolved = tag_keys - internal_place_keys - external_match_original_keys

    result["tag_files"][filename] = {
        "unique_tag_place_count": len(tag_keys),
        "internal_place_matched": len(internal_matched),
        "external_place_matched": len(external_matched),
        "unresolved_missing_count": len(unresolved),
        "unresolved_missing_samples": [
            {"source": source, "external_id": external_id}
            for source, external_id in sorted(unresolved)[:50]
        ],
    }

all_internal_matched = all_tag_keys & internal_place_keys
all_external_matched = all_tag_keys & external_match_original_keys
all_unresolved = all_tag_keys - internal_place_keys - external_match_original_keys

result["total"] = {
    "tag_total_unique_place_keys": len(all_tag_keys),
    "internal_place_matched": len(all_internal_matched),
    "external_place_matched": len(all_external_matched),
    "unresolved_missing_count": len(all_unresolved),
    "unresolved_missing_samples": [
        {"source": source, "external_id": external_id}
        for source, external_id in sorted(all_unresolved)[:100]
    ],
}

with OUTPUT_PATH.open("w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"저장 완료: {OUTPUT_PATH}")
print(json.dumps(result["total"], ensure_ascii=False, indent=2))