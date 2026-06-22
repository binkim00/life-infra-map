<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { aiSearchRecommendations, getKakaoPlaceTags, getSavedPlaces } from '@/api/recommendation'
import KakaoMap from '@/components/KakaoMap.vue'

const props = defineProps({
  initialTab: {
    type: String,
    default: 'search',
  },
})

const normalizeTab = (tab) => {
  return ['search', 'map'].includes(tab) ? tab : 'search'
}

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
}
const CATEGORY_KAKAO_KEYWORDS = {
  cafe: '카페',
  shelter: '쉼터',
  city_park: '공원',
  beach: '해수욕장',
  tourism: '관광지',
  smoking_area: '흡연구역',
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
}
const INTENT_NEGATIVE_TAGS = {
  waiting_place: ['실외', '야외'],
}
const INTENT_KAKAO_KEYWORD_CANDIDATES = {
  work_cafe: ['카페', '작업 카페', '공부 카페', '스터디카페'],
  waiting_place: ['카페', '쉼터', '실내 쉼터'],
  walk_healing: ['공원', '산책로', '전망대'],
  smoking_area: ['흡연구역', '흡연실'],
}
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

const mapCenter = ref(DEFAULT_CENTER)
const mapViewportBounds = ref(null)
const mapFitBoundsKey = ref(0)
const currentLocationPlace = ref([])
const allSearchResults = ref([])
const visibleCount = ref(DISPLAY_BATCH_SIZE)
const sortMode = ref('distance')
const resultSourceLabel = ref('검색 결과')
const resultMessageSuffix = ref('')
const selectedPlace = ref(null)
const detailTagList = ref(null)
const baseLocationCandidates = ref([])
const pendingBaseLocationSearch = ref(null)
const isResultListCollapsed = ref(false)
const isPlaceDetailCollapsed = ref(false)

const isLocating = ref(false)
const isSearchingMap = ref(false)

const locationMessage = ref('지도 버튼을 누르면 현재 위치 기준으로 지도를 표시합니다.')
const loadingMessage = ref('')
const mapSearchKeyword = ref('')
const aiSearchKeyword = ref('')
const mapAiParse = ref(null)
const activeSearchPlan = ref(null)

const showDetailPanel = ref(false)
const detailFrameError = ref(false)

const sortedSearchResults = computed(() => {
  return sortSearchResults(allSearchResults.value)
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
  return visibleCount.value < allSearchResults.value.length
})

const resultCountText = computed(() => {
  if (!allSearchResults.value.length) {
    return ''
  }

  const suffix = resultMessageSuffix.value
    ? ` · ${resultMessageSuffix.value}`
    : ''

  return `${resultSourceLabel.value} ${allSearchResults.value.length}개 중 ${searchedPlaces.value.length}개 표시${suffix}`
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

  },
)

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

  mapSearchKeyword.value = searchKeyword.value.trim()
  activeTab.value = 'map'

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

const openMapWithCurrentLocation = () => {
  activeTab.value = 'map'

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
  const currentContextPrefixPattern = /^(근처|주변|인근|가까운|가까이)\s+(.+)$/
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

  return !NON_REGION_LOCATION_WORDS.some((word) => {
    const wordText = normalizeLocationText(word)
    return baseText === wordText || baseText.includes(wordText)
  })
}

const isLikelyRegionSearchPair = (locationQuery, targetQuery) => {
  const locationText = normalizeLocationText(locationQuery)
  const targetText = normalizeLocationText(targetQuery)

  if (!locationText || !targetText) return false

  if (NON_REGION_LOCATION_WORDS.some((word) => locationText === normalizeLocationText(word))) {
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
  '쉴',
  '쉬',
  '힐링',
  '산책',
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
  const hasWorkCafeKeyword = WORK_CAFE_KEYWORDS.some((keyword) => {
    return queryText.includes(normalizeLocationText(keyword))
  })

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
  const targetQuery = parsed.targetQuery || parsed.targetKeyword || correction.normalizedQuery
  const categoryHint = getCategoryHint(targetQuery)
  const recommendationIntent = getRecommendationIntent(`${correction.normalizedQuery} ${targetQuery}`)
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
  const preferredMatched = tagNames.filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return preferredTags.some((preferredTag) => {
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
    return preferredTags.some((preferredTag) => {
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
    kakaoPlaceId: kakaoPlace.kakaoPlaceId || dbPlace.kakaoPlaceId || dbPlace.externalId,
    placeUrl: kakaoPlace.placeUrl || dbPlace.placeUrl,
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

const getKakaoDetailUrl = (place) => {
  if (place?.placeUrl || place?.place_url) {
    return place.placeUrl || place.place_url
  }

  if (place?.kakaoPlaceId) {
    return `https://place.map.kakao.com/${place.kakaoPlaceId}`
  }

  if ((place?.source === 'kakao_local' || place?.rawSource === 'kakao_local') && place?.externalId) {
    return `https://place.map.kakao.com/${place.externalId}`
  }

  return ''
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
    place?.sourceLabel === 'DB추천' ||
    place?.sourceLabel === '카카오+DB' ||
    place?.tagSource === 'DB 추천 결과' ||
    place?.tagSource?.includes('DB 추천 결과')
  )
}

const useDefaultMapLocation = () => {
  activeTab.value = 'map'
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

  return baseScore + sourceBonus + placeShapeScore - waitingPenalty
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

const compareByDistance = (firstPlace, secondPlace) => {
  const firstDistance = getDistanceValue(firstPlace)
  const secondDistance = getDistanceValue(secondPlace)

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
    if (sortMode.value === 'recommendation') {
      return compareForRecommendationSearch(firstPlace, secondPlace)
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
  } = {},
) => {
  return places.map((place) => {
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
    const ancillaryAdjustment = getAncillaryPlaceAdjustment({
      place,
      query,
      categoryHint,
      recommendationIntent,
      isAncillaryIntent,
    })

    return {
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
      dataQualityStatus: savedTagData.data_quality_status || null,
      dataQualityScore: savedTagData.data_quality_score || null,
      rawScores,
      recommendScore: hasTagData
        ? (
          recommendationData.recommendScore ??
          rawScores.recommendation_ready_score ??
          savedTagData.data_quality_score ??
          null
        )
        : null,
      recommendationReason: recommendationData.recommendationReason,
      matchedTags: recommendationData.matchedTags,
      recommendationConfidence: recommendationData.recommendationConfidence,
      externalCandidateMessage: hasTagData ? '' : '세부 태그 데이터 없음',
      recommendationIntent,
      preferredTags,
      preferredMatchCount: recommendationData.preferredMatchCount || 0,
      takeoutHeavy,
      waitingPlacePenalty: recommendationData.waitingPlacePenalty || waitingSuitability.penalty || 0,
      waitingPlaceExcluded: recommendationData.waitingPlaceExcluded || waitingSuitability.excluded || false,
      waitingPlacePenaltyReason: recommendationData.waitingPlacePenaltyReason || waitingSuitability.reason || null,
      mainPlaceScore: ancillaryAdjustment.mainPlaceScore,
      ancillaryPlacePenalty: ancillaryAdjustment.ancillaryPlacePenalty,
      intentMismatchPenalty: ancillaryAdjustment.intentMismatchPenalty,
      isAncillaryPlace: ancillaryAdjustment.isAncillaryPlace,
      resultType: hasTagData
        ? (
          !preferredTags.length || recommendationData.preferredMatchCount > 0
            ? 'kakao_tag_matched'
            : 'kakao_tag_weak'
        )
        : (
          waitingSuitability.excluded
            ? 'kakao_unsuitable_waiting_place'
            : (takeoutHeavy ? 'kakao_takeout_untagged' : 'kakao_only')
        ),
    }
  }).filter((place) => {
    return !(recommendationIntent === 'waiting_place' && place.waitingPlaceExcluded)
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

  place.tags?.forEach((tag) => {
    tags.push(makeTag(tag.name, tag.source))
  })

  return tags
}

const convertDbPlaces = (places) => {
  return places.map((place) => {
    const externalId = place.external_id || place.externalId || null
    const isKakaoLocal = place.source === 'kakao_local'
    const ancillaryAdjustment = getAncillaryPlaceAdjustment({
      place: {
        ...place,
        rawCategory: place.category,
      },
      query: place.name || '',
    })

    return {
      id: `db-${place.id}`,
      savedPlaceId: place.id,
      source: place.source,
      sourceName: place.source_name || place.sourceName || '',
      externalId,
      kakaoPlaceId: isKakaoLocal && externalId ? externalId : null,
      rawCategory: place.category,
      name: place.name,
      category: getDbCategoryText(place.category),
      address: place.address,
      detailLocation: place.detail_location,
      lat: Number(place.lat),
      lng: Number(place.lng),
      distance: place.distance ?? null,
      phone: '',
      placeUrl: isKakaoLocal && externalId
        ? `https://place.map.kakao.com/${externalId}`
        : '',
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
      recommendScore:
        place.raw?.scores?.recommendation_ready_score ??
        place.data_quality_score ??
        null,
      mainPlaceScore: ancillaryAdjustment.mainPlaceScore,
      ancillaryPlacePenalty: ancillaryAdjustment.ancillaryPlacePenalty,
      intentMismatchPenalty: ancillaryAdjustment.intentMismatchPenalty,
      isAncillaryPlace: ancillaryAdjustment.isAncillaryPlace,
    }
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

  ; (place.matched_tags || place.runtime_tags || []).forEach((tagName) => {
    tags.push(makeTag(tagName, 'checked'))
  })

  place.suggested_tags?.forEach((tagName) => {
    tags.push(makeTag(tagName, 'blog_search'))
  })

  place.verified_tags?.forEach((tagName) => {
    tags.push(makeTag(tagName, 'user_verified'))
  })

  place.warning_tags?.forEach((tagName) => {
    tags.push(makeTag(tagName, 'warning_tags'))
  })

  return tags
}

const getPreferredTagMatchCount = (tagNames = [], preferredTags = []) => {
  return tagNames.filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return preferredTags.some((preferredTag) => {
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
  } = {},
) => {
  return places.map((place) => {
    const externalId = place.external_id || place.externalId || null
    const isKakaoLocal = place.source === 'kakao_local'
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
        ...(place.matched_tags || []),
        ...(place.runtime_tags || []),
        ...(place.suggested_tags || []),
        ...(place.verified_tags || []),
      ],
      preferredTags,
    )

    return {
      id: `recommendation-${place.id}`,
      savedPlaceId: place.id,
      source: place.source,
      sourceName: place.source_name || place.sourceName || '',
      externalId,
      kakaoPlaceId: isKakaoLocal && externalId ? externalId : null,
      rawCategory: place.category,
      name: place.name,
      category: getDbCategoryText(place.category),
      address: place.address,
      detailLocation: place.detail_location,
      lat: Number(place.lat),
      lng: Number(place.lng),
      distance: place.distance ?? place.distance_m ?? null,
      phone: '',
      placeUrl: isKakaoLocal && externalId
        ? `https://place.map.kakao.com/${externalId}`
        : '',
      navigationUrl: `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`,
      markerColor: '#7c3aed',
      searchSource: 'local_db',
      sourceLabel: 'DB추천',
      tags: makeRecommendationTags(place),
      tagSource: 'DB 추천 결과',
      dataQualityStatus: place.data_quality_status,
      dataQualityScore: place.data_quality_score,
      rawScores: place.raw_scores || {},
      suggestedTags: place.suggested_tags || [],
      verifiedTags: place.verified_tags || [],
      warningTags: place.warning_tags || [],
      tagDetails: place.tag_details || [],
      recommendScore: Math.min(
        100,
        Number(place.score ?? place.data_quality_score ?? 0) + preferredMatchCount * 8,
      ),
      recommendationReason: place.recommend_reason,
      matchedTags: place.matched_tags || place.runtime_tags || [],
      matchLevel: place.match_level,
      recommendationConfidence: place.recommendation_confidence,
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
    }
  })
}

const assignMarkerLabels = (places) => {
  return places.map((place, index) => ({
    ...place,
    markerLabel: getMarkerLabel(index),
  }))
}

const setSearchResults = ({
  results,
  sourceLabel = '검색 결과',
  messageSuffix = '',
}) => {
  allSearchResults.value = results
  visibleCount.value = DISPLAY_BATCH_SIZE
  resultSourceLabel.value = sourceLabel
  resultMessageSuffix.value = messageSuffix
  placeListItemRefs.value = {}
  mapFitBoundsKey.value += 1
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
    allSearchResults.value.length,
  )
}

const searchSavedPlaces = async ({
  targetKeyword,
  center,
  radius = SEARCH_RADIUS,
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

  return convertDbPlaces(allowedPlaces)
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
    },
  )
  const dedupedResults = shouldUseDbPlaces
    ? dedupeSearchResults(kakaoResults, dbPlaces)
    : kakaoResults

  if (!dedupedResults.length) {
    clearSearchResults()
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 검색 결과가 없습니다.`
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
    return
  }

  setSearchResults({
    results: dedupedResults,
    sourceLabel: '카카오 결과',
  })
  locationMessage.value = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 카카오 검색 결과를 표시했습니다.`
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

const getBaseCandidateKind = (candidate) => {
  const nameText = normalizeLocationText(candidate.place_name)
  const categoryText = normalizeLocationText(candidate.category_name)

  if (candidate.source === 'address') {
    return '주소'
  }

  if (BASE_LOCATION_TRANSPORT_KEYWORDS.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return nameText.includes(normalizedKeyword) || categoryText.includes(normalizedKeyword)
  })) {
    return '역/교통'
  }

  return '장소'
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
  const reasons = []
  let score = 0

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
    candidateKind: getBaseCandidateKind(candidate),
  }
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

  return dedupeBaseLocationCandidates(candidates)
    .map((candidate) => scoreBaseLocationCandidate(candidate, baseKeyword))
    .sort((first, second) => {
      return second.score - first.score || first.rank - second.rank
    })
    .slice(0, 8)
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

const getKakaoKeywordForAiSearch = (data, query) => {
  const categories = data?.conditions?.categories || data?.ai_parse?.categories || []
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
  const categoryHint = parsedIntent?.categoryHint || ''
  const isAncillaryIntent = parsedIntent?.isAncillaryIntent || false
  const data = await aiSearchRecommendations({
    query: targetQuery,
    lat: center.lat,
    lng: center.lng,
    limit: DB_SEARCH_RESULT_COUNT,
  })

  mapAiParse.value = data.ai_parse || null
  const recommendationResults = convertRecommendationPlaces(data.results || [], {
    preferredTags,
    recommendationIntent,
  })
  const kakaoKeywordCandidates = parsedIntent?.kakaoKeywordCandidates?.length
    ? parsedIntent.kakaoKeywordCandidates
    : [parsedIntent?.categoryKeyword || getKakaoKeywordForAiSearch(data, targetQuery)]
  let kakaoResults = []

  if (kakaoKeywordCandidates.length) {
    loadingMessage.value = '주변 장소 검색 중'
    const centerLatLng = new window.kakao.maps.LatLng(center.lat, center.lng)
    const kakaoSearchOptions = {
      location: centerLatLng,
      radius: SEARCH_RADIUS,
      sort: window.kakao.maps.services.SortBy.DISTANCE,
    }
    let kakaoPlaces = await runKakaoKeywordCandidateSearch(
      placesService,
      kakaoKeywordCandidates,
      kakaoSearchOptions,
      { maxPages: 1 },
    )
    kakaoPlaces = await appendMainPlaceFallbackResults({
      placesService,
      places: kakaoPlaces,
      searchOptions: kakaoSearchOptions,
      searchContext: {
        query: targetQuery,
        categoryHint,
        recommendationIntent,
        isAncillaryIntent,
      },
      fallbackKeyword: parsedIntent?.mainPlaceFallbackKeyword || '',
    })
    const savedTagDataByExternalId = await searchKakaoSavedTags(kakaoPlaces)
    kakaoResults = convertKakaoPlaces(kakaoPlaces, savedTagDataByExternalId, {
      query: targetQuery,
      center,
      preferredTags,
      recommendationIntent,
      categoryHint,
      isAncillaryIntent,
    })
  }

  loadingMessage.value = '추천 결과 정리 중'
  const mergedResults = dedupeSearchResults(kakaoResults, recommendationResults)

  if (!mergedResults.length) {
    clearSearchResults()
    locationMessage.value = `"${originalQuery}" 조건에 맞는 추천 결과가 없습니다.`
    return
  }

  setSearchResults({
    results: mergedResults,
    sourceLabel: 'AI 검색 결과',
    messageSuffix: `DB ${recommendationResults.length}개, 카카오 ${kakaoResults.length}개 · ${data.scenario}`,
  })

  locationMessage.value = `${baseLabel} "${originalQuery}" 자연어 조건의 DB 추천과 카카오 검색 결과를 함께 표시했습니다.`
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

const runRegionMapSearch = async ({
  placesService,
  originalQuery,
  locationQuery,
  targetQuery,
  parsedIntent = null,
}) => {
  loadingMessage.value = '지역 장소 검색 중'
  const recommendationIntent = parsedIntent?.recommendationIntent || getRecommendationIntent(`${originalQuery} ${targetQuery}`)
  const preferredTags = parsedIntent?.preferredTags || getPreferredTagsForIntent(recommendationIntent)
  const categoryHint = parsedIntent?.categoryHint || ''
  const isAncillaryIntent = parsedIntent?.isAncillaryIntent || false
  sortMode.value = recommendationIntent ? 'recommendation' : 'distance'
  const categoryKeyword = parsedIntent?.categoryKeyword || getRegionSearchCoreKeyword(targetQuery)
  const searchKeywords = [
    `${locationQuery} ${targetQuery}`.trim(),
    ...(parsedIntent?.kakaoKeywordCandidates || []).map((keyword) => `${locationQuery} ${keyword}`.trim()),
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
    return
  }

  const savedTagDataByExternalId = await searchKakaoSavedTags(kakaoPlaces)
  const convertedResults = convertKakaoPlaces(kakaoPlaces, savedTagDataByExternalId, {
    query: originalQuery,
    preferredTags,
    recommendationIntent,
    categoryHint,
    isAncillaryIntent,
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
  locationMessage.value = `"${originalQuery}" 지역 검색 결과를 표시했습니다.`
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

const searchKakaoPlaces = async ({ useMapBounds = false } = {}) => {
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
  loadingMessage.value = '주변 장소 검색 중'
  sortMode.value = 'distance'
  mapAiParse.value = null
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false

  const placesService = new window.kakao.maps.services.Places()
  const geocoder = new window.kakao.maps.services.Geocoder()
  const parsedKeyword = buildSearchPlan(keyword)
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

    if (!parsedKeyword.hasBaseLocation) {
      const currentContext = await resolveCurrentContextCenter()
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

const searchAiRecommendationsOnMap = async () => {
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
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false

  try {
    const placesService = new window.kakao.maps.services.Places()
    const geocoder = new window.kakao.maps.services.Geocoder()
    const parsedQuery = buildSearchPlan(query)
    activeSearchPlan.value = parsedQuery
    let searchCenter = mapCenter.value
    let baseLabel = '현재 지도 중심 기준'

    baseLocationCandidates.value = []
    pendingBaseLocationSearch.value = null

    if (parsedQuery.searchMode === 'region_search') {
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
      const currentContext = await resolveCurrentContextCenter()
      searchCenter = currentContext.center
      baseLabel = currentContext.baseLabel
    }

    if (parsedQuery.hasBaseLocation) {
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

      searchCenter = resolvedBase.center
      baseLabel = resolvedBase.label
      pendingBaseLocationSearch.value = null
    }

    await runAiMapSearchAtCenter({
      placesService,
      originalQuery: query,
      targetQuery: parsedQuery.targetQuery,
      center: searchCenter,
      baseLabel,
      parsedIntent: parsedQuery,
    })
  } catch (error) {
    console.error(error)
    mapAiParse.value = null
    clearSearchResults()
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = 'AI 검색 중 오류가 발생했습니다.'
  } finally {
    if (!baseLocationCandidates.value.length) {
      isSearchingMap.value = false
      loadingMessage.value = ''
    }
  }
}

const performUnifiedMapSearch = async ({ useMapBounds = false } = {}) => {
  const keyword = mapSearchKeyword.value.trim()

  if (!keyword) {
    alert('검색어를 입력해주세요.')
    return
  }

  const parsedKeyword = buildSearchPlan(keyword)
  activeSearchPlan.value = parsedKeyword
  const searchMode = getUnifiedSearchMode(keyword, parsedKeyword, { useMapBounds })

  if (['region_search', 'recommendation_query'].includes(searchMode)) {
    sortMode.value = parsedKeyword.recommendationIntent
      ? 'recommendation'
      : 'distance'
    aiSearchKeyword.value = keyword
    await searchAiRecommendationsOnMap()
    return
  }

  sortMode.value = 'distance'
  await searchKakaoPlaces({ useMapBounds })
}

const runAiPresetSearch = async (query) => {
  mapSearchKeyword.value = query
  await nextTick()
  await performUnifiedMapSearch()
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
      setSearchResults({
        results: candidate.regionResults || [],
        sourceLabel: '지역 검색 결과',
        messageSuffix: `${candidate.place_name} · 카카오 ${(candidate.regionResults || []).length}개`,
      })
      locationMessage.value = `${resolvedBase.label} "${pendingSearch.originalQuery}" 지역 검색 결과를 표시했습니다.`
      return
    }

    await runAiMapSearchAtCenter({
      placesService,
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
  mapSearchKeyword.value = ''
  aiSearchKeyword.value = ''
  mapAiParse.value = null
  activeSearchPlan.value = null
  baseLocationCandidates.value = []
  pendingBaseLocationSearch.value = null
  loadingMessage.value = ''
  isSearchingMap.value = false
  currentLocationPlace.value = []
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false
  clearSearchResults()
  locationMessage.value = '검색이 초기화되었습니다. 검색어를 입력하거나 지도를 이동한 뒤 다시 검색해보세요.'
}

const selectPlace = (place) => {
  selectedPlace.value = place
  detailFrameError.value = false
  isPlaceDetailCollapsed.value = false
}

const selectPlaceFromList = (place) => {
  selectedPlace.value = place
  detailFrameError.value = false
  isPlaceDetailCollapsed.value = false
}

const closePlaceCard = () => {
  selectedPlace.value = null
  detailFrameError.value = false
  isPlaceDetailCollapsed.value = false
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
  <main class="home-page">
    <header class="page-header">
      <div class="header-main">
        <div class="top-bar">
          <button type="button" class="tab-button" :class="{ active: activeTab === 'search' }"
            @click="activeTab = 'search'">
            검색창
          </button>

          <button type="button" class="tab-button" :class="{ active: activeTab === 'map' }"
            @click="openMapWithCurrentLocation">
            지도
          </button>
        </div>
      </div>

      
    </header>

    <section v-if="activeTab === 'search'" class="search-section">
      <div class="intro">
        <p class="eyebrow">상황 기반 장소 추천 지도 서비스</p>
        <h1>지금 필요한 장소를 검색해보세요</h1>
        <p class="description">
          예: 조용히 노트북 할 카페, 근처 화장실, 산책하기 좋은 곳
        </p>
      </div>

      <div class="search-box">
        <input v-model="searchKeyword" type="text" placeholder="지금 어떤 장소가 필요하신가요?" @keyup.enter="handleSearch" />

        <button type="button" @click="handleSearch">
          검색
        </button>
      </div>
    </section>

    <section v-else-if="activeTab === 'map'" class="map-section-wrap">
      <div class="map-header">
        <div>
          <h1>상황 기반 추천 지도</h1>
          <p>
            {{ isLocating ? '현재 위치를 불러오는 중입니다...' : locationMessage }}
          </p>
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
            검색 초기화
          </button>
        </div>
      </div>

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

      <form class="map-search-box ai-search-box" @submit.prevent="performUnifiedMapSearch">
        <label for="map-keyword-search">AI 추천 검색</label>
        <input
          id="map-keyword-search"
          v-model="mapSearchKeyword"
          type="text"
          placeholder="예: 카페, 광주 카페, 서면역 근처 흡연 가능한 곳, 비 오는데 쉴 곳"
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
        class="map-content"
        :class="{
          'has-result-list': searchedPlaces.length,
          'has-selected-place': selectedPlace,
          'is-list-collapsed': isResultListCollapsed,
        }"
      >
        <aside
          v-if="searchedPlaces.length || isSearchingMap"
          class="place-list-panel"
          :class="{ 'is-collapsed': isResultListCollapsed }"
        >
          <div class="place-list-top">
            <div>
              <p class="place-list-label">검색 결과</p>
              <h2>{{ isSearchingMap ? loadingMessage : resultCountText }}</h2>
            </div>

            <button
              type="button"
              class="panel-toggle-button"
              @click="isResultListCollapsed = !isResultListCollapsed"
            >
              {{ isResultListCollapsed ? '펼치기' : '접기' }}
            </button>
          </div>

          <div v-if="isResultListCollapsed" class="collapsed-panel-summary">
            {{ allSearchResults.length }}개
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
                  @click="selectPlaceFromList(place)"
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

                  </span>
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
          />

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
                </div>

              </section>

              <div class="info-list compact-info-list">
                <div v-if="isRecommendationPlace(selectedPlace)" class="recommendation-summary">
                  <div v-if="selectedPlace.recommendScore !== null && selectedPlace.recommendScore !== undefined">
                    <span>추천 점수</span>
                    <strong>{{ getRecommendScore(selectedPlace) }}점</strong>
                  </div>

                  <div v-if="getRecommendationConfidence(selectedPlace)">
                    <span>추천 신뢰도</span>
                    <strong>{{ getRecommendationConfidenceText(getRecommendationConfidence(selectedPlace)) }}</strong>
                  </div>
                </div>

                <div v-if="isRecommendationPlace(selectedPlace) && getRecommendationReason(selectedPlace)" class="info-row">
                  <span>추천 이유</span>
                  <p>{{ getRecommendationReason(selectedPlace) }}</p>
                </div>

                <div v-if="isRecommendationPlace(selectedPlace) && getMatchedTagText(selectedPlace)" class="info-row">
                  <span>매칭 태그</span>
                  <p>{{ getMatchedTagText(selectedPlace) }}</p>
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
      </div>
    </section>

  </main>
</template>

<style scoped>
.page-header {
  margin-bottom: 24px;
}

.header-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 16px;
  align-items: center;
}

.top-bar {
  grid-column: 2;
}

@media (max-width: 720px) {
  .header-main {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
}

.home-page {
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(80, 140, 255, 0.14), transparent 32%),
    linear-gradient(180deg, #ffffff 0%, #f6f7fb 100%);
}

.top-bar {
  width: fit-content;
  margin: 0 auto;
  padding: 6px;
  display: flex;
  gap: 6px;
  background: #ffffff;
  border: 1px solid #e5e8f0;
  border-radius: 999px;
  box-shadow: 0 8px 24px rgba(20, 35, 70, 0.08);
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
}

.tab-button.active {
  background: #2563eb;
  color: #ffffff;
}

.search-section {
  min-height: calc(100vh - 90px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.intro {
  margin-bottom: 32px;
  text-align: center;
}

.eyebrow {
  margin: 0 0 12px;
  color: #2563eb;
  font-size: 15px;
  font-weight: 800;
}

h1 {
  margin: 0;
  color: #111827;
  font-size: 42px;
  line-height: 1.25;
  letter-spacing: -0.04em;
}

.description {
  margin: 16px 0 0;
  color: #667085;
  font-size: 17px;
}

.search-box {
  width: min(720px, 100%);
  padding: 8px;
  display: flex;
  gap: 8px;
  background: #ffffff;
  border: 1px solid #e5e8f0;
  border-radius: 22px;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.12);
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
  border-radius: 16px;
  background: #2563eb;
  color: #ffffff;
  font-size: 16px;
  font-weight: 800;
  cursor: pointer;
}

.map-section-wrap {
  width: 100%;
  max-width: none;
  margin: 28px 0 0;
}

.map-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.map-header h1 {
  font-size: 24px;
}

.map-header p {
  margin: 6px 0 0;
  color: #667085;
  font-size: 14px;
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
  border: 0;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
}

.map-location-button {
  background: #eef6ff;
  color: #1d4ed8;
}

.map-location-button:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.map-parser-status {
  margin-bottom: 12px;
  padding: 10px 12px;
  display: grid;
  gap: 3px;
  border-radius: 8px;
}

.map-parser-status strong {
  font-size: 14px;
}

.map-parser-status span {
  font-size: 13px;
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
  margin-bottom: 12px;
  padding: 8px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  background: #ffffff;
  border: 1px solid #e5e8f0;
  border-radius: 14px;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
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
  padding: 12px 14px;
  border: 0;
  border-radius: 10px;
  background: #f8fafc;
  outline: none;
  font-size: 15px;
}

.ai-search-box {
  border-color: #ddd6fe;
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
  background: #ef4444;
  color: #ffffff;
  font-size: 15px;
  font-weight: 800;
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
  background: #7c3aed !important;
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
  background: #f2f4f7 !important;
  color: #344054 !important;
  font-size: 13px;
}

.map-reset-button {
  background: #f2f4f7 !important;
  color: #344054 !important;
}

.base-location-candidates {
  margin-bottom: 12px;
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
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: clamp(16px, 1.4vw, 24px);
  align-items: stretch;
}

.map-content.has-result-list {
  grid-template-columns: clamp(300px, 22vw, 380px) minmax(0, 1fr);
}

.map-content.has-result-list.is-list-collapsed {
  grid-template-columns: 84px minmax(0, 1fr);
}

.map-content.has-result-list.has-selected-place {
  grid-template-columns: clamp(300px, 22vw, 380px) minmax(0, 1fr);
}

.map-content.has-result-list.has-selected-place.is-list-collapsed {
  grid-template-columns: 84px minmax(0, 1fr);
}

.map-content.has-selected-place:not(.has-result-list) {
  grid-template-columns: minmax(0, 1fr);
}

.place-list-panel {
  height: calc(100vh - clamp(200px, 20vh, 230px));
  min-height: 520px;
  padding: clamp(12px, 1vw, 16px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #ffffff;
  border: 1px solid #e5e8f0;
  border-radius: 22px;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.12);
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
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
}

.place-list-top h2 {
  margin: 0;
  color: #111827;
  font-size: 16px;
  letter-spacing: -0.03em;
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
  background: #eff6ff;
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

.place-list-marker {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  margin-top: 2px;
  display: grid;
  place-items: center;
  border: 2px solid #ef4444;
  border-radius: 999px;
  background: #ffffff;
  color: #ef4444;
  font-size: 13px;
  font-weight: 900;
}

.place-list-marker.source-db {
  border-color: #2563eb;
  color: #2563eb;
}

.place-list-marker.source-base {
  border-color: #16a34a;
  color: #16a34a;
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
  height: calc(100vh - clamp(200px, 20vh, 230px));
  min-height: 520px;
  border: 0;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.12);
}

.place-detail-panel {
  position: absolute;
  top: clamp(14px, 1.2vw, 20px);
  right: clamp(14px, 1.2vw, 20px);
  bottom: clamp(14px, 1.2vw, 20px);
  z-index: 8;
  width: min(clamp(360px, 28vw, 520px), calc(100% - 28px));
  min-height: 0;
  overflow-y: auto;
}

.place-detail-panel.is-collapsed {
  top: auto;
  left: auto;
  bottom: clamp(14px, 1.2vw, 20px);
  width: min(360px, calc(100% - 28px));
  overflow: visible;
}

.place-detail-panel.is-compact-detail {
  bottom: auto;
  max-height: calc(100% - 28px);
}

.place-detail-panel.is-collapsed.is-compact-detail {
  bottom: clamp(14px, 1.2vw, 20px);
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
  height: auto;
  min-height: 100%;
  padding: clamp(16px, 1.2vw, 22px);
  display: flex;
  flex-direction: column;
  gap: clamp(14px, 1.1vw, 18px);
  background: #ffffff;
  border: 1px solid #e5e8f0;
  border-radius: 22px;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.12);
}

.split-place-card.has-kakao-detail {
  height: auto;
  min-height: 100%;
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
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 12px;
  border-bottom: 1px solid #eef0f4;
  scrollbar-width: thin;
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
  border-radius: 14px;
  font-size: 14px;
  font-weight: 900;
  text-align: center;
  text-decoration: none;
}

.detail-action-button.primary {
  background: #fee500;
  color: #111827;
}

.detail-action-button.secondary {
  background: #f2f4f7;
  color: #344054;
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

  .map-content.has-result-list,
  .map-content.has-result-list.has-selected-place,
  .map-content.has-result-list.is-list-collapsed,
  .map-content.has-result-list.has-selected-place.is-list-collapsed,
  .map-content.has-selected-place:not(.has-result-list) {
    grid-template-columns: 1fr;
  }

  .place-list-panel {
    height: auto;
    min-height: auto;
  }

  .place-list-panel.is-collapsed {
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
    max-height: 240px;
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

  .map-section-wrap {
    margin-top: 22px;
  }

  .map-header {
    flex-direction: column;
  }

  .map-header-actions {
    width: 100%;
    justify-content: stretch;
  }

  .map-location-button,
  .map-header-reset {
    flex: 1;
    min-width: 0;
  }

  .map-search-box {
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
    height: calc(100vh - 270px);
    min-height: 440px;
  }

  .place-detail-panel {
    top: auto;
    right: 8px;
    bottom: 8px;
    left: 8px;
    width: auto;
    max-height: 58%;
  }

  .place-detail-panel.is-collapsed {
    right: 8px;
    bottom: 8px;
    left: 8px;
    width: auto;
    max-height: none;
  }

  .place-detail-panel.is-compact-detail {
    max-height: 58%;
  }

  .split-place-card,
  .split-place-card.has-kakao-detail {
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
</style>
