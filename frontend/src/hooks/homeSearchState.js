import {
  DEFAULT_CENTER,
  DISPLAY_BATCH_SIZE,
} from '@/constants/homeSearchConstants'
import { RESULT_FILTER_OPTIONS } from '@/constants/homeViewUiConstants'
import { assignMarkerLabels } from '@/utils/placeResultConverters'
import { getTextValue, matchesResultFilter } from '@/utils/homePlaceHelpers'

/**
 * 홈 검색 화면의 상태입니다.
 *
 * Vue 에서는 ref 를 고치고 바로 다음 줄에서 computed 를 읽는 코드가 많습니다.
 * (예: setMainResults() 직후 displayResults.value.length 로 분기)
 * React 의 setState 는 비동기라 그대로 옮기면 이 흐름이 깨지므로,
 * 검색 파이프라인이 쓰는 상태는 일반 객체로 두고 동기적으로 고칩니다.
 * 화면 갱신은 commit() 이 버전을 올려서 처리합니다.
 */
export const createHomeSearchState = () => ({
  activeTab: 'search',
  searchKeyword: '',
  mapCenter: DEFAULT_CENTER,
  mapViewportBounds: null,
  mapFitBoundsKey: 0,
  currentLocationPlace: [],
  allSearchResults: [],
  mainResults: [],
  fallbackResults: [],
  webReferenceResults: [],
  preserveBackendResultOrder: false,
  visibleCount: DISPLAY_BATCH_SIZE,
  resultFilterMode: 'all',
  sortMode: 'distance',
  searchResultStatus: 'idle',
  searchLogSaveState: {
    status: 'idle',
    message: '',
    statusCode: null,
  },
  searchErrorMessage: '',
  resultSourceLabel: '검색 결과',
  resultMessageSuffix: '',
  selectedPlace: null,
  hiddenMapMarkerPlaceId: null,
  markerChoiceRequestKey: 0,
  resolvedKakaoDetailUrls: {},
  kakaoDetailLookupStatus: {},
  baseLocationCandidates: [],
  pendingBaseLocationSearch: null,
  isResultListCollapsed: false,
  isPlaceDetailCollapsed: false,
  isPlaceDetailDismissed: false,
  activeResultView: 'results',

  isLocating: false,
  isSearchingMap: false,

  locationMessage: '지도 버튼을 누르면 현재 위치 기준으로 지도를 표시합니다.',
  loadingMessage: '',
  mapSearchKeyword: '',
  aiSearchKeyword: '',
  aiSearchError: '',
  mapAiParse: null,
  aiWebSearchContext: null,
  aiWebSearchAvailability: null,
  aiWebSearchStatus: 'idle',
  aiWebSearchMessage: '',
  aiWebSearchCandidates: [],
  aiWebSearchClientCache: {},
  aiWebSearchLastResult: null,
  activeSearchPlan: null,
  conversationMessages: [],
  pendingClarification: null,
  clarificationThread: [],
  followUpInput: '',
  conversationModeStarted: false,
  activeMenuSearchProfile: null,

  showDetailPanel: false,
  detailFrameError: false,
})

const getDisplayResultKey = (place = {}) => {
  return [
    place.id,
    place.savedPlaceId,
    place.kakaoPlaceId,
    place.externalId,
    `${place.name || ''}:${place.address || ''}`,
  ].find((value) => value !== undefined && value !== null && String(value).trim()) || ''
}

export const mergeAndSortMainResults = (primaryResults = [], secondaryResults = []) => {
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

/** Vue 의 computed 와 같은 자리입니다. 읽을 때마다 현재 상태로 계산합니다. */
export const getDisplayResults = (state) => {
  if (state.preserveBackendResultOrder) {
    return Array.isArray(state.mainResults) ? state.mainResults : []
  }

  return mergeAndSortMainResults(state.mainResults, state.fallbackResults)
}

export const getFilteredSearchResults = (state) => {
  return getDisplayResults(state).filter((place) => {
    return matchesResultFilter(place, state.resultFilterMode)
  })
}

export const getSearchedPlaces = (state, sortSearchResults) => {
  const filtered = getFilteredSearchResults(state)
  const sorted = state.preserveBackendResultOrder ? filtered : sortSearchResults(filtered)

  return assignMarkerLabels(sorted.slice(0, state.visibleCount))
}

export const canShowPlaceOnMap = (place = {}) => {
  if (place?.canShowOnMap === false || place?.can_show_on_map === false) {
    return false
  }

  const lat = Number(place?.lat)
  const lng = Number(place?.lng)
  return Number.isFinite(lat) && Number.isFinite(lng)
}

export const getResultFilterLabel = (filterMode) => {
  return RESULT_FILTER_OPTIONS.find((option) => option.value === filterMode)?.label || '전체'
}

export const isSearchErrorMessage = (message = '') => {
  const text = getTextValue(message)
  return text.includes('오류가 발생했습니다') || text.includes('다시 시도해 주세요')
}
