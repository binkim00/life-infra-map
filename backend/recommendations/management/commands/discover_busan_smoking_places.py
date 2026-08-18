import csv
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.models import Place


RETRIEVED_AT = "2026-08-18"


DISTRICT_SOURCES = [
    {"district": district, "official_source_found": district in {"동구", "연제구", "사하구", "부산진구", "사상구"}, "notes": notes}
    for district, notes in [
        ("중구", "구청·보건소·공공데이터·보도자료 검색. 위치 목록 미발견"),
        ("서구", "구청·보건소·공공데이터·보도자료 검색. 위치 목록 미발견"),
        ("동구", "보건소의 2024 실외 흡연실 설치·지정 안내 확인. 개별 위치 목록은 검색 색인에서 미발견"),
        ("영도구", "구청·보건소·공공데이터·보도자료 검색. 위치 목록 미발견"),
        ("부산진구", "2026 주민참여예산의 설치 제안 확인. 설치 완료 근거가 아니므로 후보 제외"),
        ("동래구", "구청·보건소·공공데이터·보도자료 검색. 위치 목록 미발견"),
        ("남구", "구청·보건소·공공데이터·보도자료 검색. 위치 목록 미발견"),
        ("북구", "구청·보건소·공공데이터·보도자료 검색. 위치 목록 미발견"),
        ("해운대구", "구청·보건소·BEXCO 시설자료 검색. 흡연 위치를 명시한 최신 공식 페이지 미발견"),
        ("사하구", "2021·2024 주민참여예산에서 흡연부스 제안이 실행불가였음을 확인"),
        ("금정구", "구청·보건소·공공데이터·보도자료 검색. 위치 목록 미발견"),
        ("강서구", "한국공항공사 김해공항 공식 시설 홈페이지 확인. DB에 이미 공항 6건 존재"),
        ("연제구", "공공데이터포털 2025-09-05 흡연실 현황 105행 확인. DB에 103건 존재"),
        ("수영구", "구청·보건소·광안리 시설자료 검색. 위치 목록 미발견"),
        ("사상구", "2012 정부 정책기사의 서부버스터미널 흡연부스 확인. 최신 운영 근거 부족"),
        ("기장군", "군청·보건소·공공데이터·보도자료 검색. 위치 목록 미발견"),
    ]
]


CANDIDATES = [
    {
        "candidate_name": "부산역 5번 출구 외부 흡연구역",
        "facility_type": "designated_smoking_area",
        "smoking_permission": "unverified",
        "district": "동구",
        "address": "부산광역시 동구 중앙대로 206",
        "location_description": "부산역 5번 출구 외부, 아스티호텔 방면",
        "latitude": None,
        "longitude": None,
        "source_url": "https://pioom.cloud/blog/busan-station-smoking-area-guide",
        "source_title": "부산역 주변 흡연구역 가이드",
        "source_type": "web_guide",
        "published_at": "2026-05",
        "retrieved_at": RETRIEVED_AT,
        "evidence_span": "부산역의 공식 지정 흡연구역은 역사 5번 출구 외부(아스티호텔 방면)",
        "identity_confidence": 85,
        "evidence_confidence": 58,
        "freshness": "recent_web_only",
        "status": "HIGH_CONFIDENCE_WEB",
        "source_count": 2,
        "last_verified_at": RETRIEVED_AT,
        "notes": "최신 웹문서 1건뿐. 코레일/부산역 공식 현행 안내로 재검증 필요",
    },
    {
        "candidate_name": "부산서부버스터미널 승강장 앞 흡연부스",
        "facility_type": "smoking_booth",
        "smoking_permission": "unverified",
        "district": "사상구",
        "address": "부산광역시 사상구 사상로 201",
        "location_description": "서부시외버스터미널 승강장 앞",
        "latitude": None,
        "longitude": None,
        "source_url": "https://m.korea.kr/news/policyNewsView.do?newsId=148737615",
        "source_title": "금연구역 취지는 좋은데 흡연자들은 어떡하라고?",
        "source_type": "government_policy_article",
        "published_at": "2012",
        "retrieved_at": RETRIEVED_AT,
        "evidence_span": "부산 사상구 서부시외버스터미널 승강장 앞에 설치된 흡연부스",
        "identity_confidence": 90,
        "evidence_confidence": 78,
        "freshness": "stale_official",
        "status": "STALE",
        "source_count": 1,
        "last_verified_at": "2012",
        "notes": "공식 설치 근거는 명확하지만 14년 경과. 철거·이전 가능성 때문에 needs_verification",
    },
    {
        "candidate_name": "김해공항 국제선 출국장 흡연실",
        "facility_type": "smoking_room",
        "smoking_permission": "designated",
        "district": "강서구",
        "address": "부산광역시 강서구 공항진입로 108",
        "location_description": "국제선 출국심사 후 면세구역 내",
        "latitude": 35.1796,
        "longitude": 128.9382,
        "source_url": "https://www.airport.co.kr/gimhae/",
        "source_title": "김해국제공항 공식 홈페이지",
        "source_type": "official_public_facility",
        "published_at": None,
        "retrieved_at": RETRIEVED_AT,
        "evidence_span": "공항 공식 시설 페이지는 현행 운영 주체를 확인하나 검색 색인 본문에는 흡연실 위치가 노출되지 않음",
        "identity_confidence": 100,
        "evidence_confidence": 80,
        "freshness": "current_official_identity",
        "status": "EXISTING",
        "source_count": 2,
        "last_verified_at": RETRIEVED_AT,
        "notes": "DB smokearea_kr_supabase 레코드와 동일",
    },
    {
        "candidate_name": "사하구 학교 주변 흡연부스 제안",
        "facility_type": "smoking_booth",
        "smoking_permission": "not_installed",
        "district": "사하구",
        "address": "",
        "location_description": "장소 미정 제안",
        "latitude": None,
        "longitude": None,
        "source_url": "https://www.busan.go.kr/yesan/spiritOffer1/1479154",
        "source_title": "사하구 학교 주변 길거리 흡연부스 설치 주민참여예산",
        "source_type": "official_budget_review",
        "published_at": "2021",
        "retrieved_at": RETRIEVED_AT,
        "evidence_span": "부지 선정 및 관리 문제를 들어 설치 곤란 검토",
        "identity_confidence": 0,
        "evidence_confidence": 95,
        "freshness": "historical_rejection",
        "status": "REJECTED",
        "source_count": 1,
        "last_verified_at": "2021",
        "notes": "설치 제안일 뿐 실제 장소가 아님",
    },
]


# Facility-first inventory.  These are investigation targets, not smoking places.
FACILITY_INVENTORY = [
    ("부산역", "동구", "transport"), ("부산서부버스터미널", "사상구", "transport"),
    ("부산종합버스터미널", "금정구", "transport"), ("김해국제공항", "강서구", "transport"),
    ("부산항 국제여객터미널", "동구", "transport"), ("부전역", "부산진구", "transport"),
    ("사상역", "사상구", "transport"), ("서면역", "부산진구", "transport"),
    ("동래역", "동래구", "transport"), ("연산역", "연제구", "transport"),
    ("센텀시티역", "해운대구", "transport"), ("해운대역", "해운대구", "transport"),
    ("덕천역", "북구", "transport"), ("수영역", "수영구", "transport"),
    ("부산대역", "금정구", "transport"),
    ("자갈치시장", "중구", "market_tourism"), ("국제시장", "중구", "market_tourism"),
    ("부평깡통시장", "중구", "market_tourism"), ("남포동 BIFF광장", "중구", "market_tourism"),
    ("광복동 패션거리", "중구", "market_tourism"), ("용두산공원", "중구", "market_tourism"),
    ("감천문화마을", "사하구", "market_tourism"), ("다대포해수욕장", "사하구", "market_tourism"),
    ("해운대해수욕장", "해운대구", "market_tourism"), ("송정해수욕장", "해운대구", "market_tourism"),
    ("광안리해수욕장", "수영구", "market_tourism"), ("민락수변공원", "수영구", "market_tourism"),
    ("태종대", "영도구", "market_tourism"), ("흰여울문화마을", "영도구", "market_tourism"),
    ("국립해양박물관", "영도구", "market_tourism"), ("오륙도 스카이워크", "남구", "market_tourism"),
    ("부산시민공원", "부산진구", "market_tourism"), ("어린이대공원", "부산진구", "market_tourism"),
    ("금강공원", "동래구", "market_tourism"), ("화명생태공원", "북구", "market_tourism"),
    ("을숙도생태공원", "사하구", "market_tourism"), ("기장시장", "기장군", "market_tourism"),
    ("아홉산숲", "기장군", "market_tourism"), ("아난티 코브", "기장군", "market_tourism"),
    ("BEXCO 제1전시장", "해운대구", "large_facility"), ("BEXCO 제2전시장", "해운대구", "large_facility"),
    ("신세계백화점 센텀시티", "해운대구", "shopping"), ("롯데백화점 센텀시티점", "해운대구", "shopping"),
    ("롯데백화점 부산본점", "부산진구", "shopping"), ("롯데백화점 광복점", "중구", "shopping"),
    ("롯데백화점 동래점", "동래구", "shopping"), ("롯데몰 동부산점", "기장군", "shopping"),
    ("NC백화점 서면점", "부산진구", "shopping"), ("NC백화점 부산대점", "금정구", "shopping"),
    ("삼정타워", "부산진구", "shopping"), ("서면 지하도상가", "부산진구", "shopping"),
    ("홈플러스 센텀시티점", "해운대구", "shopping"), ("르네시떼", "사상구", "shopping"),
    ("애플아울렛", "사상구", "shopping"), ("메가마트 동래점", "동래구", "shopping"),
    ("영화의전당", "해운대구", "culture"),
    ("파라다이스호텔 부산", "해운대구", "hotel"), ("시그니엘 부산", "해운대구", "hotel"),
    ("웨스틴 조선 부산", "해운대구", "hotel"), ("그랜드 조선 부산", "해운대구", "hotel"),
    ("파크하얏트 부산", "해운대구", "hotel"), ("롯데호텔 부산", "부산진구", "hotel"),
    ("아스티호텔 부산역", "동구", "hotel"), ("코모도호텔 부산", "중구", "hotel"),
    ("호텔농심", "동래구", "hotel"), ("힐튼 부산", "기장군", "hotel"),
    ("부산대학교병원", "서구", "hospital"), ("동아대학교병원", "서구", "hospital"),
    ("고신대학교복음병원", "서구", "hospital"), ("인제대학교 부산백병원", "부산진구", "hospital"),
    ("인제대학교 해운대백병원", "해운대구", "hospital"), ("부산성모병원", "남구", "hospital"),
    ("부산의료원", "연제구", "hospital"), ("동래봉생병원", "동래구", "hospital"),
    ("좋은강안병원", "수영구", "hospital"), ("부민병원", "북구", "hospital"),
    ("부산대학교", "금정구", "university"), ("부경대학교 대연캠퍼스", "남구", "university"),
    ("경성대학교", "남구", "university"), ("동아대학교 승학캠퍼스", "사하구", "university"),
    ("동의대학교", "부산진구", "university"), ("한국해양대학교", "영도구", "university"),
    ("신라대학교", "사상구", "university"), ("동서대학교", "사상구", "university"),
    ("부산외국어대학교", "금정구", "university"), ("고신대학교 영도캠퍼스", "영도구", "university"),
    ("부산광역시청", "연제구", "public_sports"), ("부산진구청", "부산진구", "public_sports"),
    ("해운대구청", "해운대구", "public_sports"), ("중부소방서", "중구", "public_sports"),
    ("부산아시아드주경기장", "연제구", "public_sports"), ("사직야구장", "동래구", "public_sports"),
    ("부산체육회관", "동래구", "public_sports"), ("구덕운동장", "서구", "public_sports"),
    ("부산문화회관", "남구", "public_sports"), ("부산시민회관", "동구", "public_sports"),
    ("부산항 연안여객터미널", "중구", "transport"), ("노포역", "금정구", "transport"),
    ("부산공동어시장", "서구", "market_tourism"), ("스포원파크", "금정구", "public_sports"),
]

assert len(FACILITY_INVENTORY) == 100


PIOOM_REGION_URL = "https://pioom.cloud/zones/regions"


def web_candidate(name, district, location, url, status="NEEDS_VERIFICATION", address="", confirmations=None,
                  negative_reports=None, notes="", source_title=None):
    return {
        "candidate_name": name, "facility_type": "smoking_area_candidate",
        "smoking_permission": "unverified", "district": district, "address": address,
        "location_description": location, "latitude": None, "longitude": None,
        "source_url": url, "source_title": source_title or name,
        "source_type": "web_location_service", "published_at": None,
        "retrieved_at": RETRIEVED_AT, "evidence_span": f"{name}으로 위치 안내; 재떨이 편의시설 표시",
        "identity_confidence": 85 if address else 65,
        "evidence_confidence": 80 if status == "HIGH_CONFIDENCE_WEB" else 58,
        "freshness": "recent_user_check" if confirmations else "unknown",
        "status": status, "source_count": 1, "last_verified_at": RETRIEVED_AT if confirmations else None,
        "confirmations": confirmations or 0, "negative_reports": negative_reports or 0,
        "notes": notes or "웹 위치 서비스 단일 출처; 공식 허용 여부 미확인",
    }


CANDIDATES.extend([
    {
        "candidate_name": "부산 중부소방서 흡연부스", "facility_type": "smoking_booth",
        "smoking_permission": "unverified", "district": "중구", "address": "부산광역시 중구 중앙대로 110",
        "location_description": "중부소방서 청사 내 설치 위치 미공개", "latitude": None, "longitude": None,
        "source_url": "https://www.busan.go.kr/depart/abcontract?curPage=5&schCtrtkindcd=1",
        "source_title": "중부소방서 흡연부스 설치 공사 계약", "source_type": "official_contract",
        "published_at": "2026-06-17", "retrieved_at": RETRIEVED_AT,
        "evidence_span": "중부소방서 흡연부스 설치 공사 발주 및 계약 체결, 계약금액 8,950,000원",
        "identity_confidence": 100, "evidence_confidence": 88, "freshness": "current_contract",
        "status": "NEEDS_VERIFICATION", "source_count": 2, "last_verified_at": "2026-06-23",
        "notes": "설치 계약과 공식 청사 주소는 확인. 준공·현재 이용 가능 여부 확인 전 confirmed 금지",
    },
    {
        "candidate_name": "어반풋볼파크 부산사상점 B구장 뒤 재떨이", "facility_type": "ashtray_only",
        "smoking_permission": "unknown", "district": "사상구", "address": "부산광역시 사상구 광장로 7",
        "location_description": "르네시떼 주차장 옥상 B구장 뒤", "latitude": None, "longitude": None,
        "source_url": "https://www.urbanfootball.co.kr/goods/goods_view.html?goods_no=57821",
        "source_title": "어반풋볼파크 부산사상점 이용안내", "source_type": "official_facility_operator",
        "published_at": None, "retrieved_at": RETRIEVED_AT,
        "evidence_span": "흡연구역준수(B구장 뒤 재떨이)", "identity_confidence": 95,
        "evidence_confidence": 90, "freshness": "current_facility_page", "status": "ASHTRAY_ONLY",
        "source_count": 1, "last_verified_at": RETRIEVED_AT,
        "notes": "재떨이와 운영사 안내는 확인. 공식 지정 흡연구역 여부는 unknown 유지",
    },
    web_candidate("광복동 패션거리 흡연구역", "중구", "광복중앙로 38", "https://pioom.cloud/zones/b269fa48-6f73-4b4e-a594-acc4988e6d6e", "HIGH_CONFIDENCE_WEB", "부산 중구 광복중앙로 38", 1, 0),
    web_candidate("남포역 5번 출구 흡연구역", "중구", "남포역 5번 출구", "https://pioom.cloud/zones/32adc274-b232-4c54-808a-7ee36eee000f", "NEEDS_VERIFICATION", "부산 중구 남포동 2가", 3, 2, "최근 확인 3건이나 위치 부정확 신고 2건"),
    web_candidate("자갈치역 7번 출구 흡연구역", "중구", "자갈치역 7번 출구", "https://pioom.cloud/zones/0d2c7f62-c187-4995-8853-e03f237d8e86", "POSSIBLY_REMOVED", "부산 중구 자갈치해안로 52", 0, 1, "폐쇄 신고 1건; 현장 확인 전 노출 비권장"),
    web_candidate("롯데백화점 부산본점 옆 흡연구역", "부산진구", "롯데백화점 옆", "https://pioom.cloud/zones/e8a2b4e4-e37a-4049-b493-b5e15f5946b2"),
    web_candidate("서면역 1번 출구 흡연구역", "부산진구", "서면역 1번 출구", "https://pioom.cloud/zones/3acb0785-1e3b-46ed-89e6-f93d3324b09d", "HIGH_CONFIDENCE_WEB", "부산 부산진구 중앙대로 680", 2, 1, "최근 확인 2건, 위치 부정확 신고 1건"),
    web_candidate("센텀시티역 6번 출구 흡연구역", "해운대구", "센텀시티역 6번 출구", "https://pioom.cloud/zones/47e54e12-4734-46a2-9826-3c7b58cd5015", "HIGH_CONFIDENCE_WEB", "부산 해운대구 센텀남대로 35", 5, 2, "최근 확인 5건; 위치 부정확 1건·폐쇄 1건도 있어 현장 안내 확인 필요"),
    web_candidate("해운대역 3번 출구 흡연구역", "해운대구", "해운대역 3번 출구", "https://pioom.cloud/zones/e0c7b080-4ee1-4b80-a7b2-33f56fb92038", "HIGH_CONFIDENCE_WEB", "부산 해운대구 구남로 33", 14, 3, "최근 확인 14건, 부정 신호 3건"),
    web_candidate("부산대역 3번 출구 흡연구역", "금정구", "부산대역 3번 출구", "https://pioom.cloud/zones/7cb99b80-13a8-4296-972b-f8600208ecec"),
    web_candidate("동래역 1번 출구 흡연구역", "동래구", "동래역 1번 출구", "https://pioom.cloud/zones/d460b152-71a7-4b6a-8772-4608c5930e46"),
    web_candidate("덕천역 3번 출구 흡연구역", "북구", "덕천역 3번 출구", "https://pioom.cloud/zones/cf1be592-2dce-459c-8257-b53de030521a"),
    web_candidate("사상역 5번 출구 흡연구역", "사상구", "사상역 5번 출구", "https://pioom.cloud/zones/21c0988b-711b-4e31-b2dd-f977c6f85376"),
    web_candidate("수영역 4번 출구 흡연구역", "수영구", "수영역 4번 출구", "https://pioom.cloud/zones/1d4fba12-29ab-42f9-a81c-7199206a3ec1"),
    web_candidate("바른병원 인근 재떨이", "중구", "광복동 패션거리 후보에서 약 486m", "https://pioom.cloud/zones/486e231e-d664-43b7-b354-df9fab381f12", "ASHTRAY_ONLY", notes="상세 주소·공식 흡연 허용 확인 전 재떨이 후보로만 유지"),
    web_candidate("바른빌딩 인근 재떨이", "중구", "광복동 패션거리 후보에서 약 486m", "https://pioom.cloud/zones/1d8149b5-01d3-473e-b9e8-e4c8c5f683d7", "ASHTRAY_ONLY", notes="상세 주소·공식 흡연 허용 확인 전 재떨이 후보로만 유지"),
    web_candidate("한국전력 남부건설공사 인근 재떨이", "중구", "광복동 패션거리 후보에서 약 489m", "https://pioom.cloud/zones/9a885f04-ceb2-4e4f-80e4-e039fb920773", "ASHTRAY_ONLY", notes="상세 주소·공식 흡연 허용 확인 전 재떨이 후보로만 유지"),
])

# A web smoking candidate may mention an ashtray, but ASHTRAY_ONLY is reserved for
# records where the ashtray is the only independently usable fact.
for candidate in CANDIDATES:
    if candidate["status"] == "ASHTRAY_ONLY":
        candidate["facility_type"] = "ashtray_only"
        candidate["smoking_permission"] = "unknown"


HUBS = [
    ("부산역", 35.1152, 129.0414), ("서면", 35.1578, 129.0590),
    ("남포동", 35.0978, 129.0348), ("해운대", 35.1632, 129.1636),
    ("광안리", 35.1532, 129.1187), ("센텀", 35.1690, 129.1302),
    ("사상", 35.1623, 128.9840), ("부산서부버스터미널", 35.1623, 128.9840),
    ("동래", 35.2056, 129.0785), ("연산", 35.1861, 129.0815),
    ("경성대/부경대", 35.1376, 129.1005),
]


def distance_m(lat1, lng1, lat2, lng2):
    radius = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def normalize(value):
    return re.sub(r"[^0-9a-z가-힣]", "", (value or "").lower())


class Command(BaseCommand):
    help = "Create a read-only 부산 smoking-place baseline and discovery dry-run report."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="tmp")

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        baseline = list(Place.objects.filter(category="smoking_area", lat__gte=34.8, lat__lte=35.4, lng__gte=128.7, lng__lte=129.35).order_by("id"))
        key_for = lambda p: (normalize(p.address), round(p.lat, 5), round(p.lng, 5))
        key_counts = Counter(key_for(p) for p in baseline)
        duplicate_keys = {key for key, count in key_counts.items() if count > 1}
        duplicate_groups = []
        for number, key in enumerate(sorted(duplicate_keys), 1):
            members = [p for p in baseline if key_for(p) == key]
            commercial = any(any(token in p.name for token in ("PC", "피씨", "당구")) for p in members)
            duplicate_groups.append({"group_id": number, "classification": "SAME_BUILDING_DIFFERENT_FACILITY" if commercial else "AMBIGUOUS", "place_ids": [p.id for p in members], "names": [p.name for p in members]})
        baseline_rows = []
        for place in baseline:
            source_class = "structured_public_data" if "연제구_흡연실" in place.source else "airport_facility"
            audit_status = "DUPLICATE_CANDIDATE" if key_for(place) in duplicate_keys else ("CURRENT_BUT_UNVERIFIED" if source_class == "structured_public_data" else "NEEDS_VERIFICATION")
            baseline_rows.append({
                "id": place.id, "name": place.name, "category": place.category,
                "address": place.address, "latitude": place.lat, "longitude": place.lng,
                "source": place.source, "external_id": place.external_id,
                "source_name": place.source_name,
                "source_updated_at": place.source_updated_at.isoformat() if place.source_updated_at else None,
                "created_at": place.created_at.isoformat() if place.created_at else None,
                "detail_location": place.detail_location, "raw": place.raw,
                "data_quality_status": place.data_quality_status,
                "source_class": source_class, "audit_status": audit_status,
                "duplicate_group": next((g for g in duplicate_groups if place.id in g["place_ids"]), None),
                "evidence": list(place.tag_evidence.select_related("tag").values("tag__name", "source", "source_reference", "confidence", "evidence", "observed_at", "expires_at", "raw")),
            })

        for candidate in CANDIDATES:
            matches = []
            for place in baseline:
                dist = distance_m(candidate["latitude"], candidate["longitude"], place.lat, place.lng) if candidate["latitude"] is not None else None
                name_match = normalize(candidate["candidate_name"]) == normalize(place.name)
                address_match = bool(candidate["address"] and normalize(candidate["address"]) == normalize(place.address))
                if (dist is not None and dist <= 100) or name_match or address_match:
                    matches.append({"place_id": place.id, "name": place.name, "distance_m": round(dist, 1) if dist is not None else None, "name_match": name_match, "address_match": address_match, "source": place.source, "external_id": place.external_id})
            candidate["dedup_matches"] = matches
            candidate["dedup_result"] = "EXISTING" if candidate["status"] == "EXISTING" or matches else ("NEW" if candidate["identity_confidence"] >= 60 else "AMBIGUOUS")

        hub_terms = {"부산역": ["부산역"], "서면": ["서면", "부산본점"], "남포동": ["남포", "광복동", "자갈치"], "부산항": ["부산항"], "해운대": ["해운대역"], "광안리": ["광안리"], "센텀": ["센텀"], "사상": ["사상역", "르네시떼"], "부산서부버스터미널": ["서부버스터미널"], "노포터미널": ["노포", "종합버스터미널"], "동래": ["동래역"], "연산": ["연산"], "경성대/부경대": ["경성", "부경"], "김해공항": ["김해공항"], "BEXCO": ["BEXCO"]}
        coverage = []
        for hub, terms in hub_terms.items():
            related = [c for c in CANDIDATES if any(t.lower() in (c["candidate_name"] + c["location_description"]).lower() for t in terms)]
            existing = [r for r in baseline_rows if any(t.lower() in (r["name"] + (r["address"] or "")).lower() for t in terms)]
            coverage.append({"hub": hub, "existing_db": [{"id": r["id"], "name": r["name"]} for r in existing], "official_smoking_places": [c["candidate_name"] for c in related if c["status"] == "VERIFIED_OFFICIAL"], "web_candidates": [c["candidate_name"] for c in related if c["status"] in {"HIGH_CONFIDENCE_WEB", "NEEDS_VERIFICATION", "STALE", "POSSIBLY_REMOVED"}], "ashtrays": [c["candidate_name"] for c in related if c["status"] == "ASHTRAY_ONLY"], "coverage": "evidence_found" if existing or related else "none"})
        facility_rows = []
        for name, district, kind in FACILITY_INVENTORY:
            related = [c["candidate_name"] for c in CANDIDATES if normalize(name) in normalize(c["candidate_name"] + c["location_description"])]
            facility_rows.append({"facility": name, "district": district, "kind": kind, "search_terms": ["흡연실", "흡연구역", "흡연부스", "재떨이"], "evidence_found": bool(related), "candidate_names": related, "status": "evidence_found" if related else "no_indexed_evidence"})
        district_coverage = []
        for district in (row["district"] for row in DISTRICT_SOURCES):
            rows = [r for r in baseline_rows if district in (r["address"] or "") or (district == "강서구" and r["source_class"] == "airport_facility")]
            found = [c for c in CANDIDATES if c["district"] == district and c["status"] != "EXISTING"]
            district_coverage.append({"district": district, "existing": len(rows), "verified": sum(r["audit_status"] == "VERIFIED_CURRENT" for r in rows), "new_official": sum(c["status"] == "VERIFIED_OFFICIAL" for c in found), "web_candidate": sum(c["status"] in {"HIGH_CONFIDENCE_WEB", "NEEDS_VERIFICATION"} and c["facility_type"] != "ashtray_only" for c in found), "ashtray": sum(c["status"] == "ASHTRAY_ONLY" for c in found), "stale": sum(c["status"] == "STALE" for c in found), "rejected": sum(c["status"] == "REJECTED" for c in found)})
        counts = Counter(c["status"] for c in CANDIDATES)
        new_smoking = [c for c in CANDIDATES if c["status"] in {"VERIFIED_OFFICIAL", "HIGH_CONFIDENCE_WEB", "NEEDS_VERIFICATION", "STALE", "POSSIBLY_REMOVED"} and c["dedup_result"] != "EXISTING"]
        summary = {"existing_audit": dict(Counter(r["audit_status"] for r in baseline_rows)), "new_actual_smoking_candidates_found": len(new_smoking), "officially_verified_new": counts["VERIFIED_OFFICIAL"], "high_confidence_web": counts["HIGH_CONFIDENCE_WEB"], "ashtray_only": counts["ASHTRAY_ONLY"], "needs_verification": counts["NEEDS_VERIFICATION"], "stale": counts["STALE"], "possibly_removed": counts["POSSIBLY_REMOVED"], "safe_for_automatic_db_save": counts["VERIFIED_OFFICIAL"], "facilities_investigated": len(facility_rows), "facilities_with_evidence": sum(r["evidence_found"] for r in facility_rows), "database_writes": 0}
        report = {
            "generated_at": RETRIEVED_AT, "dry_run": True, "database_writes": 0,
            "baseline": {"all_smoking_places": Place.objects.filter(category="smoking_area").count(), "busan_places": len(baseline), "source_counts": dict(Counter(p.source for p in baseline)), "source_class_counts": dict(Counter(r["source_class"] for r in baseline_rows)), "places_with_evidence": sum(bool(row["evidence"]) for row in baseline_rows), "possible_duplicate_coordinate_address_groups": len(duplicate_groups), "duplicate_groups": duplicate_groups, "rows": baseline_rows},
            "candidates": CANDIDATES, "district_sources": DISTRICT_SOURCES,
            "hub_coverage": coverage, "district_coverage": district_coverage, "facility_inventory": facility_rows,
            "summary": summary,
            "limitations": ["검색엔진 색인으로 확인 가능한 공개 웹 자료 기준이며 비색인 QR 지도·첨부파일·내부 지도는 후속 정보공개/현장 확인 대상", "주소가 아니라 좌표 부산 범위로 baseline을 산정", "공식 또는 허용된 지오코딩 근거가 없는 신규 후보 좌표는 비워 둠"],
        }
        payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        for name in ("busan_smoking_place_discovery.json", "busan_smoking_facility_discovery.json"):
            (output_dir / name).write_text(payload, encoding="utf-8")
        (output_dir / "busan_smoking_existing_audit.json").write_text(json.dumps({"generated_at": RETRIEVED_AT, "summary": summary["existing_audit"], "duplicate_groups": duplicate_groups, "rows": baseline_rows}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (output_dir / "busan_smoking_sources.json").write_text(json.dumps({"retrieved_at": RETRIEVED_AT, "district_sources": DISTRICT_SOURCES, "sources": [{k: c[k] for k in ("source_url", "source_title", "source_type", "published_at", "retrieved_at")} for c in CANDIDATES]}, ensure_ascii=False, indent=2), encoding="utf-8")
        csv_fields = ["장소", "구", "위치", "facility_type", "smoking_permission", "상태", "Source", "Evidence", "최신성", "기존 DB 존재 여부", "identity_confidence", "evidence_confidence", "published_at", "retrieved_at", "notes"]
        for filename in ("busan_smoking_place_discovery.csv", "busan_smoking_facility_discovery.csv", "busan_ashtray_candidates.csv"):
          with (output_dir / filename).open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=csv_fields)
            writer.writeheader()
            for c in CANDIDATES:
                if filename != "busan_ashtray_candidates.csv" or c["status"] == "ASHTRAY_ONLY":
                    writer.writerow({"장소": c["candidate_name"], "구": c["district"], "위치": c["location_description"], "facility_type": c["facility_type"], "smoking_permission": c["smoking_permission"], "상태": c["status"], "Source": c["source_url"], "Evidence": c["evidence_span"], "최신성": c["freshness"], "기존 DB 존재 여부": "Y" if c["dedup_result"] == "EXISTING" else "N", "identity_confidence": c["identity_confidence"], "evidence_confidence": c["evidence_confidence"], "published_at": c["published_at"], "retrieved_at": c["retrieved_at"], "notes": c["notes"]})
        audit_fields = ["id", "name", "category", "source", "source_class", "external_id", "address", "latitude", "longitude", "source_updated_at", "created_at", "audit_status", "duplicate_group"]
        with (output_dir / "busan_smoking_existing_audit.csv").open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=audit_fields); writer.writeheader()
            for row in baseline_rows:
                writer.writerow({key: json.dumps(row[key], ensure_ascii=False) if key == "duplicate_group" and row[key] else row[key] for key in audit_fields})
        self.stdout.write(self.style.SUCCESS(json.dumps(summary, ensure_ascii=False)))
