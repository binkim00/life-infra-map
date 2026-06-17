# collect_cafe_tags_busan_part2.py
# 실행 위치:
#   cd Test/apiTest/tag/cafeTag
#   python collect_cafe_tags_busan_part2.py
#
# 목적:
#   기존 collect_cafe_tags_by_area.py의 카카오 검색 + 네이버 블로그 태그 판별 로직을 재사용하면서
#   부산 행정 읍/면/동 단위로 카페 태그 후보를 수집합니다.
#
# 주의:
#   이 파일은 결과를 results_busan/part_02_east_west 폴더에만 저장합니다.
#   다른 part 파일과 동시에 실행해도 같은 JSON 파일을 덮어쓰지 않도록 분리했습니다.

import json
import re
import time
from collections import Counter
from pathlib import Path

import collect_cafe_tags_by_area as base


# =========================
# 실행 설정
# =========================

SCRIPT_DIR = Path(__file__).resolve().parent
RESULT_DIR = SCRIPT_DIR / "results_busan" / "part_02_east_west"

PART_NAME = "부산 카페 태그 수집 PART 2 / 동부·서부·기장"

RESUME_MODE = True
RETRY_NO_TAG_PLACES = False

# 카카오는 한 페이지당 최대 15개입니다.
KAKAO_SEARCH_SIZE = base.KAKAO_SEARCH_SIZE

# 1차 전체 수집은 3페이지를 추천합니다.
# 더 많이 보강하고 싶으면 5로 올려서 다시 실행하면 됩니다.
KAKAO_SEARCH_PAGES = 5

# 네이버 블로그 검색은 기존 로직 그대로 사용합니다.
# 기존 파일의 기본값은 50이었고, 여기서는 한 번 호출할 때 근거를 더 넓게 보기 위해 100으로 올립니다.
NAVER_BLOG_DISPLAY = 100
base.NAVER_BLOG_DISPLAY = NAVER_BLOG_DISPLAY

# 과호출 방지용 대기 시간은 기존 파일 값을 재사용합니다.
KAKAO_REQUEST_DELAY = base.KAKAO_REQUEST_DELAY
PLACE_REQUEST_DELAY = base.PLACE_REQUEST_DELAY

MIN_BLOG_EVIDENCE_FOR_SAVE = base.MIN_BLOG_EVIDENCE_FOR_SAVE
REQUIRE_TAGS_FOR_SAVE = base.REQUIRE_TAGS_FOR_SAVE


# =========================
# 부산 행정 읍/면/동 수집 대상
# =========================
# 부산시 공식 행정 읍/면/동 현황 기준으로 나눈 목록입니다.
# 좌표를 임의로 만들지 않고, "부산 + 구/군 + 행정동 + 카페" 키워드 중심으로 검색합니다.
# 실제 장소 좌표는 카카오 Local API 응답값을 저장합니다.

TARGET_GU_DONGS = {'해운대구': ['우제1동', '우제2동', '우제3동', '중제1동', '중제2동', '좌제1동', '좌제2동', '좌제3동', '좌제4동', '송정동', '반여제1동', '반여제2동', '반여제3동', '반여제4동', '반송제1동', '반송제2동', '재송제1동', '재송제2동'], '사하구': ['괴정제1동', '괴정제2동', '괴정제3동', '괴정제4동', '당리동', '하단제1동', '하단제2동', '신평제1동', '신평제2동', '장림제1동', '장림제2동', '다대제1동', '다대제2동', '구평동', '감천제1동', '감천제2동'], '금정구': ['서제1동', '서제2동', '서제3동', '금사동', '부곡제1동', '부곡제2동', '부곡제3동', '부곡제4동', '장전제1동', '장전제2동', '선두구동', '청룡노포동', '남산동', '구서제1동', '구서제2동', '금성동'], '강서구': ['대저1동', '대저2동', '강동동', '명지1동', '명지2동', '가락동', '녹산동', '신호동', '가덕도동'], '연제구': ['거제제1동', '거제제2동', '거제제3동', '거제제4동', '연산제1동', '연산제2동', '연산제3동', '연산제4동', '연산제5동', '연산제6동', '연산제8동', '연산제9동'], '수영구': ['남천제1동', '남천제2동', '수영동', '망미제1동', '망미제2동', '광안제1동', '광안제2동', '광안제3동', '광안제4동', '민락동'], '사상구': ['삼락동', '모라제1동', '모라제3동', '덕포제1동', '덕포제2동', '괘법동', '감전동', '주례제1동', '주례제2동', '주례제3동', '학장동', '엄궁동'], '기장군': ['기장읍', '장안읍', '정관읍', '일광읍', '철마면']}

AREA_KEY_MAP = {'해운대구': 'haeundae', '사하구': 'saha', '금정구': 'geumjeong', '강서구': 'gangseo', '연제구': 'yeonje', '수영구': 'suyeong', '사상구': 'sasang', '기장군': 'gijang'}

# 바다/야경/드라이브 성격 검색어를 추가할 구·군 또는 행정동입니다.
COASTAL_GU_NAMES = {
    "서구", "영도구", "남구", "해운대구", "사하구", "강서구", "수영구", "기장군",
}

DRIVE_GU_NAMES = {
    "강서구", "기장군",
}

DRIVE_DONG_NAMES = {
    "가덕도동", "녹산동", "명지1동", "명지2동", "송정동", "금성동", "철마면", "장안읍", "일광읍", "기장읍",
}

UNIVERSITY_OR_WORK_DONG_NAMES = {
    "부전제1동", "부전제2동", "전포제1동", "전포제2동", "대연제3동", "장전제1동", "장전제2동", "하단제1동", "하단제2동",
}


# =========================
# 유틸
# =========================

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_json(path):
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
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


def normalize_admin_dong_for_query(dong_name):
    """
    행정동명은 '전포제1동'처럼 쓰이지만 실제 검색어는 '전포1동' 또는 '전포동'이 더 자연스러운 경우가 있습니다.
    여기서는 검색어 후보만 자연스럽게 바꾸고, 저장되는 sub_area_name은 공식 행정동명을 유지합니다.
    """
    text = dong_name.strip()
    text = re.sub(r"제(?=\d)", "", text)
    return text


def simplify_numbered_dong_name(dong_name):
    """
    우1동 → 우동, 전포1동 → 전포동 같은 보조 검색어를 만듭니다.
    단, 대저1동/명지1동처럼 숫자가 실제 생활권 구분으로 자주 쓰이는 경우도 있으므로
    원래 검색어와 보조 검색어를 둘 다 사용합니다.
    """
    text = normalize_admin_dong_for_query(dong_name)
    text = re.sub(r"\d동$", "동", text)
    return text


def unique_keep_order(values):
    result = []
    seen = set()

    for value in values:
        value = str(value).strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result


def build_query_names(dong_name):
    base_name = normalize_admin_dong_for_query(dong_name)
    simplified_name = simplify_numbered_dong_name(dong_name)

    return unique_keep_order([base_name, simplified_name, dong_name])


def build_queries(gu_name, dong_name):
    names = build_query_names(dong_name)
    queries = []

    # 기본 후보 수집 검색어
    for name in names[:2]:
        queries.extend([
            f"부산 {gu_name} {name} 카페",
            f"{gu_name} {name} 카페",
            f"부산 {name} 카페",
        ])

    primary_name = names[0]

    # 추천 태그 후보를 만들기 위한 확장 검색어
    queries.extend([
        f"부산 {gu_name} {primary_name} 디저트 카페",
        f"부산 {gu_name} {primary_name} 감성카페",
        f"부산 {gu_name} {primary_name} 조용한 카페",
        f"부산 {gu_name} {primary_name} 작업 카페",
        f"부산 {gu_name} {primary_name} 노트북 카페",
    ])

    if gu_name in COASTAL_GU_NAMES:
        queries.extend([
            f"부산 {gu_name} {primary_name} 오션뷰 카페",
            f"부산 {gu_name} {primary_name} 뷰 좋은 카페",
            f"부산 {gu_name} {primary_name} 야경 카페",
        ])

    if gu_name in DRIVE_GU_NAMES or dong_name in DRIVE_DONG_NAMES:
        queries.extend([
            f"부산 {gu_name} {primary_name} 대형카페",
            f"부산 {gu_name} {primary_name} 드라이브 카페",
            f"부산 {gu_name} {primary_name} 주차되는 카페",
        ])

    if dong_name in UNIVERSITY_OR_WORK_DONG_NAMES:
        queries.extend([
            f"부산 {gu_name} {primary_name} 공부 카페",
            f"부산 {gu_name} {primary_name} 카공 카페",
        ])

    return unique_keep_order(queries)


def make_search_points():
    search_points = []

    for gu_name, dong_names in TARGET_GU_DONGS.items():
        area_key = AREA_KEY_MAP[gu_name]

        for dong_name in dong_names:
            search_points.append({
                "area_key": area_key,
                "area_name": gu_name,
                "sub_area_key": f"{area_key}_{normalize_admin_dong_for_query(dong_name)}",
                "sub_area_name": dong_name,
                "queries": build_queries(gu_name, dong_name),
            })

    return search_points


def make_area_context(search_point, use_sub_area_for_blog=True):
    """
    기존 collect_tags_for_cafe는 area_name을 블로그 검색어에 사용합니다.
    태그 근거 검색 정확도를 위해 블로그 검색에는 행정동명을 사용하고,
    저장 결과에는 다시 구/군명과 행정동명을 함께 남깁니다.
    """
    return {
        "area_key": search_point["area_key"],
        "area_name": search_point["sub_area_name"] if use_sub_area_for_blog else search_point["area_name"],
    }


def add_sub_area_info(item, search_point):
    item["area_key"] = search_point["area_key"]
    item["area_name"] = search_point["area_name"]
    item["sub_area_key"] = search_point["sub_area_key"]
    item["sub_area_name"] = search_point["sub_area_name"]
    item["part_name"] = PART_NAME
    return item


def make_skip_place(search_point, place, reason, query=None):
    area_context = {
        "area_key": search_point["area_key"],
        "area_name": search_point["area_name"],
    }
    skipped = base.make_skip_place(area_context, place, reason, query)
    return add_sub_area_info(skipped, search_point)


# =========================
# 기존 결과 이어하기
# =========================

def get_result_file_names():
    file_names = [
        "cafe_all_results.json",
        "cafe_all_skipped_results.json",
    ]

    for area_key in AREA_KEY_MAP.values():
        file_names.append(f"cafe_{area_key}_results.json")
        file_names.append(f"cafe_{area_key}_skipped_results.json")

    return file_names


def build_already_checked_ids():
    already_checked_ids = set()

    for file_name in get_result_file_names():
        for item in load_json(RESULT_DIR / file_name):
            external_id = get_external_id(item)

            if not external_id:
                continue

            if RETRY_NO_TAG_PLACES and is_no_tag_skip(item):
                continue

            already_checked_ids.add(external_id)

    return already_checked_ids


def load_existing_area_results():
    existing = {}

    for area_key in AREA_KEY_MAP.values():
        existing[area_key] = {
            "results": load_json(RESULT_DIR / f"cafe_{area_key}_results.json"),
            "skipped": load_json(RESULT_DIR / f"cafe_{area_key}_skipped_results.json"),
        }

    existing["all"] = {
        "results": load_json(RESULT_DIR / "cafe_all_results.json"),
        "skipped": load_json(RESULT_DIR / "cafe_all_skipped_results.json"),
    }

    return existing


# =========================
# 카카오 후보 수집
# =========================

def collect_kakao_places_for_search_point(search_point, already_checked_ids, stats):
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
                data = base.search_kakao_cafes(
                    query=query,
                    lat=None,
                    lng=None,
                    radius=None,
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
                    skipped_places.append(make_skip_place(search_point, place, "카카오 장소 ID 없음", query))
                    continue

                if external_id in seen_ids:
                    continue

                seen_ids.add(external_id)

                if RESUME_MODE and external_id in already_checked_ids:
                    stats["duplicate_skipped"] += 1
                    print(f"  중복 패스: {place.get('place_name')} / {external_id}")
                    continue

                skip, reason = base.should_skip_place(place)

                if skip:
                    skipped_places.append(make_skip_place(search_point, place, reason, query))
                    print(f"  제외: {place.get('place_name')} / {reason}")
                    continue

                place["_source_query"] = query
                place["_sub_area_key"] = search_point["sub_area_key"]
                place["_sub_area_name"] = search_point["sub_area_name"]
                all_places.append(place)

            if meta.get("is_end"):
                break

    return all_places, skipped_places


# =========================
# 태그 수집
# =========================

def collect_search_point(search_point, already_checked_ids, stats):
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

    area_context = make_area_context(search_point, use_sub_area_for_blog=True)

    for index, place in enumerate(places, start=1):
        print(
            f"[{search_point['area_name']} / {search_point['sub_area_name']} "
            f"{index}/{len(places)}] {place.get('place_name')}"
        )

        result = base.collect_tags_for_cafe(area_context, place)
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


# =========================
# 저장/병합
# =========================

def merge_area_data(existing, new_results_by_area, new_skipped_by_area):
    area_results = {}

    for area_key in AREA_KEY_MAP.values():
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

    for area_key in AREA_KEY_MAP.values():
        all_results.extend(area_results[area_key]["results"])

    all_results = dedupe_by_external_id(all_results)

    for item in all_results:
        external_id = get_external_id(item)

        if external_id:
            result_ids.add(external_id)

    if existing:
        all_skipped_results.extend(existing["all"]["skipped"])

    for area_key in AREA_KEY_MAP.values():
        all_skipped_results.extend(area_results[area_key]["skipped"])

    all_skipped_results = remove_ids(all_skipped_results, result_ids)
    all_skipped_results = dedupe_by_external_id(all_skipped_results)

    save_json(RESULT_DIR / "cafe_all_results.json", all_results)
    save_json(RESULT_DIR / "cafe_all_skipped_results.json", all_skipped_results)

    return all_results, all_skipped_results


def print_target_summary(search_points):
    counter = Counter(point["area_name"] for point in search_points)

    print("\n==============================")
    print(f"{PART_NAME} 수집 대상")
    print("==============================")
    print(f"결과 폴더: {RESULT_DIR}")
    print(f"행정 읍/면/동 수: {len(search_points)}")
    print(f"KAKAO_SEARCH_PAGES: {KAKAO_SEARCH_PAGES}")
    print(f"NAVER_BLOG_DISPLAY: {NAVER_BLOG_DISPLAY}")
    print()

    for gu_name, count in counter.items():
        print(f"- {gu_name}: {count}개")


def main():
    if not base.KAKAO_REST_API_KEY:
        raise ValueError("KAKAO_REST_API_KEY가 없습니다. .env 파일을 확인해주세요.")

    if not base.NAVER_CLIENT_ID or not base.NAVER_CLIENT_SECRET:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 없습니다. .env 파일을 확인해주세요.")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    search_points = make_search_points()
    print_target_summary(search_points)

    existing = load_existing_area_results()
    already_checked_ids = build_already_checked_ids()

    stats = {
        "duplicate_skipped": 0,
        "new_analyzed": 0,
    }

    print("\n==============================")
    print(f"{PART_NAME} 카페 태그 수집 시작")
    print("==============================")
    print(f"기존 확인된 장소 수: {len(already_checked_ids)}")
    print(f"RESUME_MODE: {RESUME_MODE}")
    print(f"RETRY_NO_TAG_PLACES: {RETRY_NO_TAG_PLACES}")

    new_results_by_area = {area_key: [] for area_key in AREA_KEY_MAP.values()}
    new_skipped_by_area = {area_key: [] for area_key in AREA_KEY_MAP.values()}

    for search_point in search_points:
        new_results, new_skipped = collect_search_point(
            search_point=search_point,
            already_checked_ids=already_checked_ids,
            stats=stats,
        )

        area_key = search_point["area_key"]
        new_results_by_area[area_key].extend(new_results)
        new_skipped_by_area[area_key].extend(new_skipped)

        # 같은 실행 안에서 새로 처리한 장소도 이후 행정동에서 다시 분석하지 않게 추가합니다.
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
    print(f"{PART_NAME} 카페 태그 수집 완료")
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
