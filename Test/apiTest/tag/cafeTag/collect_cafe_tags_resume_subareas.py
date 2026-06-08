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


# =========================
# 이어하기 설정
# =========================

RESUME_MODE = True
RETRY_NO_TAG_PLACES = False
KAKAO_SEARCH_PAGES = 5

# 중심점 세분화 버전
# 청사포 / 송정은 이번 수집 범위에서 제외
SEARCH_POINTS = [
    # 광안리
    {
        "area_key": "gwangalli",
        "area_name": "광안리",
        "sub_area_key": "gwangalli_beach",
        "sub_area_name": "광안리해변 중심",
        "center_lat": 35.1532,
        "center_lng": 129.1186,
        "radius": 1500,
        "queries": [
            "광안리 카페",
            "광안리 디저트 카페",
            "광안리 감성카페",
            "광안리 조용한 카페",
            "광안리 오션뷰 카페",
            "광안리 뷰 좋은 카페",
            "광안리 야경 카페",
            "광안리 루프탑 카페",
            "광안리 대형카페",
        ],
    },
    {
        "area_key": "gwangalli",
        "area_name": "광안리",
        "sub_area_key": "minrak_waterfront",
        "sub_area_name": "민락수변공원 중심",
        "center_lat": 35.1536,
        "center_lng": 129.1258,
        "radius": 1500,
        "queries": [
            "민락동 카페",
            "민락수변공원 카페",
            "민락동 오션뷰 카페",
            "민락동 뷰 좋은 카페",
            "민락동 감성카페",
            "민락동 대형카페",
        ],
    },
    {
        "area_key": "gwangalli",
        "area_name": "광안리",
        "sub_area_key": "namcheon",
        "sub_area_name": "남천동 중심",
        "center_lat": 35.1459,
        "center_lng": 129.1127,
        "radius": 1500,
        "queries": [
            "남천동 카페",
            "남천동 디저트 카페",
            "남천동 감성카페",
            "남천동 조용한 카페",
            "남천동 작업 카페",
            "남천동 대형카페",
        ],
    },
    {
        "area_key": "gwangalli",
        "area_name": "광안리",
        "sub_area_key": "suyeong_station",
        "sub_area_name": "수영역 중심",
        "center_lat": 35.1658,
        "center_lng": 129.1149,
        "radius": 1500,
        "queries": [
            "수영역 카페",
            "수영역 디저트 카페",
            "수영역 감성카페",
            "수영역 조용한 카페",
            "수영역 작업 카페",
            "수영역 카공 카페",
        ],
    },

    # 서면
    {
        "area_key": "seomyeon",
        "area_name": "서면",
        "sub_area_key": "seomyeon_station",
        "sub_area_name": "서면역 중심",
        "center_lat": 35.1577,
        "center_lng": 129.0592,
        "radius": 1500,
        "queries": [
            "서면 카페",
            "서면 디저트 카페",
            "서면 감성카페",
            "서면 조용한 카페",
            "서면 공부 카페",
            "서면 카공 카페",
            "서면 노트북 카페",
            "서면 대형카페",
        ],
    },
    {
        "area_key": "seomyeon",
        "area_name": "서면",
        "sub_area_key": "jeonpo_station",
        "sub_area_name": "전포역 중심",
        "center_lat": 35.1540,
        "center_lng": 129.0656,
        "radius": 1500,
        "queries": [
            "전포 카페",
            "전포동 카페",
            "전포 디저트 카페",
            "전포 감성카페",
            "전포 조용한 카페",
            "전포 작업 카페",
            "전포 카공 카페",
            "전포 노트북 카페",
        ],
    },
    {
        "area_key": "seomyeon",
        "area_name": "서면",
        "sub_area_key": "jeonpo_cafe_street",
        "sub_area_name": "전포카페거리 중심",
        "center_lat": 35.1558,
        "center_lng": 129.0644,
        "radius": 1200,
        "queries": [
            "전포 카페거리 카페",
            "전포 카페거리 디저트 카페",
            "전포 카페거리 감성카페",
            "전포 카페거리 조용한 카페",
            "전포 카페거리 작업 카페",
            "전포 카페거리 대형카페",
        ],
    },
    {
        "area_key": "seomyeon",
        "area_name": "서면",
        "sub_area_key": "bujeon_citizen_park",
        "sub_area_name": "부전역/시민공원 중심",
        "center_lat": 35.1666,
        "center_lng": 129.0590,
        "radius": 1700,
        "queries": [
            "부전동 카페",
            "부전역 카페",
            "부산시민공원 카페",
            "시민공원 카페",
            "부전동 조용한 카페",
            "부전동 작업 카페",
        ],
    },

    # 해운대
    {
        "area_key": "haeundae",
        "area_name": "해운대",
        "sub_area_key": "haeundae_station",
        "sub_area_name": "해운대역 중심",
        "center_lat": 35.1631,
        "center_lng": 129.1635,
        "radius": 1600,
        "queries": [
            "해운대 카페",
            "해운대 디저트 카페",
            "해운대 감성카페",
            "해운대 조용한 카페",
            "해운대 작업 카페",
            "해운대 노트북 카페",
            "해운대 오션뷰 카페",
            "해운대 대형카페",
        ],
    },
    {
        "area_key": "haeundae",
        "area_name": "해운대",
        "sub_area_key": "haeridangil",
        "sub_area_name": "해리단길 중심",
        "center_lat": 35.1657,
        "center_lng": 129.1585,
        "radius": 1200,
        "queries": [
            "해리단길 카페",
            "해리단길 디저트 카페",
            "해리단길 감성카페",
            "해리단길 조용한 카페",
            "해리단길 작업 카페",
            "해리단길 대형카페",
        ],
    },
    {
        "area_key": "haeundae",
        "area_name": "해운대",
        "sub_area_key": "dalmaji",
        "sub_area_name": "달맞이길 중심",
        "center_lat": 35.1585,
        "center_lng": 129.1770,
        "radius": 1800,
        "queries": [
            "달맞이길 카페",
            "달맞이길 디저트 카페",
            "달맞이길 감성카페",
            "달맞이길 조용한 카페",
            "달맞이길 오션뷰 카페",
            "달맞이길 뷰 좋은 카페",
            "달맞이길 대형카페",
        ],
    },
    {
        "area_key": "haeundae",
        "area_name": "해운대",
        "sub_area_key": "marine_city",
        "sub_area_name": "마린시티 중심",
        "center_lat": 35.1547,
        "center_lng": 129.1456,
        "radius": 1600,
        "queries": [
            "마린시티 카페",
            "마린시티 디저트 카페",
            "마린시티 감성카페",
            "마린시티 조용한 카페",
            "마린시티 오션뷰 카페",
            "마린시티 뷰 좋은 카페",
            "마린시티 작업 카페",
        ],
    },
]


AREA_KEYS = ["gwangalli", "seomyeon", "haeundae"]

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

    for area_key in AREA_KEYS:
        existing[area_key] = {
            "results": load_json(RESULT_DIR / f"cafe_{area_key}_results.json"),
            "skipped": load_json(RESULT_DIR / f"cafe_{area_key}_skipped_results.json"),
        }

    existing["all"] = {
        "results": load_json(RESULT_DIR / "cafe_all_results.json"),
        "skipped": load_json(RESULT_DIR / "cafe_all_skipped_results.json"),
    }

    return existing


def build_already_checked_ids():
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


def make_area_context(search_point):
    return {
        "area_key": search_point["area_key"],
        "area_name": search_point["area_name"],
        "sub_area_key": search_point["sub_area_key"],
        "sub_area_name": search_point["sub_area_name"],
    }


def add_sub_area_info(item, search_point):
    item["sub_area_key"] = search_point["sub_area_key"]
    item["sub_area_name"] = search_point["sub_area_name"]
    return item


def collect_kakao_places_for_search_point(search_point, already_checked_ids, stats):
    area_context = make_area_context(search_point)

    all_places = []
    seen_ids = set()
    skipped_places = []

    print("\n==============================")
    print(f"{search_point['area_name']} / {search_point['sub_area_name']} 카카오 후보 수집 시작")
    print("==============================")

    for query in search_point["queries"]:
        print(f"\n카카오 검색: {query}")

        for page in range(1, KAKAO_SEARCH_PAGES + 1):
            try:
                data = search_kakao_cafes(
                    query=query,
                    lat=search_point["center_lat"],
                    lng=search_point["center_lng"],
                    radius=search_point["radius"],
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
                    skipped_places.append(
                        add_sub_area_info(
                            make_skip_place(area_context, place, "카카오 장소 ID 없음", query),
                            search_point,
                        )
                    )
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
                    skipped_places.append(
                        add_sub_area_info(
                            make_skip_place(area_context, place, reason, query),
                            search_point,
                        )
                    )
                    print(f"  제외: {place.get('place_name')} / {reason}")
                    continue

                place["_source_query"] = query
                place["_sub_area_key"] = search_point["sub_area_key"]
                place["_sub_area_name"] = search_point["sub_area_name"]
                all_places.append(place)

            if meta.get("is_end"):
                break

    return all_places, skipped_places


def collect_search_point_resume(search_point, already_checked_ids, stats):
    area_context = make_area_context(search_point)

    places, skipped_places = collect_kakao_places_for_search_point(
        search_point=search_point,
        already_checked_ids=already_checked_ids,
        stats=stats,
    )

    print(f"\n{search_point['area_name']} / {search_point['sub_area_name']} 카카오 후보 수집 완료")
    print(f"새로 분석할 장소 수: {len(places)}")
    print(f"카카오 단계 신규 제외 장소 수: {len(skipped_places)}\n")

    new_results = []
    skipped_after_blog = []

    for index, place in enumerate(places, start=1):
        print(
            f"[{search_point['area_name']} / {search_point['sub_area_name']} "
            f"{index}/{len(places)}] {place.get('place_name')}"
        )

        result = collect_tags_for_cafe(area_context, place)
        result = add_sub_area_info(result, search_point)
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

    return new_results, skipped_places + skipped_after_blog


def merge_area_data(existing, new_results_by_area, new_skipped_by_area):
    area_results = {}

    for area_key in AREA_KEYS:
        merged_results = dedupe_by_external_id(
            existing[area_key]["results"] + new_results_by_area.get(area_key, [])
        )

        result_ids = {
            get_external_id(item)
            for item in merged_results
            if get_external_id(item)
        }

        merged_skipped = remove_ids(existing[area_key]["skipped"], result_ids)
        merged_skipped = dedupe_by_external_id(
            merged_skipped + new_skipped_by_area.get(area_key, [])
        )

        save_json(RESULT_DIR / f"cafe_{area_key}_results.json", merged_results)
        save_json(RESULT_DIR / f"cafe_{area_key}_skipped_results.json", merged_skipped)

        area_results[area_key] = {
            "results": merged_results,
            "skipped": merged_skipped,
        }

        print(f"\n{area_key} 저장 완료")
        print(f"  results 저장 수: {len(merged_results)}")
        print(f"  skipped 저장 수: {len(merged_skipped)}")

    return area_results


def save_all_results(area_results, existing=None):
    all_results = []
    all_skipped_results = []
    result_ids = set()

    if existing:
        all_results.extend(existing["all"]["results"])

    for area_key in AREA_KEYS:
        all_results.extend(area_results[area_key]["results"])

    all_results = dedupe_by_external_id(all_results)

    for item in all_results:
        external_id = get_external_id(item)

        if external_id:
            result_ids.add(external_id)

    if existing:
        all_skipped_results.extend(existing["all"]["skipped"])

    for area_key in AREA_KEYS:
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
    already_checked_ids = build_already_checked_ids()

    stats = {
        "duplicate_skipped": 0,
        "new_analyzed": 0,
    }

    print("\n==============================")
    print("카페 태그 sub-area resume 수집 시작")
    print("==============================")
    print(f"기존 확인된 장소 수: {len(already_checked_ids)}")
    print(f"RESUME_MODE: {RESUME_MODE}")
    print(f"RETRY_NO_TAG_PLACES: {RETRY_NO_TAG_PLACES}")
    print(f"KAKAO_SEARCH_PAGES: {KAKAO_SEARCH_PAGES}")
    print("제외된 중심점: 청사포, 송정")

    new_results_by_area = {area_key: [] for area_key in AREA_KEYS}
    new_skipped_by_area = {area_key: [] for area_key in AREA_KEYS}

    for search_point in SEARCH_POINTS:
        new_results, new_skipped = collect_search_point_resume(
            search_point=search_point,
            already_checked_ids=already_checked_ids,
            stats=stats,
        )

        area_key = search_point["area_key"]
        new_results_by_area[area_key].extend(new_results)
        new_skipped_by_area[area_key].extend(new_skipped)

        # 같은 실행 안에서 새로 처리한 장소도 이후 중심점에서 다시 분석하지 않게 추가
        for item in new_results + new_skipped:
            external_id = get_external_id(item)

            if external_id:
                already_checked_ids.add(external_id)

    area_results = merge_area_data(
        existing=existing,
        new_results_by_area=new_results_by_area,
        new_skipped_by_area=new_skipped_by_area,
    )

    all_results, all_skipped_results = save_all_results(area_results, existing)

    print("\n==============================")
    print("카페 태그 sub-area resume 수집 완료")
    print("==============================")
    print(f"기존 확인 + 이번 실행 확인 장소 수: {len(already_checked_ids)}")
    print(f"이번 실행에서 중복이라 패스한 장소 수: {stats['duplicate_skipped']}")
    print(f"이번 실행에서 새로 분석한 장소 수: {stats['new_analyzed']}")
    print(f"최종 results 저장 수: {len(all_results)}")
    print(f"최종 skipped 저장 수: {len(all_skipped_results)}")
    print(f"전체 결과: {RESULT_DIR / 'cafe_all_results.json'}")
    print(f"전체 skipped 결과: {RESULT_DIR / 'cafe_all_skipped_results.json'}")


if __name__ == "__main__":
    main()
