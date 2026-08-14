import re
from datetime import datetime

from recommendations.services.naver_search_provider import _clean_html, _request_channel, _safe_text


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
        'positive': ('콘센트 있', '콘센트 많', '전원 사용', '충전 가능'),
        'negative': ('콘센트 없', '콘센트 부족', '전원 사용 불가'),
    },
    '무료와이파이': {
        'positive': ('무료 와이파이', '와이파이 제공', 'wifi 제공'),
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
    '데이트좋음': {
        'positive': ('데이트하기 좋', '데이트 코스', '커플'),
        'negative': ('데이트 비추천',),
    },
    '대화하기좋음': {
        'positive': ('대화하기 좋', '이야기하기 좋', '얘기하기 좋'),
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
}

SEARCH_KEYWORDS = {
    '조용함': '조용',
    '작업하기좋음': '작업',
    '노트북작업': '노트북',
    '콘센트있음': '콘센트',
    '무료와이파이': '와이파이',
    '분위기좋음': '분위기',
    '혼밥좋음': '혼밥',
    '데이트좋음': '데이트',
    '대화하기좋음': '대화',
    '전망좋음': '전망',
    '웨이팅적음': '웨이팅',
}


def compact(value):
    return re.sub(r'[^0-9a-z가-힣]', '', str(value or '').lower())


def address_identity_terms(address):
    terms = []
    for token in re.findall(r'[가-힣0-9]{2,}', str(address or '')):
        if token.endswith(('시', '군', '구', '동', '읍', '면', '로', '길')):
            terms.append(token)
    return list(dict.fromkeys(terms))[-4:]


def identity_matches(place, text):
    compact_text = compact(text)
    name_terms = [compact(term) for term in re.findall(r'[0-9a-zA-Z가-힣]+', str(place.name or ''))]
    name_terms = [term for term in name_terms if len(term) >= 2]
    if not name_terms or not all(term in compact_text for term in name_terms):
        return False
    strong_branch_identity = any(
        term.endswith('점') or any(character.isdigit() for character in term) or term.endswith('dt') or 'dt점' in term
        for term in name_terms[1:]
    )
    if len(name_terms) >= 2 and strong_branch_identity:
        return True
    address_terms = address_identity_terms(place.address)
    return not address_terms or any(compact(term) in compact_text for term in address_terms)


def evidence_polarity(tag_name, text):
    terms = TAG_TERMS.get(tag_name) or {}
    compact_text = compact(text)
    has_negative = any(compact(term) in compact_text for term in terms.get('negative', ()))
    has_positive = any(compact(term) in compact_text for term in terms.get('positive', ()))
    if has_negative and has_positive:
        return 'unknown'
    if has_negative:
        return 'negative'
    if has_positive:
        return 'positive'
    return 'unknown'


def collect_naver_tag_evidence(place, tag_name):
    terms = TAG_TERMS.get(tag_name)
    if not terms:
        return {'executed': True, 'polarity': 'unknown', 'error': 'unsupported_tag'}
    keyword = SEARCH_KEYWORDS.get(tag_name) or terms['positive'][0]
    location = ' '.join(address_identity_terms(place.address)[-2:])
    query = '{} {} {}'.format(place.name, location, keyword).strip()
    try:
        payload = _request_channel('blog', query)
    except Exception:
        return {'executed': True, 'error': 'request_failed'}
    evidences = []
    for item in (payload or {}).get('items') or []:
        title = _clean_html(item.get('title'), 180)
        summary = _clean_html(item.get('description'), 500)
        combined = '{} {}'.format(title, summary)
        if not identity_matches(place, combined):
            continue
        polarity = evidence_polarity(tag_name, combined)
        url = _safe_text(item.get('link'), 500)
        if polarity == 'unknown' or not url.startswith(('http://', 'https://')):
            continue
        postdate = str(item.get('postdate') or '')
        observed_at = None
        if re.fullmatch(r'\d{8}', postdate):
            observed_at = datetime.strptime(postdate, '%Y%m%d').date().isoformat()
        evidences.append({
            'polarity': polarity,
            'evidence_summary': summary or title,
            'source_url': url,
            'source_title': title,
            'observed_date': observed_at,
            'raw': {'channel': 'naver_blog', 'query': query},
        })
    if not evidences:
        return {'executed': True, 'polarity': 'unknown', 'error': 'insufficient_evidence'}
    return {'executed': True, 'evidences': evidences[:5]}
