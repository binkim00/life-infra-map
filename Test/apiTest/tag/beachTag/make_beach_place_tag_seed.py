import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "beach_tag_results.json"
SKIPPED_INPUT_PATH = BASE_DIR / "beach_tag_skipped_results.json"

OUTPUT_PLACE_TAG_SEED_PATH = BASE_DIR / "beach_place_tag_seed.json"
OUTPUT_SUMMARY_PATH = BASE_DIR / "beach_place_tag_seed_summary.json"


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


def build_place_external_id(item):
    sido = safe_str(item.get("sido_nm"))
    gugun = safe_str(item.get("gugun_nm"))
    name = safe_str(item.get("sta_nm"))

    if not name:
        return ""

    return f"beach_{sido}_{gugun}_{name}"


def get_address(item):
    sido = safe_str(item.get("sido_nm"))
    gugun = safe_str(item.get("gugun_nm"))
    return " ".join([part for part in [sido, gugun] if part])


def normalize_tag_name(tag_name):
    tag_name = safe_str(tag_name)

    tag_map = {
        "산책": "산책좋음",
        "힐링": "힐링",
        "드라이브": "드라이브목적지",
        "사진명소": "사진찍기좋음",
        "데이트": "데이트좋음",
        "가족방문": "가족방문좋음",
        "야경": "야경",
        "물놀이": "물놀이",
        "반려동물": "반려동물동반",
        "캠핑": "캠핑",
        "서핑": "서핑",
        "해수욕장": "해수욕장",
        "바다": "바다",
        "모래해변": "모래해변",
        "자갈해변": "자갈해변",
        "몽돌해변": "몽돌해변",
        "긴해변": "긴해변",
        "넓은해변": "넓은해변",
    }

    return tag_map.get(tag_name, tag_name)


def get_tag_type(tag_name):
    category_tags = {
        "해수욕장",
        "바다",
        "모래해변",
        "자갈해변",
        "몽돌해변",
    }

    if tag_name in category_tags:
        return "category"

    return "recommendation"


def make_evidence(tag_name, source_type, item):
    if source_type == "category_rule":
        return "해수욕장 카테고리 기본 태그"

    if source_type == "field_rule":
        return "해수욕장 원본 필드 기반 태그"

    if source_type == "blog_search":
        matched_keywords = item.get("matched_keywords", {}).get(tag_name, [])
        blog_count = item.get("blog_count", 0)
        search_query = item.get("search_query", "")

        parts = []

        if search_query:
            parts.append(f"검색어: {search_query}")

        if blog_count:
            parts.append(f"블로그 검색 결과 {blog_count}건")

        if matched_keywords:
            parts.append("매칭 키워드: " + ", ".join(matched_keywords))

        if parts:
            return " / ".join(parts)

        return "블로그 검색 결과 기반 해수욕장 태그 후보"

    return "해수욕장 태그 후보"


def make_seed_row(item, tag_name, source_type, status, confidence):
    normalized_tag_name = normalize_tag_name(tag_name)

    return {
        # Place 매칭용
        "place_source": "beach_api",
        "place_external_id": build_place_external_id(item),
        "place_name": safe_str(item.get("sta_nm")),
        "category": "beach",
        "address": get_address(item),
        "lat": safe_float(item.get("lat")),
        "lng": safe_float(item.get("lon")),

        # Tag 생성용
        "tag_name": normalized_tag_name,
        "tag_type": get_tag_type(normalized_tag_name),

        # PlaceTag 생성용
        "source": source_type,
        "status": status,
        "confidence": confidence,
        "evidence": make_evidence(tag_name, source_type, item),
        "is_verified": status == "confirmed",

        # 추적용
        "raw": {
            "num": item.get("num"),
            "sido_nm": item.get("sido_nm"),
            "gugun_nm": item.get("gugun_nm"),
            "sta_nm": item.get("sta_nm"),
            "beach_knd": item.get("beach_knd"),
            "beach_len": item.get("beach_len"),
            "beach_wid": item.get("beach_wid"),
            "original_tag_name": tag_name,
            "normalized_tag_name": normalized_tag_name,
            "source_type": source_type,
            "blog_count": item.get("blog_count"),
            "search_query": item.get("search_query"),
            "matched_keywords": item.get("matched_keywords", {}).get(tag_name, []),
            "data_note": (
                "해수욕장 데이터의 기본/원본 필드/블로그 검색 결과를 기반으로 만든 "
                "PlaceTag seed입니다. 블로그 기반 태그는 실제 시설 여부를 확정한 "
                "검증 태그가 아니므로 candidate 상태로 사용합니다."
            ),
        },
    }


def build_seed_rows(items):
    rows = []
    skipped = []
    seen = set()

    for item in items:
        place_external_id = build_place_external_id(item)
        place_name = safe_str(item.get("sta_nm"))
        lat = safe_float(item.get("lat"))
        lng = safe_float(item.get("lon"))

        if not place_external_id or not place_name or lat is None or lng is None:
            skipped.append({
                "reason": "place_external_id_or_name_or_coordinate_missing",
                "place_external_id": place_external_id,
                "place_name": place_name,
                "lat": lat,
                "lng": lng,
                "raw": item,
            })
            continue

        tag_groups = [
            {
                "tags": item.get("default_tags", []),
                "source": "category_rule",
                "status": "confirmed",
                "confidence": 90,
            },
            {
                "tags": item.get("original_tags", []),
                "source": "field_rule",
                "status": "candidate",
                "confidence": 70,
            },
            {
                "tags": item.get("blog_tags", []),
                "source": "blog_search",
                "status": "candidate",
                "confidence": 60,
            },
        ]

        for group in tag_groups:
            for tag_name in group["tags"]:
                tag_name = safe_str(tag_name)

                if not tag_name:
                    continue

                normalized_tag_name = normalize_tag_name(tag_name)

                key = (
                    "beach_api",
                    place_external_id,
                    normalized_tag_name,
                    group["source"],
                )

                if key in seen:
                    continue

                seen.add(key)

                rows.append(
                    make_seed_row(
                        item=item,
                        tag_name=tag_name,
                        source_type=group["source"],
                        status=group["status"],
                        confidence=group["confidence"],
                    )
                )

    return rows, skipped


def build_summary(items, skipped_input_items, seed_rows, skipped):
    tag_counter = Counter()
    source_counter = Counter()
    status_counter = Counter()
    region_counter = Counter()
    place_keys = set()

    for item in items:
        region = f"{safe_str(item.get('sido_nm'))} {safe_str(item.get('gugun_nm'))}".strip()
        region_counter[region] += 1

    for row in seed_rows:
        place_keys.add((row["place_source"], row["place_external_id"]))
        tag_counter[row["tag_name"]] += 1
        source_counter[row["source"]] += 1
        status_counter[row["status"]] += 1

    return {
        "input": {
            "input_path": str(INPUT_PATH),
            "skipped_input_path": str(SKIPPED_INPUT_PATH),
            "input_beach_count": len(items),
            "input_skipped_count": len(skipped_input_items),
        },
        "output": {
            "place_tag_seed_place_count": len(place_keys),
            "place_tag_seed_row_count": len(seed_rows),
            "skipped_count": len(skipped),
            "place_tag_seed_path": str(OUTPUT_PLACE_TAG_SEED_PATH),
            "summary_path": str(OUTPUT_SUMMARY_PATH),
        },
        "tag_counts": dict(tag_counter.most_common()),
        "source_counts": dict(source_counter.most_common()),
        "status_counts": dict(status_counter.most_common()),
        "region_counts": dict(region_counter.most_common()),
        "skipped": skipped,
        "data_note": (
            "이 파일은 해수욕장 Place에 붙일 PlaceTag seed입니다. "
            "category_rule은 기본 카테고리 태그, field_rule은 원본 필드 기반 후보 태그, "
            "blog_search는 블로그 검색 기반 후보 태그입니다."
        ),
    }


def main():
    items = load_json(INPUT_PATH, [])
    skipped_input_items = load_json(SKIPPED_INPUT_PATH, [])

    if not items:
        print("해수욕장 태그 결과 데이터가 없습니다.")
        return

    seed_rows, skipped = build_seed_rows(items)

    summary = build_summary(
        items=items,
        skipped_input_items=skipped_input_items,
        seed_rows=seed_rows,
        skipped=skipped,
    )

    save_json(OUTPUT_PLACE_TAG_SEED_PATH, seed_rows)
    save_json(OUTPUT_SUMMARY_PATH, summary)

    print("해수욕장 PlaceTag seed 생성 완료")
    print(f"입력 해수욕장 수: {summary['input']['input_beach_count']}")
    print(f"입력 스킵 수: {summary['input']['input_skipped_count']}")
    print(f"PlaceTag seed 장소 수: {summary['output']['place_tag_seed_place_count']}")
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
    print("태그별 개수")
    for tag, count in summary["tag_counts"].items():
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()