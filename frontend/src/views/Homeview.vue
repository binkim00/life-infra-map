<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { aiSearchRecommendations, getKakaoPlaceTags, getSavedPlaces } from '@/api/recommendation'
import KakaoMap from '@/components/KakaoMap.vue'
import RecommendationTestPanel from '@/components/RecommendationTestPanel.vue'

const props = defineProps({
  initialTab: {
    type: String,
    default: 'search',
  },
})

const normalizeTab = (tab) => {
  return ['search', 'map', 'recommendation'].includes(tab) ? tab : 'search'
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

const isLocating = ref(false)
const isSearchingMap = ref(false)

const locationMessage = ref('지도 버튼을 누르면 현재 위치 기준으로 지도를 표시합니다.')
const mapSearchKeyword = ref('')
const mapAiParse = ref(null)

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

const placeListItemRefs = ref({})

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
  () => {
    scrollSelectedPlaceIntoView()
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
    await searchKakaoPlaces()
  } catch (error) {
    console.error(error)
    locationMessage.value = '카카오 지도 서비스를 불러오는 중입니다. 잠시 후 지도 검색 버튼을 눌러주세요.'
  }
}

const openMapWithCurrentLocation = () => {
  activeTab.value = 'map'

  if (!navigator.geolocation) {
    locationMessage.value = '현재 브라우저에서 위치 정보를 지원하지 않아 기본 위치로 지도를 표시합니다.'
    mapCenter.value = DEFAULT_CENTER
    return
  }

  isLocating.value = true
  locationMessage.value = '현재 위치를 확인하는 중입니다.'

  navigator.geolocation.getCurrentPosition(
    (position) => {
      const lat = position.coords.latitude
      const lng = position.coords.longitude

      mapCenter.value = {
        lat,
        lng,
      }

      currentLocationPlace.value = [
        {
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
        },
      ]

      locationMessage.value = '현재 위치 기준으로 지도를 표시하고 있습니다.'
      isLocating.value = false
    },
    (error) => {
      console.error(error)

      mapCenter.value = DEFAULT_CENTER
      currentLocationPlace.value = []

      if (error.code === error.PERMISSION_DENIED) {
        locationMessage.value = '위치 권한이 거부되어 기본 위치로 지도를 표시합니다.'
      } else if (error.code === error.TIMEOUT) {
        locationMessage.value = '현재 위치 확인 시간이 초과되어 기본 위치로 지도를 표시합니다.'
      } else {
        locationMessage.value = '현재 위치를 가져오지 못해 기본 위치로 지도를 표시합니다.'
      }

      isLocating.value = false
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 300000,
    },
  )
}

const parseMapSearchInput = (keyword) => {
  const normalizedKeyword = keyword.replace(/\s+/g, ' ').trim()

  const aroundPattern = /^(.+?)\s*(주변|근처|인근)(?:의)?\s+(.+)$/
  const matched = normalizedKeyword.match(aroundPattern)

  if (!matched) {
    return {
      hasBaseLocation: false,
      baseKeyword: '',
      targetKeyword: normalizedKeyword,
    }
  }

  return {
    hasBaseLocation: true,
    baseKeyword: matched[1].trim(),
    targetKeyword: matched[3].trim(),
  }
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
) => {
  const allResults = []
  let page = 1

  while (allResults.length < MAX_SEARCH_RESULT_COUNT) {
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
  return name
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[^0-9a-z가-힣]/g, '')
}

const isSimilarPlaceName = (firstName, secondName) => {
  const first = normalizePlaceName(firstName)
  const second = normalizePlaceName(secondName)

  if (!first || !second) {
    return false
  }

  return first === second || first.includes(second) || second.includes(first)
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

const isDuplicateDbPlace = (kakaoPlace, dbPlace) => {
  if (
    dbPlace.source === 'kakao_local' &&
    dbPlace.externalId &&
    String(dbPlace.externalId) === String(kakaoPlace.kakaoPlaceId)
  ) {
    return true
  }

  return (
    isSimilarPlaceName(kakaoPlace.name, dbPlace.name) &&
    getDistanceMetersBetweenPlaces(kakaoPlace, dbPlace) <= 30
  )
}

const mergeDbDataIntoKakaoPlace = (kakaoPlace, dbPlace) => {
  return {
    ...kakaoPlace,
    savedPlaceId: kakaoPlace.savedPlaceId || dbPlace.savedPlaceId,
    tags: mergeTags(kakaoPlace.tags, dbPlace.tags),
    tagSource: `${kakaoPlace.tagSource} + DB 저장 데이터`,
    dataQualityStatus: kakaoPlace.dataQualityStatus || dbPlace.dataQualityStatus,
    dataQualityScore: kakaoPlace.dataQualityScore ?? dbPlace.dataQualityScore,
  }
}

const dedupeSearchResults = (kakaoResults, dbPlaces) => {
  const mergedKakaoResults = [...kakaoResults]
  const additionalDbPlaces = []

  dbPlaces.forEach((dbPlace) => {
    const duplicateIndex = mergedKakaoResults.findIndex((kakaoPlace) => {
      return isDuplicateDbPlace(kakaoPlace, dbPlace)
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
  if (place?.searchSource !== 'kakao') {
    return ''
  }

  return place.placeUrl || place.place_url || ''
}

const getPlaceNavigationUrl = (place) => {
  return (
    place?.navigationUrl ||
    place?.navigation_url ||
    place?.placeUrl ||
    place?.place_url ||
    ''
  )
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

const getRecommendScore = (place) => {
  const score = Number(
    place.recommendScore ??
    place.score ??
    place.dataQualityScore ??
    0,
  )

  return Number.isFinite(score) ? score : 0
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

const compareByRecommendation = (firstPlace, secondPlace) => {
  const scoreDifference =
    getRecommendScore(secondPlace) - getRecommendScore(firstPlace)

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
      return compareByRecommendation(firstPlace, secondPlace)
    }

    return compareByDistance(firstPlace, secondPlace)
  })

  return sortedResults.map(({ originalOrder, ...place }) => place)
}

const convertKakaoPlaces = (places, savedTagDataByExternalId = {}) => {
  return places.map((place) => {
    const savedTagData = savedTagDataByExternalId[String(place.id)] || {}
    const rawScores = savedTagData.raw_scores || {}

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
      markerColor: 'red',
      searchSource: 'kakao',
      sourceLabel: '카카오',
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
      recommendScore:
        rawScores.recommendation_ready_score ??
        savedTagData.data_quality_score ??
        null,
    }
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
  return places.map((place) => ({
    id: `db-${place.id}`,
    savedPlaceId: place.id,
    source: place.source,
    externalId: place.external_id,
    rawCategory: place.category,
    name: place.name,
    category: getDbCategoryText(place.category),
    address: place.address,
    detailLocation: place.detail_location,
    lat: Number(place.lat),
    lng: Number(place.lng),
    distance: place.distance ?? null,
    phone: '',
    placeUrl: '',
    navigationUrl: `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`,
    markerColor: 'blue',
    searchSource: 'local_db',
    sourceLabel: 'DB',
    tags: makeDbTags(place),
    tagSource: 'DB 저장 데이터',
    dataQualityStatus: place.data_quality_status,
    dataQualityScore: place.data_quality_score,
    rawScores: place.raw?.scores || {},
    recommendScore:
      place.raw?.scores?.recommendation_ready_score ??
      place.data_quality_score ??
      null,
  }))
}

const makeRecommendationTags = (place) => {
  const tags = [
    makeTag('DB추천', 'external_data'),
  ]

  const categoryText = getDbCategoryText(place.category)

  if (categoryText) {
    tags.push(makeTag(categoryText, 'category_rule'))
  }

  ;(place.matched_tags || place.runtime_tags || []).forEach((tagName) => {
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

const convertRecommendationPlaces = (places) => {
  return places.map((place) => ({
    id: `recommendation-${place.id}`,
    savedPlaceId: place.id,
    source: place.source,
    externalId: place.external_id,
    rawCategory: place.category,
    name: place.name,
    category: getDbCategoryText(place.category),
    address: place.address,
    detailLocation: place.detail_location,
    lat: Number(place.lat),
    lng: Number(place.lng),
    distance: place.distance ?? place.distance_m ?? null,
    phone: '',
    placeUrl: '',
    navigationUrl: `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`,
    markerColor: '#7c3aed',
    searchSource: 'local_db',
    sourceLabel: 'AI 추천',
    tags: makeRecommendationTags(place),
    tagSource: 'DB 추천 결과',
    dataQualityStatus: place.data_quality_status,
    dataQualityScore: place.data_quality_score,
    rawScores: place.raw_scores || {},
    recommendScore: place.score ?? place.data_quality_score ?? null,
    recommendationReason: place.recommend_reason,
    matchLevel: place.match_level,
    recommendationConfidence: place.recommendation_confidence,
  }))
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
  center,
  bounds = null,
  radius = SEARCH_RADIUS,
  baseLabel,
}) => {
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

  const kakaoPlaces = await runKakaoKeywordSearchLimited(
    placesService,
    targetKeyword,
    searchOptions,
  )

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
  mapAiParse.value = null
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false

  const placesService = new window.kakao.maps.services.Places()
  const parsedKeyword = parseMapSearchInput(keyword)
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
        center: mapCenter.value,
        bounds: searchBounds,
        radius: searchRadius,
        baseLabel: '현재 지도 화면 기준',
      })

      return
    }

    if (!parsedKeyword.hasBaseLocation) {
      await searchAroundCenter({
        placesService,
        targetKeyword,
        center: mapCenter.value,
        baseLabel: '현재 지도 중심 기준',
      })

      return
    }

    const currentCenter = new window.kakao.maps.LatLng(
      mapCenter.value.lat,
      mapCenter.value.lng,
    )

    const baseLocationResults = await runKakaoKeywordSearch(
      placesService,
      parsedKeyword.baseKeyword,
      {
        location: currentCenter,
        sort: window.kakao.maps.services.SortBy.ACCURACY,
      },
    )

    if (!baseLocationResults.length) {
      clearSearchResults()
      currentLocationPlace.value = []
      selectedPlace.value = null
      showDetailPanel.value = false
      locationMessage.value = `"${parsedKeyword.baseKeyword}" 위치를 찾지 못했습니다.`
      return
    }

    const basePlace = baseLocationResults[0]

    const baseCenter = {
      lat: Number(basePlace.y),
      lng: Number(basePlace.x),
    }

    mapCenter.value = baseCenter

    currentLocationPlace.value = [
      {
        id: `base-location-${basePlace.id}`,
        name: `검색 기준 위치: ${basePlace.place_name}`,
        category: basePlace.category_name,
        address: basePlace.road_address_name || basePlace.address_name,
        lat: Number(basePlace.y),
        lng: Number(basePlace.x),
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

    await searchAroundCenter({
      placesService,
      targetKeyword,
      center: baseCenter,
      baseLabel: `${basePlace.place_name} 기준`,
    })
  } catch (error) {
    console.error(error)
    clearSearchResults()
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = '장소 검색 중 오류가 발생했습니다.'
  } finally {
    isSearchingMap.value = false
  }
}

const searchAiRecommendationsOnMap = async () => {
  const query = mapSearchKeyword.value.trim()

  if (!query) {
    alert('AI 추천에 사용할 자연어를 입력해주세요.')
    return
  }

  isSearchingMap.value = true
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false

  try {
    const data = await aiSearchRecommendations({
      query,
      lat: mapCenter.value.lat,
      lng: mapCenter.value.lng,
      limit: DB_SEARCH_RESULT_COUNT,
    })

    mapAiParse.value = data.ai_parse || null
    const recommendationResults = convertRecommendationPlaces(data.results || [])

    if (!recommendationResults.length) {
      clearSearchResults()
      locationMessage.value = `"${query}" 조건에 맞는 DB 추천 결과가 없습니다.`
      return
    }

    setSearchResults({
      results: recommendationResults,
      sourceLabel: 'AI 추천 결과',
      messageSuffix: `${data.scenario} · ${mapAiParse.value?.parser_provider || 'rule'}`,
    })

    locationMessage.value = `"${query}" 자연어 조건을 DB 추천 결과로 표시했습니다.`
  } catch (error) {
    console.error(error)
    mapAiParse.value = null
    clearSearchResults()
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = 'AI 추천 중 오류가 발생했습니다.'
  } finally {
    isSearchingMap.value = false
  }
}

const searchCurrentMapView = () => {
  searchKakaoPlaces({ useMapBounds: true })
}

const resetMapSearch = () => {
  mapSearchKeyword.value = ''
  mapAiParse.value = null
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
}

const selectPlaceFromList = (place) => {
  selectedPlace.value = place
  detailFrameError.value = false
}

const closePlaceCard = () => {
  selectedPlace.value = null
  detailFrameError.value = false
}

const openDetailPanel = () => {
  if (!getPlaceNavigationUrl(selectedPlace.value)) {
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
    <header class="top-bar">
      <button
        type="button"
        class="tab-button"
        :class="{ active: activeTab === 'search' }"
        @click="activeTab = 'search'"
      >
        검색창
      </button>

      <button
        type="button"
        class="tab-button"
        :class="{ active: activeTab === 'map' }"
        @click="openMapWithCurrentLocation"
      >
        지도
      </button>

      <button
        type="button"
        class="tab-button"
        :class="{ active: activeTab === 'recommendation' }"
        @click="activeTab = 'recommendation'"
      >
        추천 테스트
      </button>
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
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="지금 어떤 장소가 필요하신가요?"
          @keyup.enter="handleSearch"
        />

        <button type="button" @click="handleSearch">
          검색
        </button>
      </div>
    </section>

    <section v-else-if="activeTab === 'map'" class="map-section-wrap">
      <div class="map-header">
        <div>
          <h1>지도에서 장소 검색하기</h1>
          <p>
            {{ isLocating ? '현재 위치를 불러오는 중입니다...' : locationMessage }}
          </p>
        </div>
      </div>

      <div
        v-if="mapParserStatus"
        class="map-parser-status"
        :class="mapParserStatus.className"
      >
        <strong>{{ mapParserStatus.label }}</strong>
        <span>{{ mapParserStatus.detail }}</span>
      </div>

      <div class="map-search-box">
        <input
          v-model="mapSearchKeyword"
          type="text"
          placeholder="예: 카페, 식당, 수영역 주변 카페, 서면역 근처 맛집"
          @keyup.enter="searchKakaoPlaces()"
        />

        <div class="map-search-actions">
          <button
            type="button"
            class="map-search-submit"
            :disabled="isSearchingMap"
            @click="searchKakaoPlaces()"
          >
            {{ isSearchingMap ? '검색 중...' : '지도 검색' }}
          </button>

          <button
            type="button"
            class="map-ai-button"
            :disabled="isSearchingMap || !mapSearchKeyword.trim()"
            @click="searchAiRecommendationsOnMap"
          >
            AI 추천
          </button>

          <button
            type="button"
            class="map-research-button"
            :disabled="isSearchingMap || !mapSearchKeyword.trim()"
            @click="searchCurrentMapView"
          >
            현재 지도에서 재검색
          </button>

          <button
            type="button"
            class="map-reset-button"
            :disabled="isSearchingMap"
            @click="resetMapSearch"
          >
            검색 초기화
          </button>
        </div>
      </div>

      <div
        class="map-content"
        :class="{
          'has-result-list': searchedPlaces.length,
          'has-selected-place': selectedPlace,
        }"
      >
        <aside
          v-if="searchedPlaces.length"
          class="place-list-panel"
        >
          <div class="place-list-top">
            <div>
              <p class="place-list-label">검색 결과</p>
              <h2>{{ resultCountText }}</h2>
            </div>
          </div>

          <div class="place-list">
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
          </div>

          <div v-if="hasMoreResults" class="show-more-wrap">
            <button
              type="button"
              class="show-more-button"
              @click="showMoreResults"
            >
              더보기
            </button>
          </div>
        </aside>

        <div class="map-area">
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
            :class="{ 'is-compact-detail': !hasKakaoDetail(selectedPlace) }"
          >
            <div
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
                  class="close-card-button"
                  @click="closePlaceCard"
                >
                  ×
                </button>
              </div>

              <div
                v-if="selectedPlace.tags && selectedPlace.tags.length"
                class="tag-list"
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

              <section
                v-if="hasKakaoDetail(selectedPlace)"
                class="kakao-frame-section"
              >
                <div class="iframe-fallback" v-if="detailFrameError">
                  <p>카카오맵 상세페이지를 현재 화면에 표시하지 못했습니다.</p>

                  <a
                    :href="getKakaoDetailUrl(selectedPlace)"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    새창에서 열기
                  </a>
                </div>

                <div v-else class="kakao-frame-scroll">
                  <iframe
                    :src="getKakaoDetailUrl(selectedPlace)"
                    class="inline-kakao-frame"
                    title="카카오맵 장소 상세페이지"
                    scrolling="no"
                    referrerpolicy="no-referrer-when-downgrade"
                    @error="handleDetailFrameError"
                  ></iframe>
                </div>
              </section>

              <section
                v-else-if="isDbPlace(selectedPlace)"
                class="db-summary-card"
              >
                <div>
                  <strong>DB에 저장된 장소입니다.</strong>
                  <p>좌표 기준으로 지도에서 위치를 확인할 수 있습니다.</p>
                </div>

                <a
                  v-if="getPlaceNavigationUrl(selectedPlace)"
                  :href="getPlaceNavigationUrl(selectedPlace)"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  카카오맵에서 위치 보기
                </a>
              </section>

              <div class="info-list compact-info-list">
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

              <a
                v-if="!isDbPlace(selectedPlace) && getPlaceNavigationUrl(selectedPlace)"
                :href="getPlaceNavigationUrl(selectedPlace)"
                target="_blank"
                rel="noopener noreferrer"
                class="fallback-link"
              >
                새창에서 열기
              </a>
            </div>
          </aside>
        </div>
      </div>
    </section>

    <section v-else class="recommendation-lab-section">
      <RecommendationTestPanel />
    </section>
  </main>
</template>

<style scoped>
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

.recommendation-lab-section {
  min-height: calc(100vh - 90px);
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
  padding: 6px;
  display: flex;
  gap: 8px;
  background: #ffffff;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.map-search-box input {
  flex: 1;
  min-width: 0;
  padding: 12px 14px;
  border: 0;
  outline: none;
  font-size: 15px;
}

.map-search-actions {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.map-search-box button {
  padding: 0 16px;
  border: 0;
  border-radius: 13px;
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

.map-research-button {
  background: #111827 !important;
}

.map-ai-button {
  background: #7c3aed !important;
}

.map-reset-button {
  background: #f2f4f7 !important;
  color: #344054 !important;
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

.map-content.has-result-list.has-selected-place {
  grid-template-columns: clamp(300px, 22vw, 380px) minmax(0, 1fr);
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

.place-list-top {
  padding-bottom: 10px;
  border-bottom: 1px solid #eef0f4;
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

.place-list {
  min-height: 0;
  flex: 1;
  margin-top: 10px;
  overflow-y: auto;
  padding-right: 4px;
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

.place-list-meta small + small::before {
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
  z-index: 5;
  width: min(clamp(360px, 28vw, 520px), calc(100% - 28px));
  min-height: 0;
  overflow-y: auto;
}

.place-detail-panel.is-compact-detail {
  bottom: auto;
  max-height: calc(100% - 28px);
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

.fallback-link {
  margin-top: 12px;
  width: 100%;
  padding: 12px 16px;
  display: block;
  border-radius: 14px;
  background: #fee500;
  color: #111827;
  font-size: 14px;
  font-weight: 900;
  text-align: center;
  text-decoration: none;
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
  .map-content.has-selected-place:not(.has-result-list) {
    grid-template-columns: 1fr;
  }

  .place-list-panel {
    height: auto;
    min-height: auto;
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
