<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { createPlaceReport } from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const reportType = ref('tag_suggestion')
const placeId = ref('')
const suggestedName = ref('')
const suggestedCategory = ref('')
const suggestedAddress = ref('')
const suggestedLat = ref('')
const suggestedLng = ref('')
const selectedTags = ref([])
const extraTagsText = ref('')
const description = ref('')
const images = ref([])
const message = ref('')
const isSubmitting = ref(false)
const mapContainer = ref(null)
const mapStatusMessage = ref('')
const selectedLocationSummary = ref('')
const placeSearchKeyword = ref('')
const placeSearchResults = ref([])
const placeSearchMessage = ref('')
const isSearchingPlace = ref(false)

let reportMap = null
let reportMarker = null
let reportGeocoder = null
let reportPlaces = null

const reportTypeOptions = [
  { value: 'new_place', label: '새로운 장소 제보' },
  { value: 'tag_suggestion', label: '태그 추가 제보' },
  { value: 'wrong_info', label: '잘못된 정보 제보' },
  { value: 'edit_place', label: '장소 정보 수정 제보' },
]

const tagOptions = [
  '조용함',
  '노트북 작업 가능',
  '콘센트 있음',
  '와이파이 있음',
  '혼자 이용 좋음',
  '잠깐 쉬기 좋음',
  '산책하기 좋음',
  '야경 보기 좋음',
  '주차 가능',
  '실내 이용 가능',
]

const allowedExtensions = ['jpg', 'jpeg', 'png', 'webp']
const maxImageSize = 5 * 1024 * 1024

const isNewPlaceReport = computed(() => reportType.value === 'new_place')
const isTagSuggestionReport = computed(() => reportType.value === 'tag_suggestion')
const hasTargetPlace = computed(() =>
  Boolean(
    placeId.value ||
      suggestedName.value ||
      suggestedAddress.value ||
      (suggestedLat.value && suggestedLng.value),
  ),
)
const placePickerTitle = computed(() =>
  isNewPlaceReport.value ? '새 장소 위치' : '제보 대상 장소 선택',
)
const placePickerDescription = computed(() =>
  isNewPlaceReport.value
    ? '장소를 검색하거나 지도를 클릭해서 새 장소 위치를 선택해 주세요'
    : '장소를 검색하거나 지도를 클릭해서 제보 대상 위치를 보완할 수 있습니다',
)
const targetPlaceTitle = computed(() => {
  if (suggestedName.value) return suggestedName.value
  if (placeId.value) return `장소 ID ${placeId.value}`
  return '제보 대상 장소'
})
const selectedTagsPreview = computed(() => normalizeTagList(selectedTags.value, extraTagsText.value))

const getQueryValue = (...keys) => {
  for (const key of keys) {
    const value = route.query[key]
    if (Array.isArray(value)) {
      const firstValue = value.find(Boolean)
      if (firstValue) return String(firstValue)
    } else if (value) {
      return String(value)
    }
  }
  return ''
}

const normalizeCoordinate = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue.toFixed(6) : ''
}

const normalizeTagList = (selected = [], extraText = '') => {
  const extraTags = String(extraText || '')
    .split(/[,\n]/)
    .map((tag) => tag.trim())
    .filter(Boolean)

  return [...new Set([...selected, ...extraTags].map((tag) => tag.trim()).filter(Boolean))]
}

const toggleTag = (tag) => {
  if (selectedTags.value.includes(tag)) {
    selectedTags.value = selectedTags.value.filter((item) => item !== tag)
    return
  }

  selectedTags.value = [...selectedTags.value, tag]
}

const handleImageChange = (event) => {
  const selectedFiles = Array.from(event.target.files || [])
  message.value = ''

  for (const file of selectedFiles) {
    const extension = file.name.split('.').pop()?.toLowerCase()

    if (!allowedExtensions.includes(extension)) {
      message.value = 'jpg, jpeg, png, webp 이미지만 첨부할 수 있습니다.'
      continue
    }
    if (file.size > maxImageSize) {
      message.value = '이미지는 1개당 최대 5MB까지 첨부할 수 있습니다.'
      continue
    }
    if (images.value.length >= 3) {
      message.value = '이미지는 최대 3장까지 첨부할 수 있습니다.'
      break
    }

    images.value.push(file)
  }

  event.target.value = ''
}

const removeImage = (index) => {
  images.value.splice(index, 1)
}

const loadKakaoMapScript = () => {
  return new Promise((resolve, reject) => {
    if (window.kakao && window.kakao.maps && window.kakao.maps.services) {
      window.kakao.maps.load(() => resolve())
      return
    }

    const kakaoKey = import.meta.env.VITE_KAKAO_JAVASCRIPT_KEY

    if (!kakaoKey) {
      reject(new Error('VITE_KAKAO_JAVASCRIPT_KEY가 설정되지 않았습니다.'))
      return
    }

    const existingScript = document.querySelector('script[data-kakao-map-sdk="true"]')

    if (existingScript) {
      existingScript.addEventListener('load', () => window.kakao.maps.load(() => resolve()), {
        once: true,
      })
      existingScript.addEventListener('error', () => reject(new Error('카카오맵 SDK를 불러오지 못했습니다.')), {
        once: true,
      })
      return
    }

    const script = document.createElement('script')
    script.dataset.kakaoMapSdk = 'true'
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${kakaoKey}&autoload=false&libraries=services`
    script.async = true
    script.onload = () => {
      window.kakao.maps.load(() => resolve())
    }
    script.onerror = () => reject(new Error('카카오맵 SDK를 불러오지 못했습니다.'))
    document.head.appendChild(script)
  })
}

const formatCoordinateSummary = () => {
  if (!suggestedLat.value || !suggestedLng.value) {
    return ''
  }

  return `선택 좌표: ${suggestedLat.value}, ${suggestedLng.value}`
}

const updateSelectedLocationSummary = () => {
  selectedLocationSummary.value = suggestedAddress.value || formatCoordinateSummary()
}

const getCategoryLabel = (categoryName = '') => {
  const parts = String(categoryName || '')
    .split('>')
    .map((part) => part.trim())
    .filter(Boolean)

  return parts.at(-1) || String(categoryName || '').trim()
}

const getSearchResultAddress = (place) => {
  return place.road_address_name || place.address_name || ''
}

const reverseGeocodeSelection = (lat, lng) => {
  if (!reportGeocoder || !window.kakao?.maps?.services) {
    updateSelectedLocationSummary()
    return
  }

  reportGeocoder.coord2Address(lng, lat, (result, status) => {
    if (status === window.kakao.maps.services.Status.OK && result?.[0]) {
      const address =
        result[0].road_address?.address_name ||
        result[0].address?.address_name ||
        ''
      suggestedAddress.value = address
    }

    updateSelectedLocationSummary()
  })
}

const setMapSelection = (latLng, { reverseGeocode = true } = {}) => {
  const lat = latLng.getLat()
  const lng = latLng.getLng()

  suggestedLat.value = normalizeCoordinate(lat)
  suggestedLng.value = normalizeCoordinate(lng)

  if (!reportMarker) {
    reportMarker = new window.kakao.maps.Marker({
      map: reportMap,
      position: latLng,
    })
  } else {
    reportMarker.setPosition(latLng)
  }

  reportMap.setCenter(latLng)
  if (reverseGeocode) {
    reverseGeocodeSelection(lat, lng)
  } else {
    updateSelectedLocationSummary()
  }
}

const applyPlaceSearchResult = (place) => {
  const lat = Number(place.y)
  const lng = Number(place.x)

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    placeSearchMessage.value = '선택한 장소의 좌표를 확인할 수 없습니다.'
    return
  }

  const latLng = new window.kakao.maps.LatLng(lat, lng)

  placeId.value = ''
  suggestedName.value = place.place_name || suggestedName.value
  suggestedCategory.value = getCategoryLabel(place.category_name) || suggestedCategory.value
  suggestedAddress.value = getSearchResultAddress(place)
  placeSearchKeyword.value = place.place_name || placeSearchKeyword.value
  placeSearchResults.value = []
  placeSearchMessage.value = ''

  setMapSelection(latLng, { reverseGeocode: !suggestedAddress.value })
}

const searchReportPlaces = async () => {
  const keyword = placeSearchKeyword.value.trim()

  if (!keyword) {
    placeSearchMessage.value = '검색할 장소명이나 주소를 입력해 주세요.'
    return
  }

  await initializeReportMap()

  if (!reportPlaces || !window.kakao?.maps?.services) {
    placeSearchMessage.value = '장소 검색을 사용할 수 없습니다.'
    return
  }

  isSearchingPlace.value = true
  placeSearchMessage.value = ''

  const options = reportMap ? { location: reportMap.getCenter() } : {}

  reportPlaces.keywordSearch(
    keyword,
    (data, status) => {
      isSearchingPlace.value = false

      if (status === window.kakao.maps.services.Status.OK) {
        placeSearchResults.value = data.slice(0, 5)
        placeSearchMessage.value = placeSearchResults.value.length
          ? ''
          : '검색 결과가 없습니다.'
        return
      }

      placeSearchResults.value = []
      placeSearchMessage.value =
        status === window.kakao.maps.services.Status.ZERO_RESULT
          ? '검색 결과가 없습니다.'
          : '장소 검색 중 오류가 발생했습니다.'
    },
    options,
  )
}

const initializeReportMap = async () => {
  if (!mapContainer.value) {
    return
  }

  try {
    await loadKakaoMapScript()

    if (reportMap) {
      setTimeout(() => reportMap?.relayout(), 80)
      return
    }

    const initialLat = Number(suggestedLat.value) || 35.1796
    const initialLng = Number(suggestedLng.value) || 129.0756
    const center = new window.kakao.maps.LatLng(initialLat, initialLng)

    reportMap = new window.kakao.maps.Map(mapContainer.value, {
      center,
      level: 4,
    })
    reportGeocoder = new window.kakao.maps.services.Geocoder()
    reportPlaces = new window.kakao.maps.services.Places()

    window.kakao.maps.event.addListener(reportMap, 'click', (mouseEvent) => {
      suggestedAddress.value = ''
      if (!placeId.value && !isNewPlaceReport.value) {
        suggestedName.value = ''
      }
      setMapSelection(mouseEvent.latLng)
    })

    if (suggestedLat.value && suggestedLng.value) {
      setMapSelection(center, { reverseGeocode: !suggestedAddress.value })
    }

    mapStatusMessage.value = ''
    setTimeout(() => reportMap?.relayout(), 80)
  } catch (error) {
    mapStatusMessage.value = error.message || '지도를 불러오지 못했습니다.'
  }
}

watch(reportType, async () => {
  await nextTick()
  initializeReportMap()
})

watch(suggestedAddress, () => {
  updateSelectedLocationSummary()
})

const buildFormData = () => {
  const formData = new FormData()
  formData.append('report_type', reportType.value)

  if (!isNewPlaceReport.value && placeId.value) {
    formData.append('place', placeId.value)
  }

  if (suggestedName.value) formData.append('suggested_name', suggestedName.value)
  if (suggestedCategory.value) formData.append('suggested_category', suggestedCategory.value)
  if (suggestedAddress.value) formData.append('suggested_address', suggestedAddress.value)
  if (suggestedLat.value) formData.append('suggested_lat', suggestedLat.value)
  if (suggestedLng.value) formData.append('suggested_lng', suggestedLng.value)
  if (description.value) formData.append('description', description.value)

  const tags = isTagSuggestionReport.value ? selectedTagsPreview.value : []
  formData.append('suggested_tags', JSON.stringify(tags))
  images.value.forEach((file) => formData.append('images', file))
  return formData
}

const validateReport = () => {
  if (isNewPlaceReport.value) {
    if (!suggestedName.value.trim()) return '새로운 장소명을 입력해 주세요.'
    if (!suggestedCategory.value.trim()) return '새로운 장소의 카테고리를 입력해 주세요.'
    if (!suggestedLat.value || !suggestedLng.value) {
      return '새로운 장소를 제보하려면 지도에서 위치를 선택해 주세요.'
    }
  } else if (!hasTargetPlace.value) {
    return '제보 대상 장소를 검색하거나 지도에서 위치를 선택해 주세요.'
  }

  if (!description.value.trim()) {
    return '제보 내용을 입력해 주세요.'
  }

  return ''
}

const submitReport = async () => {
  message.value = ''

  const validationMessage = validateReport()
  if (validationMessage) {
    message.value = validationMessage
    return
  }

  try {
    isSubmitting.value = true
    await createPlaceReport(buildFormData())
    message.value = '제보가 접수되었습니다. 관리자 검토 후 반영됩니다.'
    router.push('/mypage/reports')
  } catch (error) {
    const data = error.response?.data
    message.value =
      data?.detail ||
      data?.non_field_errors?.[0] ||
      Object.values(data || {})?.flat?.()?.[0] ||
      '제보 접수에 실패했습니다.'
  } finally {
    isSubmitting.value = false
  }
}

const hydrateFromRoute = () => {
  placeId.value = getQueryValue('placeId', 'place')
  suggestedName.value = getQueryValue('name', 'placeName', 'suggestedName')
  suggestedCategory.value = getQueryValue('category', 'suggestedCategory')
  suggestedAddress.value = getQueryValue('address', 'suggestedAddress')
  suggestedLat.value = normalizeCoordinate(getQueryValue('lat', 'suggestedLat'))
  suggestedLng.value = normalizeCoordinate(getQueryValue('lng', 'suggestedLng'))

  const incomingReportType = getQueryValue('reportType', 'type')
  const isAllowedType = reportTypeOptions.some((option) => option.value === incomingReportType)

  if (isAllowedType) {
    reportType.value = incomingReportType
  } else {
    reportType.value = hasTargetPlace.value ? 'tag_suggestion' : 'new_place'
  }

  placeSearchKeyword.value = suggestedName.value || suggestedAddress.value || ''
  updateSelectedLocationSummary()
}

onMounted(async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  hydrateFromRoute()

  await nextTick()
  initializeReportMap()
})

onBeforeUnmount(() => {
  reportMap = null
  reportMarker = null
  reportGeocoder = null
})
</script>

<template>
  <main class="report-page">
    <section class="report-container">
      <header class="page-title">
        <RouterLink to="/" class="back-link">홈으로 돌아가기</RouterLink>
        <p class="eyebrow">PLACE REPORT</p>
        <h1>장소 정보 제보</h1>
        <p>제보 내용은 바로 반영되지 않고 관리자 검토 후 처리됩니다.</p>
      </header>

      <form class="panel report-form" @submit.prevent="submitReport">
        <label class="form-field">
          <span>제보 유형</span>
          <select v-model="reportType">
            <option v-for="option in reportTypeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>

        <section v-if="!isNewPlaceReport" class="target-place-card">
          <div>
            <p class="section-label">제보 대상 장소</p>
            <h2>{{ targetPlaceTitle }}</h2>
            <p v-if="suggestedAddress">{{ suggestedAddress }}</p>
            <p v-else-if="placeId">선택한 DB 장소에 대한 제보입니다.</p>
            <p v-else>검색 결과 카드에서 장소 정보를 전달받지 못했습니다.</p>
          </div>
          <span v-if="placeId" class="target-id-chip">ID {{ placeId }}</span>
          <span v-else class="target-id-chip">외부 후보</span>
        </section>

        <section v-if="isNewPlaceReport" class="form-section">
          <div class="section-heading">
            <p class="section-label">새로운 장소</p>
            <h2>장소 기본 정보를 알려주세요</h2>
          </div>

          <div class="field-grid">
            <label class="form-field">
              <span>장소명</span>
              <input v-model="suggestedName" type="text" maxlength="255" placeholder="예: 사상 감전천 쉼터" />
            </label>
            <label class="form-field">
              <span>카테고리</span>
              <input v-model="suggestedCategory" type="text" maxlength="50" placeholder="예: 카페, 공원, 쉼터" />
            </label>
          </div>

        </section>

        <section class="map-picker">
          <div class="section-heading">
            <p class="section-label">{{ placePickerTitle }}</p>
            <h2>{{ placePickerDescription }}</h2>
          </div>

          <div class="place-search-box">
            <input
              v-model="placeSearchKeyword"
              type="text"
              placeholder="장소명 또는 주소 검색"
              @keydown.enter.prevent="searchReportPlaces"
            />
            <button type="button" :disabled="isSearchingPlace" @click="searchReportPlaces">
              {{ isSearchingPlace ? '검색 중' : '검색' }}
            </button>
          </div>

          <div v-if="placeSearchResults.length" class="place-search-results">
            <button
              v-for="place in placeSearchResults"
              :key="place.id || `${place.place_name}-${place.x}-${place.y}`"
              type="button"
              class="place-search-result"
              @click="applyPlaceSearchResult(place)"
            >
              <strong>{{ place.place_name }}</strong>
              <span>{{ getSearchResultAddress(place) || '주소 정보 없음' }}</span>
              <small v-if="place.category_name">{{ getCategoryLabel(place.category_name) }}</small>
            </button>
          </div>

          <p v-if="placeSearchMessage" class="map-status">{{ placeSearchMessage }}</p>

          <div ref="mapContainer" class="report-map" aria-label="제보 장소 위치 선택 지도"></div>
          <p v-if="mapStatusMessage" class="map-status">{{ mapStatusMessage }}</p>

          <label class="form-field">
            <span>선택 위치</span>
            <input
              v-model="suggestedAddress"
              type="text"
              maxlength="255"
              placeholder="지도 클릭 또는 장소 검색 후 주소가 채워집니다"
            />
          </label>

          <p class="selected-location">
            {{ selectedLocationSummary || '아직 선택된 위치가 없습니다.' }}
          </p>
        </section>

        <section v-if="isTagSuggestionReport" class="form-section">
          <div class="section-heading">
            <p class="section-label">추천 태그</p>
            <h2>장소에 어울리는 특징을 선택해 주세요</h2>
          </div>

          <div class="tag-chip-grid">
            <button
              v-for="tag in tagOptions"
              :key="tag"
              type="button"
              class="tag-chip-button"
              :class="{ selected: selectedTags.includes(tag) }"
              @click="toggleTag(tag)"
            >
              {{ tag }}
            </button>
          </div>

          <label class="form-field">
            <span>추가로 제안할 특징</span>
            <input v-model="extraTagsText" type="text" placeholder="쉼표로 구분해서 입력해 주세요" />
          </label>

          <p v-if="selectedTagsPreview.length" class="selected-tags-preview">
            선택 태그: {{ selectedTagsPreview.join(', ') }}
          </p>
        </section>

        <label class="form-field">
          <span>설명</span>
          <textarea
            v-model="description"
            rows="6"
            :placeholder="isNewPlaceReport ? '새 장소를 확인할 수 있는 설명을 적어 주세요.' : '검토에 필요한 근거를 적어 주세요.'"
          ></textarea>
        </label>

        <label class="form-field">
          <span>이미지 첨부</span>
          <input
            type="file"
            accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
            multiple
            @change="handleImageChange"
          />
        </label>

        <div v-if="images.length" class="image-list">
          <span v-for="(image, index) in images" :key="`${image.name}-${index}`" class="image-chip">
            {{ image.name }}
            <button type="button" @click="removeImage(index)">삭제</button>
          </span>
        </div>

        <p v-if="message" class="status-message">{{ message }}</p>

        <div class="form-actions">
          <RouterLink to="/mypage/reports" class="ghost-button">내 제보 보기</RouterLink>
          <button type="submit" :disabled="isSubmitting">
            {{ isSubmitting ? '접수 중' : '제보 접수' }}
          </button>
        </div>
      </form>
    </section>
  </main>
</template>

<style scoped>
.report-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.report-container {
  max-width: 880px;
  margin: 0 auto;
  display: grid;
  gap: 14px;
}

.page-title {
  display: grid;
  gap: 6px;
}

.back-link {
  width: fit-content;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  text-decoration: none;
}

.eyebrow,
.page-title p,
.target-place-card p,
.section-heading p,
.selected-location,
.map-status,
.selected-tags-preview {
  margin: 0;
}

.eyebrow,
.section-label {
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
}

h1,
h2 {
  margin: 0;
  color: #111827;
}

h2 {
  font-size: 16px;
}

.page-title p,
.target-place-card p,
.selected-location,
.selected-tags-preview {
  color: #667085;
  font-weight: 700;
}

.panel {
  padding: 22px;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.report-form,
.form-section,
.section-heading,
.map-picker {
  display: grid;
  gap: 14px;
}

.target-place-card {
  padding: 16px;
  display: flex;
  gap: 14px;
  justify-content: space-between;
  align-items: flex-start;
  border: 1px solid #dbeafe;
  border-radius: 14px;
  background: #eff6ff;
}

.target-id-chip {
  flex-shrink: 0;
  padding: 6px 10px;
  border-radius: 999px;
  background: #ffffff;
  color: #2563eb;
  font-size: 12px;
  font-weight: 900;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.form-field {
  display: grid;
  gap: 6px;
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

input,
select,
textarea {
  width: 100%;
  padding: 11px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 10px;
  color: #111827;
  font: inherit;
  outline: none;
}

textarea {
  resize: vertical;
  line-height: 1.5;
}

.report-map {
  width: 100%;
  min-height: 320px;
  overflow: hidden;
  border: 1px solid #d0d5dd;
  border-radius: 16px;
  background: #eef2f7;
}

.place-search-box {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.place-search-box button {
  min-height: 44px;
  padding: 0 16px;
  border: 0;
  border-radius: 10px;
  background: #2563eb;
  color: #ffffff;
  font-weight: 900;
  cursor: pointer;
}

.place-search-box button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.place-search-results {
  max-height: 220px;
  overflow-y: auto;
  display: grid;
  gap: 8px;
}

.place-search-result {
  width: 100%;
  padding: 12px;
  display: grid;
  gap: 4px;
  border: 1px solid #e5e8f0;
  border-radius: 12px;
  background: #ffffff;
  color: #111827;
  text-align: left;
  cursor: pointer;
}

.place-search-result:hover {
  border-color: #2563eb;
  background: #eff6ff;
}

.place-search-result strong,
.place-search-result span,
.place-search-result small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.place-search-result strong {
  font-size: 14px;
}

.place-search-result span,
.place-search-result small {
  color: #667085;
  font-size: 12px;
  font-weight: 800;
}

.map-status {
  padding: 10px 12px;
  border-radius: 12px;
  background: #fff7ed;
  color: #c2410c;
  font-weight: 800;
}

.selected-location {
  padding: 10px 12px;
  border-radius: 12px;
  background: #f9fafb;
  font-size: 13px;
}

.tag-chip-grid,
.image-list,
.form-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.tag-chip-button {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid #d0d5dd;
  border-radius: 999px;
  background: #ffffff;
  color: #344054;
  font-weight: 900;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-chip-button.selected {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}

.selected-tags-preview {
  font-size: 13px;
}

.image-chip {
  padding: 6px 8px;
  display: inline-flex;
  gap: 8px;
  align-items: center;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 13px;
  font-weight: 900;
}

.image-chip button,
.ghost-button,
.form-actions > button {
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  background: #ffffff;
  color: #344054;
  font-weight: 900;
  text-decoration: none;
  cursor: pointer;
}

.form-actions > button {
  border: 0;
  background: #2563eb;
  color: #ffffff;
}

.form-actions > button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.status-message {
  margin: 0;
  padding: 12px;
  border-radius: 12px;
  background: #f9fafb;
  color: #2563eb;
  font-weight: 800;
}

@media (max-width: 720px) {
  .report-page {
    padding: 28px 14px;
  }

  .field-grid {
    grid-template-columns: 1fr;
  }

  .target-place-card {
    display: grid;
  }

  .report-map {
    min-height: 280px;
  }

  .place-search-box {
    grid-template-columns: 1fr;
  }
}
</style>
