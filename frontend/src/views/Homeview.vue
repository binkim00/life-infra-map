<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import KakaoMap from '@/components/KakaoMap.vue'

const activeTab = ref('search')
const searchKeyword = ref('')

const DEFAULT_CENTER = {
  lat: 35.1796,
  lng: 129.0756,
}

// 지도 검색 반경: 5km
const SEARCH_RADIUS = 5000

// 카카오 장소 검색은 한 번에 최대 15개까지 가져오는 구조라서
// 15개씩 페이지를 추가 조회한 뒤 최대 50개까지만 사용합니다.
const SEARCH_SIZE_PER_PAGE = 15
const MAX_SEARCH_RESULT_COUNT = 50

const mapCenter = ref(DEFAULT_CENTER)
const currentLocationPlace = ref([])
const searchedPlaces = ref([])
const selectedPlace = ref(null)

const isLocating = ref(false)
const isSearchingMap = ref(false)

const locationMessage = ref('지도 버튼을 누르면 현재 위치 기준으로 지도를 표시합니다.')
const mapSearchKeyword = ref('')

const showDetailPanel = ref(false)
const detailFrameError = ref(false)

const mapPlaces = computed(() => {
  return [
    ...currentLocationPlace.value,
    ...searchedPlaces.value,
  ]
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

const handleSearch = () => {
  if (!searchKeyword.value.trim()) {
    alert('검색어를 입력해주세요.')
    return
  }

  console.log('검색어:', searchKeyword.value)
  alert(`검색어: ${searchKeyword.value}`)
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

const makeTemporaryTags = (place, keyword) => {
  const tags = []

  const category = place.category_name || ''
  const searchText = `${keyword} ${category} ${place.place_name}`

  // 기본 태그: 검정
  tags.push(makeTag('카카오검색결과', 'category_rule'))

  if (searchText.includes('카페')) {
    tags.push(makeTag('카페', 'category_rule'))
    tags.push(makeTag('실내후보', 'category_rule'))

    // 블로그 검색 태그: 초록
    // 현재는 화면 확인용 임시 태그입니다.
    // 추후 백엔드에서 blog_search source를 내려주면 이 부분을 교체하면 됩니다.
    tags.push(makeTag('조용함후보', 'blog_search'))
    tags.push(makeTag('노트북작업후보', 'blog_search'))

    // 사용자 검증 태그: 빨강
    // 현재는 화면 확인용 임시 태그입니다.
    tags.push(makeTag('콘센트있음', 'user_verified'))
  }

  if (
    searchText.includes('식당') ||
    searchText.includes('음식') ||
    searchText.includes('한식') ||
    searchText.includes('일식') ||
    searchText.includes('중식') ||
    searchText.includes('양식')
  ) {
    tags.push(makeTag('식당', 'category_rule'))
    tags.push(makeTag('맛집후보', 'blog_search'))
    tags.push(makeTag('재방문후보', 'user_verified'))
  }

  if (searchText.includes('편의점')) {
    tags.push(makeTag('편의점', 'category_rule'))
  }

  if (searchText.includes('주차')) {
    tags.push(makeTag('주차가능확인필요', 'category_rule'))
  }

  if (place.distance) {
    tags.push(makeTag('검색기준위치기준', 'category_rule'))
  }

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

  return 'tag-default'
}

const getTagSourceText = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source

  if (source === 'blog_search') {
    return '블로그'
  }

  if (source === 'user_verified') {
    return '사용자검증'
  }

  return '기본'
}

const getTagSortOrder = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source

  if (source === 'category_rule') {
    return 1
  }

  if (source === 'blog_search') {
    return 2
  }

  if (source === 'user_verified') {
    return 3
  }

  return 99
}

const getSortedTags = (tags = []) => {
  return [...tags].sort((a, b) => {
    return getTagSortOrder(a) - getTagSortOrder(b)
  })
}

const getMarkerLabel = (index) => {
  return String(index + 1)
}

const convertKakaoPlaces = (places, targetKeyword) => {
  return places.map((place, index) => ({
    id: place.id,
    name: place.place_name,
    category: place.category_name,
    address: place.road_address_name || place.address_name,
    lat: Number(place.y),
    lng: Number(place.x),
    distance: place.distance ? Number(place.distance) : null,
    phone: place.phone,
    placeUrl: place.place_url,
    markerColor: 'red',
    markerLabel: getMarkerLabel(index),
    tags: makeTemporaryTags(place, targetKeyword),
    tagSource: '카카오 API 검색 결과 기반 임시 태그',
  }))
}

const searchAroundCenter = async ({
  placesService,
  targetKeyword,
  center,
  baseLabel,
}) => {
  const centerLatLng = new window.kakao.maps.LatLng(center.lat, center.lng)

  const places = await runKakaoKeywordSearchLimited(
    placesService,
    targetKeyword,
    {
      location: centerLatLng,
      radius: SEARCH_RADIUS,
      sort: window.kakao.maps.services.SortBy.DISTANCE,
    },
  )

  searchedPlaces.value = convertKakaoPlaces(places, targetKeyword)

  if (!places.length) {
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = `${baseLabel} ${SEARCH_RADIUS / 1000}km 이내 "${targetKeyword}" 검색 결과가 없습니다.`
    return
  }

  locationMessage.value = `${baseLabel} ${SEARCH_RADIUS / 1000}km 이내 "${targetKeyword}" 검색 결과 ${places.length}개를 표시했습니다.`
}

const searchKakaoPlaces = async () => {
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
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false

  const placesService = new window.kakao.maps.services.Places()
  const parsedKeyword = parseMapSearchInput(keyword)

  try {
    if (!parsedKeyword.hasBaseLocation) {
      await searchAroundCenter({
        placesService,
        targetKeyword: parsedKeyword.targetKeyword,
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
      searchedPlaces.value = []
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
        tags: [makeTag('검색기준위치', 'category_rule')],
        tagSource: '카카오 API 장소 검색 결과',
      },
    ]

    await searchAroundCenter({
      placesService,
      targetKeyword: parsedKeyword.targetKeyword,
      center: baseCenter,
      baseLabel: `${basePlace.place_name} 기준`,
    })
  } catch (error) {
    console.error(error)
    searchedPlaces.value = []
    selectedPlace.value = null
    showDetailPanel.value = false
    locationMessage.value = '카카오 장소 검색 중 오류가 발생했습니다.'
  } finally {
    isSearchingMap.value = false
  }
}

const selectPlace = (place) => {
  selectedPlace.value = place
  showDetailPanel.value = false
  detailFrameError.value = false
}

const selectPlaceFromList = (place) => {
  selectedPlace.value = place
  showDetailPanel.value = false
  detailFrameError.value = false
}

const closePlaceCard = () => {
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false
}

const openDetailPanel = () => {
  if (!selectedPlace.value?.placeUrl) {
    alert('카카오맵 상세 URL이 없는 장소입니다.')
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

    <section v-else class="map-section-wrap">
      <div class="map-header">
        <div>
          <h1>지도에서 장소 검색하기</h1>
          <p>
            {{ isLocating ? '현재 위치를 불러오는 중입니다...' : locationMessage }}
          </p>
        </div>
      </div>

      <div class="map-search-box">
        <input
          v-model="mapSearchKeyword"
          type="text"
          placeholder="예: 카페, 식당, 수영역 주변 카페, 서면역 근처 맛집"
          @keyup.enter="searchKakaoPlaces"
        />

        <button type="button" @click="searchKakaoPlaces">
          {{ isSearchingMap ? '검색 중...' : '지도 검색' }}
        </button>
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
              <h2>장소 {{ searchedPlaces.length }}</h2>
            </div>
          </div>

          <div class="place-list">
            <button
              v-for="place in searchedPlaces"
              :key="place.id"
              :ref="(el) => setPlaceListItemRef(el, place.id)"
              type="button"
              class="place-list-item"
              :class="{ active: selectedPlace && selectedPlace.id === place.id }"
              @click="selectPlaceFromList(place)"
            >
              <span class="place-list-marker">
                {{ place.markerLabel }}
              </span>

              <span class="place-list-name">
                {{ place.name }}
              </span>
            </button>
          </div>
        </aside>

        <div class="map-area">
          <KakaoMap
            :center="mapCenter"
            :places="mapPlaces"
            :selected-place-id="selectedPlace?.id || null"
            @select-place="selectPlace"
          />
        </div>

        <aside
          v-if="selectedPlace"
          class="place-detail-panel"
        >
          <div class="place-card">
            <div class="card-top">
              <p class="card-label">선택한 장소</p>

              <button
                type="button"
                class="close-card-button"
                @click="closePlaceCard"
              >
                ×
              </button>
            </div>

            <h2>{{ selectedPlace.name }}</h2>

            <p v-if="selectedPlace.category" class="category">
              {{ selectedPlace.category }}
            </p>

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

            <div class="info-list">
              <div v-if="selectedPlace.address" class="info-row">
                <span>주소</span>
                <p>{{ selectedPlace.address }}</p>
              </div>

              <div v-if="selectedPlace.distance" class="info-row">
                <span>거리</span>
                <p>검색 기준 위치에서 {{ selectedPlace.distance }}m</p>
              </div>

              <div v-if="selectedPlace.phone" class="info-row">
                <span>전화</span>
                <p>{{ selectedPlace.phone }}</p>
              </div>

            </div>

            <button
              v-if="selectedPlace.placeUrl"
              type="button"
              class="detail-button"
              @click="openDetailPanel"
            >
              상세 정보 보기
            </button>

            <a
              v-if="selectedPlace.placeUrl"
              :href="selectedPlace.placeUrl"
              target="_blank"
              rel="noopener noreferrer"
              class="fallback-link"
            >
              새창에서 열기
            </a>
          </div>
        </aside>
      </div>

      <div
        v-if="showDetailPanel && selectedPlace"
        class="detail-drawer-backdrop"
        @click.self="closeDetailPanel"
      >
        <aside class="kakao-detail-drawer">
          <div class="drawer-header">
            <div>
              <p class="drawer-label">카카오맵 상세 정보</p>
              <h2>{{ selectedPlace.name }}</h2>
            </div>

            <button
              type="button"
              class="drawer-close-button"
              @click="closeDetailPanel"
            >
              ×
            </button>
          </div>

          <div class="drawer-notice">
            <p>
              카카오 장소 상세페이지를 iframe으로 표시합니다.
              브라우저 또는 카카오 측 제한으로 표시되지 않을 경우 아래 링크로 열어주세요.
            </p>

            <a
              :href="selectedPlace.placeUrl"
              target="_blank"
              rel="noopener noreferrer"
            >
              새창에서 열기
            </a>
          </div>

          <div
            v-if="detailFrameError"
            class="iframe-fallback"
          >
            <p>상세페이지를 현재 화면에 표시하지 못했습니다.</p>
            <a
              :href="selectedPlace.placeUrl"
              target="_blank"
              rel="noopener noreferrer"
            >
              카카오맵 상세페이지 새창에서 열기
            </a>
          </div>

          <iframe
            v-else
            :src="selectedPlace.placeUrl"
            class="kakao-detail-frame"
            title="카카오맵 장소 상세페이지"
            referrerpolicy="no-referrer-when-downgrade"
            @error="handleDetailFrameError"
          ></iframe>
        </aside>
      </div>
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
  max-width: 1280px;
  margin: 48px auto 0;
}

.map-header {
  margin-bottom: 20px;
}

.map-header h1 {
  font-size: 30px;
}

.map-header p {
  margin: 10px 0 0;
  color: #667085;
}

.map-search-box {
  margin-bottom: 16px;
  padding: 8px;
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
  padding: 15px 16px;
  border: 0;
  outline: none;
  font-size: 15px;
}

.map-search-box button {
  padding: 0 22px;
  border: 0;
  border-radius: 13px;
  background: #ef4444;
  color: #ffffff;
  font-size: 15px;
  font-weight: 800;
  cursor: pointer;
}

.map-content {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
  align-items: stretch;
}

.map-content.has-result-list {
  grid-template-columns: 280px minmax(0, 1fr);
}

.map-content.has-result-list.has-selected-place {
  grid-template-columns: 280px minmax(0, 1fr) 360px;
}

.map-content.has-selected-place:not(.has-result-list) {
  grid-template-columns: minmax(0, 1fr) 360px;
}

.place-list-panel {
  height: calc(100vh - 290px);
  min-height: 520px;
  padding: 16px;
  overflow: hidden;
  background: #ffffff;
  border: 1px solid #e5e8f0;
  border-radius: 22px;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.12);
}

.place-list-top {
  padding-bottom: 12px;
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
  font-size: 18px;
  letter-spacing: -0.03em;
}

.place-list {
  height: calc(100% - 58px);
  margin-top: 10px;
  overflow-y: auto;
  padding-right: 4px;
}

.place-list-item {
  width: 100%;
  padding: 12px 8px;
  display: flex;
  gap: 10px;
  align-items: center;
  border: 0;
  border-bottom: 1px solid #eef0f4;
  background: transparent;
  color: #111827;
  text-align: left;
  cursor: pointer;
}

.place-list-item:hover,
.place-list-item.active {
  background: #eff6ff;
  border-radius: 12px;
}

.place-list-marker {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border: 2px solid #ef4444;
  border-radius: 999px;
  background: #ffffff;
  color: #ef4444;
  font-size: 13px;
  font-weight: 900;
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

.map-area {
  min-width: 0;
}

:deep(.map) {
  height: calc(100vh - 290px);
  min-height: 520px;
  border: 0;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.12);
}

.place-detail-panel {
  min-height: 520px;
}

.place-card {
  height: 100%;
  padding: 24px;
  background: #ffffff;
  border: 1px solid #e5e8f0;
  border-radius: 22px;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.12);
}

.card-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}

.card-label {
  margin: 0;
  color: #2563eb;
  font-size: 13px;
  font-weight: 800;
}

.close-card-button,
.drawer-close-button {
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

.close-card-button:hover,
.drawer-close-button:hover {
  background: #e5e7eb;
  color: #111827;
}

.place-card h2 {
  margin: 0;
  color: #111827;
  font-size: 24px;
  line-height: 1.35;
  letter-spacing: -0.03em;
}

.category {
  margin: 12px 0 0;
  color: #667085;
  font-size: 14px;
  line-height: 1.5;
}

.tag-list {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-chip {
  padding: 7px 10px;
  display: inline-flex;
  gap: 6px;
  align-items: center;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 800;
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

.info-list {
  margin-top: 22px;
  border-top: 1px solid #eef0f4;
}

.info-row {
  padding: 14px 0;
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

.detail-button {
  margin-top: 22px;
  width: 100%;
  padding: 14px 16px;
  border: 0;
  border-radius: 14px;
  background: #2563eb;
  color: #ffffff;
  font-size: 15px;
  font-weight: 900;
  cursor: pointer;
}

.fallback-link {
  margin-top: 10px;
  width: 100%;
  padding: 13px 16px;
  display: block;
  border-radius: 14px;
  background: #fee500;
  color: #111827;
  font-size: 14px;
  font-weight: 900;
  text-align: center;
  text-decoration: none;
}

.detail-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(15, 23, 42, 0.3);
  display: flex;
  justify-content: flex-end;
}

.kakao-detail-drawer {
  width: min(560px, 100%);
  height: 100vh;
  padding: 20px;
  background: #ffffff;
  box-shadow: -16px 0 48px rgba(15, 23, 42, 0.22);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.drawer-label {
  margin: 0 0 6px;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
}

.drawer-header h2 {
  margin: 0;
  color: #111827;
  font-size: 22px;
  line-height: 1.35;
}

.drawer-notice {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #f8fafc;
  border: 1px solid #e5e8f0;
  border-radius: 14px;
}

.drawer-notice p,
.iframe-fallback p {
  margin: 0;
  color: #667085;
  font-size: 13px;
  line-height: 1.5;
}

.drawer-notice a,
.iframe-fallback a {
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  text-decoration: none;
}

.kakao-detail-frame {
  flex: 1;
  width: 100%;
  min-height: 0;
  border: 1px solid #e5e8f0;
  border-radius: 16px;
  background: #ffffff;
}

.iframe-fallback {
  padding: 18px;
  border: 1px solid #e5e8f0;
  border-radius: 16px;
  background: #ffffff;
}

@media (max-width: 1100px) {
  .map-content.has-result-list,
  .map-content.has-result-list.has-selected-place,
  .map-content.has-selected-place:not(.has-result-list) {
    grid-template-columns: 1fr;
  }

  .place-list-panel,
  .place-detail-panel {
    height: auto;
    min-height: auto;
  }

  .place-list {
    max-height: 240px;
  }

  .place-card {
    height: auto;
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

  .search-box input,
  .map-search-box input {
    padding: 16px;
  }

  .search-box button,
  .map-search-box button {
    padding: 15px;
  }

  .tab-button {
    min-width: 84px;
  }

  .kakao-detail-drawer {
    width: 100%;
  }
}
</style>
