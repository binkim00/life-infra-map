import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

ORIGINAL_INPUT_PATH = BASE_DIR / "park_original_tag_results.json"
BLOG_INPUT_PATH = BASE_DIR / "park_blog_tag_results.json"

OUTPUT_PLACE_TAG_SEED_PATH = BASE_DIR / "park_place_tag_seed.json"
OUTPUT_SUMMARY_PATH = BASE_DIR / "park_place_tag_seed_summary.json"


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
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def make_place_key(item):
    """
    original 결과와 blog 결과를 같은 공원으로 매칭하기 위한 키입니다.
    관리번호가 있으면 관리번호 우선, 없으면 이름+좌표를 사용합니다.
    """
    management_no = safe_str(item.get("management_no"))
    provider_code = safe_str(item.get("provider_code"))

    if management_no or provider_code:
        return f"{provider_code}_{management_no}"

    name = safe_str(item.get("name"))
    lat = safe_str(item.get("lat"))
    lon = safe_str(item.get("lon"))

    return f"{name}_{lat}_{lon}"


def build_place_external_id(item):
    """
    clean_citypark.py의 external_id 생성 규칙과 맞춥니다.
    clean_citypark.py는 provider_code 또는 manage_no가 있으면
    citypark_{provider_code}_{manage_no} 형식으로 만듭니다.
    """
    management_no = safe_str(item.get("management_no"))
    provider_code = safe_str(item.get("provider_code"))

    if management_no or provider_code:
        return f"citypark_{provider_code}_{management_no}"

    name = safe_str(item.get("name"))
    lat = safe_str(item.get("lat"))
    lon = safe_str(item.get("lon"))

    return f"citypark_{name}_{lat}_{lon}"


def get_address(item):
    return safe_str(item.get("road_address")) or safe_str(item.get("lot_address"))


def normalize_tag_name(tag_name):
    """
    기존 공원 태그명을 서비스 태그명과 최대한 맞춥니다.
    너무 세부적인 시설 태그는 그대로 둡니다.
    """
    tag_name = safe_str(tag_name)

    tag_map = {
        "산책": "산책좋음",
        "휴식": "잠깐쉬기좋음",
        "잠깐쉬기": "잠깐쉬기좋음",
        "힐링": "힐링",
        "사진명소": "사진찍기좋음",
        "데이트": "데이트좋음",
        "야경": "야경",
        "드라이브": "드라이브목적지",
        "가족방문": "가족방문좋음",
        "아이동반": "아이와가기좋음",
        "운동": "운동하기좋음",
        "체육활동": "운동하기좋음",
        "조용한": "조용한",
        "피크닉": "피크닉",
        "반려동물": "반려동물동반",
        "벚꽃": "벚꽃",
        "단풍": "단풍",
        "호수": "호수",
        "물가산책": "수변산책",
    }

    return tag_map.get(tag_name, tag_name)


def get_tag_type(tag_name):
    category_tags = {
        "공원",
        "야외",
        "도시공원",
        "근린공원",
        "어린이공원",
        "소공원",
        "수변공원",
        "문화공원",
        "체육공원",
        "역사공원",
        "묘지공원",
        "도시농업공원",
        "가로공원",
    }

    if tag_name in category_tags:
        return "category"

    return "recommendation"


def make_evidence(tag_name, source_type, item):
    if source_type == "category_rule":
        return "공원 카테고리 기본 태그"

    if source_type == "field_rule":
        return "도시공원 원본 필드 기반 태그"

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

        return "블로그 검색 결과 기반 공원 태그 후보"

    return "공원 태그 후보"


def make_seed_row(item, tag_name, source_type, status, confidence):
    normalized_tag_name = normalize_tag_name(tag_name)

    return {
        # Place 매칭용
        "place_source": "citypark_standard",
        "place_external_id": build_place_external_id(item),
        "place_name": safe_str(item.get("name")),
        "category": "city_park",
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
            "management_no": safe_str(item.get("management_no")),
            "provider_code": safe_str(item.get("provider_code")),
            "park_type": safe_str(item.get("park_type")),
            "area": item.get("area"),
            "original_tag_name": tag_name,
            "normalized_tag_name": normalized_tag_name,
            "source_type": source_type,
            "blog_count": item.get("blog_count"),
            "search_query": item.get("search_query"),
            "matched_keywords": item.get("matched_keywords", {}).get(tag_name, []),
            "data_note": (
                "도시공원 데이터의 기본/원본 필드/블로그 검색 결과를 기반으로 만든 "
                "PlaceTag seed입니다. 블로그 기반 태그는 실제 시설 여부를 확정한 "
                "검증 태그가 아니므로 candidate 상태로 사용합니다."
            ),
        },
    }


def merge_blog_data(original_items, blog_items):
    blog_map = {
        make_place_key(item): item
        for item in blog_items
    }

    merged = []

    for item in original_items:
        key = make_place_key(item)
        blog_item = blog_map.get(key)

        merged_item = dict(item)

        if blog_item:
            merged_item["blog_tags"] = blog_item.get("blog_tags", [])
            merged_item["matched_keywords"] = blog_item.get("matched_keywords", {})
            merged_item["blog_count"] = blog_item.get("blog_count", 0)
            merged_item["search_query"] = blog_item.get("search_query", "")
        else:
            merged_item["blog_tags"] = []
            merged_item["matched_keywords"] = {}
            merged_item["blog_count"] = 0
            merged_item["search_query"] = ""

        merged.append(merged_item)

    return merged


def build_seed_rows(merged_items):
    rows = []
    seen = set()
    skipped = []

    for item in merged_items:
        place_external_id = build_place_external_id(item)
        place_name = safe_str(item.get("name"))

        if not place_external_id or not place_name:
            skipped.append({
                "reason": "place_external_id_or_name_missing",
                "name": place_name,
                "place_external_id": place_external_id,
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
                    "citypark_standard",
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


def build_summary(original_items, blog_items, seed_rows, skipped):
    tag_counter = Counter()
    source_counter = Counter()
    status_counter = Counter()
    place_keys = set()

    for row in seed_rows:
        place_keys.add((row["place_source"], row["place_external_id"]))
        tag_counter[row["tag_name"]] += 1
        source_counter[row["source"]] += 1
        status_counter[row["status"]] += 1

    return {
        "input": {
            "original_input_path": str(ORIGINAL_INPUT_PATH),
            "blog_input_path": str(BLOG_INPUT_PATH),
            "original_place_count": len(original_items),
            "blog_place_count": len(blog_items),
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
        "skipped": skipped,
        "data_note": (
            "이 파일은 도시공원 Place에 붙일 PlaceTag seed입니다. "
            "category_rule은 기본 카테고리 태그, field_rule은 원본 필드 기반 후보 태그, "
            "blog_search는 블로그 검색 기반 후보 태그입니다."
        ),
    }


def main():
    original_items = load_json(ORIGINAL_INPUT_PATH, [])
    blog_items = load_json(BLOG_INPUT_PATH, [])

    if not original_items:
        print("공원 원본 태그 결과가 없습니다. 먼저 make_park_original_tags.py를 실행해주세요.")
        return

    merged_items = merge_blog_data(original_items, blog_items)
    seed_rows, skipped = build_seed_rows(merged_items)

    summary = build_summary(
        original_items=original_items,
        blog_items=blog_items,
        seed_rows=seed_rows,
        skipped=skipped,
    )

    save_json(OUTPUT_PLACE_TAG_SEED_PATH, seed_rows)
    save_json(OUTPUT_SUMMARY_PATH, summary)

    print("공원 PlaceTag seed 생성 완료")
    print(f"원본 공원 수: {summary['input']['original_place_count']}")
    print(f"블로그 태그 공원 수: {summary['input']['blog_place_count']}")
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
    print("상위 태그")
    for tag, count in list(summary["tag_counts"].items())[:20]:
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()