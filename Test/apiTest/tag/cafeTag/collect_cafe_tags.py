import os
import re
import json
import time
import requests
from html import unescape
from dotenv import load_dotenv
from pathlib import Path


load_dotenv()

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"


# =========================
# 테스트 설정
# =========================

# 부산 서면역 근처
CENTER_LAT = 35.1577
CENTER_LNG = 129.0592

SEARCH_RADIUS = 1500

# 카카오는 한 페이지당 최대 15개까지만 가능
KAKAO_SEARCH_SIZE = 15

# 검색어 하나당 몇 페이지까지 가져올지
# 3이면 검색어 하나당 최대 45개 시도
KAKAO_SEARCH_PAGES = 3

# 네이버 블로그 검색어별 가져올 글 수
NAVER_BLOG_DISPLAY = 50

# 관련 블로그 글이 이 개수 미만이면 최종 결과에서 제외
MIN_BLOG_EVIDENCE_FOR_SAVE = 5

# 카카오 검색어
KAKAO_QUERIES = [
    "서면 카페",
    "서면 디저트 카페",
    "서면 감성카페",
    "서면 브런치 카페",
    "서면 베이커리 카페",
    "서면 조용한 카페",
    "서면 작업하기 좋은 카페",

    "전포 카페",
    "전포 디저트 카페",
    "전포 감성카페",
    "전포 브런치 카페",
    "전포 베이커리 카페",
    "전포 조용한 카페",
    "전포 작업하기 좋은 카페",
]


# =========================
# 제외 브랜드
# =========================
# 전통찻집, 생과일전문점 같은 카테고리는 제외하지 않음
# 저가/테이크아웃 위주 브랜드만 테스트 대상에서 제외

EXCLUDE_NAME_KEYWORDS = [
    "메가MGC커피",
    "메가커피",
    "빽다방",
    "컴포즈커피",
    "쥬씨",
    "매머드커피",
    "매머드익스프레스",
    "더벤티",
    "하삼동커피",
]


# =========================
# 태그 기준
# =========================

TAG_STATUS = {
    "suggested": "추천 태그 후보",
    "verified": "검증된 태그",
    "rejected": "반려된 태그",
}


TAG_KEYWORDS = {
    "노트북작업": [
        "노트북",
        "작업하기",
        "작업하기 좋은",
        "공부하기",
        "공부하기 좋은",
        "카공",
    ],
    "콘센트있음": [
        "콘센트",
        "전원",
        "충전",
        "플러그",
    ],
    "와이파이": [
        "와이파이",
        "wifi",
        "wi-fi",
        "무선인터넷",
    ],
    "조용한": [
        "조용한",
        "조용해서",
        "한적한",
        "차분한",
        "공부하기 좋은",
    ],
    "혼자이용좋음": [
        "혼카페",
        "혼자",
        "1인석",
        "바 좌석",
        "바좌석",
    ],
    "좌석많음": [
        "좌석 많",
        "자리가 많",
        "넓은 좌석",
    ],
    "오래머물기좋음": [
        "오래 머물",
        "오래 있기",
        "장시간",
        "편한 좌석",
    ],
    "주차가능": [
        "주차 가능",
        "주차가능",
        "무료주차",
        "전용 주차장",
        "건물 주차장",
        "주차 지원",
    ],
    "전망좋음": [
        "한강뷰",
        "시티뷰",
        "전망 좋",
        "뷰가 좋",
        "창가 자리",
    ],
    "야경": [
        "야경",
        "밤뷰",
        "야간뷰",
        "밤에 예쁜",
    ],
    "드라이브목적지": [
        "드라이브",
        "근교 카페",
        "외곽 카페",
        "차로 가기",
        "차 타고",
    ],
    "루프탑": [
        "루프탑",
        "옥상",
        "옥상 테라스",
    ],
    "디저트": [
        "디저트",
        "케이크",
        "베이커리",
        "빵",
    ],
    "분위기좋음": [
        "분위기",
        "감성",
        "인테리어",
        "예쁜 카페",
    ],
    "핫플": [
        "핫플",
        "핫플레이스",
        "인기 카페",
        "요즘 뜨는",
        "요즘 핫한",
        "사람 많",
        "사람이 많",
    ],
    "사진맛집": [
        "사진맛집",
        "사진 맛집",
        "포토존",
        "사진 찍기",
        "인생샷",
        "예쁘게 나오는",
    ],
    "데이트좋음": [
        "데이트",
        "데이트 코스",
        "연인",
        "커플",
        "기념일",
    ],
    "웨이팅주의": [
        "웨이팅",
        "대기",
        "줄 서",
        "줄서는",
        "만석",
        "사람 많",
        "사람이 많",
    ],
    "야외자리": [
        "야외석",
        "야외 자리",
        "테라스",
        "테라스석",
        "바깥 자리",
    ],
    "커피맛집": [
        "커피 맛집",
        "원두",
        "라떼 맛집",
        "에스프레소",
        "필터커피",
        "핸드드립",
    ],
}


NEGATIVE_KEYWORDS = {
    "주차가능": [
        "주차 불가",
        "주차불가",
        "주차 어려움",
        "주차가 어려움",
        "주차 안",
        "주차는 불편",
        "주차 힘",
        "주차공간 없음",
        "주차 공간 없음",
        "주차 지원 안",
        "주차 지원 없음",
        "근처 공영주차장",
        "주차는 근처",
        "주차는 별도",
        "유료주차",
        "주차비",
        "주차 요금",
    ],
    "조용한": [
        "시끄러운",
        "시끄러움",
        "소란",
        "붐비는",
        "붐빔",
        "정신없는",
        "사람 많",
        "사람이 많",
        "웨이팅",
        "만석",
    ],
    "콘센트있음": [
        "콘센트 없음",
        "콘센트없음",
        "콘센트 부족",
        "콘센트가 없",
        "콘센트는 없음",
        "충전 어려움",
    ],
    "와이파이": [
        "와이파이 없음",
        "와이파이없음",
        "wifi 없음",
        "wi-fi 없음",
        "무선인터넷 없음",
    ],
    "좌석많음": [
        "좌석 부족",
        "자리가 부족",
        "자리 없음",
        "만석",
        "협소",
    ],
    "오래머물기좋음": [
        "오래 있기 어려움",
        "오래 머물기 어려움",
        "이용 시간 제한",
        "시간 제한",
        "회전율",
    ],
    "야외자리": [
        "테라스 없음",
        "야외석 없음",
        "야외 자리 없음",
        "테라스는 없음",
    ],
    "커피맛집": [
        "커피는 아쉬움",
        "커피가 아쉬움",
        "커피 맛은 아쉬움",
        "커피는 평범",
    ],
}


TAG_MIN_COUNTS = {
    "디저트": 2,
    "분위기좋음": 3,

    "노트북작업": 3,
    "콘센트있음": 3,
    "와이파이": 3,
    "혼자이용좋음": 3,

    "조용한": 4,
    "좌석많음": 4,
    "오래머물기좋음": 4,

    "주차가능": 3,

    "전망좋음": 5,
    "야경": 5,
    "루프탑": 4,
    "드라이브목적지": 5,

    "핫플": 3,
    "사진맛집": 3,
    "데이트좋음": 3,
    "웨이팅주의": 2,
    "야외자리": 3,
    "커피맛집": 3,
}


WEAK_PLACE_NAME_WORDS = [
    "카페",
    "커피",
    "다방",
    "마당",
    "아트",
    "라운지",
    "스튜디오",
]


# =========================
# 공통 유틸
# =========================

def clean_text(value):
    if not value:
        return ""

    text = unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip().lower()


def normalize_for_match(value):
    value = clean_text(value)
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[^0-9a-z가-힣]", "", value)

    return value


def is_weak_place_name(place_name):
    normalized_name = normalize_for_match(place_name)

    if len(normalized_name) <= 4:
        return True

    for word in WEAK_PLACE_NAME_WORDS:
        if normalized_name == normalize_for_match(word):
            return True

    return False


def get_address_keywords(address):
    address_parts = address.split()

    sigungu = address_parts[1] if len(address_parts) > 1 else ""
    road = address_parts[2] if len(address_parts) > 2 else ""

    keywords = []

    if sigungu:
        keywords.append(sigungu)

    if road:
        keywords.append(road)

    return keywords


# =========================
# 카카오 장소 검색
# =========================

def is_cafe_place(place):
    category_name = place.get("category_name", "")

    return "카페" in category_name


def should_skip_place(place):
    name = place.get("place_name", "")
    category = place.get("category_name", "")

    if not is_cafe_place(place):
        return True, "카페 카테고리 아님"

    for keyword in EXCLUDE_NAME_KEYWORDS:
        if keyword in name:
            return True, f"제외 브랜드: {keyword}"

    return False, ""


def search_kakao_cafes(query, lat=None, lng=None, radius=1000, size=10, page=1):
    if not KAKAO_REST_API_KEY:
        raise ValueError("KAKAO_REST_API_KEY가 없습니다.")

    headers = {
        "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}",
    }

    params = {
        "query": query,
        "size": size,
        "page": page,
    }

    if lat is not None and lng is not None:
        params.update({
            "x": lng,
            "y": lat,
            "radius": radius,
            "sort": "accuracy",
        })

    response = requests.get(
        KAKAO_KEYWORD_URL,
        headers=headers,
        params=params,
        timeout=5,
    )
    response.raise_for_status()

    return response.json()


def collect_kakao_places():
    all_places = []
    seen_ids = set()
    skipped_places = []

    for query in KAKAO_QUERIES:
        print(f"\n카카오 검색: {query}")

        for page in range(1, KAKAO_SEARCH_PAGES + 1):
            try:
                data = search_kakao_cafes(
                    query=query,
                    lat=CENTER_LAT,
                    lng=CENTER_LNG,
                    radius=SEARCH_RADIUS,
                    size=KAKAO_SEARCH_SIZE,
                    page=page,
                )

                places = data.get("documents", [])
                meta = data.get("meta", {})

                time.sleep(0.2)

            except Exception as error:
                print(f"  카카오 검색 실패: {error}")
                break

            print(f"  {page}페이지 검색 결과 {len(places)}건")

            if not places:
                break

            for place in places:
                place_id = place.get("id")

                if not place_id:
                    continue

                if place_id in seen_ids:
                    continue

                seen_ids.add(place_id)

                skip, reason = should_skip_place(place)

                if skip:
                    skipped_places.append({
                        "source": "kakao_local",
                        "external_id": place.get("id"),
                        "name": place.get("place_name"),
                        "category": place.get("category_name"),
                        "address": place.get("road_address_name") or place.get("address_name"),
                        "phone": place.get("phone"),
                        "place_url": place.get("place_url"),
                        "skip_reason": reason,
                    })
                    print(f"  제외: {place.get('place_name')} / {reason}")
                    continue

                all_places.append(place)

            if meta.get("is_end"):
                break

    return all_places, skipped_places


# =========================
# 네이버 블로그 검색
# =========================

def search_naver_blogs(query, display=NAVER_BLOG_DISPLAY):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 없습니다.")

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    params = {
        "query": query,
        "display": display,
        "start": 1,
        "sort": "sim",
    }

    response = requests.get(
        NAVER_BLOG_URL,
        headers=headers,
        params=params,
        timeout=5,
    )
    response.raise_for_status()

    return response.json().get("items", [])


def build_blog_queries(place_name, address):
    address_parts = address.split()

    sido = address_parts[0] if len(address_parts) > 0 else ""
    sigungu = address_parts[1] if len(address_parts) > 1 else ""
    road = address_parts[2] if len(address_parts) > 2 else ""

    queries = [
        f"{place_name} {sido} {sigungu}",
        f"{place_name} {road}",
        place_name,
    ]

    return [query.strip() for query in queries if query.strip()]


def is_related_blog_item(place_name, address, item):
    title = clean_text(item.get("title", ""))
    description = clean_text(item.get("description", ""))

    text = normalize_for_match(title + " " + description)
    normalized_place_name = normalize_for_match(place_name)

    if not normalized_place_name:
        return False

    has_place_name = normalized_place_name in text

    if not has_place_name:
        return False

    address_keywords = get_address_keywords(address)

    normalized_address_keywords = [
        normalize_for_match(keyword)
        for keyword in address_keywords
        if keyword
    ]

    has_address_keyword = any(
        keyword in text
        for keyword in normalized_address_keywords
        if keyword
    )

    return has_address_keyword


def remove_duplicate_blog_items(items):
    unique_items = []
    seen_links = set()

    for item in items:
        link = item.get("link")

        if not link:
            continue

        if link in seen_links:
            continue

        seen_links.add(link)
        unique_items.append(item)

    return unique_items


# =========================
# 태그 분석
# =========================

def has_negative_keyword(tag_name, text):
    negative_words = NEGATIVE_KEYWORDS.get(tag_name, [])

    for word in negative_words:
        if word.lower() in text:
            return True

    return False


def get_matched_keywords(tag_name, text):
    keywords = TAG_KEYWORDS.get(tag_name, [])

    matched = []

    for word in keywords:
        if word.lower() in text:
            matched.append(word)

    return matched


def analyze_blog_items(items):
    tag_hits = {}
    tag_words = {}

    for item in items:
        description = clean_text(item.get("description", ""))

        # 태그 판단은 제목보다 요약(description)을 우선 사용
        tag_text = description
        link = item.get("link") or description

        if not tag_text:
            continue

        for tag_name in TAG_KEYWORDS:
            if has_negative_keyword(tag_name, tag_text):
                continue

            matched = get_matched_keywords(tag_name, tag_text)

            if not matched:
                continue

            tag_hits.setdefault(tag_name, set()).add(link)
            tag_words.setdefault(tag_name, set()).update(matched)

    tags = []

    for tag_name, links in tag_hits.items():
        count = len(links)
        required_count = TAG_MIN_COUNTS.get(tag_name, 4)

        if count < required_count:
            continue

        confidence = min(60 + count * 4, 88)
        keywords = sorted(tag_words.get(tag_name, []))

        tags.append({
            "name": tag_name,
            "confidence": confidence,
            "status": "suggested",
            "status_label": TAG_STATUS["suggested"],
            "evidence_count": count,
            "required_count": required_count,
            "evidence": f"네이버 블로그 검색 결과 {count}건에서 {', '.join(keywords)} 표현 확인",
            "source": "naver_blog_description",
            "is_ai_generated": False,
            "is_verified": False,
        })

    return tags


def collect_tags_for_cafe(place):
    place_name = place.get("place_name", "")
    address = place.get("road_address_name") or place.get("address_name") or ""

    all_blog_items = []

    for query in build_blog_queries(place_name, address):
        try:
            print(f"  - 블로그 검색: {query}")
            items = search_naver_blogs(query)

            related_items = []

            for item in items:
                if is_related_blog_item(place_name, address, item):
                    related_items.append(item)

            print(f"    관련 글 {len(related_items)}건 사용 / 전체 {len(items)}건")

            all_blog_items.extend(related_items)
            time.sleep(0.2)

        except Exception as error:
            print(f"    검색 실패: {error}")

    all_blog_items = remove_duplicate_blog_items(all_blog_items)
    tags = analyze_blog_items(all_blog_items)

    return {
        "source": "kakao_local",
        "external_id": place.get("id"),
        "name": place_name,
        "category": place.get("category_name"),
        "address": address,
        "lat": float(place.get("y")),
        "lng": float(place.get("x")),
        "phone": place.get("phone"),
        "place_url": place.get("place_url"),
        "blog_evidence_count": len(all_blog_items),
        "tags": tags,
    }


# =========================
# 실행
# =========================

def main():
    places, skipped_places = collect_kakao_places()

    print(f"\n카카오 후보 수집 완료")
    print(f"분석 대상 장소 수: {len(places)}")
    print(f"카카오 단계 제외 장소 수: {len(skipped_places)}\n")

    results = []
    skipped_after_blog = []

    for index, place in enumerate(places, start=1):
        print(f"[{index}/{len(places)}] {place.get('place_name')}")

        result = collect_tags_for_cafe(place)

        if result["blog_evidence_count"] < MIN_BLOG_EVIDENCE_FOR_SAVE:
            skipped_after_blog.append({
                **result,
                "skip_reason": f"관련 블로그 글 {MIN_BLOG_EVIDENCE_FOR_SAVE}건 미만",
            })
            print(f"  최종 제외: 관련 블로그 글 {result['blog_evidence_count']}건\n")
            time.sleep(0.3)
            continue

        results.append(result)
        time.sleep(0.3)

    script_dir = Path(__file__).resolve().parent

    output_path = script_dir / "cafe_tag_results.json"
    skipped_output_path = script_dir / "cafe_tag_skipped_results.json"

    all_skipped_results = skipped_places + skipped_after_blog

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)

    with open(skipped_output_path, "w", encoding="utf-8") as file:
        json.dump(all_skipped_results, file, ensure_ascii=False, indent=2)

    print(f"\n완료: {output_path} 저장")
    print(f"제외 결과: {skipped_output_path} 저장")
    print(f"최종 저장 장소 수: {len(results)}")
    print(f"제외 장소 수: {len(all_skipped_results)}")


if __name__ == "__main__":
    main()