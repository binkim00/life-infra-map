import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "outputs" / "cafe_external_place_tags_seed.json"

OUTPUT_PLACE_TAG_SEED_PATH = BASE_DIR / "cafe_place_tag_seed.json"
OUTPUT_SUMMARY_PATH = BASE_DIR / "cafe_place_tag_seed_summary.json"


def load_json(path, default):
    if not path.exists():
        print(f"파일 없음: {path}")
        return default

    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print(f"빈 파일: {path}")
        return default

    return json.loads(content)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (ValueError, TypeError):
        return default


def normalize_status(status):
    status = safe_str(status)

    allowed = {
        "confirmed",
        "candidate",
        "needs_verification",
        "rejected",
    }

    if status in allowed:
        return status

    return "candidate"


def normalize_source(source):
    source = safe_str(source)

    allowed = {
        "category_rule",
        "field_rule",
        "keyword_rule",
        "blog_search",
        "external_api",
        "external_data",
        "ai_suggested",
        "checked",
        "user_verified",
        "warning_tags",
    }

    if source in allowed:
        return source

    return "blog_search"


def normalize_tag_type(tag_type, tag_name):
    tag_type = safe_str(tag_type)
    tag_name = safe_str(tag_name)

    if tag_name == "웨이팅주의":
        return "warning"

    allowed = {
        "category",
        "recommendation",
        "warning",
    }

    if tag_type in allowed:
        return tag_type

    return "recommendation"


def build_place_tag_seed_row(item):
    place_source = safe_str(item.get("external_source")) or "kakao_local"
    place_external_id = safe_str(item.get("external_id"))

    place_name = safe_str(item.get("place_name"))
    category = safe_str(item.get("category")) or "cafe"
    address = safe_str(item.get("address"))

    lat = safe_float(item.get("lat"))
    lng = safe_float(item.get("lng"))

    tag_name = safe_str(item.get("tag_name"))
    tag_type = normalize_tag_type(item.get("tag_type"), tag_name)

    source = normalize_source(item.get("tag_source"))
    status = normalize_status(item.get("status"))
    confidence = safe_int(item.get("confidence"), 50)
    evidence = safe_str(item.get("evidence"))

    raw = item.get("raw", {})
    if not isinstance(raw, dict):
        raw = {"original_raw": raw}

    raw.update({
        "converted_from": "cafe_external_place_tags_seed",
        "original_external_source": item.get("external_source"),
        "original_external_id": item.get("external_id"),
        "original_tag_source": item.get("tag_source"),
        "data_note": (
            "카카오 Local API 장소 후보와 네이버 블로그 검색 결과 기반으로 생성한 "
            "카페 PlaceTag seed입니다. 블로그 기반 태그는 실제 시설 여부를 확정한 "
            "검증 태그가 아니므로 candidate 또는 needs_verification 상태로 사용합니다."
        ),
    })

    return {
        # Place 매칭/생성용
        "place_source": place_source,
        "place_external_id": place_external_id,
        "place_name": place_name,
        "category": category,
        "address": address,
        "lat": lat,
        "lng": lng,

        # Tag 생성용
        "tag_name": tag_name,
        "tag_type": tag_type,

        # PlaceTag 생성용
        "source": source,
        "status": status,
        "confidence": confidence,
        "evidence": evidence,
        "is_verified": status == "confirmed",

        # 추적용
        "raw": raw,
    }


def validate_row(row):
    if not row["place_source"]:
        return "place_source 없음"

    if not row["place_external_id"]:
        return "place_external_id 없음"

    if not row["place_name"]:
        return "place_name 없음"

    if row["lat"] is None or row["lng"] is None:
        return "좌표 없음"

    if not row["tag_name"]:
        return "tag_name 없음"

    return None


def build_summary(input_rows, seed_rows, skipped):
    place_keys = set()
    tag_counter = Counter()
    source_counter = Counter()
    status_counter = Counter()
    tag_type_counter = Counter()
    category_counter = Counter()
    region_counter = Counter()

    for row in seed_rows:
        place_keys.add((row["place_source"], row["place_external_id"]))
        tag_counter[row["tag_name"]] += 1
        source_counter[row["source"]] += 1
        status_counter[row["status"]] += 1
        tag_type_counter[row["tag_type"]] += 1
        category_counter[row["category"]] += 1

        address = row.get("address", "")
        region = "미상"

        if address.startswith("부산 "):
            parts = address.split()
            if len(parts) >= 2:
                region = parts[1]

        region_counter[region] += 1

    skipped_counter = Counter(item["reason"] for item in skipped)

    return {
        "input": {
            "input_path": str(INPUT_PATH),
            "input_row_count": len(input_rows),
        },
        "output": {
            "place_tag_seed_path": str(OUTPUT_PLACE_TAG_SEED_PATH),
            "summary_path": str(OUTPUT_SUMMARY_PATH),
            "place_count": len(place_keys),
            "place_tag_seed_row_count": len(seed_rows),
            "skipped_count": len(skipped),
        },
        "tag_counts": dict(tag_counter.most_common()),
        "source_counts": dict(source_counter.most_common()),
        "status_counts": dict(status_counter.most_common()),
        "tag_type_counts": dict(tag_type_counter.most_common()),
        "category_counts": dict(category_counter.most_common()),
        "region_counts_from_address": dict(region_counter.most_common()),
        "skipped_reason_counts": dict(skipped_counter.most_common()),
        "data_note": (
            "이 파일은 카페 Place에 붙일 PlaceTag seed입니다. "
            "place_source는 kakao_local, place_external_id는 카카오 장소 ID입니다. "
            "source가 blog_search인 태그는 네이버 블로그 검색 기반 후보 태그이며, "
            "실제 시설 여부를 확정한 검증 태그가 아닙니다."
        ),
    }


def main():
    input_rows = load_json(INPUT_PATH, [])

    if not input_rows:
        print("입력 데이터가 없습니다.")
        return

    seed_rows = []
    skipped = []
    seen = set()

    for item in input_rows:
        row = build_place_tag_seed_row(item)
        reason = validate_row(row)

        if reason:
            skipped.append({
                "reason": reason,
                "raw": item,
            })
            continue

        key = (
            row["place_source"],
            row["place_external_id"],
            row["tag_name"],
            row["source"],
        )

        if key in seen:
            skipped.append({
                "reason": "place_tag 중복",
                "place_source": row["place_source"],
                "place_external_id": row["place_external_id"],
                "tag_name": row["tag_name"],
                "source": row["source"],
            })
            continue

        seen.add(key)
        seed_rows.append(row)

    seed_rows.sort(
        key=lambda row: (
            row["place_name"],
            row["place_external_id"],
            row["tag_name"],
            row["source"],
        )
    )

    summary = build_summary(
        input_rows=input_rows,
        seed_rows=seed_rows,
        skipped=skipped,
    )

    save_json(OUTPUT_PLACE_TAG_SEED_PATH, seed_rows)
    save_json(OUTPUT_SUMMARY_PATH, summary)

    print("==============================")
    print("카페 PlaceTag seed 변환 완료")
    print("==============================")
    print(f"입력 row 수: {len(input_rows)}")
    print(f"PlaceTag seed 장소 수: {summary['output']['place_count']}")
    print(f"PlaceTag seed row 수: {summary['output']['place_tag_seed_row_count']}")
    print(f"스킵 수: {summary['output']['skipped_count']}")
    print()
    print(f"PlaceTag seed 파일: {OUTPUT_PLACE_TAG_SEED_PATH}")
    print(f"요약 파일: {OUTPUT_SUMMARY_PATH}")
    print()
    print("source별 개수")
    for source, count in summary["source_counts"].items():
        print(f"- {source}: {count}")

    print()
    print("status별 개수")
    for status, count in summary["status_counts"].items():
        print(f"- {status}: {count}")

    print()
    print("태그별 개수")
    for tag, count in summary["tag_counts"].items():
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()