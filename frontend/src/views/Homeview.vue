<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  aiSearchRecommendations,
  buildConversationalSearchPlan,
  checkSearchSafety,
  getKakaoPlaceTags,
  getSavedPlaces,
  runAiWebSearch,
  saveSearchLog,
} from '@/api/recommendation'
import KakaoMap from '@/components/KakaoMap.vue'
import { useAuthStore } from '@/stores/auth'

const IS_DEV = import.meta.env.DEV

const props = defineProps({
  initialTab: {
    type: String,
    default: 'search',
  },
})

const normalizeTab = (tab) => {
  return ['search', 'map'].includes(tab) ? tab : 'search'
}

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const activeTab = ref(normalizeTab(props.initialTab))
const searchKeyword = ref('')

watch(
  () => props.initialTab,
  (nextTab) => {
    activeTab.value = normalizeTab(nextTab)
  },
)

const DEFAULT_CENTER = {
  lat: 35.1796,
  lng: 129.0756,
}

// 지도 검색 반경: 5km
const SEARCH_RADIUS = 5000
const MIN_VIEWPORT_SEARCH_RADIUS = 500
const MAX_VIEWPORT_SEARCH_RADIUS = 20000

// 카카오 장소 검색은 한 번에 최대 15개까지 가져오는 구조라서
// 15개씩 페이지를 추가 조회한 뒤 최대 50개까지만 사용합니다.
const SEARCH_SIZE_PER_PAGE = 15
const MAX_SEARCH_RESULT_COUNT = 50
const DB_SEARCH_RESULT_COUNT = 50
const DISPLAY_BATCH_SIZE = 15
const KAKAO_FALLBACK_MIN_RESULTS = 3
const KAKAO_FALLBACK_MAX_QUERIES = 5
const KAKAO_WALK_HEALING_FALLBACK_MAX_QUERIES = 9
const KAKAO_FALLBACK_MAX_RESULTS = 8
const WALK_HEALING_FALLBACK_RADII = [3000, 5000]
const KAKAO_FALLBACK_MAX_SCORE = 60
const AI_WEB_SEARCH_MIN_DB_RESULTS = 3
const AI_WEB_SEARCH_MIN_TOTAL_RESULTS = 5
const AI_WEB_SEARCH_SUFFICIENT_TOTAL_RESULTS = 10
const AI_WEB_SEARCH_INFRA_BLOCK_CATEGORIES = new Set([
  'toilet',
  'parking',
  'smoking_area',
  'freewifi',
])
const AI_WEB_SEARCH_EXPLICIT_KEYWORDS = [
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
const AI_WEB_SEARCH_HELPFUL_KEYWORDS = [
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
const AI_WEB_SEARCH_HELPFUL_CATEGORIES = new Set([
  'restaurant',
  'cafe',
  'tourism',
  'beach',
  'city_park',
])
const AI_WEB_SEARCH_DETAIL_KEYWORDS = [
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
const CAFE_SEARCH_KEYWORDS = ['카페', '커피', 'cafe']
const INFRA_SEARCH_KEYWORDS = [
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
const DB_MARKER_ALLOWED_CATEGORIES = [
  'toilet',
  'freewifi',
  'smoking_area',
  'beach',
  'parking',
  'city_park',
  'tourism',
]
const AI_SCENARIO_KAKAO_KEYWORDS = {
  work_cafe: '카페',
  waiting_place: '카페',
  walk_healing: '공원',
  smoking_area: '흡연구역',
  restaurant: '식당',
}
const SCENARIO_DISPLAY_LABELS = {
  work_cafe: '조용히 작업할 곳',
  waiting_place: '잠깐 쉴 곳',
  walk_healing: '산책/힐링',
  smoking_area: '흡연 가능한 곳',
  restaurant: '식당/맛집',
  blocked: '검색 불가',
}
const CATEGORY_KAKAO_KEYWORDS = {
  cafe: '카페',
  shelter: '쉼터',
  city_park: '공원',
  beach: '해수욕장',
  tourism: '관광지',
  smoking_area: '흡연구역',
  restaurant: '식당',
}
const CATEGORY_KEYWORD_MAP = [
  { category: 'toilet', keyword: '화장실', aliases: ['화장실', '공중화장실'] },
  { category: 'parking', keyword: '주차장', aliases: ['주차장', '주차'] },
  { category: 'smoking_area', keyword: '흡연구역', aliases: ['흡연구역', '흡연장', '흡연'] },
  { category: 'freewifi', keyword: '와이파이', aliases: ['와이파이', '무료와이파이', 'wifi', 'wi-fi'] },
  { category: 'city_park', keyword: '공원', aliases: ['공원'] },
  { category: 'shelter', keyword: '쉼터', aliases: ['쉼터', '쉴 곳', '쉴곳', '휴식'] },
  { category: 'beach', keyword: '해수욕장', aliases: ['해수욕장', '바다'] },
  { category: 'tourism', keyword: '관광지', aliases: ['관광지', '가볼만한 곳', '가볼만한곳'] },
  { category: 'restaurant', keyword: '식당', aliases: ['식당', '맛집', '음식점'] },
  { category: 'cafe', keyword: '카페', aliases: ['카페', '커피', 'cafe'] },
]
const WORK_CAFE_KEYWORDS = [
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
const WORK_CAFE_PREFERRED_TAGS = [
  '노트북작업',
  '콘센트있음',
  '와이파이',
  '조용한',
  '혼자이용좋음',
]
const WAITING_PLACE_KEYWORDS = [
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
const RESTAURANT_INTENT_KEYWORDS = [
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
const WALK_HEALING_KEYWORDS = [
  '산책',
  '힐링',
  '야경',
  '걷기',
]
const SMOKING_INTENT_KEYWORDS = [
  '흡연가능',
  '흡연 가능',
  '담배',
]
const INTENT_PREFERRED_TAGS = {
  work_cafe: WORK_CAFE_PREFERRED_TAGS,
  waiting_place: ['실내쉼터', '잠깐쉬기좋음'],
  walk_healing: ['산책좋음', '힐링', '야경'],
  smoking_area: ['흡연가능', '흡연구역'],
  restaurant: ['혼자이용좋음', '혼밥좋음', '조용한', '식사좋음'],
}
const INTENT_NEGATIVE_TAGS = {
  waiting_place: ['실외', '야외'],
}
const INTENT_KAKAO_KEYWORD_CANDIDATES = {
  work_cafe: ['카페', '작업 카페', '공부 카페', '스터디카페'],
  waiting_place: ['카페', '쉼터', '실내 쉼터'],
  walk_healing: ['공원', '산책로', '강변', '하천', '둘레길', '해변', '해수욕장', '관광지', '전망대'],
  smoking_area: ['흡연구역', '흡연실'],
  restaurant: ['혼밥', '식당', '밥집', '음식점'],
}
const WALK_HEALING_FALLBACK_QUERIES = [
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
const WALK_HEALING_LOCATION_QUERY_KEYWORDS = [
  '공원',
  '산책로',
  '강변',
  '하천',
  '걷기 좋은 곳',
]
const WALK_HEALING_ALLOWED_KEYWORDS = [
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
const WALK_HEALING_EXCLUDE_KEYWORDS = [
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
const WALK_HEALING_CAFE_KEYWORDS = ['카페', '커피', '디저트', '베이커리', '빵집']
const KAKAO_FALLBACK_KEYWORD_RULES = [
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
const FOOD_MENU_KNOWN_KEYWORDS = ['소금빵', '디저트', '브런치', '커피', '파스타', '쌀국수', '돈까스', '돈가스', '밥', '식사', '빵']
const FOOD_MENU_PATTERN_SUFFIXES = [
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
const FOOD_BAKERY_KEYWORDS = ['빵', '소금빵', '디저트', '베이커리', '빵집']
const FOOD_CAFE_KEYWORDS = ['카페', '커피', '디저트', '브런치', '소금빵', '빵']
const ABSTRACT_TARGET_KEYWORDS = [
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
const TYPO_CORRECTION_MAP = [
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
const TAKEOUT_HEAVY_KEYWORDS = [
  '컴포즈',
  '메가커피',
  '메가MGC',
  '빽다방',
  '더벤티',
  '테이크아웃',
  'takeout',
]
const WAITING_PLACE_EXCLUDE_KEYWORDS = [
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
const WAITING_PLACE_PENALTY_KEYWORDS = [
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
const WAITING_PLACE_PREFERRED_KEYWORDS = [
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
const ANCILLARY_PLACE_KEYWORDS = [
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
const DESTINATION_CATEGORY_KEYWORDS = [
  '공원',
  '관광명소',
  '문화시설',
  '해수욕장',
  '전망대',
  '산책로',
  '관광지',
]
const ANCILLARY_INTENT_CATEGORIES = [
  'parking',
  'toilet',
  'freewifi',
]
const REQUEST_CONDITION_RULES = [
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
const GENERIC_CONDITION_TARGETS = ['곳', '장소', '데', '근처', '주변', '추천', '찾아줘', '찾아', '갈만한곳', '갈만한 곳']

const mapCenter = ref(DEFAULT_CENTER)
const mapViewportBounds = ref(null)
const mapFitBoundsKey = ref(0)
const currentLocationPlace = ref([])
const allSearchResults = ref([])
const mainResults = ref([])
const fallbackResults = ref([])
const webReferenceResults = ref([])
const visibleCount = ref(DISPLAY_BATCH_SIZE)
const resultFilterMode = ref('all')
const sortMode = ref('distance')
const searchResultStatus = ref('idle')
const searchErrorMessage = ref('')
const resultSourceLabel = ref('검색 결과')
const resultMessageSuffix = ref('')
const selectedPlace = ref(null)
const detailTagList = ref(null)
const resolvedKakaoDetailUrls = ref({})
const kakaoDetailLookupStatus = ref({})
const baseLocationCandidates = ref([])
const pendingBaseLocationSearch = ref(null)
const isResultListCollapsed = ref(false)
const isPlaceDetailCollapsed = ref(false)
const activeResultView = ref('results')

const isLocating = ref(false)
const isSearchingMap = ref(false)

const locationMessage = ref('지도 버튼을 누르면 현재 위치 기준으로 지도를 표시합니다.')
const loadingMessage = ref('')
const mapSearchKeyword = ref('')
const aiSearchKeyword = ref('')
const aiSearchError = ref('')
const mapAiParse = ref(null)
const aiWebSearchContext = ref(null)
const aiWebSearchAvailability = ref(null)
const aiWebSearchStatus = ref('idle')
const aiWebSearchMessage = ref('')
const aiWebSearchCandidates = ref([])
const aiWebSearchClientCache = ref({})
const aiWebSearchLastResult = ref(null)
const activeSearchPlan = ref(null)
const pendingClarification = ref(null)
const clarificationThread = ref([])
const followUpInput = ref('')
const followUpInputRef = ref(null)
const primarySearchInputRef = ref(null)
const conversationModeStarted = ref(false)
const activeMenuSearchProfile = ref(null)

const showDetailPanel = ref(false)
const detailFrameError = ref(false)

const displayUserName = computed(() => {
  const user = authStore.user || {}
  return user.profile?.nickname ||
    user.nickname ||
    user.username ||
    '사용자'
})

const applyRouteSearchQuery = (value) => {
  const nextQuery = Array.isArray(value) ? value[0] : value
  const normalizedQuery = String(nextQuery || '').trim()

  if (!normalizedQuery) return

  searchKeyword.value = normalizedQuery
  mapSearchKeyword.value = normalizedQuery
  activeTab.value = 'search'
}

watch(
  () => route.query.q,
  applyRouteSearchQuery,
  { immediate: true },
)

const NO_RESULT_MESSAGE_PATTERNS = [
  '검색 결과가 없습니다',
  '추천 결과가 없습니다',
  '조건에 맞는 추천 결과가 없습니다',
  '후보를 찾지 못했습니다',
]

const isNoResultLocationMessage = (message = '') => {
  return NO_RESULT_MESSAGE_PATTERNS.some((pattern) => {
    return String(message || '').includes(pattern)
  })
}

const clearNoResultLocationMessage = () => {
  if (isNoResultLocationMessage(locationMessage.value)) {
    locationMessage.value = ''
  }
}

const resetSearchStatusMessage = (message = '검색 조건을 확인하는 중입니다.') => {
  locationMessage.value = message
}

const KAKAO_DETAIL_LOOKUP_RADIUS_M = 300
const KAKAO_DETAIL_MATCH_DISTANCE_M = 150
const KAKAO_DETAIL_WIDE_MATCH_DISTANCE_M = 300
const KAKAO_DETAIL_WIDE_CATEGORIES = new Set([
  'city_park',
  'citypark',
  'tourism',
  'beach',
  '공원',
  '관광지',
  '해수욕장',
])
const KAKAO_DETAIL_WIDE_NAME_KEYWORDS = [
  '공원',
  '해수욕장',
  '관광지',
  '산책',
  '광장',
]
const KAKAO_DETAIL_NAME_SIMILARITY_MIN = 0.72
const KAKAO_DETAIL_MAX_QUERY_COUNT = 5
const KAKAO_DETAIL_GENERIC_NAMES = new Set([
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
const KAKAO_DETAIL_SUFFIX_BOUNDARY_WORDS = [
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

const RESULT_FILTER_OPTIONS = [
  { value: 'all', label: '전체' },
  { value: 'db', label: 'DB 추천' },
  { value: 'kakao', label: '카카오 후보' },
]

const RESULT_SORT_OPTIONS = [
  { value: 'recommendation', label: '추천순' },
  { value: 'distance', label: '거리순' },
  { value: 'confidence', label: '신뢰도순' },
]

const getResultFilterLabel = (filterMode = resultFilterMode.value) => {
  return RESULT_FILTER_OPTIONS.find((option) => option.value === filterMode)?.label || '전체'
}

const isSearchErrorMessage = (message = '') => {
  const text = getTextValue(message)
  return text.includes('오류가 발생했습니다') || text.includes('다시 시도해 주세요')
}

const clearMainSearchErrorState = () => {
  searchErrorMessage.value = ''
  aiSearchError.value = ''

  if (isSearchErrorMessage(locationMessage.value)) {
    locationMessage.value = ''
  }
}

const beginMainSearch = ({ preserveClarificationThread = false } = {}) => {
  mainResults.value = []
  fallbackResults.value = []
  webReferenceResults.value = []
  pendingClarification.value = null
  if (!preserveClarificationThread) {
    clarificationThread.value = []
  }
  baseLocationCandidates.value = []
  pendingBaseLocationSearch.value = null
  syncLegacySearchResults()
  searchResultStatus.value = 'loading'
  clearMainSearchErrorState()
}

const setMainSearchError = (message) => {
  if (displayResults.value.length > 0) {
    searchResultStatus.value = 'success'
    clearMainSearchErrorState()
    return
  }

  const fallbackMessage = message || '검색 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'
  searchResultStatus.value = 'error'
  searchErrorMessage.value = fallbackMessage
  aiSearchError.value = fallbackMessage
  locationMessage.value = fallbackMessage
}

const getDisplayResultKey = (place = {}) => {
  return [
    place.id,
    place.savedPlaceId,
    place.kakaoPlaceId,
    place.externalId,
    `${place.name || ''}:${place.address || ''}`,
  ].find((value) => value !== undefined && value !== null && String(value).trim()) || ''
}

const mergeAndSortMainResults = (primaryResults = [], secondaryResults = []) => {
  const mergedResults = [...primaryResults]
  const seenKeys = new Set(
    mergedResults
      .map(getDisplayResultKey)
      .filter(Boolean),
  )

  secondaryResults.forEach((place) => {
    const key = getDisplayResultKey(place)
    if (key && seenKeys.has(key)) return

    if (key) {
      seenKeys.add(key)
    }
    mergedResults.push(place)
  })

  return mergedResults
}

const displayResults = computed(() => {
  return mergeAndSortMainResults(mainResults.value, fallbackResults.value)
})

const syncLegacySearchResults = () => {
  allSearchResults.value = displayResults.value
}

const logSearchResultState = async () => {
  if (!import.meta.env.DEV) return

  await nextTick()
  console.debug('[검색 결과 상태]', {
    mainCount: mainResults.value.length,
    fallbackCount: fallbackResults.value.length,
    displayCount: displayResults.value.length,
    webReferenceCount: webReferenceResults.value.length,
    status: searchResultStatus.value,
    errorMessage: searchErrorMessage.value,
    locationMessage: locationMessage.value,
  })
}

const setMainResults = (results = []) => {
  mainResults.value = Array.isArray(results) ? results : []
  syncLegacySearchResults()

  if (displayResults.value.length > 0) {
    searchResultStatus.value = 'success'
    clearMainSearchErrorState()
  }
}

const setFallbackResults = (results = []) => {
  fallbackResults.value = Array.isArray(results) ? results : []
  syncLegacySearchResults()

  if (displayResults.value.length > 0) {
    searchResultStatus.value = 'success'
    clearMainSearchErrorState()
  }
}

const filteredSearchResults = computed(() => {
  return displayResults.value.filter((place) => {
    return matchesResultFilter(place, resultFilterMode.value)
  })
})

const sortedSearchResults = computed(() => {
  return sortSearchResults(filteredSearchResults.value)
})

const searchedPlaces = computed(() => {
  return assignMarkerLabels(
    sortedSearchResults.value.slice(0, visibleCount.value),
  )
})

const mapPlaces = computed(() => {
  return [
    ...currentLocationPlace.value,
    ...searchedPlaces.value,
  ]
})

const mapLayoutKey = computed(() => {
  return [
    searchedPlaces.value.length > 0 ? 'has-results' : 'no-results',
    selectedPlace.value ? 'has-detail' : 'no-detail',
  ].join(':')
})

const hasMoreResults = computed(() => {
  return visibleCount.value < filteredSearchResults.value.length
})

const resultCountText = computed(() => {
  if (!displayResults.value.length) {
    return ''
  }

  const suffix = resultMessageSuffix.value
    ? ` · ${resultMessageSuffix.value}`
    : ''

  if (resultFilterMode.value !== 'all') {
    return `${getResultFilterLabel()} ${filteredSearchResults.value.length}개 중 ${searchedPlaces.value.length}개 표시${suffix}`
  }

  return `${resultSourceLabel.value} ${filteredSearchResults.value.length}개 중 ${searchedPlaces.value.length}개 표시${suffix}`
})

const mapParserStatus = computed(() => {
  if (!mapAiParse.value) {
    return null
  }

  if (!mapAiParse.value.parser_fallback && mapAiParse.value.parser_provider === 'gms') {
    return {
      label: 'AI 사용',
      detail: 'GMS가 자연어를 추천 조건으로 해석했습니다.',
      className: 'ai',
    }
  }

  return {
    label: '규칙 기반 파서 사용',
    detail: 'AI 호출이 없거나 실패해서 키워드 규칙으로 추천 조건을 해석했습니다.',
    className: 'fallback',
  }
})

const searchPlanStatus = computed(() => {
  if (!activeSearchPlan.value?.correctionApplied) {
    return null
  }

  return {
    label: '검색어 보정',
    detail: `'${activeSearchPlan.value.normalizedQuery}'로 이해했어요.`,
    className: 'fallback',
  }
})

const getAiWebSearchSignalParts = (query = '', condition = {}, searchPlan = {}) => {
  return [
    query,
    condition?.intent,
    condition?.scenario,
    condition?.category,
    condition?.categoryHint,
    condition?.category_hint,
    condition?.keyword,
    searchPlan?.targetQuery,
    searchPlan?.target_query,
    searchPlan?.targetKeyword,
    searchPlan?.target_keyword,
    searchPlan?.categoryHint,
    searchPlan?.category_hint,
    ...(Array.isArray(condition?.keywords) ? condition.keywords : []),
    ...(Array.isArray(condition?.menu_keywords) ? condition.menu_keywords : []),
    ...(Array.isArray(condition?.place_type_keywords) ? condition.place_type_keywords : []),
    ...(Array.isArray(condition?.purpose_keywords) ? condition.purpose_keywords : []),
    ...(Array.isArray(condition?.required_tags) ? condition.required_tags : []),
    ...(Array.isArray(condition?.preferred_tags) ? condition.preferred_tags : []),
    ...(Array.isArray(condition?.tags) ? condition.tags : []),
    ...(Array.isArray(searchPlan?.menu_keywords) ? searchPlan.menu_keywords : []),
    ...(Array.isArray(searchPlan?.place_type_keywords) ? searchPlan.place_type_keywords : []),
    ...(Array.isArray(searchPlan?.requestedConditions) ? searchPlan.requestedConditions : []),
    ...(Array.isArray(searchPlan?.requested_conditions) ? searchPlan.requested_conditions : []),
  ]
}

const getAiWebSearchSignalText = (query = '', condition = {}, searchPlan = {}) => {
  return normalizeLocationText(getAiWebSearchSignalParts(query, condition, searchPlan).filter(Boolean).join(' '))
}

const hasAiWebSearchKeyword = (keywords = [], query = '', condition = {}, searchPlan = {}) => {
  const text = getAiWebSearchSignalText(query, condition, searchPlan)
  return keywords.some((keyword) => text.includes(normalizeLocationText(keyword)))
}

const hasAiWebSearchDetailCondition = (query = '', condition = {}, searchPlan = {}) => {
  return hasAiWebSearchKeyword(AI_WEB_SEARCH_DETAIL_KEYWORDS, query, condition, searchPlan)
}

const hasExplicitAiWebSearchRequest = (query = '', condition = {}, searchPlan = {}) => {
  return hasAiWebSearchKeyword(AI_WEB_SEARCH_EXPLICIT_KEYWORDS, query, condition, searchPlan)
}

const getAiWebSearchCategories = (condition = {}, searchPlan = {}) => {
  return [
    condition?.category,
    condition?.categoryHint,
    condition?.category_hint,
    condition?.scenario,
    searchPlan?.categoryHint,
    searchPlan?.category_hint,
  ].map((value) => getTextValue(value))
}

const isAiWebSearchHelpfulTopic = (query = '', condition = {}, searchPlan = {}) => {
  if (getAiWebSearchCategories(condition, searchPlan).some((category) => {
    return AI_WEB_SEARCH_HELPFUL_CATEGORIES.has(category)
  })) {
    return true
  }

  return hasAiWebSearchKeyword(AI_WEB_SEARCH_HELPFUL_KEYWORDS, query, condition, searchPlan)
}

const isAiWebSearchInfraBlockedTopic = (query = '', condition = {}, searchPlan = {}) => {
  if (getAiWebSearchCategories(condition, searchPlan).some((category) => {
    return AI_WEB_SEARCH_INFRA_BLOCK_CATEGORIES.has(category)
  })) {
    return true
  }

  if (isAiWebSearchHelpfulTopic(query, condition, searchPlan)) {
    return false
  }

  const targetText = normalizeLocationText([
    searchPlan?.targetQuery,
    searchPlan?.target_query,
    searchPlan?.targetKeyword,
    searchPlan?.target_keyword,
    condition?.keyword,
    query,
  ].filter(Boolean).join(' '))

  return [
    '공중화장실',
    '화장실',
    '주차장',
    '흡연구역',
    '흡연장',
    '무료와이파이',
    '무료wifi',
    'freewifi',
  ].some((keyword) => targetText.includes(normalizeLocationText(keyword)))
}

const hasAiWebSearchStrongEvidence = (place = {}) => {
  if (isCategoryFallbackRecommendation(place)) return false

  const evidenceLabels = [
    ...getRecommendationMatchedLabels(place),
    ...toDisplayList(place?.verifiedTags || place?.verified_tags),
    ...toDisplayList(place?.matchedTags || place?.matched_tags),
  ]
  if (evidenceLabels.length) return true

  const sourceType = getTextValue(place.recommendationSourceType || place.source_type)
  const confidence = getTextValue(getRecommendationConfidence(place)).toLowerCase()
  return ['db_verified', 'db_candidate'].includes(sourceType) && confidence !== 'low'
}

const getAiWebSearchLowConfidenceCount = (results = []) => {
  return results.filter((place) => {
    const confidence = getTextValue(
      place?.recommendationConfidence ||
      place?.confidence ||
      getRecommendationConfidence(place),
    ).toLowerCase()
    return confidence === 'low'
  }).length
}

const getAiWebSearchStrongEvidenceCount = (results = []) => {
  return results.filter((place) => hasAiWebSearchStrongEvidence(place)).length
}

const shouldSuggestAiWebSearch = computed(() => {
  const context = aiWebSearchContext.value
  if (!context) return false

  const summary = context.existingResultsSummary || {}
  const dbCount = Number(summary.db_count || 0)
  const kakaoFallbackCount = Number(summary.kakao_fallback_count || 0)
  const totalCount = Number(summary.total_count || dbCount + kakaoFallbackCount)
  const rawTotalCount = Number(summary.raw_total_count || totalCount)
  const lowConfidenceCount = Number(summary.low_confidence_count || 0)
  const weakMatchCount = Number(summary.weak_match_count || 0)
  const strongEvidenceCount = Number(summary.strong_evidence_count || 0)
  const directMatchCount = Number(summary.direct_match_count ?? dbCount)
  const menuIntent = Boolean(summary.menu_intent)
  const searchPlan = context.searchPlan || {}
  const explicitRequest = Boolean(summary.explicit_web_request) ||
    hasExplicitAiWebSearchRequest(context.query, context.condition, searchPlan)
  const helpfulTopic = Boolean(summary.web_helpful_topic) ||
    isAiWebSearchHelpfulTopic(context.query, context.condition, searchPlan)

  if (summary.infra_blocked_topic || isAiWebSearchInfraBlockedTopic(context.query, context.condition, searchPlan)) {
    return false
  }

  if (explicitRequest) {
    return true
  }

  if (!helpfulTopic) {
    return false
  }

  if (rawTotalCount >= AI_WEB_SEARCH_SUFFICIENT_TOTAL_RESULTS) {
    return false
  }

  if (
    strongEvidenceCount > 0 &&
    dbCount >= AI_WEB_SEARCH_MIN_DB_RESULTS &&
    totalCount >= AI_WEB_SEARCH_MIN_TOTAL_RESULTS &&
    lowConfidenceCount < Math.max(1, Math.ceil(totalCount / 2))
  ) {
    return false
  }

  const lacksEnoughResults = (
    totalCount === 0 ||
    dbCount < AI_WEB_SEARCH_MIN_DB_RESULTS ||
    (menuIntent && directMatchCount < KAKAO_FALLBACK_MIN_RESULTS)
  )
  const kakaoOnlyOrWeak = kakaoFallbackCount > 0 && strongEvidenceCount === 0
  const lowQualityMajority = totalCount > 0 && (
    lowConfidenceCount >= Math.max(1, Math.ceil(totalCount / 2)) ||
    weakMatchCount >= Math.max(1, Math.ceil(totalCount / 2))
  )

  return (
    lacksEnoughResults ||
    kakaoOnlyOrWeak ||
    lowQualityMajority ||
    (hasAiWebSearchDetailCondition(context.query, context.condition, searchPlan) && strongEvidenceCount === 0)
  )
})

const shouldShowAiWebSearchPanel = computed(() => {
  return Boolean(
    aiWebSearchContext.value &&
    !isSearchingMap.value &&
    !isResultListCollapsed.value &&
    shouldSuggestAiWebSearch.value,
  )
})

const hasSearchExperienceContent = computed(() => {
  return Boolean(
    mapSearchKeyword.value.trim() ||
    pendingClarification.value ||
    clarificationThread.value.length ||
    displayResults.value.length ||
    isSearchingMap.value ||
    shouldShowAiWebSearchPanel.value ||
    baseLocationCandidates.value.length,
  )
})

const hasMapExperienceContent = computed(() => {
  return Boolean(
    (activeTab.value === 'map' || activeTab.value === 'search') &&
    (
      hasSearchExperienceContent.value ||
      currentLocationPlace.value.length
    ),
  )
})

const isConversationMode = computed(() => {
  return Boolean(
    conversationModeStarted.value ||
    clarificationThread.value.length ||
    pendingClarification.value ||
    isSearchingMap.value ||
    displayResults.value.length ||
    baseLocationCandidates.value.length,
  )
})

const clearTopSearchInputsForClarification = () => {
  searchKeyword.value = ''
  mapSearchKeyword.value = ''
}

const focusFollowUpInput = async () => {
  await nextTick()
  followUpInputRef.value?.focus?.()
}

const focusPrimarySearchInput = async () => {
  await nextTick()
  primarySearchInputRef.value?.focus?.()
}

const setClarificationThread = (query, plan, message) => {
  const userText = String(query || '').trim()
  const assistantText = String(
    message ||
    plan?.clarification_question ||
    plan?.message ||
    '지역과 목적을 함께 입력해 주세요.',
  ).trim()
  const partialSearchPlan = plan?.search_plan && typeof plan.search_plan === 'object'
    ? { ...plan.search_plan }
    : {}
  const partialConditions = getPlannerList(
    getSearchPlanValue(partialSearchPlan, 'requestedConditions', 'requested_conditions', 'conditions') ||
    plan?.conditions ||
    [],
  )

  pendingClarification.value = {
    original_query: userText,
    query: userText,
    plan,
    partial_search_plan: {
      ...partialSearchPlan,
      locationQuery: getPlannerText(getSearchPlanValue(partialSearchPlan, 'locationQuery', 'location_query')),
      baseLocationQuery: getPlannerText(getSearchPlanValue(partialSearchPlan, 'baseLocationQuery', 'base_location_query')),
      targetQuery: getPlannerText(getSearchPlanValue(partialSearchPlan, 'targetQuery', 'target_query')),
      scenario: getPlannerText(partialSearchPlan.scenario),
      conditions: partialConditions,
      requestedConditions: partialConditions,
    },
    missing_field: 'location',
    clarification_question: assistantText,
    message: assistantText,
  }
  conversationModeStarted.value = true
  followUpInput.value = ''
  clearTopSearchInputsForClarification()
  clarificationThread.value = [
    userText ? { role: 'user', label: displayUserName.value, text: userText } : null,
    assistantText ? { role: 'assistant', label: 'AI', text: assistantText } : null,
  ].filter(Boolean).slice(-3)
  focusFollowUpInput()
}

const clearPendingClarification = () => {
  pendingClarification.value = null
  clarificationThread.value = []
  followUpInput.value = ''
}

const shouldShowClarificationThread = computed(() => {
  return clarificationThread.value.length > 0
})

const shouldShowFollowUpInput = computed(() => {
  return Boolean(
    pendingClarification.value &&
    pendingClarification.value.missing_field === 'location',
  )
})

const searchConversationTitle = computed(() => {
  const query = mapSearchKeyword.value.trim() || searchKeyword.value.trim()

  if (isSearchingMap.value) {
    return query ? `“${query}”에 맞는 장소를 찾는 중이에요.` : '필요한 장소를 찾는 중이에요.'
  }

  if (pendingClarification.value) {
    return '검색 조건을 조금 더 알려주세요.'
  }

  if (displayResults.value.length && query) {
    return `현재 위치 기준으로 “${query}” 결과를 찾았어요.`
  }

  if (query) {
    return `“${query}” 검색을 준비했어요.`
  }

  return '상황을 입력하면 지도와 결과를 함께 정리해드려요.'
})

const searchConversationDetail = computed(() => {
  if (isSearchingMap.value) {
    return loadingMessage.value || '검색 조건을 확인하고 있습니다.'
  }

  if (displayResults.value.length) {
    if (
      locationMessage.value &&
      !isSearchErrorMessage(locationMessage.value) &&
      !isNoResultLocationMessage(locationMessage.value)
    ) {
      return locationMessage.value
    }

    return `${resultSourceLabel.value} ${filteredSearchResults.value.length}개를 확인했습니다.`
  }

  if (searchErrorMessage.value) {
    return searchErrorMessage.value
  }

  if (locationMessage.value) {
    return locationMessage.value
  }

  return '검색 결과가 부족하면 웹 검색 참고 링크를 보조로 확인할 수 있어요.'
})

const searchConversationChips = computed(() => {
  const chips = []
  const query = mapSearchKeyword.value.trim()
  const target = getTextValue(activeSearchPlan.value?.targetQuery || activeSearchPlan.value?.targetKeyword)
  const scenarioLabel = getScenarioDisplayLabel(activeSearchPlan.value?.recommendationIntent || '')
  const category = scenarioLabel ||
    getTextValue(activeSearchPlan.value?.categoryKeyword || activeSearchPlan.value?.categoryHint)

  if (query) {
    chips.push({ label: '검색어', value: query })
  }

  if (target && target !== query) {
    chips.push({ label: '대상', value: target })
  }

  if (category) {
    chips.push({ label: '분류', value: category })
  }

  if (displayResults.value.length) {
    chips.push({ label: '결과', value: `${filteredSearchResults.value.length}개` })
  }

  return chips.slice(0, 4)
})

const searchConversationNotice = computed(() => {
  const missingLabels = [
    ...new Set(displayResults.value.flatMap((place) => getRecommendationMissingLabels(place))),
  ]

  if (missingLabels.length) {
    return `“${missingLabels.slice(0, 2).join(', ')}”는 현재 데이터로 확인되지 않아 방문 전 확인이 필요합니다.`
  }

  if (shouldShowAiWebSearchPanel.value) {
    return '웹 검색 참고 결과도 함께 확인할 수 있어요.'
  }

  return ''
})

const setResultViewMode = (mode) => {
  activeResultView.value = mode === 'map' ? 'map' : 'results'
  isResultListCollapsed.value = activeResultView.value === 'map'
}

const toggleResultListPanel = () => {
  isResultListCollapsed.value = !isResultListCollapsed.value
  activeResultView.value = isResultListCollapsed.value ? 'map' : 'results'
}

const aiWebSearchButtonDisabled = computed(() => {
  return (
    aiWebSearchStatus.value === 'loading' ||
    !aiWebSearchAvailability.value?.enabled ||
    !aiWebSearchAvailability.value?.supported
  )
})

const aiWebSearchSummary = computed(() => {
  const summary = aiWebSearchLastResult.value?.summary
  return summary && typeof summary === 'object' ? summary : null
})

const aiWebSearchEvidenceCandidates = computed(() => {
  return aiWebSearchCandidates.value.slice(0, 5)
})

const stableStringify = (value) => {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value)
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`
  }

  return `{${Object.keys(value).sort().map((key) => {
    return `${JSON.stringify(key)}:${stableStringify(value[key])}`
  }).join(',')}}`
}

const getAiWebSearchRequestKey = (context) => {
  if (!context) return ''
  return stableStringify({
    query: context.query || '',
    lat: context.lat ?? null,
    lng: context.lng ?? null,
    locationHint: context.locationHint || '',
    searchPlan: context.searchPlan || {},
    condition: context.condition || {},
    existingResultsSummary: context.existingResultsSummary || {},
  })
}

const getAiWebSearchStatusMessage = (result = {}) => {
  const candidates = Array.isArray(result.candidates) ? result.candidates : []

  if (!result.enabled || !result.supported) {
    return 'AI 웹 검색 기능이 현재 비활성화되어 있습니다.'
  }

  if (result.error === 'incomplete_response') {
    return 'AI 웹 검색 응답이 완성되지 않아 후보를 표시하지 않았습니다.'
  }

  if (result.reason === 'manual_required') {
    return ''
  }

  if (result.error === 'temporary_server_error') {
    return 'AI 웹 검색 서버 응답이 일시적으로 실패했습니다. 다시 시도해 주세요.'
  }

  if (result.error === 'empty_candidates' || result.reason === 'no_valid_candidates') {
    return 'AI 웹 검색에서 표시할 후보를 찾지 못했습니다.'
  }

  if (result.error === 'missing_credentials') {
    return '검색 API 설정이 없어 참고 링크를 가져오지 못했습니다.'
  }

  if (result.reason === 'no_search_result') {
    return '웹 검색 참고 결과를 찾지 못했습니다.'
  }

  if (result.reason === 'no_location_matched_search_result') {
    return '현재 위치와 일치하는 웹 검색 참고 결과를 찾지 못했습니다.'
  }

  if (result.reason === 'missing_location_hint_for_broad_search') {
    return '웹 검색 참고 결과를 보려면 현재 위치 또는 지역 정보가 필요합니다.'
  }

  if (result.reason === 'invalid_request') {
    return 'AI 웹 검색 요청 설정을 확인해야 합니다.'
  }

  if (result.error === 'api_error') {
    return 'AI 웹 검색 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'
  }

  if (result.error && !candidates.length) {
    return 'AI 웹 검색 중 오류가 발생했습니다.'
  }

  if (!candidates.length) {
    return 'AI 웹 검색 결과가 없습니다.'
  }

  if (result.provider === 'naver_search') {
    return `방문 전 확인이 필요한 참고 링크 ${candidates.length}개입니다.`
  }

  return `AI 웹 검색 후보 ${candidates.length}개를 찾았습니다.`
}

const aiWebSearchDebugText = computed(() => {
  if (!import.meta.env.DEV) return ''

  const result = aiWebSearchLastResult.value
  const detail = result?.error_detail
  const summary = detail?.debug_summary || result?.debug_summary || null
  if (!detail && !summary) return ''

  const summaryText = summary
    ? [
        summary.output_count != null ? `outputs ${summary.output_count}` : '',
        Array.isArray(summary.output_types) && summary.output_types.length
          ? `types ${summary.output_types.join('/')}`
          : '',
        summary.source_count != null ? `sources ${summary.source_count}` : '',
        summary.output_url_count != null ? `output urls ${summary.output_url_count}` : '',
        summary.instruction_url_count != null ? `instruction urls ${summary.instruction_url_count}` : '',
        summary.annotation_count != null ? `annotations ${summary.annotation_count}` : '',
        summary.url_citation_count != null ? `citations ${summary.url_citation_count}` : '',
        summary.message_count != null ? `messages ${summary.message_count}` : '',
        summary.reasoning_count != null ? `reasoning ${summary.reasoning_count}` : '',
        summary.web_search_call_count != null ? `web search ${summary.web_search_call_count}` : '',
        summary.output_text_length != null ? `text ${summary.output_text_length}` : '',
        Array.isArray(summary.web_search_action_keys) && summary.web_search_action_keys.length
          ? `action keys ${summary.web_search_action_keys.join('/')}`
          : '',
      ].filter(Boolean).join(' · ')
    : ''

  return [
    result.reason,
    detail?.status_code ? `status ${detail.status_code}` : '',
    detail?.status || '',
    detail?.type || '',
    summaryText,
  ].filter(Boolean).join(' · ')
})

const placeListItemRefs = ref({})

const aiSearchPresets = [
  {
    label: '조용히 작업할 곳',
    query: '조용히 작업하기 좋은 카페',
  },
  {
    label: '잠깐 쉴 곳',
    query: '잠깐 쉴 곳',
  },
  {
    label: '산책/힐링',
    query: '산책하고 힐링하기 좋은 곳',
  },
  {
    label: '흡연 가능한 곳',
    query: '흡연 가능한 곳',
  },
]

const setPlaceListItemRef = (el, placeId) => {
  if (el) {
    placeListItemRefs.value[placeId] = el
  }
}

const scrollSelectedPlaceIntoView = async () => {
  await nextTick()

  if (!selectedPlace.value?.id) {
    return
  }

  const targetElement = placeListItemRefs.value[selectedPlace.value.id]

  if (!targetElement) {
    return
  }

  targetElement.scrollIntoView({
    behavior: 'smooth',
    block: 'nearest',
  })
}

watch(
  () => selectedPlace.value?.id,
  async () => {
    scrollSelectedPlaceIntoView()
    await nextTick()

    if (detailTagList.value) {
      detailTagList.value.scrollLeft = 0
      detailTagList.value.scrollTop = 0
    }

    resolveKakaoDetailUrlForPlace(selectedPlace.value)
  },
)

watch(resultFilterMode, async () => {
  visibleCount.value = DISPLAY_BATCH_SIZE
  mapFitBoundsKey.value += 1
  await nextTick()
  clearSelectedPlaceIfFilteredOut()
})

watch(sortMode, () => {
  visibleCount.value = DISPLAY_BATCH_SIZE
  mapFitBoundsKey.value += 1
})

const toFiniteCoordinate = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

const isSameMapCenter = (firstCenter, secondCenter) => {
  if (!firstCenter || !secondCenter) return false

  return (
    Math.abs(Number(firstCenter.lat) - Number(secondCenter.lat)) < 0.000001 &&
    Math.abs(Number(firstCenter.lng) - Number(secondCenter.lng)) < 0.000001
  )
}

const handleMapViewportChange = ({ center, bounds } = {}) => {
  const nextCenter = {
    lat: toFiniteCoordinate(center?.lat),
    lng: toFiniteCoordinate(center?.lng),
  }

  if (nextCenter.lat === null || nextCenter.lng === null) {
    return
  }

  if (!isSameMapCenter(mapCenter.value, nextCenter)) {
    mapCenter.value = nextCenter
  }

  const southWest = bounds?.southWest
  const northEast = bounds?.northEast

  if (!southWest || !northEast) {
    mapViewportBounds.value = null
    return
  }

  const nextBounds = {
    southWest: {
      lat: toFiniteCoordinate(southWest.lat),
      lng: toFiniteCoordinate(southWest.lng),
    },
    northEast: {
      lat: toFiniteCoordinate(northEast.lat),
      lng: toFiniteCoordinate(northEast.lng),
    },
  }

  if (
    nextBounds.southWest.lat === null ||
    nextBounds.southWest.lng === null ||
    nextBounds.northEast.lat === null ||
    nextBounds.northEast.lng === null
  ) {
    mapViewportBounds.value = null
    return
  }

  mapViewportBounds.value = nextBounds
}

const getSearchBoundsFromViewport = () => {
  if (!window.kakao?.maps || !mapViewportBounds.value) {
    return null
  }

  const { southWest, northEast } = mapViewportBounds.value

  return new window.kakao.maps.LatLngBounds(
    new window.kakao.maps.LatLng(southWest.lat, southWest.lng),
    new window.kakao.maps.LatLng(northEast.lat, northEast.lng),
  )
}

const getViewportSearchRadius = (center = mapCenter.value) => {
  if (!mapViewportBounds.value) {
    return SEARCH_RADIUS
  }

  const { southWest, northEast } = mapViewportBounds.value
  const corners = [
    southWest,
    northEast,
    { lat: southWest.lat, lng: northEast.lng },
    { lat: northEast.lat, lng: southWest.lng },
  ]

  const radius = Math.max(
    ...corners.map((corner) => getDistanceMetersBetweenPlaces(center, corner)),
  )

  if (!Number.isFinite(radius)) {
    return SEARCH_RADIUS
  }

  return Math.min(
    Math.max(Math.ceil(radius), MIN_VIEWPORT_SEARCH_RADIUS),
    MAX_VIEWPORT_SEARCH_RADIUS,
  )
}

const formatSearchRadius = (radius) => {
  if (radius >= 1000) {
    return `${Number((radius / 1000).toFixed(1))}km`
  }

  return `${radius}m`
}

const waitForKakaoServices = () => {
  return new Promise((resolve, reject) => {
    let retryCount = 0

    const checkLoaded = () => {
      if (window.kakao && window.kakao.maps && window.kakao.maps.services) {
        resolve()
        return
      }

      retryCount += 1

      if (retryCount >= 20) {
        reject(new Error('카카오 지도 서비스를 불러오지 못했습니다.'))
        return
      }

      window.setTimeout(checkLoaded, 250)
    }

    checkLoaded()
  })
}

const handleSearch = async () => {
  if (!searchKeyword.value.trim()) {
    alert('검색어를 입력해주세요.')
    return
  }

  conversationModeStarted.value = true
  mapSearchKeyword.value = searchKeyword.value.trim()
  activeTab.value = 'search'
  activeResultView.value = 'results'
  isResultListCollapsed.value = false

  await nextTick()

  try {
    await waitForKakaoServices()
    await performUnifiedMapSearch()
  } catch (error) {
    console.error(error)
    locationMessage.value = '카카오 지도 서비스를 불러오는 중입니다. 잠시 후 지도 검색 버튼을 눌러주세요.'
  }
}

const makeCurrentLocationMarker = ({ lat, lng }) => {
  return {
    id: 'current-location',
    name: '현재 위치',
    lat,
    lng,
    address: '',
    distance: null,
    markerColor: 'green',
    searchSource: 'current_location',
    sourceLabel: '기준',
    tags: [makeTag('현재위치', 'category_rule')],
  }
}

const requestBrowserLocation = () => {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('현재 브라우저에서 위치 정보를 지원하지 않습니다.'))
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        })
      },
      reject,
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 300000,
      },
    )
  })
}

const resolveCurrentContextCenter = async ({ updateMessage = true } = {}) => {
  if (updateMessage) {
    isLocating.value = true
    loadingMessage.value = '현재 위치 확인 중'
  }

  try {
    const currentCenter = await requestBrowserLocation()
    mapCenter.value = currentCenter
    currentLocationPlace.value = [makeCurrentLocationMarker(currentCenter)]

    if (updateMessage) {
      locationMessage.value = '현재 위치 기준으로 검색합니다.'
    }

    return {
      center: currentCenter,
      baseLabel: '현재 위치 기준',
      source: 'current_location',
    }
  } catch (error) {
    if (updateMessage) {
      locationMessage.value = '현재 위치를 가져오지 못해 현재 지도 중심 기준으로 검색합니다.'
    }

    return {
      center: mapCenter.value,
      baseLabel: '현재 지도 중심 기준',
      source: 'map_center',
    }
  } finally {
    if (updateMessage) {
      isLocating.value = false
      loadingMessage.value = ''
    }
  }
}

const getSearchCenterForRecommendation = async ({ updateMessage = true } = {}) => {
  const currentContext = await resolveCurrentContextCenter({ updateMessage })
  const center = currentContext?.center || mapCenter.value || DEFAULT_CENTER

  return {
    center,
    baseLabel: currentContext?.baseLabel || '현재 지도 중심 기준',
    source: currentContext?.source || 'map_center',
  }
}

const openMapWithCurrentLocation = () => {
  activeTab.value = 'map'
  activeResultView.value = 'map'
  isResultListCollapsed.value = true

  isLocating.value = true
  locationMessage.value = '현재 위치를 확인하는 중입니다.'

  requestBrowserLocation()
    .then((currentCenter) => {
      mapCenter.value = currentCenter
      currentLocationPlace.value = [makeCurrentLocationMarker(currentCenter)]
      locationMessage.value = '현재 위치 기준으로 지도를 표시하고 있습니다.'
    })
    .catch((error) => {
      mapCenter.value = DEFAULT_CENTER
      currentLocationPlace.value = []

      if (error.code === error.PERMISSION_DENIED) {
        locationMessage.value = '위치 권한이 거부되어 기본 위치로 지도를 표시합니다.'
      } else if (error.code === error.TIMEOUT) {
        locationMessage.value = '현재 위치 확인 시간이 초과되어 기본 위치로 지도를 표시합니다.'
      } else {
        locationMessage.value = '현재 위치를 가져오지 못해 기본 위치로 지도를 표시합니다.'
      }
    })
    .finally(() => {
      isLocating.value = false
    })
}

const parseMapSearchInput = (keyword) => {
  const normalizedKeyword = keyword.replace(/\s+/g, ' ').trim()
  const currentContextPattern = /^(현재\s*위치|내\s*주변|내\s*근처|이\s*근처|이\s*주변|이\s*지도|지도|현재\s*지도)\s*(?:주변|근처|인근|가까운)?(?:에서|의)?\s*(.+)$/
  const currentContextMatched = normalizedKeyword.match(currentContextPattern)
  const currentContextPrefixPattern = /^(근처|주변|인근|가까운|가까이)(?:에|에서|의)?\s+(.+)$/
  const currentContextPrefixMatched = normalizedKeyword.match(currentContextPrefixPattern)

  if (currentContextMatched || currentContextPrefixMatched) {
    const targetQuery = (currentContextMatched?.[2] || currentContextPrefixMatched?.[2] || '').trim()

    return {
      hasBaseLocation: false,
      explicitCurrentContext: true,
      searchMode: 'current_context',
      baseKeyword: '',
      baseLocationQuery: '',
      locationQuery: '',
      targetKeyword: targetQuery,
      targetQuery,
    }
  }

  const aroundPattern = /^(.+?)\s*(주변|근처|인근)(?:에서|의)?\s+(.+)$/
  const matched = normalizedKeyword.match(aroundPattern)

  if (!matched) {
    const regionPatterns = [
      /^(.+?)에서\s+(.+)$/,
      /^(.+?)에\s+있는\s+(.+)$/,
      /^(.+?)\s+쪽\s+(.+)$/,
      /^(.+?)\s+일대\s+(.+)$/,
      /^(.+?)\s+지역\s+(.+)$/,
      /^([가-힣A-Za-z0-9]+(?:특별시|광역시|특별자치시|특별자치도|도|시|군|구|읍|면|동)?(?:\s+[가-힣A-Za-z0-9]+(?:시|군|구|읍|면|동)?)?)\s+(.+)$/,
    ]

    for (const pattern of regionPatterns) {
      const regionMatched = normalizedKeyword.match(pattern)

      if (!regionMatched) continue

      const locationQuery = regionMatched[1].trim()
      const targetQuery = regionMatched[2].trim()

      if (!locationQuery || !targetQuery) continue
      if (!isLikelyRegionSearchPair(locationQuery, targetQuery)) continue

      return {
        hasBaseLocation: true,
        explicitCurrentContext: false,
        searchMode: 'region_search',
        baseKeyword: locationQuery,
        baseLocationQuery: locationQuery,
        locationQuery,
        targetKeyword: targetQuery,
        targetQuery,
      }
    }

    return {
      hasBaseLocation: false,
      explicitCurrentContext: false,
      searchMode: 'current_context',
      baseKeyword: '',
      baseLocationQuery: '',
      locationQuery: '',
      targetKeyword: normalizedKeyword,
      targetQuery: normalizedKeyword,
    }
  }

  const baseKeyword = matched[1].trim()
  const targetKeyword = matched[3].trim()

  if (!isValidAroundBaseLocation(baseKeyword)) {
    const fallbackTargetQuery = `${baseKeyword} ${targetKeyword}`.trim()
    return {
      hasBaseLocation: false,
      explicitCurrentContext: true,
      searchMode: 'current_context',
      baseKeyword: '',
      baseLocationQuery: '',
      locationQuery: '',
      targetKeyword: fallbackTargetQuery,
      targetQuery: fallbackTargetQuery,
    }
  }

  return {
    hasBaseLocation: true,
    explicitCurrentContext: false,
    searchMode: 'around_location',
    baseKeyword,
    baseLocationQuery: baseKeyword,
    locationQuery: baseKeyword,
    targetKeyword,
    targetQuery: targetKeyword,
  }
}

const REGION_TARGET_HINT_KEYWORDS = [
  '카페',
  '맛집',
  '식당',
  '흡연',
  '산책',
  '쉴',
  '쉬',
  '가볼',
  '갈만',
  '볼만',
  '공원',
  '해수욕장',
  '도서관',
  '병원',
  '주차',
  '화장실',
]
const NON_REGION_LOCATION_WORDS = [
  '조용한',
  '조용히',
  '가까운',
  '가까이',
  '혼자',
  '혼밥',
  '사람',
  '사람많은',
  '붐비는',
  '밖',
  '실외',
  '노트북',
  '작업',
  '공부',
  '잠깐',
  '근처',
  '주변',
  '인근',
  '내주변',
  '내근처',
  '현재위치',
  '비',
  '눈',
  '더운',
  '추운',
  '좋은',
  '가볼만한',
  '가볼만',
  '흡연',
  '산책',
]

const isValidAroundBaseLocation = (baseKeyword = '') => {
  const baseText = normalizeLocationText(baseKeyword)

  if (!baseText) return false

  return !isNonRegionLocationText(baseText)
}

const isNonRegionLocationText = (locationText = '') => {
  const normalizedLocationText = normalizeLocationText(locationText)

  return NON_REGION_LOCATION_WORDS.some((word) => {
    const wordText = normalizeLocationText(word)
    return (
      normalizedLocationText === wordText ||
      normalizedLocationText === `${wordText}에` ||
      normalizedLocationText === `${wordText}에서` ||
      normalizedLocationText === `${wordText}의`
    )
  })
}

const isLikelyRegionSearchPair = (locationQuery, targetQuery) => {
  const locationText = normalizeLocationText(locationQuery)
  const targetText = normalizeLocationText(targetQuery)

  if (!locationText || !targetText) return false

  if (isNonRegionLocationText(locationText)) {
    return false
  }

  if (isRecommendationQueryText(locationQuery)) {
    return false
  }

  if (/[시도군구읍면동]$/.test(locationQuery) || hasRegionQualifier(locationQuery)) {
    return true
  }

  if (hasPoiHint(locationQuery)) {
    return true
  }

  const hasTargetHint = REGION_TARGET_HINT_KEYWORDS.some((keyword) => {
    return targetText.includes(normalizeLocationText(keyword))
  })

  return locationText.length >= 2 && locationText.length <= 8 && hasTargetHint
}

const RECOMMENDATION_QUERY_HINTS = [
  '비',
  '눈',
  '더위',
  '더운',
  '추위',
  '추운',
  '실내',
  '조용',
  '작업',
  '노트북',
  '공부',
  '콘센트',
  '와이파이',
  'wifi',
  '오래',
  '혼자',
  '혼밥',
  '찾아줘',
  '찾아',
  '갈만한',
  '좋은곳',
  '좋은 곳',
  '식당',
  '밥집',
  '음식점',
  '맛집',
  '브런치',
  '카페',
  '쉼터',
  '쉴',
  '쉬',
  '힐링',
  '산책',
  '공원',
  '화장실',
  '주차장',
  '흡연',
  '가능',
  '가볼',
  '추천',
]

const isRecommendationQueryText = (query = '') => {
  const queryText = normalizeLocationText(query)
  return RECOMMENDATION_QUERY_HINTS.some((keyword) => {
    return queryText.includes(normalizeLocationText(keyword))
  })
}

const getCategoryHint = (query = '') => {
  const queryText = normalizeLocationText(query)
  const matched = CATEGORY_KEYWORD_MAP.find(({ aliases }) => {
    return aliases.some((alias) => queryText.includes(normalizeLocationText(alias)))
  })

  return matched
    ? {
      category: matched.category,
      keyword: matched.keyword,
    }
    : {
      category: '',
      keyword: query.trim(),
    }
}

const normalizeSearchQuery = (query = '') => {
  let normalizedQuery = query.replace(/\s+/g, ' ').trim()
  const correctionReasons = []

  TYPO_CORRECTION_MAP.forEach(([from, to]) => {
    if (normalizedQuery.includes(from)) {
      normalizedQuery = normalizedQuery.split(from).join(to)
      correctionReasons.push(`${from} -> ${to}`)
    }
  })

  normalizedQuery = normalizedQuery
    .replace(/\s+/g, ' ')
    .trim()

  return {
    originalQuery: query,
    normalizedQuery,
    correctionApplied: normalizedQuery !== query.trim(),
    correctionReason: correctionReasons.length ? correctionReasons.join(', ') : null,
  }
}

const getTargetType = ({ targetQuery = '', categoryHint = '' }) => {
  const targetText = normalizeLocationText(targetQuery)

  if (categoryHint) return 'category'

  if (ABSTRACT_TARGET_KEYWORDS.some((keyword) => {
    return targetText.includes(normalizeLocationText(keyword))
  })) {
    return 'abstract'
  }

  return targetQuery.trim() ? 'unknown' : 'unknown'
}

const getRecommendationIntent = (query = '') => {
  const queryText = normalizeLocationText(query)
  const hasRestaurantKeyword = RESTAURANT_INTENT_KEYWORDS.some((keyword) => {
    return queryText.includes(normalizeLocationText(keyword))
  })
  const hasWorkCafeKeyword = WORK_CAFE_KEYWORDS.some((keyword) => {
    return queryText.includes(normalizeLocationText(keyword))
  })

  if (hasRestaurantKeyword) {
    return 'restaurant'
  }

  if (hasWorkCafeKeyword) {
    return 'work_cafe'
  }

  if (WAITING_PLACE_KEYWORDS.some((keyword) => queryText.includes(normalizeLocationText(keyword)))) {
    return 'waiting_place'
  }

  if (WALK_HEALING_KEYWORDS.some((keyword) => queryText.includes(normalizeLocationText(keyword)))) {
    return 'walk_healing'
  }

  if (SMOKING_INTENT_KEYWORDS.some((keyword) => queryText.includes(normalizeLocationText(keyword)))) {
    return 'smoking_area'
  }

  return ''
}

const getPreferredTagsForIntent = (intent = '') => {
  return INTENT_PREFERRED_TAGS[intent] || []
}

const getNegativeTagsForIntent = (intent = '') => {
  return INTENT_NEGATIVE_TAGS[intent] || []
}

const getKakaoKeywordCandidates = ({
  targetQuery,
  targetType,
  categoryKeyword,
  recommendationIntent,
}) => {
  const candidates = []

  if (categoryKeyword) {
    candidates.push(categoryKeyword)
  }

  if (recommendationIntent && INTENT_KAKAO_KEYWORD_CANDIDATES[recommendationIntent]) {
    candidates.push(...INTENT_KAKAO_KEYWORD_CANDIDATES[recommendationIntent])
  }

  if (targetType !== 'abstract' && targetQuery) {
    candidates.push(targetQuery)
  }

  if (!candidates.length && targetQuery) {
    candidates.push(targetQuery)
  }

  return [...new Set(candidates.map((candidate) => candidate.trim()).filter(Boolean))]
}

function toArray(value) {
  if (Array.isArray(value)) return value
  if (value === null || value === undefined) return []
  return [value]
}

const hasRequestedConditionKeyword = (text = '', rule) => {
  const normalizedText = normalizeLocationText(text)
  return toArray(rule?.keywords).some((keyword) => {
    return normalizedText.includes(normalizeLocationText(keyword))
  })
}

const cleanupConditionTargetText = (text = '', conditions = []) => {
  let cleaned = text

  toArray(conditions).forEach((condition) => {
    toArray(condition?.cleanupPatterns).forEach((pattern) => {
      cleaned = cleaned.replace(pattern, ' ')
    })
  })

  return cleaned
    .replace(/\s+/g, ' ')
    .replace(/^(?:에서|에|의)\s+/, '')
    .replace(/\s*(?:인|인 곳|인 장소|인 데)$/g, '')
    .replace(/\s*(?:있는|가능한|추천해줘|추천|찾아줘|찾아)$/g, '')
    .trim()
}

const isGenericConditionTarget = (target = '') => {
  const normalizedTarget = normalizeLocationText(target)
  if (!normalizedTarget) return true

  return GENERIC_CONDITION_TARGETS.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return normalizedTarget === normalizedKeyword || normalizedTarget.endsWith(normalizedKeyword)
  })
}

const extractRequestedConditions = (query = '', rawTargetQuery = '') => {
  const matchedConditions = REQUEST_CONDITION_RULES.filter((rule) => {
    return hasRequestedConditionKeyword(query, rule) || hasRequestedConditionKeyword(rawTargetQuery, rule)
  })

  if (!matchedConditions.length) {
    return {
      requestedConditions: [],
      targetQuery: rawTargetQuery,
      hasExplicitConditionTarget: false,
    }
  }

  const cleanedTargetQuery = cleanupConditionTargetText(rawTargetQuery, matchedConditions)
  const hasExplicitConditionTarget = Boolean(cleanedTargetQuery) && !isGenericConditionTarget(cleanedTargetQuery)

  return {
    requestedConditions: matchedConditions,
    targetQuery: hasExplicitConditionTarget ? cleanedTargetQuery : rawTargetQuery,
    hasExplicitConditionTarget,
  }
}

const getRequestedConditionEvidenceText = (place = {}) => {
  const tagDetails = toDisplayList(toArray(place.tagDetails || place.tag_details).map((tag) => tag?.name))
  return [
    place.name,
    place.category,
    place.rawCategory,
    ...toArray(place.tags).map((tag) => getTagName(tag)),
    ...toArray(place.suggestedTags || place.suggested_tags),
    ...toArray(place.verifiedTags || place.verified_tags),
    ...toArray(place.warningTags || place.warning_tags),
    ...toArray(place.matchedTags || place.matched_tags),
    ...toArray(place.matchedTagLabels || place.matched_tag_labels),
    ...tagDetails,
  ].filter(Boolean).join(' ')
}

const getRequestedConditionReview = (place = {}, requestedConditions = []) => {
  const evidenceText = normalizeLocationText(getRequestedConditionEvidenceText(place))
  const matchedLabels = []
  const missingLabels = []
  const safeConditions = toArray(requestedConditions).filter((condition) => {
    return condition && typeof condition === 'object'
  })

  safeConditions.forEach((condition) => {
    const evidenceKeywords = toArray(condition.evidenceKeywords)
    if (!evidenceKeywords.length) return

    const hasEvidence = evidenceKeywords.some((keyword) => {
      const evidenceKeyword = normalizeLocationText(keyword)
      return evidenceText.includes(evidenceKeyword)
    })

    if (hasEvidence) {
      const matchLabel = getTextValue(condition.matchLabel)
      if (matchLabel) matchedLabels.push(matchLabel)
      return
    }

    const missingLabel = getTextValue(condition.missingLabel)
    if (missingLabel) missingLabels.push(missingLabel)
  })

  return {
    matchedLabels: [...new Set(matchedLabels)],
    missingLabels: [...new Set(missingLabels)],
  }
}

const mergeRequestedConditionReview = (place = {}, requestedConditions = []) => {
  const safeConditions = toArray(requestedConditions).filter((condition) => {
    return condition && typeof condition === 'object'
  })
  if (!safeConditions.length) return place

  const review = getRequestedConditionReview(place, safeConditions)
  const missingLabels = [...new Set([
    ...toDisplayList(place.missingTagLabels || place.missing_tag_labels),
    ...review.missingLabels,
  ])]
  const matchedLabels = [...new Set([
    ...toDisplayList(place.matchedTagLabels || place.matched_tag_labels),
    ...review.matchedLabels,
  ])]
  const caution = missingLabels.length
    ? '요청한 조건은 현재 데이터로 확인되지 않았습니다. 방문 전 확인이 필요합니다.'
    : getTextValue(place.recommendationCaution || place.caution_message || place.caution)

  return {
    ...place,
    requestedConditionIds: safeConditions.map((condition) => condition.id).filter(Boolean),
    matchedTagLabels: matchedLabels,
    matched_tag_labels: matchedLabels,
    missingTagLabels: missingLabels,
    missing_tag_labels: missingLabels,
    recommendationCaution: caution,
    caution_message: caution,
  }
}

const getMainPlaceFallbackKeyword = (query = '') => {
  let keyword = query.trim()

  ANCILLARY_PLACE_KEYWORDS
    .slice()
    .sort((first, second) => second.length - first.length)
    .forEach((ancillaryKeyword) => {
      keyword = keyword.replace(new RegExp(`${ancillaryKeyword}$`), '').trim()
    })

  return keyword && keyword !== query.trim() ? keyword : ''
}

const getMainPlaceKeywordFromAncillaryName = (name = '') => {
  const placeName = name.trim()

  if (!placeName) return ''

  for (const ancillaryKeyword of ANCILLARY_PLACE_KEYWORDS.slice().sort((first, second) => second.length - first.length)) {
    const keywordIndex = placeName.indexOf(ancillaryKeyword)

    if (keywordIndex <= 0) continue

    const mainPlaceKeyword = placeName.slice(0, keywordIndex).trim()

    if (mainPlaceKeyword.length >= 2) {
      return mainPlaceKeyword
    }
  }

  return ''
}

const getMainPlaceFallbackKeywordsFromResults = (places = [], fallbackKeyword = '') => {
  const resultKeywords = places
    .map((place) => getMainPlaceKeywordFromAncillaryName(place.place_name || place.name || ''))
    .filter(Boolean)

  return [...new Set([fallbackKeyword, ...resultKeywords].filter(Boolean))]
}

const buildSearchPlan = (query) => {
  const correction = normalizeSearchQuery(query)
  const parsed = parseMapSearchInput(correction.normalizedQuery)
  const rawTargetQuery = parsed.targetQuery || parsed.targetKeyword || correction.normalizedQuery
  const conditionPlan = extractRequestedConditions(correction.normalizedQuery, rawTargetQuery)
  const targetQuery = conditionPlan.targetQuery || rawTargetQuery
  const categoryHint = getCategoryHint(targetQuery)
  const recommendationIntent = conditionPlan.hasExplicitConditionTarget
    ? getRecommendationIntent(targetQuery)
    : getRecommendationIntent(`${correction.normalizedQuery} ${targetQuery}`)
  const preferredTags = getPreferredTagsForIntent(recommendationIntent)
  const negativeTags = getNegativeTagsForIntent(recommendationIntent)
  const targetType = getTargetType({
    targetQuery,
    categoryHint: categoryHint.category,
  })
  const kakaoKeywordCandidates = getKakaoKeywordCandidates({
    targetQuery,
    targetType,
    categoryKeyword: categoryHint.keyword,
    recommendationIntent,
  })

  return {
    ...parsed,
    originalQuery: correction.originalQuery,
    normalizedQuery: correction.normalizedQuery,
    correctionApplied: correction.correctionApplied,
    correctionReason: correction.correctionReason,
    locationQuery: parsed.locationQuery || null,
    baseLocationQuery: parsed.baseLocationQuery || null,
    targetQuery,
    targetKeyword: kakaoKeywordCandidates[0] || categoryHint.keyword || targetQuery,
    targetType,
    categoryHint: categoryHint.category,
    categoryKeyword: categoryHint.keyword,
    recommendationIntent,
    requestedConditions: conditionPlan.requestedConditions,
    hasExplicitConditionTarget: conditionPlan.hasExplicitConditionTarget,
    preferredTags,
    negativeTags,
    isAncillaryIntent: ANCILLARY_INTENT_CATEGORIES.includes(categoryHint.category),
    kakaoKeywordCandidates,
    mainPlaceFallbackKeyword: getMainPlaceFallbackKeyword(targetQuery),
    confidence: categoryHint.category || recommendationIntent ? 'high' : (targetType === 'abstract' ? 'medium' : 'low'),
    fallbackReason: targetType === 'abstract' && !recommendationIntent
      ? '추상 장소 표현을 검색 가능한 후보 키워드로 해석했습니다.'
      : null,
  }
}

const getPlannerText = (value = '') => {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number') return String(value)
  if (!value || typeof value !== 'object') return ''

  return String(
    value.label ||
    value.name ||
    value.display_name ||
    value.displayName ||
    value.value ||
    value.text ||
    '',
  ).trim()
}

const getPlannerList = (value = []) => {
  const items = Array.isArray(value) ? value : (value ? [value] : [])
  return [...new Set(items.map(getPlannerText).filter((item) => item && item !== '[object Object]'))]
}

const getSearchPlanValue = (searchPlan = {}, ...keys) => {
  for (const key of keys) {
    const value = searchPlan?.[key]
    if (value === true || value === false) {
      return value
    }
    if (Array.isArray(value) ? value.length : getPlannerText(value)) {
      return value
    }
  }

  return ''
}

const getPlannerBoolean = (value, fallback = null) => {
  if (value === true || value === false) return value
  if (value === 'true') return true
  if (value === 'false') return false
  if (value === 1 || value === '1') return true
  if (value === 0 || value === '0') return false
  return fallback
}

const getConversationalPreviousContext = () => {
  if (!activeSearchPlan.value || !displayResults.value.length) {
    return null
  }

  return {
    query: mapSearchKeyword.value.trim() || searchKeyword.value.trim(),
    search_plan: {
      locationQuery: activeSearchPlan.value.locationQuery || '',
      baseLocationQuery: activeSearchPlan.value.baseLocationQuery || '',
      targetQuery: activeSearchPlan.value.targetQuery || '',
      scenario: activeSearchPlan.value.recommendationIntent || '',
      categoryHint: activeSearchPlan.value.categoryHint || '',
      menu_keywords: activeSearchPlan.value.menu_keywords || [],
      place_type_keywords: activeSearchPlan.value.place_type_keywords || [],
      requestedConditions: activeSearchPlan.value.requestedConditions || [],
    },
    result_count: displayResults.value.length,
  }
}

const resolveConversationalSearchPlan = async (keyword, previousContext = null) => {
  try {
    loadingMessage.value = '검색 의도 해석 중'
    const data = await buildConversationalSearchPlan({
      query: keyword,
      lat: mapCenter.value?.lat ?? null,
      lng: mapCenter.value?.lng ?? null,
      mapCenter: mapCenter.value || null,
      previousContext,
    })

    if (import.meta.env.DEV) {
      console.debug('[대화형 검색 해석]', {
        action: data?.action,
        scenario: data?.search_plan?.scenario,
        locationQuery: data?.search_plan?.locationQuery,
        targetQuery: data?.search_plan?.targetQuery,
        needsClarification: data?.needs_clarification,
        provider: data?.parser_provider,
      })
    }

    return data && typeof data === 'object' ? data : null
  } catch (error) {
    if (import.meta.env.DEV) {
      console.warn('[대화형 검색 해석] fallback to local planner')
    }
    return null
  }
}

const adaptConversationalSearchPlan = (conversationalPlan, originalQuery) => {
  const basePlan = buildSearchPlan(originalQuery)
  const plan = conversationalPlan?.search_plan || {}

  if (!plan || typeof plan !== 'object') {
    return basePlan
  }

  const locationQuery = getPlannerText(getSearchPlanValue(plan, 'locationQuery', 'location_query'))
  const hasExplicitLocation = getPlannerBoolean(
    getSearchPlanValue(plan, 'has_explicit_location'),
    Boolean(locationQuery),
  )
  const locationResolutionRequired = getPlannerBoolean(
    getSearchPlanValue(plan, 'location_resolution_required'),
    Boolean(locationQuery),
  )
  const shouldUseLocationQuery = Boolean(locationQuery && hasExplicitLocation && locationResolutionRequired)
  const targetQuery = getPlannerText(
    getSearchPlanValue(plan, 'targetQuery', 'target_query') ||
    basePlan.targetQuery ||
    originalQuery,
  )
  const categories = getPlannerList(plan.categories)
  const categoryHint = getPlannerText(getSearchPlanValue(plan, 'categoryHint', 'category_hint')) ||
    categories[0] ||
    basePlan.categoryHint
  const categoryKeyword = CATEGORY_KAKAO_KEYWORDS[categoryHint] || basePlan.categoryKeyword
  const recommendationIntent = getPlannerText(plan.scenario) || basePlan.recommendationIntent
  const menuKeywords = getPlannerList(plan.menu_keywords)
  const placeTypeKeywords = getPlannerList(plan.place_type_keywords)
  const requestedConditions = getPlannerList(
    getSearchPlanValue(plan, 'requestedConditions', 'requested_conditions') ||
    conversationalPlan.conditions ||
    basePlan.requestedConditions,
  )
  const preferredTags = getPlannerList(plan.preferred_tags).length
    ? getPlannerList(plan.preferred_tags)
    : basePlan.preferredTags
  const negativeTags = getPlannerList(plan.negative_tags).length
    ? getPlannerList(plan.negative_tags)
    : basePlan.negativeTags
  const targetType = getPlannerText(getSearchPlanValue(plan, 'targetType', 'target_type')) ||
    getTargetType({ targetQuery, categoryHint })
  const kakaoKeywordCandidates = getPlannerList(
    getSearchPlanValue(plan, 'kakaoKeywordCandidates', 'kakao_keyword_candidates'),
  )

  return {
    ...basePlan,
    originalQuery,
    normalizedQuery: originalQuery,
    locationQuery: shouldUseLocationQuery ? locationQuery : '',
    baseLocationQuery: shouldUseLocationQuery ? locationQuery : '',
    hasBaseLocation: shouldUseLocationQuery,
    hasExplicitLocation: shouldUseLocationQuery,
    locationResolutionRequired: shouldUseLocationQuery,
    explicitCurrentContext: !shouldUseLocationQuery,
    searchMode: shouldUseLocationQuery ? 'region_search' : 'current_context',
    baseKeyword: shouldUseLocationQuery ? locationQuery : '',
    targetQuery,
    targetKeyword: kakaoKeywordCandidates[0] || categoryKeyword || targetQuery,
    targetType,
    categoryHint,
    categoryKeyword,
    recommendationIntent,
    requestedConditions,
    preferredTags,
    negativeTags,
    kakaoKeywordCandidates: kakaoKeywordCandidates.length
      ? kakaoKeywordCandidates
      : getKakaoKeywordCandidates({
        targetQuery,
        targetType,
        categoryKeyword,
        recommendationIntent,
      }),
    menu_keywords: menuKeywords,
    place_type_keywords: placeTypeKeywords,
    conversationalSearchPlan: conversationalPlan,
    userIntentSummary: conversationalPlan?.user_intent_summary || '',
    executionPolicy: conversationalPlan?.execution_policy || {},
    confidence: conversationalPlan?.confidence ?? basePlan.confidence,
    fallbackReason: conversationalPlan?.fallback_reason || basePlan.fallbackReason,
    aiSearchPlanApplied: true,
  }
}

const CLARIFICATION_CURRENT_CONTEXT_ANSWERS = [
  '현재위치',
  '현재',
  '내위치',
  '내주변',
  '내근처',
  '근처',
  '주변',
  '여기',
  '기본위치',
  '지도중심',
]
const LOCATION_CHOICE_CLARIFICATION_MESSAGE = '현재 위치 기준으로 찾아볼까요, 아니면 원하는 지역이 있나요? 예: 현재 위치, 서면, 하단역, 광안리'
const CURRENT_CONTEXT_SEARCH_REQUEST_KEYWORDS = [
  '현재 위치',
  '현재위치',
  '내 주변',
  '내주변',
  '내 근처',
  '내근처',
  '이 근처',
  '이근처',
  '이 주변',
  '이주변',
  '근처',
  '주변',
]

const FOLLOW_UP_BLOCKED_HINTS = [
  '비트코인',
  '주식',
  '코인',
  '투자',
  '숙제',
  '과제',
  '파이썬',
  '불법',
  '위험',
  '해킹',
  '마약',
]

const isCurrentContextClarificationAnswer = (answer = '') => {
  const text = normalizeLocationText(answer)
  return CLARIFICATION_CURRENT_CONTEXT_ANSWERS.includes(text)
}

const hasExplicitCurrentContextSearchRequest = (query = '') => {
  const text = normalizeLocationText(query)
  return CURRENT_CONTEXT_SEARCH_REQUEST_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
}

const looksLikeLocationClarificationAnswer = (answer = '') => {
  const text = String(answer || '').trim()
  const normalizedText = normalizeLocationText(text)

  if (!text || normalizedText.length > 12) return false
  if (FOLLOW_UP_BLOCKED_HINTS.some((keyword) => normalizedText.includes(normalizeLocationText(keyword)))) return false
  if (isCurrentContextClarificationAnswer(text)) return true
  if (isRecommendationQueryText(text)) return false
  if (getRecommendationIntent(text)) return false

  return /^[가-힣A-Za-z0-9\s]+$/.test(text)
}

const buildClarificationFollowUpTargetText = (partialPlan = {}) => {
  const conditions = getPlannerList(partialPlan.conditions || partialPlan.requestedConditions || [])
  const scenario = getPlannerText(partialPlan.scenario)
  const targetQuery = getPlannerText(partialPlan.targetQuery || partialPlan.target_keyword) || '장소'
  const conditionText = normalizeLocationText(conditions.join(' '))

  if (scenario === 'work_cafe') {
    if (conditionText.includes('조용') || conditionText.includes('노트북')) {
      return '조용히 작업할 카페'
    }
    return '작업할 카페'
  }

  if (scenario === 'waiting_place') {
    if (conditionText.includes('비피하기') || conditionText.includes('실내') || conditionText.includes('앉을수있음')) {
      return '실내에 앉아 쉴 곳'
    }
    if (conditionText.includes('혼자') || conditionText.includes('조용') || conditionText.includes('붐비지')) {
      return '혼자 조용히 쉴 곳'
    }
  }

  if (scenario === 'walk_healing') {
    return '산책할 곳'
  }

  return targetQuery
}

const buildClarificationFollowUpPlan = (answer = '') => {
  const pending = pendingClarification.value
  if (!pending || pending.missing_field !== 'location') return null
  if (!looksLikeLocationClarificationAnswer(answer)) return null

  const locationAnswer = String(answer || '').trim()
  const useCurrentContext = isCurrentContextClarificationAnswer(locationAnswer)
  const partialPlan = {
    ...(pending.partial_search_plan || pending.plan?.search_plan || {}),
  }
  const conditions = getPlannerList(
    partialPlan.requestedConditions ||
    partialPlan.conditions ||
    pending.plan?.conditions ||
    [],
  )
  const targetQuery = getPlannerText(partialPlan.targetQuery || partialPlan.target_query) ||
    buildClarificationFollowUpTargetText(partialPlan)
  const scenario = getPlannerText(partialPlan.scenario) || ''
  const targetText = buildClarificationFollowUpTargetText({
    ...partialPlan,
    targetQuery,
    conditions,
  })
  const combinedMessage = useCurrentContext
    ? `현재 위치 기준으로 ${targetText}을 찾아볼게요.`
    : `${locationAnswer}에서 ${targetText}을 찾아볼게요.`
  const searchPlan = {
    ...partialPlan,
    locationQuery: useCurrentContext ? '' : locationAnswer,
    baseLocationQuery: useCurrentContext ? '' : locationAnswer,
    has_explicit_location: !useCurrentContext,
    location_resolution_required: !useCurrentContext,
    targetQuery,
    scenario,
    requestedConditions: conditions,
    conditions,
  }

  return {
    action: 'search',
    intent_type: 'place_recommendation',
    user_intent_summary: combinedMessage,
    message: combinedMessage,
    location: {
      text: useCurrentContext ? '' : locationAnswer,
      is_explicit: !useCurrentContext,
      fallback: useCurrentContext ? 'current_location' : '',
    },
    targets: [targetQuery].filter(Boolean),
    conditions,
    preferences: getPlannerList(partialPlan.preferred_tags || pending.plan?.preferences || []),
    avoid: getPlannerList(pending.plan?.avoid || []),
    search_plan: searchPlan,
    execution_policy: {
      run_search: true,
      preserve_explicit_location: !useCurrentContext,
      allow_kakao_fallback: true,
      allow_ai_web_search_auto: false,
      merge_ai_web_results: false,
    },
    needs_clarification: false,
    clarification_question: '',
    blocked_reason: '',
    out_of_scope_reason: '',
    confidence: pending.plan?.confidence ?? 76,
    fallback_reason: 'clarification_follow_up',
    parser_provider: pending.plan?.parser_provider || 'frontend',
    parser_fallback: true,
    clarification_follow_up: {
      original_query: pending.original_query || pending.query || '',
      answer: locationAnswer,
    },
  }
}

const appendClarificationFollowUpThread = (answer = '', message = '') => {
  const nextItems = [
    ...clarificationThread.value,
    { role: 'user', label: displayUserName.value, text: String(answer || '').trim() },
    { role: 'assistant', label: 'AI', text: String(message || '').trim() },
  ].filter((item) => item.text)

  clarificationThread.value = nextItems.slice(-4)
  followUpInput.value = ''
  clearTopSearchInputsForClarification()
}

const submitClarificationFollowUp = async () => {
  const answer = followUpInput.value.trim()

  if (!answer || isSearchingMap.value) return

  followUpInput.value = ''
  mapSearchKeyword.value = answer
  activeTab.value = 'search'
  activeResultView.value = 'results'
  isResultListCollapsed.value = false

  await nextTick()
  await performUnifiedMapSearch()
}

const isNaturalLanguageScenarioSearch = (searchPlan = {}, rawQuery = '') => {
  const scenario = getPlannerText(searchPlan.scenario)
  if (!['waiting_place', 'work_cafe', 'walk_healing'].includes(scenario)) return false

  const conditions = getPlannerList(
    searchPlan.requestedConditions ||
    searchPlan.requested_conditions ||
    searchPlan.conditions ||
    [],
  )

  return conditions.length > 0 || isRecommendationQueryText(rawQuery)
}

const shouldAskLocationChoiceBeforeSearch = ({
  conversationalPlan = null,
  rawQuery = '',
  allowImplicitCurrentContext = false,
} = {}) => {
  if (allowImplicitCurrentContext) return false
  if (!conversationalPlan || conversationalPlan.action !== 'search') return false
  if (hasExplicitCurrentContextSearchRequest(rawQuery)) return false

  const searchPlan = conversationalPlan.search_plan || {}
  const locationQuery = getPlannerText(getSearchPlanValue(searchPlan, 'locationQuery', 'location_query'))
  if (locationQuery) return false

  const hasExplicitLocation = getPlannerBoolean(
    getSearchPlanValue(searchPlan, 'has_explicit_location'),
    false,
  )
  if (hasExplicitLocation) return false

  return isNaturalLanguageScenarioSearch(searchPlan, rawQuery)
}

const makeLocationChoiceClarificationPlan = (conversationalPlan = {}, rawQuery = '') => {
  const searchPlan = conversationalPlan.search_plan && typeof conversationalPlan.search_plan === 'object'
    ? { ...conversationalPlan.search_plan }
    : {}
  const conditions = getPlannerList(
    searchPlan.requestedConditions ||
    searchPlan.requested_conditions ||
    searchPlan.conditions ||
    conversationalPlan.conditions ||
    [],
  )

  return {
    ...conversationalPlan,
    action: 'ask_clarification',
    message: LOCATION_CHOICE_CLARIFICATION_MESSAGE,
    needs_clarification: true,
    clarification_question: LOCATION_CHOICE_CLARIFICATION_MESSAGE,
    search_plan: {
      ...searchPlan,
      locationQuery: '',
      baseLocationQuery: '',
      has_explicit_location: false,
      location_resolution_required: false,
      requestedConditions: conditions,
      conditions,
    },
    conditions,
    execution_policy: {
      ...(conversationalPlan.execution_policy || {}),
      run_search: false,
      preserve_explicit_location: false,
    },
    fallback_reason: 'location_choice_required',
    location_choice_required: true,
    original_query: rawQuery,
  }
}

const enrichParsedSearchIntent = (parsed, originalKeyword) => {
  const targetQuery = parsed.targetQuery || parsed.targetKeyword || originalKeyword
  const categoryHint = getCategoryHint(targetQuery)
  const recommendationIntent = getRecommendationIntent(`${originalKeyword} ${targetQuery}`)

  return {
    ...parsed,
    targetKeyword: categoryHint.keyword || targetQuery,
    targetQuery,
    categoryHint: categoryHint.category,
    categoryKeyword: categoryHint.keyword,
    recommendationIntent,
    preferredTags: getPreferredTagsForIntent(recommendationIntent),
  }
}

const getUnifiedSearchMode = (keyword, parsedKeyword, { useMapBounds = false } = {}) => {
  if (useMapBounds) {
    return 'current_context'
  }

  if (parsedKeyword.explicitCurrentContext) {
    return parsedKeyword.recommendationIntent
      ? 'recommendation_query'
      : 'current_context'
  }

  if (parsedKeyword.searchMode === 'region_search') {
    return 'region_search'
  }

  if (parsedKeyword.searchMode === 'around_location') {
    return parsedKeyword.recommendationIntent
      ? 'recommendation_query'
      : 'around_location'
  }

  return parsedKeyword.recommendationIntent
    ? 'recommendation_query'
    : 'simple_keyword'
}

const runKakaoKeywordSearch = (placesService, keyword, options = {}) => {
  return new Promise((resolve, reject) => {
    placesService.keywordSearch(
      keyword,
      (data, status) => {
        if (status === window.kakao.maps.services.Status.OK) {
          resolve(data)
          return
        }

        if (status === window.kakao.maps.services.Status.ZERO_RESULT) {
          resolve([])
          return
        }

        reject(new Error('카카오 장소 검색 중 오류가 발생했습니다.'))
      },
      options,
    )
  })
}

const runKakaoKeywordSearchLimited = async (
  placesService,
  keyword,
  options = {},
  {
    maxPages = Math.ceil(MAX_SEARCH_RESULT_COUNT / SEARCH_SIZE_PER_PAGE),
  } = {},
) => {
  const allResults = []
  let page = 1

  while (allResults.length < MAX_SEARCH_RESULT_COUNT && page <= maxPages) {
    const pageResults = await runKakaoKeywordSearch(
      placesService,
      keyword,
      {
        ...options,
        size: SEARCH_SIZE_PER_PAGE,
        page,
      },
    )

    if (!pageResults.length) {
      break
    }

    allResults.push(...pageResults)

    if (pageResults.length < SEARCH_SIZE_PER_PAGE) {
      break
    }

    page += 1
  }

  return allResults.slice(0, MAX_SEARCH_RESULT_COUNT)
}

const runKakaoKeywordCandidateSearch = async (
  placesService,
  keywords = [],
  options = {},
  searchOptions = { maxPages: 1 },
) => {
  const results = []

  for (const keyword of keywords.filter(Boolean)) {
    const keywordResults = await runKakaoKeywordSearchLimited(
      placesService,
      keyword,
      options,
      searchOptions,
    )

    results.push(...keywordResults)

    if (results.length >= SEARCH_SIZE_PER_PAGE) {
      break
    }
  }

  return dedupeKakaoRawPlaces(results).slice(0, MAX_SEARCH_RESULT_COUNT)
}

const runKakaoAddressSearch = (geocoder, keyword) => {
  return new Promise((resolve, reject) => {
    geocoder.addressSearch(keyword, (data, status) => {
      if (status === window.kakao.maps.services.Status.OK) {
        resolve(data)
        return
      }

      if (status === window.kakao.maps.services.Status.ZERO_RESULT) {
        resolve([])
        return
      }

      reject(new Error('카카오 주소 검색 중 오류가 발생했습니다.'))
    })
  })
}

const normalizeKakaoRegionName = (name = '') => {
  return getTextValue(name)
    .replace(/특별자치시$/, '')
    .replace(/특별자치도$/, '')
    .replace(/특별시$/, '')
    .replace(/광역시$/, '')
    .replace(/자치도$/, '')
    .replace(/도$/, '')
}

const formatKakaoRegionHint = (address = {}) => {
  const region1 = normalizeKakaoRegionName(address.region_1depth_name)
  const region2 = getTextValue(address.region_2depth_name)

  if (region1 && region2) {
    return `${region1} ${region2}`.trim()
  }

  const addressNameParts = getTextValue(address.address_name).split(/\s+/).filter(Boolean)
  if (addressNameParts.length >= 2) {
    return `${normalizeKakaoRegionName(addressNameParts[0])} ${addressNameParts[1]}`.trim()
  }

  return region1 || region2 || ''
}

const reverseGeocodeLocationHint = (geocoder, center) => {
  if (!geocoder || !center || !Number.isFinite(Number(center.lat)) || !Number.isFinite(Number(center.lng))) {
    return Promise.resolve('')
  }

  return new Promise((resolve) => {
    geocoder.coord2Address(Number(center.lng), Number(center.lat), (data, status) => {
      if (status !== window.kakao.maps.services.Status.OK || !Array.isArray(data) || !data.length) {
        resolve('')
        return
      }

      const first = data[0] || {}
      const address = first.address || first.road_address || {}
      resolve(formatKakaoRegionHint(address))
    })
  })
}

const makeTag = (name, source) => {
  return {
    name,
    source,
  }
}

const makeKakaoResultTags = (place, savedTagData = {}) => {
  const tags = []

  const category = place.category_name || ''
  const placeName = place.place_name || ''

  if (category.includes('카페') || placeName.includes('카페')) {
    tags.push(makeTag('카페', 'category_rule'))
  }

  savedTagData.suggested_tags?.forEach((tagName) => {
    tags.push(makeTag(tagName, 'blog_search'))
  })

  savedTagData.verified_tags?.forEach((tagName) => {
    tags.push(makeTag(tagName, 'user_verified'))
  })

  savedTagData.warning_tags?.forEach((tagName) => {
    tags.push(makeTag(tagName, 'warning_tags'))
  })

  const uniqueTags = []
  const seen = new Set()

  tags.forEach((tag) => {
    const key = `${tag.name}-${tag.source}`

    if (!seen.has(key)) {
      seen.add(key)
      uniqueTags.push(tag)
    }
  })

  return uniqueTags
}

const getSavedTagNames = (savedTagData = {}) => {
  return [
    ...(savedTagData.suggested_tags || []),
    ...(savedTagData.verified_tags || []),
  ].filter(Boolean)
}

const hasSavedTagMatch = (savedTagData = {}) => {
  return Boolean(
    savedTagData.saved_place_id ||
    getSavedTagNames(savedTagData).length ||
    (savedTagData.warning_tags || []).length,
  )
}

const isTakeoutHeavyCafeCandidate = (place = {}) => {
  const placeText = normalizeLocationText(
    `${place.place_name || place.name || ''} ${place.category_name || place.category || ''}`,
  )

  return TAKEOUT_HEAVY_KEYWORDS.some((keyword) => {
    return placeText.includes(normalizeLocationText(keyword))
  })
}

const getPlaceTextForRule = (place = {}, extraTags = []) => {
  return normalizeLocationText([
    place.place_name,
    place.name,
    place.category_name,
    place.category,
    place.address_name,
    place.road_address_name,
    place.address,
    place.detailLocation,
    place.__fallbackQuery,
    place.fallbackQuery,
    place.kakaoFallbackQuery,
    ...extraTags,
  ].filter(Boolean).join(' '))
}

const getWaitingPlaceSuitability = (place = {}, savedTagData = {}) => {
  const text = getPlaceTextForRule(place, [
    ...(savedTagData.suggested_tags || []),
    ...(savedTagData.verified_tags || []),
    ...(savedTagData.warning_tags || []),
  ])

  const hasExcludedKeyword = WAITING_PLACE_EXCLUDE_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
  if (hasExcludedKeyword) {
    return {
      excluded: true,
      penalty: 140,
      bonus: 0,
      reason: 'limited_access_shelter',
    }
  }

  const hasPenaltyKeyword = WAITING_PLACE_PENALTY_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
  const hasPreferredKeyword = WAITING_PLACE_PREFERRED_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })

  return {
    excluded: false,
    penalty: hasPenaltyKeyword ? 65 : 0,
    bonus: hasPreferredKeyword ? 12 : 0,
    reason: hasPenaltyKeyword ? 'public_admin_penalty' : null,
  }
}

const getAncillaryPlaceAdjustment = ({
  place = {},
  query = '',
  categoryHint = '',
  recommendationIntent = '',
  isAncillaryIntent = false,
}) => {
  const text = getPlaceTextForRule(place)
  const queryText = normalizeLocationText(query)
  const hasAncillaryKeyword = ANCILLARY_PLACE_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
  const hasDestinationKeyword = DESTINATION_CATEGORY_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
  const isDestinationCategory = ['city_park', 'tourism', 'beach'].includes(place.rawCategory || place.categoryHint || place.category)
  const normalizedName = normalizeLocationText(place.place_name || place.name || '')
  const mainPlaceScore = (
    (!hasAncillaryKeyword && (hasDestinationKeyword || isDestinationCategory)) ||
    (queryText && normalizedName === queryText)
  )
    ? 18
    : 0
  const shouldPenalizeAncillary = hasAncillaryKeyword && !isAncillaryIntent
  const walkOrNightIntent = recommendationIntent === 'walk_healing'
  const ancillaryPlacePenalty = shouldPenalizeAncillary ? (walkOrNightIntent ? 38 : 26) : 0
  const intentMismatchPenalty = shouldPenalizeAncillary && walkOrNightIntent ? 12 : 0

  return {
    mainPlaceScore,
    ancillaryPlacePenalty,
    intentMismatchPenalty,
    isAncillaryPlace: hasAncillaryKeyword,
  }
}

const isAncillaryPlaceCandidate = (place = {}, searchContext = {}) => {
  return getAncillaryPlaceAdjustment({
    place,
    query: searchContext.query || '',
    categoryHint: searchContext.categoryHint || '',
    recommendationIntent: searchContext.recommendationIntent || '',
    isAncillaryIntent: searchContext.isAncillaryIntent || false,
  }).isAncillaryPlace
}

const shouldTryMainPlaceFallbackSearch = (places = [], searchContext = {}) => {
  if (!places.length || searchContext.isAncillaryIntent) return false

  const hasMainPlaceCandidate = places.some((place) => {
    return !isAncillaryPlaceCandidate(place, searchContext)
  })

  return !hasMainPlaceCandidate
}

const appendMainPlaceFallbackResults = async ({
  placesService,
  places = [],
  searchOptions = {},
  searchContext = {},
  fallbackKeyword = '',
}) => {
  if (!shouldTryMainPlaceFallbackSearch(places, searchContext)) {
    return places
  }

  const fallbackKeywords = getMainPlaceFallbackKeywordsFromResults(places, fallbackKeyword)

  if (!fallbackKeywords.length) {
    return places
  }

  const fallbackPlaces = await runKakaoKeywordCandidateSearch(
    placesService,
    fallbackKeywords,
    searchOptions,
    { maxPages: 1 },
  )

  if (!fallbackPlaces.length) {
    return places
  }

  return dedupeKakaoRawPlaces([...fallbackPlaces, ...places])
}

const getTagConfidenceScore = (savedTagData = {}) => {
  const confidenceValues = (savedTagData.tag_details || [])
    .map((tag) => Number(tag.confidence ?? tag.score ?? tag.weight))
    .filter((value) => Number.isFinite(value))

  if (!confidenceValues.length) {
    return savedTagData.verified_tags?.length ? 8 : 4
  }

  const average = confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length
  return average <= 1 ? Math.round(average * 10) : Math.min(10, Math.round(average / 10))
}

const getMatchedSavedTags = (savedTagData = {}, query = '', preferredTags = []) => {
  const queryText = normalizeLocationText(query)
  const tagNames = getSavedTagNames(savedTagData)
  const safePreferredTags = toArray(preferredTags)
  const preferredMatched = tagNames.filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return safePreferredTags.some((preferredTag) => {
      const preferredText = normalizeLocationText(preferredTag)
      return tagText && preferredText && (
        tagText.includes(preferredText) ||
        preferredText.includes(tagText)
      )
    })
  })
  const queryMatched = tagNames.filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return tagText && queryText && (queryText.includes(tagText) || tagText.includes(queryText))
  })
  const matched = [...new Set([...preferredMatched, ...queryMatched])]

  return matched.length ? matched : tagNames.slice(0, 4)
}

const calculateKakaoTagRecommendation = ({
  place,
  savedTagData = {},
  query = '',
  center = null,
  preferredTags = [],
  recommendationIntent = '',
}) => {
  if (!hasSavedTagMatch(savedTagData)) {
    return {
      recommendScore: null,
      matchedTags: [],
      recommendationReason: '',
      recommendationConfidence: '',
      preferredMatchCount: 0,
    }
  }

  const matchedTags = getMatchedSavedTags(savedTagData, query, preferredTags)
  const warningTags = savedTagData.warning_tags || []
  const waitingSuitability = recommendationIntent === 'waiting_place'
    ? getWaitingPlaceSuitability(place, savedTagData)
    : { excluded: false, penalty: 0, bonus: 0, reason: null }
  const rawScores = savedTagData.raw_scores || {}
  const preferredMatchCount = matchedTags.filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return toArray(preferredTags).some((preferredTag) => {
      const preferredText = normalizeLocationText(preferredTag)
      return tagText.includes(preferredText) || preferredText.includes(tagText)
    })
  }).length
  const distance = center
    ? getDistanceMetersBetweenPlaces(
      { lat: center.lat, lng: center.lng },
      { lat: Number(place.y), lng: Number(place.x) },
    )
    : Number(place.distance || 0)
  const distanceScore = distance
    ? Math.max(0, 15 - Math.min(15, Math.floor(distance / 250)))
    : 8
  const tagMatchScore = Math.min(34, matchedTags.length * 7 + preferredMatchCount * 8)
  const confidenceScore = getTagConfidenceScore(savedTagData)
  const verifiedScore = Math.min(12, (savedTagData.verified_tags || []).length * 4)
  const warningPenalty = Math.min(20, warningTags.length * 8)
  const qualityScore = Number(savedTagData.data_quality_score || 0)
  const qualityBonus = qualityScore ? Math.min(10, Math.round(qualityScore / 10)) : 0
  const rawScoreBonus = Number.isFinite(Number(rawScores.recommendation_ready_score))
    ? Math.min(12, Math.round(Number(rawScores.recommendation_ready_score) / 8))
    : 0
  const weakWorkCafePenalty = preferredTags.length && preferredMatchCount === 0 ? 18 : 0
  const recommendScore = Math.max(
    0,
    Math.min(
      100,
      42 +
        tagMatchScore +
        distanceScore +
        confidenceScore +
        verifiedScore +
        qualityBonus +
        rawScoreBonus -
        warningPenalty -
        weakWorkCafePenalty +
        waitingSuitability.bonus -
        waitingSuitability.penalty,
    ),
  )

  const reasonParts = []
  if (preferredMatchCount > 0) {
    reasonParts.push(`${matchedTags.slice(0, 3).join(', ')} 태그가 작업 목적과 일치합니다.`)
  } else if (matchedTags.length) {
    reasonParts.push(`저장된 태그(${matchedTags.slice(0, 3).join(', ')})가 검색 조건과 연결됩니다.`)
  } else {
    reasonParts.push('DB에 저장된 장소 태그가 확인된 카카오 결과입니다.')
  }
  if (preferredTags.length && preferredMatchCount === 0) {
    reasonParts.push('작업 선호 태그와 직접 일치하는 정보는 부족해 후순위로 반영했습니다.')
  }
  if ((savedTagData.verified_tags || []).length) {
    reasonParts.push('검증 태그가 포함되어 신뢰도를 높였습니다.')
  }
  if (distance && distance <= 1000) {
    reasonParts.push('기준 위치에서 가까운 카페입니다.')
  }
  if (warningTags.length) {
    reasonParts.push(`주의 태그(${warningTags.join(', ')})가 있어 점수를 낮췄습니다.`)
  }
  if (waitingSuitability.reason) {
    reasonParts.push('일반적인 잠깐 휴식 목적과는 맞지 않을 수 있어 후순위로 반영했습니다.')
  }
  reasonParts.push('세부 태그는 후보 정보이므로 실제 이용 가능 여부는 확인이 필요합니다.')

  let recommendationConfidence = 'medium'
  if ((savedTagData.verified_tags || []).length && confidenceScore >= 7 && !warningTags.length && (!preferredTags.length || preferredMatchCount > 0)) {
    recommendationConfidence = 'high'
  } else if (warningTags.length || waitingSuitability.reason || confidenceScore <= 3 || (preferredTags.length && preferredMatchCount === 0)) {
    recommendationConfidence = 'low'
  }

  return {
    recommendScore,
    matchedTags,
    recommendationReason: reasonParts.join(' '),
    recommendationConfidence,
    preferredMatchCount,
    waitingPlacePenalty: waitingSuitability.penalty,
    waitingPlaceExcluded: waitingSuitability.excluded,
    waitingPlacePenaltyReason: waitingSuitability.reason,
  }
}

const getTagName = (tag) => {
  if (typeof tag === 'string') {
    return tag
  }

  return tag.name
}

const getTagClass = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source

  if (source === 'blog_search') {
    return 'tag-blog'
  }

  if (source === 'user_verified') {
    return 'tag-user'
  }

  if (source === 'warning_tags') {
    return 'tag-warning'
  }

  return 'tag-default'
}

const getTagSourceText = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source

  if (source === 'external_data') {
    return 'DB'
  }

  if (source === 'field_rule') {
    return '필드'
  }

  if (source === 'keyword_rule') {
    return '키워드'
  }

  if (source === 'checked') {
    return '검수'
  }

  if (source === 'blog_search') {
    return '블로그'
  }

  if (source === 'user_verified') {
    return '사용자검증'
  }

  if (source === 'warning_tags') {
    return '주의'
  }

  return '기본'
}

const getTagSortOrder = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source

  if (source === 'blog_search') {
    return 1
  }

  if (source === 'user_verified') {
    return 2
  }

  if (source === 'warning_tags') {
    return 3
  }

  if (source === 'category_rule') {
    return 99
  }

  return 50
}

const getSortedTags = (tags = []) => {
  return [...tags].sort((a, b) => {
    return getTagSortOrder(a) - getTagSortOrder(b)
  })
}

const normalizeLabelValue = (item) => {
  if (typeof item === 'string') return item.trim()
  if (typeof item === 'number' && Number.isFinite(item)) return String(item)
  if (!item || typeof item !== 'object') return ''

  const labelKeys = ['label', 'name', 'display_name', 'displayName', 'value', 'text']
  for (const key of labelKeys) {
    const label = normalizeLabelValue(item[key])
    if (label) return label
  }

  return ''
}

const toDisplayList = (value) => {
  if (!Array.isArray(value)) {
    return []
  }

  return [...new Set(
    value
      .map(normalizeLabelValue)
      .filter((item) => item && item !== '[object Object]'),
  )]
}

const getTextValue = (value) => String(value || '').trim()

const getScenarioDisplayLabel = (scenario) => {
  const value = getTextValue(scenario)
  return SCENARIO_DISPLAY_LABELS[value] || value
}

const getRecommendationMatchedLabels = (place) => {
  const labels = toDisplayList(place?.matchedTagLabels || place?.matched_tag_labels)
  const baseLabels = labels.length ? labels : toDisplayList(place?.matchedTags || place?.matched_tags)
  const menuLabels = getMenuDisplayMatchedLabels(place)

  return [...new Set([...baseLabels, ...menuLabels])]
}

const getRecommendationMissingLabels = (place) => {
  return toDisplayList(place?.missingTagLabels || place?.missing_tag_labels)
}

const getRecommendationMetaText = (place) => {
  const metaParts = [
    getTextValue(place?.recommendationSourceLabel || place?.source_label),
    getTextValue(place?.recommendationConfidenceLabel || place?.confidence_label),
  ].filter(Boolean)

  return metaParts.join(' · ')
}

const getRecommendationFallbackText = (place) => {
  if (isLowConfidenceWalkHealingFallback(place)) {
    return '낮은 신뢰도 후보'
  }

  return getTextValue(place?.recommendationFallbackLabel || place?.fallback_label)
}

const getRecommendationFallbackDescription = (place) => {
  return getTextValue(place?.recommendationFallbackDescription || place?.fallback_description)
}

const getRecommendationCaution = (place) => {
  return getTextValue(place?.recommendationCaution || place?.caution_message || place?.caution)
}

const getPersonalizationBoost = (place) => {
  const boost = Number(place?.personalizationBoost ?? place?.personalization_boost ?? 0)

  return Number.isFinite(boost) ? boost : 0
}

const getPersonalizationReasons = (place) => {
  return toDisplayList(place?.personalizationReasons || place?.personalization_reasons)
}

const getPersonalizationBoostText = (place) => {
  const boost = getPersonalizationBoost(place)

  if (boost <= 0) return ''
  return `개인화 +${boost.toFixed(1)}`
}

watch(displayResults, (results) => {
  if (!IS_DEV || !Array.isArray(results) || !results.length) return

  const boosts = results
    .map((place) => getPersonalizationBoost(place))
    .filter((boost) => boost > 0)

  if (!boosts.length) return

  console.debug('[개인화 추천]', {
    personalizedCount: boosts.length,
    maxBoost: Math.max(...boosts),
  })
})

const getRecommendationPreviewLabels = (labels = [], limit = 3) => {
  return toDisplayList(labels).slice(0, limit)
}

const normalizeSearchText = (text = '') => {
  return text.toLowerCase().replace(/\s+/g, '')
}

const isCafeSearchKeyword = (keyword) => {
  const normalizedKeyword = normalizeSearchText(keyword)

  return CAFE_SEARCH_KEYWORDS.some((word) => {
    return normalizedKeyword.includes(normalizeSearchText(word))
  })
}

const isInfraSearchKeyword = (keyword) => {
  const normalizedKeyword = normalizeSearchText(keyword)

  return INFRA_SEARCH_KEYWORDS.some((word) => {
    return normalizedKeyword.includes(normalizeSearchText(word))
  })
}

const shouldAppendDbPlaces = (keyword) => {
  return !isCafeSearchKeyword(keyword) && isInfraSearchKeyword(keyword)
}

const normalizePlaceName = (name = '') => {
  return String(name || '')
    .toLowerCase()
    .replace(/\([^)]*\)/g, '')
    .replace(/\[[^\]]*\]/g, '')
    .replace(/본점$/g, '')
    .replace(/지점$/g, '')
    .replace(/\s+[가-힣a-z0-9]{1,8}점$/g, '')
    .replace(/점$/g, '')
    .replace(/\s+/g, '')
    .replace(/[^0-9a-z가-힣]/g, '')
}

const getPlaceNameSimilarity = (firstName, secondName) => {
  const first = normalizePlaceName(firstName)
  const second = normalizePlaceName(secondName)

  if (!first || !second) return 0
  if (first === second) return 1
  if (first.includes(second) || second.includes(first)) return 0.92

  const makeBigrams = (text) => {
    if (text.length <= 1) return [text]

    return Array.from({ length: text.length - 1 }, (_, index) => text.slice(index, index + 2))
  }
  const firstBigrams = makeBigrams(first)
  const secondBigrams = makeBigrams(second)
  const secondCounts = secondBigrams.reduce((counts, bigram) => {
    counts[bigram] = (counts[bigram] || 0) + 1
    return counts
  }, {})
  let intersection = 0

  firstBigrams.forEach((bigram) => {
    if (!secondCounts[bigram]) return

    intersection += 1
    secondCounts[bigram] -= 1
  })

  return (2 * intersection) / (firstBigrams.length + secondBigrams.length)
}

const isSimilarPlaceName = (firstName, secondName) => {
  return getPlaceNameSimilarity(firstName, secondName) >= 0.72
}

const getDistanceMetersBetweenPlaces = (firstPlace, secondPlace) => {
  const lat1 = Number(firstPlace.lat)
  const lng1 = Number(firstPlace.lng)
  const lat2 = Number(secondPlace.lat)
  const lng2 = Number(secondPlace.lng)

  if ([lat1, lng1, lat2, lng2].some((value) => Number.isNaN(value))) {
    return Number.POSITIVE_INFINITY
  }

  const radius = 6371000
  const toRadians = (degree) => degree * (Math.PI / 180)
  const deltaLat = toRadians(lat2 - lat1)
  const deltaLng = toRadians(lng2 - lng1)

  const a =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) *
    Math.cos(toRadians(lat2)) *
    Math.sin(deltaLng / 2) ** 2

  return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

const getTagKey = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source
  return `${getTagName(tag)}-${source}`
}

const mergeTags = (firstTags = [], secondTags = []) => {
  const mergedTags = []
  const seen = new Set()

    ;[...firstTags, ...secondTags].forEach((tag) => {
      const key = getTagKey(tag)

      if (seen.has(key)) {
        return
      }

      seen.add(key)
      mergedTags.push(tag)
    })

  return mergedTags
}

const getAddressOverlapMatched = (firstAddress = '', secondAddress = '') => {
  const first = normalizePlaceName(firstAddress)
  const second = normalizePlaceName(secondAddress)

  if (!first || !second) return false

  return first.includes(second.slice(0, 8)) || second.includes(first.slice(0, 8))
}

const getDbKakaoMergeDecision = (kakaoPlace, dbPlace) => {
  const idMatched = Boolean(
    dbPlace.source === 'kakao_local' &&
    dbPlace.externalId &&
    kakaoPlace.kakaoPlaceId &&
    String(dbPlace.externalId) === String(kakaoPlace.kakaoPlaceId),
  )
  const nameSimilarity = getPlaceNameSimilarity(kakaoPlace.name, dbPlace.name)
  const nameMatched = nameSimilarity >= 0.72
  const distanceMeters = getDistanceMetersBetweenPlaces(kakaoPlace, dbPlace)
  const distanceMatched = distanceMeters <= 30
  const addressMatched = getAddressOverlapMatched(kakaoPlace.address, dbPlace.address)

  if (idMatched) {
    return {
      matched: true,
      reason: 'external_id_matched',
      nameSimilarity,
      distanceMeters,
      addressMatched,
    }
  }

  if (nameMatched && distanceMatched) {
    return {
      matched: true,
      reason: 'name_and_distance_matched',
      nameSimilarity,
      distanceMeters,
      addressMatched,
    }
  }

  if (nameMatched && addressMatched) {
    return {
      matched: true,
      reason: 'name_and_address_matched',
      nameSimilarity,
      distanceMeters,
      addressMatched,
    }
  }

  const reason = !nameMatched
    ? 'name_not_similar'
    : (!distanceMatched && !addressMatched ? 'distance_and_address_not_matched' : 'unknown')

  return {
    matched: false,
    reason,
    nameSimilarity,
    distanceMeters,
    addressMatched,
  }
}

const isDuplicateDbPlace = (kakaoPlace, dbPlace) => {
  return getDbKakaoMergeDecision(kakaoPlace, dbPlace).matched
}

const getBestKakaoMergeCandidate = (kakaoResults, dbPlace) => {
  let bestCandidate = null

  kakaoResults.forEach((kakaoPlace) => {
    const decision = getDbKakaoMergeDecision(kakaoPlace, dbPlace)

    if (decision.matched) {
      const score =
        (decision.reason === 'external_id_matched' ? 100 : 0) +
        (decision.nameSimilarity || 0) * 20 +
        (Number.isFinite(decision.distanceMeters) ? Math.max(0, 30 - decision.distanceMeters) : 0) +
        (decision.addressMatched ? 10 : 0)

      if (!bestCandidate || score > bestCandidate.score) {
        bestCandidate = {
          kakaoPlace,
          decision,
          score,
        }
      }

      return
    }
  })

  return bestCandidate
}

const mergeDbDataIntoKakaoPlace = (kakaoPlace, dbPlace) => {
  const hasRecommendationData =
    dbPlace?.sourceLabel === 'DB추천' || dbPlace?.tagSource === 'DB 추천 결과'

  return {
    ...kakaoPlace,
    savedPlaceId: kakaoPlace.savedPlaceId || dbPlace.savedPlaceId,
    source: dbPlace.source || kakaoPlace.source,
    sourceName: dbPlace.sourceName || kakaoPlace.sourceName,
    externalId: kakaoPlace.externalId || dbPlace.externalId,
    kakaoPlaceId:
      kakaoPlace.kakaoPlaceId ||
      dbPlace.kakaoPlaceId ||
      (
        hasKakaoSourceHint(dbPlace) && isKakaoPlaceId(dbPlace.externalId)
          ? dbPlace.externalId
          : null
      ),
    placeUrl: kakaoPlace.placeUrl || dbPlace.placeUrl,
    kakaoPlaceUrl: kakaoPlace.kakaoPlaceUrl || dbPlace.kakaoPlaceUrl || '',
    kakaoUrl: kakaoPlace.kakaoUrl || dbPlace.kakaoUrl || '',
    detailUrl: kakaoPlace.detailUrl || dbPlace.detailUrl || '',
    navigationUrl: kakaoPlace.navigationUrl || dbPlace.navigationUrl,
    tags: mergeTags(kakaoPlace.tags, dbPlace.tags),
    tagSource: hasRecommendationData
      ? `${kakaoPlace.tagSource} + DB 추천 데이터`
      : `${kakaoPlace.tagSource} + DB 저장 데이터`,
    sourceLabel: '카카오+DB',
    dataQualityStatus: kakaoPlace.dataQualityStatus || dbPlace.dataQualityStatus,
    dataQualityScore: kakaoPlace.dataQualityScore ?? dbPlace.dataQualityScore,
    recommendScore: dbPlace.recommendScore ?? kakaoPlace.recommendScore,
    recommendationReason:
      dbPlace.recommendationReason || kakaoPlace.recommendationReason,
    matchedTags: dbPlace.matchedTags?.length
      ? dbPlace.matchedTags
      : (kakaoPlace.matchedTags || []),
    matchedTagLabels: dbPlace.matchedTagLabels?.length
      ? dbPlace.matchedTagLabels
      : (kakaoPlace.matchedTagLabels || []),
    missingTagLabels: dbPlace.missingTagLabels?.length
      ? dbPlace.missingTagLabels
      : (kakaoPlace.missingTagLabels || []),
    recommendationSourceLabel:
      dbPlace.recommendationSourceLabel || kakaoPlace.recommendationSourceLabel || '',
    recommendationConfidenceLabel:
      dbPlace.recommendationConfidenceLabel || kakaoPlace.recommendationConfidenceLabel || '',
    recommendationFallbackLabel:
      dbPlace.recommendationFallbackLabel || kakaoPlace.recommendationFallbackLabel || '',
    recommendationFallbackDescription:
      dbPlace.recommendationFallbackDescription || kakaoPlace.recommendationFallbackDescription || '',
    recommendationCaution:
      dbPlace.recommendationCaution || kakaoPlace.recommendationCaution || '',
    suggestedTags: dbPlace.suggestedTags?.length
      ? dbPlace.suggestedTags
      : (kakaoPlace.suggestedTags || []),
    verifiedTags: dbPlace.verifiedTags?.length
      ? dbPlace.verifiedTags
      : (kakaoPlace.verifiedTags || []),
    warningTags: dbPlace.warningTags?.length
      ? dbPlace.warningTags
      : (kakaoPlace.warningTags || []),
    tagDetails: dbPlace.tagDetails?.length
      ? dbPlace.tagDetails
      : (kakaoPlace.tagDetails || []),
    matchLevel: dbPlace.matchLevel || kakaoPlace.matchLevel,
    recommendationConfidence:
      dbPlace.recommendationConfidence || kakaoPlace.recommendationConfidence,
  }
}

const dedupeSearchResults = (kakaoResults, dbPlaces) => {
  const mergedKakaoResults = [...kakaoResults]
  const additionalDbPlaces = []

  dbPlaces.forEach((dbPlace) => {
    const bestCandidate = getBestKakaoMergeCandidate(mergedKakaoResults, dbPlace)

    if (!bestCandidate) {
      additionalDbPlaces.push(dbPlace)
      return
    }

    const duplicateIndex = mergedKakaoResults.findIndex((kakaoPlace) => {
      return kakaoPlace.id === bestCandidate.kakaoPlace.id
    })

    if (duplicateIndex === -1) {
      additionalDbPlaces.push(dbPlace)
      return
    }

    mergedKakaoResults[duplicateIndex] = mergeDbDataIntoKakaoPlace(
      mergedKakaoResults[duplicateIndex],
      dbPlace,
    )
  })

  return [...mergedKakaoResults, ...additionalDbPlaces]
}

const mergeKakaoFallbackIntoDbResults = (dbResults = [], kakaoFallbackResults = []) => {
  const finalResults = [...dbResults]

  kakaoFallbackResults.forEach((kakaoPlace) => {
    const duplicateExists = finalResults.some((dbPlace) => {
      return isDuplicateDbPlace(kakaoPlace, dbPlace)
    })

    if (!duplicateExists) {
      finalResults.push(kakaoPlace)
    }
  })

  return finalResults
}

const logSearchResultMerge = async ({
  dbResults = [],
  kakaoFallbackResults = [],
  finalResults = [],
} = {}) => {
  if (!import.meta.env.DEV) return

  await nextTick()
  console.debug('[검색 결과 병합]', {
    dbCount: dbResults.length,
    kakaoFallbackCount: kakaoFallbackResults.length,
    finalCount: finalResults.length,
    displayedCount: searchedPlaces.value.length,
    status: searchResultStatus.value,
  })
}

const getPlaceSourceText = (place) => {
  return place.sourceLabel || '장소'
}

const getPlaceSourceClass = (place) => {
  if (place.searchSource === 'local_db') {
    return 'source-db'
  }

  if (place.searchSource === 'kakao') {
    return 'source-kakao'
  }

  return 'source-base'
}

const isDbPlace = (place) => {
  return place?.searchSource === 'local_db'
}

const KAKAO_PLACE_ID_PATTERN = /^\d{5,20}$/

const normalizeKakaoDetailUrl = (url) => {
  const cleanedUrl = getTextValue(url)

  if (!cleanedUrl) {
    return ''
  }

  const candidateUrl = cleanedUrl.startsWith('place.map.kakao.com/')
    ? `https://${cleanedUrl}`
    : cleanedUrl

  try {
    const parsedUrl = new URL(candidateUrl)
    const [placeId] = parsedUrl.pathname.split('/').filter(Boolean)

    if (
      parsedUrl.hostname !== 'place.map.kakao.com' ||
      !KAKAO_PLACE_ID_PATTERN.test(placeId)
    ) {
      return ''
    }

    return `https://place.map.kakao.com/${placeId}`
  } catch (error) {
    return ''
  }
}

const isKakaoPlaceId = (value) => {
  return KAKAO_PLACE_ID_PATTERN.test(getTextValue(value))
}

const hasKakaoSourceHint = (place) => {
  const sourceText = [
    place?.source,
    place?.rawSource,
    place?.sourceName,
    place?.source_name,
  ]
    .map((value) => getTextValue(value).toLowerCase())
    .join(' ')

  return sourceText.includes('kakao')
}

const getKakaoDetailLookupKey = (place) => {
  if (!place) {
    return ''
  }

  const stableId = place.id || place.savedPlaceId || place.externalId || place.external_id
  if (stableId) {
    return String(stableId)
  }

  return [
    getTextValue(place.name),
    getTextValue(place.lat),
    getTextValue(place.lng),
  ].join(':')
}

const getDirectKakaoDetailUrl = (place) => {
  const explicitUrl = [
    place?.kakaoPlaceUrl,
    place?.kakao_place_url,
    place?.kakaoUrl,
    place?.kakao_url,
    place?.placeUrl,
    place?.place_url,
    place?.detailUrl,
    place?.detail_url,
  ]
    .map(normalizeKakaoDetailUrl)
    .find(Boolean)

  if (explicitUrl) {
    return explicitUrl
  }

  const kakaoPlaceId = getTextValue(place?.kakaoPlaceId || place?.kakao_place_id)
  if (isKakaoPlaceId(kakaoPlaceId)) {
    return `https://place.map.kakao.com/${kakaoPlaceId}`
  }

  const externalId = getTextValue(place?.externalId || place?.external_id)
  if (hasKakaoSourceHint(place) && isKakaoPlaceId(externalId)) {
    return `https://place.map.kakao.com/${externalId}`
  }

  return ''
}

const getResolvedKakaoDetailUrl = (place) => {
  const lookupKey = getKakaoDetailLookupKey(place)
  return lookupKey ? resolvedKakaoDetailUrls.value[lookupKey] || '' : ''
}

const getKakaoDetailLookupStatus = (place) => {
  const lookupKey = getKakaoDetailLookupKey(place)
  return lookupKey ? kakaoDetailLookupStatus.value[lookupKey] || 'idle' : 'idle'
}

const getKakaoDetailUrl = (place) => {
  return getDirectKakaoDetailUrl(place) || getResolvedKakaoDetailUrl(place)
}

const debugKakaoDetailLog = (label, payload = {}) => {
  if (!import.meta.env.DEV) {
    return
  }

  console.debug(label, payload)
}

const getKakaoDetailPlaceCoordinates = (place) => {
  const lat = Number(place?.lat ?? place?.y)
  const lng = Number(place?.lng ?? place?.x)

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return null
  }

  return { lat, lng }
}

const getKakaoDetailCandidateCoordinates = (candidate) => {
  const lat = Number(candidate?.y ?? candidate?.lat)
  const lng = Number(candidate?.x ?? candidate?.lng)

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return null
  }

  return { lat, lng }
}

const escapeKakaoDetailRegExp = (value) => {
  return getTextValue(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const removeKakaoDetailBracketContent = (name = '') => {
  return getTextValue(name)
    .replace(/\([^)]*\)/g, ' ')
    .replace(/\[[^\]]*\]/g, ' ')
    .replace(/\{[^}]*\}/g, ' ')
}

const removeKakaoDetailBracketCharacters = (name = '') => {
  return getTextValue(name).replace(/[()[\]{}]/g, ' ')
}

const replaceKakaoDetailSpecialCharacters = (name = '') => {
  return getTextValue(name).replace(/[^\p{L}\p{N}]+/gu, ' ')
}

const normalizeKakaoDetailWhitespace = (name = '') => {
  return getTextValue(name).replace(/\s+/g, ' ').trim()
}

const insertKakaoDetailNameBoundaries = (name = '') => {
  let spacedName = normalizeKakaoDetailWhitespace(name)

  KAKAO_DETAIL_SUFFIX_BOUNDARY_WORDS.forEach((word) => {
    const escapedWord = escapeKakaoDetailRegExp(word)

    if (!escapedWord) {
      return
    }

    spacedName = spacedName.replace(new RegExp(`(${escapedWord})(?=\\S)`, 'g'), '$1 ')
  })

  return normalizeKakaoDetailWhitespace(spacedName)
}

const normalizeKakaoMatchName = (name = '') => {
  return replaceKakaoDetailSpecialCharacters(removeKakaoDetailBracketContent(name))
    .toLowerCase()
    .replace(/\s+/g, '')
}

const normalizeKakaoLookupQueryKey = (query = '') => {
  return replaceKakaoDetailSpecialCharacters(query)
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

const isGenericKakaoMatchName = (name = '') => {
  const normalizedName = normalizeKakaoMatchName(name)

  return !normalizedName || normalizedName.length <= 2 || KAKAO_DETAIL_GENERIC_NAMES.has(normalizedName)
}

const getUniqueKakaoDetailValues = (values = [], getKey = normalizeKakaoLookupQueryKey) => {
  const seen = new Set()
  const uniqueValues = []

  values.forEach((value) => {
    const textValue = normalizeKakaoDetailWhitespace(value)
    const key = getKey(textValue)

    if (!textValue || !key || seen.has(key)) {
      return
    }

    seen.add(key)
    uniqueValues.push(textValue)
  })

  return uniqueValues
}

const buildKakaoDetailLookupQueries = (place) => {
  const placeName = getTextValue(place?.name)

  if (!placeName) {
    return []
  }

  const bracketCharactersRemoved = removeKakaoDetailBracketCharacters(placeName)
  const bracketContentRemoved = removeKakaoDetailBracketContent(placeName)
  const specialCharactersReplaced = replaceKakaoDetailSpecialCharacters(placeName)
  const queryCandidates = [
    placeName,
    bracketCharactersRemoved,
    bracketContentRemoved,
    specialCharactersReplaced,
    insertKakaoDetailNameBoundaries(placeName),
    insertKakaoDetailNameBoundaries(bracketCharactersRemoved),
    insertKakaoDetailNameBoundaries(bracketContentRemoved),
    insertKakaoDetailNameBoundaries(specialCharactersReplaced),
  ]

  return getUniqueKakaoDetailValues(queryCandidates)
    .filter((query) => !isGenericKakaoMatchName(query))
    .slice(0, KAKAO_DETAIL_MAX_QUERY_COUNT)
}

const getKakaoMatchNameVariants = (name = '') => {
  const sourceName = getTextValue(name)

  if (!sourceName) {
    return []
  }

  return getUniqueKakaoDetailValues(
    [
      sourceName,
      removeKakaoDetailBracketCharacters(sourceName),
      removeKakaoDetailBracketContent(sourceName),
      replaceKakaoDetailSpecialCharacters(sourceName),
      insertKakaoDetailNameBoundaries(sourceName),
      insertKakaoDetailNameBoundaries(removeKakaoDetailBracketCharacters(sourceName)),
      insertKakaoDetailNameBoundaries(removeKakaoDetailBracketContent(sourceName)),
    ],
    normalizeKakaoMatchName,
  )
    .map(normalizeKakaoMatchName)
    .filter(Boolean)
}

const getKakaoNormalizedNameSimilarity = (firstName = '', secondName = '') => {
  if (!firstName || !secondName) {
    return 0
  }

  if (firstName === secondName) {
    return 1
  }

  if (firstName.includes(secondName) || secondName.includes(firstName)) {
    return 0.92
  }

  const makeBigrams = (text) => {
    if (text.length <= 1) {
      return [text]
    }

    return Array.from({ length: text.length - 1 }, (_, index) => text.slice(index, index + 2))
  }
  const firstBigrams = makeBigrams(firstName)
  const secondBigrams = makeBigrams(secondName)
  const secondCounts = secondBigrams.reduce((counts, bigram) => {
    counts[bigram] = (counts[bigram] || 0) + 1
    return counts
  }, {})
  let intersection = 0

  firstBigrams.forEach((bigram) => {
    if (!secondCounts[bigram]) {
      return
    }

    intersection += 1
    secondCounts[bigram] -= 1
  })

  return (2 * intersection) / (firstBigrams.length + secondBigrams.length)
}

const getKakaoDetailNameEvaluation = (placeName, candidateName) => {
  const placeVariants = getKakaoMatchNameVariants(placeName)
  const candidateVariants = getKakaoMatchNameVariants(candidateName)
  const hasGenericName = isGenericKakaoMatchName(placeName) || isGenericKakaoMatchName(candidateName)
  let exactMatched = false
  let containmentMatched = false
  let bestSimilarity = 0

  placeVariants.forEach((placeVariant) => {
    candidateVariants.forEach((candidateVariant) => {
      if (placeVariant === candidateVariant && placeVariant.length >= 3) {
        exactMatched = true
      }

      const shorterLength = Math.min(placeVariant.length, candidateVariant.length)
      if (
        shorterLength >= 4 &&
        !hasGenericName &&
        (placeVariant.includes(candidateVariant) || candidateVariant.includes(placeVariant))
      ) {
        containmentMatched = true
      }

      bestSimilarity = Math.max(
        bestSimilarity,
        getKakaoNormalizedNameSimilarity(placeVariant, candidateVariant),
      )
    })
  })

  if (!placeVariants.length || !candidateVariants.length) {
    return {
      passed: false,
      reason: 'missing_name',
      similarity: 0,
      exactMatched: false,
      containmentMatched: false,
    }
  }

  if (hasGenericName) {
    return {
      passed: false,
      reason: 'generic_name',
      similarity: bestSimilarity,
      exactMatched,
      containmentMatched: false,
    }
  }

  const similarityMatched = bestSimilarity >= KAKAO_DETAIL_NAME_SIMILARITY_MIN
  const passed = exactMatched || containmentMatched || similarityMatched

  return {
    passed,
    reason: passed ? 'name_matched' : 'name_mismatch',
    similarity: bestSimilarity,
    exactMatched,
    containmentMatched,
  }
}

const getKakaoDetailMaxDistance = (place) => {
  const categoryText = [
    place?.rawCategory,
    place?.category,
  ]
    .map((value) => getTextValue(value))
    .filter(Boolean)

  const searchText = [
    ...categoryText,
    place?.name,
  ]
    .map((value) => getTextValue(value))
    .join(' ')
  const isWidePlace = (
    categoryText.some((category) => KAKAO_DETAIL_WIDE_CATEGORIES.has(category)) ||
    KAKAO_DETAIL_WIDE_NAME_KEYWORDS.some((keyword) => searchText.includes(keyword))
  )

  return isWidePlace
    ? KAKAO_DETAIL_WIDE_MATCH_DISTANCE_M
    : KAKAO_DETAIL_MATCH_DISTANCE_M
}

const getKakaoDetailCandidateUrl = (candidate) => {
  const candidateUrl = normalizeKakaoDetailUrl(candidate?.place_url || candidate?.placeUrl)

  if (candidateUrl) {
    return candidateUrl
  }

  const candidateId = getTextValue(candidate?.id)

  return isKakaoPlaceId(candidateId)
    ? `https://place.map.kakao.com/${candidateId}`
    : ''
}

const evaluateKakaoDetailCandidate = (place, candidate, query = '') => {
  const placeCoordinates = getKakaoDetailPlaceCoordinates(place)
  const maxDistance = getKakaoDetailMaxDistance(place)
  const candidateCoordinates = getKakaoDetailCandidateCoordinates(candidate)
  const url = getKakaoDetailCandidateUrl(candidate)
  const nameEvaluation = getKakaoDetailNameEvaluation(place?.name, candidate?.place_name)
  const rejectReasons = []
  let distance = null

  if (!placeCoordinates) {
    rejectReasons.push('missing_db_coordinates')
  }

  if (!candidateCoordinates) {
    rejectReasons.push('missing_candidate_coordinates')
  }

  if (placeCoordinates && candidateCoordinates) {
    distance = getDistanceMetersBetweenPlaces(placeCoordinates, candidateCoordinates)

    if (!Number.isFinite(distance)) {
      rejectReasons.push('invalid_distance')
    } else if (distance > maxDistance) {
      rejectReasons.push('distance_over_limit')
    }
  }

  if (!nameEvaluation.passed) {
    rejectReasons.push(nameEvaluation.reason)
  }

  if (!url) {
    rejectReasons.push('missing_url')
  }

  return {
    candidate,
    url,
    query,
    distance,
    maxDistance,
    nameSimilarity: nameEvaluation.similarity,
    nameEvaluation,
    hasUrl: Boolean(url),
    distanceMatched: Number.isFinite(distance) && distance <= maxDistance,
    nameMatched: nameEvaluation.passed,
    passed: rejectReasons.length === 0,
    rejectReasons,
  }
}

const isReliableKakaoDetailMatch = (dbPlace, kakaoCandidate) => {
  return evaluateKakaoDetailCandidate(dbPlace, kakaoCandidate).passed
}

const getBestKakaoDetailCandidate = (place, candidates = [], query = '') => {
  return candidates
    .map((candidate) => evaluateKakaoDetailCandidate(place, candidate, query))
    .map((evaluation) => {
      debugKakaoDetailLog('[카카오 상세 후보 평가]', {
        query: evaluation.query,
        dbPlaceName: place?.name,
        candidateName: evaluation.candidate?.place_name,
        candidateCoordinates: getKakaoDetailCandidateCoordinates(evaluation.candidate),
        distance: evaluation.distance,
        maxDistance: evaluation.maxDistance,
        nameSimilarity: evaluation.nameSimilarity,
        nameMatched: evaluation.nameMatched,
        distanceMatched: evaluation.distanceMatched,
        hasUrl: evaluation.hasUrl,
        passed: evaluation.passed,
        rejectReasons: evaluation.rejectReasons,
      })

      return evaluation
    })
    .filter((evaluation) => evaluation.passed)
    .sort((first, second) => {
      if (Number(second.nameEvaluation.exactMatched) !== Number(first.nameEvaluation.exactMatched)) {
        return Number(second.nameEvaluation.exactMatched) - Number(first.nameEvaluation.exactMatched)
      }

      if (Number(second.nameEvaluation.containmentMatched) !== Number(first.nameEvaluation.containmentMatched)) {
        return Number(second.nameEvaluation.containmentMatched) - Number(first.nameEvaluation.containmentMatched)
      }

      if (second.nameSimilarity !== first.nameSimilarity) {
        return second.nameSimilarity - first.nameSimilarity
      }

      return first.distance - second.distance
    })[0] || null
}

const shouldLookupKakaoDetailUrl = (place) => {
  if (!isDbPlace(place) || getDirectKakaoDetailUrl(place)) {
    return false
  }

  const lookupKey = getKakaoDetailLookupKey(place)
  if (!lookupKey || resolvedKakaoDetailUrls.value[lookupKey]) {
    return false
  }

  const status = kakaoDetailLookupStatus.value[lookupKey]
  if (['loading', 'success', 'failed'].includes(status)) {
    return false
  }

  return Boolean(
    buildKakaoDetailLookupQueries(place).length &&
    getKakaoDetailPlaceCoordinates(place),
  )
}

const resolveKakaoDetailUrlForPlace = async (place) => {
  if (!shouldLookupKakaoDetailUrl(place)) {
    return
  }

  if (!window.kakao || !window.kakao.maps || !window.kakao.maps.services) {
    return
  }

  const lookupKey = getKakaoDetailLookupKey(place)
  const placeCoordinates = getKakaoDetailPlaceCoordinates(place)
  const lookupQueries = buildKakaoDetailLookupQueries(place)

  kakaoDetailLookupStatus.value = {
    ...kakaoDetailLookupStatus.value,
    [lookupKey]: 'loading',
  }

  try {
    const placesService = new window.kakao.maps.services.Places()
    let matchedCandidate = null

    debugKakaoDetailLog('[카카오 상세 매칭 시작]', {
      dbPlaceName: place?.name,
      category: place?.rawCategory || place?.category,
      source: place?.sourceType || place?.source_type || place?.searchSource,
      coordinates: placeCoordinates,
      lookupQueries,
      radius: KAKAO_DETAIL_LOOKUP_RADIUS_M,
    })

    for (const query of lookupQueries) {
      const results = await runKakaoKeywordSearchLimited(
        placesService,
        query,
        {
          location: new window.kakao.maps.LatLng(placeCoordinates.lat, placeCoordinates.lng),
          radius: KAKAO_DETAIL_LOOKUP_RADIUS_M,
          sort: window.kakao.maps.services.SortBy.DISTANCE,
        },
        { maxPages: 1 },
      )

      matchedCandidate = getBestKakaoDetailCandidate(place, results, query)

      if (matchedCandidate) {
        break
      }
    }

    if (!matchedCandidate) {
      kakaoDetailLookupStatus.value = {
        ...kakaoDetailLookupStatus.value,
        [lookupKey]: 'failed',
      }
      debugKakaoDetailLog('[카카오 상세 매칭 결과]', {
        success: false,
        dbPlaceName: place?.name,
        lookupQueries,
        reason: 'no_reliable_candidate',
      })
      return
    }

    resolvedKakaoDetailUrls.value = {
      ...resolvedKakaoDetailUrls.value,
      [lookupKey]: matchedCandidate.url,
    }
    kakaoDetailLookupStatus.value = {
      ...kakaoDetailLookupStatus.value,
      [lookupKey]: 'success',
    }

    if (selectedPlace.value && getKakaoDetailLookupKey(selectedPlace.value) === lookupKey) {
      detailFrameError.value = false
    }

    debugKakaoDetailLog('[카카오 상세 매칭 결과]', {
      success: true,
      dbPlaceName: place?.name,
      query: matchedCandidate.query,
      selectedCandidateName: matchedCandidate.candidate?.place_name,
      selectedUrl: matchedCandidate.url,
      distance: matchedCandidate.distance,
      nameSimilarity: matchedCandidate.nameSimilarity,
    })
  } catch (error) {
    kakaoDetailLookupStatus.value = {
      ...kakaoDetailLookupStatus.value,
      [lookupKey]: 'failed',
    }
    debugKakaoDetailLog('[카카오 상세 매칭 결과]', {
      success: false,
      dbPlaceName: place?.name,
      lookupQueries,
      reason: error?.message || 'lookup_error',
    })
  }
}

const getCurrentLocationNavigationOrigin = () => {
  const currentPlace = currentLocationPlace.value.find((place) => {
    return place.searchSource === 'current_location'
  })
  const lat = Number(currentPlace?.lat)
  const lng = Number(currentPlace?.lng)

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return null
  }

  return {
    name: currentPlace.name || '현재 위치',
    lat,
    lng,
  }
}

const getPlaceNavigationUrl = (place) => {
  const destinationLat = Number(place?.lat)
  const destinationLng = Number(place?.lng)

  if (!Number.isFinite(destinationLat) || !Number.isFinite(destinationLng)) {
    return ''
  }

  const destinationName = encodeURIComponent(place?.name || '목적지')
  const origin = getCurrentLocationNavigationOrigin()

  if (origin) {
    return `https://map.kakao.com/link/from/${encodeURIComponent(origin.name)},${origin.lat},${origin.lng}/to/${destinationName},${destinationLat},${destinationLng}`
  }

  return (
    place?.navigationUrl ||
    place?.navigation_url ||
    `https://map.kakao.com/link/to/${destinationName},${destinationLat},${destinationLng}`
  )
}

const getPlaceDetailUrl = (place) => {
  return getKakaoDetailUrl(place)
}

const hasKakaoDetail = (place) => {
  return Boolean(getKakaoDetailUrl(place))
}

const getMarkerLabel = (index) => {
  return String(index + 1)
}

const getDistanceValue = (place) => {
  const distance = Number(place.distance)

  return Number.isFinite(distance) ? distance : null
}

const getDistanceText = (place) => {
  const distance = getDistanceValue(place)

  if (distance === null) {
    return ''
  }

  if (distance >= 1000) {
    return `${Number((distance / 1000).toFixed(1))}km`
  }

  return `${Math.round(distance)}m`
}

const getPlaceListTags = (place) => {
  return getSortedTags(place.tags || []).slice(0, 3)
}

const isRecommendationPlace = (place) => {
  return (
    toDisplayList(place?.requestedConditionIds).length > 0 ||
    place?.sourceLabel === 'DB추천' ||
    place?.sourceLabel === '카카오+DB' ||
    place?.recommendationSourceType === 'kakao_candidate' ||
    place?.source_type === 'kakao_candidate' ||
    place?.resultType === 'kakao_fallback_candidate' ||
    place?.tagSource === 'DB 추천 결과' ||
    place?.tagSource?.includes('DB 추천 결과')
  )
}

const isDbRecommendationResult = (place = {}) => {
  const sourceType = getTextValue(place.recommendationSourceType || place.source_type)
  const dbSourceTypes = ['db_verified', 'db_candidate', 'db_category_fallback']

  return (
    dbSourceTypes.includes(sourceType) ||
    place.sourceLabel === 'DB추천' ||
    place.sourceLabel === '카카오+DB' ||
    place.searchSource === 'local_db' ||
    Boolean(place.savedPlaceId)
  )
}

const isKakaoCandidateResult = (place = {}) => {
  const sourceType = getTextValue(place.recommendationSourceType || place.source_type)

  return (
    ['kakao_candidate', 'kakao_with_db_tags'].includes(sourceType) ||
    place.sourceLabel === '카카오' ||
    place.sourceLabel === '카카오+DB' ||
    place.searchSource === 'kakao' ||
    String(place.resultType || '').startsWith('kakao_') ||
    Boolean(place.kakaoPlaceId)
  )
}

const matchesResultFilter = (place, filterMode = 'all') => {
  if (filterMode === 'db') {
    return isDbRecommendationResult(place)
  }

  if (filterMode === 'kakao') {
    return isKakaoCandidateResult(place)
  }

  return true
}

const clearSelectedPlaceIfFilteredOut = () => {
  if (!selectedPlace.value?.id) {
    return
  }

  const selectedPlaceVisible = filteredSearchResults.value.some((place) => {
    return place.id === selectedPlace.value.id
  })

  if (selectedPlaceVisible) {
    return
  }

  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false
  isPlaceDetailCollapsed.value = false
}

const setResultFilterMode = (filterMode) => {
  resultFilterMode.value = filterMode
}

const useDefaultMapLocation = () => {
  activeTab.value = 'map'
  activeResultView.value = 'map'
  isResultListCollapsed.value = true
  mapCenter.value = DEFAULT_CENTER
  currentLocationPlace.value = [
    {
      id: 'default-location',
      name: '기본 설정 위치',
      lat: DEFAULT_CENTER.lat,
      lng: DEFAULT_CENTER.lng,
      address: '',
      distance: null,
      markerColor: 'green',
      searchSource: 'default_location',
      sourceLabel: '기준',
      tags: [makeTag('기본위치', 'category_rule')],
    },
  ]
  locationMessage.value = '기본 설정 위치 기준으로 지도를 표시하고 있습니다.'
}

const getMatchedTagText = (place) => {
  return (place?.matchedTags || [])
    .filter(Boolean)
    .join(', ')
}

const getRecommendationReason = (place) => {
  if (!isRecommendationPlace(place)) {
    return ''
  }

  if (place?.recommendationReason) {
    return place.recommendationReason
  }

  if (place?.waitingPlacePenaltyReason || place?.waitingPlacePenalty) {
    return '일반적인 잠깐 휴식 목적과는 맞지 않을 수 있어 후순위로 반영했습니다.'
  }

  const matchedTags = place?.matchedTags || []
  const savedTags = [
    ...(place?.suggestedTags || []),
    ...(place?.verifiedTags || []),
  ]

  if (matchedTags.length) {
    return `${matchedTags.slice(0, 3).join(', ')} 태그가 입력 조건과 일치합니다.`
  }

  if (savedTags.length) {
    return 'DB에 저장된 태그 정보를 바탕으로 추천 후보로 표시했습니다.'
  }

  if (getDistanceValue(place) !== null) {
    return '검색 기준 위치에서 가까운 장소입니다.'
  }

  return 'DB에 저장된 장소 정보를 바탕으로 추천 후보로 표시했습니다.'
}

const getRecommendationReasonSummary = (place) => {
  if (!isRecommendationPlace(place)) {
    return ''
  }

  const matchedLabels = getRecommendationPreviewLabels(getRecommendationMatchedLabels(place), 2)
  const missingLabels = getRecommendationPreviewLabels(getRecommendationMissingLabels(place), 1)
  const fallbackText = getRecommendationFallbackText(place)
  const menuDisplayLabels = getRecommendationPreviewLabels(getMenuDisplayMatchedLabels(place), 2)
  const rawMatchedLabels = [
    ...toDisplayList(place?.matchedTagLabels || place?.matched_tag_labels),
    ...toDisplayList(place?.matchedTags || place?.matched_tags),
  ]

  if (menuDisplayLabels.length && !rawMatchedLabels.length) {
    return `${menuDisplayLabels.join(', ')} 조건과 일치 · 세부 정보는 방문 전 확인 필요`
  }

  if (missingLabels.length && !matchedLabels.length) {
    return '요청한 조건은 현재 데이터로 확인되지 않았습니다. 방문 전 확인이 필요합니다.'
  }

  if (matchedLabels.length) {
    const summaryParts = [`${matchedLabels.join(', ')} 조건과 일치`]

    if (missingLabels.length) {
      summaryParts.push(`${missingLabels.join(', ')} 확인 필요`)
    }

    return summaryParts.join(' · ')
  }

  if (fallbackText) {
    return missingLabels.length
      ? `${fallbackText} · ${missingLabels.join(', ')} 확인 필요`
      : fallbackText
  }

  const reason = getRecommendationReason(place)
  const sentenceEndIndex = reason.indexOf('.')
  const firstSentence = sentenceEndIndex >= 0
    ? reason.slice(0, sentenceEndIndex + 1)
    : reason

  if (firstSentence.length <= 80) {
    return firstSentence
  }

  return `${firstSentence.slice(0, 80).trim()}...`
}

const getCandidateDescription = (place) => {
  return place?.externalCandidateMessage
    ? `카카오 지도 검색 결과입니다. ${place.externalCandidateMessage}`
    : '카카오 지도 검색 결과입니다. 세부 태그 데이터는 아직 없습니다.'
}

const getRecommendationConfidence = (place) => {
  if (!isRecommendationPlace(place)) {
    return ''
  }

  if (place?.recommendationConfidence) {
    return place.recommendationConfidence
  }

  if ((place?.warningTags || []).length) {
    return 'low'
  }

  if ((place?.verifiedTags || []).length || (place?.matchedTags || []).length) {
    return 'medium'
  }

  if ((place?.suggestedTags || []).length) {
    return 'low'
  }

  return 'medium'
}

const getRecommendationConfidenceText = (confidence) => {
  const confidenceMap = {
    high: '높음',
    medium: '보통',
    low: '낮음',
  }

  return confidenceMap[confidence] || confidence || ''
}

const getRecommendScore = (place) => {
  const score = Number(
    place.recommendScore ??
    place.score ??
    place.dataQualityScore ??
    0,
  )

  return Number.isFinite(score) ? score : 0
}

const getRecommendationSortScore = (place) => {
  const baseScore = getRecommendScore(place)
  const sourceBonusMap = {
    'DB추천': 35,
    '카카오+DB': 32,
    '카카오': 0,
  }
  const sourceBonus = sourceBonusMap[place?.sourceLabel] || 0
  const waitingPenalty = place?.waitingPlacePenalty || 0
  const mainPlaceScore = place?.mainPlaceScore || 0
  const ancillaryPenalty = place?.ancillaryPlacePenalty || 0
  const intentMismatchPenalty = place?.intentMismatchPenalty || 0
  const placeShapeScore = mainPlaceScore - ancillaryPenalty - intentMismatchPenalty

  if (place?.resultType === 'kakao_takeout_untagged') {
    return baseScore + sourceBonus + placeShapeScore - 35 - waitingPenalty
  }

  if (place?.resultType === 'kakao_only') {
    return baseScore + sourceBonus + placeShapeScore - 20 - waitingPenalty
  }

  if (place?.resultType === 'kakao_tag_weak') {
    return baseScore + sourceBonus + placeShapeScore - 12 - waitingPenalty
  }

  if (place?.resultType === 'kakao_fallback_candidate') {
    return baseScore + sourceBonus + placeShapeScore - 75 - waitingPenalty
  }

  return baseScore + sourceBonus + placeShapeScore - waitingPenalty
}

const isLowConfidenceWalkHealingFallback = (place = {}) => {
  if (place?.recommendationIntent !== 'walk_healing') return false

  const score = getRecommendScore(place)
  return isCategoryFallbackRecommendation(place) || score < 40
}

const compareLowConfidenceFallback = (firstPlace, secondPlace) => {
  return Number(isLowConfidenceWalkHealingFallback(firstPlace)) -
    Number(isLowConfidenceWalkHealingFallback(secondPlace))
}

const getConfidenceRank = (place) => {
  const confidence = getTextValue(
    place?.recommendationConfidence ||
    place?.confidence ||
    getRecommendationConfidence(place),
  ).toLowerCase()
  const confidenceRankMap = {
    high: 3,
    medium: 2,
    low: 1,
  }

  return confidenceRankMap[confidence] || 0
}

const getResultSourceRank = (place) => {
  if (place?.sourceLabel === '카카오+DB') {
    return 0
  }

  if (place?.sourceLabel === 'DB추천' || place?.searchSource === 'local_db') {
    return 1
  }

  return 2
}

const hasNormalizedKeywordMatch = (text = '', keywords = []) => {
  return keywords.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return normalizedKeyword && text.includes(normalizedKeyword)
  })
}

const getSpecificPlaceTypeTerms = (menuProfile = {}) => {
  return (menuProfile.placeTypeTerms || []).filter((term) => {
    const normalizedTerm = normalizeLocationText(term)
    return !['카페', '식당', '음식점', '맛집'].includes(normalizedTerm)
  })
}

const getTagDetailTextValues = (tagDetails = []) => {
  return (Array.isArray(tagDetails) ? tagDetails : []).flatMap((tag) => {
    if (typeof tag === 'string') return [tag]

    return [
      tag?.name,
      tag?.display_name,
      tag?.displayName,
      tag?.label,
    ].filter(Boolean)
  })
}

const getTagTextValues = (tags = []) => {
  return (Array.isArray(tags) ? tags : []).flatMap((tag) => {
    if (typeof tag === 'string') return [tag]

    return [
      tag?.name,
      tag?.display_name,
      tag?.displayName,
      tag?.label,
    ].filter(Boolean)
  })
}

const getDirectMenuMatchText = (place = {}) => {
  const fallbackTerms = place.resultType === 'kakao_fallback_candidate'
    ? [
      place.fallbackQuery,
      place.kakaoFallbackQuery,
      ...(place.matchedSearchKeywords || []),
    ]
    : []

  return normalizeLocationText([
    place.name,
    place.category,
    place.category_name,
    place.rawCategory,
    ...getTagTextValues(place.matchedTags || place.matched_tags),
    ...getTagTextValues(place.matchedTagLabels || place.matched_tag_labels),
    ...getTagTextValues(place.suggestedTags || place.suggested_tags),
    ...getTagTextValues(place.suggestedTagLabels || place.suggested_tag_labels),
    ...getTagTextValues(place.verifiedTags || place.verified_tags),
    ...getTagTextValues(place.verifiedTagLabels || place.verified_tag_labels),
    ...getTagDetailTextValues(place.tagDetails || place.tag_details),
    ...getTagTextValues(place.tags),
    ...fallbackTerms,
  ].filter(Boolean).join(' '))
}

const getMenuDisplayMatchedLabels = (place = {}) => {
  const menuProfile = activeMenuSearchProfile.value
  if (!menuProfile?.menuIntent) {
    return []
  }

  const matchText = getDirectMenuMatchText(place)
  const candidateTerms = [
    ...(menuProfile.directMenuTerms || menuProfile.directTerms || []),
    ...getSpecificPlaceTypeTerms(menuProfile),
  ]

  return [...new Set(candidateTerms.filter((term) => {
    return hasNormalizedKeywordMatch(matchText, [term])
  }))]
}

const getMenuSearchSortRank = (place = {}) => {
  const menuProfile = activeMenuSearchProfile.value
  if (!menuProfile?.menuIntent) {
    return 0
  }

  const matchText = getDirectMenuMatchText(place)
  const menuTerms = menuProfile.directMenuTerms || menuProfile.directTerms || []
  const strongPlaceTypeTerms = getSpecificPlaceTypeTerms(menuProfile)
  const fallbackQueryText = normalizeLocationText([
    place.fallbackQuery,
    place.kakaoFallbackQuery,
    ...(place.matchedSearchKeywords || []),
  ].filter(Boolean).join(' '))
  const hasMenuMatch = hasNormalizedKeywordMatch(matchText, menuTerms)
  const hasPlaceTypeMatch = hasNormalizedKeywordMatch(matchText, strongPlaceTypeTerms)
  const isMenuKakaoFallback = (
    place.resultType === 'kakao_fallback_candidate' &&
    (
      hasNormalizedKeywordMatch(fallbackQueryText, menuTerms) ||
      hasNormalizedKeywordMatch(fallbackQueryText, strongPlaceTypeTerms)
    )
  )
  const hasTagMatch = (
    !isCategoryFallbackRecommendation(place) &&
    (
      getRecommendationMatchedLabels(place).length > 0 ||
      (place.matchedTags || []).length > 0 ||
      ['db_verified', 'db_candidate'].includes(getTextValue(place.recommendationSourceType || place.source_type))
    )
  )
  const rawMatchedLabels = [
    ...toDisplayList(place.matchedTagLabels || place.matched_tag_labels),
    ...toDisplayList(place.matchedTags || place.matched_tags),
  ]
  const hasVerifiedMenuMatch = (
    hasMenuMatch &&
    (
      rawMatchedLabels.length > 0 ||
      (place.matchedTags || []).length > 0 ||
      getTextValue(place.recommendationSourceType || place.source_type) === 'db_verified'
    )
  )

  if (hasVerifiedMenuMatch) return 6
  if (isMenuKakaoFallback) return 5
  if (hasMenuMatch) return 4
  if (hasPlaceTypeMatch) return 3
  if (hasTagMatch) return 2
  if (isCategoryFallbackRecommendation(place)) return 0

  return 1
}

const compareByDistance = (firstPlace, secondPlace) => {
  const firstDistance = getDistanceValue(firstPlace)
  const secondDistance = getDistanceValue(secondPlace)

  if (firstDistance === null && secondDistance !== null) {
    return 1
  }

  if (firstDistance !== null && secondDistance === null) {
    return -1
  }

  if (
    firstDistance !== null &&
    secondDistance !== null &&
    firstDistance !== secondDistance
  ) {
    return firstDistance - secondDistance
  }

  return firstPlace.originalOrder - secondPlace.originalOrder
}

const compareForGeneralSearch = (firstPlace, secondPlace) => {
  const sourceRankDifference =
    getResultSourceRank(firstPlace) - getResultSourceRank(secondPlace)

  if (sourceRankDifference !== 0) {
    return sourceRankDifference
  }

  const shapeDifference =
    ((secondPlace.mainPlaceScore || 0) - (secondPlace.ancillaryPlacePenalty || 0) - (secondPlace.intentMismatchPenalty || 0)) -
    ((firstPlace.mainPlaceScore || 0) - (firstPlace.ancillaryPlacePenalty || 0) - (firstPlace.intentMismatchPenalty || 0))

  if (shapeDifference !== 0) {
    return shapeDifference
  }

  return compareByDistance(firstPlace, secondPlace)
}

const compareForRecommendationSearch = (firstPlace, secondPlace) => {
  const menuRankDifference = getMenuSearchSortRank(secondPlace) - getMenuSearchSortRank(firstPlace)

  if (menuRankDifference !== 0) {
    return menuRankDifference
  }

  const scoreDifference =
    getRecommendationSortScore(secondPlace) - getRecommendationSortScore(firstPlace)

  if (scoreDifference !== 0) {
    return scoreDifference
  }

  return compareByDistance(firstPlace, secondPlace)
}

const compareForConfidenceSearch = (firstPlace, secondPlace) => {
  const confidenceDifference = getConfidenceRank(secondPlace) - getConfidenceRank(firstPlace)

  if (confidenceDifference !== 0) {
    return confidenceDifference
  }

  const scoreDifference =
    getRecommendationSortScore(secondPlace) - getRecommendationSortScore(firstPlace)

  if (scoreDifference !== 0) {
    return scoreDifference
  }

  return compareByDistance(firstPlace, secondPlace)
}

const sortSearchResults = (results = []) => {
  const indexedResults = results.map((place, index) => ({
    ...place,
    originalOrder: index,
  }))

  const sortedResults = [...indexedResults].sort((firstPlace, secondPlace) => {
    const fallbackDifference = compareLowConfidenceFallback(firstPlace, secondPlace)
    if (fallbackDifference !== 0) {
      return fallbackDifference
    }

    if (sortMode.value === 'recommendation') {
      return compareForRecommendationSearch(firstPlace, secondPlace)
    }

    if (sortMode.value === 'confidence') {
      return compareForConfidenceSearch(firstPlace, secondPlace)
    }

    return compareForGeneralSearch(firstPlace, secondPlace)
  })

  return sortedResults.map(({ originalOrder, ...place }) => place)
}

const convertKakaoPlaces = (
  places,
  savedTagDataByExternalId = {},
  {
    query = '',
    center = null,
    preferredTags = [],
    recommendationIntent = '',
    categoryHint = '',
    isAncillaryIntent = false,
    fallbackCandidate = false,
    requestedConditions = [],
  } = {},
) => {
  return toArray(places).map((place) => {
    const savedTagData = savedTagDataByExternalId[String(place.id)] || {}
    const rawScores = savedTagData.raw_scores || {}
    const hasTagData = hasSavedTagMatch(savedTagData)
    const recommendationData = calculateKakaoTagRecommendation({
      place,
      savedTagData,
      query,
      center,
      preferredTags,
      recommendationIntent,
    })
    const takeoutHeavy = isTakeoutHeavyCafeCandidate(place)
    const waitingSuitability = recommendationIntent === 'waiting_place'
      ? getWaitingPlaceSuitability(place, savedTagData)
      : { excluded: false, penalty: 0 }
    const walkHealingSuitability = recommendationIntent === 'walk_healing'
      ? getWalkHealingSuitability({ place, query })
      : { excluded: false, penalty: 0, bonus: 0, reason: null }
    const ancillaryAdjustment = getAncillaryPlaceAdjustment({
      place,
      query,
      categoryHint,
      recommendationIntent,
      isAncillaryIntent,
    })
    const fallbackScore = getKakaoFallbackCandidateScore({
      place,
      center,
      mainPlaceScore: ancillaryAdjustment.mainPlaceScore,
      ancillaryPlacePenalty: ancillaryAdjustment.ancillaryPlacePenalty,
      intentMismatchPenalty: ancillaryAdjustment.intentMismatchPenalty,
      waitingPlacePenalty: recommendationData.waitingPlacePenalty || waitingSuitability.penalty || 0,
      walkHealingPenalty: walkHealingSuitability.penalty || 0,
      walkHealingBonus: walkHealingSuitability.bonus || 0,
    })
    const fallbackReason = 'DB 추천 결과가 부족해 카카오 검색 결과를 낮은 신뢰도 후보로 함께 표시합니다. 외부 검색 결과이므로 방문 전 세부 조건 확인이 필요합니다.'

    return mergeRequestedConditionReview({
      id: `kakao-${place.id}`,
      kakaoPlaceId: place.id,
      savedPlaceId: savedTagData.saved_place_id || null,
      name: place.place_name,
      category: place.category_name,
      address: place.road_address_name || place.address_name,
      lat: Number(place.y),
      lng: Number(place.x),
      distance: place.distance ? Number(place.distance) : null,
      phone: place.phone,
      placeUrl: place.place_url,
      kakaoPlaceUrl: place.place_url,
      fallbackQuery: fallbackCandidate ? getTextValue(place.__fallbackQuery) : '',
      kakaoFallbackQuery: fallbackCandidate ? getTextValue(place.__fallbackQuery) : '',
      fallbackQueryRank: fallbackCandidate && Number.isFinite(Number(place.__fallbackQueryRank))
        ? Number(place.__fallbackQueryRank)
        : null,
      navigationUrl: `https://map.kakao.com/link/to/${encodeURIComponent(place.place_name)},${place.y},${place.x}`,
      markerColor: 'red',
      searchSource: 'kakao',
      sourceLabel: hasTagData ? '카카오+DB' : '카카오',
      tags: makeKakaoResultTags(place, savedTagData),
      tagSource: savedTagData.saved_place_id
        ? '카카오 API 검색 결과 + DB 저장 태그'
        : '카카오 API 검색 결과',
      suggestedTags: savedTagData.suggested_tags || [],
      verifiedTags: savedTagData.verified_tags || [],
      warningTags: savedTagData.warning_tags || [],
      tagDetails: savedTagData.tag_details || [],
      matchedTagLabels: fallbackCandidate && hasTagData
        ? getSavedTagNames(savedTagData).slice(0, 3)
        : [],
      matchedSearchKeywords: fallbackCandidate
        ? toDisplayList([place.__fallbackQuery]).filter(Boolean)
        : [],
      matched_tag_labels: fallbackCandidate && hasTagData
        ? getSavedTagNames(savedTagData).slice(0, 3)
        : [],
      missingTagLabels: [],
      missing_tag_labels: [],
      recommendationSourceLabel: fallbackCandidate ? '카카오 검색 후보' : '',
      source_type: fallbackCandidate ? 'kakao_candidate' : '',
      source_label: fallbackCandidate ? '카카오 검색 후보' : '',
      recommendationConfidenceLabel: fallbackCandidate ? '낮은 신뢰도' : '',
      confidence: fallbackCandidate ? 'low' : '',
      confidence_label: fallbackCandidate ? '낮은 신뢰도' : '',
      recommendationFallbackLabel: fallbackCandidate ? '카카오 검색 기반 후보' : '',
      fallback_level: fallbackCandidate ? 5 : null,
      fallback_label: fallbackCandidate ? '카카오 검색 기반 후보' : '',
      recommendationFallbackDescription: fallbackCandidate
        ? 'DB 추천 결과가 부족해 카카오 검색 결과를 함께 표시한 후보입니다.'
        : '',
      fallback_description: fallbackCandidate
        ? 'DB 추천 결과가 부족해 카카오 검색 결과를 함께 표시한 후보입니다.'
        : '',
      recommendationCaution: fallbackCandidate
        ? '외부 검색 결과 기반 후보이므로 세부 정보는 방문 전 확인이 필요합니다.'
        : '',
      caution_message: fallbackCandidate
        ? '외부 검색 결과 기반 후보이므로 세부 정보는 방문 전 확인이 필요합니다.'
        : '',
      dataQualityStatus: savedTagData.data_quality_status || null,
      dataQualityScore: savedTagData.data_quality_score || null,
      rawScores,
      recommendScore: fallbackCandidate
        ? fallbackScore
        : hasTagData
        ? (
          recommendationData.recommendScore ??
          rawScores.recommendation_ready_score ??
          savedTagData.data_quality_score ??
          null
        )
        : null,
      score: fallbackCandidate ? fallbackScore : null,
      recommendationReason: fallbackCandidate
        ? fallbackReason
        : recommendationData.recommendationReason,
      matchedTags: recommendationData.matchedTags,
      recommendationConfidence: fallbackCandidate
        ? 'low'
        : recommendationData.recommendationConfidence,
      recommendationSourceType: fallbackCandidate ? 'kakao_candidate' : '',
      fallbackLevel: fallbackCandidate ? 5 : null,
      externalCandidateMessage: hasTagData ? '' : '세부 태그 데이터 없음',
      recommendationIntent,
      preferredTags,
      preferredMatchCount: recommendationData.preferredMatchCount || 0,
      takeoutHeavy,
      waitingPlacePenalty: recommendationData.waitingPlacePenalty || waitingSuitability.penalty || 0,
      waitingPlaceExcluded: recommendationData.waitingPlaceExcluded || waitingSuitability.excluded || false,
      waitingPlacePenaltyReason: recommendationData.waitingPlacePenaltyReason || waitingSuitability.reason || null,
      walkHealingPenalty: walkHealingSuitability.penalty || 0,
      walkHealingExcluded: walkHealingSuitability.excluded || false,
      walkHealingPenaltyReason: walkHealingSuitability.reason || null,
      mainPlaceScore: ancillaryAdjustment.mainPlaceScore,
      ancillaryPlacePenalty: ancillaryAdjustment.ancillaryPlacePenalty,
      intentMismatchPenalty: ancillaryAdjustment.intentMismatchPenalty,
      isAncillaryPlace: ancillaryAdjustment.isAncillaryPlace,
      resultType: hasTagData
        ? (
          fallbackCandidate
            ? 'kakao_fallback_candidate'
            : (
              !preferredTags.length || recommendationData.preferredMatchCount > 0
                ? 'kakao_tag_matched'
                : 'kakao_tag_weak'
            )
        )
        : fallbackCandidate
        ? 'kakao_fallback_candidate'
        : (
          waitingSuitability.excluded
            ? 'kakao_unsuitable_waiting_place'
            : (takeoutHeavy ? 'kakao_takeout_untagged' : 'kakao_only')
        ),
    }, requestedConditions)
  }).filter((place) => {
    if (recommendationIntent === 'waiting_place' && place.waitingPlaceExcluded) return false
    if (recommendationIntent === 'walk_healing' && place.walkHealingExcluded) return false
    return true
  })
}

const searchKakaoSavedTags = async (places) => {
  const externalIds = places
    .map((place) => String(place.id || '').trim())
    .filter(Boolean)

  if (!externalIds.length) {
    return {}
  }

  try {
    const data = await getKakaoPlaceTags(externalIds)
    return data.results || {}
  } catch (error) {
    console.error(error)
    return {}
  }
}

const getKakaoFallbackCandidateScore = ({
  place,
  center = null,
  mainPlaceScore = 0,
  ancillaryPlacePenalty = 0,
  intentMismatchPenalty = 0,
  waitingPlacePenalty = 0,
  walkHealingPenalty = 0,
  walkHealingBonus = 0,
} = {}) => {
  const distance = center
    ? getDistanceMetersBetweenPlaces(
      { lat: center.lat, lng: center.lng },
      { lat: Number(place?.y ?? place?.lat), lng: Number(place?.x ?? place?.lng) },
    )
    : Number(place?.distance || 0)
  const distanceBonus = Number.isFinite(distance)
    ? (
      distance <= 500
        ? 8
        : distance <= 1000
        ? 5
        : distance <= 3000
        ? 2
        : 0
    )
    : 0
  const shapeScore = Math.max(
    -12,
    Math.min(8, mainPlaceScore - ancillaryPlacePenalty - intentMismatchPenalty),
  )
  const penalty = Math.min(24, Math.round((waitingPlacePenalty + walkHealingPenalty) / 10))

  return Math.max(
    40,
    Math.min(
      KAKAO_FALLBACK_MAX_SCORE,
      45 + distanceBonus + shapeScore + walkHealingBonus - penalty,
    ),
  )
}

const isKakaoFallbackLikelySparseQuery = ({
  query = '',
  recommendationIntent = '',
  categoryHint = '',
  data = {},
} = {}) => {
  const condition = getRecommendationConditionData(data)

  if (['restaurant', 'work_cafe'].includes(recommendationIntent)) {
    return true
  }

  if (['restaurant', 'cafe'].includes(categoryHint)) {
    return true
  }

  const text = normalizeLocationText([
    query,
    data?.scenario,
    condition?.intent,
    ...toDisplayList(condition?.keywords),
    ...toDisplayList(condition?.preferred_tag_labels),
  ].filter(Boolean).join(' '))

  return KAKAO_FALLBACK_KEYWORD_RULES.slice(0, 2).some((rule) => {
    return rule.keywords.some((keyword) => text.includes(normalizeLocationText(keyword)))
  })
}

const shouldRunKakaoRecommendationFallback = ({
  dbResults = [],
  query = '',
  recommendationIntent = '',
  categoryHint = '',
  data = {},
  menuProfile = null,
} = {}) => {
  const resolvedMenuProfile = menuProfile || getMenuSearchProfile({ query, data })
  if (
    resolvedMenuProfile.menuIntent &&
    getDirectMenuDbMatchCount(dbResults, resolvedMenuProfile) < KAKAO_FALLBACK_MIN_RESULTS
  ) {
    return true
  }

  if (dbResults.length < KAKAO_FALLBACK_MIN_RESULTS) {
    return true
  }

  return (
    dbResults.length < KAKAO_FALLBACK_MAX_RESULTS &&
    isKakaoFallbackLikelySparseQuery({
      query,
      recommendationIntent,
      categoryHint,
      data,
    })
  )
}

const getKakaoFallbackCategoryKeywords = (categories = []) => {
  return categories
    .map((category) => CATEGORY_KAKAO_KEYWORDS[category])
    .filter(Boolean)
}

const getRecommendationConditionData = (data = {}) => {
  return {
    ...(data?.ai_parse || {}),
    ...(data?.recommendation_condition || {}),
    ...(data?.condition || {}),
    ...(data?.conditions || {}),
  }
}

const cleanFoodMenuKeyword = (value = '') => {
  return getTextValue(value)
    .replace(/^(근처에|근처|주변에|주변|가까운|가까이|여기서|지금)\s*/g, '')
    .replace(/(추천|찾아줘|찾아|좋은|괜찮은|먹고\s*싶어|먹고싶어)$/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 40)
}

const extractFoodMenuKeywords = (query = '') => {
  const text = getTextValue(query)
  const menuKeywords = []

  FOOD_MENU_PATTERN_SUFFIXES.forEach((suffix) => {
    const index = text.indexOf(suffix)
    if (index > 0) {
      const menu = cleanFoodMenuKeyword(text.slice(0, index))
      if (menu) menuKeywords.push(menu)
    }
  })

  const compactText = normalizeLocationText(text)
  FOOD_MENU_KNOWN_KEYWORDS.forEach((keyword) => {
    if (compactText.includes(normalizeLocationText(keyword))) {
      menuKeywords.push(keyword)
    }
  })

  return [...new Set(menuKeywords)].slice(0, 3)
}

const inferFoodPlaceTypeKeywords = ({ query = '', menuKeywords = [], conditionPlaceTypes = [] } = {}) => {
  const explicitPlaceTypes = toDisplayList(conditionPlaceTypes)
  if (explicitPlaceTypes.length) {
    return explicitPlaceTypes
  }

  const text = normalizeLocationText([query, ...menuKeywords].join(' '))

  if (FOOD_BAKERY_KEYWORDS.some((keyword) => text.includes(normalizeLocationText(keyword)))) {
    return ['베이커리', '빵집', '카페']
  }

  if (FOOD_CAFE_KEYWORDS.some((keyword) => text.includes(normalizeLocationText(keyword)))) {
    return ['카페']
  }

  return ['식당', '음식점']
}

const compactKeyword = (keyword = '') => normalizeLocationText(keyword)

const getPrimaryMenuKeywords = (menuKeywords = []) => {
  const uniqueKeywords = [...new Set(menuKeywords.filter(Boolean))]

  return uniqueKeywords.filter((keyword) => {
    const normalizedKeyword = compactKeyword(keyword)
    if (normalizedKeyword.length > 2) return true

    return !uniqueKeywords.some((otherKeyword) => {
      const normalizedOther = compactKeyword(otherKeyword)
      return (
        normalizedOther !== normalizedKeyword &&
        normalizedOther.length > normalizedKeyword.length &&
        normalizedOther.includes(normalizedKeyword)
      )
    })
  })
}

const buildFoodMenuFallbackQueries = ({ query = '', data = {} } = {}) => {
  const condition = getRecommendationConditionData(data)
  const menuKeywords = getPrimaryMenuKeywords([
    ...toDisplayList(condition?.menu_keywords),
    ...extractFoodMenuKeywords(query),
  ].filter((keyword, index, keywords) => keyword && keywords.indexOf(keyword) === index))

  if (!menuKeywords.length) {
    return []
  }

  const placeTypeKeywords = inferFoodPlaceTypeKeywords({
    query,
    menuKeywords,
    conditionPlaceTypes: condition?.place_type_keywords,
  })
  const purposeKeywords = toDisplayList(condition?.purpose_keywords)
  const hasMatjipIntent = normalizeLocationText([query, ...purposeKeywords].join(' ')).includes(normalizeLocationText('맛집'))
  const queries = []

  menuKeywords.forEach((menu) => {
    if (hasMatjipIntent) queries.push(`${menu} 맛집`)
    queries.push(menu)

    if (placeTypeKeywords.some((keyword) => ['베이커리', '빵집', '카페'].includes(keyword))) {
      queries.push(`${menu} 카페`)
    } else {
      queries.push(`${menu} 식당`)
    }
  })

  queries.push(...placeTypeKeywords)
  return [...new Set(queries.filter(Boolean))]
}

const getMenuSearchProfile = ({ query = '', data = {} } = {}) => {
  const condition = getRecommendationConditionData(data)
  const menuKeywords = getPrimaryMenuKeywords([
    ...toDisplayList(condition?.menu_keywords),
    ...extractFoodMenuKeywords(query),
  ].filter((keyword, index, keywords) => keyword && keywords.indexOf(keyword) === index))
  const placeTypeKeywords = inferFoodPlaceTypeKeywords({
    query,
    menuKeywords,
    conditionPlaceTypes: condition?.place_type_keywords,
  })
  const purposeKeywords = [
    ...toDisplayList(condition?.purpose_keywords),
    ...(normalizeLocationText(query).includes(normalizeLocationText('맛집')) ? ['맛집'] : []),
  ].filter((keyword, index, keywords) => keyword && keywords.indexOf(keyword) === index)

  return {
    menuIntent: Boolean(menuKeywords.length || purposeKeywords.length),
    menuKeywords,
    placeTypeKeywords,
    purposeKeywords,
    directMenuTerms: [...new Set(menuKeywords.filter(Boolean))],
    placeTypeTerms: [...new Set(placeTypeKeywords.filter(Boolean))],
    directTerms: [...new Set(menuKeywords.filter(Boolean))],
  }
}

const getRecommendationDirectMatchText = (place = {}) => {
  return getDirectMenuMatchText(place)
}

const isCategoryFallbackRecommendation = (place = {}) => {
  const sourceType = getTextValue(place.recommendationSourceType || place.source_type)
  return (
    sourceType === 'db_category_fallback' ||
    place.matchLevel === 'category_distance_fallback' ||
    place.fallbackLevel >= 3
  )
}

const isDirectMenuDbMatch = (place = {}, menuProfile = {}) => {
  if (!menuProfile.menuIntent) return true

  const directTerms = [
    ...(menuProfile.directTerms || []),
    ...getSpecificPlaceTypeTerms(menuProfile),
  ]
  const directMatchText = getRecommendationDirectMatchText(place)
  const hasDirectTermMatch = directTerms.some((term) => {
    return directMatchText.includes(normalizeLocationText(term))
  })

  return hasDirectTermMatch
}

const getDirectMenuDbMatchCount = (dbResults = [], menuProfile = {}) => {
  if (!menuProfile.menuIntent) {
    return dbResults.length
  }

  return dbResults.filter((place) => isDirectMenuDbMatch(place, menuProfile)).length
}

const buildKakaoRecommendationFallbackQueries = ({
  query = '',
  data = {},
  parsedIntent = null,
} = {}) => {
  const condition = getRecommendationConditionData(data)
  const walkHealingIntent = isWalkHealingSearchIntent({
    query,
    data,
    parsedIntent,
  })

  if (walkHealingIntent) {
    const walkQueries = [...WALK_HEALING_FALLBACK_QUERIES]

    if (hasExplicitWalkCafeIntent(query, parsedIntent)) {
      walkQueries.push('산책 카페', '공원 카페', '카페')
    }

    return [...new Set(walkQueries.filter(Boolean))]
      .slice(0, KAKAO_WALK_HEALING_FALLBACK_MAX_QUERIES)
  }

  const textForRules = normalizeLocationText([
    query,
    data?.scenario,
    parsedIntent?.recommendationIntent,
    parsedIntent?.categoryHint,
    condition?.intent,
    ...toDisplayList(condition?.keywords),
    ...toDisplayList(condition?.preferred_tag_labels),
  ].filter(Boolean).join(' '))
  const foodMenuQueries = buildFoodMenuFallbackQueries({ query, data })
  const ruleQueries = KAKAO_FALLBACK_KEYWORD_RULES
    .filter((rule) => {
      return rule.keywords.some((keyword) => textForRules.includes(normalizeLocationText(keyword)))
    })
    .flatMap((rule) => rule.queries)
  const categories = [
    ...toDisplayList(condition?.categories),
    parsedIntent?.categoryHint,
  ].filter(Boolean)
  const conditionKeywords = [
    ...toDisplayList(condition?.menu_keywords),
    ...toDisplayList(condition?.place_type_keywords),
    ...toDisplayList(condition?.purpose_keywords),
    ...toDisplayList(condition?.keywords),
    ...toDisplayList(condition?.preferred_tag_labels),
    ...toDisplayList(condition?.required_tag_labels),
  ]
  const candidates = [
    ...foodMenuQueries,
    ...ruleQueries,
    ...getKakaoFallbackCategoryKeywords(categories),
    ...toDisplayList(parsedIntent?.kakaoKeywordCandidates),
    getKakaoKeywordForAiSearch(data, query),
    ...conditionKeywords,
    query,
  ]

  return [...new Set(
    candidates
      .map((keyword) => getTextValue(keyword))
      .filter(Boolean),
  )].slice(0, KAKAO_FALLBACK_MAX_QUERIES)
}

const isWalkHealingSearchIntent = ({
  query = '',
  data = {},
  parsedIntent = null,
  categoryHint = '',
} = {}) => {
  const condition = getRecommendationConditionData(data)
  const text = normalizeLocationText([
    query,
    data?.scenario,
    parsedIntent?.recommendationIntent,
    parsedIntent?.scenario,
    categoryHint,
    condition?.scenario,
    condition?.intent,
    ...toDisplayList(condition?.categories),
    ...toDisplayList(parsedIntent?.categories),
  ].filter(Boolean).join(' '))

  return (
    text.includes('walk_healing') ||
    text.includes(normalizeLocationText('산책')) ||
    text.includes(normalizeLocationText('힐링')) ||
    text.includes(normalizeLocationText('공원'))
  )
}

const hasExplicitWalkCafeIntent = (query = '', parsedIntent = null) => {
  const text = normalizeLocationText([
    query,
    parsedIntent?.targetQuery,
    parsedIntent?.targetKeyword,
    ...toDisplayList(parsedIntent?.place_type_keywords),
    ...toDisplayList(parsedIntent?.kakaoKeywordCandidates),
  ].filter(Boolean).join(' '))

  return WALK_HEALING_CAFE_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
}

const getWalkHealingSuitability = ({
  place = {},
  query = '',
  parsedIntent = null,
} = {}) => {
  const placeText = getPlaceTextForRule(place)
  const explicitCafeIntent = hasExplicitWalkCafeIntent(query, parsedIntent)
  const hasNatureSignal = WALK_HEALING_ALLOWED_KEYWORDS.some((keyword) => {
    return placeText.includes(normalizeLocationText(keyword))
  })
  const hasCafeSignal = WALK_HEALING_CAFE_KEYWORDS.some((keyword) => {
    return placeText.includes(normalizeLocationText(keyword))
  })
  const blockedKeywords = WALK_HEALING_EXCLUDE_KEYWORDS.filter((keyword) => {
    return placeText.includes(normalizeLocationText(keyword))
  })
  const cafeOnlyBlocked = hasCafeSignal && !hasNatureSignal && !explicitCafeIntent
  const hardBlockedKeywords = blockedKeywords.filter((keyword) => {
    return !WALK_HEALING_CAFE_KEYWORDS.includes(keyword)
  })

  if (hardBlockedKeywords.length || cafeOnlyBlocked) {
    return {
      excluded: true,
      penalty: 90,
      bonus: 0,
      reason: hardBlockedKeywords[0] || 'cafe_without_walk_signal',
    }
  }

  if (!hasNatureSignal && hasCafeSignal && explicitCafeIntent) {
    return {
      excluded: false,
      penalty: 28,
      bonus: 0,
      reason: 'auxiliary_cafe_candidate',
    }
  }

  if (!hasNatureSignal) {
    return {
      excluded: true,
      penalty: 70,
      bonus: 0,
      reason: 'missing_walk_healing_signal',
    }
  }

  return {
    excluded: false,
    penalty: 0,
    bonus: 14,
    reason: null,
  }
}

const buildWalkHealingLocationQueries = (locationQuery = '') => {
  const locationText = getPlannerText(locationQuery)
  if (!locationText) return []

  return WALK_HEALING_LOCATION_QUERY_KEYWORDS.map((keyword) => {
    return `${locationText} ${keyword}`.trim()
  })
}

const buildWalkHealingFallbackStages = ({ locationQuery = '', includeCafe = false } = {}) => {
  const baseQueries = [
    ...WALK_HEALING_FALLBACK_QUERIES,
    ...(includeCafe ? ['산책 카페', '공원 카페', '카페'] : []),
  ]
  const locationQueries = buildWalkHealingLocationQueries(locationQuery)
  const stages = []

  WALK_HEALING_FALLBACK_RADII.forEach((radius) => {
    stages.push({
      name: `walk_base_${radius}`,
      radius,
      queries: baseQueries,
    })

    if (locationQueries.length) {
      stages.push({
        name: `walk_location_${radius}`,
        radius,
        queries: locationQueries,
      })
    }
  })

  return stages.map((stage) => ({
    ...stage,
    queries: [...new Set(stage.queries.filter(Boolean))],
  })).filter((stage) => stage.queries.length)
}

const getKakaoFallbackAllowedKeywords = ({
  recommendationIntent = '',
  categoryHint = '',
  query = '',
} = {}) => {
  const text = normalizeLocationText(`${recommendationIntent} ${categoryHint} ${query}`)
  const foodMenuKeywords = buildFoodMenuFallbackQueries({ query })

  if (recommendationIntent === 'restaurant' || categoryHint === 'restaurant') {
    return [
      '음식',
      '식당',
      '밥집',
      '맛집',
      '한식',
      '중식',
      '일식',
      '양식',
      '분식',
      '레스토랑',
      '브런치',
      '카페',
      '커피',
      '디저트',
      '베이커리',
      '빵집',
      '빵',
      ...foodMenuKeywords,
    ]
  }

  if (recommendationIntent === 'work_cafe' || categoryHint === 'cafe' || text.includes('카페')) {
    return ['카페', '커피', '디저트', '베이커리', '빵집', '빵', '스터디카페', ...foodMenuKeywords]
  }

  if (recommendationIntent === 'waiting_place') {
    return ['쉼터', '휴게', '도서관', '공원', '문화시설', '관광', '대합실', '터미널', '역사']
  }

  if (recommendationIntent === 'walk_healing') {
    return WALK_HEALING_ALLOWED_KEYWORDS
  }

  if (recommendationIntent === 'smoking_area' || categoryHint === 'smoking_area') {
    return ['흡연']
  }

  return []
}

const isRelevantKakaoFallbackCandidate = ({
  place,
  query = '',
  recommendationIntent = '',
  categoryHint = '',
} = {}) => {
  const placeText = getPlaceTextForRule(place)
  const allowedKeywords = getKakaoFallbackAllowedKeywords({
    recommendationIntent,
    categoryHint,
    query,
  })

  if (!allowedKeywords.length) {
    return true
  }

  const hasAllowedKeyword = allowedKeywords.some((keyword) => {
    return placeText.includes(normalizeLocationText(keyword))
  })

  if (recommendationIntent === 'walk_healing') {
    return !getWalkHealingSuitability({
      place,
      query,
    }).excluded
  }

  if (!hasAllowedKeyword) {
    return false
  }

  if (recommendationIntent === 'waiting_place') {
    const blockedKeywords = ['음식점', '식당', '술집', '주점', '노래방', '편의점']
    return !blockedKeywords.some((keyword) => placeText.includes(normalizeLocationText(keyword)))
  }

  return true
}

const filterKakaoFallbackRawPlaces = ({
  places = [],
  center = null,
  radius = SEARCH_RADIUS,
  query = '',
  recommendationIntent = '',
  categoryHint = '',
} = {}) => {
  return places.filter((place) => {
    const hasUrl = Boolean(place?.place_url || isKakaoPlaceId(place?.id))
    const lat = Number(place?.y)
    const lng = Number(place?.x)

    if (!hasUrl || !Number.isFinite(lat) || !Number.isFinite(lng)) {
      return false
    }

    if (center) {
      const distance = getDistanceMetersBetweenPlaces(center, { lat, lng })
      if (!Number.isFinite(distance) || distance > radius) {
        return false
      }
    }

    return isRelevantKakaoFallbackCandidate({
      place,
      query,
      recommendationIntent,
      categoryHint,
    })
  }).slice(0, KAKAO_FALLBACK_MAX_RESULTS)
}

const runKakaoRecommendationFallbackSearch = async ({
  placesService,
  query = '',
  data = {},
  parsedIntent = null,
  fallbackQueries = null,
  center,
  preferredTags = [],
  recommendationIntent = '',
  categoryHint = '',
  isAncillaryIntent = false,
  requestedConditions = [],
  radius = SEARCH_RADIUS,
} = {}) => {
  const fallbackSearchQueries = Array.isArray(fallbackQueries)
    ? fallbackQueries
    : buildKakaoRecommendationFallbackQueries({
      query,
      data,
      parsedIntent,
    })

  if (!fallbackSearchQueries.length) {
    return {
      results: [],
      rawCount: 0,
      dedupedCount: 0,
      queries: [],
      queryResultCounts: [],
      excludedCount: 0,
      dedupeExcludedCount: 0,
    }
  }

  const searchOptions = {
    location: new window.kakao.maps.LatLng(center.lat, center.lng),
    radius,
    sort: window.kakao.maps.services.SortBy.DISTANCE,
  }
  const rawPlaces = []
  const queryResultCounts = []
  const shouldLogMenuFallback = getMenuSearchProfile({ query, data }).menuIntent

  for (const [queryIndex, searchQuery] of fallbackSearchQueries.entries()) {
    const queryResults = await runKakaoKeywordSearchLimited(
      placesService,
      searchQuery,
      searchOptions,
      { maxPages: 1 },
    )

    queryResultCounts.push({
      query: searchQuery,
      count: queryResults.length,
    })
    const taggedQueryResults = queryResults.map((place) => ({
      ...place,
      __fallbackQuery: searchQuery,
      __fallbackQueryRank: queryIndex,
    }))

    if (import.meta.env.DEV && shouldLogMenuFallback) {
      const dedupedQueryResults = dedupeKakaoRawPlaces(taggedQueryResults)
      const filteredQueryResults = filterKakaoFallbackRawPlaces({
        places: dedupedQueryResults,
        center,
        radius,
        query,
        recommendationIntent,
        categoryHint,
      })

      console.debug('[메뉴 fallback query 결과]', {
        query: searchQuery,
        resultCount: queryResults.length,
        filteredCount: filteredQueryResults.length,
        dedupedCount: dedupedQueryResults.length,
      })
    }

    rawPlaces.push(...taggedQueryResults)
  }

  const rawCount = rawPlaces.length
  const dedupedRawPlaces = dedupeKakaoRawPlaces(rawPlaces)
  const filteredPlaces = filterKakaoFallbackRawPlaces({
    places: dedupedRawPlaces,
    center,
    radius,
    query,
    recommendationIntent,
    categoryHint,
  })
  const savedTagDataByExternalId = await searchKakaoSavedTags(filteredPlaces)

  return {
    results: convertKakaoPlaces(filteredPlaces, savedTagDataByExternalId, {
      query,
      center,
      preferredTags,
      recommendationIntent,
      categoryHint,
      isAncillaryIntent,
      fallbackCandidate: true,
      requestedConditions,
    }),
    rawCount,
    dedupedCount: dedupedRawPlaces.length,
    filteredCount: filteredPlaces.length,
    queries: fallbackSearchQueries,
    queryResultCounts,
    dedupeExcludedCount: Math.max(0, rawCount - dedupedRawPlaces.length),
    excludedCount: Math.max(0, dedupedRawPlaces.length - filteredPlaces.length),
    fallbackStage: 'default',
    radius,
    status: filteredPlaces.length ? 'success' : (rawCount > 0 ? 'filtered_empty' : 'empty'),
  }
}

const runWalkHealingFallbackSearch = async ({
  placesService,
  query = '',
  data = {},
  parsedIntent = null,
  center,
  preferredTags = [],
  categoryHint = '',
  isAncillaryIntent = false,
  requestedConditions = [],
} = {}) => {
  const locationQuery = getSearchPlanLocationQuery(parsedIntent)
  const stages = buildWalkHealingFallbackStages({
    locationQuery,
    includeCafe: hasExplicitWalkCafeIntent(query, parsedIntent),
  })
  const summary = {
    results: [],
    rawCount: 0,
    dedupedCount: 0,
    filteredCount: 0,
    queries: [],
    queryResultCounts: [],
    dedupeExcludedCount: 0,
    excludedCount: 0,
    fallbackStage: '',
    radius: WALK_HEALING_FALLBACK_RADII[0],
    status: 'empty',
  }

  for (const stage of stages) {
    const stageResult = await runKakaoRecommendationFallbackSearch({
      placesService,
      query,
      data,
      parsedIntent,
      fallbackQueries: stage.queries,
      center,
      preferredTags,
      recommendationIntent: 'walk_healing',
      categoryHint,
      isAncillaryIntent,
      requestedConditions,
      radius: stage.radius,
    })

    summary.rawCount += stageResult.rawCount || 0
    summary.dedupedCount += stageResult.dedupedCount || 0
    summary.filteredCount += stageResult.filteredCount || stageResult.results?.length || 0
    summary.dedupeExcludedCount += stageResult.dedupeExcludedCount || 0
    summary.excludedCount += stageResult.excludedCount || 0
    summary.queries.push(...(stageResult.queries || []))
    summary.queryResultCounts.push(...(stageResult.queryResultCounts || []))
    summary.fallbackStage = stage.name
    summary.radius = stage.radius
    summary.status = summary.rawCount > 0 ? 'filtered_empty' : 'empty'

    if (import.meta.env.DEV) {
      console.debug('[walk_healing 결과]', {
        rawCount: stageResult.rawCount || 0,
        filteredCount: stageResult.filteredCount || stageResult.results?.length || 0,
        excludedCount: stageResult.excludedCount || 0,
        fallbackStage: stage.name,
        radius: stage.radius,
        queries: stage.queries,
      })
    }

    if (stageResult.results?.length) {
      return {
        ...stageResult,
        fallbackStage: stage.name,
        radius: stage.radius,
        status: 'success',
      }
    }
  }

  return {
    ...summary,
    queries: [...new Set(summary.queries)],
    excludedCount: Math.max(summary.excludedCount, summary.dedupedCount - summary.filteredCount),
  }
}

const getDbCategoryText = (category) => {
  const categoryMap = {
    toilet: '화장실',
    freewifi: '무료 와이파이',
    smoking_area: '흡연구역',
    beach: '해수욕장',
    shelter: '쉼터',
    parking: '주차장',
    city_park: '공원',
    citypark: '공원',
    tourism: '관광지',
  }

  return categoryMap[category] || category || ''
}

const makeDbTags = (place) => {
  const tags = [
    makeTag('DB저장데이터', 'external_data'),
  ]

  const categoryText = getDbCategoryText(place.category)

  if (categoryText) {
    tags.push(makeTag(categoryText, 'category_rule'))
  }

  toArray(place.tags).forEach((tag) => {
    tags.push(makeTag(tag.name, tag.source))
  })

  return tags
}

const convertDbPlaces = (places, { requestedConditions = [] } = {}) => {
  return toArray(places).map((place) => {
    const externalId = place.external_id || place.externalId || null
    const isKakaoLocal = place.source === 'kakao_local'
    const sourceName = place.source_name || place.sourceName || ''
    const kakaoPlaceId = isKakaoLocal && isKakaoPlaceId(externalId) ? externalId : null
    const kakaoDetailUrl = getKakaoDetailUrl({
      ...place,
      externalId,
      sourceName,
      kakaoPlaceId,
    })
    const ancillaryAdjustment = getAncillaryPlaceAdjustment({
      place: {
        ...place,
        rawCategory: place.category,
      },
      query: place.name || '',
    })

    return mergeRequestedConditionReview({
      id: `db-${place.id}`,
      savedPlaceId: place.id,
      source: place.source,
      sourceName,
      externalId,
      kakaoPlaceId,
      rawCategory: place.category,
      name: place.name,
      category: getDbCategoryText(place.category),
      address: place.address,
      detailLocation: place.detail_location,
      lat: Number(place.lat),
      lng: Number(place.lng),
      distance: place.distance ?? null,
      phone: '',
      placeUrl: kakaoDetailUrl,
      kakaoPlaceUrl: getTextValue(place.kakao_place_url || place.kakaoPlaceUrl),
      kakaoUrl: getTextValue(place.kakao_url || place.kakaoUrl),
      detailUrl: getTextValue(place.detail_url || place.detailUrl),
      navigationUrl: `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`,
      markerColor: 'blue',
      searchSource: 'local_db',
      sourceLabel: 'DB추천',
      tags: makeDbTags(place),
      tagSource: 'DB 저장 데이터',
      dataQualityStatus: place.data_quality_status,
      dataQualityScore: place.data_quality_score,
      rawScores: place.raw?.scores || {},
      suggestedTags: place.suggested_tags || [],
      verifiedTags: place.verified_tags || [],
      warningTags: place.warning_tags || [],
      tagDetails: place.tag_details || [],
      matchedTagLabels: toDisplayList(place.matched_tag_labels),
      matchedSearchKeywords: toDisplayList(place.matched_search_keywords || place.matchedSearchKeywords),
      missingTagLabels: toDisplayList(place.missing_tag_labels),
      recommendationSourceLabel: getTextValue(place.source_label),
      recommendationConfidenceLabel: getTextValue(place.confidence_label),
      recommendationFallbackLabel: getTextValue(place.fallback_label),
      recommendationFallbackDescription: getTextValue(place.fallback_description),
      recommendationCaution: getTextValue(place.caution_message || place.caution),
      recommendationReason: getTextValue(
        place.recommendation_reason || place.recommend_reason || place.reason,
      ),
      personalizationBoost: Number(place.personalization_boost || 0),
      personalizationReasons: toDisplayList(place.personalization_reasons),
      recommendScore:
        place.raw?.scores?.recommendation_ready_score ??
        place.data_quality_score ??
        null,
      mainPlaceScore: ancillaryAdjustment.mainPlaceScore,
      ancillaryPlacePenalty: ancillaryAdjustment.ancillaryPlacePenalty,
      intentMismatchPenalty: ancillaryAdjustment.intentMismatchPenalty,
      isAncillaryPlace: ancillaryAdjustment.isAncillaryPlace,
    }, requestedConditions)
  })
}

const makeRecommendationTags = (place) => {
  const tags = [
    makeTag('DB추천', 'external_data'),
  ]

  const categoryText = getDbCategoryText(place.category)

  if (categoryText) {
    tags.push(makeTag(categoryText, 'category_rule'))
  }

  ;toArray(place.matched_tags || place.runtime_tags).forEach((tagName) => {
    tags.push(makeTag(tagName, 'checked'))
  })

  toArray(place.suggested_tags).forEach((tagName) => {
    tags.push(makeTag(tagName, 'blog_search'))
  })

  toArray(place.verified_tags).forEach((tagName) => {
    tags.push(makeTag(tagName, 'user_verified'))
  })

  toArray(place.warning_tags).forEach((tagName) => {
    tags.push(makeTag(tagName, 'warning_tags'))
  })

  return tags
}

const getPreferredTagMatchCount = (tagNames = [], preferredTags = []) => {
  const safePreferredTags = toArray(preferredTags)

  return toArray(tagNames).filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return safePreferredTags.some((preferredTag) => {
      const preferredText = normalizeLocationText(preferredTag)
      return tagText.includes(preferredText) || preferredText.includes(tagText)
    })
  }).length
}

const convertRecommendationPlaces = (
  places,
  {
    preferredTags = [],
    recommendationIntent = '',
    requestedConditions = [],
  } = {},
) => {
  return toArray(places).map((place) => {
    try {
    const externalId = place.external_id || place.externalId || null
    const isKakaoLocal = place.source === 'kakao_local'
    const sourceName = place.source_name || place.sourceName || ''
    const kakaoPlaceId = isKakaoLocal && isKakaoPlaceId(externalId) ? externalId : null
    const kakaoDetailUrl = getKakaoDetailUrl({
      ...place,
      externalId,
      sourceName,
      kakaoPlaceId,
    })
    const ancillaryAdjustment = getAncillaryPlaceAdjustment({
      place: {
        ...place,
        rawCategory: place.category,
      },
      query: place.name || '',
      recommendationIntent,
    })
    const preferredMatchCount = getPreferredTagMatchCount(
      [
        ...toArray(place.matched_tags),
        ...toArray(place.runtime_tags),
        ...toArray(place.suggested_tags),
        ...toArray(place.verified_tags),
      ],
      preferredTags,
    )

    return mergeRequestedConditionReview({
      id: `recommendation-${place.id}`,
      savedPlaceId: place.id,
      source: place.source,
      sourceName,
      externalId,
      kakaoPlaceId,
      rawCategory: place.category,
      name: place.name,
      category: getDbCategoryText(place.category),
      address: place.address,
      detailLocation: place.detail_location,
      lat: Number(place.lat),
      lng: Number(place.lng),
      distance: place.distance ?? place.distance_m ?? null,
      phone: '',
      placeUrl: kakaoDetailUrl,
      kakaoPlaceUrl: getTextValue(place.kakao_place_url || place.kakaoPlaceUrl),
      kakaoUrl: getTextValue(place.kakao_url || place.kakaoUrl),
      detailUrl: getTextValue(place.detail_url || place.detailUrl),
      navigationUrl: `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`,
      markerColor: '#7c3aed',
      searchSource: 'local_db',
      sourceLabel: 'DB추천',
      tags: makeRecommendationTags(place),
      tagSource: 'DB 추천 결과',
      dataQualityStatus: place.data_quality_status,
      dataQualityScore: place.data_quality_score,
      rawScores: place.raw_scores || {},
      suggestedTags: toArray(place.suggested_tags),
      verifiedTags: toArray(place.verified_tags),
      warningTags: toArray(place.warning_tags),
      tagDetails: toArray(place.tag_details),
      matchedTagLabels: toDisplayList(place.matched_tag_labels),
      missingTagLabels: toDisplayList(place.missing_tag_labels),
      recommendationSourceLabel: getTextValue(place.source_label),
      recommendationConfidenceLabel: getTextValue(place.confidence_label),
      recommendationFallbackLabel: getTextValue(place.fallback_label),
      recommendationFallbackDescription: getTextValue(place.fallback_description),
      recommendationCaution: getTextValue(place.caution_message || place.caution),
      recommendScore: Math.min(
        100,
        Number(place.score ?? place.data_quality_score ?? 0) + preferredMatchCount * 8,
      ),
      recommendationReason: getTextValue(
        place.recommendation_reason || place.recommend_reason || place.reason,
      ),
      personalizationBoost: Number(place.personalization_boost || 0),
      personalizationReasons: toDisplayList(place.personalization_reasons),
      matchedTags: toArray(place.matched_tags || place.runtime_tags),
      matchLevel: place.match_level,
      recommendationConfidence: place.confidence || place.recommendation_confidence,
      recommendationSourceType: place.source_type || '',
      fallbackLevel: place.fallback_level ?? null,
      recommendationIntent,
      preferredTags,
      preferredMatchCount,
      waitingPlacePenalty: place.score_breakdown?.unsuitable_place_penalty || 0,
      waitingPlaceExcluded: place.score_breakdown?.excluded_by_waiting_place || false,
      waitingPlacePenaltyReason: place.score_breakdown?.waiting_place_penalty_reason || null,
      resultType: 'db_recommendation',
      mainPlaceScore: ancillaryAdjustment.mainPlaceScore,
      ancillaryPlacePenalty: ancillaryAdjustment.ancillaryPlacePenalty,
      intentMismatchPenalty: ancillaryAdjustment.intentMismatchPenalty,
      isAncillaryPlace: ancillaryAdjustment.isAncillaryPlace,
    }, requestedConditions)
    } catch (error) {
      console.warn('[추천 결과 변환 실패]', { place, error })
      return null
    }
  }).filter(Boolean)
}

const assignMarkerLabels = (places) => {
  return places.map((place, index) => ({
    ...place,
    markerLabel: getMarkerLabel(index),
  }))
}

const resetAiWebSearchState = () => {
  aiWebSearchContext.value = null
  aiWebSearchAvailability.value = null
  aiWebSearchStatus.value = 'idle'
  aiWebSearchMessage.value = ''
  aiWebSearchCandidates.value = []
  webReferenceResults.value = []
  aiWebSearchLastResult.value = null
}

const stripAiWebSearchRequestWords = (query = '') => {
  return getTextValue(query)
    .replace(/\s*(찾아줘|찾아주세요|추천해줘|추천해주세요|알려줘|알려주세요)\s*$/g, '')
    .replace(/\s*(먹고\s*싶어|먹고싶어|먹을래|가고\s*싶어|가고싶어)\s*$/g, '')
    .trim()
}

const buildAiWebTargetQuery = ({
  rawTarget = '',
  originalQuery = '',
  menuKeywords = [],
  placeTypeKeywords = [],
}) => {
  const cleanedTarget = stripAiWebSearchRequestWords(rawTarget || originalQuery)
  const normalizedOriginal = normalizeLocationText(`${originalQuery} ${rawTarget}`)
  const firstMenu = getTextValue(menuKeywords[0])

  if (firstMenu) {
    const hasCafeType = placeTypeKeywords.some((keyword) => normalizeLocationText(keyword).includes('카페'))
    if (normalizedOriginal.includes('카페') && hasCafeType) {
      return `${firstMenu} 카페`
    }
    if (normalizedOriginal.includes('맛집')) {
      return `${firstMenu} 맛집`
    }
    return firstMenu
  }

  return cleanedTarget
}

const buildAiWebSearchPlanPayload = (parsedIntent = null, condition = {}, originalQuery = '') => {
  const source = parsedIntent || {}
  const menuKeywords = condition?.menu_keywords || source.menu_keywords || []
  const placeTypeKeywords = condition?.place_type_keywords || source.place_type_keywords || []
  const rawTarget = source.targetQuery || source.targetKeyword || condition?.keyword || originalQuery

  return {
    locationQuery: source.locationQuery || '',
    baseLocationQuery: source.baseLocationQuery || '',
    targetQuery: buildAiWebTargetQuery({
      rawTarget,
      originalQuery,
      menuKeywords,
      placeTypeKeywords,
    }),
    targetType: source.targetType || '',
    categoryHint: source.categoryHint || '',
    requestedConditions: Array.isArray(source.requestedConditions)
      ? source.requestedConditions
      : [],
    menu_keywords: menuKeywords,
    place_type_keywords: placeTypeKeywords,
  }
}

const getAiWebSearchLocationHint = (baseLabel = '', parsedIntent = null) => {
  const planLocation = parsedIntent?.locationQuery || parsedIntent?.baseLocationQuery || ''
  if (planLocation) return planLocation

  const label = getTextValue(baseLabel)
  if (!label || label.includes('현재') || label.includes('지도')) {
    return ''
  }
  return label.replace(/\s*기준\s*$/g, '').trim()
}

const resolveAiWebSearchLocationHint = async ({
  geocoder = null,
  center = null,
  baseLabel = '',
  parsedIntent = null,
}) => {
  const explicitHint = getAiWebSearchLocationHint(baseLabel, parsedIntent)
  if (explicitHint) return explicitHint

  return reverseGeocodeLocationHint(geocoder, center)
}

const setAiWebSearchContext = ({
  query,
  center,
  locationHint = '',
  searchPlan = null,
  condition,
  aiWebSearchStatusData,
  existingResultsSummary,
}) => {
  aiWebSearchContext.value = {
    query,
    lat: center?.lat ?? null,
    lng: center?.lng ?? null,
    locationHint,
    searchPlan: searchPlan || {},
    condition: condition || {},
    existingResultsSummary: existingResultsSummary || {},
  }
  aiWebSearchAvailability.value = aiWebSearchStatusData || {
    enabled: false,
    supported: false,
  }
  aiWebSearchStatus.value = 'idle'
  aiWebSearchMessage.value = ''
  aiWebSearchCandidates.value = []
  webReferenceResults.value = []
  aiWebSearchLastResult.value = null
}

const getSearchLogAuthToken = () => {
  try {
    return localStorage.getItem('authToken')
  } catch (error) {
    return ''
  }
}

const getFirstSearchLogList = (...values) => {
  for (const value of values) {
    const list = toDisplayList(value)
    if (list.length) return list
  }

  return []
}

const getSearchLogLocationHint = ({
  searchPlan = null,
  baseLabel = '',
  locationHint = '',
} = {}) => {
  const explicitLocation = getTextValue(
    searchPlan?.locationQuery ||
    searchPlan?.baseLocationQuery ||
    locationHint,
  )
  if (explicitLocation) return explicitLocation.slice(0, 100)

  const label = getTextValue(baseLabel)
    .replace(/\s*기준\s*$/g, '')
    .trim()

  if (!label || label.includes('현재 위치') || label.includes('현재 지도')) {
    return ''
  }

  return label.slice(0, 100)
}

const buildSearchPlanSnapshotForLog = (searchPlan = {}) => {
  const snapshot = {}
  const snapshotFields = [
    'locationQuery',
    'baseLocationQuery',
    'targetQuery',
    'targetType',
    'categoryHint',
    'confidence',
    'fallbackReason',
  ]

  snapshotFields.forEach((fieldName) => {
    const value = getTextValue(searchPlan?.[fieldName])
    if (value) snapshot[fieldName] = value
  })

  if (typeof searchPlan?.recommendationIntent === 'boolean') {
    snapshot.recommendationIntent = searchPlan.recommendationIntent
  } else if (searchPlan?.recommendationIntent) {
    snapshot.recommendationIntent = true
  }

  return snapshot
}

const getFiniteSearchLogCount = (value, fallback = 0) => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return fallback

  return Math.max(0, Math.trunc(numericValue))
}

const SEARCH_LOG_TEXT_LIMITS = {
  query: 255,
  searchMode: 50,
  scenario: 50,
  locationHint: 100,
  targetQuery: 255,
  categoryHint: 50,
}

const getSearchLogText = (value, maxLength) => {
  const text = getTextValue(value)
  return maxLength ? text.slice(0, maxLength) : text
}

const getSearchLogCoordinate = (value) => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return null

  return Number(numericValue.toFixed(6))
}

const buildSearchLogPayload = ({
  query,
  searchMode = '',
  scenario = '',
  locationHint = '',
  baseLabel = '',
  center = null,
  searchPlan = null,
  condition = {},
  results = [],
  dbResultCount = null,
  kakaoResultCount = null,
  aiWebResultCount = 0,
} = {}) => {
  const visibleResults = Array.isArray(results) ? results : []
  const normalizedQuery = getSearchLogText(
    query || searchPlan?.originalQuery || searchPlan?.normalizedQuery,
    SEARCH_LOG_TEXT_LIMITS.query,
  )
  const menuKeywords = getFirstSearchLogList(
    condition?.menu_keywords,
    condition?.menuKeywords,
    searchPlan?.menu_keywords,
    searchPlan?.menuKeywords,
    extractFoodMenuKeywords(normalizedQuery),
  )
  const explicitPlaceTypeKeywords = getFirstSearchLogList(
    condition?.place_type_keywords,
    condition?.placeTypeKeywords,
    searchPlan?.place_type_keywords,
    searchPlan?.placeTypeKeywords,
  )
  const placeTypeKeywords = explicitPlaceTypeKeywords.length
    ? explicitPlaceTypeKeywords
    : (
      menuKeywords.length || isCafeSearchKeyword(normalizedQuery)
        ? inferFoodPlaceTypeKeywords({
          query: normalizedQuery,
          menuKeywords,
          conditionPlaceTypes: explicitPlaceTypeKeywords,
        })
        : []
    )
  const fallbackDbCount = visibleResults.filter(isDbRecommendationResult).length
  const fallbackKakaoCount = visibleResults.filter(isKakaoCandidateResult).length

  return {
    query: normalizedQuery,
    search_mode: getSearchLogText(
      searchMode || searchPlan?.searchMode,
      SEARCH_LOG_TEXT_LIMITS.searchMode,
    ),
    scenario: getSearchLogText(
      scenario || condition?.scenario || searchPlan?.scenario,
      SEARCH_LOG_TEXT_LIMITS.scenario,
    ),
    location_hint: getSearchLogLocationHint({
      searchPlan,
      baseLabel,
      locationHint,
    }),
    lat: getSearchLogCoordinate(center?.lat),
    lng: getSearchLogCoordinate(center?.lng),
    target_query: getSearchLogText(
      condition?.targetQuery ||
      condition?.target_query ||
      searchPlan?.targetQuery ||
      searchPlan?.targetKeyword ||
      normalizedQuery,
      SEARCH_LOG_TEXT_LIMITS.targetQuery,
    ),
    category_hint: getSearchLogText(
      condition?.categoryHint ||
      condition?.category_hint ||
      searchPlan?.categoryHint,
      SEARCH_LOG_TEXT_LIMITS.categoryHint,
    ),
    requested_conditions: getFirstSearchLogList(
      condition?.requested_conditions,
      condition?.requestedConditions,
      searchPlan?.requested_conditions,
      searchPlan?.requestedConditions,
    ),
    menu_keywords: menuKeywords,
    place_type_keywords: placeTypeKeywords,
    preferred_tags: getFirstSearchLogList(
      condition?.preferred_tags,
      condition?.preferredTags,
      searchPlan?.preferred_tags,
      searchPlan?.preferredTags,
    ),
    negative_tags: getFirstSearchLogList(
      condition?.negative_tags,
      condition?.negativeTags,
      searchPlan?.negative_tags,
      searchPlan?.negativeTags,
    ),
    result_count: visibleResults.length,
    db_result_count: getFiniteSearchLogCount(dbResultCount, fallbackDbCount),
    kakao_result_count: getFiniteSearchLogCount(kakaoResultCount, fallbackKakaoCount),
    ai_web_result_count: getFiniteSearchLogCount(aiWebResultCount, 0),
    search_plan_snapshot: buildSearchPlanSnapshotForLog(searchPlan),
  }
}

const saveSearchLogSilently = async (payload) => {
  if (!getSearchLogAuthToken() || !payload?.query) return

  try {
    await saveSearchLog(payload)
  } catch (error) {
    if (import.meta.env.DEV) {
      console.debug('[SearchLog] save failed', {
        status: error?.response?.status || 'request_failed',
        responseData: error?.response?.data || null,
        payload,
      })
    }
  }
}

const setSearchResults = ({
  results,
  sourceLabel = '검색 결과',
  messageSuffix = '',
  status = '',
}) => {
  const normalizedResults = Array.isArray(results) ? results : []
  resetAiWebSearchState()
  activeMenuSearchProfile.value = null
  mainResults.value = normalizedResults
  fallbackResults.value = []
  syncLegacySearchResults()
  resultFilterMode.value = 'all'
  visibleCount.value = DISPLAY_BATCH_SIZE
  searchResultStatus.value = displayResults.value.length ? 'success' : (status || 'empty')
  if (displayResults.value.length) {
    clearMainSearchErrorState()
  }
  resultSourceLabel.value = sourceLabel
  resultMessageSuffix.value = messageSuffix
  placeListItemRefs.value = {}
  mapFitBoundsKey.value += 1
  activeResultView.value = displayResults.value.length ? 'results' : activeResultView.value
  isResultListCollapsed.value = false

  if (displayResults.value.length > 0) {
    clearNoResultLocationMessage()
    if (isSearchErrorMessage(locationMessage.value)) {
      locationMessage.value = ''
    }
  }
}

const clearSearchResults = () => {
  setSearchResults({
    results: [],
    sourceLabel: '검색 결과',
    messageSuffix: '',
  })
}

const showMoreResults = () => {
  visibleCount.value = Math.min(
    visibleCount.value + DISPLAY_BATCH_SIZE,
    displayResults.value.length,
  )
}

const searchSavedPlaces = async ({
  targetKeyword,
  center,
  radius = SEARCH_RADIUS,
  requestedConditions = [],
}) => {
  const data = await getSavedPlaces({
    q: targetKeyword,
    lat: center.lat,
    lng: center.lng,
    radius,
    limit: DB_SEARCH_RESULT_COUNT,
  })

  const allowedPlaces = (data.results || []).filter((place) => {
    return DB_MARKER_ALLOWED_CATEGORIES.includes(place.category)
  })

  return convertDbPlaces(allowedPlaces, { requestedConditions })
}

const searchAroundCenter = async ({
  placesService,
  targetKeyword,
  kakaoKeywordCandidates = [],
  center,
  bounds = null,
  radius = SEARCH_RADIUS,
  baseLabel,
  preferredTags = [],
  recommendationIntent = '',
}) => {
  loadingMessage.value = '주변 장소 검색 중'
  const centerLatLng = new window.kakao.maps.LatLng(center.lat, center.lng)
  const searchOptions = {
    location: centerLatLng,
    sort: window.kakao.maps.services.SortBy.DISTANCE,
  }

  if (bounds) {
    searchOptions.bounds = bounds
  } else {
    searchOptions.radius = radius
  }

  const searchKeywords = kakaoKeywordCandidates.length
    ? kakaoKeywordCandidates
    : [targetKeyword]
  const categoryHint = activeSearchPlan.value?.categoryHint || ''
  const isAncillaryIntent = activeSearchPlan.value?.isAncillaryIntent || false
  const requestedConditions = activeSearchPlan.value?.requestedConditions || []
  let kakaoPlaces = await runKakaoKeywordCandidateSearch(
    placesService,
    searchKeywords,
    searchOptions,
    { maxPages: 1 },
  )
  kakaoPlaces = await appendMainPlaceFallbackResults({
    placesService,
    places: kakaoPlaces,
    searchOptions,
    searchContext: {
      query: targetKeyword,
      categoryHint,
      recommendationIntent,
      isAncillaryIntent,
    },
    fallbackKeyword: activeSearchPlan.value?.mainPlaceFallbackKeyword || '',
  })

  const shouldUseDbPlaces = shouldAppendDbPlaces(targetKeyword)
  const [savedTagDataByExternalId, dbPlaces] = await Promise.all([
    searchKakaoSavedTags(kakaoPlaces),
    shouldUseDbPlaces
      ? searchSavedPlaces({
        targetKeyword,
        center,
        radius,
        requestedConditions,
      })
      : Promise.resolve([]),
  ])
  const kakaoResults = convertKakaoPlaces(
    kakaoPlaces,
    savedTagDataByExternalId,
    {
      query: targetKeyword,
      center,
      preferredTags,
      recommendationIntent,
      categoryHint,
      isAncillaryIntent,
      requestedConditions,
    },
  )
  const dedupedResults = shouldUseDbPlaces
    ? dedupeSearchResults(kakaoResults, dbPlaces)
    : kakaoResults
  const saveAroundCenterSearchLog = ({
    results = dedupedResults,
    dbCount = null,
    kakaoCount = kakaoResults.length,
  } = {}) => {
    saveSearchLogSilently(buildSearchLogPayload({
      query: activeSearchPlan.value?.originalQuery || mapSearchKeyword.value.trim() || targetKeyword,
      searchMode: bounds ? 'map_bounds_search' : (activeSearchPlan.value?.searchMode || 'keyword_search'),
      locationHint: getSearchLogLocationHint({
        searchPlan: activeSearchPlan.value,
        baseLabel,
      }),
      baseLabel,
      center,
      searchPlan: activeSearchPlan.value,
      condition: activeSearchPlan.value || {},
      results,
      dbResultCount: dbCount,
      kakaoResultCount: kakaoCount,
      aiWebResultCount: 0,
    }))
  }

  if (!dedupedResults.length) {
    clearSearchResults()
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 검색 결과가 없습니다.`
    saveAroundCenterSearchLog({
      results: [],
      dbCount: 0,
      kakaoCount: 0,
    })
    return
  }

  const enrichedCount = kakaoResults.filter((place) => place.savedPlaceId).length

  if (isCafeSearchKeyword(targetKeyword)) {
    setSearchResults({
      results: dedupedResults,
      sourceLabel: '카카오 결과',
      messageSuffix: enrichedCount ? `태그 보강 카페 ${enrichedCount}개` : '',
    })
    locationMessage.value = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 카카오 검색 결과를 표시했습니다.`
    saveAroundCenterSearchLog({
      results: dedupedResults,
      dbCount: 0,
      kakaoCount: kakaoResults.length,
    })
    return
  }

  if (shouldUseDbPlaces) {
    const displayedDbCount = dedupedResults.filter((place) => {
      return place.searchSource === 'local_db'
    }).length

    setSearchResults({
      results: dedupedResults,
      sourceLabel: '검색 결과',
      messageSuffix: `카카오 ${kakaoResults.length}개, DB ${displayedDbCount}개`,
    })
    locationMessage.value = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 검색 결과를 표시했습니다.`
    saveAroundCenterSearchLog({
      results: dedupedResults,
      dbCount: displayedDbCount,
      kakaoCount: kakaoResults.length,
    })
    return
  }

  setSearchResults({
    results: dedupedResults,
    sourceLabel: '카카오 결과',
  })
  locationMessage.value = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 카카오 검색 결과를 표시했습니다.`
  saveAroundCenterSearchLog({
    results: dedupedResults,
    dbCount: 0,
    kakaoCount: kakaoResults.length,
  })
}

const setBaseLocationFromKakaoPlace = (basePlace) => {
  const baseCenter = {
    lat: Number(basePlace.y ?? basePlace.lat),
    lng: Number(basePlace.x ?? basePlace.lng),
  }

  mapCenter.value = baseCenter

  currentLocationPlace.value = [
    {
      id: `base-location-${basePlace.id}`,
      name: `검색 기준 위치: ${basePlace.place_name}`,
      category: basePlace.category_name,
      address: basePlace.road_address_name || basePlace.address_name,
      lat: baseCenter.lat,
      lng: baseCenter.lng,
      distance: null,
      phone: basePlace.phone,
      placeUrl: basePlace.place_url,
      markerColor: 'green',
      searchSource: 'base_location',
      sourceLabel: '기준',
      tags: [makeTag('검색기준위치', 'category_rule')],
      tagSource: '카카오 API 장소 검색 결과',
    },
  ]

  return {
    center: baseCenter,
    label: `${basePlace.place_name} 기준`,
    place: basePlace,
  }
}

const normalizeLocationText = (text = '') => {
  return String(text).toLowerCase().replace(/\s+/g, '')
}

const getRegionTokens = (query) => {
  return String(query)
    .replace(/[^\w가-힣\s]/g, ' ')
    .split(/\s+/)
    .map((token) => token.trim())
    .filter((token) => /[시도군구읍면동리]$/.test(token) && token.length >= 2)
}

const hasRegionQualifier = (query) => {
  return getRegionTokens(query).some((token) => /[시도군구]$/.test(token))
}

const BASE_LOCATION_POI_KEYWORDS = [
  '역',
  '터미널',
  '대학교',
  '대학',
  '공항',
  '백화점',
  '시장',
  '거리',
  '광장',
  '공원',
  '병원',
  '해수욕장',
  '도서관',
  '구청',
  '시청',
  '군청',
  '상권',
  '번화가',
]
const BASE_LOCATION_TRANSPORT_KEYWORDS = [
  '역',
  '터미널',
  '공항',
  '정류장',
  '버스',
  '지하철',
  '전철',
]
const BASE_LOCATION_PLACE_CATEGORY_KEYWORDS = [
  '교통',
  '지하철',
  '전철',
  '터미널',
  '공항',
  '관광',
  '명소',
  '문화',
  '시설',
  '백화점',
  '시장',
  '상권',
  '도서관',
]
const BASE_LOCATION_REPRESENTATIVE_KEYWORDS = [
  '해수욕장',
  '광장',
  '공원',
  '대학교',
  '대학',
  '캠퍼스',
  '관광',
  '관광지',
  '명소',
  '문화',
  '시장',
  '백화점',
  '도서관',
]
const BASE_LOCATION_FACILITY_KEYWORDS = [
  '주차장',
  '공영주차장',
  '화장실',
  '공중화장실',
  '편의점',
  '미용실',
  '헤어',
  '카페',
  '커피',
  '음식점',
  '식당',
  '매장',
  '업체',
  '상점',
  '지점',
  '역점',
  '가맹점',
  '마트',
  '이마트24',
  '세븐일레븐',
  'cu',
  'gs25',
]
const BASE_LOCATION_REGION_KEYWORDS = [
  '동',
  '읍',
  '면',
  '리',
  '구',
  '군',
]

const hasPoiHint = (query) => {
  const queryText = normalizeLocationText(query)
  return BASE_LOCATION_POI_KEYWORDS.some((keyword) => {
    return queryText.includes(normalizeLocationText(keyword))
  })
}

const buildBaseLocationSearchQueries = (baseKeyword) => {
  const cleanedKeyword = baseKeyword.trim()
  return [
    cleanedKeyword,
    `${cleanedKeyword}역`,
    `${cleanedKeyword} 거리`,
    `${cleanedKeyword} 상권`,
    `${cleanedKeyword} 번화가`,
  ].filter((query, index, queries) => {
    return query && queries.indexOf(query) === index
  })
}

const getBaseLocationCandidateSearchText = (candidate = {}) => {
  return normalizeLocationText([
    candidate.place_name,
    candidate.category_name,
    candidate.address_name,
    candidate.road_address_name,
  ].filter(Boolean).join(' '))
}

const hasBaseLocationCandidateKeyword = (candidate = {}, keywords = []) => {
  const text = getBaseLocationCandidateSearchText(candidate)
  return keywords.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
}

const isFacilityBaseLocationCandidate = (candidate = {}) => {
  return hasBaseLocationCandidateKeyword(candidate, BASE_LOCATION_FACILITY_KEYWORDS)
}

const isRegionBaseLocationCandidate = (candidate = {}) => {
  if (candidate.source === 'address') {
    const addressText = candidate.address_name || candidate.place_name || ''
    const lastToken = String(addressText).trim().split(/\s+/).pop() || ''
    return /[동읍면리구군]$/.test(lastToken)
  }

  const nameText = normalizeLocationText(candidate.place_name)
  return BASE_LOCATION_REGION_KEYWORDS.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return nameText.endsWith(normalizedKeyword)
  })
}

const isTransportBaseLocationCandidate = (candidate = {}) => {
  if (isFacilityBaseLocationCandidate(candidate)) return false

  const nameText = normalizeLocationText(candidate.place_name)
  const categoryText = normalizeLocationText(candidate.category_name)

  return BASE_LOCATION_TRANSPORT_KEYWORDS.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return nameText.includes(normalizedKeyword) || categoryText.includes(normalizedKeyword)
  })
}

const isRepresentativeBaseLocationCandidate = (candidate = {}) => {
  if (isFacilityBaseLocationCandidate(candidate)) return false
  return hasBaseLocationCandidateKeyword(candidate, BASE_LOCATION_REPRESENTATIVE_KEYWORDS)
}

const getBaseLocationCandidatePriority = (candidate = {}) => {
  if (isFacilityBaseLocationCandidate(candidate)) return 5
  if (isTransportBaseLocationCandidate(candidate)) return 1
  if (isRegionBaseLocationCandidate(candidate)) return 2
  if (isRepresentativeBaseLocationCandidate(candidate)) return 3
  return 4
}

const getBaseLocationCandidatePriorityLabel = (priority) => {
  if (priority === 1) return '역/교통'
  if (priority === 2) return '지역'
  if (priority === 3) return '대표 장소'
  if (priority === 5) return '시설/매장'
  return '장소'
}

const getBaseCandidateKind = (candidate) => {
  if (candidate.source === 'address') {
    return isRegionBaseLocationCandidate(candidate) ? '지역' : '주소'
  }

  return getBaseLocationCandidatePriorityLabel(getBaseLocationCandidatePriority(candidate))
}

const isPlaceCandidate = (candidate) => {
  return candidate?.source !== 'address'
}

const hasBasePoiSignal = (candidate) => {
  const nameText = normalizeLocationText(candidate?.place_name)
  const categoryText = normalizeLocationText(candidate?.category_name)

  return BASE_LOCATION_POI_KEYWORDS.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return nameText.includes(normalizedKeyword) || categoryText.includes(normalizedKeyword)
  }) || BASE_LOCATION_PLACE_CATEGORY_KEYWORDS.some((keyword) => {
    return categoryText.includes(normalizeLocationText(keyword))
  })
}

const isExactPoiMatch = (candidate, query) => {
  if (!candidate) return false

  const queryText = normalizeLocationText(query)
  const nameText = normalizeLocationText(candidate.place_name)
  const sourceQueryText = normalizeLocationText(candidate.sourceQuery)

  if (!queryText || !nameText) return false

  if (nameText === queryText) return true

  if (sourceQueryText && nameText === sourceQueryText && hasBasePoiSignal(candidate)) {
    return true
  }

  if (hasPoiHint(query) && (nameText.includes(queryText) || queryText.includes(nameText))) {
    return true
  }

  return false
}

const isBroadAdministrativeAddress = (candidate) => {
  if (candidate.source !== 'address') return false

  const addressText = candidate.address_name || candidate.place_name
  const tokens = String(addressText).trim().split(/\s+/)
  const lastToken = tokens[tokens.length - 1] || ''

  return /[시도군구읍면]$/.test(lastToken) && !/[동리]$/.test(lastToken)
}

const normalizeKakaoBaseCandidate = (item, source, index, sourceQuery = '') => {
  const id = item.id || `${source}-${item.x}-${item.y}-${index}`
  const name = item.place_name || item.address_name || item.road_address?.address_name || item.address?.address_name || ''
  const address = item.road_address_name || item.address_name || item.address?.address_name || ''
  const lat = Number(item.y)
  const lng = Number(item.x)

  return {
    id: `base-candidate-${id}`,
    kakaoId: id,
    place_name: name,
    category_name: item.category_name || (source === 'address' ? '주소' : ''),
    address_name: address,
    road_address_name: item.road_address_name || '',
    phone: item.phone || '',
    place_url: item.place_url || '',
    x: item.x,
    y: item.y,
    lat,
    lng,
    source,
    sourceQuery,
    rank: index + 1,
    score: 0,
    scoreReasons: [],
    candidateKind: '',
  }
}

const scoreBaseLocationCandidate = (candidate, query) => {
  const queryText = normalizeLocationText(query)
  const nameText = normalizeLocationText(candidate.place_name)
  const addressText = normalizeLocationText(candidate.address_name || candidate.road_address_name)
  const categoryText = normalizeLocationText(candidate.category_name)
  const sourceQueryText = normalizeLocationText(candidate.sourceQuery)
  const baseLocationPriority = getBaseLocationCandidatePriority(candidate)
  const reasons = []
  let score = 0

  if (baseLocationPriority === 1) {
    score += 120
    reasons.push('교통 기준점 우선')
  } else if (baseLocationPriority === 2) {
    score += 90
    reasons.push('지역 기준점 우선')
  } else if (baseLocationPriority === 3) {
    score += 70
    reasons.push('대표 장소 우선')
  } else if (baseLocationPriority === 5) {
    score -= 90
    reasons.push('시설/매장 후순위')
  }

  if (nameText === queryText) {
    score += 45
    reasons.push('장소명 정확 일치')
  } else if (nameText && (nameText.includes(queryText) || queryText.includes(nameText))) {
    score += 30
    reasons.push('장소명 유사')
  }

  if (candidate.source !== 'address' && sourceQueryText && nameText.includes(sourceQueryText)) {
    score += 18
    reasons.push('확장 장소 검색어 일치')
  }

  if (addressText.includes(queryText)) {
    score += candidate.source === 'address' ? 18 : 24
    reasons.push('주소 일치')
  }

  const regionMatches = getRegionTokens(query).filter((token) => {
    return addressText.includes(normalizeLocationText(token))
  })

  if (regionMatches.length) {
    score += Math.min(regionMatches.length * 10, 25)
    reasons.push('지역명 일치')
  }

  if (BASE_LOCATION_POI_KEYWORDS.some((keyword) => {
    return nameText.includes(normalizeLocationText(keyword)) || categoryText.includes(normalizeLocationText(keyword))
  })) {
    score += 28
    reasons.push('기준 위치 POI')
  }

  if (BASE_LOCATION_PLACE_CATEGORY_KEYWORDS.some((keyword) => {
    return categoryText.includes(normalizeLocationText(keyword))
  })) {
    score += 18
    reasons.push('장소형 카테고리')
  }

  if (candidate.source !== 'address') {
    score += 16
    reasons.push('장소 후보')
  } else {
    score -= 10
    reasons.push('주소 후보')
  }

  if (candidate.source === 'address' && (!candidate.place_name || candidate.place_name === candidate.address_name)) {
    score -= 12
    reasons.push('주소명만 있음')
  }

  if (isBroadAdministrativeAddress(candidate)) {
    score -= 18
    reasons.push('넓은 행정구역')
  }

  score += Math.max(20 - candidate.rank * 2, 2)

  const distance = getDistanceMetersBetweenPlaces(mapCenter.value, candidate)
  if (Number.isFinite(distance)) {
    score += Math.max(8 - distance / 50000, 0)
  }

  return {
    ...candidate,
    score: Math.round(score),
    scoreReasons: reasons,
    baseLocationPriority,
    candidateKind: getBaseCandidateKind(candidate),
  }
}

const sortBaseLocationCandidates = (candidates = []) => {
  return [...candidates].sort((first, second) => {
    const firstPriority = first.baseLocationPriority || getBaseLocationCandidatePriority(first)
    const secondPriority = second.baseLocationPriority || getBaseLocationCandidatePriority(second)

    return (
      firstPriority - secondPriority ||
      second.score - first.score ||
      first.rank - second.rank
    )
  })
}

const dedupeBaseLocationCandidates = (candidates) => {
  const deduped = []
  const seen = new Set()

  candidates.forEach((candidate) => {
    if (!Number.isFinite(candidate.lat) || !Number.isFinite(candidate.lng)) return

    const key = [
      normalizeLocationText(candidate.place_name),
      Math.round(candidate.lat * 10000),
      Math.round(candidate.lng * 10000),
    ].join(':')

    if (seen.has(key)) return

    seen.add(key)
    deduped.push(candidate)
  })

  return deduped
}

const getAutoSelectedBaseCandidate = (candidates, query) => {
  if (!candidates.length) return null

  const [first, second] = candidates
  const queryLength = normalizeLocationText(query).length
  const shortAmbiguousQuery = (
    queryLength <= 3 &&
    !hasRegionQualifier(query) &&
    !hasPoiHint(query)
  )
  const hasAddressCandidatesFromMultipleRegions = new Set(
    candidates
      .filter((candidate) => candidate.source === 'address')
      .map((candidate) => {
        return String(candidate.address_name || candidate.place_name).split(/\s+/).slice(0, 2).join(' ')
      })
      .filter(Boolean),
  ).size > 1
  const scoreGap = second ? first.score - second.score : first.score
  const firstIsPlacePoi = isPlaceCandidate(first) && hasBasePoiSignal(first)
  const exactPoiMatch = isExactPoiMatch(first, query)
  const hasClearQuery = hasPoiHint(query) || hasRegionQualifier(query)

  const autoSelectConfidence = {
    exactPoiMatch,
    placePoiHighScore: firstIsPlacePoi && first.score >= 70,
    strongScoreGap: scoreGap >= (firstIsPlacePoi ? 10 : 18),
    clearPoiQueryMatch: hasPoiHint(query) && firstIsPlacePoi && (
      normalizeLocationText(first.place_name).includes(normalizeLocationText(query)) ||
      normalizeLocationText(query).includes(normalizeLocationText(first.place_name))
    ),
    clearRegionPlace: hasRegionQualifier(query) && firstIsPlacePoi && first.score >= 68,
  }

  if (
    shortAmbiguousQuery &&
    candidates.length > 1
  ) {
    return null
  }

  if (
    shortAmbiguousQuery &&
    hasAddressCandidatesFromMultipleRegions &&
    first.source === 'address'
  ) {
    return null
  }

  if (shortAmbiguousQuery && first.source === 'address' && first.candidateKind === '주소') {
    return null
  }

  if (
    autoSelectConfidence.exactPoiMatch &&
    firstIsPlacePoi &&
    first.score >= 62
  ) {
    return first
  }

  if (
    autoSelectConfidence.clearPoiQueryMatch &&
    autoSelectConfidence.placePoiHighScore
  ) {
    return first
  }

  if (
    autoSelectConfidence.clearRegionPlace &&
    autoSelectConfidence.strongScoreGap
  ) {
    return first
  }

  if (
    firstIsPlacePoi &&
    first.score >= (hasClearQuery ? 68 : 78) &&
    autoSelectConfidence.strongScoreGap
  ) {
    return first
  }

  return null
}

const collectBaseLocationCandidates = async ({
  placesService,
  geocoder,
  baseKeyword,
}) => {
  loadingMessage.value = '기준 위치 후보 확인 중'
  const keywordQueries = buildBaseLocationSearchQueries(baseKeyword)

  const [keywordResultGroups, addressResults] = await Promise.all([
    Promise.all(
      keywordQueries.map((query) => {
        return runKakaoKeywordSearchLimited(placesService, query, {
          sort: window.kakao.maps.services.SortBy.ACCURACY,
        }).then((results) => ({
          query,
          results,
        }))
      }),
    ),
    runKakaoAddressSearch(geocoder, baseKeyword),
  ])

  const candidates = [
    ...keywordResultGroups.flatMap((group) => {
      return group.results.map((item, index) => {
        return normalizeKakaoBaseCandidate(item, 'keyword', index, group.query)
      })
    }),
    ...addressResults.map((item, index) => normalizeKakaoBaseCandidate(item, 'address', index, baseKeyword)),
  ]

  return sortBaseLocationCandidates(
    dedupeBaseLocationCandidates(candidates)
      .map((candidate) => scoreBaseLocationCandidate(candidate, baseKeyword)),
  ).slice(0, 8)
}

const resolveBaseLocation = async ({
  placesService,
  geocoder,
  baseKeyword,
}) => {
  const candidates = await collectBaseLocationCandidates({
    placesService,
    geocoder,
    baseKeyword,
  })

  if (!candidates.length) {
    clearSearchResults()
    currentLocationPlace.value = []
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = `"${baseKeyword}" 위치를 찾지 못했습니다.`
    return null
  }

  const selectedCandidate = getAutoSelectedBaseCandidate(candidates, baseKeyword)

  if (selectedCandidate) {
    baseLocationCandidates.value = []
    pendingBaseLocationSearch.value = null
    return setBaseLocationFromKakaoPlace(selectedCandidate)
  }

  baseLocationCandidates.value = candidates
  loadingMessage.value = '기준 위치 선택 대기 중'
  locationMessage.value = '기준 위치가 여러 곳으로 검색되었습니다. 원하는 지역을 선택해 주세요.'
  return null
}

const getSearchPlanLocationQuery = (searchPlan = {}) => {
  return getPlannerText(
    searchPlan.locationQuery ||
    searchPlan.baseLocationQuery ||
    searchPlan.baseKeyword,
  )
}

const shouldResolveBaseLocation = (plan = {}, response = null) => {
  const responsePlan = response?.search_plan || plan?.conversationalSearchPlan?.search_plan || {}
  const locationQuery = getPlannerText(
    getSearchPlanValue(responsePlan, 'locationQuery', 'location_query', 'baseLocationQuery', 'base_location_query') ||
    getSearchPlanValue(plan, 'locationQuery', 'baseLocationQuery'),
  )

  if (!locationQuery) return false

  const hasExplicitLocation = getPlannerBoolean(
    getSearchPlanValue(responsePlan, 'has_explicit_location'),
    getPlannerBoolean(plan.hasExplicitLocation, Boolean(locationQuery)),
  )
  const locationResolutionRequired = getPlannerBoolean(
    getSearchPlanValue(responsePlan, 'location_resolution_required'),
    getPlannerBoolean(plan.locationResolutionRequired, Boolean(locationQuery)),
  )

  if (hasExplicitLocation === false || locationResolutionRequired === false) {
    return false
  }

  if (isNonRegionLocationText(locationQuery) || isRecommendationQueryText(locationQuery)) {
    return false
  }

  return true
}

const resolveSearchPlanLocationQuery = async ({
  placesService,
  geocoder,
  parsedIntent,
  originalQuery,
  pendingType = 'ai',
}) => {
  if (!shouldResolveBaseLocation(parsedIntent)) {
    return null
  }

  const locationQuery = getSearchPlanLocationQuery(parsedIntent)

  if (!locationQuery) {
    return null
  }

  pendingBaseLocationSearch.value = {
    type: pendingType,
    originalQuery,
    targetQuery: parsedIntent.targetQuery || parsedIntent.targetKeyword,
    parsedIntent: {
      ...parsedIntent,
      hasBaseLocation: true,
      baseKeyword: locationQuery,
      baseLocationQuery: locationQuery,
      locationQuery,
    },
  }

  const resolvedBase = await resolveBaseLocation({
    placesService,
    geocoder,
    baseKeyword: locationQuery,
  })

  if (import.meta.env.DEV) {
    console.debug('[Location resolve]', {
      locationQuery,
      resolved: Boolean(resolvedBase),
      fallbackReason: resolvedBase ? '' : 'location_query_not_resolved',
    })
  }

  if (!resolvedBase) {
    if (!baseLocationCandidates.value.length) {
      locationMessage.value = `"${locationQuery}" 위치를 찾지 못해 검색을 진행하지 않았습니다. 지역명이나 장소명을 다시 확인해 주세요.`
      pendingBaseLocationSearch.value = null
    }
    return null
  }

  pendingBaseLocationSearch.value = null

  return {
    ...resolvedBase,
    label: `${locationQuery} 기준`,
    locationQuery,
  }
}

const getKakaoKeywordForAiSearch = (data, query) => {
  const condition = getRecommendationConditionData(data)
  const categories = condition?.categories || []
  const categoryKeyword = categories
    .map((category) => CATEGORY_KAKAO_KEYWORDS[category])
    .find(Boolean)

  if (categoryKeyword) {
    return categoryKeyword
  }

  if (AI_SCENARIO_KAKAO_KEYWORDS[data?.scenario]) {
    return AI_SCENARIO_KAKAO_KEYWORDS[data.scenario]
  }

  return query
}

const runAiMapSearchAtCenter = async ({
  placesService,
  geocoder = null,
  originalQuery,
  targetQuery,
  center,
  baseLabel,
  parsedIntent = null,
}) => {
  loadingMessage.value = '상황 해석 중'
  sortMode.value = 'recommendation'
  const recommendationIntent = parsedIntent?.recommendationIntent || getRecommendationIntent(`${originalQuery} ${targetQuery}`)
  const preferredTags = parsedIntent?.preferredTags || getPreferredTagsForIntent(recommendationIntent)
  const requestedConditions = parsedIntent?.requestedConditions || []
  const categoryHint = parsedIntent?.categoryHint || ''
  const isAncillaryIntent = parsedIntent?.isAncillaryIntent || false
  const data = await aiSearchRecommendations({
    query: targetQuery,
    lat: center.lat,
    lng: center.lng,
    limit: DB_SEARCH_RESULT_COUNT,
  })

  mapAiParse.value = data.ai_parse || null

  if (data.blocked || data.ai_parse?.blocked || data.ai_parse?.is_searchable === false) {
    clearSearchResults()
    selectedPlace.value = null
    showDetailPanel.value = false
    detailFrameError.value = false
    locationMessage.value = data.message || data.ai_parse?.user_message || '요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.'
    return
  }

  const dbResults = Array.isArray(data.results) ? data.results : []
  const recommendationResults = convertRecommendationPlaces(dbResults, {
    preferredTags,
    recommendationIntent,
    requestedConditions,
  })
  if (recommendationResults.length) {
    setMainResults(recommendationResults)
    resultFilterMode.value = 'all'
    visibleCount.value = DISPLAY_BATCH_SIZE
    resultSourceLabel.value = 'AI 검색 결과'
    resultMessageSuffix.value = `DB ${recommendationResults.length}개 · ${getScenarioDisplayLabel(data.scenario)}`
    placeListItemRefs.value = {}
    mapFitBoundsKey.value += 1
    activeResultView.value = 'results'
    isResultListCollapsed.value = false
  }

  let kakaoResults = []
  let kakaoFallbackQueries = []
  let kakaoFallbackDebug = {
    queryResultCounts: [],
    excludedCount: 0,
    rawCount: 0,
    dedupeExcludedCount: 0,
  }
  const menuSearchProfile = getMenuSearchProfile({
    query: targetQuery,
    data,
  })
  const directMenuDbMatchCount = getDirectMenuDbMatchCount(
    recommendationResults,
    menuSearchProfile,
  )
  const dbCategoryFallbackCount = recommendationResults.filter((place) => {
    return isCategoryFallbackRecommendation(place)
  }).length
  const shouldRunFallback = shouldRunKakaoRecommendationFallback({
    dbResults: recommendationResults,
    query: targetQuery,
    recommendationIntent,
    categoryHint,
    data,
    menuProfile: menuSearchProfile,
  })
  kakaoFallbackQueries = buildKakaoRecommendationFallbackQueries({
    query: targetQuery,
    data,
    parsedIntent,
  })

  if (import.meta.env.DEV && menuSearchProfile.menuIntent) {
    console.debug('[메뉴 fallback 진입]', {
      query: targetQuery,
      scenario: data.scenario,
      isMenuSearch: menuSearchProfile.menuIntent,
      menuKeywords: menuSearchProfile.menuKeywords,
      placeTypeKeywords: menuSearchProfile.placeTypeKeywords,
      dbCount: recommendationResults.length,
      dbCategoryFallbackCount,
      directMenuMatchCount: directMenuDbMatchCount,
      shouldRunKakaoFallback: shouldRunFallback,
    })
  }

  if (import.meta.env.DEV) {
    console.debug('[카카오 fallback 시작]', {
      query: targetQuery,
      originalQuery,
      dbResultCount: recommendationResults.length,
      directMenuDbMatchCount,
      menuIntent: menuSearchProfile.menuIntent,
      shouldRunFallback,
      center,
      fallbackQueries: kakaoFallbackQueries,
    })
  }

  if (shouldRunFallback) {
    try {
      if (import.meta.env.DEV && menuSearchProfile.menuIntent) {
        console.debug('[메뉴 fallback 실행]', {
          queries: kakaoFallbackQueries,
          center,
          radius: SEARCH_RADIUS,
        })
      }

      loadingMessage.value = '부족한 추천 후보 보강 중'
      const fallbackData = recommendationIntent === 'walk_healing'
        ? await runWalkHealingFallbackSearch({
          placesService,
          query: targetQuery,
          data,
          parsedIntent,
          center,
          preferredTags,
          categoryHint,
          isAncillaryIntent,
          requestedConditions,
        })
        : await runKakaoRecommendationFallbackSearch({
          placesService,
          query: targetQuery,
          data,
          parsedIntent,
          fallbackQueries: kakaoFallbackQueries,
          center,
          preferredTags,
          recommendationIntent,
          categoryHint,
          isAncillaryIntent,
          requestedConditions,
        })
      kakaoResults = fallbackData.results
      kakaoFallbackQueries = fallbackData.queries
      kakaoFallbackDebug = {
        queryResultCounts: fallbackData.queryResultCounts || [],
        excludedCount: fallbackData.excludedCount || 0,
        rawCount: fallbackData.rawCount || 0,
        filteredCount: fallbackData.filteredCount || fallbackData.results?.length || 0,
        dedupeExcludedCount: fallbackData.dedupeExcludedCount || 0,
        fallbackStage: fallbackData.fallbackStage || '',
        radius: fallbackData.radius || SEARCH_RADIUS,
        status: fallbackData.status || '',
      }
    } catch (error) {
      console.warn('[카카오 fallback] 보조 후보 보강 실패', error)
      kakaoResults = []
      kakaoFallbackQueries = []
      kakaoFallbackDebug = {
        ...kakaoFallbackDebug,
        status: 'fallback_failed',
      }
    }
  }

  loadingMessage.value = '추천 결과 정리 중'
  setFallbackResults(kakaoResults)
  const finalResults = displayResults.value
  const hasAnyResults = finalResults.length > 0
  const willShowNoResultMessage = !hasAnyResults
  const recommendationCondition = getRecommendationConditionData(data)
  const aiWebSearchPlan = buildAiWebSearchPlanPayload(parsedIntent, recommendationCondition, originalQuery)
  const searchLogPlan = {
    ...(parsedIntent || {}),
    ...aiWebSearchPlan,
  }
  let aiWebSearchLocationHint = ''
  try {
    aiWebSearchLocationHint = await resolveAiWebSearchLocationHint({
      geocoder,
      center,
      baseLabel,
      parsedIntent,
    })
  } catch (error) {
    console.warn('[AI 웹 검색 위치 힌트] 보조 위치 확인 실패', error)
    aiWebSearchLocationHint = getAiWebSearchLocationHint(baseLabel, parsedIntent)
  }

  if (import.meta.env.DEV && menuSearchProfile.menuIntent) {
    console.debug('[메뉴 fallback 최종]', {
      finalMergedCount: kakaoResults.length,
      totalResultsAfterMerge: finalResults.length,
      kakaoFallbackSummaryCount: kakaoResults.length,
    })
  }

  if (import.meta.env.DEV) {
    console.debug('[카카오 fallback 결과]', {
      query: targetQuery,
      queryResultCounts: kakaoFallbackDebug.queryResultCounts,
      rawCandidateCount: kakaoFallbackDebug.rawCount,
      excludedCandidateCount: kakaoFallbackDebug.excludedCount,
      mergedFallbackCount: kakaoResults.length,
      totalMergedCount: finalResults.length,
      willShowNoResultMessage,
    })
  }

  if (import.meta.env.DEV && menuSearchProfile.menuIntent) {
    const dbCategoryFallbackCount = recommendationResults.filter((place) => {
      return isCategoryFallbackRecommendation(place)
    }).length

    console.debug('[메뉴 검색 결과 품질]', {
      query: targetQuery,
      scenario: data.scenario,
      menu_keywords: menuSearchProfile.menuKeywords,
      place_type_keywords: menuSearchProfile.placeTypeKeywords,
      db_count: recommendationResults.length,
      db_category_fallback_count: dbCategoryFallbackCount,
      direct_menu_match_count: directMenuDbMatchCount,
      should_run_kakao_fallback: shouldRunFallback,
      kakao_fallback_count: kakaoResults.length,
    })
  }

  if (import.meta.env.DEV) {
    console.debug('[카카오 fallback 병합]', {
      fallback_queries: kakaoFallbackQueries,
      query_result_counts: kakaoFallbackDebug.queryResultCounts,
      relevance_excluded_count: kakaoFallbackDebug.excludedCount,
      dedupe_excluded_count: kakaoFallbackDebug.dedupeExcludedCount,
      final_merged_count: kakaoResults.length,
    })
  }

  if (!hasAnyResults) {
    clearSearchResults()
    const emptyStatus = recommendationIntent === 'walk_healing' && kakaoFallbackDebug.rawCount > 0
      ? 'filtered_empty'
      : 'empty'
    searchResultStatus.value = emptyStatus
    setAiWebSearchContext({
      query: originalQuery,
      center,
      locationHint: aiWebSearchLocationHint,
      searchPlan: aiWebSearchPlan,
      condition: recommendationCondition,
      aiWebSearchStatusData: data.ai_web_search || null,
      existingResultsSummary: {
        db_count: 0,
        kakao_fallback_count: 0,
        total_count: 0,
        raw_total_count: 0,
        weak_match_count: 0,
        low_confidence_count: 0,
        strong_evidence_count: 0,
        web_helpful_topic: isAiWebSearchHelpfulTopic(originalQuery, recommendationCondition, aiWebSearchPlan),
        infra_blocked_topic: isAiWebSearchInfraBlockedTopic(originalQuery, recommendationCondition, aiWebSearchPlan),
        explicit_web_request: hasExplicitAiWebSearchRequest(originalQuery, recommendationCondition, aiWebSearchPlan),
      },
    })
    if (recommendationIntent === 'walk_healing') {
      const baseText = baseLabel || '현재 기준'
      locationMessage.value = emptyStatus === 'filtered_empty'
        ? `${baseText} 검색 결과는 있었지만 산책 목적에 맞는 후보를 찾지 못했습니다. 검색 반경을 넓히거나 다른 표현으로 다시 검색해 주세요.`
        : `${baseText} 산책 후보를 찾지 못했습니다. 지도 범위를 넓히거나 주변 공원, 강변, 산책로 같은 표현으로 다시 검색해 주세요.`
    } else {
      locationMessage.value = parsedIntent?.userIntentSummary
        ? `${parsedIntent.userIntentSummary} 조건에 맞는 추천 결과가 없습니다.`
        : `"${originalQuery}" 조건에 맞는 추천 결과가 없습니다.`
    }
    saveSearchLogSilently(buildSearchLogPayload({
      query: originalQuery,
      searchMode: parsedIntent?.searchMode || 'recommendation_query',
      scenario: data.scenario,
      locationHint: aiWebSearchLocationHint,
      baseLabel,
      center,
      searchPlan: searchLogPlan,
      condition: recommendationCondition,
      results: [],
      dbResultCount: 0,
      kakaoResultCount: 0,
      aiWebResultCount: 0,
    }))
    await logSearchResultState()
    return
  }

  resultFilterMode.value = 'all'
  visibleCount.value = DISPLAY_BATCH_SIZE
  searchResultStatus.value = 'success'
  clearMainSearchErrorState()
  resultSourceLabel.value = 'AI 검색 결과'
  resultMessageSuffix.value = `DB ${recommendationResults.length}개, 카카오 fallback ${kakaoResults.length}개 · ${getScenarioDisplayLabel(data.scenario)}`
  placeListItemRefs.value = {}
  mapFitBoundsKey.value += 1
  activeResultView.value = 'results'
  isResultListCollapsed.value = false
  await logSearchResultMerge({
    dbResults: recommendationResults,
    kakaoFallbackResults: kakaoResults,
    finalResults,
  })
  await logSearchResultState()
  activeMenuSearchProfile.value = menuSearchProfile.menuIntent ? menuSearchProfile : null
  setAiWebSearchContext({
    query: originalQuery,
    center,
    locationHint: aiWebSearchLocationHint,
    searchPlan: aiWebSearchPlan,
    condition: recommendationCondition,
    aiWebSearchStatusData: data.ai_web_search || null,
    existingResultsSummary: {
      db_count: menuSearchProfile.menuIntent ? directMenuDbMatchCount : recommendationResults.length,
      raw_db_count: recommendationResults.length,
      kakao_fallback_count: kakaoResults.length,
      total_count: (menuSearchProfile.menuIntent ? directMenuDbMatchCount : recommendationResults.length) + kakaoResults.length,
      raw_total_count: finalResults.length,
      direct_match_count: directMenuDbMatchCount,
      menu_intent: menuSearchProfile.menuIntent,
      weak_match_count: recommendationResults.filter((place) => {
        return (
          !getRecommendationMatchedLabels(place).length ||
          place.recommendationSourceType === 'db_category_fallback' ||
          place.matchLevel === 'category_distance_fallback'
        )
      }).length,
      low_confidence_count: getAiWebSearchLowConfidenceCount(finalResults),
      strong_evidence_count: getAiWebSearchStrongEvidenceCount(finalResults),
      web_helpful_topic: isAiWebSearchHelpfulTopic(originalQuery, recommendationCondition, aiWebSearchPlan),
      infra_blocked_topic: isAiWebSearchInfraBlockedTopic(originalQuery, recommendationCondition, aiWebSearchPlan),
      explicit_web_request: hasExplicitAiWebSearchRequest(originalQuery, recommendationCondition, aiWebSearchPlan),
    },
  })

  const intentSummaryMessage = parsedIntent?.userIntentSummary || ''
  locationMessage.value = intentSummaryMessage
    ? `${intentSummaryMessage} ${kakaoResults.length ? 'DB 추천이 부족해 카카오 fallback 후보를 함께 표시했습니다.' : 'DB 추천 결과를 표시했습니다.'}`
    : (
      kakaoResults.length
        ? `${baseLabel} "${originalQuery}" DB 추천이 부족해 카카오 fallback 후보를 함께 표시했습니다.`
        : `${baseLabel} "${originalQuery}" 자연어 조건의 DB 추천 결과를 표시했습니다.`
    )
  saveSearchLogSilently(buildSearchLogPayload({
    query: originalQuery,
    searchMode: parsedIntent?.searchMode || 'recommendation_query',
    scenario: data.scenario,
    locationHint: aiWebSearchLocationHint,
    baseLabel,
    center,
    searchPlan: searchLogPlan,
    condition: recommendationCondition,
    results: finalResults,
    dbResultCount: recommendationResults.length,
    kakaoResultCount: kakaoResults.length,
    aiWebResultCount: 0,
  }))
}

const applyAiWebSearchResult = (aiWebSearch = {}) => {
  const candidates = Array.isArray(aiWebSearch.candidates)
    ? dedupeAiWebSearchCandidates(aiWebSearch.candidates)
    : []
  aiWebSearchLastResult.value = aiWebSearch
  const hasMainResults = displayResults.value.length > 0

  if (!aiWebSearch.enabled || !aiWebSearch.supported) {
    aiWebSearchStatus.value = 'disabled'
    aiWebSearchCandidates.value = []
    webReferenceResults.value = []
    aiWebSearchMessage.value = getAiWebSearchStatusMessage(aiWebSearch)
    return
  }

  if (aiWebSearch.reason === 'manual_required') {
    aiWebSearchStatus.value = 'idle'
    aiWebSearchCandidates.value = []
    webReferenceResults.value = []
    aiWebSearchMessage.value = ''
    return
  }

  if (aiWebSearch.error === 'incomplete_response') {
    aiWebSearchStatus.value = 'empty'
    aiWebSearchCandidates.value = []
    webReferenceResults.value = []
    aiWebSearchMessage.value = getAiWebSearchStatusMessage(aiWebSearch)
    return
  }

  if (aiWebSearch.error && !candidates.length) {
    aiWebSearchStatus.value = hasMainResults ? 'empty' : 'error'
    aiWebSearchCandidates.value = []
    webReferenceResults.value = []
    aiWebSearchMessage.value = hasMainResults ? '' : getAiWebSearchStatusMessage(aiWebSearch)
    return
  }

  aiWebSearchCandidates.value = candidates
  webReferenceResults.value = candidates
  aiWebSearchStatus.value = candidates.length ? 'success' : 'empty'
  aiWebSearchMessage.value = getAiWebSearchStatusMessage(aiWebSearch)
}

const searchAiWebCandidatesManually = async () => {
  const context = aiWebSearchContext.value
  if (!context || aiWebSearchStatus.value === 'loading') return

  if (!aiWebSearchAvailability.value?.enabled || !aiWebSearchAvailability.value?.supported) {
    applyAiWebSearchResult({
      ...(aiWebSearchAvailability.value || {}),
      candidates: [],
    })
    return
  }

  const requestKey = getAiWebSearchRequestKey(context)
  const cachedResult = aiWebSearchClientCache.value[requestKey]
  if (cachedResult) {
    if (import.meta.env.DEV) {
      console.debug('[AI 웹 검색 응답]', {
        executed: false,
        reason: 'client_cached_result',
        error: cachedResult.error,
        candidate_count: Array.isArray(cachedResult.candidates) ? cachedResult.candidates.length : 0,
      })
    }
    applyAiWebSearchResult({
      ...cachedResult,
      executed: false,
      cached: true,
    })
    return
  }

  aiWebSearchStatus.value = 'loading'
  aiWebSearchMessage.value = 'AI 웹 검색 중입니다...'
  aiWebSearchLastResult.value = null

  if (import.meta.env.DEV) {
    console.debug('[AI 웹 검색 요청]', {
      query: context.query,
      location_hint: context.locationHint || '',
      search_plan: context.searchPlan || {},
      scenario: context.condition?.scenario,
      menu_keywords: context.condition?.menu_keywords || [],
      place_type_keywords: context.condition?.place_type_keywords || [],
    })
  }

  try {
    const data = await runAiWebSearch({
      query: context.query,
      lat: context.lat,
      lng: context.lng,
      locationHint: context.locationHint,
      searchPlan: context.searchPlan,
      condition: context.condition,
      existingResultsSummary: context.existingResultsSummary,
    })
    const aiWebSearch = data?.ai_web_search || {}
    aiWebSearchClientCache.value = {
      ...aiWebSearchClientCache.value,
      [requestKey]: aiWebSearch,
    }
    if (import.meta.env.DEV) {
      console.debug('[AI 웹 검색 응답]', {
        executed: aiWebSearch.executed,
        reason: aiWebSearch.reason,
        error: aiWebSearch.error,
        candidate_count: Array.isArray(aiWebSearch.candidates) ? aiWebSearch.candidates.length : 0,
      })
    }
    applyAiWebSearchResult(aiWebSearch)
  } catch (error) {
    console.error('AI 웹 검색 중 오류가 발생했습니다.')
    aiWebSearchCandidates.value = []
    webReferenceResults.value = []
    if (displayResults.value.length) {
      aiWebSearchStatus.value = 'empty'
      aiWebSearchMessage.value = ''
      return
    }

    aiWebSearchStatus.value = 'error'
    aiWebSearchMessage.value = 'AI 웹 검색 중 오류가 발생했습니다.'
  }
}

const getAiEvidenceSources = (candidate = {}) => {
  return Array.isArray(candidate.evidence_sources)
    ? candidate.evidence_sources.filter((source) => source?.url)
    : []
}

const getAiWebCandidateSourceUrl = (candidate = {}) => {
  return getTextValue(candidate.source_url || getAiEvidenceSources(candidate)[0]?.url)
}

const normalizeAiWebReferenceTitle = (candidate = {}) => {
  return normalizeLocationText(
    getTextValue(candidate.source_title || candidate.name)
      .replace(/[\[\](){}<>]/g, ' ')
      .replace(/[|｜].*$/g, ' ')
      .replace(/\s+/g, ' ')
      .trim(),
  )
}

const getAiWebTitleTokens = (candidate = {}) => {
  const title = getTextValue(candidate.source_title || candidate.name)
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .map((token) => normalizeLocationText(token))
    .filter((token) => token.length >= 2)

  return [...new Set(title)]
}

const hasSimilarAiWebReferenceTitle = (candidate, seenTokenSets) => {
  const tokens = getAiWebTitleTokens(candidate)
  if (!tokens.length) return false

  return seenTokenSets.some((seenTokens) => {
    const overlapCount = tokens.filter((token) => seenTokens.has(token)).length
    const smallerTokenCount = Math.min(tokens.length, seenTokens.size)
    return overlapCount >= 3 || (smallerTokenCount >= 2 && overlapCount >= smallerTokenCount)
  })
}

const dedupeAiWebSearchCandidates = (candidates = []) => {
  const seenUrls = new Set()
  const seenTitles = new Set()
  const seenTokenSets = []
  const deduped = []

  candidates.forEach((candidate) => {
    const url = getTextValue(candidate.source_url)
    const normalizedTitle = normalizeAiWebReferenceTitle(candidate)

    if (url && seenUrls.has(url)) return
    if (normalizedTitle && seenTitles.has(normalizedTitle)) return

    if (isAiWebSourceReference(candidate) && hasSimilarAiWebReferenceTitle(candidate, seenTokenSets)) {
      return
    }

    if (url) seenUrls.add(url)
    if (normalizedTitle) seenTitles.add(normalizedTitle)
    if (isAiWebSourceReference(candidate)) {
      seenTokenSets.push(new Set(getAiWebTitleTokens(candidate)))
    }
    deduped.push(candidate)
  })

  return deduped
}

const getAiWebCandidateSummary = (candidate = {}) => {
  return getTextValue(candidate.evidence_summary || candidate.recommendation_reason)
}

const isAiWebSourceReference = (candidate = {}) => {
  return candidate?.candidate_type === 'web_source_reference'
}

const getAiWebCandidateBadge = (candidate = {}) => {
  return isAiWebSourceReference(candidate)
    ? '참고 링크'
    : (candidate.category_hint || 'AI 웹 검색 후보')
}

const getAiWebSourceChannelLabel = (candidate = {}) => {
  const channel = getTextValue(candidate.source_channel)
  if (channel === 'local') return '네이버 지역'
  if (channel === 'blog') return '네이버 블로그'
  if (channel === 'webkr') return '네이버 웹문서'
  return '웹 검색'
}

const getAiWebCandidateCaution = (candidate = {}) => {
  if (isAiWebSourceReference(candidate)) {
    if (candidate.source_channel === 'local') {
      return '네이버 지역 검색 참고 결과입니다. 방문 전 상세 정보를 확인해 주세요.'
    }

    return '이 결과는 웹 검색 출처 기반 참고 정보이며, 실제 장소 정보는 방문 전 확인이 필요합니다.'
  }

  return candidate.caution_message || 'AI 웹 검색 기반 후보입니다. 위치, 운영 여부, 메뉴, 분위기는 방문 전 확인이 필요합니다.'
}

const getRegionSearchCoreKeyword = (targetQuery) => {
  const targetText = normalizeLocationText(targetQuery)

  const rules = [
    ['카페', '카페'],
    ['커피', '카페'],
    ['맛집', '맛집'],
    ['식당', '식당'],
    ['흡연', '흡연구역'],
    ['산책', '공원'],
    ['쉴', '쉼터'],
    ['쉬', '쉼터'],
    ['공원', '공원'],
    ['해수욕장', '해수욕장'],
    ['도서관', '도서관'],
    ['주차', '주차장'],
    ['화장실', '화장실'],
  ]

  const matched = rules.find(([keyword]) => {
    return targetText.includes(normalizeLocationText(keyword))
  })

  return matched?.[1] || targetQuery
}

const getKakaoResultRegionKey = (place) => {
  const address = place.road_address_name || place.address_name || ''
  const tokens = address.split(/\s+/).filter(Boolean)

  if (tokens.length >= 2) {
    return tokens.slice(0, 2).join(' ')
  }

  return tokens[0] || '지역 미상'
}

const getPlacesCenter = (places) => {
  const validPlaces = places
    .map((place) => ({
      lat: Number(place.y ?? place.lat),
      lng: Number(place.x ?? place.lng),
    }))
    .filter((place) => Number.isFinite(place.lat) && Number.isFinite(place.lng))

  if (!validPlaces.length) {
    return null
  }

  return {
    lat: validPlaces.reduce((sum, place) => sum + place.lat, 0) / validPlaces.length,
    lng: validPlaces.reduce((sum, place) => sum + place.lng, 0) / validPlaces.length,
  }
}

const groupKakaoPlacesByRegion = (places) => {
  const groupsByKey = new Map()

  places.forEach((place) => {
    const key = getKakaoResultRegionKey(place)
    const group = groupsByKey.get(key) || {
      key,
      places: [],
    }

    group.places.push(place)
    groupsByKey.set(key, group)
  })

  return [...groupsByKey.values()]
    .map((group) => ({
      ...group,
      center: getPlacesCenter(group.places),
    }))
    .sort((first, second) => second.places.length - first.places.length)
}

const shouldAskRegionCandidateSelection = (groups, totalCount) => {
  if (groups.length <= 1) return false

  const [first, second] = groups
  if (!first || !second) return false

  const topRatio = first.places.length / Math.max(totalCount, 1)
  return topRatio < 0.6 || first.places.length - second.places.length <= 2
}

const makeRegionCandidateFromGroup = (group, convertedResults) => {
  const center = group.center

  return {
    id: `region-candidate-${group.key}`,
    place_name: group.key,
    category_name: '지역',
    address_name: `${group.places.length}개 결과`,
    road_address_name: '',
    lat: center?.lat,
    lng: center?.lng,
    y: center?.lat,
    x: center?.lng,
    source: 'region',
    candidateKind: '지역',
    score: group.places.length,
    regionResults: convertedResults,
  }
}

const applySearchSafetyBlock = (data = {}) => {
  const aiParse = data.ai_parse || null
  const blocked = data.blocked || aiParse?.blocked || data.is_searchable === false || aiParse?.is_searchable === false

  if (!blocked) return false

  mapAiParse.value = aiParse
  clearSearchResults()
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false
  isSearchingMap.value = false
  loadingMessage.value = ''
  locationMessage.value = data.message || aiParse?.user_message || '요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.'
  return true
}

const ensureSearchSafety = async (query) => {
  const trimmedQuery = (query || '').trim()

  if (!trimmedQuery) return true

  loadingMessage.value = '요청 안전 확인 중'

  try {
    const data = await checkSearchSafety({ query: trimmedQuery })
    return !applySearchSafetyBlock(data)
  } catch (error) {
    if (import.meta.env.DEV) {
      console.warn('[SearchSafety] check failed', error)
    }

    applySearchSafetyBlock({
      blocked: true,
      reason: 'safety_check_unavailable',
      message: '요청을 안전하게 확인하지 못해 검색을 진행하지 않았습니다. 잠시 후 다시 시도해 주세요.',
      ai_parse: {
        blocked: true,
        is_searchable: false,
        block_reason: 'safety_check_unavailable',
      },
    })
    return false
  }
}

const runRegionMapSearch = async ({
  placesService,
  originalQuery,
  locationQuery,
  targetQuery,
  parsedIntent = null,
}) => {
  loadingMessage.value = '지역 장소 검색 중'
  const allowed = await ensureSearchSafety(originalQuery)

  if (!allowed) return

  loadingMessage.value = '지역 장소 검색 중'
  const recommendationIntent = parsedIntent?.recommendationIntent || getRecommendationIntent(`${originalQuery} ${targetQuery}`)
  const preferredTags = parsedIntent?.preferredTags || getPreferredTagsForIntent(recommendationIntent)
  const requestedConditions = parsedIntent?.requestedConditions || []
  const categoryHint = parsedIntent?.categoryHint || ''
  const isAncillaryIntent = parsedIntent?.isAncillaryIntent || false
  sortMode.value = recommendationIntent ? 'recommendation' : 'distance'
  const categoryKeyword = parsedIntent?.categoryKeyword || getRegionSearchCoreKeyword(targetQuery)
  const searchKeywords = [
    `${locationQuery} ${targetQuery}`.trim(),
    ...toDisplayList(parsedIntent?.kakaoKeywordCandidates).map((keyword) => `${locationQuery} ${keyword}`.trim()),
    `${locationQuery} ${categoryKeyword}`.trim(),
  ].filter((keyword, index, keywords) => keyword && keywords.indexOf(keyword) === index)
  let kakaoPlaces = await runKakaoKeywordCandidateSearch(placesService, searchKeywords, {
    sort: window.kakao.maps.services.SortBy.ACCURACY,
  }, { maxPages: 1 })
  kakaoPlaces = await appendMainPlaceFallbackResults({
    placesService,
    places: kakaoPlaces,
    searchOptions: {
      sort: window.kakao.maps.services.SortBy.ACCURACY,
    },
    searchContext: {
      query: originalQuery,
      categoryHint,
      recommendationIntent,
      isAncillaryIntent,
    },
    fallbackKeyword: parsedIntent?.mainPlaceFallbackKeyword || '',
  })

  if (!kakaoPlaces.length) {
    clearSearchResults()
    locationMessage.value = `"${originalQuery}" 검색 결과가 없습니다. 더 구체적인 지역명을 입력해 주세요.`
    saveSearchLogSilently(buildSearchLogPayload({
      query: originalQuery,
      searchMode: 'region_search',
      locationHint: locationQuery,
      searchPlan: parsedIntent,
      condition: parsedIntent || {},
      results: [],
      dbResultCount: 0,
      kakaoResultCount: 0,
      aiWebResultCount: 0,
    }))
    return
  }

  const savedTagDataByExternalId = await searchKakaoSavedTags(kakaoPlaces)
  const convertedResults = convertKakaoPlaces(kakaoPlaces, savedTagDataByExternalId, {
    query: originalQuery,
    preferredTags,
    recommendationIntent,
    categoryHint,
    isAncillaryIntent,
    requestedConditions,
  })
  const groups = groupKakaoPlacesByRegion(kakaoPlaces)

  if (shouldAskRegionCandidateSelection(groups, kakaoPlaces.length)) {
    baseLocationCandidates.value = groups
      .slice(0, 6)
      .map((group) => {
        const groupIds = new Set(group.places.map((place) => String(place.id)))
        const groupResults = convertedResults.filter((place) => {
          return groupIds.has(String(place.kakaoPlaceId))
        })

        return makeRegionCandidateFromGroup(group, groupResults)
      })
      .filter((candidate) => Number.isFinite(candidate.lat) && Number.isFinite(candidate.lng))

    pendingBaseLocationSearch.value = {
      type: 'region_results',
      originalQuery,
      targetQuery,
    }
    loadingMessage.value = '지역 선택 대기 중'
    locationMessage.value = '검색 결과가 여러 지역으로 나뉘었습니다. 원하는 지역을 선택해 주세요.'
    return
  }

  const dominantGroup = groups[0]
  const displayResults = dominantGroup
    ? convertedResults.filter((place) => {
      return dominantGroup.places.some((rawPlace) => String(rawPlace.id) === String(place.kakaoPlaceId))
    })
    : convertedResults
  const nextCenter = dominantGroup?.center || getPlacesCenter(kakaoPlaces)

  if (nextCenter) {
    mapCenter.value = nextCenter
  }

  setSearchResults({
    results: displayResults,
    sourceLabel: '지역 검색 결과',
    messageSuffix: `${locationQuery} · 카카오 ${displayResults.length}개`,
  })
  locationMessage.value = parsedIntent?.userIntentSummary
    ? `${parsedIntent.userIntentSummary} 지역 검색 결과를 표시했습니다.`
    : `"${originalQuery}" 지역 검색 결과를 표시했습니다.`
  saveSearchLogSilently(buildSearchLogPayload({
    query: originalQuery,
    searchMode: 'region_search',
    locationHint: locationQuery,
    center: nextCenter,
    searchPlan: parsedIntent,
    condition: parsedIntent || {},
    results: displayResults,
    dbResultCount: 0,
    kakaoResultCount: displayResults.length,
    aiWebResultCount: 0,
  }))
}

const dedupeKakaoRawPlaces = (places) => {
  const seen = new Set()
  const deduped = []

  places.forEach((place) => {
    const key = String(place.id || `${place.place_name}-${place.x}-${place.y}`)
    if (seen.has(key)) return

    seen.add(key)
    deduped.push(place)
  })

  return deduped
}

const searchKakaoPlaces = async ({ useMapBounds = false, searchPlanOverride = null } = {}) => {
  const keyword = mapSearchKeyword.value.trim()

  if (!keyword) {
    alert('지도에서 검색할 키워드를 입력해주세요.')
    return
  }

  if (!window.kakao || !window.kakao.maps || !window.kakao.maps.services) {
    alert('카카오 지도 서비스를 불러오는 중입니다. 잠시 후 다시 검색해주세요.')
    return
  }

  isSearchingMap.value = true
  loadingMessage.value = '요청 안전 확인 중'
  const allowed = await ensureSearchSafety(keyword)

  if (!allowed) return

  isSearchingMap.value = true
  loadingMessage.value = '주변 장소 검색 중'
  resetSearchStatusMessage('주변 장소를 검색하는 중입니다.')
  sortMode.value = 'distance'
  mapAiParse.value = null
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false

  const placesService = new window.kakao.maps.services.Places()
  const geocoder = new window.kakao.maps.services.Geocoder()
  const parsedKeyword = searchPlanOverride || buildSearchPlan(keyword)
  activeSearchPlan.value = parsedKeyword
  const targetKeyword = parsedKeyword.targetKeyword
  const searchBounds = useMapBounds ? getSearchBoundsFromViewport() : null
  const searchRadius = useMapBounds
    ? getViewportSearchRadius(mapCenter.value)
    : SEARCH_RADIUS

  try {
    if (useMapBounds) {
      currentLocationPlace.value = [
        {
          id: 'map-view-center',
          name: '현재 지도 중심',
          lat: mapCenter.value.lat,
          lng: mapCenter.value.lng,
          address: '',
          distance: null,
          markerColor: 'green',
          searchSource: 'map_view_center',
          sourceLabel: '기준',
          tags: [makeTag('지도화면', 'category_rule')],
        },
      ]

      await searchAroundCenter({
        placesService,
        targetKeyword,
        kakaoKeywordCandidates: parsedKeyword.kakaoKeywordCandidates,
        center: mapCenter.value,
        bounds: searchBounds,
        radius: searchRadius,
        baseLabel: '현재 지도 화면 기준',
      })

      return
    }

    baseLocationCandidates.value = []
    pendingBaseLocationSearch.value = null

    if (!parsedKeyword.hasBaseLocation || !shouldResolveBaseLocation(parsedKeyword)) {
      const currentContext = await getSearchCenterForRecommendation()
      await searchAroundCenter({
        placesService,
        targetKeyword,
        kakaoKeywordCandidates: parsedKeyword.kakaoKeywordCandidates,
        center: currentContext.center,
        baseLabel: currentContext.baseLabel,
      })

      return
    }

    pendingBaseLocationSearch.value = {
      type: 'map',
      originalQuery: keyword,
      targetQuery: targetKeyword,
      parsedIntent: parsedKeyword,
    }

    const resolvedBase = await resolveBaseLocation({
      placesService,
      geocoder,
      baseKeyword: parsedKeyword.baseKeyword,
    })

    if (!resolvedBase) return

    await searchAroundCenter({
      placesService,
      targetKeyword,
      kakaoKeywordCandidates: parsedKeyword.kakaoKeywordCandidates,
      center: resolvedBase.center,
      baseLabel: resolvedBase.label,
    })
    pendingBaseLocationSearch.value = null
  } catch (error) {
    console.error(error)
    clearSearchResults()
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = '장소 검색 중 오류가 발생했습니다.'
  } finally {
    if (!baseLocationCandidates.value.length) {
      isSearchingMap.value = false
      loadingMessage.value = ''
    }
  }
}

const searchAiRecommendationsOnMap = async (searchPlanOverride = null) => {
  const query = aiSearchKeyword.value.trim()

  if (!query) {
    alert('AI 검색에 사용할 자연어를 입력해주세요.')
    return
  }

  if (!window.kakao || !window.kakao.maps || !window.kakao.maps.services) {
    alert('카카오 지도 서비스를 불러오는 중입니다. 잠시 후 다시 검색해주세요.')
    return
  }

  isSearchingMap.value = true
  loadingMessage.value = '상황 해석 중'
  resetSearchStatusMessage('AI 추천 조건을 확인하는 중입니다.')
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false

  try {
    const placesService = new window.kakao.maps.services.Places()
    const geocoder = new window.kakao.maps.services.Geocoder()
    const parsedQuery = searchPlanOverride || buildSearchPlan(query)
    activeSearchPlan.value = parsedQuery
    let resolvedSearchCenter = mapCenter.value
    let baseLabel = '현재 지도 중심 기준'

    baseLocationCandidates.value = []
    pendingBaseLocationSearch.value = null

    const explicitLocationQuery = shouldResolveBaseLocation(parsedQuery)
      ? getSearchPlanLocationQuery(parsedQuery)
      : ''

    if (explicitLocationQuery) {
      const shouldRunAiRecommendation = Boolean(parsedQuery.recommendationIntent)
      const resolvedBase = await resolveSearchPlanLocationQuery({
        placesService,
        geocoder,
        parsedIntent: parsedQuery,
        originalQuery: query,
        pendingType: shouldRunAiRecommendation ? 'ai' : 'map',
      })

      if (!resolvedBase) return

      resolvedSearchCenter = resolvedBase.center
      baseLabel = resolvedBase.label

      const resolvedParsedQuery = {
        ...parsedQuery,
        hasBaseLocation: true,
        baseKeyword: explicitLocationQuery,
        baseLocationQuery: explicitLocationQuery,
        locationQuery: explicitLocationQuery,
      }

      if (!shouldRunAiRecommendation) {
        await searchAroundCenter({
          placesService,
          targetKeyword: resolvedParsedQuery.targetKeyword,
          kakaoKeywordCandidates: resolvedParsedQuery.kakaoKeywordCandidates,
          center: resolvedSearchCenter,
          baseLabel,
        })
        return
      }

      await runAiMapSearchAtCenter({
        placesService,
        geocoder,
        originalQuery: query,
        targetQuery: resolvedParsedQuery.targetQuery,
        center: resolvedSearchCenter,
        baseLabel,
        parsedIntent: resolvedParsedQuery,
      })
      return
    }

    if (parsedQuery.searchMode === 'region_search' && shouldResolveBaseLocation(parsedQuery)) {
      await runRegionMapSearch({
        placesService,
        originalQuery: query,
        locationQuery: parsedQuery.locationQuery,
        targetQuery: parsedQuery.targetQuery,
        parsedIntent: parsedQuery,
      })
      return
    }

    if (!parsedQuery.hasBaseLocation) {
      const currentContext = await getSearchCenterForRecommendation()
      resolvedSearchCenter = currentContext.center
      baseLabel = currentContext.baseLabel
    }

    if (parsedQuery.hasBaseLocation && shouldResolveBaseLocation(parsedQuery)) {
      pendingBaseLocationSearch.value = {
        type: 'ai',
        originalQuery: query,
        targetQuery: parsedQuery.targetQuery,
        parsedIntent: parsedQuery,
      }

      const resolvedBase = await resolveBaseLocation({
        placesService,
        geocoder,
        baseKeyword: parsedQuery.baseKeyword,
      })

      if (!resolvedBase) return

      resolvedSearchCenter = resolvedBase.center
      baseLabel = resolvedBase.label
      pendingBaseLocationSearch.value = null
    }

    await runAiMapSearchAtCenter({
      placesService,
      geocoder,
      originalQuery: query,
      targetQuery: parsedQuery.targetQuery,
      center: resolvedSearchCenter,
      baseLabel,
      parsedIntent: parsedQuery,
    })
  } catch (error) {
    console.error(error)
    if (displayResults.value.length) {
      searchResultStatus.value = 'success'
      clearMainSearchErrorState()
      return
    }

    mapAiParse.value = null
    clearSearchResults()
    setMainSearchError('검색 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.')
    selectedPlace.value = null
    showDetailPanel.value = false
  } finally {
    if (!baseLocationCandidates.value.length) {
      isSearchingMap.value = false
      loadingMessage.value = ''
    }
  }
}

const performUnifiedMapSearch = async ({
  useMapBounds = false,
  allowImplicitCurrentContext = false,
} = {}) => {
  const keyword = mapSearchKeyword.value.trim()

  if (!keyword) {
    alert('검색어를 입력해주세요.')
    return
  }

  conversationModeStarted.value = true
  const previousContext = getConversationalPreviousContext()
  const previousMainResults = [...mainResults.value]
  const previousFallbackResults = [...fallbackResults.value]
  const previousWebReferenceResults = [...webReferenceResults.value]
  const clarificationFollowUpPlan = useMapBounds
    ? null
    : buildClarificationFollowUpPlan(keyword)
  beginMainSearch({ preserveClarificationThread: Boolean(clarificationFollowUpPlan) })

  let conversationalPlan = clarificationFollowUpPlan || (
    useMapBounds
      ? null
      : await resolveConversationalSearchPlan(keyword, previousContext)
  )

  if (clarificationFollowUpPlan) {
    appendClarificationFollowUpThread(keyword, clarificationFollowUpPlan.message)
  } else if (shouldAskLocationChoiceBeforeSearch({
    conversationalPlan,
    rawQuery: keyword,
    allowImplicitCurrentContext,
  })) {
    conversationalPlan = makeLocationChoiceClarificationPlan(conversationalPlan, keyword)
  }

  if (
    conversationalPlan?.action &&
    conversationalPlan.action !== 'search'
  ) {
    if (
      conversationalPlan.action === 'ask_clarification' ||
      (conversationalPlan.action === 'refine_previous_search' && previousContext)
    ) {
      mainResults.value = previousMainResults
      fallbackResults.value = previousFallbackResults
      webReferenceResults.value = previousWebReferenceResults
      syncLegacySearchResults()
    }

    activeSearchPlan.value = adaptConversationalSearchPlan(conversationalPlan, keyword)
    const fallbackMessage = conversationalPlan.action === 'blocked'
      ? '해당 요청은 안전상 안내하기 어렵습니다.'
      : conversationalPlan.action === 'out_of_scope'
        ? '이 서비스는 생활 장소 추천을 위한 서비스라 해당 질문은 도와드리기 어렵습니다.'
        : conversationalPlan.action === 'refine_previous_search'
          ? (previousContext ? '이전 검색 조건을 반영했습니다.' : '이전 검색 결과를 조정하려면 기준이 되는 검색 결과가 필요합니다.')
          : '검색 기준을 조금 더 알려주시면 더 정확히 찾아드릴게요.'
    locationMessage.value = conversationalPlan.message ||
      conversationalPlan.clarification_question ||
      fallbackMessage
    if (conversationalPlan.action === 'ask_clarification') {
      setClarificationThread(keyword, conversationalPlan, locationMessage.value)
    } else {
      clearPendingClarification()
    }
    searchResultStatus.value = displayResults.value.length ? 'success' : 'idle'
    loadingMessage.value = ''
    isSearchingMap.value = false
    return
  }

  if (!clarificationFollowUpPlan) {
    clearPendingClarification()
  } else {
    pendingClarification.value = null
  }
  const parsedKeyword = conversationalPlan
    ? adaptConversationalSearchPlan(conversationalPlan, keyword)
    : buildSearchPlan(keyword)
  activeSearchPlan.value = parsedKeyword
  const searchMode = getUnifiedSearchMode(keyword, parsedKeyword, { useMapBounds })

  if (['region_search', 'recommendation_query'].includes(searchMode)) {
    sortMode.value = parsedKeyword.recommendationIntent
      ? 'recommendation'
      : 'distance'
    aiSearchKeyword.value = keyword
    await searchAiRecommendationsOnMap(parsedKeyword)
    return
  }

  sortMode.value = 'distance'
  await searchKakaoPlaces({ useMapBounds, searchPlanOverride: parsedKeyword })
}

const runAiPresetSearch = async (query) => {
  conversationModeStarted.value = true
  mapSearchKeyword.value = query
  activeResultView.value = 'results'
  isResultListCollapsed.value = false
  await nextTick()
  await performUnifiedMapSearch({ allowImplicitCurrentContext: true })
}

const runLandingPresetSearch = async (query) => {
  conversationModeStarted.value = true
  searchKeyword.value = query
  await nextTick()
  await handleSearch()
}

const searchCurrentMapView = () => {
  performUnifiedMapSearch({ useMapBounds: true })
}

const clearBaseLocationCandidateSelection = () => {
  baseLocationCandidates.value = []
  pendingBaseLocationSearch.value = null
  isSearchingMap.value = false
  loadingMessage.value = ''
}

const selectBaseLocationCandidate = async (candidate) => {
  const pendingSearch = pendingBaseLocationSearch.value

  if (!pendingSearch) {
    clearBaseLocationCandidateSelection()
    return
  }

  isSearchingMap.value = true
  loadingMessage.value = '주변 장소 검색 중'
  baseLocationCandidates.value = []
  pendingBaseLocationSearch.value = null

  try {
    const placesService = new window.kakao.maps.services.Places()
    const geocoder = new window.kakao.maps.services.Geocoder()
    const resolvedBase = setBaseLocationFromKakaoPlace(candidate)

    if (pendingSearch.type === 'map') {
      await searchAroundCenter({
        placesService,
        targetKeyword: pendingSearch.parsedIntent?.categoryKeyword || pendingSearch.targetQuery,
        kakaoKeywordCandidates: pendingSearch.parsedIntent?.kakaoKeywordCandidates || [],
        center: resolvedBase.center,
        baseLabel: resolvedBase.label,
      })
      return
    }

    if (pendingSearch.type === 'region_results') {
      const regionResults = candidate.regionResults || []
      setSearchResults({
        results: regionResults,
        sourceLabel: '지역 검색 결과',
        messageSuffix: `${candidate.place_name} · 카카오 ${regionResults.length}개`,
      })
      locationMessage.value = `${resolvedBase.label} "${pendingSearch.originalQuery}" 지역 검색 결과를 표시했습니다.`
      saveSearchLogSilently(buildSearchLogPayload({
        query: pendingSearch.originalQuery,
        searchMode: 'region_search',
        locationHint: resolvedBase.label,
        baseLabel: resolvedBase.label,
        center: resolvedBase.center,
        searchPlan: {
          locationQuery: resolvedBase.label,
          baseLocationQuery: resolvedBase.label,
          targetQuery: pendingSearch.targetQuery,
          targetType: '',
          categoryHint: '',
        },
        condition: {},
        results: regionResults,
        dbResultCount: 0,
        kakaoResultCount: regionResults.length,
        aiWebResultCount: 0,
      }))
      return
    }

    await runAiMapSearchAtCenter({
      placesService,
      geocoder,
      originalQuery: pendingSearch.originalQuery,
      targetQuery: pendingSearch.targetQuery,
      center: resolvedBase.center,
      baseLabel: resolvedBase.label,
      parsedIntent: pendingSearch.parsedIntent,
    })
  } catch (error) {
    console.error(error)
    clearSearchResults()
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = '선택한 기준 위치로 검색하는 중 오류가 발생했습니다.'
  } finally {
    isSearchingMap.value = false
    loadingMessage.value = ''
  }
}

const resetMapSearch = () => {
  conversationModeStarted.value = false
  mapSearchKeyword.value = ''
  aiSearchKeyword.value = ''
  mapAiParse.value = null
  activeSearchPlan.value = null
  clearPendingClarification()
  baseLocationCandidates.value = []
  pendingBaseLocationSearch.value = null
  loadingMessage.value = ''
  isSearchingMap.value = false
  currentLocationPlace.value = []
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false
  activeResultView.value = 'results'
  isResultListCollapsed.value = false
  clearSearchResults()
  locationMessage.value = '검색이 초기화되었습니다. 검색어를 입력하거나 지도를 이동한 뒤 다시 검색해보세요.'
}

const startNewConversationSearch = async () => {
  conversationModeStarted.value = false
  searchKeyword.value = ''
  mapSearchKeyword.value = ''
  aiSearchKeyword.value = ''
  mapAiParse.value = null
  activeSearchPlan.value = null
  activeMenuSearchProfile.value = null
  clearPendingClarification()
  baseLocationCandidates.value = []
  pendingBaseLocationSearch.value = null
  loadingMessage.value = ''
  isSearchingMap.value = false
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false
  activeTab.value = 'search'
  activeResultView.value = 'results'
  isResultListCollapsed.value = false
  clearSearchResults()
  locationMessage.value = '새 검색어를 입력해 주세요.'

  await focusPrimarySearchInput()
}

const getListMarkerTarget = (event) => {
  const markerElement = event?.currentTarget?.querySelector?.('.place-list-marker')
  const rect = markerElement?.getBoundingClientRect()

  if (!rect) return null

  return {
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
  }
}

const dispatchMascotFetch = (place, target = null) => {
  window.dispatchEvent(new CustomEvent('place-marker-fetch', {
    detail: {
      placeId: place?.id,
      placeName: place?.name,
      target,
    },
  }))
}

const updateMascotFetchTarget = (place, target = null) => {
  if (!selectedPlace.value || String(selectedPlace.value.id) !== String(place?.id)) return

  window.dispatchEvent(new CustomEvent('place-marker-fetch-update', {
    detail: {
      placeId: place?.id,
      placeName: place?.name,
      target,
    },
  }))
}

const selectPlace = (place, target = null) => {
  selectedPlace.value = place
  detailFrameError.value = false
  isPlaceDetailCollapsed.value = false
  dispatchMascotFetch(place, target)
}

const selectPlaceFromList = (place, event) => {
  selectedPlace.value = place
  detailFrameError.value = false
  isPlaceDetailCollapsed.value = false
  dispatchMascotFetch(place, getListMarkerTarget(event))
}

const getPlaceReportQuery = (place) => {
  const query = {
    reportType: 'tag_suggestion',
  }

  if (isDbPlace(place) && place?.id) {
    query.placeId = place.id
  }

  const name = getTextValue(place?.name)
  const category = getTextValue(place?.category)
  const address = getTextValue(place?.address || place?.detailLocation || place?.roadAddress)
  const lat = Number(place?.lat)
  const lng = Number(place?.lng)

  if (name) query.name = name
  if (category) query.category = category
  if (address) query.address = address
  if (Number.isFinite(lat)) query.lat = lat.toFixed(6)
  if (Number.isFinite(lng)) query.lng = lng.toFixed(6)

  return query
}

const goToPlaceReport = (place) => {
  router.push({
    name: 'place-report',
    query: getPlaceReportQuery(place),
  })
}

const closePlaceCard = () => {
  selectedPlace.value = null
  detailFrameError.value = false
  isPlaceDetailCollapsed.value = false
  window.dispatchEvent(new CustomEvent('place-marker-fetch-clear'))
}

const openDetailPanel = () => {
  if (!getPlaceDetailUrl(selectedPlace.value)) {
    alert('열 수 있는 상세 URL이 없는 장소입니다.')
    return
  }

  showDetailPanel.value = true
  detailFrameError.value = false
}

const closeDetailPanel = () => {
  showDetailPanel.value = false
  detailFrameError.value = false
}

const handleDetailFrameError = () => {
  detailFrameError.value = true
}
</script>

<template>
  <main
    class="home-page"
    :class="{
      'is-search-tab': activeTab === 'search',
      'is-map-tab': activeTab === 'map',
      'is-idle-experience': activeTab === 'search' && !hasSearchExperienceContent,
      'has-search-results': activeTab === 'search' && hasSearchExperienceContent,
      'is-conversation-mode': isConversationMode,
    }"
  >
    <header class="page-header">
      <div class="header-main">
        <div class="top-bar">
          <button
            type="button"
            class="tab-button"
            :class="{ active: activeTab === 'search' }"
            @click="activeTab = 'search'">
            검색장
          </button>

          <button
            type="button"
            class="tab-button"
            :class="{ active: activeTab === 'map' }"
            @click="openMapWithCurrentLocation">
            지도
          </button>
        </div>
      </div>
    </header>

    <section
      v-if="activeTab === 'search' && !hasSearchExperienceContent"
      class="search-section search-experience is-idle"
    >
      <div class="intro">
        <p class="eyebrow">상황 기반 장소 추천 지도 서비스</p>
        <h1>지금 필요한 장소를 검색해보세요</h1>
        <p class="description">
          예: 조용히 노트북 할 카페, 근처 화장실, 산책하기 좋은 곳
        </p>
      </div>

      <div class="search-box">
        <input
          ref="primarySearchInputRef"
          v-model="searchKeyword"
          type="text"
          placeholder="지금 어떤 장소가 필요하신가요?"
          @keyup.enter="handleSearch"
        />

        <button type="button" @click="handleSearch">
          검색
        </button>
      </div>

      <div class="landing-preset-buttons">
        <button
          v-for="preset in aiSearchPresets"
          :key="`landing-${preset.label}`"
          type="button"
          @click="runLandingPresetSearch(preset.query)"
        >
          {{ preset.label }}
        </button>
      </div>

      <p class="search-idle-hint">
        검색하면 지도와 추천 결과를 한 화면에서 함께 보여드릴게요.
      </p>
    </section>

    <section
      v-else-if="activeTab === 'map' || (activeTab === 'search' && hasSearchExperienceContent)"
      class="map-section-wrap search-experience"
      :class="{
        'has-results': activeTab === 'search' && hasSearchExperienceContent,
        'is-map-tab-view': activeTab === 'map',
      }"
    >
      <section
        class="conversation-search-card search-hero-card"
        :class="{
          'has-results': hasMapExperienceContent,
          'is-conversation-mode': isConversationMode,
        }"
      >
        <div class="conversation-card-top">
          <div class="conversation-copy">
            <p class="eyebrow">대화형 장소 추천 지도</p>
            <h1>{{ hasMapExperienceContent ? '필요한 장소를 계속 찾아볼까요?' : '지도에서 바로 찾아볼까요?' }}</h1>
          </div>

          <div class="map-header-actions">
            <button
              type="button"
              class="map-location-button"
              :disabled="isSearchingMap || isLocating"
              @click="openMapWithCurrentLocation"
            >
              {{ isLocating ? '확인 중...' : '현재 위치' }}
            </button>

            <button
              type="button"
              class="map-location-button"
              :disabled="isSearchingMap"
              @click="useDefaultMapLocation"
            >
              기본 위치
            </button>

            <button
              type="button"
              class="map-reset-button map-header-reset"
              :disabled="isSearchingMap"
              @click="resetMapSearch"
            >
              초기화
            </button>
          </div>
        </div>

        <div
          v-if="isConversationMode"
          class="conversation-compact-bar"
        >
          <span>현재 대화형 검색 중</span>
          <button
            type="button"
            :disabled="isSearchingMap"
            @click="startNewConversationSearch"
          >
            새 검색
          </button>
        </div>

        <form
          class="map-search-box ai-search-box search-panel"
          :class="{ 'search-panel--compact': isConversationMode }"
          @submit.prevent="performUnifiedMapSearch"
        >
          <label for="map-keyword-search">상황을 입력해 주세요</label>
          <input
            id="map-keyword-search"
            ref="primarySearchInputRef"
            v-model="mapSearchKeyword"
            type="text"
            placeholder="예: 소금빵 맛집, 조용히 작업할 카페, 비 오는데 쉴 곳"
          />

          <button
            type="submit"
            class="map-ai-button"
            :disabled="isSearchingMap || !mapSearchKeyword.trim()"
          >
            {{ isSearchingMap ? '검색 중...' : '검색' }}
          </button>

          <div class="ai-preset-buttons">
            <button
              v-for="preset in aiSearchPresets"
              :key="preset.label"
              type="button"
              :disabled="isSearchingMap"
              @click="runAiPresetSearch(preset.query)"
            >
              {{ preset.label }}
            </button>
          </div>
        </form>

        <div class="conversation-status">
          <div>
            <strong>{{ searchConversationTitle }}</strong>
            <p>{{ searchConversationDetail }}</p>
          </div>

          <div
            v-if="shouldShowClarificationThread"
            class="clarification-thread"
            aria-live="polite"
          >
            <div
              v-for="item in clarificationThread"
              :key="`${item.role}-${item.text}`"
              class="clarification-bubble"
              :class="`is-${item.role}`"
            >
              <span>{{ item.label }}</span>
              <p>{{ item.text }}</p>
            </div>
          </div>

          <form
            v-if="shouldShowFollowUpInput"
            class="clarification-follow-up"
            @submit.prevent="submitClarificationFollowUp"
            @keydown.stop
          >
            <input
              ref="followUpInputRef"
              v-model="followUpInput"
              type="text"
              placeholder="예: 현재 위치, 서면, 하단역"
              :disabled="isSearchingMap"
              @keydown.stop
            />
            <button
              type="submit"
              :disabled="isSearchingMap || !followUpInput.trim()"
            >
              보내기
            </button>
          </form>

          <div
            v-if="searchConversationChips.length"
            class="conversation-chip-list"
          >
            <span
              v-for="chip in searchConversationChips"
              :key="`${chip.label}-${chip.value}`"
            >
              {{ chip.label }}: {{ chip.value }}
            </span>
          </div>

          <p
            v-if="searchConversationNotice"
            class="conversation-notice"
          >
            {{ searchConversationNotice }}
          </p>
        </div>

        <div
          v-if="activeTab === 'search' && hasSearchExperienceContent"
          class="view-switch"
          :class="{ 'is-map-active': activeResultView === 'map' }"
          aria-label="결과와 지도 보기 전환"
        >
          <button
            type="button"
            :class="{ active: activeResultView === 'results' }"
            @click="setResultViewMode('results')"
          >
            결과 보기
          </button>

          <button
            type="button"
            :class="{ active: activeResultView === 'map' }"
            @click="setResultViewMode('map')"
          >
            지도 보기
          </button>
        </div>
      </section>

      <div v-if="mapParserStatus" class="map-parser-status" :class="mapParserStatus.className">
        <strong>{{ mapParserStatus.label }}</strong>
        <span>{{ mapParserStatus.detail }}</span>
      </div>

      <div
        v-if="searchPlanStatus"
        class="map-parser-status"
        :class="searchPlanStatus.className"
      >
        <strong>{{ searchPlanStatus.label }}</strong>
        <span>{{ searchPlanStatus.detail }}</span>
      </div>

      <section
        v-if="baseLocationCandidates.length"
        class="base-location-candidates"
      >
        <div class="candidate-header">
          <div>
            <strong>기준 위치가 여러 곳으로 검색되었습니다.</strong>
            <p>원하는 지역을 선택해 주세요.</p>
          </div>

          <button
            type="button"
            class="candidate-cancel-button"
            @click="clearBaseLocationCandidateSelection"
          >
            취소
          </button>
        </div>

        <div class="candidate-list">
          <button
            v-for="candidate in baseLocationCandidates"
            :key="candidate.id"
            type="button"
            class="candidate-button"
            @click="selectBaseLocationCandidate(candidate)"
          >
            <span>
              <strong>{{ candidate.place_name }}</strong>
              <small>{{ candidate.address_name || candidate.road_address_name }}</small>
            </span>
            <small class="candidate-kind">
              {{ candidate.candidateKind || '기준 위치' }}
              <span v-if="candidate.category_name"> · {{ candidate.category_name }}</span>
            </small>
          </button>
        </div>
      </section>

      <div
        class="map-content search-reveal-area"
        :class="{
          'has-result-list': displayResults.length || isSearchingMap || shouldShowAiWebSearchPanel,
          'has-selected-place': selectedPlace,
          'is-list-collapsed': isResultListCollapsed,
          'is-result-focused': activeResultView === 'results',
          'is-map-focused': activeResultView === 'map',
        }"
      >
        <aside
          v-if="displayResults.length || isSearchingMap || shouldShowAiWebSearchPanel"
          class="place-list-panel"
          :class="{ 'is-collapsed': isResultListCollapsed }"
        >
          <div class="place-list-top">
            <div>
              <p class="place-list-label">검색 결과</p>
              <h2>{{ isSearchingMap ? loadingMessage : (resultCountText || '추천 결과 보강') }}</h2>
            </div>

            <button
              type="button"
              class="panel-toggle-button"
              @click="toggleResultListPanel"
            >
              {{ isResultListCollapsed ? '펼치기' : '접기' }}
            </button>
          </div>

          <div
            v-if="displayResults.length && !isSearchingMap && !isResultListCollapsed"
            class="result-controls"
          >
            <div class="result-filter-buttons" aria-label="결과 필터">
              <button
                v-for="filterOption in RESULT_FILTER_OPTIONS"
                :key="filterOption.value"
                type="button"
                class="result-filter-button"
                :class="{ active: resultFilterMode === filterOption.value }"
                @click="setResultFilterMode(filterOption.value)"
              >
                {{ filterOption.label }}
              </button>
            </div>

            <label class="result-sort-select">
              <span>정렬</span>
              <select v-model="sortMode">
                <option
                  v-for="sortOption in RESULT_SORT_OPTIONS"
                  :key="sortOption.value"
                  :value="sortOption.value"
                >
                  {{ sortOption.label }}
                </option>
              </select>
            </label>
          </div>

          <section
            v-if="shouldShowAiWebSearchPanel"
            class="ai-web-search-panel"
            :class="`is-${aiWebSearchStatus}`"
          >
            <div class="ai-web-search-heading">
              <div>
                <strong>AI 웹 검색 참고 결과</strong>
                <span>웹 검색을 사용하므로 시간이 조금 걸릴 수 있습니다.</span>
              </div>

              <button
                v-if="aiWebSearchAvailability?.enabled && aiWebSearchAvailability?.supported"
                type="button"
                class="ai-web-search-button"
                :disabled="aiWebSearchButtonDisabled"
                @click="searchAiWebCandidatesManually"
              >
                {{ aiWebSearchStatus === 'loading' ? '검색 중...' : '웹 검색 참고 링크 보기' }}
              </button>
            </div>

            <p
              v-if="!aiWebSearchAvailability?.enabled || !aiWebSearchAvailability?.supported"
              class="ai-web-search-message"
            >
              AI 웹 검색 기능이 현재 비활성화되어 있습니다.
            </p>

            <p
              v-else-if="aiWebSearchMessage"
              class="ai-web-search-message"
            >
              {{ aiWebSearchMessage }}
            </p>

            <p
              v-if="IS_DEV && aiWebSearchDebugText"
              class="ai-web-search-message ai-web-search-debug"
            >
              {{ aiWebSearchDebugText }}
            </p>

            <div
              v-if="aiWebSearchCandidates.length"
              class="ai-web-search-candidates"
            >
              <article
                v-if="aiWebSearchSummary"
                class="ai-web-search-summary-card"
              >
                <strong>{{ aiWebSearchSummary.title || 'AI 웹 검색 요약' }}</strong>
                <p>{{ aiWebSearchSummary.main_text }}</p>
                <p
                  v-if="Array.isArray(aiWebSearchSummary.keywords) && aiWebSearchSummary.keywords.length"
                  class="ai-web-search-summary-keywords"
                >
                  키워드: {{ aiWebSearchSummary.keywords.join(', ') }}
                </p>
                <small>{{ aiWebSearchSummary.caution || '웹 검색 출처 기반 참고 정보이며, 실제 정보는 방문 전 확인이 필요합니다.' }}</small>
              </article>

              <div class="ai-web-search-evidence-heading">
                근거 링크 {{ aiWebSearchEvidenceCandidates.length }}개
              </div>

              <article
                v-for="(candidate, index) in aiWebSearchEvidenceCandidates"
                :key="`ai-web-${candidate.name}-${index}`"
                class="ai-web-search-candidate"
                :class="{ 'is-reference': isAiWebSourceReference(candidate) }"
              >
                <div
                  v-if="isAiWebSourceReference(candidate)"
                  class="ai-web-search-reference-badges"
                >
                  <span>참고 링크</span>
                  <span>{{ getAiWebSourceChannelLabel(candidate) }}</span>
                </div>

                <div class="ai-web-search-candidate-title">
                  <a
                    v-if="getAiWebCandidateSourceUrl(candidate)"
                    :href="getAiWebCandidateSourceUrl(candidate)"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {{ candidate.name }}
                  </a>
                  <strong v-else>{{ candidate.name }}</strong>
                  <span v-if="!isAiWebSourceReference(candidate)">{{ getAiWebCandidateBadge(candidate) }}</span>
                </div>

                <p
                  v-if="candidate.address_hint"
                  class="ai-web-search-hint ai-web-search-address"
                >
                  {{ candidate.address_hint }}
                </p>

                <p
                  v-else-if="isAiWebSourceReference(candidate) && candidate.source_title && candidate.source_title !== candidate.name"
                  class="ai-web-search-hint"
                >
                  {{ candidate.source_title }}
                </p>

                <p
                  v-if="getAiWebCandidateSummary(candidate)"
                  class="ai-web-search-summary"
                >
                  {{ getAiWebCandidateSummary(candidate) }}
                </p>

                <div
                  v-if="getAiEvidenceSources(candidate).length"
                  class="ai-web-search-sources"
                >
                  <a
                    v-for="(source, sourceIndex) in getAiEvidenceSources(candidate)"
                    :key="`ai-web-source-${index}-${sourceIndex}`"
                    :href="source.url"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    출처 보기
                  </a>
                </div>

                <p class="ai-web-search-caution">
                  {{ getAiWebCandidateCaution(candidate) }}
                </p>
              </article>
            </div>
          </section>

          <div v-if="isResultListCollapsed" class="collapsed-panel-summary">
            {{ displayResults.length }}개
          </div>

          <template v-else>
          <div class="place-list">
            <div v-if="isSearchingMap" class="skeleton-list">
              <article
                v-for="index in 5"
                :key="`skeleton-${index}`"
                class="skeleton-card"
              >
                <span class="skeleton-marker"></span>
                <span class="skeleton-main">
                  <span class="skeleton-line skeleton-title"></span>
                  <span class="skeleton-line skeleton-meta"></span>
                  <span class="skeleton-line skeleton-address"></span>
                </span>
              </article>
            </div>

            <template v-else>
              <div
                v-if="!searchedPlaces.length && displayResults.length"
                class="filtered-empty-message"
              >
                선택한 필터에 맞는 결과가 없습니다.
              </div>

              <article
                v-for="place in searchedPlaces"
                :key="place.id"
                :ref="(el) => setPlaceListItemRef(el, place.id)"
                class="place-list-item"
                :class="{ active: selectedPlace && selectedPlace.id === place.id }"
              >
                <button
                  type="button"
                  class="place-list-select-button"
                  @click="selectPlaceFromList(place, $event)"
                >
                  <span class="place-list-marker" :class="getPlaceSourceClass(place)">
                    {{ place.markerLabel }}
                  </span>

                  <span class="place-list-main">
                    <span class="place-list-name-row">
                      <span class="place-list-name">
                        {{ place.name }}
                      </span>

                      <span class="source-badge" :class="getPlaceSourceClass(place)">
                        {{ getPlaceSourceText(place) }}
                      </span>
                    </span>

                    <span class="place-list-meta">
                      <small v-if="place.category">
                        {{ place.category }}
                      </small>

                      <small v-if="getDistanceText(place)">
                        {{ getDistanceText(place) }}
                      </small>

                      <small v-if="isRecommendationPlace(place) && getRecommendScore(place)">
                        추천 점수 {{ getRecommendScore(place) }}
                      </small>

                      <small v-if="isRecommendationPlace(place) && getPersonalizationBoost(place) > 0">
                        {{ getPersonalizationBoostText(place) }}
                      </small>

                    </span>

                    <span
                      v-if="isRecommendationPlace(place) && (getRecommendationMetaText(place) || getRecommendationFallbackText(place))"
                      class="place-list-recommend-meta"
                    >
                      <small v-if="getRecommendationMetaText(place)">
                        {{ getRecommendationMetaText(place) }}
                      </small>
                      <small v-if="getRecommendationFallbackText(place)">
                        {{ getRecommendationFallbackText(place) }}
                      </small>
                    </span>

                    <span
                      v-if="isRecommendationPlace(place) && getPersonalizationBoost(place) > 0"
                      class="place-list-personalization personalization-badge"
                    >
                      최근 선호 반영
                    </span>

                    <span
                      v-if="isRecommendationPlace(place) && getRecommendationReasonSummary(place)"
                      class="place-list-reason"
                    >
                      {{ getRecommendationReasonSummary(place) }}
                    </span>

                    <span
                      v-if="isRecommendationPlace(place) && getPersonalizationReasons(place).length"
                      class="personalization-reasons"
                    >
                      <span class="personalization-reasons-label">최근 선호</span>
                      <span
                        v-for="reason in getRecommendationPreviewLabels(getPersonalizationReasons(place), 3)"
                        :key="`personalization-${place.id}-${reason}`"
                        class="personalization-reason-chip"
                      >
                        {{ reason.replace(/^최근 자주 찾은\s*/, '') }}
                      </span>
                    </span>

                    <span
                      v-if="isRecommendationPlace(place) && getRecommendationMatchedLabels(place).length"
                      class="place-list-condition-group"
                    >
                      <span class="place-list-condition-label">일치 조건</span>
                      <span
                        v-for="(label, index) in getRecommendationPreviewLabels(getRecommendationMatchedLabels(place), 3)"
                        :key="`matched-${place.id}-${label}-${index}`"
                        class="place-list-condition-chip matched"
                      >
                        {{ label }}
                      </span>
                    </span>

                    <span
                      v-if="isRecommendationPlace(place) && getRecommendationMissingLabels(place).length"
                      class="place-list-condition-group needs-check"
                    >
                      <span class="place-list-condition-label">확인 필요</span>
                      <span
                        v-for="(label, index) in getRecommendationPreviewLabels(getRecommendationMissingLabels(place), 2)"
                        :key="`missing-${place.id}-${label}-${index}`"
                        class="place-list-condition-chip missing"
                      >
                        {{ label }}
                      </span>
                    </span>

                    <span
                      v-if="place.address || place.detailLocation"
                      class="place-list-address"
                      :title="place.address || place.detailLocation"
                    >
                      {{ place.address || place.detailLocation }}
                    </span>

                    <span
                      v-if="place.phone"
                      class="place-list-phone"
                    >
                      전화 {{ place.phone }}
                    </span>

                    <span
                      v-if="isRecommendationPlace(place) && getRecommendationCaution(place)"
                      class="place-list-caution"
                    >
                      {{ getRecommendationCaution(place) }}
                    </span>

                  </span>
                </button>
                <button
                  type="button"
                  class="place-report-link-button"
                  @click.stop="goToPlaceReport(place)"
                >
                  정보 제보
                </button>
              </article>
            </template>
          </div>

          <div v-if="hasMoreResults" class="show-more-wrap">
            <button type="button" class="show-more-button" @click="showMoreResults">
              더보기
            </button>
          </div>
          </template>
        </aside>

        <div class="map-area">
          <button v-if="mapSearchKeyword.trim()" type="button" class="map-overlay-research-button"
            :disabled="isSearchingMap" @click="searchCurrentMapView">
            현재 지도에서 재검색
          </button>

          <div v-if="isSearchingMap" class="map-loading-overlay">
            <div class="map-loading-box">
              <span class="loading-spinner"></span>
              <strong>{{ loadingMessage || '검색 중' }}</strong>
            </div>
          </div>

          <KakaoMap
            :center="mapCenter"
            :places="mapPlaces"
            :fit-bounds-key="mapFitBoundsKey"
            :layout-key="mapLayoutKey"
            :selected-place-id="selectedPlace?.id || null"
            :selected-place="selectedPlace"
            @center-change="handleMapViewportChange"
            @select-place="selectPlace"
            @marker-target-change="updateMascotFetchTarget"
          />
        </div>

        <aside
          v-if="selectedPlace"
          class="place-detail-panel"
          :class="{
            'is-compact-detail': !hasKakaoDetail(selectedPlace),
            'is-collapsed': isPlaceDetailCollapsed,
          }"
        >
            <div v-if="isPlaceDetailCollapsed" class="detail-collapsed-bar">
              <button
                type="button"
                class="detail-collapsed-main"
                @click="isPlaceDetailCollapsed = false"
              >
                <span>상세정보</span>
                <strong>{{ selectedPlace.name }}</strong>
              </button>

              <button
                type="button"
                class="close-card-button"
                @click="closePlaceCard"
              >
                ×
              </button>
            </div>

            <div
              v-else
              class="split-place-card"
              :class="{ 'has-kakao-detail': hasKakaoDetail(selectedPlace) }"
            >
              <div class="split-card-top">
                <div>
                  <p class="card-label">
                    선택한 장소
                    <span class="source-badge" :class="getPlaceSourceClass(selectedPlace)">
                      {{ getPlaceSourceText(selectedPlace) }}
                    </span>
                  </p>
                  <h2>{{ selectedPlace.name }}</h2>
                </div>

                <button
                  type="button"
                  class="panel-toggle-button"
                  @click="isPlaceDetailCollapsed = true"
                >
                  접기
                </button>

                <button
                  type="button"
                  class="close-card-button"
                  @click="closePlaceCard"
                >
                  ×
                </button>
              </div>

              <div
                v-if="selectedPlace.tags && selectedPlace.tags.length"
                class="tag-list"
                :key="selectedPlace.id"
                ref="detailTagList"
              >
                <span
                  v-for="tag in getSortedTags(selectedPlace.tags)"
                  :key="`${getTagName(tag)}-${typeof tag === 'string' ? 'category_rule' : tag.source}`"
                  class="tag-chip"
                  :class="getTagClass(tag)"
                >
                  #{{ getTagName(tag) }}
                  <small>{{ getTagSourceText(tag) }}</small>
                </span>
              </div>

              <section v-if="hasKakaoDetail(selectedPlace)" class="kakao-frame-section">
                <div class="iframe-fallback" v-if="detailFrameError">
                  <p>카카오맵 상세페이지를 현재 화면에 표시하지 못했습니다.</p>

                  <a :href="getKakaoDetailUrl(selectedPlace)" target="_blank" rel="noopener noreferrer">
                    새창에서 열기
                  </a>
                </div>

                <div v-else class="kakao-frame-scroll">
                  <iframe :src="getKakaoDetailUrl(selectedPlace)" class="inline-kakao-frame" title="카카오맵 장소 상세페이지"
                    scrolling="no" referrerpolicy="no-referrer-when-downgrade" @error="handleDetailFrameError"></iframe>
                </div>
              </section>

              <section
                v-else-if="isDbPlace(selectedPlace) && !getKakaoDetailUrl(selectedPlace)"
                class="db-summary-card"
              >
                <div>
                  <strong>DB에 저장된 장소입니다.</strong>
                  <p>좌표 기준으로 지도에서 위치를 확인할 수 있습니다.</p>
                  <p v-if="getKakaoDetailLookupStatus(selectedPlace) === 'loading'">
                    카카오 상세 링크를 확인하는 중입니다.
                  </p>
                </div>

              </section>

              <div class="info-list compact-info-list">
                <div v-if="isRecommendationPlace(selectedPlace)" class="recommendation-summary">
                  <div v-if="selectedPlace.recommendScore !== null && selectedPlace.recommendScore !== undefined">
                    <span>추천 점수</span>
                    <strong>{{ getRecommendScore(selectedPlace) }}점</strong>
                  </div>

                  <div v-if="getRecommendationMetaText(selectedPlace) || getRecommendationConfidence(selectedPlace)">
                    <span>출처/신뢰도</span>
                    <strong>
                      {{ getRecommendationMetaText(selectedPlace) || getRecommendationConfidenceText(getRecommendationConfidence(selectedPlace)) }}
                    </strong>
                  </div>

                  <div v-if="getRecommendationFallbackText(selectedPlace)">
                    <span>추천 방식</span>
                    <strong>{{ getRecommendationFallbackText(selectedPlace) }}</strong>
                  </div>
                </div>

                <div v-if="isRecommendationPlace(selectedPlace) && getRecommendationReason(selectedPlace)" class="info-row">
                  <span>추천 이유</span>
                  <p class="recommendation-reason-text">{{ getRecommendationReason(selectedPlace) }}</p>
                </div>

                <div
                  v-if="isRecommendationPlace(selectedPlace) && getRecommendationFallbackDescription(selectedPlace)"
                  class="info-row subtle-info-row"
                >
                  <span>추천 기준</span>
                  <p>{{ getRecommendationFallbackDescription(selectedPlace) }}</p>
                </div>

                <div
                  v-if="isRecommendationPlace(selectedPlace) && getRecommendationMatchedLabels(selectedPlace).length"
                  class="info-row"
                >
                  <span>일치 조건</span>
                  <div class="recommendation-chip-list">
                    <span
                      v-for="(label, index) in getRecommendationMatchedLabels(selectedPlace)"
                      :key="`detail-matched-${selectedPlace.id}-${label}-${index}`"
                      class="recommendation-chip matched"
                    >
                      {{ label }}
                    </span>
                  </div>
                </div>

                <div
                  v-if="isRecommendationPlace(selectedPlace) && getRecommendationMissingLabels(selectedPlace).length"
                  class="info-row missing-info-row"
                >
                  <span>확인 필요</span>
                  <div class="recommendation-chip-list">
                    <span
                      v-for="(label, index) in getRecommendationMissingLabels(selectedPlace)"
                      :key="`detail-missing-${selectedPlace.id}-${label}-${index}`"
                      class="recommendation-chip missing"
                    >
                      {{ label }}
                    </span>
                  </div>
                </div>

                <div
                  v-if="isRecommendationPlace(selectedPlace) && getRecommendationCaution(selectedPlace)"
                  class="info-row caution-info-row"
                >
                  <span>안내</span>
                  <p>{{ getRecommendationCaution(selectedPlace) }}</p>
                </div>

                <div v-if="selectedPlace.warningTags && selectedPlace.warningTags.length" class="info-row warning-info-row">
                  <span>주의 태그</span>
                  <p>{{ selectedPlace.warningTags.join(', ') }}</p>
                </div>

                <div v-if="!isRecommendationPlace(selectedPlace)" class="info-row">
                  <span>후보 유형</span>
                  <p>{{ getCandidateDescription(selectedPlace) }}</p>
                </div>

                <div v-if="selectedPlace.category" class="info-row">
                  <span>분류</span>
                  <p>{{ selectedPlace.category }}</p>
                </div>

                <div v-if="selectedPlace.address" class="info-row">
                  <span>주소</span>
                  <p>{{ selectedPlace.address }}</p>
                </div>

                <div v-if="selectedPlace.detailLocation" class="info-row">
                  <span>상세위치</span>
                  <p>{{ selectedPlace.detailLocation }}</p>
                </div>

                <div v-if="selectedPlace.distance" class="info-row">
                  <span>거리</span>
                  <p>검색 기준 위치에서 {{ selectedPlace.distance }}m</p>
                </div>

                <div v-if="selectedPlace.phone" class="info-row">
                  <span>전화</span>
                  <p>{{ selectedPlace.phone }}</p>
                </div>

                <div class="info-row">
                  <span>출처</span>
                  <p>{{ getPlaceSourceText(selectedPlace) }}</p>
                </div>

                <div v-if="selectedPlace.dataQualityStatus" class="info-row">
                  <span>DB 품질</span>
                  <p>{{ selectedPlace.dataQualityStatus }} · {{ selectedPlace.dataQualityScore }}점</p>
                </div>
              </div>

              <div class="detail-action-row">
                <button
                  type="button"
                  class="detail-action-button report"
                  @click="goToPlaceReport(selectedPlace)"
                >
                  정보 제보
                </button>

                <a
                  v-if="getPlaceDetailUrl(selectedPlace)"
                  :href="getPlaceDetailUrl(selectedPlace)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="detail-action-button secondary"
                >
                  카카오 상세 보기
                </a>

                <a
                  v-if="getPlaceNavigationUrl(selectedPlace)"
                  :href="getPlaceNavigationUrl(selectedPlace)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="detail-action-button primary"
                >
                  카카오맵 길찾기
                </a>
              </div>
            </div>
        </aside>
      </div>
    </section>

  </main>
</template>

<style scoped>
.home-page {
  position: relative;
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(circle at 14% 18%, rgba(255, 237, 206, 0.82), transparent 28%),
    radial-gradient(circle at 86% 12%, rgba(231, 242, 255, 0.84), transparent 28%),
    linear-gradient(180deg, #fffaf1 0%, #f8f6ef 100%);
}

.home-page::before {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(90deg, rgba(34, 34, 34, 0.035) 1px, transparent 1px),
    linear-gradient(180deg, rgba(34, 34, 34, 0.035) 1px, transparent 1px);
  background-size: 38px 38px;
  content: "";
  mask-image: linear-gradient(180deg, black, transparent 78%);
}

.home-page > * {
  position: relative;
  z-index: 1;
}

.page-header {
  margin-bottom: clamp(16px, 2vw, 24px);
}

.header-main {
  display: flex;
  justify-content: center;
}

.top-bar {
  width: fit-content;
  margin: 0 auto;
  padding: 6px;
  display: flex;
  gap: 6px;
  background: #ffffff;
  border: 2px solid #222222;
  border-radius: 999px;
  box-shadow: 0 5px 0 #f2d7b0;
}

.tab-button {
  min-width: 96px;
  padding: 11px 18px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #667085;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.22s ease, color 0.22s ease, transform 0.22s ease;
}

.tab-button.active {
  background: #222222;
  color: #ffffff;
  transform: translateY(-1px);
}

.search-section {
  min-height: calc(100vh - 90px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: clamp(24px, 6vh, 72px) 0;
  transition: transform 0.28s ease, opacity 0.28s ease;
}

.search-experience {
  transition: opacity 0.28s ease, transform 0.28s ease;
}

.search-experience.is-idle {
  animation: idleSearchEnter 0.28s ease both;
}

.intro {
  max-width: 820px;
  margin-bottom: 30px;
  padding: 34px 28px 24px;
  border: 3px solid #222222;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.86);
  text-align: center;
  box-shadow: 0 8px 0 #f2d7b0;
  transition: margin 0.25s ease, opacity 0.25s ease, transform 0.25s ease;
}

.eyebrow {
  margin: 0 0 12px;
  color: #7b7166;
  font-size: 15px;
  font-weight: 900;
}

h1 {
  margin: 0;
  color: #222222;
  font-size: clamp(34px, 5vw, 54px);
  line-height: 1.25;
  letter-spacing: 0;
}

.description {
  margin: 16px 0 0;
  color: #4f4a44;
  font-size: 17px;
  font-weight: 800;
}

.search-box {
  width: min(720px, 100%);
  padding: 9px;
  display: flex;
  gap: 8px;
  background: #ffffff;
  border: 3px solid #222222;
  border-radius: 20px;
  box-shadow: 0 8px 0 #f2d7b0;
  transition: all 0.25s ease;
}

.search-box input {
  flex: 1;
  min-width: 0;
  padding: 18px 20px;
  border: 0;
  outline: none;
  color: #111827;
  font-size: 17px;
}

.search-box button {
  padding: 0 28px;
  border: 0;
  border-radius: 14px;
  background: #222222;
  color: #ffffff;
  font-size: 16px;
  font-weight: 900;
  cursor: pointer;
}

.landing-preset-buttons {
  width: min(720px, 100%);
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.landing-preset-buttons button {
  min-height: 38px;
  padding: 0 14px;
  border: 1px solid #e5e8f0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  color: #344054;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
  box-shadow: 0 8px 20px rgba(20, 35, 70, 0.07);
  transition: transform 0.22s ease, border-color 0.22s ease, background 0.22s ease;
}

.landing-preset-buttons button:hover {
  border-color: #14b8a6;
  background: #f0fdfa;
  transform: translateY(-1px);
}

.search-idle-hint {
  margin: 14px 0 0;
  color: #667085;
  font-size: 13px;
  font-weight: 800;
}

.map-section-wrap {
  width: 100%;
  max-width: none;
  margin: 0;
}

.map-section-wrap.has-results {
  animation: compactSearchEnter 0.28s ease both;
}

.conversation-search-card {
  width: min(1180px, 100%);
  margin: 0 auto 14px;
  padding: clamp(14px, 1.6vw, 20px) 0;
  display: grid;
  gap: 12px;
  border: 1px solid rgba(229, 232, 240, 0.95);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.11);
  backdrop-filter: blur(14px);
  transition: transform 0.25s ease, box-shadow 0.25s ease, padding 0.25s ease;
}

.conversation-search-card.has-results {
  padding: 14px 0;
  transform: translateY(-8px);
}

.conversation-search-card.is-conversation-mode {
  gap: 10px;
}

.search-experience.has-results .search-hero-card {
  width: min(1040px, 100%);
  margin-bottom: 6px;
  padding: 12px 0;
  border-radius: 20px;
  box-shadow: 0 14px 38px rgba(20, 35, 70, 0.1);
}

.search-experience.has-results .conversation-card-top {
  align-items: center;
}

.search-experience.has-results .conversation-copy h1 {
  font-size: 20px;
}

.search-experience.has-results .conversation-copy .eyebrow {
  margin-bottom: 3px;
  font-size: 11px;
}

.search-experience.has-results .map-search-box {
  grid-template-columns: minmax(0, 1fr) auto;
}

.search-experience.has-results .map-search-box label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
}

.search-experience.has-results .ai-preset-buttons {
  flex-wrap: nowrap;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
}

.search-experience.has-results .ai-preset-buttons button {
  flex: 0 0 auto;
  min-height: 32px;
  font-size: 12px;
}

.conversation-compact-bar {
  min-height: 42px;
  padding: 8px 10px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  border: 1px solid #e5e8f0;
  border-radius: 14px;
  background: #f8fafc;
  color: #344054;
  animation: compactSearchEnter 0.22s ease both;
}

.conversation-compact-bar span {
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-compact-bar button {
  flex: 0 0 auto;
  min-height: 32px;
  padding: 0 12px;
  border: 0;
  border-radius: 999px;
  background: #111827;
  color: #ffffff;
  font-size: 12px;
  font-weight: 900;
  cursor: pointer;
}

.conversation-compact-bar button:disabled {
  background: #98a2b3;
  cursor: not-allowed;
}

.conversation-card-top,
.map-header {
  padding: 18px 20px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
  border: 3px solid #222222;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 8px 0 #f2d7b0;
}

.conversation-copy {
  min-width: 0;
}

.conversation-copy .eyebrow {
  margin-bottom: 5px;
  font-size: 12px;
}

.conversation-copy h1,
.map-header h1 {
  margin: 0;
  font-size: 24px;
  line-height: 1.3;
  letter-spacing: 0;
}

.map-header p {
  margin: 6px 0 0;
  color: #4f4a44;
  font-size: 14px;
  font-weight: 800;
}

.map-header-actions {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.map-location-button,
.map-header-reset {
  padding: 10px 14px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.22s ease, background 0.22s ease, border-color 0.22s ease;
}

.map-location-button {
  background: #ffffff;
  color: #222222;
  border: 2px solid #222222;
  box-shadow: 0 4px 0 #f2d7b0;
}

.map-location-button:hover:not(:disabled),
.map-header-reset:hover:not(:disabled) {
  transform: translateY(-1px);
}

.map-location-button:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.map-parser-status {
  box-sizing: border-box;
  width: min(1180px, 100%);
  margin: 0 auto 12px;
  padding: 10px 12px;
  display: grid;
  gap: 3px;
  border-radius: 8px;
}

.search-experience.has-results .map-parser-status {
  width: min(1040px, 100%);
}

.map-parser-status strong {
  font-size: 14px;
}

.map-parser-status span {
  font-size: 13px;
  white-space: pre-line;
}

.map-parser-status.ai {
  background: #e7f5ff;
  color: #1864ab;
}

.map-parser-status.fallback {
  background: #fff3bf;
  color: #8d6b00;
}

.map-search-box {
  margin: 0 0 12px;
  padding: 10px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  background: #ffffff;
  border: 3px solid #222222;
  border-radius: 18px;
  box-shadow: 0 6px 0 #f2d7b0;
}

.search-panel {
  max-height: 220px;
  overflow: hidden;
  opacity: 1;
  transform: scale(1);
  transition:
    max-height 0.45s ease,
    padding 0.35s ease,
    margin 0.35s ease,
    opacity 0.3s ease,
    transform 0.35s ease,
    border-color 0.3s ease;
}

.search-panel--compact {
  max-height: 0;
  margin: -4px 0 0;
  padding-top: 0;
  padding-bottom: 0;
  border-color: transparent;
  opacity: 0;
  pointer-events: none;
  transform: scale(0.985);
}

.map-search-box label {
  grid-column: 1 / -1;
  padding: 0 6px;
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

.map-search-box input {
  min-width: 0;
  padding: 13px 15px;
  border: 0;
  border-radius: 13px;
  background: #ffffff;
  outline: none;
  font-size: 15px;
}

.ai-search-box {
  border-color: #dbeafe;
}

.map-search-actions {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.map-search-box button {
  min-height: 44px;
  padding: 0 16px;
  border: 0;
  border-radius: 10px;
  background: #222222;
  color: #ffffff;
  font-size: 15px;
  font-weight: 900;
  cursor: pointer;
}

.map-search-box button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.map-header-reset:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.map-ai-button {
  background: #222222 !important;
}

.ai-preset-buttons {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ai-preset-buttons button {
  min-height: 36px;
  padding: 0 12px;
  background: #ffffff !important;
  border: 1px solid #e5e8f0;
  color: #344054 !important;
  font-size: 13px;
}

.map-reset-button {
  background: #f2f4f7 !important;
  color: #344054 !important;
}

.conversation-status {
  padding: 12px 14px;
  display: grid;
  gap: 8px;
  border-radius: 16px;
  background: #f8fafc;
}

.conversation-status strong {
  display: block;
  margin-bottom: 4px;
  color: #111827;
  font-size: 14px;
  font-weight: 900;
}

.conversation-status p {
  margin: 0;
  display: -webkit-box;
  overflow: hidden;
  color: #667085;
  font-size: 13px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.conversation-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.conversation-chip-list span {
  max-width: 100%;
  padding: 5px 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #ffffff;
  color: #344054;
  font-size: 12px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-status .conversation-notice {
  color: #92400e;
}

.clarification-thread {
  display: grid;
  gap: 8px;
}

.clarification-bubble {
  max-width: min(520px, 100%);
  padding: 8px 10px;
  border: 1px solid #e5e8f0;
  border-radius: 12px;
  background: #ffffff;
}

.clarification-bubble.is-user {
  justify-self: end;
  background: #e0f2fe;
  border-color: #bae6fd;
}

.clarification-bubble.is-assistant {
  justify-self: start;
}

.clarification-bubble span {
  display: block;
  margin-bottom: 3px;
  color: #475467;
  font-size: 11px;
  font-weight: 900;
}

.conversation-status .clarification-bubble p {
  display: block;
  overflow: visible;
  color: #1f2937;
  -webkit-line-clamp: unset;
}

.clarification-follow-up {
  width: min(520px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.clarification-follow-up input {
  min-width: 0;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 10px;
  background: #ffffff;
  color: #111827;
  font-size: 13px;
  outline: none;
}

.clarification-follow-up input:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.clarification-follow-up button {
  min-height: 40px;
  padding: 0 14px;
  border: 0;
  border-radius: 10px;
  background: #111827;
  color: #ffffff;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
}

.clarification-follow-up button:disabled {
  background: #98a2b3;
  cursor: not-allowed;
}

.view-switch {
  position: relative;
  width: min(360px, 100%);
  padding: 4px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border: 1px solid #e5e8f0;
  border-radius: 999px;
  background: #f2f4f7;
}

.view-switch::before {
  content: "";
  position: absolute;
  inset: 4px auto 4px 4px;
  width: calc(50% - 4px);
  border-radius: 999px;
  background: #ffffff;
  box-shadow: 0 8px 20px rgba(20, 35, 70, 0.12);
  transition: transform 0.25s ease;
}

.view-switch.is-map-active::before {
  transform: translateX(100%);
}

.view-switch button {
  position: relative;
  z-index: 1;
  min-height: 34px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #667085;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
  transition: color 0.22s ease;
}

.view-switch button.active {
  color: #111827;
}

@keyframes fadeSlideIn {
  from {
    opacity: 0;
    transform: translateY(14px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes compactSearchEnter {
  from {
    opacity: 0.96;
    transform: translateY(18px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes revealWorkspace {
  from {
    opacity: 0;
    transform: translateY(20px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes idleSearchEnter {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.base-location-candidates {
  width: min(1180px, 100%);
  margin: 0 auto 12px;
  padding: 14px;
  display: grid;
  gap: 12px;
  border: 1px solid #dbeafe;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.candidate-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.candidate-header strong {
  color: #111827;
  font-size: 14px;
}

.candidate-header p {
  margin: 4px 0 0;
  color: #667085;
  font-size: 13px;
}

.candidate-cancel-button {
  min-height: 36px;
  padding: 0 12px;
  border: 0;
  border-radius: 10px;
  background: #f2f4f7;
  color: #344054;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
}

.candidate-list {
  display: grid;
  gap: 8px;
}

.candidate-button {
  width: 100%;
  padding: 11px 12px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  border: 1px solid #e5e8f0;
  border-radius: 12px;
  background: #f8fafc;
  color: #111827;
  text-align: left;
  cursor: pointer;
}

.candidate-button:hover {
  border-color: #93c5fd;
  background: #eff6ff;
}

.candidate-button > span {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.candidate-button strong,
.candidate-button small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-button strong {
  font-size: 14px;
}

.candidate-button small {
  color: #667085;
  font-size: 12px;
  font-weight: 700;
}

.candidate-kind {
  flex-shrink: 0;
  max-width: 38%;
  text-align: right;
}

.map-content {
  --workspace-height: min(720px, calc(100vh - clamp(190px, 20vh, 230px)));
  width: min(1400px, 100%);
  margin: 0 auto;
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: clamp(16px, 1.4vw, 24px);
  align-items: stretch;
  animation: fadeSlideIn 0.3s ease both;
  transition: grid-template-columns 0.25s ease;
}

.search-reveal-area {
  opacity: 0;
  transform: translateY(20px);
  animation: revealWorkspace 0.34s ease 0.04s both;
}

.map-content.has-result-list {
  grid-template-columns: clamp(340px, 26vw, 420px) minmax(0, 1fr);
}

.map-content.has-result-list.is-list-collapsed {
  grid-template-columns: 84px minmax(0, 1fr);
}

.map-content.has-result-list.has-selected-place {
  grid-template-columns: clamp(340px, 25vw, 400px) minmax(0, 1fr) clamp(320px, 24vw, 420px);
}

.map-content.has-result-list.has-selected-place.is-list-collapsed {
  grid-template-columns: 84px minmax(0, 1fr) clamp(320px, 24vw, 420px);
}

.map-content.has-selected-place:not(.has-result-list) {
  grid-template-columns: minmax(0, 1fr) clamp(320px, 24vw, 420px);
}

.place-list-panel {
  position: relative;
  z-index: 10;
  height: var(--workspace-height);
  min-height: 520px;
  padding: clamp(12px, 1vw, 16px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.96);
  border: 3px solid #222222;
  border-radius: 18px;
  box-shadow: 0 8px 0 #f2d7b0;
  transition: width 0.25s ease, height 0.25s ease, transform 0.25s ease, opacity 0.25s ease, padding 0.25s ease;
}

.place-list-panel.is-collapsed {
  padding: 10px;
  align-items: stretch;
}

.place-list-top {
  padding-bottom: 10px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
  border-bottom: 1px solid #eef0f4;
}

.place-list-panel.is-collapsed .place-list-top {
  min-height: 0;
  padding-bottom: 0;
  display: grid;
  gap: 8px;
  border-bottom: 0;
}

.place-list-label {
  margin: 0 0 4px;
  color: #7b7166;
  font-size: 13px;
  font-weight: 900;
}

.place-list-top h2 {
  margin: 0;
  display: -webkit-box;
  overflow: hidden;
  color: #111827;
  font-size: 16px;
  line-height: 1.35;
  letter-spacing: 0;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.result-controls {
  padding: 10px 0;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  flex-wrap: nowrap;
  border-bottom: 1px solid #eef0f4;
}

.result-filter-buttons {
  min-width: 0;
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: thin;
}

.result-filter-button {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid #e5e8f0;
  border-radius: 999px;
  background: #ffffff;
  color: #475467;
  font-size: 12px;
  font-weight: 900;
  cursor: pointer;
}

.result-filter-button.active {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}

.result-sort-select {
  flex-shrink: 0;
  display: flex;
  gap: 6px;
  align-items: center;
  color: #667085;
  font-size: 12px;
  font-weight: 900;
}

.result-sort-select select {
  min-height: 30px;
  padding: 0 26px 0 10px;
  border: 1px solid #e5e8f0;
  border-radius: 999px;
  background: #ffffff;
  color: #344054;
  font-size: 12px;
  font-weight: 900;
}

.ai-web-search-panel {
  margin: 10px 0;
  padding: 12px;
  flex-shrink: 0;
  max-height: 220px;
  display: grid;
  gap: 10px;
  overflow-y: auto;
  border: 1px solid #e5e8f0;
  border-radius: 12px;
  background: #f8fafc;
  animation: aiPanelReveal 0.25s ease both;
}

.ai-web-search-heading {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.ai-web-search-heading div {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.ai-web-search-heading strong {
  color: #111827;
  font-size: 13px;
  font-weight: 900;
}

.ai-web-search-heading span,
.ai-web-search-message,
.ai-web-search-caution {
  color: #667085;
  font-size: 12px;
  line-height: 1.45;
}

.ai-web-search-button {
  flex-shrink: 0;
  min-height: 32px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  background: #111827;
  color: #ffffff;
  font-size: 12px;
  font-weight: 900;
  cursor: pointer;
}

.ai-web-search-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.ai-web-search-message {
  margin: 0;
}

.ai-web-search-debug {
  color: #475467;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  overflow-wrap: anywhere;
}

.ai-web-search-candidates {
  display: grid;
  gap: 6px;
}

.ai-web-search-summary-card {
  padding: 10px;
  display: grid;
  gap: 6px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #eff6ff;
}

.ai-web-search-summary-card strong {
  color: #1e3a8a;
  font-size: 13px;
  font-weight: 900;
}

.ai-web-search-summary-card p,
.ai-web-search-summary-card small {
  margin: 0;
  color: #344054;
  font-size: 12px;
  line-height: 1.45;
}

.ai-web-search-summary-card p {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.ai-web-search-summary-card small {
  color: #475467;
}

.ai-web-search-summary-keywords {
  color: #1d4ed8;
  font-weight: 800;
}

.ai-web-search-evidence-heading {
  margin-top: 2px;
  color: #475467;
  font-size: 12px;
  font-weight: 900;
}

.ai-web-search-candidate {
  padding: 10px;
  display: grid;
  gap: 7px;
  border: 1px solid #e5e8f0;
  border-radius: 10px;
  background: #ffffff;
}

.ai-web-search-candidate.is-reference {
  padding: 9px;
  gap: 6px;
  border-radius: 8px;
}

.ai-web-search-reference-badges {
  display: flex;
  gap: 5px;
  align-items: center;
  flex-wrap: wrap;
}

.ai-web-search-reference-badges span {
  min-height: 20px;
  padding: 2px 7px;
  border-radius: 999px;
  background: #f2f4f7;
  color: #475467;
  font-size: 11px;
  font-weight: 900;
  line-height: 1.35;
}

.ai-web-search-reference-badges span:first-child {
  background: #eff6ff;
  color: #1d4ed8;
}

.ai-web-search-candidate-title {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.ai-web-search-candidate-title strong,
.ai-web-search-candidate-title a {
  min-width: 0;
  display: -webkit-box;
  overflow: hidden;
  color: #111827;
  font-size: 14px;
  line-height: 1.35;
  font-weight: 900;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.ai-web-search-candidate-title a {
  text-decoration: none;
}

.ai-web-search-candidate-title a:hover {
  color: #1d4ed8;
}

.ai-web-search-candidate-title span {
  flex-shrink: 0;
  max-width: 45%;
  color: #475467;
  font-size: 12px;
  font-weight: 800;
  text-align: right;
}

.ai-web-search-hint,
.ai-web-search-summary,
.ai-web-search-caution {
  margin: 0;
}

.ai-web-search-hint {
  display: -webkit-box;
  overflow: hidden;
  color: #475467;
  font-size: 12px;
  line-height: 1.4;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.ai-web-search-summary {
  display: -webkit-box;
  overflow: hidden;
  color: #344054;
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.ai-web-search-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ai-web-search-sources a {
  padding: 4px 8px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 900;
  text-decoration: none;
}

.ai-web-search-caution {
  font-size: 11px;
  line-height: 1.4;
  color: #92400e;
}

.place-list-panel.is-collapsed .place-list-label,
.place-list-panel.is-collapsed .place-list-top h2 {
  writing-mode: vertical-rl;
  text-orientation: mixed;
}

.panel-toggle-button {
  flex-shrink: 0;
  min-height: 32px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  background: #f2f4f7;
  color: #344054;
  font-size: 12px;
  font-weight: 900;
  cursor: pointer;
}

.panel-toggle-button:hover {
  background: #e5e7eb;
  color: #111827;
}

.collapsed-panel-summary {
  margin-top: 12px;
  display: grid;
  place-items: center;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
}

.place-list {
  min-height: 0;
  flex: 1;
  margin-top: 10px;
  overflow-y: auto;
  padding-right: 4px;
}

.filtered-empty-message {
  padding: 18px 10px;
  border-radius: 12px;
  background: #f8fafc;
  color: #667085;
  font-size: 13px;
  font-weight: 800;
  text-align: center;
}

.skeleton-list {
  display: grid;
  gap: 8px;
}

.skeleton-card {
  padding: 11px 8px;
  display: flex;
  gap: 10px;
  align-items: flex-start;
  border-bottom: 1px solid #eef0f4;
}

.skeleton-marker,
.skeleton-line {
  position: relative;
  overflow: hidden;
  background: #e5e7eb;
}

.skeleton-marker::after,
.skeleton-line::after {
  content: '';
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.7), transparent);
  animation: skeleton-shimmer 1.2s infinite;
}

.skeleton-marker {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  margin-top: 2px;
  border-radius: 999px;
}

.skeleton-main {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 8px;
}

.skeleton-line {
  height: 12px;
  border-radius: 999px;
}

.skeleton-title {
  width: 72%;
}

.skeleton-meta {
  width: 42%;
}

.skeleton-address {
  width: 92%;
}

@keyframes skeleton-shimmer {
  100% {
    transform: translateX(100%);
  }
}

.place-list-item {
  width: 100%;
  border-bottom: 1px solid #eef0f4;
  background: transparent;
  color: #111827;
}

.place-list-item:hover,
.place-list-item.active {
  background: #fff1d8;
  border-radius: 12px;
}

.place-list-select-button {
  width: 100%;
  padding: 11px 8px;
  display: flex;
  gap: 10px;
  align-items: flex-start;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.place-report-link-button {
  margin: 0 8px 10px 46px;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid #d0d5dd;
  border-radius: 999px;
  background: #ffffff;
  color: #475467;
  font-size: 12px;
  font-weight: 900;
  cursor: pointer;
}

.place-report-link-button:hover {
  border-color: #2563eb;
  color: #1d4ed8;
}

.place-list-marker {
  position: relative;
  width: 54px;
  height: 54px;
  flex-shrink: 0;
  margin-top: -10px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #222222;
  font-size: 12px;
  font-weight: 900;
  isolation: isolate;
}

.place-list-marker::before {
  position: absolute;
  inset: 0;
  z-index: -1;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='54' height='54' viewBox='0 0 54 54'%3E%3Cg transform='rotate(-45 27 27)'%3E%3Cpath d='M14.6 6.2 C16.4 2.9 20.8 1.8 24 4 C25.7 5.1 26.7 6.8 27 8.6 C27.3 6.8 28.3 5.1 30 4 C33.2 1.8 37.6 2.9 39.4 6.2 C41.4 9.8 39.8 14.2 36.3 15.8 L36.3 38.2 C39.8 39.8 41.4 44.2 39.4 47.8 C37.6 51.1 33.2 52.2 30 50 C28.3 48.9 27.3 47.2 27 45.4 C26.7 47.2 25.7 48.9 24 50 C20.8 52.2 16.4 51.1 14.6 47.8 C12.6 44.2 14.2 39.8 17.7 38.2 L17.7 15.8 C14.2 14.2 12.6 9.8 14.6 6.2 Z' fill='white' stroke='%23222222' stroke-width='4' stroke-linejoin='round'/%3E%3C/g%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  content: "";
}

.place-list-marker.source-db {
  border-color: currentColor;
  color: #222222;
}

.place-list-marker.source-base {
  border-color: currentColor;
  color: #222222;
}

.place-list-main {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 6px;
}

.place-list-name-row {
  min-width: 0;
  display: flex;
  gap: 8px;
  align-items: center;
}

.place-list-name {
  min-width: 0;
  overflow: hidden;
  color: #111827;
  font-size: 14px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.place-list-main small {
  overflow: hidden;
  color: #667085;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.place-list-meta {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
}

.place-list-meta small+small::before {
  content: '·';
  margin-right: 8px;
  color: #98a2b3;
}

.place-list-recommend-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
}

.place-list-recommend-meta small {
  color: #475467;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.35;
  white-space: normal;
}

.place-list-recommend-meta small+small::before {
  content: '·';
  margin-right: 8px;
  color: #98a2b3;
}

.place-list-personalization {
  width: fit-content;
  max-width: 100%;
  padding: 4px 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #ecfdf3;
  color: #047857;
  font-size: 11px;
  font-weight: 900;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.personalization-reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
}

.personalization-reasons-label {
  color: #047857;
  font-size: 11px;
  font-weight: 900;
}

.personalization-reason-chip {
  max-width: 100%;
  padding: 3px 7px;
  overflow: hidden;
  border-radius: 999px;
  background: #f0fdf4;
  color: #166534;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.place-list-reason {
  display: -webkit-box;
  overflow: hidden;
  color: #475467;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.place-list-condition-group {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
}

.place-list-condition-label {
  color: #667085;
  font-size: 11px;
  font-weight: 900;
}

.place-list-condition-chip {
  max-width: 100%;
  padding: 3px 7px;
  overflow: hidden;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.place-list-condition-chip.matched {
  background: #eff6ff;
  color: #1d4ed8;
}

.place-list-condition-chip.missing {
  background: #fff7ed;
  color: #b45309;
}

.place-list-caution {
  display: -webkit-box;
  overflow: hidden;
  color: #92400e;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.place-list-phone {
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.35;
}

.place-list-address {
  display: -webkit-box;
  overflow: hidden;
  color: #475467;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.place-list-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.place-list-tag {
  max-width: 100%;
  padding: 4px 7px;
  overflow: hidden;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.show-more-wrap {
  padding-top: 12px;
  border-top: 1px solid #eef0f4;
}

.show-more-button {
  width: 100%;
  padding: 12px 14px;
  border: 0;
  border-radius: 12px;
  background: #111827;
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
}

.show-more-button:hover {
  background: #374151;
}

.source-badge {
  flex-shrink: 0;
  padding: 3px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 900;
  line-height: 1.2;
}

.source-badge.source-kakao {
  background: #fee2e2;
  color: #b91c1c;
}

.source-badge.source-db {
  background: #dbeafe;
  color: #1d4ed8;
}

.source-badge.source-base {
  background: #dcfce7;
  color: #166534;
}

.map-area {
  min-width: 0;
  position: relative;
  z-index: 1;
  height: var(--workspace-height);
  min-height: 520px;
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.map-area :deep(.map-section) {
  height: 100%;
  min-height: inherit;
}

.map-loading-overlay {
  position: absolute;
  z-index: 7;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
  background: rgba(248, 250, 252, 0.42);
}

.map-loading-box {
  padding: 13px 16px;
  display: inline-flex;
  gap: 10px;
  align-items: center;
  border: 1px solid rgba(229, 232, 240, 0.9);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  color: #111827;
  font-size: 14px;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.18);
}

.loading-spinner {
  width: 18px;
  height: 18px;
  border: 3px solid #dbeafe;
  border-top-color: #2563eb;
  border-radius: 999px;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.map-overlay-research-button {
  position: absolute;
  z-index: 4;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  min-height: 42px;
  padding: 0 16px;
  border: 0;
  border-radius: 999px;
  background: #111827;
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.22);
  cursor: pointer;
}

.map-overlay-research-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

:deep(.map) {
  height: 100%;
  min-height: 0;
  border: 3px solid #222222;
  border-radius: 20px;
  box-shadow: 0 8px 0 #f2d7b0;
  overflow: hidden;
}

@keyframes aiPanelReveal {
  from {
    max-height: 0;
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    max-height: 220px;
    opacity: 1;
    transform: translateY(0);
  }
}

.place-detail-panel {
  min-width: 0;
  position: relative;
  z-index: 8;
  width: 100%;
  height: var(--workspace-height);
  min-height: 520px;
  overflow: visible;
}

.place-detail-panel.is-collapsed {
  overflow: visible;
}

.place-detail-panel.is-compact-detail {
  max-height: none;
}

.place-detail-panel.is-collapsed.is-compact-detail {
  max-height: none;
}

.detail-collapsed-bar {
  padding: 10px;
  display: flex;
  gap: 8px;
  align-items: center;
  border: 1px solid #e5e8f0;
  border-radius: 999px;
  background: #ffffff;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.18);
}

.detail-collapsed-main {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 2px;
  border: 0;
  background: transparent;
  color: #111827;
  text-align: left;
  cursor: pointer;
}

.detail-collapsed-main span {
  color: #2563eb;
  font-size: 11px;
  font-weight: 900;
}

.detail-collapsed-main strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.split-place-card {
  box-sizing: border-box;
  height: 100%;
  min-height: 0;
  padding: clamp(16px, 1.2vw, 22px);
  display: flex;
  flex-direction: column;
  gap: clamp(14px, 1.1vw, 18px);
  overflow-x: hidden;
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.96);
  border: 3px solid #222222;
  border-radius: 18px;
  box-shadow: 0 8px 0 #f2d7b0;
}

.split-place-card.has-kakao-detail {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.split-card-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.split-card-top > div:first-child {
  min-width: 0;
  flex: 1;
}

.card-label {
  margin: 0 0 8px;
  display: flex;
  gap: 8px;
  align-items: center;
  color: #2563eb;
  font-size: 13px;
  font-weight: 800;
}

.close-card-button {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 999px;
  background: #f2f4f7;
  color: #667085;
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
}

.close-card-button:hover {
  background: #e5e7eb;
  color: #111827;
}

.split-card-top h2 {
  margin: 0;
  color: #111827;
  font-size: 22px;
  line-height: 1.35;
  letter-spacing: -0.03em;
}

.kakao-frame-section {
  height: clamp(420px, 56vh, 680px);
  min-height: 0;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
}

.kakao-frame-scroll {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  padding-right: 6px;
  overflow-x: hidden;
  overflow-y: scroll;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

.db-summary-card {
  min-height: 180px;
  padding: 18px;
  display: grid;
  align-content: center;
  gap: 12px;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #f9fafb;
}

.db-summary-card strong {
  display: block;
  margin-bottom: 5px;
  color: #111827;
  font-size: 14px;
}

.db-summary-card p {
  margin: 0;
  color: #667085;
  font-size: 13px;
  line-height: 1.5;
}

.db-summary-card a {
  width: fit-content;
  padding: 10px 12px;
  border-radius: 12px;
  background: #2563eb;
  color: #ffffff;
  font-size: 13px;
  font-weight: 900;
  text-decoration: none;
}

.inline-kakao-frame {
  width: 100%;
  height: clamp(1100px, 145vh, 1800px);
  min-height: 0;
  border: 0;
  background: #ffffff;
  display: block;
}

.category {
  margin: 12px 0 0;
  color: #667085;
  font-size: 14px;
  line-height: 1.5;
}

.tag-list {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  flex: 0 0 auto;
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  overscroll-behavior-x: contain;
  padding: 0 2px 12px 0;
  border-bottom: 1px solid #eef0f4;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

.tag-list::-webkit-scrollbar {
  height: 8px;
}

.tag-list::-webkit-scrollbar-track {
  border-radius: 999px;
  background: #f2f4f7;
}

.tag-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: #cbd5e1;
}

.tag-list::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

.tag-chip {
  flex: 0 0 auto;
  padding: 7px 10px;
  display: inline-flex;
  gap: 6px;
  align-items: center;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 800;
  white-space: nowrap;
}

.tag-chip small {
  font-size: 10px;
  font-weight: 900;
  opacity: 0.8;
}

.tag-default {
  background: #111827;
  color: #ffffff;
}

.tag-blog {
  background: #16a34a;
  color: #ffffff;
}

.tag-user {
  background: #ef4444;
  color: #ffffff;
}

.tag-warning {
  background: #f59e0b;
  color: #111827;
}

.info-list {
  margin-top: 0;
  border-top: 0;
}

.compact-info-list {
  margin-top: 0;
}

.recommendation-summary {
  margin-bottom: 4px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.recommendation-summary div {
  padding: 12px;
  display: grid;
  gap: 5px;
  border-radius: 12px;
  background: #f5f3ff;
}

.recommendation-summary span {
  color: #6d28d9;
  font-size: 12px;
  font-weight: 900;
}

.recommendation-summary strong {
  color: #111827;
  font-size: 16px;
}

.info-row {
  padding: 11px 0;
  border-bottom: 1px solid #eef0f4;
}

.info-row span {
  display: block;
  margin-bottom: 5px;
  color: #98a2b3;
  font-size: 12px;
  font-weight: 800;
}

.info-row p {
  margin: 0;
  color: #344054;
  font-size: 14px;
  line-height: 1.5;
}

.recommendation-reason-text {
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.subtle-info-row p {
  color: #667085;
}

.recommendation-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.recommendation-chip {
  padding: 5px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.2;
}

.recommendation-chip.matched {
  background: #eff6ff;
  color: #1d4ed8;
}

.recommendation-chip.missing {
  background: #fff7ed;
  color: #b45309;
}

.missing-info-row {
  padding: 11px 10px;
  border-radius: 12px;
  border-bottom: 0;
  background: #fffbeb;
}

.missing-info-row span {
  color: #b45309;
}

.caution-info-row p {
  color: #92400e;
  font-size: 13px;
}

.warning-info-row p {
  color: #b42318;
  font-weight: 800;
}

.detail-action-row {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.detail-action-button {
  flex: 1;
  min-width: 150px;
  width: 100%;
  padding: 12px 16px;
  display: block;
  border: 0;
  border-radius: 14px;
  font-size: 14px;
  font-weight: 900;
  text-align: center;
  text-decoration: none;
  cursor: pointer;
}

.detail-action-button.primary {
  background: #fee500;
  color: #111827;
}

.detail-action-button.secondary {
  background: #f2f4f7;
  color: #344054;
}

.detail-action-button.report {
  background: #eef2ff;
  color: #3730a3;
}

.iframe-fallback {
  height: 100%;
  min-height: 220px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  border-radius: 16px;
  background: #ffffff;
}

.iframe-fallback p {
  margin: 0;
  color: #667085;
  font-size: 13px;
  line-height: 1.5;
}

.iframe-fallback a {
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  text-decoration: none;
}

@media (max-width: 1100px) {

  .conversation-card-top {
    flex-direction: column;
  }

  .conversation-search-card,
  .base-location-candidates,
  .map-content {
    width: 100%;
  }

  .map-content.has-result-list,
  .map-content.has-result-list.has-selected-place,
  .map-content.has-result-list.is-list-collapsed,
  .map-content.has-result-list.has-selected-place.is-list-collapsed,
  .map-content.has-selected-place:not(.has-result-list) {
    grid-template-columns: 1fr;
  }

  .map-area {
    order: 1;
  }

  .place-detail-panel {
    order: 3;
    width: 100%;
    height: auto;
    min-height: 0;
  }

  .split-place-card,
  .split-place-card.has-kakao-detail {
    height: auto;
    min-height: 0;
  }

  .place-list-panel {
    order: 2;
    position: relative;
    right: auto;
    bottom: auto;
    left: auto;
    z-index: 10;
    width: 100%;
    height: clamp(260px, 38vh, 360px);
    max-height: clamp(260px, 38vh, 360px);
    min-height: 0;
    margin-top: -18px;
    border-radius: 22px 22px 18px 18px;
  }

  .map-content.has-selected-place .place-list-panel {
    height: clamp(220px, 32vh, 320px);
    max-height: clamp(220px, 32vh, 320px);
    min-height: 0;
  }

  .place-list-panel.is-collapsed {
    height: 64px;
    max-height: 64px;
    min-height: 0;
  }

  .place-list-panel.is-collapsed .place-list-top {
    display: flex;
    align-items: center;
  }

  .place-list-panel.is-collapsed .place-list-label,
  .place-list-panel.is-collapsed .place-list-top h2 {
    writing-mode: horizontal-tb;
  }

  .place-list {
    max-height: none;
  }

}

@media (max-width: 768px) {
  .home-page {
    width: 100%;
    max-width: 100%;
    padding: 16px;
    overflow-x: hidden;
  }

  .page-header {
    margin-bottom: 12px;
  }

  .top-bar {
    width: 100%;
    max-width: 100%;
    padding: 4px;
    gap: 4px;
  }

  .tab-button {
    flex: 1;
    min-width: 0;
    padding: 10px 12px;
    font-size: 14px;
  }

  .search-section {
    min-height: auto;
    padding: 40px 0 24px;
  }

  .intro {
    margin-bottom: 20px;
  }

  h1 {
    font-size: 34px;
  }

  .description {
    font-size: 15px;
    line-height: 1.55;
  }

  .search-box,
  .landing-preset-buttons,
  .conversation-search-card,
  .base-location-candidates,
  .map-content {
    width: 100%;
    max-width: none;
  }

  .search-box {
    border-radius: 20px;
  }

  .landing-preset-buttons {
    justify-content: flex-start;
    gap: 8px;
  }

  .landing-preset-buttons button,
  .ai-preset-buttons button {
    min-height: 36px;
    padding: 0 12px;
    font-size: 12px;
  }

  .conversation-search-card {
    padding: 12px 0;
    border-radius: 18px;
  }

  .conversation-card-top {
    gap: 10px;
  }

  .conversation-copy h1 {
    font-size: 20px;
  }

  .map-header-actions {
    width: 100%;
    justify-content: stretch;
  }

  .map-location-button,
  .map-header-reset {
    flex: 1;
    min-width: 0;
    padding: 9px 10px;
    font-size: 13px;
  }

  .conversation-compact-bar {
    min-width: 0;
    flex-wrap: wrap;
  }

  .conversation-compact-bar span {
    flex: 1 1 160px;
  }

  .clarification-bubble {
    max-width: 95%;
    overflow-wrap: anywhere;
  }

  .clarification-follow-up {
    width: 100%;
  }

  .map-search-box {
    grid-template-columns: 1fr;
  }

  .search-experience.has-results .map-search-box {
    grid-template-columns: 1fr;
  }

  .map-content.has-result-list,
  .map-content.has-result-list.has-selected-place,
  .map-content.has-result-list.is-list-collapsed,
  .map-content.has-result-list.has-selected-place.is-list-collapsed,
  .map-content.has-selected-place:not(.has-result-list) {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .place-list-panel {
    order: 1;
    width: 100%;
    height: auto;
    max-height: none;
    min-height: 0;
    margin-top: 0;
    border-radius: 18px;
  }

  .map-area {
    order: 2;
    height: auto;
    min-height: 0;
  }

  .map-area :deep(.map-section) {
    height: auto;
    min-height: 0;
  }

  .place-detail-panel {
    order: 3;
    position: relative;
    top: auto;
    right: auto;
    bottom: auto;
    left: auto;
    width: 100%;
    height: auto;
    min-height: 0;
    max-height: none;
  }

  .place-list {
    max-height: min(52vh, 460px);
  }

  :deep(.map) {
    height: 420px;
    min-height: 320px;
    border-radius: 18px;
  }

  .base-location-candidates {
    padding: 12px;
    border-radius: 14px;
  }

  .candidate-header {
    flex-direction: column;
    align-items: stretch;
  }

  .candidate-cancel-button {
    width: 100%;
  }

  .candidate-button {
    align-items: flex-start;
  }

  .candidate-button strong,
  .candidate-button small {
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .candidate-kind {
    max-width: 42%;
  }
}

@media (max-width: 640px) {
  .home-page {
    padding: 18px;
  }

  h1 {
    font-size: 30px;
  }

  .description {
    font-size: 15px;
  }

  .search-box,
  .map-search-box {
    flex-direction: column;
    border-radius: 18px;
  }

  .search-section {
    min-height: calc(100vh - 84px);
    justify-content: flex-start;
    padding-top: 54px;
  }

  .landing-preset-buttons {
    justify-content: flex-start;
  }

  .map-section-wrap {
    margin-top: 0;
  }

  .map-header {
    flex-direction: column;
  }

  .result-controls {
    align-items: flex-start;
    flex-direction: column;
  }

  .result-sort-select {
    width: 100%;
    justify-content: space-between;
  }

  .map-header-actions {
    width: 100%;
    justify-content: stretch;
  }

  .conversation-search-card {
    border-radius: 20px;
  }

  .conversation-copy h1 {
    font-size: 20px;
  }

  .conversation-status {
    padding: 11px;
  }

  .view-switch {
    width: 100%;
  }

  .map-location-button,
  .map-header-reset {
    flex: 1;
    min-width: 0;
  }

  .map-search-box {
    grid-template-columns: 1fr;
  }

  .search-experience.has-results .map-search-box {
    grid-template-columns: 1fr;
  }

  .search-box input,
  .map-search-box input {
    padding: 13px 14px;
  }

  .map-search-actions {
    width: 100%;
  }

  .map-search-actions button {
    flex: 1;
    min-width: 0;
  }

  .map-overlay-research-button {
    top: 12px;
    z-index: 4;
    max-width: calc(100% - 24px);
    white-space: nowrap;
  }

  .search-box button,
  .map-search-box button {
    padding: 13px;
  }

  :deep(.map) {
    height: min(58vh, 560px);
    min-height: 360px;
    border-radius: 20px;
  }

  .place-list-panel {
    position: relative;
    right: auto;
    bottom: auto;
    left: auto;
    z-index: 10;
    width: 100%;
    height: auto;
    max-height: none;
    min-height: 0;
    margin-top: 0;
  }

  .map-content.has-selected-place .place-list-panel {
    height: auto;
    max-height: none;
  }

  .place-detail-panel {
    position: relative;
    right: auto;
    bottom: auto;
    left: auto;
    width: 100%;
    height: auto;
    min-height: 0;
    max-height: none;
  }

  .place-detail-panel.is-collapsed {
    max-height: none;
  }

  .place-detail-panel.is-compact-detail {
    max-height: none;
  }

  .split-place-card,
  .split-place-card.has-kakao-detail {
    height: auto;
    min-height: 0;
  }

  .kakao-frame-section {
    height: 300px;
    min-height: 260px;
  }

  .tab-button {
    min-width: 84px;
  }

  .kakao-detail-drawer {
    width: 100%;
  }
}

@media (max-width: 480px) {
  .home-page {
    padding: 12px;
  }

  h1 {
    font-size: 28px;
  }

  .search-section {
    padding-top: 32px;
  }

  .search-box {
    flex-direction: column;
    gap: 6px;
    padding: 8px;
  }

  .search-box input {
    width: 100%;
    padding: 13px 14px;
  }

  .search-box button,
  .map-search-box button,
  .clarification-follow-up button {
    width: 100%;
  }

  .landing-preset-buttons,
  .ai-preset-buttons {
    gap: 6px;
  }

  .conversation-search-card {
    padding: 10px 0;
    border-radius: 16px;
  }

  .conversation-compact-bar {
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .conversation-compact-bar button {
    width: 100%;
  }

  .clarification-bubble {
    max-width: 100%;
  }

  .clarification-follow-up {
    grid-template-columns: 1fr;
  }

  .result-controls {
    gap: 8px;
  }

  .result-filter-buttons {
    width: 100%;
  }

  .place-list-name-row,
  .place-list-meta,
  .place-list-recommend-meta,
  .ai-web-search-heading,
  .ai-web-search-candidate-title {
    align-items: flex-start;
    flex-direction: column;
  }

  .source-badge,
  .ai-web-search-candidate-title span {
    max-width: 100%;
    text-align: left;
  }

  .candidate-button {
    flex-direction: column;
    gap: 6px;
  }

  .candidate-kind {
    max-width: 100%;
    text-align: left;
  }

  .place-list-panel {
    padding: 10px;
  }

  .place-list-select-button {
    padding: 10px 6px;
  }

  :deep(.map) {
    height: 360px;
    min-height: 300px;
  }
}
</style>
