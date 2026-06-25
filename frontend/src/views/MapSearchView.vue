<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import KakaoMap from '@/components/KakaoMap.vue'
import { searchMapPlaces } from '@/api/recommendation'

const router = useRouter()

const DEFAULT_CENTER = {
  lat: 35.1796,
  lng: 129.0756,
}

const SOURCE_OPTIONS = [
  { value: 'all', label: '전체' },
  { value: 'db', label: '저장 장소' },
  { value: 'kakao', label: '카카오' },
]

const SOURCE_META = {
  db: {
    label: '저장 장소',
    color: '#2563eb',
    className: 'source-db',
  },
  kakao: {
    label: '카카오 장소',
    color: '#ef4444',
    className: 'source-kakao',
  },
}

const query = ref('')
const source = ref('all')
const radius = ref(3000)
const places = ref([])
const selectedPlace = ref(null)
const mapCenter = ref({ ...DEFAULT_CENTER })
const fitBoundsKey = ref(0)
const isLoading = ref(false)
const message = ref('장소명, 주소, 태그를 그대로 검색할 수 있어요.')
const counts = ref({ db: 0, kakao: 0, db_total: 0 })

const normalizedQuery = computed(() => query.value.trim())
const hasResults = computed(() => places.value.length > 0)
const selectedSourceMeta = computed(() => getSourceMeta(selectedPlace.value))

const toNumber = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

const toArray = (value) => Array.isArray(value) ? value : []

const getSourceMeta = (place = {}) => {
  return SOURCE_META[place?.resultSource] || SOURCE_META.db
}

const formatDistance = (distance) => {
  const value = Number(distance)
  if (!Number.isFinite(value)) return ''
  if (value >= 1000) return `${(value / 1000).toFixed(1)}km`
  return `${Math.round(value)}m`
}

const getAddress = (place = {}) => {
  return place.address || place.detailLocation || ''
}

const getDetailUrl = (place = {}) => {
  return place.detailUrl || place.placeUrl || place.kakaoPlaceUrl || ''
}

const getNavigationUrl = (place = {}) => {
  if (place.navigationUrl) return place.navigationUrl
  if (!place.lat || !place.lng) return ''
  return `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`
}

const getTagName = (tag) => {
  if (typeof tag === 'string') return tag
  return tag?.name || tag?.label || ''
}

const normalizeTags = (place = {}) => {
  const tags = []
  const category = place.categoryLabel || place.category
  if (category) {
    tags.push({ name: category, source: 'category' })
  }

  toArray(place.tags).forEach((tag) => {
    const name = getTagName(tag)
    if (name && !tags.some((item) => item.name === name)) {
      tags.push({
        name,
        source: tag?.source || 'tag',
      })
    }
  })

  return tags
}

const normalizePlace = (place, index) => {
  const resultSource = place.result_source || place.resultSource || 'db'
  const sourceMeta = SOURCE_META[resultSource] || SOURCE_META.db
  const lat = toNumber(place.lat)
  const lng = toNumber(place.lng)
  const sourceId = place.external_id || place.id || index
  const id = `${resultSource}-${sourceId}`

  return {
    id,
    savedPlaceId: resultSource === 'db' ? place.id : null,
    externalId: place.external_id || '',
    resultSource,
    sourceLabel: place.source_label || sourceMeta.label,
    source: place.source || resultSource,
    sourceName: place.source_name || '',
    name: place.name || '장소명 없음',
    category: place.category_label || place.category || '',
    categoryLabel: place.category_label || '',
    address: place.address || '',
    detailLocation: place.detail_location || '',
    phone: place.phone || '',
    lat,
    lng,
    distance: place.distance ?? null,
    tags: normalizeTags(place),
    markerLabel: String(index + 1),
    markerColor: sourceMeta.color,
    searchSource: resultSource === 'kakao' ? 'kakao' : 'local_db',
    placeUrl: place.place_url || place.kakao_place_url || '',
    kakaoPlaceUrl: place.kakao_place_url || place.place_url || '',
    detailUrl: place.place_url || place.kakao_place_url || '',
    navigationUrl: lat && lng
      ? `https://map.kakao.com/link/to/${encodeURIComponent(place.name || '장소')},${lat},${lng}`
      : '',
    dataQualityStatus: place.data_quality_status || '',
    dataQualityScore: place.data_quality_score ?? null,
  }
}

const runSearch = async () => {
  isLoading.value = true
  selectedPlace.value = null
  message.value = '장소 데이터를 찾는 중입니다.'

  try {
    const data = await searchMapPlaces({
      q: normalizedQuery.value,
      source: source.value,
      lat: mapCenter.value.lat,
      lng: mapCenter.value.lng,
      radius: radius.value,
      limit: 40,
    })

    counts.value = data.candidate_counts || { db: 0, kakao: 0, db_total: 0 }
    places.value = toArray(data.results)
      .filter((place) => toNumber(place.lat) !== null && toNumber(place.lng) !== null)
      .map(normalizePlace)
    fitBoundsKey.value += 1

    if (places.value.length) {
      message.value = `${places.value.length}곳을 찾았어요.`
    } else if (!normalizedQuery.value) {
      message.value = '검색어를 입력하거나 지도 중심 기준으로 저장 장소를 둘러보세요.'
    } else {
      message.value = '조건에 맞는 장소를 찾지 못했어요.'
    }

    if (data.kakao_error) {
      message.value = `${message.value} 카카오 결과는 잠시 불러오지 못했습니다.`
    }
  } catch (error) {
    console.error(error)
    places.value = []
    counts.value = { db: 0, kakao: 0, db_total: 0 }
    message.value = '지도 검색을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const handleCenterChange = ({ center }) => {
  if (!center) return
  mapCenter.value = {
    lat: center.lat,
    lng: center.lng,
  }
}

const selectPlace = (place) => {
  selectedPlace.value = place
}

const clearSelection = () => {
  selectedPlace.value = null
}

const goToPlaceReport = (place) => {
  const queryParams = {
    reportType: place.savedPlaceId ? 'tag_suggestion' : 'new_place',
    name: place.name,
    category: place.category,
    address: getAddress(place),
  }

  if (place.savedPlaceId) {
    queryParams.placeId = place.savedPlaceId
  }
  if (place.lat) {
    queryParams.lat = Number(place.lat).toFixed(6)
  }
  if (place.lng) {
    queryParams.lng = Number(place.lng).toFixed(6)
  }

  router.push({
    name: 'place-report',
    query: queryParams,
  })
}
</script>

<template>
  <main class="map-search-page">
    <section class="map-search-shell" :class="{ 'has-detail': selectedPlace }">
      <aside class="map-search-panel">
        <header class="map-search-header">
          <p>일반 지도 검색</p>
          <h1>장소 데이터 검색</h1>
          <span>AI 해석 없이 저장 장소와 카카오 장소를 그대로 찾습니다.</span>
        </header>

        <form class="map-search-form" @submit.prevent="runSearch">
          <label>
            <span>검색어</span>
            <input
              v-model="query"
              type="search"
              placeholder="예: 카페, 화장실, 조용함, 부산시청"
            />
          </label>

          <div class="map-search-controls">
            <label>
              <span>출처</span>
              <select v-model="source">
                <option
                  v-for="option in SOURCE_OPTIONS"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </option>
              </select>
            </label>

            <label>
              <span>반경</span>
              <select v-model.number="radius">
                <option :value="1000">1km</option>
                <option :value="3000">3km</option>
                <option :value="5000">5km</option>
                <option :value="10000">10km</option>
              </select>
            </label>
          </div>

          <button type="submit" :disabled="isLoading">
            {{ isLoading ? '검색 중' : '검색' }}
          </button>
        </form>

        <div class="map-search-status">
          <strong>{{ message }}</strong>
          <span v-if="hasResults">
            저장 장소 {{ counts.db || 0 }}곳 · 카카오 {{ counts.kakao || 0 }}곳
          </span>
        </div>

        <div class="map-source-legend" aria-label="마커 색상 안내">
          <span><i class="legend-dot db"></i>저장 장소</span>
          <span><i class="legend-dot kakao"></i>카카오</span>
        </div>

        <section class="map-result-list" aria-label="장소 검색 결과">
          <article
            v-for="place in places"
            :key="place.id"
            class="map-result-item"
            :class="{ active: selectedPlace?.id === place.id }"
          >
            <button type="button" @click="selectPlace(place)">
              <span class="result-marker" :class="getSourceMeta(place).className">
                {{ place.markerLabel }}
              </span>
              <span class="result-main">
                <span class="result-title-row">
                  <strong>{{ place.name }}</strong>
                  <small :class="['source-chip', getSourceMeta(place).className]">
                    {{ place.sourceLabel }}
                  </small>
                </span>
                <span class="result-meta">
                  <small v-if="place.category">{{ place.category }}</small>
                  <small v-if="formatDistance(place.distance)">{{ formatDistance(place.distance) }}</small>
                </span>
                <span v-if="getAddress(place)" class="result-address">
                  {{ getAddress(place) }}
                </span>
              </span>
            </button>
          </article>
        </section>
      </aside>

      <section class="map-search-map-area">
        <KakaoMap
          :places="places"
          :center="mapCenter"
          :selected-place-id="selectedPlace?.id || null"
          :selected-place="selectedPlace"
          :fit-bounds-key="fitBoundsKey"
          @select-place="selectPlace"
          @center-change="handleCenterChange"
        />
      </section>

      <aside v-if="selectedPlace" class="map-detail-panel">
        <div class="map-detail-top">
          <div>
            <span :class="['source-chip', selectedSourceMeta.className]">
              {{ selectedPlace.sourceLabel }}
            </span>
            <h2>{{ selectedPlace.name }}</h2>
          </div>
          <button type="button" @click="clearSelection">닫기</button>
        </div>

        <div v-if="selectedPlace.tags.length" class="map-detail-tags">
          <span
            v-for="tag in selectedPlace.tags"
            :key="`${selectedPlace.id}-${tag.name}`"
          >
            {{ tag.name }}
          </span>
        </div>

        <section v-if="getDetailUrl(selectedPlace)" class="map-detail-frame">
          <iframe
            :src="getDetailUrl(selectedPlace)"
            title="카카오맵 장소 상세페이지"
            scrolling="no"
            referrerpolicy="no-referrer-when-downgrade"
          ></iframe>
        </section>

        <dl class="map-detail-info">
          <div v-if="selectedPlace.category">
            <dt>분류</dt>
            <dd>{{ selectedPlace.category }}</dd>
          </div>
          <div v-if="getAddress(selectedPlace)">
            <dt>주소</dt>
            <dd>{{ getAddress(selectedPlace) }}</dd>
          </div>
          <div v-if="formatDistance(selectedPlace.distance)">
            <dt>거리</dt>
            <dd>지도 중심에서 {{ formatDistance(selectedPlace.distance) }}</dd>
          </div>
          <div v-if="selectedPlace.phone">
            <dt>전화</dt>
            <dd>{{ selectedPlace.phone }}</dd>
          </div>
          <div v-if="selectedPlace.dataQualityStatus">
            <dt>상태</dt>
            <dd>{{ selectedPlace.dataQualityStatus }}</dd>
          </div>
        </dl>

        <div class="map-detail-actions">
          <button type="button" @click="goToPlaceReport(selectedPlace)">
            정보 제보
          </button>
          <a
            v-if="getDetailUrl(selectedPlace)"
            :href="getDetailUrl(selectedPlace)"
            target="_blank"
            rel="noopener noreferrer"
          >
            카카오맵 보기
          </a>
          <a
            v-if="getNavigationUrl(selectedPlace)"
            :href="getNavigationUrl(selectedPlace)"
            target="_blank"
            rel="noopener noreferrer"
            class="primary"
          >
            길찾기
          </a>
        </div>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.map-search-page {
  min-height: calc(100vh - 40px);
  padding: 28px;
  background: #eef6f8;
  color: #1f2937;
}

.map-search-shell {
  display: grid;
  grid-template-columns: minmax(300px, 380px) minmax(420px, 1fr);
  gap: 18px;
  height: calc(100vh - 96px);
  min-height: 680px;
}

.map-search-shell.has-detail {
  grid-template-columns: minmax(300px, 380px) minmax(420px, 1fr) minmax(300px, 360px);
}

.map-search-panel,
.map-detail-panel {
  overflow: hidden;
  border: 2px solid #222;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
}

.map-search-panel {
  display: flex;
  flex-direction: column;
}

.map-search-header {
  padding: 22px 22px 16px;
  border-bottom: 1px solid #e5e7eb;
}

.map-search-header p {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 800;
  color: #2563eb;
}

.map-search-header h1 {
  margin: 0;
  font-size: 26px;
}

.map-search-header span,
.map-search-status span {
  display: block;
  margin-top: 8px;
  color: #64748b;
  font-size: 14px;
}

.map-search-form {
  display: grid;
  gap: 12px;
  padding: 18px 22px;
  border-bottom: 1px solid #e5e7eb;
}

.map-search-form label {
  display: grid;
  gap: 7px;
  font-size: 13px;
  font-weight: 800;
}

.map-search-form input,
.map-search-form select {
  width: 100%;
  min-height: 44px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 0 12px;
  background: #fff;
  font: inherit;
}

.map-search-controls {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.map-search-form button,
.map-detail-actions button,
.map-detail-actions a,
.map-detail-top button {
  min-height: 42px;
  border: 1px solid #222;
  border-radius: 8px;
  padding: 0 14px;
  background: #222;
  color: #fff;
  font-weight: 900;
  cursor: pointer;
  text-decoration: none;
}

.map-search-form button:disabled {
  opacity: 0.6;
  cursor: wait;
}

.map-search-status,
.map-source-legend {
  padding: 14px 22px;
  border-bottom: 1px solid #e5e7eb;
}

.map-source-legend {
  display: flex;
  gap: 14px;
  font-size: 13px;
  font-weight: 800;
}

.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 6px;
  border-radius: 50%;
}

.legend-dot.db {
  background: #2563eb;
}

.legend-dot.kakao {
  background: #ef4444;
}

.map-result-list {
  overflow: auto;
  padding: 10px;
}

.map-result-item {
  border-bottom: 1px solid #edf2f7;
}

.map-result-item.active {
  background: #fff4d8;
}

.map-result-item button {
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 12px;
  width: 100%;
  border: 0;
  padding: 14px 10px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.result-marker {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  font-weight: 900;
}

.source-db {
  background: #2563eb;
}

.source-kakao {
  background: #ef4444;
}

.result-main,
.result-title-row,
.result-meta {
  display: grid;
  gap: 5px;
}

.result-title-row {
  grid-template-columns: 1fr auto;
  align-items: start;
}

.result-title-row strong {
  font-size: 15px;
}

.source-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  border-radius: 999px;
  padding: 0 9px;
  color: #fff;
  font-size: 12px;
  font-weight: 900;
  white-space: nowrap;
}

.result-meta {
  grid-auto-flow: column;
  justify-content: start;
  color: #64748b;
  font-size: 13px;
}

.result-address {
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
}

.map-search-map-area {
  overflow: hidden;
  border: 2px solid #222;
  border-radius: 8px;
  background: #dbeafe;
}

.map-search-map-area :deep(.map-section),
.map-search-map-area :deep(.map) {
  width: 100%;
  height: 100%;
}

.map-search-map-area :deep(.map) {
  border: 0;
  border-radius: 0;
}

.map-detail-panel {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 20px;
}

.map-detail-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.map-detail-top h2 {
  margin: 12px 0 0;
  font-size: 24px;
  line-height: 1.25;
}

.map-detail-top button {
  min-height: 36px;
  background: #fff;
  color: #222;
}

.map-detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 18px 0;
}

.map-detail-tags span {
  border-radius: 999px;
  padding: 7px 10px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 12px;
  font-weight: 800;
}

.map-detail-frame {
  overflow: hidden;
  height: 320px;
  margin-bottom: 18px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
}

.map-detail-frame iframe {
  width: 100%;
  height: 100%;
  border: 0;
}

.map-detail-info {
  display: grid;
  gap: 12px;
  margin: 0;
}

.map-detail-info div {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #edf2f7;
}

.map-detail-info dt {
  color: #64748b;
  font-weight: 900;
}

.map-detail-info dd {
  margin: 0;
  line-height: 1.5;
}

.map-detail-actions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 20px;
}

.map-detail-actions button,
.map-detail-actions a {
  display: grid;
  place-items: center;
  background: #fff;
  color: #222;
  text-align: center;
}

.map-detail-actions .primary {
  background: #ffe500;
  color: #222;
}

@media (max-width: 1180px) {
  .map-search-shell {
    grid-template-columns: minmax(280px, 360px) 1fr;
  }

  .map-detail-panel {
    grid-column: 1 / -1;
    min-height: 420px;
  }
}

@media (max-width: 860px) {
  .map-search-page {
    padding: 14px;
  }

  .map-search-shell {
    display: flex;
    flex-direction: column;
    height: auto;
    min-height: 0;
  }

  .map-search-map-area {
    height: 460px;
  }

  .map-detail-actions {
    grid-template-columns: 1fr;
  }
}
</style>
