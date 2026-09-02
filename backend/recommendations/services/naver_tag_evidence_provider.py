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
        'positive': (
            '작업하기 좋', '공부하기 좋', '오래 작업', '작업하기 편',
            '공부하기 편', '카공하기 좋', '카공하기 편',
        ),
        'negative': ('작업하기 어렵', '공부하기 어렵', '장시간 이용 불가'),
    },
    '노트북작업': {
        'positive': (
            '노트북 사용', '노트북 작업', '노트북을 켜', '노트북 하는',
            '노트북 하러', '노트북을 가지고', '카공', '랩탑',
        ),
        'negative': ('노트북 금지', '노트북 사용 불가', '카공 금지'),
    },
    '콘센트있음': {
        'positive': (
            '콘센트 있', '콘센트도 있', '콘센트 많', '자리마다 콘센트',
            '콘센트가 있', '콘센트도 마련', '충전 콘센트',
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
        'positive': (
            '분위기 좋', '감성적', '감성 카페', '아늑', '무드 있',
            '감각적인 인테리어', '인테리어가 좋', '예쁜 카페', '예뻤던 카페',
            '분위기가 물씬', '분위기 물씬',
        ),
        'negative': ('분위기 별로', '어수선', '정신없'),
    },
    '혼밥좋음': {
        'positive': (
            '혼밥', '혼자 먹기 좋', '혼자 먹기 편', '혼자 식사하기 좋',
            '혼자 식사하기 편', '혼자 가기 좋', '1인석', '일인석',
            '1인 메뉴', '일인 메뉴', '바 좌석',
        ),
        'negative': ('혼밥 어렵', '혼자 가기 부담', '1인 주문 불가'),
    },
    '혼자이용좋음': {
        'positive': (
            '혼자 이용하기 좋', '혼자 가기 편', '혼자 머물기 좋', '혼자 쉬기 좋',
            '혼자 책 읽기 좋', '혼자 공부하기 좋', '혼자 시간 보내기 좋',
            '혼자 와도 부담 없', '혼자 커피 한잔', '혼자 온 손님',
            '혼자 방문', '혼자 오셔', '혼자 앉', '1인석', '일인석',
            '1인 메뉴', '일인 메뉴', '바 좌석', '혼카페',
        ),
        'negative': ('혼자 이용하기 어렵', '혼자 가기 부담', '혼자 머물기 어렵'),
    },
    '데이트좋음': {
        'positive': ('데이트하기 좋', '데이트 코스', '데이트 장소', '둘이 가기 좋'),
        'negative': ('데이트 비추천',),
    },
    '대화하기좋음': {
        'positive': (
            '대화하기 좋', '이야기하기 좋', '얘기하기 좋',
            '이야기 나누기 좋', '대화 나누기 좋', '수다 떨기 좋',
            '대화나누기도 좋', '수다떨기도 좋', '한적해서 이야기',
            '좌석 간격이 넓고 한적',
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
            '오래 작업', '시간 보내기 좋', '시간 보내기 편', '머물기 좋',
            '오래 있어도 편', '장시간 머물',
        ),
        'negative': (
            '장시간 이용 불가', '장시간 노트북 사용 제한', '장시간 노트북 사용 금지',
            '장시간 카공 제한', '장시간 카공 금지', '이용 시간 제한', '오래 있기 어렵',
        ),
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

TAG_TERMS.update({
    '단체석있음': {
        'positive': ('단체석 있', '단체 좌석 있', '단체 테이블 있', '여럿이 앉을 수'),
        'negative': ('단체석 없', '단체 이용 불가', '단체 손님 불가'),
    },
    '예약가능': {
        'positive': ('예약 가능', '전화 예약', '네이버 예약', '예약할 수'),
        'negative': ('예약 불가', '예약 안 받', '예약을 받지 않'),
    },
    '개별룸있음': {
        'positive': ('개별 룸 있', '개별룸 있', '프라이빗 룸', '룸 예약 가능'),
        'negative': ('개별 룸 없', '개별룸 없', '룸 없음'),
    },
    '넓은테이블': {
        'positive': ('테이블 넓', '큰 테이블', '대형 테이블'),
        'negative': ('테이블 좁', '테이블이 작'),
    },
    '좌석간격넓음': {
        'positive': ('좌석 간격 넓', '테이블 간격 넓', '자리 간격 넓'),
        'negative': ('좌석 간격 좁', '테이블 간격 좁', '자리 간격 좁'),
    },
    '편한좌석': {
        'positive': ('좌석 편', '의자 편', '편한 좌석', '소파 좌석'),
        'negative': ('좌석 불편', '의자 불편', '딱딱한 의자'),
    },
    '유아의자있음': {
        'positive': ('유아 의자 있', '아기 의자 있', '하이체어 있', '아기 의자 요청'),
        'negative': ('유아 의자 없', '아기 의자 없', '하이체어 없'),
    },
    '유모차접근': {
        'positive': ('유모차 접근 가능', '유모차 입장 가능', '유모차 들어갈 수'),
        'negative': ('유모차 접근 불가', '유모차 입장 불가'),
    },
    '아이메뉴있음': {
        'positive': ('아이 메뉴 있', '어린이 메뉴 있', '키즈 메뉴 있'),
        'negative': ('아이 메뉴 없', '어린이 메뉴 없', '키즈 메뉴 없'),
    },
    '엘리베이터있음': {
        'positive': ('엘리베이터 있', '승강기 있'),
        'negative': ('엘리베이터 없', '승강기 없'),
    },
    '무단차접근': {
        'positive': ('무단차', '단차 없', '문턱 없', '계단 없이'),
        'negative': ('단차 있', '문턱 있', '계단으로만'),
    },
    '테이크아웃전문': {
        'positive': ('테이크아웃 전문', '포장 전문', '테이크아웃만'),
        'negative': ('매장 식사 가능', '매장 이용 가능'),
    },
    '좌석없음': {
        'positive': ('좌석 없', '앉을 곳 없', '매장 좌석 없'),
        'negative': ('좌석 있', '매장 좌석 있'),
    },
    '시간제한있음': {
        'positive': ('이용 시간 제한', '좌석 시간제', '체류 시간 제한'),
        'negative': ('시간 제한 없', '이용 시간 제한 없'),
    },
    '예약필수': {
        'positive': ('예약 필수', '사전 예약제', '예약 없이는 이용 불가'),
        'negative': ('예약 없이 가능', '예약 불필요'),
    },
    '웨이팅많음': {
        'positive': ('웨이팅 많', '대기 길', '줄이 길', '오래 기다'),
        'negative': ('웨이팅 없', '대기 없이', '바로 입장'),
    },
    '혼잡함': {
        'positive': ('혼잡', '붐비', '북적', '사람이 많'),
        'negative': ('한산', '한적', '붐비지 않', '북적이지 않'),
    },
    '소음큼': {
        'positive': ('시끄럽', '소음 크', '음악 소리 크', '대화하기 어렵'),
        'negative': ('조용', '시끄럽지 않', '소음 적'),
    },
    '계단접근만가능': {
        'positive': ('계단만 있', '엘리베이터 없', '계단 이용만'),
        'negative': ('엘리베이터 있', '무단차', '계단 없이'),
    },
    '주차어려움': {
        'positive': ('주차 어려', '주차 불가', '주차장 없'),
        'negative': ('주차 가능', '주차장 있'),
    },
    '자연채광좋음': {
        'positive': ('자연광이 좋', '채광이 좋', '햇살이 잘 들', '햇빛이 잘 들'),
        'negative': ('채광이 아쉽', '자연광이 없', '어두운 편'),
    },
    '야외좌석': {
        'positive': ('야외 좌석 있', '테라스 좌석 있', '테라스석 있', '루프탑 좌석'),
        'negative': ('야외 좌석 없', '테라스 좌석 없'),
    },
    '반려동물동반': {
        'positive': ('반려동물 동반 가능', '애견 동반 가능', '강아지 동반 가능', '펫 동반 가능'),
        'negative': ('반려동물 동반 불가', '애견 동반 불가', '강아지 동반 불가'),
    },
    '디저트특화': {
        'positive': ('디저트 맛집', '디저트 전문', '베이커리 맛집', '케이크 맛집'),
        'negative': ('디저트가 아쉽', '디저트 종류가 적'),
    },
    '커피맛좋음': {
        'positive': (
            '커피가 맛있', '커피가 맛이', '커피 맛이 좋', '커피 맛있',
            '원두가 좋', '커피 맛집',
        ),
        'negative': ('커피가 아쉽', '커피 맛이 별로'),
    },
    '사진찍기좋음': {
        'positive': ('사진 찍기 좋', '포토존 있', '사진이 잘 나오', '인생샷'),
        'negative': ('사진 찍기 어렵', '촬영 금지'),
    },
    '대표메뉴뚜렷함': {
        'positive': ('대표 메뉴', '시그니처 메뉴', '대표메뉴', '이 집의 시그니처'),
        'negative': ('대표 메뉴가 없', '시그니처가 없'),
    },
    '메뉴선택폭넓음': {
        'positive': ('메뉴가 다양', '메뉴 종류가 많', '선택지가 많'),
        'negative': ('메뉴가 적', '선택지가 적', '메뉴가 한정'),
    },
    '여럿이먹기좋은메뉴': {
        'positive': ('나눠 먹기 좋', '여럿이 먹기 좋', '단체로 먹기 좋', '세트 메뉴'),
        'negative': ('나눠 먹기 어렵', '1인 메뉴만'),
    },
    '가성비좋음': {
        'positive': ('가성비 좋', '가격 대비 훌륭', '가격이 합리적', '푸짐한 편'),
        'negative': ('가성비 아쉽', '가격이 비싼 편', '양이 적은 편'),
    },
})


TAG_TERMS['와이파이있음'] = {
    'positive': (
        '와이파이 제공', '와이파이 있', '와이파이 가능', '와이파이 잘',
        '와이파이 빵빵', '무선인터넷', 'wifi 제공',
    ),
    'negative': ('와이파이 없', '무선인터넷 없', 'wifi 없'),
}
TAG_TERMS['무료와이파이'] = {
    'positive': ('무료 와이파이', '공공 와이파이', '무료 무선인터넷', 'free wifi'),
    'negative': ('와이파이 유료', '무선인터넷 유료', '무료 와이파이 없'),
}
TAG_TERMS['와이파이있음']['positive'] += ('와이파이도 잘', '와이파이가 잘')
TAG_TERMS['단체석있음']['positive'] += ('단체석이 있', '단체석이 마련', '여럿이 함께 앉')
TAG_TERMS['단체석있음']['negative'] += ('단체석은 없', '단체석이 없')
TAG_TERMS['개별룸있음']['positive'] += ('개별 룸이 있', '개별룸이 있', '룸이 있')
TAG_TERMS['유아의자있음']['positive'] += ('유아 의자를', '아기 의자를', '하이체어를')
TAG_TERMS['좌석없음']['positive'] += ('좌석이 없', '앉을 곳이 없')
TAG_TERMS['노트북작업']['positive'] += (
    '노트북 하기', '노트북으로 작업', '노트북 펼치', '노트북 가져',
    '노트북 해야', '노트북이나 해야',
)
TAG_TERMS['노트북작업']['negative'] += (
    '노트북 하기 어렵', '노트북 사용하기 어렵', '노트북 하기 불편',
)
TAG_TERMS['작업하기좋음']['positive'] += (
    '작업하기에 좋', '공부하기에 좋', '노트북 하기 좋', '업무 보기 좋',
)
TAG_TERMS['콘센트있음']['positive'] += (
    '콘센트 구비', '콘센트 사용', '콘센트 자리', '콘센트 완비',
)
TAG_TERMS['와이파이있음']['positive'] += (
    '와이파이 비밀번호', 'wifi 비밀번호', '와이파이 사용',
)
TAG_TERMS['시간제한있음']['positive'] += ('시간 제한', '시간이 제한')
TAG_TERMS['장기체류좋음']['positive'] += (
    '오래 머무르', '오래 있기 편', '여유롭게 머물',
)


QUALITATIVE_TAGS = frozenset({
    '조용함', '작업하기좋음', '혼자이용좋음', '혼밥좋음',
    '분위기좋음', '데이트좋음', '대화하기좋음', '장기체류좋음',
})

SUPPORTING_TERMS = {
    '작업하기좋음': (
        '작업이나 공부하러 가기도 괜찮', '공부하러 가기 괜찮',
        '작업하러 가기 괜찮', '노트북 하기 괜찮', '카공하기 괜찮',
    ),
    '혼자이용좋음': (
        '혼자 온 손님', '혼자 방문', '혼자 오셔', '혼자 앉',
        '혼자 와도', '1인석', '일인석', '바 좌석',
    ),
    '혼밥좋음': (
        '혼자 온 손님', '혼자 방문', '혼자 오셔', '혼자 먹기 편',
        '혼자 식사', '1인 메뉴', '일인 메뉴', '1인석', '바 좌석',
    ),
    '분위기좋음': ('감각적인 인테리어', '편안한 분위기', '따뜻한 분위기'),
    '데이트좋음': ('데이트 장소로 추천', '둘이 방문하기 좋', '커플이 가기 좋'),
    '대화하기좋음': ('좌석 간격이 넓', '한적해서 이야기', '이야기 나누기 편'),
    '장기체류좋음': ('오래 있어도 편', '오래 앉아 있기 편', '장시간 머물'),
    '조용함': ('조용한 편', '한적한 편', '북적이지 않', '시끄럽지 않', '집중하기 좋'),
}

WEAK_TERMS = {
    '작업하기좋음': ('테이블 넓', '좌석 넓', '콘센트',),
    '혼자이용좋음': ('혼자', '1인',),
    '혼밥좋음': ('혼자', '1인',),
    '분위기좋음': ('인테리어', '분위기', '감성',),
    '데이트좋음': ('커플', '둘이',),
    '대화하기좋음': ('좌석 간격', '한적',),
    '장기체류좋음': ('장시간', '오래',),
}

SEARCH_QUERY_VOCABULARY = {
    '조용함': {'direct': ('조용',), 'synonym': ('한적', '차분'), 'situational': ('북적이지 않음', '집중하기 좋음'), 'supporting_signal': ('시끄럽지 않음',)},
    '노트북작업': {'direct': ('노트북', '랩탑'), 'synonym': ('카공', '공부', '작업'), 'situational': ('노트북 공부',), 'supporting_signal': ('콘센트', '충전', '전원', '테이블', '좌석')},
    '작업하기좋음': {'direct': ('작업', '공부'), 'synonym': ('카공', '노트북'), 'situational': ('오래 작업', '테이블 넓은', '좌석 넓은'), 'supporting_signal': ('콘센트',)},
    '콘센트있음': {'direct': ('콘센트',), 'synonym': ('충전', '전원', '플러그'), 'situational': (), 'supporting_signal': ()},
    '무료와이파이': {'direct': ('와이파이', 'WiFi', 'Wi-Fi'), 'synonym': ('무선인터넷', '무료 인터넷'), 'situational': (), 'supporting_signal': ()},
    '혼자이용좋음': {'direct': ('혼자', '혼카페'), 'synonym': ('혼자 방문', '1인', '1인석'), 'situational': ('혼자 가기', '혼자 앉기'), 'supporting_signal': ('바 좌석',)},
    '혼밥좋음': {'direct': ('혼밥',), 'synonym': ('혼자 식사', '혼자 먹기', '1인'), 'situational': ('혼자 방문', '1인 메뉴'), 'supporting_signal': ('1인석', '바 좌석')},
    '분위기좋음': {'direct': ('분위기',), 'synonym': ('감성', '아늑', '무드'), 'situational': ('분위기 있는',), 'supporting_signal': ('인테리어',)},
    '데이트좋음': {'direct': ('데이트',), 'synonym': ('커플', '데이트 코스'), 'situational': ('데이트 장소', '둘이 가기 좋은'), 'supporting_signal': ()},
    '대화하기좋음': {'direct': ('대화', '이야기'), 'synonym': ('수다', '이야기 나누기'), 'situational': ('좌석 간격',), 'supporting_signal': ('한적',)},
    '장기체류좋음': {'direct': ('오래 앉아', '오래 머물'), 'synonym': ('장시간', '오래 있기'), 'situational': ('시간 보내기', '오래 작업'), 'supporting_signal': ()},
    '웨이팅적음': {'direct': ('웨이팅 없음', '대기 없음'), 'synonym': ('바로 입장',), 'situational': ('기다리지 않고', '웨이팅 적음'), 'supporting_signal': ()},
}

SEARCH_QUERY_VOCABULARY.update({
    '단체석있음': {'direct': ('단체석',), 'synonym': ('단체 좌석', '단체 테이블'), 'situational': ('가족 모임', '회식'), 'supporting_signal': ('8인석', '여럿이 앉기')},
    '예약가능': {'direct': ('예약 가능',), 'synonym': ('전화 예약', '네이버 예약'), 'situational': (), 'supporting_signal': ()},
    '개별룸있음': {'direct': ('개별 룸', '개별룸'), 'synonym': ('프라이빗 룸', '룸 예약'), 'situational': ('가족 모임 룸',), 'supporting_signal': ()},
    '편한좌석': {'direct': ('편한 좌석',), 'synonym': ('소파 좌석', '의자 편한'), 'situational': ('오래 앉기',), 'supporting_signal': ()},
    '유아의자있음': {'direct': ('유아 의자', '아기 의자'), 'synonym': ('하이체어',), 'situational': ('아이 동반',), 'supporting_signal': ()},
    '유모차접근': {'direct': ('유모차 접근',), 'synonym': ('유모차 입장',), 'situational': ('아이 동반',), 'supporting_signal': ('엘리베이터', '무단차')},
    '테이크아웃전문': {'direct': ('테이크아웃 전문',), 'synonym': ('포장 전문',), 'situational': (), 'supporting_signal': ('좌석 없음',)},
    '좌석없음': {'direct': ('좌석 없음',), 'synonym': ('매장 좌석 없음',), 'situational': (), 'supporting_signal': ('포장 전문',)},
    '자연채광좋음': {'direct': ('채광',), 'synonym': ('자연광', '햇살'), 'situational': ('햇빛 잘 드는',), 'supporting_signal': ('창가 좌석',)},
    '야외좌석': {'direct': ('야외 좌석',), 'synonym': ('테라스 좌석', '루프탑 좌석'), 'situational': (), 'supporting_signal': ()},
    '반려동물동반': {'direct': ('반려동물 동반',), 'synonym': ('애견 동반', '강아지 동반'), 'situational': (), 'supporting_signal': ()},
    '디저트특화': {'direct': ('디저트 맛집',), 'synonym': ('디저트 전문', '케이크 맛집'), 'situational': (), 'supporting_signal': ('베이커리',)},
    '커피맛좋음': {'direct': ('커피 맛집',), 'synonym': ('원두', '커피가 맛있는'), 'situational': (), 'supporting_signal': ()},
    '사진찍기좋음': {'direct': ('사진 찍기 좋은',), 'synonym': ('포토존', '인생샷'), 'situational': (), 'supporting_signal': ()},
    '대표메뉴뚜렷함': {'direct': ('대표 메뉴',), 'synonym': ('시그니처 메뉴',), 'situational': (), 'supporting_signal': ()},
    '메뉴선택폭넓음': {'direct': ('메뉴 다양',), 'synonym': ('메뉴 종류', '선택지'), 'situational': (), 'supporting_signal': ()},
    '여럿이먹기좋은메뉴': {'direct': ('여럿이 먹기 좋은',), 'synonym': ('나눠 먹기', '세트 메뉴'), 'situational': ('모임 식사',), 'supporting_signal': ()},
    '가성비좋음': {'direct': ('가성비',), 'synonym': ('가격 대비', '합리적인 가격'), 'situational': (), 'supporting_signal': ('푸짐한',)},
})


SEARCH_QUERY_VOCABULARY['와이파이있음'] = {
    'direct': ('와이파이', 'WiFi', 'Wi-Fi'),
    'synonym': ('무선인터넷',),
    'situational': (),
    'supporting_signal': (),
}
SEARCH_QUERY_VOCABULARY['무료와이파이'] = {
    'direct': ('무료 와이파이', '공공 와이파이'),
    'synonym': ('무료 인터넷', 'free wifi'),
    'situational': (),
    'supporting_signal': (),
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

SEARCH_KEYWORDS.update({
    tag_name: vocabulary['direct'][0]
    for tag_name, vocabulary in SEARCH_QUERY_VOCABULARY.items()
    if tag_name not in SEARCH_KEYWORDS and vocabulary.get('direct')
})
SEARCH_KEYWORDS['와이파이있음'] = '와이파이'
SEARCH_KEYWORDS['무료와이파이'] = '무료 와이파이'


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


def place_search_location_terms(place):
    """Prefer district/neighborhood terms already present in source raw data.

    SEMAS service addresses are usually road addresses without a neighborhood,
    while `raw.source_address` retains the official lot address.  Using the
    district and neighborhood narrows search results without relaxing identity.
    """
    raw = getattr(place, "raw", {})
    raw = raw if isinstance(raw, dict) else {}
    candidates = []
    for value in (
        raw.get("source_address"),
        raw.get("source_road_address"),
        getattr(place, "address", ""),
    ):
        for term in address_identity_terms(value):
            if term not in candidates:
                candidates.append(term)
    administrative = [
        term for term in candidates
        if term.endswith(("구", "군", "동", "읍", "면"))
    ]
    return administrative[:2] or search_location_terms(getattr(place, "address", ""))


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
    source = getattr(place, "source", "")
    category = getattr(place, "category", "")
    semas_food_title_required = (
        source == "semas"
        and category in {"cafe", "restaurant"}
        and not exact_in_title
    )
    short_food_title_required = (
        category in {"cafe", "restaurant"}
        and full_length <= 4
        and not exact_in_title
    )
    matched = (
        score >= 65
        and not explicit_region_mismatch
        and not semas_food_title_required
        and not short_food_title_required
    )
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
            "semas_food_title_required": semas_food_title_required,
            "short_food_title_required": short_food_title_required,
        },
    }


def evidence_polarity(tag_name, text, *, category=""):
    return polarity_assessment(tag_name, text, category=category)["polarity"]


def polarity_assessment(tag_name, text, *, category=""):
    terms = TAG_TERMS.get(tag_name) or {}
    compact_text = compact(text)
    positive_terms = [term for term in terms.get('positive', ()) if compact(term) in compact_text]
    if (
        tag_name == "대표메뉴뚜렷함"
        and any(term in compact_text for term in ("메뉴", "요리"))
        and re.search(r"(?:으로|로)유명(?:한|하|해)", compact_text)
    ):
        positive_terms.append("특정 메뉴로 유명")
    if tag_name == "대표메뉴뚜렷함" and re.search(r"[가-힣A-Za-z0-9]{2,}전문점", compact_text):
        positive_terms.append("특정 메뉴 전문점")
    negative_terms = [term for term in terms.get('negative', ()) if compact(term) in compact_text]
    supporting_terms = [
        term for term in SUPPORTING_TERMS.get(tag_name, ()) if compact(term) in compact_text
    ]
    weak_terms = [term for term in WEAK_TERMS.get(tag_name, ()) if compact(term) in compact_text]
    has_negative = bool(negative_terms)
    has_positive = bool(positive_terms or supporting_terms)
    contextual_exclusion = (
        tag_name == "웨이팅적음"
        and category in {"tourism", "city_park"}
        and any(term in compact_text for term in ("주차", "주차장", "주차기준"))
    )
    if contextual_exclusion:
        polarity = 'unknown'
        clarity = 0
        strength = 'UNKNOWN'
    elif has_negative and has_positive:
        polarity = 'unknown'
        clarity = 20
        strength = 'UNKNOWN'
    elif has_negative:
        polarity = 'negative'
        clarity = min(100, 75 + len(negative_terms) * 8)
        strength = 'CONTRADICTING'
    elif has_positive:
        polarity = 'positive'
        strength = 'DIRECT' if positive_terms else 'SUPPORTING'
        clarity = min(100, 75 + len(positive_terms) * 8) if positive_terms else min(74, 58 + len(supporting_terms) * 6)
    elif weak_terms and tag_name in QUALITATIVE_TAGS:
        polarity = 'unknown'
        clarity = 25
        strength = 'WEAK'
    else:
        polarity = 'unknown'
        clarity = 0
        strength = 'UNKNOWN'
    return {
        "polarity": polarity,
        "clarity_score": clarity,
        "positive_terms": positive_terms,
        "supporting_terms": supporting_terms,
        "weak_terms": weak_terms,
        "strength": strength,
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
