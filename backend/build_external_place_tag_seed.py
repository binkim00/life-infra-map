import argparse
import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PLACE_DIR = BASE_DIR / "recommendations" / "fixtures" / "places"
TAG_DIR = BASE_DIR / "recommendations" / "fixtures" / "tags"
OUTPUT_DIR = TAG_DIR / "external"


DATASET_CONFIGS = {
    "beach": {
        "place_file": "beach_db_ready.json",
        "tag_file": "beach_place_tag_seed.json",
        "output_file": "beach_external_place_tags_seed.json",
        "original_source": "beach_api",
        "category": "beach",
    },
    "park": {
        "place_file": "citypark_db_ready.json",
        "tag_file": "park_place_tag_seed.json",
        "output_file": "park_external_place_tags_seed.json",
        "original_source": "citypark_standard",
        "category": "city_park",
    },
    "parking": {
        "place_file": "parking_db_ready.json",
        "tag_file": "parking_place_tag_seed.json",
        "output_file": "parking_external_place_tags_seed.json",
        "original_source": "public_parking_standard",
        "category": "parking",
    },
    "tourism": {
        "place_file": "tourism_db_ready.json",
        "tag_file": "tourist_spot_busan_place_tag_seed.json",
        "output_file": "tourism_external_place_tags_seed.json",
        "original_source": "tour_api",
        "category": "tourism",
    },
    "shelter": {
        "place_file": "shelter_db_ready.json",
        "tag_file": "shelter_place_tag_seed.json",
        "output_file": "shelter_external_place_tags_seed.json",
        "original_source": "heat_shelter_api",
        "category": "shelter",
    },
}


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    text = path.read_text(encoding="utf-8")

    if text.startswith("version https://git-lfs.github.com/spec/v1"):
        raise RuntimeError(
            f"Git LFS 실제 파일이 아니라 포인터 파일입니다: {path}\n"
            "git lfs pull 실행 후 다시 시도해 주세요."
        )

    return json.loads(text)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_text(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in ["nan", "none", "null"]:
        return ""

    return value


def to_float(value):
    if value in [None, ""]:
        return None

    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def pick(row, keys):
    if not isinstance(row, dict):
        return ""

    for key in keys:
        value = row.get(key)
        if value not in [None, "", [], {}]:
            return value

    return ""


def normalize_tourism_id(original_source, external_id):
    external_id = clean_text(external_id)

    if (
        original_source == "tour_api"
        and external_id
        and not external_id.startswith("tourism_")
    ):
        return f"tourism_12_{external_id}"

    return external_id


def get_original_external_id(row, original_source):
    value = (
        pick(row, [
            "source_id",
            "original_external_id",
            "place_external_id",
            "external_id",
            "contentid",
            "content_id",
            "id",
        ])
        or pick(row.get("source", {}), [
            "source_id",
            "external_id",
            "place_external_id",
            "id",
            "contentid",
            "content_id",
        ])
        or pick(row.get("original", {}), [
            "source_id",
            "external_id",
            "place_external_id",
            "id",
            "contentid",
            "content_id",
        ])
    )

    return normalize_tourism_id(original_source, value)


def get_kakao_external_id(row):
    value = (
        pick(row, [
            "external_place_id",
            "kakao_place_id",
            "kakao_id",
            "map_external_id",
        ])
        or pick(row.get("kakao", {}), [
            "external_place_id",
            "kakao_place_id",
            "id",
        ])
        or pick(row.get("best_candidate", {}).get("kakao", {}), [
            "external_place_id",
            "kakao_place_id",
            "id",
        ])
    )

    return clean_text(value)


def get_kakao_place_name(row, fallback=""):
    value = (
        pick(row, [
            "external_place_name",
            "kakao_place_name",
            "map_place_name",
            "place_name",
            "name",
        ])
        or pick(row.get("kakao", {}), [
            "place_name",
            "external_place_name",
            "name",
        ])
        or pick(row.get("best_candidate", {}).get("kakao", {}), [
            "place_name",
            "external_place_name",
            "name",
        ])
    )

    return clean_text(value) or fallback


def get_address(external_row, tag_row):
    value = (
        pick(external_row, [
            "address",
            "road_address",
            "road_address_name",
            "address_name",
            "jibun_address",
            "addr",
        ])
        or pick(external_row.get("kakao", {}), [
            "road_address_name",
            "address_name",
            "address",
        ])
        or pick(external_row.get("best_candidate", {}).get("kakao", {}), [
            "road_address_name",
            "address_name",
            "address",
        ])
        or tag_row.get("address")
    )

    return clean_text(value)


def get_lat(external_row, tag_row):
    value = (
        pick(external_row, ["lat", "latitude", "y", "mapy"])
        or pick(external_row.get("kakao", {}), ["y", "lat", "latitude"])
        or pick(external_row.get("best_candidate", {}).get("kakao", {}), ["y", "lat", "latitude"])
        or tag_row.get("lat")
    )

    return to_float(value)


def get_lng(external_row, tag_row):
    value = (
        pick(external_row, ["lng", "lon", "longitude", "x", "mapx"])
        or pick(external_row.get("kakao", {}), ["x", "lng", "lon", "longitude"])
        or pick(external_row.get("best_candidate", {}).get("kakao", {}), ["x", "lng", "lon", "longitude"])
        or tag_row.get("lng")
    )

    return to_float(value)


def get_match_score(row):
    value = (
        row.get("match_score")
        or pick(row.get("score", {}), ["total_score", "match_score"])
        or pick(row.get("best_candidate", {}).get("score", {}), ["total_score", "match_score"])
    )

    return to_float(value) or 0


def normalize_tag_source(row):
    return clean_text(row.get("source")) or clean_text(row.get("tag_source")) or "external_data"


def build_external_map(place_data, config):
    external_places = []

    if isinstance(place_data, dict):
        external_places = place_data.get("external_places", []) or []

    if not isinstance(external_places, list):
        raise ValueError("external_places가 list 구조가 아닙니다.")

    external_map = {}
    skipped = []

    for row in external_places:
        if not isinstance(row, dict):
            continue

        original_external_id = get_original_external_id(row, config["original_source"])
        kakao_external_id = get_kakao_external_id(row)

        if not original_external_id or not kakao_external_id:
            skipped.append({
                "reason": "original_id_or_kakao_id_missing",
                "row": row,
            })
            continue

        key = (config["original_source"], original_external_id)

        if key not in external_map:
            external_map[key] = row
            continue

        if get_match_score(row) > get_match_score(external_map[key]):
            external_map[key] = row

    return external_map, skipped


def build_external_seed_row(tag_row, external_row, config):
    original_source = clean_text(tag_row.get("place_source")) or config["original_source"]
    original_external_id = clean_text(tag_row.get("place_external_id"))
    original_place_name = clean_text(tag_row.get("place_name"))

    return {
        "external_source": "kakao_local",
        "external_id": get_kakao_external_id(external_row),
        "place_name": get_kakao_place_name(external_row, fallback=original_place_name),
        "category": config["category"],
        "address": get_address(external_row, tag_row),
        "lat": get_lat(external_row, tag_row),
        "lng": get_lng(external_row, tag_row),

        "tag_name": clean_text(tag_row.get("tag_name")),
        "tag_type": clean_text(tag_row.get("tag_type")) or "recommendation",
        "tag_source": normalize_tag_source(tag_row),
        "status": clean_text(tag_row.get("status")) or "candidate",
        "confidence": tag_row.get("confidence", 50),
        "evidence": clean_text(tag_row.get("evidence")),
        "is_verified": bool(tag_row.get("is_verified")) or clean_text(tag_row.get("status")) == "confirmed",

        "raw": {
            "converted_from": "external_places",
            "dataset": config["category"],
            "original_source": original_source,
            "original_external_id": original_external_id,
            "original_place_name": original_place_name,
            "external_place": external_row,
            "original_tag_raw": tag_row.get("raw", {}),
            "data_note": (
                "원본 장소가 지도 API에서 검색된 external_places 항목이므로 "
                "kakao_local 장소 ID 기준으로 변환한 PlaceTag seed입니다."
            ),
        },
    }


def validate_external_seed_row(row):
    if not row["external_id"]:
        return "external_id_missing"
    if not row["place_name"]:
        return "place_name_missing"
    if row["lat"] is None or row["lng"] is None:
        return "coordinate_missing"
    if not row["tag_name"]:
        return "tag_name_missing"
    return None


def build_dataset(config):
    place_path = PLACE_DIR / config["place_file"]
    tag_path = TAG_DIR / config["tag_file"]
    output_path = OUTPUT_DIR / config["output_file"]
    review_path = OUTPUT_DIR / config["output_file"].replace(".json", "_unmatched_review.json")
    summary_path = OUTPUT_DIR / config["output_file"].replace(".json", "_summary.json")

    place_data = load_json(place_path)
    tag_rows = load_json(tag_path)

    if not isinstance(tag_rows, list):
        raise ValueError(f"태그 seed 파일은 list 구조여야 합니다: {tag_path}")

    external_map, external_skipped = build_external_map(place_data, config)

    seed_rows = []
    unmatched_rows = []
    skipped_rows = []
    seen = set()

    for tag_row in tag_rows:
        if not isinstance(tag_row, dict):
            continue

        original_source = clean_text(tag_row.get("place_source"))
        original_external_id = clean_text(tag_row.get("place_external_id"))
        key = (original_source, original_external_id)

        external_row = external_map.get(key)

        if not external_row:
            unmatched_rows.append({
                "reason": "external_place_not_found",
                "place_source": original_source,
                "place_external_id": original_external_id,
                "place_name": clean_text(tag_row.get("place_name")),
                "tag_name": clean_text(tag_row.get("tag_name")),
            })
            continue

        seed_row = build_external_seed_row(tag_row, external_row, config)
        invalid_reason = validate_external_seed_row(seed_row)

        if invalid_reason:
            skipped_rows.append({
                "reason": invalid_reason,
                "place_source": original_source,
                "place_external_id": original_external_id,
                "place_name": clean_text(tag_row.get("place_name")),
                "tag_name": clean_text(tag_row.get("tag_name")),
            })
            continue

        row_key = (
            seed_row["external_source"],
            seed_row["external_id"],
            seed_row["tag_name"],
            seed_row["tag_source"],
        )

        if row_key in seen:
            continue

        seen.add(row_key)
        seed_rows.append(seed_row)

    tag_counter = Counter(row["tag_name"] for row in seed_rows)
    source_counter = Counter(row["tag_source"] for row in seed_rows)
    status_counter = Counter(row["status"] for row in seed_rows)
    place_counter = Counter(row["external_id"] for row in seed_rows)

    summary = {
        "input": {
            "place_file": str(place_path),
            "tag_file": str(tag_path),
            "tag_row_count": len(tag_rows),
            "external_place_count": len(external_map),
            "external_skipped_count": len(external_skipped),
        },
        "output": {
            "external_place_tag_seed_path": str(output_path),
            "external_place_tag_seed_row_count": len(seed_rows),
            "external_place_count_with_tags": len(place_counter),
            "unmatched_tag_row_count": len(unmatched_rows),
            "skipped_tag_row_count": len(skipped_rows),
            "review_path": str(review_path),
            "summary_path": str(summary_path),
        },
        "tag_counts": dict(tag_counter.most_common()),
        "source_counts": dict(source_counter.most_common()),
        "status_counts": dict(status_counter.most_common()),
        "external_skipped_samples": external_skipped[:50],
        "skipped_samples": skipped_rows[:50],
    }

    save_json(output_path, seed_rows)
    save_json(review_path, {
        "unmatched_rows": unmatched_rows[:1000],
        "unmatched_count": len(unmatched_rows),
        "skipped_rows": skipped_rows[:1000],
        "skipped_count": len(skipped_rows),
        "note": "샘플은 최대 1000개만 저장합니다. 원본 태그 파일은 삭제하지 않습니다.",
    })
    save_json(summary_path, summary)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="external_places에 매칭된 태그를 kakao_local 기준 external PlaceTag seed로 변환합니다."
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=["all"],
        choices=list(DATASET_CONFIGS.keys()) + ["all"],
        help="변환할 데이터셋입니다. 예: --only beach park parking tourism",
    )

    args = parser.parse_args()

    selected = args.only
    if "all" in selected:
        selected = list(DATASET_CONFIGS.keys())

    all_summary = {}

    for key in selected:
        print(f"\n=== {key} ===")
        summary = build_dataset(DATASET_CONFIGS[key])
        all_summary[key] = summary

        print(f"external place 수: {summary['input']['external_place_count']:,}")
        print(f"입력 tag row: {summary['input']['tag_row_count']:,}")
        print(f"변환 tag row: {summary['output']['external_place_tag_seed_row_count']:,}")
        print(f"태그가 붙은 kakao place 수: {summary['output']['external_place_count_with_tags']:,}")
        print(f"unmatched tag row: {summary['output']['unmatched_tag_row_count']:,}")
        print(f"skipped tag row: {summary['output']['skipped_tag_row_count']:,}")
        print(f"출력: {summary['output']['external_place_tag_seed_path']}")

    all_summary_path = OUTPUT_DIR / "_external_place_tag_seed_summary.json"
    save_json(all_summary_path, all_summary)

    print(f"\n전체 요약 저장 완료: {all_summary_path}")


if __name__ == "__main__":
    main()