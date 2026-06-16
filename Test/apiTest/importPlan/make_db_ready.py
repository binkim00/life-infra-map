import argparse
import json
import re
from datetime import datetime
from pathlib import Path


DATASET_CONFIGS = {
    "toilet": {
        "input_path": Path("ExData/Cleaned/toilet_places.json"),
        "category": "toilet",
        "exclude_keywords": [],
    },
    "freewifi": {
        "input_path": Path("ExData/Cleaned/freewifi_places.json"),
        "category": "freewifi",
        "exclude_keywords": [],
    },
    "shelter": {
        "input_path": Path("ExData/Cleaned/shelter_places.json"),
        "category": "shelter",
        "exclude_keywords": ["무더위", "폭염"],
    },
}


OUTPUT_DIR = Path("ExData/ImportPlan/final")


NAME_KEYS = [
    "name",
    "place_name",
    "facility_name",
    "toilet_name",
    "wifi_name",
    "shelter_name",
    "시설명",
    "장소명",
    "명칭",
    "화장실명",
    "와이파이명",
    "쉼터명",
]

ADDRESS_KEYS = [
    "address",
    "addr",
    "road_address",
    "road_address_name",
    "address_name",
    "주소",
    "도로명주소",
    "지번주소",
    "소재지주소",
    "소재지도로명주소",
    "소재지지번주소",
]

LAT_KEYS = [
    "lat",
    "latitude",
    "위도",
    "y",
    "Y",
    "map_y",
    "wgs84_y",
]

LNG_KEYS = [
    "lng",
    "lon",
    "longitude",
    "경도",
    "x",
    "X",
    "map_x",
    "wgs84_x",
]

SOURCE_ID_KEYS = [
    "source_id",
    "id",
    "pk",
    "external_id",
    "관리번호",
    "번호",
]


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def unwrap_items(data):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ["places", "data", "items", "results", "records"]:
            value = data.get(key)

            if isinstance(value, list):
                return value

    raise ValueError("입력 JSON에서 장소 목록을 찾지 못했습니다.")


def normalize_key(key):
    return str(key).strip().lower().replace(" ", "").replace("_", "")


def flatten_dict(data, prefix=""):
    result = {}

    if not isinstance(data, dict):
        return result

    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)

        if isinstance(value, dict):
            result.update(flatten_dict(value, full_key))
        else:
            result[full_key] = value

    return result


def pick_value(record, candidate_keys):
    flat = flatten_dict(record)
    normalized_candidates = {normalize_key(key) for key in candidate_keys}

    for key, value in flat.items():
        if normalize_key(key) in normalized_candidates and value not in [None, ""]:
            return value

    for key, value in flat.items():
        last_key = key.split(".")[-1]

        if normalize_key(last_key) in normalized_candidates and value not in [None, ""]:
            return value

    return None


def to_float(value):
    if value in [None, ""]:
        return None

    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def make_safe_text(value):
    if value is None:
        return ""

    text = str(value).strip()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-zA-Z가-힣_-]", "", text)

    return text


def make_source_id(dataset, record, index):
    source_id = pick_value(record, SOURCE_ID_KEYS)

    if source_id:
        return str(source_id)

    name = pick_value(record, NAME_KEYS) or f"item{index}"
    address = pick_value(record, ADDRESS_KEYS) or ""

    safe_name = make_safe_text(name)
    safe_address = make_safe_text(address)

    if safe_address:
        return f"{dataset}_{safe_address}_{safe_name}"

    return f"{dataset}_{safe_name}_{index}"


def should_exclude(record, exclude_keywords):
    if not exclude_keywords:
        return False

    text = json.dumps(record, ensure_ascii=False)

    return any(keyword in text for keyword in exclude_keywords)


def build_place_candidate(dataset, category, record, index):
    name = pick_value(record, NAME_KEYS)
    address = pick_value(record, ADDRESS_KEYS)
    lat = to_float(pick_value(record, LAT_KEYS))
    lng = to_float(pick_value(record, LNG_KEYS))

    return {
        "source_id": make_source_id(dataset, record, index),
        "name": str(name).strip() if name else f"{category}_{index}",
        "category": category,
        "address": str(address).strip() if address else "",
        "lat": lat,
        "lng": lng,
    }


def main():
    parser = argparse.ArgumentParser(
        description="카카오 매칭 제외 데이터셋을 원본 cleaned 파일에서 바로 db_ready 파일로 변환합니다."
    )

    parser.add_argument(
        "--dataset",
        required=True,
        choices=list(DATASET_CONFIGS.keys()),
        help="처리할 데이터셋 이름",
    )

    args = parser.parse_args()

    config = DATASET_CONFIGS[args.dataset]

    input_path = config["input_path"]
    category = config["category"]
    exclude_keywords = config["exclude_keywords"]

    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾지 못했습니다: {input_path}")

    raw_data = load_json(input_path)
    items = unwrap_items(raw_data)

    place_candidates = []
    excluded_count = 0
    missing_coord_count = 0

    for index, record in enumerate(items):
        if should_exclude(record, exclude_keywords):
            excluded_count += 1
            continue

        item = build_place_candidate(
            dataset=args.dataset,
            category=category,
            record=record,
            index=index,
        )

        if item["lat"] is None or item["lng"] is None:
            missing_coord_count += 1
            continue

        place_candidates.append(item)

    result = {
        "dataset": args.dataset,
        "category": category,
        "purpose": "db_ready",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": str(input_path),
        "summary": {
            "source_total": len(items),
            "external_place_count": 0,
            "place_candidate_count": len(place_candidates),
            "excluded_count": excluded_count,
            "missing_coord_count": missing_coord_count,
            "db_ready_count": len(place_candidates),
        },
        "external_places": [],
        "place_candidates": place_candidates,
    }

    output_path = OUTPUT_DIR / f"{args.dataset}_db_ready.json"
    save_json(output_path, result)

    print("완료")
    print(f"dataset: {args.dataset}")
    print(f"출력 파일: {output_path}")
    print(f"source_total: {len(items)}")
    print(f"place_candidates: {len(place_candidates)}")
    print(f"excluded: {excluded_count}")
    print(f"missing_coord 제외: {missing_coord_count}")


if __name__ == "__main__":
    main()