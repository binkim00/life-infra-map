'''Compose broad Korean situation requests from reusable semantic dimensions.'''

import re
import unicodedata

from recommendations.services.canonical_tag_policy import canonical_tags_in_text


DIMENSION_RULES = {
    'companions': {
        'parents': ('부모님', '부모', '어머니', '아버지', '엄마', '아빠', '어르신'),
        'children': ('어린아이', '아이', '아기', '유아', '어린이', '자녀', '애기'),
        'family': ('가족', '가족들', '식구'),
        'friends': ('친구', '친구들', '동창', '친구끼리'),
        'colleagues': ('직장 동료', '회사 사람', '팀원', '회식'),
        'partner': ('연인', '애인', '남자친구', '여자친구', '데이트'),
        'pet': ('반려동물', '강아지', '고양이', '반려견'),
        'solo': ('혼자', '혼밥', '1인'),
    },
    'occasions': {
        'reunion': ('오랜만', '간만에', '재회', '다시 만나'),
        'gathering': ('모임', '회식', '단체', '여럿', '다 같이', '함께 모'),
        'celebration': ('생일', '기념일', '축하', '돌잔치', '환갑', '상견례'),
        'business': ('접대', '미팅', '회의', '비즈니스'),
    },
    'activities': {
        'meal': ('식사', '밥', '먹', '식당', '음식점', '맛집'),
        'conversation': ('대화', '이야기', '얘기', '수다', '담소', '이야기할'),
        'work': ('작업', '공부', '노트북', '업무', '과제'),
        'rest': ('쉬', '휴식', '머물', '시간 보내'),
        'walk': ('산책', '걷', '나들이'),
    },
}


PREFERENCE_PROFILES = {
    ('companions', 'parents'): {
        'prefer': ('편한좌석', '대화하기좋음', '주차가능', '무단차접근'),
        'avoid': ('계단접근만가능', '소음큼'),
    },
    ('companions', 'children'): {
        'prefer': ('유아의자있음', '유모차접근', '아이메뉴있음', '편한좌석'),
        'avoid': ('계단접근만가능', '좌석없음'),
    },
    ('companions', 'family'): {
        'prefer': ('단체석있음', '예약가능', '넓은테이블', '편한좌석'),
        'avoid': ('테이크아웃전문', '좌석없음'),
    },
    ('companions', 'friends'): {
        'prefer': ('대화하기좋음', '장기체류좋음', '단체석있음'),
        'avoid': ('테이크아웃전문', '좌석없음', '시간제한있음'),
    },
    ('companions', 'colleagues'): {
        'prefer': ('단체석있음', '예약가능', '개별룸있음', '주차가능'),
        'avoid': ('좌석없음',),
    },
    ('occasions', 'reunion'): {
        'prefer': ('대화하기좋음', '장기체류좋음', '편한좌석'),
        'avoid': ('시간제한있음', '소음큼'),
    },
    ('occasions', 'gathering'): {
        'prefer': ('단체석있음', '예약가능', '넓은테이블', '대화하기좋음'),
        'avoid': ('테이크아웃전문', '좌석없음'),
    },
    ('occasions', 'celebration'): {
        'prefer': ('예약가능', '개별룸있음', '분위기좋음', '주차가능'),
        'avoid': ('테이크아웃전문',),
    },
    ('activities', 'conversation'): {
        'prefer': ('대화하기좋음', '편한좌석', '장기체류좋음'),
        'avoid': ('소음큼', '시간제한있음'),
    },
}


DERIVED_ONLY_FEATURES = {'가족동반좋음', '데이트좋음'}


def _compact(value):
    text = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return re.sub(r'[^0-9a-z가-힣]+', '', text)


def _normalized_text(value):
    text = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return re.sub(r'[^0-9a-z가-힣]+', ' ', text).strip()


def _dedupe(values):
    return list(dict.fromkeys(value for value in values if value))


def _explicit_time_features(text):
    features = []
    if any(term in text for term in ('주말', '토요일', '일요일', '공휴일', '휴일')):
        features.append('주말휴일운영')
    if any(term in text for term in ('24시간', '이십사시간')):
        features.append('24시간운영')
    elif any(term in text for term in ('늦은밤', '밤늦게', '심야', '새벽')):
        features.append('야간운영')
    return features


def build_semantic_intent_profile(query, frame=None):
    '''Separate explicit requirements from contextual soft preferences.'''
    frame = frame if isinstance(frame, dict) else {}
    normalized_text = _normalized_text(query)
    dimensions = {name: [] for name in DIMENSION_RULES}
    for dimension, values in DIMENSION_RULES.items():
        for key, terms in values.items():
            if any(_normalized_text(term) in normalized_text for term in terms):
                dimensions[dimension].append(key)

    required = [
        feature for feature in canonical_tags_in_text(query)
        if feature not in DERIVED_ONLY_FEATURES
    ]
    required.extend(_explicit_time_features(normalized_text))
    required.extend(frame.get('required_features') or [])

    preferred = list(frame.get('preferred_features') or [])
    avoid = list(frame.get('avoid_features') or [])
    for dimension, keys in dimensions.items():
        for key in keys:
            profile = PREFERENCE_PROFILES.get((dimension, key), {})
            preferred.extend(profile.get('prefer') or [])
            avoid.extend(profile.get('avoid') or [])

    required = _dedupe(required)
    preferred = [feature for feature in _dedupe(preferred) if feature not in required]
    avoid = [feature for feature in _dedupe(avoid) if feature not in required]
    return {
        'intent_dimensions': {
            dimension: _dedupe(values) for dimension, values in dimensions.items()
        },
        'required_features': required,
        'preferred_features': preferred,
        'avoid_features': avoid,
    }
