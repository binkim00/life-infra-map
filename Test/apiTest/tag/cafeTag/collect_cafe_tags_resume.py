import json
import time

from collect_cafe_tags_by_area import (
    KAKAO_REQUEST_DELAY,
    KAKAO_SEARCH_SIZE,
    MIN_BLOG_EVIDENCE_FOR_SAVE,
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    PLACE_REQUEST_DELAY,
    REQUIRE_TAGS_FOR_SAVE,
    RESULT_DIR,
    KAKAO_REST_API_KEY,
    collect_tags_for_cafe,
    make_skip_place,
    save_json,
    search_kakao_cafes,
    should_skip_place,
)


RESUME_MODE = True
RETRY_NO_TAG_PLACES = False
KAKAO_SEARCH_PAGES = 5

RESULT_FILE_NAMES = [
    "cafe_all_results.json",
    "cafe_all_skipped_results.json",
    "cafe_gwangalli_results.json",
    "cafe_gwangalli_skipped_results.json",
    "cafe_seomyeon_results.json",
    "cafe_seomyeon_skipped_results.json",
    "cafe_haeundae_results.json",
    "cafe_haeundae_skipped_results.json",
]

TARGET_AREAS = [
    {
        "area_key": "gwangalli",
        "area_name": "광안리",
        "center_lat": 35.1532,
        "center_lng": 129.1186,
        "radius": 1800,
        "queries": [
            "광안리 카페",
            "광안리 디저트 카페",
            "광안리 감성카페",
            "광안리 브런치 카페",
            "광안리 베이커리 카페",
            "광안리 조용한 카페",
            "광안리 작업하기 좋은 카페",
            "광안리 노트북 카페",
            "광안리 오션뷰 카페",
            "광안리 뷰 좋은 카페",
            "광안리 야경 카페",
            "광안리 루프탑 카페",
            "광안리 대형카페",
            "민락동 카페",
            "광안동 카페",
        ],
    },
    {
        "area_key": "seomyeon",
        "area_name": "서면",
        "center_lat": 35.1577,
        "center_lng": 129.0592,
        "radius": 1800,
        "queries": [
            "서면 카페",
            "서면 디저트 카페",
            "서면 감성카페",
            "서면 브런치 카페",
            "서면 베이커리 카페",
            "서면 조용한 카페",
            "서면 작업하기 좋은 카페",
            "서면 노트북 카페",
            "서면 공부 카페",
            "서면 카공 카페",
            "전포 카페",
            "전포동 카페",
            "전포 카페거리 카페",
            "전포 디저트 카페",
            "전포 감성카페",
            "전포 브런치 카페",
            "전포 베이커리 카페",
            "전포 조용한 카페",
            "전포 작업하기 좋은 카페",
            "전포 노트북 카페",
        ],
    },
    {
        "area_key": "haeundae",
        "area_name": "해운대",
        "center_lat": 35.1631,
        "center_lng": 129.1635,
        "radius": 2200,
        "queries": [
            "해운대 카페",
            "해운대 디저트 카페",
            "해운대 감성카페",
            "해운대 브런치 카페",
            "해운대 베이커리 카페",
            "해운대 조용한 카페",
            "해운대 작업하기 좋은 카페",
            "해운대 노트북 카페",
            "해운대 오션뷰 카페",
            "해운대 뷰 좋은 카페",
            "해운대 야경 카페",
            "해운대 루프탑 카페",
            "해운대 대형카페",
            "해운대 주차되는 카페",
            "해리단길 카페",
            "달맞이길 카페",
            "청사포 카페",
            "송정 카페",
            "마린시티 카페",
        ],
    },
]


def load_json(path):
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return data

    return []


def get_external_id(item):
    external_id = item.get("external_id")

    if external_id is None:
        external_id = item.get("id")

    if external_id is None:
        return None

    return str(external_id)


def is_no_tag_skip(item):
    reason = item.get("skip_reason", "")

    return "추천 태그 없음" in reason or "tag" in reason.lower()


def dedupe_by_external_id(items):
    deduped = []
    seen_ids = set()

    for item in items:
        external_id = get_external_id(item)

        if not external_id:
            deduped.append(item)
            continue

        if external_id in seen_ids:
            continue

        seen_ids.add(external_id)
        deduped.append(item)

    return deduped


def remove_ids(items, ids_to_remove):
    return [
        item
        for item in items
        if not get_external_id(item) or get_external_id(item) not in ids_to_remove
    ]


def load_existing_results():
    existing = {}

    for area in TARGET_AREAS:
        area_key = area["area_key"]
        existing[area_key] = {
            "results": load_json(RESULT_DIR / f"cafe_{area_key}_results.json"),
            "skipped": load_json(RESULT_DIR / f"cafe_{area_key}_skipped_results.json"),
        }

    existing["all"] = {
        "results": load_json(RESULT_DIR / "cafe_all_results.json"),
        "skipped": load_json(RESULT_DIR / "cafe_all_skipped_results.json"),
    }

    return existing


def build_already_checked_ids(existing):
    already_checked_ids = set()

    for file_name in RESULT_FILE_NAMES:
        for item in load_json(RESULT_DIR / file_name):
            external_id = get_external_id(item)

            if not external_id:
                continue

            if RETRY_NO_TAG_PLACES and is_no_tag_skip(item):
                continue

            already_checked_ids.add(external_id)

    return already_checked_ids


def collect_kakao_places_for_area_resume(area, already_checked_ids, stats):
    all_places = []
    seen_ids = set()
    skipped_places = []

    print("\n==============================")
    print(f"{area['area_name']} 카카오 후보 수집 시작")
    print("==============================")

    for query in area["queries"]:
        print(f"\n카카오 검색: {query}")

        for page in range(1, KAKAO_SEARCH_PAGES + 1):
            try:
                data = search_kakao_cafes(
                    query=query,
                    lat=area["center_lat"],
                    lng=area["center_lng"],
                    radius=area["radius"],
                    size=KAKAO_SEARCH_SIZE,
                    page=page,
                )

                places = data.get("documents", [])
                meta = data.get("meta", {})

                time.sleep(KAKAO_REQUEST_DELAY)

            except Exception as error:
                print(f"  카카오 검색 실패: {error}")
                break

            print(f"  {page}페이지 검색 결과 {len(places)}건")

            if not places:
                break

            for place in places:
                place_id = place.get("id")
                external_id = str(place_id) if place_id else None

                if not external_id:
                    skipped_places.append(make_skip_place(area, place, "카카오 장소 ID 없음", query))
                    continue

                if external_id in seen_ids:
                    continue

                seen_ids.add(external_id)

                if RESUME_MODE and external_id in already_checked_ids:
                    stats["duplicate_skipped"] += 1
                    print(f"  중복 패스: {place.get('place_name')} / {external_id}")
                    continue

                skip, reason = should_skip_place(place)

                if skip:
                    skipped_places.append(make_skip_place(area, place, reason, query))
                    print(f"  제외: {place.get('place_name')} / {reason}")
                    continue

                place["_source_query"] = query
                all_places.append(place)

            if meta.get("is_end"):
                break

    return all_places, skipped_places


def collect_area_resume(area, existing_area, already_checked_ids, stats):
    places, skipped_places = collect_kakao_places_for_area_resume(
        area=area,
        already_checked_ids=already_checked_ids,
        stats=stats,
    )

    print(f"\n{area['area_name']} 카카오 후보 수집 완료")
    print(f"새로 분석할 장소 수: {len(places)}")
    print(f"카카오 단계 신규 제외 장소 수: {len(skipped_places)}\n")

    new_results = []
    skipped_after_blog = []

    for index, place in enumerate(places, start=1):
        print(f"[{area['area_name']} {index}/{len(places)}] {place.get('place_name')}")

        result = collect_tags_for_cafe(area, place)
        stats["new_analyzed"] += 1

        if result["blog_evidence_count"] < MIN_BLOG_EVIDENCE_FOR_SAVE:
            skipped_after_blog.append({
                **result,
                "skip_reason": f"관련 블로그 글 {MIN_BLOG_EVIDENCE_FOR_SAVE}건 미만",
            })
            print(f"  최종 제외: 관련 블로그 글 {result['blog_evidence_count']}건\n")
            time.sleep(PLACE_REQUEST_DELAY)
            continue

        if REQUIRE_TAGS_FOR_SAVE and not result["tags"]:
            skipped_after_blog.append({
                **result,
                "skip_reason": "추천 태그 없음",
            })
            print("  최종 제외: 추천 태그 없음\n")
            time.sleep(PLACE_REQUEST_DELAY)
            continue

        new_results.append(result)
        print(f"  최종 저장: 태그 {len(result['tags'])}개\n")
        time.sleep(PLACE_REQUEST_DELAY)

    result_ids = {
        get_external_id(item)
        for item in new_results
        if get_external_id(item)
    }

    merged_results = dedupe_by_external_id(existing_area["results"] + new_results)
    merged_skipped = remove_ids(existing_area["skipped"], result_ids)
    merged_skipped = dedupe_by_external_id(merged_skipped + skipped_places + skipped_after_blog)

    save_json(RESULT_DIR / f"cafe_{area['area_key']}_results.json", merged_results)
    save_json(RESULT_DIR / f"cafe_{area['area_key']}_skipped_results.json", merged_skipped)

    print(f"\n{area['area_name']} 저장 완료")
    print(f"  results 저장 수: {len(merged_results)}")
    print(f"  skipped 저장 수: {len(merged_skipped)}")

    return merged_results, merged_skipped


def save_all_results(area_results):
    all_results = []
    all_skipped_results = []
    result_ids = set()

    for area in TARGET_AREAS:
        area_key = area["area_key"]
        all_results.extend(area_results[area_key]["results"])

    all_results = dedupe_by_external_id(all_results)

    for item in all_results:
        external_id = get_external_id(item)

        if external_id:
            result_ids.add(external_id)

    for area in TARGET_AREAS:
        area_key = area["area_key"]
        all_skipped_results.extend(area_results[area_key]["skipped"])

    all_skipped_results = remove_ids(all_skipped_results, result_ids)
    all_skipped_results = dedupe_by_external_id(all_skipped_results)

    save_json(RESULT_DIR / "cafe_all_results.json", all_results)
    save_json(RESULT_DIR / "cafe_all_skipped_results.json", all_skipped_results)

    return all_results, all_skipped_results


def main():
    if not KAKAO_REST_API_KEY:
        raise ValueError("KAKAO_REST_API_KEY가 없습니다. .env 파일을 확인해주세요.")

    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 없습니다. .env 파일을 확인해주세요.")

    existing = load_existing_results()
    already_checked_ids = build_already_checked_ids(existing)

    stats = {
        "duplicate_skipped": 0,
        "new_analyzed": 0,
    }

    print("\n==============================")
    print("카페 태그 resume 수집 시작")
    print("==============================")
    print(f"기존 확인된 장소 수: {len(already_checked_ids)}")
    print(f"RESUME_MODE: {RESUME_MODE}")
    print(f"RETRY_NO_TAG_PLACES: {RETRY_NO_TAG_PLACES}")
    print(f"KAKAO_SEARCH_PAGES: {KAKAO_SEARCH_PAGES}")

    area_results = {}

    for area in TARGET_AREAS:
        results, skipped_results = collect_area_resume(
            area=area,
            existing_area=existing[area["area_key"]],
            already_checked_ids=already_checked_ids,
            stats=stats,
        )

        area_results[area["area_key"]] = {
            "results": results,
            "skipped": skipped_results,
        }

    all_results, all_skipped_results = save_all_results(area_results)

    print("\n==============================")
    print("카페 태그 resume 수집 완료")
    print("==============================")
    print(f"기존 확인된 장소 수: {len(already_checked_ids)}")
    print(f"이번 실행에서 중복이라 패스한 장소 수: {stats['duplicate_skipped']}")
    print(f"이번 실행에서 새로 분석한 장소 수: {stats['new_analyzed']}")
    print(f"최종 results 저장 수: {len(all_results)}")
    print(f"최종 skipped 저장 수: {len(all_skipped_results)}")
    print(f"전체 결과: {RESULT_DIR / 'cafe_all_results.json'}")
    print(f"전체 skipped 결과: {RESULT_DIR / 'cafe_all_skipped_results.json'}")


if __name__ == "__main__":
    main()
