export const DEFAULT_CENTER = {
  lat: 36.35,
  lng: 127.8,
}

// 지도 검색 반경: 5km
export const SEARCH_RADIUS = 5000
export const MIN_VIEWPORT_SEARCH_RADIUS = 500
export const MAX_VIEWPORT_SEARCH_RADIUS = 20000

// 카카오 장소 검색은 한 번에 최대 15개까지 가져오는 구조라서
// 15개씩 페이지를 추가 조회한 뒤 최대 50개까지만 사용합니다.
export const SEARCH_SIZE_PER_PAGE = 15
export const MAX_SEARCH_RESULT_COUNT = 50
export const DB_SEARCH_RESULT_COUNT = 50
export const DISPLAY_BATCH_SIZE = 15
export const KAKAO_FALLBACK_MIN_RESULTS = 3
export const WALK_HEALING_FALLBACK_RADII = [3000, 5000]
export const KAKAO_FALLBACK_MAX_SCORE = 60
export const AI_WEB_SEARCH_MIN_DB_RESULTS = 3
export const AI_WEB_SEARCH_MIN_TOTAL_RESULTS = 5
export const AI_WEB_SEARCH_SUFFICIENT_TOTAL_RESULTS = 10
export const AI_WEB_SEARCH_INFRA_BLOCK_CATEGORIES = new Set([
  'toilet',
  'parking',
  'smoking_area',
  'freewifi',
])
export const AI_WEB_SEARCH_EXPLICIT_KEYWORDS = [
  '웹에서',
  '웹 검색',
  '웹검색',
  '블로그',
  '후기',
  '리뷰',
  '최신',
  '최근',
  '요즘',
  '핫플',
]
export const AI_WEB_SEARCH_HELPFUL_KEYWORDS = [
  '맛집',
  '메뉴',
  '먹고',
  '식당',
  '음식점',
  '카페',
  '커피',
  '브런치',
  '디저트',
  '베이커리',
  '빵집',
  '소금빵',
  '쌀국수',
  '관광',
  '가볼만한',
  '야경',
  '산책',
  '데이트',
  '분위기',
]
export const AI_WEB_SEARCH_HELPFUL_CATEGORIES = new Set([
  'restaurant',
  'cafe',
  'tourism',
  'beach',
  'city_park',
])
export const AI_WEB_SEARCH_DETAIL_KEYWORDS = [
  '메뉴',
  '브런치',
  '디저트',
  '혼밥',
  '혼자',
  '조용',
  '분위기',
  '노트북',
  '콘센트',
  '와이파이',
  '주차',
  '목적',
  '데이트',
  '추천',
  '좋은',
]
export const CAFE_SEARCH_KEYWORDS = ['카페', '커피', 'cafe']
export const INFRA_SEARCH_KEYWORDS = [
  '화장실',
  '공중화장실',
  '와이파이',
  '무료와이파이',
  '무료 와이파이',
  'wifi',
  'wi-fi',
  '흡연',
  '흡연구역',
  '해수욕장',
  '주차장',
  '공원',
  '관광지',
]
export const DB_MARKER_ALLOWED_CATEGORIES = [
  'toilet',
  'freewifi',
  'smoking_area',
  'beach',
  'parking',
  'city_park',
  'tourism',
]
export const AI_SCENARIO_KAKAO_KEYWORDS = {
  work_cafe: '카페',
  waiting_place: '카페',
  walk_healing: '공원',
  smoking_area: '흡연구역',
  restaurant: '식당',
}
export const SCENARIO_DISPLAY_LABELS = {
  work_cafe: '조용히 작업할 곳',
  waiting_place: '잠깐 쉴 곳',
  walk_healing: '산책/힐링',
  smoking_area: '흡연 가능한 곳',
  restaurant: '식당/맛집',
  blocked: '검색 불가',
}
export const INTENT_GROUP_DISPLAY_LABELS = {
  urgent_toilet: '화장실',
  quiet_rest_place: '조용히 쉴 곳',
  work_place: '작업할 곳',
  health_nearby: '약국/병원',
  food_place: '식당/맛집',
  walk_healing: '산책/힐링',
  smoking_area: '흡연 가능한 곳',
}
export const CATEGORY_KAKAO_KEYWORDS = {
  cafe: '카페',
  shelter: '쉼터',
  city_park: '공원',
  beach: '해수욕장',
  tourism: '관광지',
  smoking_area: '흡연구역',
  restaurant: '식당',
}
export const CATEGORY_KEYWORD_MAP = [
  { category: 'toilet', keyword: '화장실', aliases: ['화장실', '공중화장실'] },
  { category: 'parking', keyword: '주차장', aliases: ['주차장', '주차'] },
  { category: 'smoking_area', keyword: '흡연구역', aliases: ['흡연구역', '흡연장', '흡연장소', '흡연실', '흡연부스', '흡연', '담배 피울 곳', '담배필곳', '재떨이'] },
  { category: 'freewifi', keyword: '와이파이', aliases: ['와이파이', '무료와이파이', 'wifi', 'wi-fi'] },
  { category: 'city_park', keyword: '공원', aliases: ['공원'] },
  { category: 'shelter', keyword: '쉼터', aliases: ['쉼터', '쉴 곳', '쉴곳', '휴식'] },
  { category: 'beach', keyword: '해수욕장', aliases: ['해수욕장', '바다'] },
  { category: 'tourism', keyword: '관광지', aliases: ['관광지', '가볼만한 곳', '가볼만한곳'] },
  { category: 'restaurant', keyword: '식당', aliases: ['식당', '맛집', '음식점'] },
  { category: 'cafe', keyword: '카페', aliases: ['카페', '커피', 'cafe'] },
]
export const WORK_CAFE_KEYWORDS = [
  '작업',
  '노트북',
  '공부',
  '조용',
  '콘센트',
  '와이파이',
  'wifi',
  '오래',
  '혼자',
]
export const WORK_CAFE_PREFERRED_TAGS = [
  '노트북작업',
  '콘센트있음',
  '와이파이',
  '조용한',
  '혼자이용좋음',
]
export const WAITING_PLACE_KEYWORDS = [
  '비',
  '눈',
  '실내',
  '잠깐쉴',
  '잠깐쉬',
  '쉴곳',
  '쉴 곳',
  '쉬기',
  '피할곳',
  '피할 곳',
]
export const RESTAURANT_INTENT_KEYWORDS = [
  '혼밥',
  '혼자밥',
  '혼자 밥',
  '혼자식사',
  '혼자 식사',
  '식당',
  '밥집',
  '음식점',
  '레스토랑',
  '맛집',
  '브런치',
  '디저트',
  '빵',
  '소금빵',
  '빵집',
  '베이커리',
  '파스타',
  '쌀국수',
  '돈까스',
  '돈가스',
  '먹고',
  '먹을',
  '식사',
]
export const WALK_HEALING_KEYWORDS = [
  '산책',
  '힐링',
  '야경',
  '걷기',
]
export const SMOKING_INTENT_KEYWORDS = [
  '흡연가능',
  '흡연 가능',
  '담배',
]
export const INTENT_PREFERRED_TAGS = {
  work_cafe: WORK_CAFE_PREFERRED_TAGS,
  waiting_place: ['실내쉼터', '잠깐쉬기좋음'],
  walk_healing: ['산책좋음', '힐링', '야경'],
  smoking_area: ['흡연가능', '흡연구역'],
  restaurant: ['혼자이용좋음', '혼밥좋음', '조용한', '식사좋음'],
}
export const INTENT_NEGATIVE_TAGS = {
  waiting_place: ['실외', '야외'],
}
export const INTENT_KAKAO_KEYWORD_CANDIDATES = {
  work_cafe: ['카페', '작업 카페', '공부 카페', '스터디카페'],
  waiting_place: ['카페', '쉼터', '실내 쉼터'],
  walk_healing: ['공원', '산책로', '강변', '하천', '둘레길', '해변', '해수욕장', '관광지', '전망대'],
  smoking_area: ['흡연구역', '흡연실'],
  restaurant: ['혼밥', '식당', '밥집', '음식점'],
}
export const WALK_HEALING_FALLBACK_QUERIES = [
  '공원',
  '산책로',
  '강변',
  '하천',
  '둘레길',
  '해변',
  '해수욕장',
  '관광지',
  '전망대',
]
export const WALK_HEALING_LOCATION_QUERY_KEYWORDS = [
  '공원',
  '산책로',
  '강변',
  '하천',
  '걷기 좋은 곳',
]
export const WALK_HEALING_ALLOWED_KEYWORDS = [
  '공원',
  '산책',
  '산책로',
  '강변',
  '하천',
  '수변',
  '둘레길',
  '해변',
  '해수욕장',
  '관광',
  '관광지',
  '전망',
  '전망대',
  '명소',
  '광장',
  '생태',
  '숲',
  '호수',
  '갈맷길',
]
export const WALK_HEALING_EXCLUDE_KEYWORDS = [
  '음식점',
  '식당',
  '맛집',
  '술집',
  '주점',
  '포차',
  '호프',
  '편의점',
  '카페',
  '커피',
  '병원',
  '약국',
  '부동산',
  '숙박',
  '모텔',
  '호텔',
  '노래방',
  'pc방',
  '피시방',
  '상가',
  '상점',
  '매장',
]
export const WALK_HEALING_CAFE_KEYWORDS = ['카페', '커피', '디저트', '베이커리', '빵집']
export const KAKAO_FALLBACK_KEYWORD_RULES = [
  {
    keywords: ['혼밥', '혼자밥', '혼자 밥', '혼자식사', '혼자 식사', '식당', '밥집', '음식점', '맛집', '브런치', '디저트', '빵', '소금빵', '빵집', '베이커리', '파스타', '쌀국수', '돈까스', '돈가스', '먹고', '식사'],
    queries: ['혼밥', '식당', '밥집', '음식점'],
  },
  {
    keywords: ['카페', '커피', '노트북', '작업', '공부', '조용'],
    queries: ['조용한 카페', '노트북 카페', '카페'],
  },
  {
    keywords: ['잠깐쉴', '잠깐 쉴', '쉴곳', '쉴 곳', '쉬기', '휴식', '쉼터'],
    queries: ['쉼터', '휴게공간', '도서관', '공원'],
  },
  {
    keywords: ['산책', '힐링', '걷기', '야경'],
    queries: ['공원', '산책로', '해변', '관광지'],
  },
]
export const FOOD_MENU_KNOWN_KEYWORDS = ['소금빵', '디저트', '브런치', '커피', '파스타', '쌀국수', '돈까스', '돈가스', '밥', '식사', '빵']
export const FOOD_MENU_PATTERN_SUFFIXES = [
  '맛집',
  '먹고 싶',
  '먹고싶',
  '파는 곳',
  '파는곳',
  '먹을 수 있는 곳',
  '먹을수있는곳',
  '카페',
  '빵집',
  '디저트',
]
export const FOOD_BAKERY_KEYWORDS = ['빵', '소금빵', '디저트', '베이커리', '빵집']
export const FOOD_CAFE_KEYWORDS = ['카페', '커피', '디저트', '브런치', '소금빵', '빵']
export const ABSTRACT_TARGET_KEYWORDS = [
  '곳',
  '장소',
  '데',
  '갈만한곳',
  '갈만한 곳',
  '쉴곳',
  '쉴 곳',
  '머물곳',
  '머물 곳',
  '작업할곳',
  '작업할 곳',
  '볼만한곳',
  '볼만한 곳',
]
export const TYPO_CORRECTION_MAP = [
  ['작엄', '작업'],
  ['카패', '카페'],
  ['와파이', '와이파이'],
  ['콘샌트', '콘센트'],
  ['놋북', '노트북'],
  ['흡구', '흡연구역'],
  ['공화', '공중화장실'],
  ['공와', '공공와이파이'],
  ['작업할만한', '작업할 만한'],
  ['가볼만한', '가볼 만한'],
]
export const TAKEOUT_HEAVY_KEYWORDS = [
  '컴포즈',
  '메가커피',
  '메가MGC',
  '빽다방',
  '더벤티',
  '테이크아웃',
  'takeout',
]
export const WAITING_PLACE_EXCLUDE_KEYWORDS = [
  '경로당',
  '노인정',
  '노인회관',
  '마을회관',
  '사랑방',
  '사랑터',
  '할머니',
  '할아버지',
  '복지관',
  '노인복지',
  '요양원',
  '어린이집',
  '유치원',
  '학교',
]
export const WAITING_PLACE_PENALTY_KEYWORDS = [
  '복지센터',
  '행정복지센터',
  '주민센터',
  '동사무소',
  '구청',
  '시청',
  '민원센터',
  '파출소',
  '경찰서',
  '소방서',
  '병원',
  '교회',
  '성당',
  '사찰',
]
export const WAITING_PLACE_PREFERRED_KEYWORDS = [
  '카페',
  '쉼터',
  '실내쉼터',
  '도서관',
  '대합실',
  '터미널',
  '역사',
  '쇼핑몰',
  '복합상가',
  '휴게공간',
  '관광안내소',
]
export const ANCILLARY_PLACE_KEYWORDS = [
  '주차장',
  '공영주차장',
  '공중화장실',
  '화장실',
  '관리사무소',
  '매표소',
  '안내소',
  '입구',
  '출입구',
  '정문',
  '후문',
  '승강장',
  '정류장',
]
export const DESTINATION_CATEGORY_KEYWORDS = [
  '공원',
  '관광명소',
  '문화시설',
  '해수욕장',
  '전망대',
  '산책로',
  '관광지',
]
export const ANCILLARY_INTENT_CATEGORIES = [
  'parking',
  'toilet',
  'freewifi',
]
export const REQUEST_CONDITION_RULES = [
  {
    id: 'smoking',
    matchLabel: '흡연 가능',
    missingLabel: '흡연 가능 여부',
    keywords: ['흡연가능', '흡연 가능', '담배'],
    cleanupPatterns: [/흡연\s*가능(?:한|함)?/g, /담배\s*(?:피울|필)\s*수\s*있는/g],
    evidenceKeywords: ['흡연가능', '흡연 가능', '흡연구역', '흡연실', '실내흡연실', '실외흡연구역', '개방형흡연구역', '부스형흡연구역'],
  },
  {
    id: 'outlet',
    matchLabel: '콘센트 있음',
    missingLabel: '콘센트 여부',
    keywords: ['콘센트', '전원', '충전'],
    cleanupPatterns: [/콘센트\s*(?:있는|있음|가능(?:한)?|사용\s*가능(?:한)?|이용\s*가능(?:한)?)/g, /전원\s*(?:있는|있음|사용\s*가능(?:한)?)/g, /충전\s*(?:가능(?:한)?|할\s*수\s*있는)/g],
    evidenceKeywords: ['콘센트있음', '콘센트', '전원', '충전가능', '충전 가능'],
  },
  {
    id: 'parking',
    matchLabel: '주차 가능',
    missingLabel: '주차 가능 여부',
    keywords: ['주차가능', '주차 가능', '주차되는', '주차 되는', '주차할 수', '주차 가능한'],
    cleanupPatterns: [/주차\s*(?:가능(?:한|함)?|되는|할\s*수\s*있는|있는|있음)/g],
    evidenceKeywords: ['주차가능', '주차 가능', '주차장', '공영주차장', '주차'],
  },
  {
    id: 'indoor',
    matchLabel: '실내 이용 가능',
    missingLabel: '실내 이용 가능 여부',
    keywords: ['실내', '실내에서'],
    cleanupPatterns: [/실내에서/g, /실내/g, /쉴\s*수\s*있는/g],
    evidenceKeywords: ['실내쉼터', '실내', '실내공간', '실내 이용', '실내시설'],
  },
  {
    id: 'quiet',
    matchLabel: '조용함',
    missingLabel: '조용함',
    keywords: ['조용한', '조용히', '조용함'],
    cleanupPatterns: [/조용한/g, /조용히/g, /조용함/g],
    evidenceKeywords: ['조용한', '조용함', '조용', '집중하기좋음', '작업가능후보'],
  },
]
export const GENERIC_CONDITION_TARGETS = ['곳', '장소', '데', '근처', '주변', '추천', '찾아줘', '찾아', '갈만한곳', '갈만한 곳']

export const KAKAO_DETAIL_LOOKUP_RADIUS_M = 300

export const KAKAO_DETAIL_MATCH_DISTANCE_M = 150

export const KAKAO_DETAIL_WIDE_MATCH_DISTANCE_M = 300

export const KAKAO_DETAIL_WIDE_CATEGORIES = new Set([
  'city_park',
  'citypark',
  'tourism',
  'beach',
  '공원',
  '관광지',
  '해수욕장',
])

export const KAKAO_DETAIL_WIDE_NAME_KEYWORDS = [
  '공원',
  '해수욕장',
  '관광지',
  '산책',
  '광장',
]

export const KAKAO_DETAIL_NAME_SIMILARITY_MIN = 0.72

export const KAKAO_DETAIL_MAX_QUERY_COUNT = 5

export const KAKAO_DETAIL_GENERIC_NAMES = new Set([
  '센터',
  '쉼터',
  '공원',
  '화장실',
  '주차장',
  '도서관',
  '카페',
  '식당',
  '관광지',
  '해수욕장',
  '광장',
])

export const KAKAO_DETAIL_SUFFIX_BOUNDARY_WORDS = [
  '센터',
  '지원센터',
  '복지관',
  '도서관',
  '주차장',
  '공영주차장',
  '공중화장실',
  '화장실',
  '해수욕장',
  '쉼터',
  '공원',
  '광장',
  '분관',
  '지점',
]
