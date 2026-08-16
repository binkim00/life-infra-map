import re
from datetime import datetime

from recommendations.services.naver_search_provider import _clean_html, _request_channel, _safe_text
from recommendations.services.evidence_scoring import evidence_confidence, parse_observed_date
from recommendations.services.tag_source_policy import NAVER_BLOG_SEARCH


TAG_TERMS = {
    '조용함': {
        'positive': ('조용', '한적', '차분', '대화하기 좋', '북적이지 않'),
        'negative': ('시끄럽', '소음', '혼잡', '북적', '사람이 많'),
    },
    '작업하기좋음': {
        'positive': ('작업하기 좋', '공부하기 좋', '오래 작업'),
        'negative': ('작업하기 어렵', '공부하기 어렵', '장시간 이용 불가'),
    },
    '노트북작업': {
        'positive': ('노트북 사용', '노트북 작업', '카공', '랩탑'),
        'negative': ('노트북 금지', '노트북 사용 불가', '카공 금지'),
    },
    '콘센트있음': {
        'positive': (
            '콘센트 있', '콘센트도 있', '콘센트 많', '자리마다 콘센트',
            '전원 사용', '충전 가능',
        ),
        'negative': ('콘센트 없', '콘센트 부족', '전원 사용 불가'),
    },
    '무료와이파이': {
        'positive': (
            '무료 와이파이', '와이파이 제공', '와이파이 있', '와이파이 가능',
            '와이파이 잘', '와이파이도 잘', '와이파이 빵빵', '와이파이도 빵빵',
            '와이파이도 있', '무선인터넷', 'wifi 제공',
        ),
        'negative': ('와이파이 없', 'wifi 없'),
    },
    '분위기좋음': {
        'positive': ('분위기 좋', '감성적', '감성 카페', '아늑', '무드 있'),
        'negative': ('분위기 별로', '어수선', '정신없'),
    },
    '혼밥좋음': {
        'positive': ('혼밥', '혼자 먹기 좋', '혼자 가기 좋', '1인석', '일인석'),
        'negative': ('혼밥 어렵', '혼자 가기 부담', '1인 주문 불가'),
    },
    '혼자이용좋음': {
        'positive': (
            '혼자 이용하기 좋', '혼자 가기 편', '혼자 머물기 좋', '혼자 쉬기 좋',
            '혼자 책 읽기 좋', '혼자 공부하기 좋', '혼자 시간 보내기 좋',
            '혼자 와도 부담 없', '혼자 커피 한잔',
        ),
        'negative': ('혼자 이용하기 어렵', '혼자 가기 부담', '혼자 머물기 어렵'),
    },
    '데이트좋음': {
        'positive': ('데이트하기 좋', '데이트 코스', '커플'),
        'negative': ('데이트 비추천',),
    },
    '대화하기좋음': {
        'positive': (
            '대화하기 좋', '이야기하기 좋', '얘기하기 좋',
            '이야기 나누기 좋', '대화 나누기 좋', '수다 떨기 좋',
        ),
        'negative': ('대화하기 어렵', '말소리 안 들'),
    },
    '전망좋음': {
        'positive': ('전망 좋', '뷰가 좋', '오션뷰', '시티뷰', '야경이 좋'),
        'negative': ('전망 없', '뷰가 막'),
    },
    '웨이팅적음': {
        'positive': ('웨이팅 없', '대기 없이', '바로 입장'),
        'negative': ('웨이팅 길', '대기 길', '오래 기다'),
    },
    '장기체류좋음': {
        'positive': (
            '오래 머물', '오래 있기 좋', '오래 앉아', '장시간 이용',
            '시간 보내기 좋', '시간 보내기 편', '머물기 좋',
        ),
        'negative': ('장시간 이용 불가', '이용 시간 제한', '오래 있기 어렵'),
    },
    '가족동반좋음': {
        'positive': ('가족 동반', '아이와 가기 좋', '아이랑 가기 좋', '가족 나들이'),
        'negative': ('아이 동반 불가', '가족 방문 비추천'),
    },
    '산책좋음': {
        'positive': ('산책하기 좋', '걷기 좋', '산책로'),
        'negative': ('산책하기 어렵', '보행 불편'),
    },
    '야외활동좋음': {
        'positive': ('야외활동', '피크닉', '나들이하기 좋'),
        'negative': ('야외활동 불가', '피크닉 금지'),
    },
    '휠체어접근': {
        'positive': ('휠체어 접근', '무장애', '배리어프리', '경사로 있'),
        'negative': ('휠체어 접근 불가', '계단만 있', '경사로 없'),
    },
    '장애인시설': {
        'positive': ('장애인 화장실', '장애인 편의시설', '장애인시설 있'),
        'negative': ('장애인시설 없', '장애인 화장실 없'),
    },
    '장애인전용주차': {
        'positive': ('장애인 주차', '장애인전용주차'),
        'negative': ('장애인 주차 없',),
    },
    '24시간운영': {
        'positive': ('24시간 운영', '24시간 개방', '상시 개방'),
        'negative': ('24시간 아님', '야간 폐쇄'),
    },
    '무료이용': {
        'positive': ('무료 이용', '무료 개방', '주차 무료'),
        'negative': ('유료 이용', '주차 유료'),
    },
    '관리잘됨': {
        'positive': ('관리 잘', '깨끗', '청결'),
        'negative': ('관리 안', '더럽', '불결'),
    },
}

SEARCH_KEYWORDS = {
    '조용함': '조용',
    '작업하기좋음': '작업',
    '노트북작업': '노트북',
    '콘센트있음': '콘센트',
    '무료와이파이': '와이파이',
    '분위기좋음': '분위기',
    '혼밥좋음': '혼밥',
    '혼자이용좋음': '혼자 이용',
    '데이트좋음': '데이트',
    '대화하기좋음': '대화',
    '전망좋음': '전망',
    '웨이팅적음': '웨이팅',
    '장기체류좋음': '오래 머물기',
    '가족동반좋음': '아이와',
    '산책좋음': '산책',
    '야외활동좋음': '피크닉',
    '휠체어접근': '휠체어',
    '장애인시설': '장애인시설',
    '장애인전용주차': '장애인주차',
    '24시간운영': '24시간',
    '무료이용': '무료',
    '관리잘됨': '청결',
}


def compact(value):
    return re.sub(r'[^0-9a-z가-힣]', '', str(value or '').lower())


def address_identity_terms(address):
    terms = []
    for token in re.findall(r'[가-힣0-9]{2,}', str(address or '')):
        if token.endswith(('시', '군', '구', '동', '읍', '면', '로', '길')):
            terms.append(token)
    return list(dict.fromkeys(terms))[-4:]


def search_location_terms(address):
    terms = address_identity_terms(address)
    administrative = [
        term for term in terms
        if term.endswith(('시', '군', '구', '동', '읍', '면'))
    ]
    selected = administrative[:2] or terms[:2]
    return selected


REGION_PREFIXES = {
    "서울": ("서울특별시", "서울 "),
    "부산": ("부산광역시", "부산 "),
    "대구": ("대구광역시", "대구 "),
    "인천": ("인천광역시", "인천 "),
    "광주": ("광주광역시", "광주 "),
    "대전": ("대전광역시", "대전 "),
    "울산": ("울산광역시", "울산 "),
    "세종": ("세종특별자치시", "세종 "),
    "경기": ("경기도",), "강원": ("강원",), "충북": ("충청북도",),
    "충남": ("충청남도",), "전북": ("전북", "전라북도"),
    "전남": ("전라남도",), "경북": ("경상북도",), "경남": ("경상남도",),
    "제주": ("제주",),
}
GENERIC_IDENTITY_TERMS = {
    "공원", "근린공원", "어린이공원", "소공원", "화장실", "공중화장실",
    "주차장", "공영주차장", "도서관", "관광지", "전망대", "경로당",
    "행정복지센터", "주민센터", "쉼터", "무더위쉼터",
}


def identity_matches(place, text, *, title=""):
    return identity_assessment(place, text, title=title)["matched"]


def identity_assessment(place, text, *, title=""):
    compact_text = compact(text)
    name_terms = [compact(term) for term in re.findall(r'[0-9a-zA-Z가-힣]+', str(place.name or ''))]
    name_terms = [term for term in name_terms if len(term) >= 2]
    full_name = compact(place.name)
    exact_name = bool(full_name and full_name in compact_text)
    matched_name_terms = [term for term in name_terms if term in compact_text]
    if not name_terms or not matched_name_terms:
        return {"matched": False, "score": 0, "signals": {"name": "none", "address_ratio": 0}}
    all_name_terms = len(matched_name_terms) == len(name_terms)
    name_score = 50 if exact_name else 40 if all_name_terms else 20
    strong_branch_identity = any(
        term.endswith('점') or any(character.isdigit() for character in term) or term.endswith('dt') or 'dt점' in term
        for term in name_terms[1:]
    )
    address_terms = address_identity_terms(place.address)
    matched_address_terms = [term for term in address_terms if compact(term) in compact_text]
    address_ratio = len(matched_address_terms) / len(address_terms) if address_terms else 0
    address_score = max(15, round(address_ratio * 35)) if matched_address_terms else 0
    branch_score = 25 if len(name_terms) >= 2 and strong_branch_identity and all_name_terms else 0
    expected_region = next(
        (region for region, prefixes in REGION_PREFIXES.items() if str(place.address or "").startswith(prefixes)),
        "",
    )
    mentioned_regions = [region for region in REGION_PREFIXES if region in compact_text]
    explicit_region_mismatch = bool(
        expected_region and mentioned_regions and expected_region not in mentioned_regions
    )
    full_length = len(full_name)
    exact_in_title = bool(full_name and full_name in compact(title))
    generic_suffix_only = full_name in {
        compact(value) for value in (
            "공립수목원", "근린공원", "어린이공원", "소공원", "공영주차장",
            "공중화장실", "화장실", "주차장", "경로당", "행정복지센터", "주민센터",
        )
    }
    distinctive_title = exact_in_title and full_length >= 5 and not generic_suffix_only
    distinctive_terms = [term for term in name_terms if term not in {compact(value) for value in GENERIC_IDENTITY_TERMS}]
    multi_term_region = (
        all_name_terms
        and len(distinctive_terms) >= 2
        and expected_region in mentioned_regions
    )
    tour_region_match = (
        getattr(place, "source", "") == "tour_api"
        and exact_name
        and expected_region in mentioned_regions
        and (full_length >= 5 or full_name.endswith("터"))
    )
    contextual_score = 15 if distinctive_title or multi_term_region or tour_region_match else 0
    score = min(100, name_score + address_score + branch_score + contextual_score)
    matched = score >= 65 and not explicit_region_mismatch
    return {
        "matched": matched,
        "score": score,
        "signals": {
            "name": "exact" if exact_name else "all_terms" if all_name_terms else "partial",
            "matched_name_terms": matched_name_terms,
            "address_ratio": round(address_ratio, 3),
            "matched_address_terms": matched_address_terms,
            "strong_branch": bool(branch_score),
            "exact_in_title": exact_in_title,
            "expected_region": expected_region,
            "mentioned_regions": mentioned_regions,
            "explicit_region_mismatch": explicit_region_mismatch,
            "contextual_score": contextual_score,
            "distinctive_name_terms": distinctive_terms,
        },
    }


def evidence_polarity(tag_name, text, *, category=""):
    return polarity_assessment(tag_name, text, category=category)["polarity"]


def polarity_assessment(tag_name, text, *, category=""):
    terms = TAG_TERMS.get(tag_name) or {}
    compact_text = compact(text)
    positive_terms = [term for term in terms.get('positive', ()) if compact(term) in compact_text]
    negative_terms = [term for term in terms.get('negative', ()) if compact(term) in compact_text]
    has_negative = bool(negative_terms)
    has_positive = bool(positive_terms)
    contextual_exclusion = (
        tag_name == "웨이팅적음"
        and category in {"tourism", "city_park"}
        and any(term in compact_text for term in ("주차", "주차장", "주차기준"))
    )
    if contextual_exclusion:
        polarity = 'unknown'
        clarity = 0
    elif has_negative and has_positive:
        polarity = 'unknown'
        clarity = 20
    elif has_negative:
        polarity = 'negative'
        clarity = min(100, 75 + len(negative_terms) * 8)
    elif has_positive:
        polarity = 'positive'
        clarity = min(100, 75 + len(positive_terms) * 8)
    else:
        polarity = 'unknown'
        clarity = 0
    return {
        "polarity": polarity,
        "clarity_score": clarity,
        "positive_terms": positive_terms,
        "negative_terms": negative_terms,
        "contextual_exclusion": contextual_exclusion,
    }


def collect_naver_tag_evidence(place, tag_name):
    terms = TAG_TERMS.get(tag_name)
    if not terms:
        return {'executed': True, 'polarity': 'unknown', 'error': 'unsupported_tag'}
    keyword = SEARCH_KEYWORDS.get(tag_name) or terms['positive'][0]
    location = ' '.join(search_location_terms(place.address))
    query = '{} {} {}'.format(place.name, location, keyword).strip()
    try:
        payload = _request_channel('blog', query)
    except Exception:
        return {'executed': True, 'error': 'request_failed'}
    evidences = []
    seen_urls = set()
    for item in (payload or {}).get('items') or []:
        title = _clean_html(item.get('title'), 180)
        summary = _clean_html(item.get('description'), 500)
        combined = '{} {}'.format(title, summary)
        identity = identity_assessment(place, combined, title=title)
        if not identity['matched']:
            continue
        extraction = polarity_assessment(tag_name, combined, category=place.category)
        polarity = extraction['polarity']
        url = _safe_text(item.get('link'), 500)
        if (
            polarity == 'unknown'
            or not url.startswith(('http://', 'https://'))
            or url in seen_urls
        ):
            continue
        seen_urls.add(url)
        postdate = str(item.get('postdate') or '')
        observed_at = None
        if re.fullmatch(r'\d{8}', postdate):
            observed_at = datetime.strptime(postdate, '%Y%m%d').date().isoformat()
        parsed_observed_at = parse_observed_date(postdate)
        confidence, confidence_factors = evidence_confidence(
            source=NAVER_BLOG_SEARCH,
            identity_score=identity['score'],
            clarity_score=extraction['clarity_score'],
            observed_at=parsed_observed_at,
        )
        evidences.append({
            'polarity': polarity,
            'evidence_summary': summary or title,
            'source_url': url,
            'source_title': title,
            'observed_date': observed_at,
            'confidence': confidence,
            'identity': identity,
            'extraction': extraction,
            'confidence_factors': confidence_factors,
            'raw': {'channel': 'naver_blog', 'query': query},
        })
    if not evidences:
        return {'executed': True, 'polarity': 'unknown', 'error': 'insufficient_evidence'}
    return {'executed': True, 'evidences': evidences[:5]}
