import json
from pathlib import Path


# 현재 파일 위치: Test/apiTest/tag/tourTag/tag_tourist_spot_busan.py
BASE_DIR = Path(__file__).resolve().parents[4]

INPUT_PATH = BASE_DIR / "ExData" / "JsonData" / "tourism" / "tourist_spot_korea.json"

OUTPUT_DIR = Path(__file__).resolve().parent
TAGGED_PATH = OUTPUT_DIR / "tourist_spot_busan_tagged.json"
SKIPPED_PATH = OUTPUT_DIR / "tourist_spot_busan_skipped.json"
SUMMARY_PATH = OUTPUT_DIR / "tourist_spot_busan_summary.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_items(raw_data):
    if isinstance(raw_data, list):
        return raw_data

    try:
        items = raw_data["response"]["body"]["items"]["item"]
        if isinstance(items, list):
            return items
        return [items]
    except (KeyError, TypeError):
        return []


def is_busan(item):
    areacode = str(item.get("areacode", "")).strip()
    addr1 = str(item.get("addr1", "")).strip()

    return areacode == "6" or addr1.startswith("부산")


def has_coordinate(item):
    mapx = str(item.get("mapx", "")).strip()
    mapy = str(item.get("mapy", "")).strip()

    return mapx != "" and mapy != ""


def is_valid_busan_coordinate(item):
    """
    좌표가 부산 근처 범위인지 확인.
    장소 자체를 버리는 게 아니라, 좌표 이상값을 따로 분리하기 위한 용도.
    """
    try:
        x = float(item.get("mapx", ""))
        y = float(item.get("mapy", ""))
    except ValueError:
        return False

    # 부산 대략 경도/위도 범위
    return 128.7 <= x <= 129.4 and 34.8 <= y <= 35.4


def make_common_place(item):
    return {
        "contentid": str(item.get("contentid", "")).strip(),
        "title": str(item.get("title", "")).strip(),
        "addr1": str(item.get("addr1", "")).strip(),
        "addr2": str(item.get("addr2", "")).strip(),
        "mapx": str(item.get("mapx", "")).strip(),
        "mapy": str(item.get("mapy", "")).strip(),
        "areacode": str(item.get("areacode", "")).strip(),
        "sigungucode": str(item.get("sigungucode", "")).strip(),
        "cat1": str(item.get("cat1", "")).strip(),
        "cat2": str(item.get("cat2", "")).strip(),
        "cat3": str(item.get("cat3", "")).strip(),
        "contenttypeid": str(item.get("contenttypeid", "")).strip(),
        "firstimage": str(item.get("firstimage", "")).strip(),
        "firstimage2": str(item.get("firstimage2", "")).strip(),
        "tel": str(item.get("tel", "")).strip(),
        "zipcode": str(item.get("zipcode", "")).strip(),
    }


def contains_any(text, keywords):
    matched = []

    for keyword in keywords:
        if keyword in text:
            matched.append(keyword)

    return matched


def is_mountain_name(title):
    """
    '산'은 너무 넓어서 그냥 끝 글자 기준으로 잡지 않음.
    예: '부산' 때문에 롯데월드 어드벤처 부산, 키자니아 부산이 산으로 잡히는 문제 방지.
    """
    mountain_keywords = [
        "금정산", "황령산", "장산", "백양산", "승학산", "봉래산",
        "금련산", "땅뫼산", "아미산", "천마산", "달음산", "아홉산"
    ]

    return contains_any(title, mountain_keywords)


def is_temple_name(title):
    """
    사찰/암자/선원/정사 계열만 태그 후보로 처리.
    단순 '사' 포함은 오탐이 많아서 쓰지 않음.
    """
    temple_keywords = [
        "범어사", "해동용궁사", "장안사", "삼광사", "관음사", "감천사",
        "국청사", "금강사", "대각사", "내원정사", "마하사", "묘관음사",
        "미륵사", "법륜사", "보광사", "복천사", "선암사", "성암사",
        "안적사", "운수사", "월명사", "은진사", "청량사", "태종사",
        "홍법사", "석탑사", "해광사", "해동성취사", "옥련선원", "혜원정사",

        # 이번 skipped 확인 후 추가
        "금강암", "금수사", "금용암", "묘심사", "소림사",
        "약수암", "연등사", "영주암", "척판암"
    ]

    matched = contains_any(title, temple_keywords)

    # 암/선원/정사로 끝나는 경우만 패턴 처리
    cleaned = title.replace("(부산)", "").strip()

    if cleaned.endswith("선원") or cleaned.endswith("정사"):
        matched.append("사찰명패턴")

    return matched


def add_tag(tags, tag_sources, tag, matched_keywords):
    if not matched_keywords:
        return

    if tag not in tags:
        tags.append(tag)

    tag_sources.append({
        "tag": tag,
        "matched_keywords": matched_keywords,
        "source": "name_rule",
    })


def apply_name_tags(place):
    title = place["title"]

    exclude_title_keywords = [
        "주식회사", "성형외과", "의원", "병원"
    ]

    if contains_any(title, exclude_title_keywords):
        place["tags"] = []
        place["tag_sources"] = []
        return place

    tags = []
    tag_sources = []

    walk_keywords = [
        "공원", "길", "산책", "둘레길", "갈맷길", "해변", "해수욕장",
        "수변", "강변", "숲", "생태", "공원길", "해안길", "계곡",
        "수원지", "동산", "산성", "연대봉", "포구", "섬", "몰운대",
        "태종대", "이기대", "동백섬",

        # 추가 유지
        "대천천", "온천천", "레일웨이", "블루라인", "모노레일", "계단"
    ]

    night_view_keywords = [
        "전망", "전망대", "타워", "대교", "브릿지", "야경", "스카이",
        "루프", "마천루", "봉수대", "낙조", "노을", "선셋",
        "마린시티", "더베이", "황령산", "해월정", "달맞이"
    ]

    healing_keywords = [
        "숲", "치유", "힐링", "자연", "생태", "수목원", "정원",
        "온천", "계곡", "폭포", "수원지", "식물원", "웰니스",
        "스파", "탕", "해수탕", "찜질", "몰운대", "태종대", "이기대",
        "동백섬",

        # 추가
        "허심청", "해수랜드", "오아시스"
    ]

    drive_keywords = [
        "해안", "해안길", "대교", "드라이브", "항구", "항", "등대",
        "전망", "고개", "터널", "포구", "선착장", "방파제", "크루즈",
        "마린시티", "산복도로", "달맞이", "가덕도", "청사포"
    ]

    solo_keywords = [
        "서점", "책방", "도서관", "미술관", "박물관", "기념관",
        "전시", "갤러리", "라이브러리", "자료실", "문화관",
        "체험관", "과학관", "교육관", "전당", "상상마당", "F1963",

        # 추가
        "에코센터", "스튜디오"
    ]
    short_rest_keywords = [
        "쉼터", "광장", "공원", "정자", "전망대", "수변공원",
        "해변", "해수욕장", "동산", "수원지", "포구"
    ]

    photo_keywords = [
        "전망", "전망대", "스카이", "해변", "해수욕장", "벽화",
        "마을", "거리", "광장", "대교", "등대", "공원", "마린시티",
        "더베이", "세트장", "케이블카", "구름다리", "분수", "골목",
        "시장", "포구", "선착장", "크루즈", "태종대", "이기대",
        "몰운대", "동백섬",

        # 추가
        "스튜디오", "마켓", "레일웨이", "블루라인", "모노레일", "계단", "연밭"
    ]

    date_keywords = [
        "해변", "해수욕장", "전망대", "공원", "수변공원",
        "문화마을", "거리", "광장", "미술관", "전시", "마린시티",
        "더베이", "청사포", "달맞이", "케이블카", "구름다리",

        # 추가
        "마켓", "블루라인", "레일웨이", "오아시스"
    ]

    mountain_matches = is_mountain_name(title)
    temple_matches = is_temple_name(title)

    add_tag(tags, tag_sources, "walk_good", contains_any(title, walk_keywords))
    add_tag(tags, tag_sources, "walk_good", mountain_matches)

    add_tag(tags, tag_sources, "night_view", contains_any(title, night_view_keywords))

    add_tag(tags, tag_sources, "healing", contains_any(title, healing_keywords))
    add_tag(tags, tag_sources, "healing", mountain_matches)
    add_tag(tags, tag_sources, "healing", temple_matches)

    add_tag(tags, tag_sources, "drive_good", contains_any(title, drive_keywords))

    add_tag(tags, tag_sources, "solo_good", contains_any(title, solo_keywords))

    # 사찰은 혼자 조용히 가기 좋은 후보로 볼 수 있어서 후보 태그만 부여
    add_tag(tags, tag_sources, "solo_good", temple_matches)

    add_tag(tags, tag_sources, "short_rest", contains_any(title, short_rest_keywords))

    add_tag(tags, tag_sources, "photo_good", contains_any(title, photo_keywords))
    add_tag(tags, tag_sources, "photo_good", mountain_matches)

    add_tag(tags, tag_sources, "date_good", contains_any(title, date_keywords))

    place["tags"] = tags
    place["tag_sources"] = tag_sources

    return place


def make_skipped_item(reason, item):
    return {
        "reason": reason,
        "contentid": str(item.get("contentid", "")).strip(),
        "title": str(item.get("title", "")).strip(),
        "addr1": str(item.get("addr1", "")).strip(),
        "addr2": str(item.get("addr2", "")).strip(),
        "mapx": str(item.get("mapx", "")).strip(),
        "mapy": str(item.get("mapy", "")).strip(),
        "areacode": str(item.get("areacode", "")).strip(),
        "sigungucode": str(item.get("sigungucode", "")).strip(),
        "cat1": str(item.get("cat1", "")).strip(),
        "cat2": str(item.get("cat2", "")).strip(),
        "cat3": str(item.get("cat3", "")).strip(),
        "contenttypeid": str(item.get("contenttypeid", "")).strip(),
        "firstimage": str(item.get("firstimage", "")).strip(),
        "firstimage2": str(item.get("firstimage2", "")).strip(),
        "tel": str(item.get("tel", "")).strip(),
        "zipcode": str(item.get("zipcode", "")).strip(),
    }


def main():
    raw_data = load_json(INPUT_PATH)
    items = get_items(raw_data)

    busan_items = []
    no_coordinate_items = []
    invalid_coordinate_items = []
    duplicated_items = []

    seen_contentids = set()
    unique_items = []

    for item in items:
        if not is_busan(item):
            continue

        busan_items.append(item)

        if not has_coordinate(item):
            no_coordinate_items.append(make_skipped_item("no_coordinate", item))
            continue

        if not is_valid_busan_coordinate(item):
            invalid_coordinate_items.append(make_skipped_item("invalid_coordinate", item))
            continue

        contentid = str(item.get("contentid", "")).strip()

        if contentid in seen_contentids:
            duplicated_items.append(make_skipped_item("duplicated_contentid", item))
            continue

        seen_contentids.add(contentid)
        unique_items.append(item)

    tagged_places = []
    skipped_places = []

    for item in unique_items:
        place = make_common_place(item)
        place = apply_name_tags(place)

        if place["tags"]:
            tagged_places.append(place)
        else:
            skipped_places.append({
                "reason": "no_matched_tag",
                **place,
            })

    summary = {
        "input_file": str(INPUT_PATH),
        "total_raw_count": len(items),
        "busan_count": len(busan_items),
        "no_coordinate_count": len(no_coordinate_items),
        "invalid_coordinate_count": len(invalid_coordinate_items),
        "duplicated_count": len(duplicated_items),
        "unique_with_valid_coordinate_count": len(unique_items),
        "tagged_count": len(tagged_places),
        "skipped_no_tag_count": len(skipped_places),
        "tag_counts": {},
    }

    for place in tagged_places:
        for tag in place["tags"]:
            if tag not in summary["tag_counts"]:
                summary["tag_counts"][tag] = 0
            summary["tag_counts"][tag] += 1

    skipped_result = {
        "no_coordinate": no_coordinate_items,
        "invalid_coordinate": invalid_coordinate_items,
        "duplicated": duplicated_items,
        "no_matched_tag": skipped_places,
    }

    save_json(TAGGED_PATH, tagged_places)
    save_json(SKIPPED_PATH, skipped_result)
    save_json(SUMMARY_PATH, summary)

    print("관광지 부산 태그 작업 완료")
    print(f"전체 원본 개수: {summary['total_raw_count']}")
    print(f"부산 데이터 개수: {summary['busan_count']}")
    print(f"좌표 없는 데이터 개수: {summary['no_coordinate_count']}")
    print(f"부산 범위 밖 좌표 개수: {summary['invalid_coordinate_count']}")
    print(f"중복 제거 개수: {summary['duplicated_count']}")
    print(f"좌표 정상 부산 고유 데이터 개수: {summary['unique_with_valid_coordinate_count']}")
    print(f"태그 적용 개수: {summary['tagged_count']}")
    print(f"태그 없는 데이터 개수: {summary['skipped_no_tag_count']}")
    print()
    print("태그별 개수")
    for tag, count in summary["tag_counts"].items():
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()