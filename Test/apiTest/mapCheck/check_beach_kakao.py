import argparse
import json
import math
import os
import re
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import requests


KAKAO_KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

DEFAULT_INPUT_PATH = Path("ExData/Cleaned/beach_places.json")
DEFAULT_OUTPUT_DIR = Path("ExData/ImportPlan/map_checked")


NAME_KEYS = [
    "name",
    "place_name",
    "placeName",
    "title",
    "beach_name",
    "facility_name",
    "시설명",
    "명칭",
    "장소명",
    "해수욕장명",
]

ADDRESS_KEYS = [
    "address",
    "addr",
    "road_address",
    "road_address_name",
    "address_name",
    "지번주소",
    "도로명주소",
    "주소",
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
]

LNG_KEYS = [
    "lng",
    "lon",
    "longitude",
    "경도",
    "x",
    "X",
]

SOURCE_ID_KEYS = [
    "id",
    "pk",
    "source_id",
    "external_id",
    "관리번호",
    "번호",
]


def load_dotenv_file(env_path=".env"):
    path = Path(env_path)

    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            os.environ.setdefault(key, value)


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
    if value is None:
        return None

    try:
        text = str(value).strip().replace(",", "")

        if text == "":
            return None

        return float(text)
    except ValueError:
        return None


def extract_place_info(record, index):
    name = pick_value(record, NAME_KEYS)
    address = pick_value(record, ADDRESS_KEYS)
    lat = to_float(pick_value(record, LAT_KEYS))
    lng = to_float(pick_value(record, LNG_KEYS))
    source_id = pick_value(record, SOURCE_ID_KEYS)

    return {
        "source_index": index,
        "source_id": source_id,
        "name": str(name).strip() if name is not None else "",
        "address": str(address).strip() if address is not None else "",
        "lat": lat,
        "lng": lng,
    }


def normalize_name(text):
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", str(text))
    text = text.lower()

    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^]]*\]", "", text)

    text = text.replace("해변", "해수욕장")
    text = text.replace("비치", "해수욕장")

    text = re.sub(r"[^0-9a-z가-힣]", "", text)

    return text


def name_similarity(source_name, kakao_name):
    source = normalize_name(source_name)
    kakao = normalize_name(kakao_name)

    if not source or not kakao:
        return 0

    if source == kakao:
        return 100

    if source in kakao or kakao in source:
        return 92

    return round(SequenceMatcher(None, source, kakao).ratio() * 100, 2)


def address_similarity(source_address, kakao_doc):
    if not source_address:
        return 0

    kakao_address = " ".join(
        [
            kakao_doc.get("address_name", ""),
            kakao_doc.get("road_address_name", ""),
        ]
    ).strip()

    if not kakao_address:
        return 0

    source_tokens = [
        token
        for token in re.split(r"\s+", source_address)
        if len(token) >= 2
    ]

    if not source_tokens:
        return 0

    source_tokens = source_tokens[:4]

    matched = 0

    for token in source_tokens:
        if token in kakao_address:
            matched += 1

    return round((matched / len(source_tokens)) * 100, 2)


def haversine_m(lat1, lng1, lat2, lng2):
    earth_radius_m = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius_m * c


def get_distance_m(source_info, kakao_doc):
    kakao_distance = kakao_doc.get("distance")

    if kakao_distance not in [None, ""]:
        try:
            return float(kakao_distance)
        except ValueError:
            pass

    source_lat = source_info.get("lat")
    source_lng = source_info.get("lng")
    kakao_lat = to_float(kakao_doc.get("y"))
    kakao_lng = to_float(kakao_doc.get("x"))

    if None in [source_lat, source_lng, kakao_lat, kakao_lng]:
        return None

    return round(haversine_m(source_lat, source_lng, kakao_lat, kakao_lng), 2)


def distance_score(distance_m):
    if distance_m is None:
        return 0

    if distance_m <= 150:
        return 100

    if distance_m <= 300:
        return 90

    if distance_m <= 700:
        return 75

    if distance_m <= 1500:
        return 55

    if distance_m <= 2500:
        return 35

    return 0


def category_score(kakao_doc):
    category_name = kakao_doc.get("category_name", "")

    if "해수욕장" in category_name:
        return 100

    if "관광" in category_name or "명소" in category_name or "여행" in category_name:
        return 70

    return 0


def score_candidate(source_info, kakao_doc):
    name_score = name_similarity(source_info["name"], kakao_doc.get("place_name", ""))
    addr_score = address_similarity(source_info.get("address", ""), kakao_doc)
    distance_m = get_distance_m(source_info, kakao_doc)
    dist_score = distance_score(distance_m)
    cate_score = category_score(kakao_doc)

    has_coord = source_info.get("lat") is not None and source_info.get("lng") is not None

    if has_coord:
        total_score = (
            name_score * 0.55
            + dist_score * 0.30
            + addr_score * 0.10
            + cate_score * 0.05
        )
    else:
        total_score = (
            name_score * 0.75
            + addr_score * 0.20
            + cate_score * 0.05
        )

    return {
        "total_score": round(total_score, 2),
        "name_score": name_score,
        "address_score": addr_score,
        "distance_score": dist_score,
        "category_score": cate_score,
        "distance_m": distance_m,
    }


def make_region_hint(address):
    if not address:
        return ""

    tokens = re.split(r"\s+", address.strip())

    return " ".join(tokens[:2])


def make_queries(source_info):
    name = source_info["name"].strip()
    address = source_info.get("address", "").strip()
    region_hint = make_region_hint(address)

    queries = []

    if name:
        queries.append(name)

    if name and "해수욕장" not in name and "해변" not in name:
        queries.append(f"{name} 해수욕장")

    if region_hint and name:
        queries.append(f"{region_hint} {name}")

    result = []
    seen = set()

    for query in queries:
        query = query.strip()

        if query and query not in seen:
            result.append(query)
            seen.add(query)

    return result


def make_cache_key(params):
    parts = []

    for key in sorted(params.keys()):
        parts.append(f"{key}={params[key]}")

    return "&".join(parts)


def kakao_keyword_search(api_key, query, source_info, radius, size, sort, cache, force_refresh=False):
    params = {
        "query": query,
        "size": size,
        "page": 1,
        "sort": sort,
    }

    if source_info.get("lat") is not None and source_info.get("lng") is not None:
        params["x"] = source_info["lng"]
        params["y"] = source_info["lat"]
        params["radius"] = radius

    cache_key = make_cache_key(params)

    if not force_refresh and cache_key in cache:
        return cache[cache_key]["response"]

    headers = {
        "Authorization": f"KakaoAK {api_key}",
    }

    response = requests.get(
        KAKAO_KEYWORD_SEARCH_URL,
        headers=headers,
        params=params,
        timeout=10,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"카카오 API 요청 실패: status={response.status_code}, body={response.text}"
        )

    data = response.json()

    cache[cache_key] = {
        "params": params,
        "response": data,
        "cached_at": datetime.now().isoformat(timespec="seconds"),
    }

    return data


def minimal_kakao_doc(doc):
    return {
        "kakao_place_id": doc.get("id"),
        "place_name": doc.get("place_name"),
        "category_name": doc.get("category_name"),
        "category_group_code": doc.get("category_group_code"),
        "category_group_name": doc.get("category_group_name"),
        "address_name": doc.get("address_name"),
        "road_address_name": doc.get("road_address_name"),
        "phone": doc.get("phone"),
        "x": doc.get("x"),
        "y": doc.get("y"),
        "place_url": doc.get("place_url"),
        "distance": doc.get("distance"),
    }


def classify_best_candidate(best):
    if best is None:
        return "unmatched"

    total_score = best["score"]["total_score"]
    name_score = best["score"]["name_score"]
    distance_m = best["score"]["distance_m"]

    if total_score >= 82 and name_score >= 75:
        return "matched"

    if name_score >= 92 and distance_m is not None and distance_m <= 1000:
        return "matched"

    if total_score >= 55 or name_score >= 70:
        return "review"

    return "unmatched"


def check_one_place(api_key, source_info, args, cache):
    queries = make_queries(source_info)

    if not source_info["name"]:
        return {
            "decision": "unmatched",
            "reason": "source_name_missing",
            "source": source_info,
            "queries": queries,
            "best_candidate": None,
            "candidates": [],
        }

    merged_candidates = {}
    used_queries = []

    for query in queries:
        data = kakao_keyword_search(
            api_key=api_key,
            query=query,
            source_info=source_info,
            radius=args.radius,
            size=args.size,
            sort=args.sort,
            cache=cache,
            force_refresh=args.force_refresh,
        )

        used_queries.append(query)

        for doc in data.get("documents", []):
            kakao_id = doc.get("id")

            if not kakao_id:
                continue

            if kakao_id not in merged_candidates:
                merged_candidates[kakao_id] = {
                    "query": query,
                    "kakao": minimal_kakao_doc(doc),
                    "score": score_candidate(source_info, doc),
                }

        time.sleep(args.sleep)

    candidates = list(merged_candidates.values())
    candidates.sort(key=lambda item: item["score"]["total_score"], reverse=True)

    best = candidates[0] if candidates else None
    decision = classify_best_candidate(best)

    result = {
        "decision": decision,
        "source": source_info,
        "queries": used_queries,
        "best_candidate": best,
        "candidates": candidates[:5],
    }

    if decision == "matched":
        result["reason"] = "auto_matched_by_score"
    elif decision == "review":
        result["reason"] = "ambiguous_score"
    else:
        if candidates:
            result["reason"] = "low_score"
        else:
            result["reason"] = "no_kakao_candidates"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="beach_places.json을 카카오 Local API로 검색해 matched / unmatched / review 파일을 생성합니다."
    )

    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_PATH),
        help="입력 정제 JSON 경로",
    )

    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="결과 저장 폴더",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="테스트할 개수. 예: --limit 10",
    )

    parser.add_argument(
        "--radius",
        type=int,
        default=2000,
        help="좌표가 있을 때 카카오 검색 반경(m)",
    )

    parser.add_argument(
        "--size",
        type=int,
        default=15,
        help="카카오 검색 결과 개수. 최대 15",
    )

    parser.add_argument(
        "--sort",
        choices=["accuracy", "distance"],
        default="distance",
        help="카카오 검색 정렬 방식",
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=0.15,
        help="API 요청 사이 대기 시간",
    )

    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="기존 검색 캐시를 무시하고 다시 요청",
    )

    args = parser.parse_args()

    load_dotenv_file()

    api_key = os.getenv("KAKAO_REST_API_KEY")

    if not api_key:
        raise RuntimeError(
            ".env에서 KAKAO_REST_API_KEY를 찾지 못했습니다."
        )

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    cache_path = output_dir / "beach_kakao_search_cache.json"

    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾지 못했습니다: {input_path}")

    if args.size > 15:
        raise ValueError("카카오 키워드 검색 size는 최대 15입니다.")

    output_dir.mkdir(parents=True, exist_ok=True)

    raw_data = load_json(input_path)
    items = unwrap_items(raw_data)

    if args.limit is not None:
        target_items = items[: args.limit]
    else:
        target_items = items

    if cache_path.exists():
        cache = load_json(cache_path)
    else:
        cache = {}

    matched = []
    unmatched = []
    review = []

    started_at = datetime.now()

    print(f"입력 파일: {input_path}")
    print(f"전체 데이터 수: {len(items)}")
    print(f"이번 확인 대상 수: {len(target_items)}")
    print(f"결과 저장 폴더: {output_dir}")
    print("-" * 60)

    for index, record in enumerate(target_items, start=1):
        source_info = extract_place_info(record, index - 1)

        print(f"[{index}/{len(target_items)}] {source_info['name']}")

        try:
            result = check_one_place(api_key, source_info, args, cache)
            result["original"] = record

            if result["decision"] == "matched":
                matched.append(result)

                best_name = result["best_candidate"]["kakao"]["place_name"]
                best_score = result["best_candidate"]["score"]["total_score"]

                print(f"  -> matched: {best_name} / score={best_score}")

            elif result["decision"] == "review":
                review.append(result)

                if result["best_candidate"]:
                    best_name = result["best_candidate"]["kakao"]["place_name"]
                    best_score = result["best_candidate"]["score"]["total_score"]
                    print(f"  -> review: {best_name} / score={best_score}")
                else:
                    print("  -> review")

            else:
                unmatched.append(result)
                print(f"  -> unmatched: {result.get('reason')}")

        except Exception as e:
            error_result = {
                "decision": "review",
                "reason": "api_or_script_error",
                "error": str(e),
                "source": source_info,
                "original": record,
            }

            review.append(error_result)

            print(f"  -> error -> review: {e}")

        save_json(cache_path, cache)

    finished_at = datetime.now()

    summary = {
        "dataset": "beach",
        "input_file": str(input_path),
        "output_dir": str(output_dir),
        "total_input_count": len(items),
        "checked_count": len(target_items),
        "limit": args.limit,
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "review_count": len(review),
        "settings": {
            "radius": args.radius,
            "size": args.size,
            "sort": args.sort,
            "sleep": args.sleep,
        },
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
    }

    save_json(output_dir / "beach_matched.json", matched)
    save_json(output_dir / "beach_unmatched.json", unmatched)
    save_json(output_dir / "beach_review.json", review)
    save_json(output_dir / "beach_map_check_summary.json", summary)
    save_json(cache_path, cache)

    print("-" * 60)
    print("완료")
    print(f"matched:   {len(matched)}")
    print(f"unmatched: {len(unmatched)}")
    print(f"review:    {len(review)}")
    print(f"summary:   {output_dir / 'beach_map_check_summary.json'}")


if __name__ == "__main__":
    main()