import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "tourist_spot_busan_final_tag_candidates.json"

OUTPUT_CANDIDATES_PATH = BASE_DIR / "tourist_spot_busan_blog_tag_save_candidates.json"
OUTPUT_PLACE_TAG_SEED_PATH = BASE_DIR / "tourist_spot_busan_place_tag_seed.json"
OUTPUT_SUMMARY_PATH = BASE_DIR / "tourist_spot_busan_place_tag_seed_summary.json"

MIN_CONFIDENCE = 0.6


TAG_NAME_MAP = {
    "walk_good": "산책좋음",
    "healing": "힐링",
    "night_view": "야경",
    "drive_good": "드라이브목적지",
    "solo_good": "혼자이용좋음",
    "short_rest": "잠깐쉬기좋음",
    "photo_good": "사진찍기좋음",
    "date_good": "데이트좋음",
}


def load_json(path):
    if not path.exists():
        print(f"파일 없음: {path}")
        return {
            "final_candidates": [],
            "excluded_candidates": [],
            "summary": {},
        }

    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print(f"빈 파일: {path}")
        return {
            "final_candidates": [],
            "excluded_candidates": [],
            "summary": {},
        }

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


def normalize_confidence(value):
    try:
        confidence = float(value)
    except (ValueError, TypeError):
        return 50

    if confidence <= 1:
        confidence = confidence * 100

    return max(0, min(100, round(confidence)))


def build_place_external_id(place):
    contentid = safe_str(place.get("contentid"))

    if not contentid:
        return ""

    # 현재 파일은 관광지 contenttypeid=12 기준으로 만들어진 후보라서 12로 고정합니다.
    return f"tourism_12_{contentid}"


def convert_tag_name(tag):
    tag = safe_str(tag)
    return TAG_NAME_MAP.get(tag, tag)


def get_tag_type(tag_name):
    return "recommendation"


def build_evidence(source):
    matched_keywords = source.get("matched_keywords", [])
    related_blog_count = source.get("related_blog_count", 0)

    parts = []

    if related_blog_count:
        parts.append(f"관련 블로그 글 {related_blog_count}건")

    if matched_keywords:
        parts.append("매칭 키워드: " + ", ".join(matched_keywords))

    if not parts:
        return "블로그 검색 결과 기반 관광지 태그 후보"

    return " / ".join(parts)


def make_save_candidate(place):
    filtered_sources = []
    filtered_tags = []

    for source in place.get("verified_tag_sources", []):
        raw_confidence = source.get("confidence", 0)

        try:
            confidence_float = float(raw_confidence)
        except (ValueError, TypeError):
            confidence_float = 0

        if confidence_float < MIN_CONFIDENCE:
            continue

        original_tag = safe_str(source.get("tag"))
        tag_name = convert_tag_name(original_tag)

        if not tag_name:
            continue

        filtered_source = {
            "original_tag": original_tag,
            "tag_name": tag_name,
            "tag_type": get_tag_type(tag_name),
            "source": source.get("source", "blog_search"),
            "matched_keywords": source.get("matched_keywords", []),
            "related_blog_count": source.get("related_blog_count", 0),
            "confidence": normalize_confidence(raw_confidence),
            "is_verified": bool(source.get("is_verified", False)),
        }

        filtered_sources.append(filtered_source)

        if tag_name not in filtered_tags:
            filtered_tags.append(tag_name)

    return {
        "contentid": safe_str(place.get("contentid")),
        "place_source": "tour_api",
        "place_external_id": build_place_external_id(place),
        "title": safe_str(place.get("title")),
        "addr1": safe_str(place.get("addr1")),
        "mapx": safe_str(place.get("mapx")),
        "mapy": safe_str(place.get("mapy")),
        "priority": safe_str(place.get("priority")),
        "verified_tags": filtered_tags,
        "verified_tag_sources": filtered_sources,
        "related_blog_count": place.get("related_blog_count", 0),
        "original_blog_evidence_count": place.get("original_blog_evidence_count", 0),
    }


def make_place_tag_seed_rows(candidate):
    rows = []

    place_source = candidate["place_source"]
    place_external_id = candidate["place_external_id"]
    place_name = candidate["title"]

    lat = safe_float(candidate.get("mapy"))
    lng = safe_float(candidate.get("mapx"))

    for source in candidate["verified_tag_sources"]:
        tag_name = source["tag_name"]

        row = {
            # Place 매칭용
            "place_source": place_source,
            "place_external_id": place_external_id,
            "place_name": place_name,
            "category": "tourist_spot",
            "address": candidate.get("addr1", ""),
            "lat": lat,
            "lng": lng,

            # Tag 생성용
            "tag_name": tag_name,
            "tag_type": source.get("tag_type", "recommendation"),

            # PlaceTag 생성용
            "source": "blog_search",
            "status": "candidate",
            "confidence": source.get("confidence", 50),
            "evidence": build_evidence(source),
            "is_verified": False,

            # 검수/추적용
            "raw": {
                "contentid": candidate.get("contentid", ""),
                "original_tag": source.get("original_tag", ""),
                "matched_keywords": source.get("matched_keywords", []),
                "related_blog_count": source.get("related_blog_count", 0),
                "original_blog_evidence_count": candidate.get(
                    "original_blog_evidence_count",
                    0,
                ),
                "priority": candidate.get("priority", ""),
                "data_note": (
                    "관광공사 장소 데이터에 블로그 검색 결과를 기반으로 붙이는 "
                    "추천 태그 후보입니다. 실제 장소의 성격을 확정한 검증 태그가 "
                    "아니므로 candidate 상태로 사용합니다."
                ),
            },
        }

        rows.append(row)

    return rows


def build_summary(input_places, excluded_places, save_candidates, skipped_candidates, place_tag_seed_rows):
    tag_counter = Counter()
    original_tag_counter = Counter()
    status_counter = Counter()
    priority_counter = Counter()
    confidence_bucket_counter = Counter()

    place_keys = set()

    for candidate in save_candidates:
        priority_counter[candidate.get("priority", "unknown")] += 1

    for row in place_tag_seed_rows:
        place_keys.add((row["place_source"], row["place_external_id"]))
        tag_counter[row["tag_name"]] += 1
        status_counter[row["status"]] += 1

        original_tag = row["raw"].get("original_tag", "")
        if original_tag:
            original_tag_counter[original_tag] += 1

        confidence = row.get("confidence", 0)

        if confidence >= 90:
            confidence_bucket_counter["90_100"] += 1
        elif confidence >= 80:
            confidence_bucket_counter["80_89"] += 1
        elif confidence >= 70:
            confidence_bucket_counter["70_79"] += 1
        elif confidence >= 60:
            confidence_bucket_counter["60_69"] += 1
        else:
            confidence_bucket_counter["under_60"] += 1

    excluded_reason_counter = Counter()

    for item in excluded_places:
        excluded_reason_counter[item.get("reason", "unknown")] += 1

    skipped_reason_counter = Counter()

    for item in skipped_candidates:
        skipped_reason_counter[item.get("reason", "unknown")] += 1

    return {
        "input": {
            "input_path": str(INPUT_PATH),
            "input_final_candidate_count": len(input_places),
            "input_excluded_candidate_count": len(excluded_places),
            "min_confidence": MIN_CONFIDENCE,
        },
        "output": {
            "save_candidate_count": len(save_candidates),
            "skipped_candidate_count": len(skipped_candidates),
            "place_tag_seed_place_count": len(place_keys),
            "place_tag_seed_row_count": len(place_tag_seed_rows),
            "candidates_path": str(OUTPUT_CANDIDATES_PATH),
            "place_tag_seed_path": str(OUTPUT_PLACE_TAG_SEED_PATH),
            "summary_path": str(OUTPUT_SUMMARY_PATH),
        },
        "tag_counts": dict(tag_counter.most_common()),
        "original_tag_counts": dict(original_tag_counter.most_common()),
        "status_counts": dict(status_counter.most_common()),
        "priority_counts": dict(priority_counter.most_common()),
        "confidence_bucket_counts": dict(confidence_bucket_counter.most_common()),
        "excluded_reason_counts": dict(excluded_reason_counter.most_common()),
        "skipped_reason_counts": dict(skipped_reason_counter.most_common()),
        "tag_name_map": TAG_NAME_MAP,
        "data_note": (
            "이 파일은 관광공사 기반 Place에 블로그 검색 기반 후보 태그를 붙이기 위한 "
            "PlaceTag seed입니다. 카페처럼 ExternalPlaceTag로 저장하지 않습니다."
        ),
    }


def main():
    data = load_json(INPUT_PATH)

    input_places = data.get("final_candidates", [])
    excluded_places = data.get("excluded_candidates", [])

    save_candidates = []
    skipped_candidates = []
    place_tag_seed_rows = []

    seen_row_keys = set()

    for place in input_places:
        candidate = make_save_candidate(place)

        if not candidate["contentid"]:
            skipped_candidates.append({
                "contentid": "",
                "title": candidate.get("title", ""),
                "reason": "contentid_missing",
            })
            continue

        if not candidate["place_external_id"]:
            skipped_candidates.append({
                "contentid": candidate.get("contentid", ""),
                "title": candidate.get("title", ""),
                "reason": "place_external_id_missing",
            })
            continue

        if not candidate["verified_tags"]:
            skipped_candidates.append({
                "contentid": candidate.get("contentid", ""),
                "title": candidate.get("title", ""),
                "reason": "no_verified_tag_after_confidence_filter",
            })
            continue

        save_candidates.append(candidate)

        rows = make_place_tag_seed_rows(candidate)

        for row in rows:
            key = (
                row["place_source"],
                row["place_external_id"],
                row["tag_name"],
                row["source"],
            )

            if key in seen_row_keys:
                continue

            seen_row_keys.add(key)
            place_tag_seed_rows.append(row)

    result = {
        "save_candidates": save_candidates,
        "skipped_candidates": skipped_candidates,
        "excluded_candidates_from_final_file": excluded_places,
        "summary": {
            "input_count": len(input_places),
            "save_candidate_count": len(save_candidates),
            "skipped_candidate_count": len(skipped_candidates),
            "min_confidence": MIN_CONFIDENCE,
            "tag_counts": {},
        },
    }

    for candidate in save_candidates:
        for tag in candidate["verified_tags"]:
            result["summary"]["tag_counts"][tag] = (
                result["summary"]["tag_counts"].get(tag, 0) + 1
            )

    summary = build_summary(
        input_places=input_places,
        excluded_places=excluded_places,
        save_candidates=save_candidates,
        skipped_candidates=skipped_candidates,
        place_tag_seed_rows=place_tag_seed_rows,
    )

    save_json(OUTPUT_CANDIDATES_PATH, result)
    save_json(OUTPUT_PLACE_TAG_SEED_PATH, place_tag_seed_rows)
    save_json(OUTPUT_SUMMARY_PATH, summary)

    print("블로그 기반 관광지 PlaceTag seed 생성 완료")
    print(f"입력 최종 후보 장소 수: {summary['input']['input_final_candidate_count']}")
    print(f"입력 제외 후보 장소 수: {summary['input']['input_excluded_candidate_count']}")
    print(f"저장 후보 장소 수: {summary['output']['save_candidate_count']}")
    print(f"제외 후보 장소 수: {summary['output']['skipped_candidate_count']}")
    print(f"PlaceTag seed 장소 수: {summary['output']['place_tag_seed_place_count']}")
    print(f"PlaceTag seed row 수: {summary['output']['place_tag_seed_row_count']}")
    print()
    print(f"저장 후보 파일: {OUTPUT_CANDIDATES_PATH}")
    print(f"PlaceTag seed 파일: {OUTPUT_PLACE_TAG_SEED_PATH}")
    print(f"요약 파일: {OUTPUT_SUMMARY_PATH}")
    print()
    print("태그별 개수")
    for tag, count in summary["tag_counts"].items():
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()