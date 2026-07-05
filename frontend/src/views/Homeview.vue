<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
import { useSavedPlaceActions } from '@/composables/useSavedPlaceActions'
import { waitForKakaoServices } from '@/composables/useKakaoMapSdk'
import { useAuthStore } from '@/stores/auth'
import {
  DEFAULT_CENTER,
  SEARCH_RADIUS,
  MIN_VIEWPORT_SEARCH_RADIUS,
  MAX_VIEWPORT_SEARCH_RADIUS,
  DB_SEARCH_RESULT_COUNT,
  DISPLAY_BATCH_SIZE,
  KAKAO_FALLBACK_MIN_RESULTS,
  AI_WEB_SEARCH_MIN_DB_RESULTS,
  AI_WEB_SEARCH_MIN_TOTAL_RESULTS,
  AI_WEB_SEARCH_SUFFICIENT_TOTAL_RESULTS,
  DB_MARKER_ALLOWED_CATEGORIES,
  KAKAO_DETAIL_LOOKUP_RADIUS_M,
} from '@/constants/homeSearchConstants'
import {
  AI_SEARCH_PRESETS,
  NO_RESULT_MESSAGE_PATTERNS,
  RESULT_FILTER_OPTIONS,
  RESULT_SORT_OPTIONS,
} from '@/constants/homeViewUiConstants'
import {
  buildBaseLocationSearchQueries,
  dedupeBaseLocationCandidates,
  getAutoSelectedBaseCandidate,
  normalizeKakaoBaseCandidate,
  scoreBaseLocationCandidate,
  sortBaseLocationCandidates,
} from '@/utils/homeBaseLocation'
import {
  appendMainPlaceFallbackResults,
  calculateKakaoTagRecommendation,
  getAncillaryPlaceAdjustment,
  getSavedTagNames,
  getStructuredPlaceEvidenceText,
  getWaitingPlaceSuitability,
  getWalkHealingSuitability,
  hasSavedTagMatch,
  isTakeoutHeavyCafeCandidate,
  makeKakaoResultTags,
  makeTag,
} from '@/utils/kakaoPlaceRecommendation'
import {
  assignMarkerLabels,
  convertDbPlaces,
  convertRecommendationPlaces,
} from '@/utils/placeResultConverters'
import {
  dedupeAiWebSearchCandidates,
  getAiEvidenceSources,
  getAiWebCandidateBadge,
  getAiWebCandidateCaution,
  getAiWebCandidateSourceUrl,
  getAiWebCandidateSummary,
  getAiWebSourceChannelLabel,
  isAiWebSourceReference,
} from '@/utils/aiWebCandidateHelpers'
import {
  buildAiWebSearchPlanPayload,
  buildSearchLogPayload,
  getAiWebSearchLocationHint,
  getSearchLogLocationHint,
} from '@/utils/searchPayloadBuilders'
import {
  getPlacesCenter,
  getRegionSearchCoreKeyword,
  groupKakaoPlacesByRegion,
  makeRegionCandidateFromGroup,
  shouldAskRegionCandidateSelection,
} from '@/utils/regionSearchHelpers'
import {
  getAiWebSearchRequestKey,
  getAiWebSearchStatusMessage,
  getBackendResultMessageSuffix,
  hasAiWebSearchDetailCondition,
  hasExplicitAiWebSearchRequest,
  isAiWebSearchHelpfulTopic,
  isAiWebSearchInfraBlockedTopic,
} from '@/utils/aiWebSearchPolicy'
import {
  getTagName,
  getTagClass,
  getTagSourceText,
  getSortedTags,
  toDisplayList,
  getTextValue,
  getScenarioDisplayLabel,
  getPersonalizationBoost,
  getPersonalizationReasons,
  getPersonalizationBoostText,
  getRecommendationPreviewLabels,
  isCafeSearchKeyword,
  shouldAppendDbPlaces,
  getDistanceMetersBetweenPlaces,
  dedupeSearchResults,
  getPlaceSourceText,
  getPlaceSourceClass,
  isDbPlace,
  getKakaoDetailLookupKey,
  getDirectKakaoDetailUrl,
  getBestKakaoDetailCandidate,
  buildKakaoDetailLookupQueries,
  getKakaoDetailPlaceCoordinates,
  debugKakaoDetailLog,
  hasNormalizedKeywordMatch,
  isCategoryFallbackRecommendation,
  getDirectMenuMatchText,
  getSpecificPlaceTypeTerms,
  getResultSourceRank,
  getConfidenceRank,
  compareLowConfidenceFallback,
  getPlaceScoreCapReasons,
  getPlaceFrameMatchStrength,
  getRecommendScore,
  getRecommendationConfidenceText,
  getRecommendationConfidence,
  getRecommendationFallbackText,
  getRecommendationMetaText,
  getRecommendationMissingLabels,
  matchesResultFilter,
  getWebEvidenceUrl,
  isWebEvidenceCandidateResult,
  isKakaoCandidateResult,
  isRecommendationPlace,
  getDistanceText,
  getDistanceValue,
  getDirectMenuDbMatchCount,
  getMenuSearchProfile,
  getRecommendationConditionData,
  getKakaoFallbackCandidateScore,
  getRecommendationIntentForScoring,
  getSearchPlanDebugSnapshot,
  buildFrameBasedKakaoKeywords,
  applyLocationToSearchKeywords,
  filterKeywordsByExclusions,
  isFrameDrivenSearch,
  getPlanKakaoKeywordCandidates,
  getIntentGroupDisplayLabel,
  getFrameLocationMode,
  getFrameCandidateCategoryCodes,
  getFrameRankingPolicy,
  getFrameResultMatchTerms,
  getFrameWebSearchQueries,
  getFrameDisplayLabel,
  getResolvedSearchPlanLocationQuery,
  getFrameAnchorLocation,
  getFrameExclusions,
  getFrameConstraints,
  getFrameTargetObjects,
  getFrameCandidatePlaceTypes,
  getSearchPlanFrame,
  getPlannerBoolean,
  getSearchPlanValue,
  isBackendAiFirstResponse,
  getClarificationOptionValue,
  getClarificationOptionLabel,
  getClarificationOptionItems,
  getPlannerList,
  getPlannerText,
  normalizeLocationText,
} from '@/utils/homePlaceHelpers'
import {
  adaptConversationalSearchPlan,
  buildSearchPlan,
  cloneSearchPlanForMapCenter,
  filterFrameDirectMatchedResults,
  filterPlacesByPlanExclusions,
  getFrameDirectMatchCount,
  getPreferredTagsForIntent,
  getRecommendationIntent,
  getUnifiedSearchMode,
  hasKakaoWorkCafeEvidence,
  isNonRegionLocationText,
  isRecommendationQueryText,
  makeLocationChoiceClarificationPlan,
  mergeRequestedConditionReview,
  shouldAskLocationChoiceBeforeSearch,
  toArray,
} from '@/utils/homeSearchPlanning'
import {
  reverseGeocodeLocationHint,
  runKakaoAddressSearch,
  runKakaoKeywordCandidateSearch,
  runKakaoKeywordSearchLimited,
} from '@/utils/kakaoSearchHelpers'

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
const {
  savingPlaceId,
  saveMessage: placeSaveMessage,
  isPlaceSaved,
  loadSavedPlaceKeys,
  savePlace: handleSavePlace,
} = useSavedPlaceActions()
const activeTab = ref(normalizeTab(props.initialTab))
const searchKeyword = ref('')

watch(
  () => props.initialTab,
  (nextTab) => {
    activeTab.value = normalizeTab(nextTab)
  },
)

const mapCenter = ref(DEFAULT_CENTER)
const mapViewportBounds = ref(null)
const mapFitBoundsKey = ref(0)
const currentLocationPlace = ref([])
const allSearchResults = ref([])
const mainResults = ref([])
const fallbackResults = ref([])
const webReferenceResults = ref([])
const preserveBackendResultOrder = ref(false)
const visibleCount = ref(DISPLAY_BATCH_SIZE)
const resultFilterMode = ref('all')
const sortMode = ref('distance')
const searchResultStatus = ref('idle')
const searchLogSaveState = ref({
  status: 'idle',
  message: '',
  statusCode: null,
})
const searchErrorMessage = ref('')
const resultSourceLabel = ref('검색 결과')
const resultMessageSuffix = ref('')
const selectedPlace = ref(null)
const hiddenMapMarkerPlaceId = ref(null)
const markerChoiceRequestKey = ref(0)
const detailTagList = ref(null)
const resolvedKakaoDetailUrls = ref({})
const kakaoDetailLookupStatus = ref({})
const baseLocationCandidates = ref([])
const pendingBaseLocationSearch = ref(null)
const isResultListCollapsed = ref(false)
const isPlaceDetailCollapsed = ref(false)
const isPlaceDetailDismissed = ref(false)
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
const conversationMessages = ref([])
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

const normalizeRouteQueryValue = (value) => {
  const nextQuery = Array.isArray(value) ? value[0] : value

  return String(nextQuery || '').trim()
}

const isRouteAutoSearchRequested = (value) => {
  return normalizeRouteQueryValue(value) === '1'
}

let lastRouteAutoSearchKey = ''

const clearRouteAutoSearchFlag = () => {
  if (!isRouteAutoSearchRequested(route.query.autoSearch)) return

  const { autoSearch, ...nextQuery } = route.query
  router.replace({ query: nextQuery }).catch(() => undefined)
}

const runRouteAutoSearchOnce = async (normalizedQuery) => {
  const autoSearchKey = normalizedQuery
  if (!autoSearchKey || lastRouteAutoSearchKey === autoSearchKey) return

  lastRouteAutoSearchKey = autoSearchKey
  await nextTick()

  if (
    !isRouteAutoSearchRequested(route.query.autoSearch) ||
    searchKeyword.value.trim() !== normalizedQuery ||
    isSearchingMap.value
  ) {
    return
  }

  clearRouteAutoSearchFlag()
  await handleSearch()
}

const applyRouteSearchQuery = (value, autoSearch = '') => {
  const normalizedQuery = normalizeRouteQueryValue(value)

  if (!normalizedQuery) return

  searchKeyword.value = normalizedQuery
  mapSearchKeyword.value = normalizedQuery
  activeTab.value = 'search'

  if (!isRouteAutoSearchRequested(autoSearch)) {
    lastRouteAutoSearchKey = ''
    return
  }

  void runRouteAutoSearchOnce(normalizedQuery)
}

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
  preserveBackendResultOrder.value = false
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

const handleKakaoMapLoadError = (error) => {
  console.error(error)
  baseLocationCandidates.value = []
  pendingBaseLocationSearch.value = null
  selectedPlace.value = null
  showDetailPanel.value = false
  detailFrameError.value = false
  isSearchingMap.value = false
  loadingMessage.value = ''
  setMainSearchError(KAKAO_MAP_LOAD_ERROR_MESSAGE)
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
  if (preserveBackendResultOrder.value) {
    return Array.isArray(mainResults.value) ? mainResults.value : []
  }

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
  if (preserveBackendResultOrder.value) {
    return filteredSearchResults.value
  }

  return sortSearchResults(filteredSearchResults.value)
})

const searchedPlaces = computed(() => {
  return assignMarkerLabels(
    sortedSearchResults.value.slice(0, visibleCount.value),
  )
})

const canShowPlaceOnMap = (place = {}) => {
  if (place?.canShowOnMap === false || place?.can_show_on_map === false) {
    return false
  }

  const lat = Number(place?.lat)
  const lng = Number(place?.lng)
  return Number.isFinite(lat) && Number.isFinite(lng)
}

const mapPlaces = computed(() => {
  return [
    ...currentLocationPlace.value,
    ...searchedPlaces.value.filter((place) => canShowPlaceOnMap(place)),
  ]
})

function canShowPlaceDetailPanel(place = {}) {
  return Boolean(place)
}

const shouldShowPlaceDetailPanel = computed(() => {
  return Boolean(
    selectedPlace.value &&
    !isPlaceDetailDismissed.value &&
    canShowPlaceDetailPanel(selectedPlace.value)
  )
})

const mapLayoutKey = computed(() => {
  return [
    searchedPlaces.value.length > 0 ? 'has-results' : 'no-results',
    shouldShowPlaceDetailPanel.value ? 'has-detail' : 'no-detail',
    isResultListCollapsed.value ? 'list-collapsed' : 'list-expanded',
    isPlaceDetailCollapsed.value ? 'detail-collapsed' : 'detail-expanded',
  ].join(':')
})

const hasMoreResults = computed(() => {
  return visibleCount.value < filteredSearchResults.value.length
})

const resultCountText = computed(() => {
  if (!displayResults.value.length) {
    return ''
  }

  if (isResultListCollapsed.value) {
    return '검색 결과'
  }

  const suffix = resultMessageSuffix.value
    ? ` · ${resultMessageSuffix.value}`
    : ''

  if (resultFilterMode.value !== 'all') {
    return `${getResultFilterLabel()} ${searchedPlaces.value.length}개를 보여드려요${suffix}`
  }

  return `${searchedPlaces.value.length}개를 찾았어요${suffix}`
})

const resultPanelTitle = computed(() => {
  if (resultCountText.value) {
    return resultCountText.value
  }
  if (['empty', 'filtered_empty'].includes(searchResultStatus.value)) {
    return '조건에 맞는 장소를 찾지 못했어요'
  }
  if (searchResultStatus.value === 'error') {
    return '검색 결과를 표시하지 못했어요'
  }
  return '검색 결과'
})

const mapParserStatus = computed(() => {
  if (!mapAiParse.value) {
    return null
  }
  if (
    !displayResults.value.length &&
    !isSearchingMap.value &&
    ['empty', 'error', 'idle'].includes(searchResultStatus.value)
  ) {
    return null
  }

  const parserProvider = getTextValue(mapAiParse.value.parser_provider)
  const parserFallback = mapAiParse.value.parser_fallback === true
  const executionMode = getTextValue(
    mapAiParse.value.execution_mode ||
    activeSearchPlan.value?.execution_mode ||
    activeSearchPlan.value?.executionMode,
  )
  const planSource = getTextValue(
    mapAiParse.value.plan_source ||
    activeSearchPlan.value?.plan_source ||
    activeSearchPlan.value?.planSource,
  )
  const hasAiFrame = executionMode === 'frame' && planSource !== 'legacy_fallback'
  const isAiFirstParser = executionMode === 'ai_first_orchestrator' ||
    parserProvider === 'ai_intent_planner' ||
    parserProvider === 'backend_ai_only'
  const isAiProviderParser = ['openai', 'gms', 'ai'].includes(parserProvider)

  if (!parserFallback && (isAiProviderParser || hasAiFrame || isAiFirstParser)) {
    return {
      label: '조건 정리 완료',
      detail: '말씀하신 내용을 장소와 조건으로 정리했어요.',
      className: 'ai',
    }
  }

  const fallbackReason = getTextValue(
    mapAiParse.value.ai_fallback_reason ||
    mapAiParse.value.fallback_reason ||
    activeSearchPlan.value?.fallbackReason,
  )

  return {
    label: '기본 검색 기준 적용',
    detail: fallbackReason
      ? `입력한 표현에서 바로 찾을 수 있는 조건을 우선 적용했어요. (${fallbackReason})`
      : '입력한 표현에서 바로 찾을 수 있는 조건을 우선 적용했어요.',
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
  const infraTopic = Boolean(summary.infra_blocked_topic) ||
    isAiWebSearchInfraBlockedTopic(context.query, context.condition, searchPlan)
  const helpfulTopic = Boolean(summary.web_helpful_topic) ||
    isAiWebSearchHelpfulTopic(context.query, context.condition, searchPlan)

  if (
    infraTopic &&
    !explicitRequest &&
    strongEvidenceCount > 0 &&
    totalCount >= AI_WEB_SEARCH_MIN_TOTAL_RESULTS &&
    lowConfidenceCount < Math.max(1, Math.ceil(totalCount / 2))
  ) {
    return false
  }

  if (explicitRequest) {
    return true
  }

  if (!helpfulTopic && !infraTopic && !isFrameDrivenSearch(searchPlan)) {
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

const shouldShowResultPanel = computed(() => {
  return Boolean(
    !isSearchingMap.value &&
    (
      displayResults.value.length ||
      shouldShowAiWebSearchPanel.value
    ),
  )
})

const shouldShowSearchMapContent = computed(() => {
  return Boolean(
    activeTab.value === 'map' ||
    isSearchingMap.value ||
    displayResults.value.length ||
    shouldShowAiWebSearchPanel.value ||
    baseLocationCandidates.value.length,
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

const makeConversationMessage = ({
  role = 'assistant',
  type = 'clarification',
  content = '',
  options = [],
  plan = null,
} = {}) => {
  const text = String(content || '').trim()
  if (!text) return null

  return {
    role,
    type,
    content: text,
    text,
    label: role === 'user' ? displayUserName.value : 'AI',
    options: getPlannerList(options),
    plan,
    createdAt: new Date().toISOString(),
  }
}

const syncClarificationThreadFromMessages = () => {
  clarificationThread.value = conversationMessages.value.filter((message) => {
    return ['user', 'assistant'].includes(message.role)
  })
}

const trimConversationMessages = (messages = [], limit = 12) => {
  return messages.filter((item) => item && item.text).slice(-limit)
}

const getClarificationStateKind = (plan = {}, partialFrame = {}) => {
  const debugStatus = getPlannerText(plan?.ai_debug?.post_validation?.status)
  if (debugStatus === 'forced_clarification') {
    return 'intent_evidence'
  }

  const reason = getPlannerText(
    plan?.fallback_reason ||
    plan?.fallbackReason ||
    plan?.ai_fallback_reason ||
    plan?.aiFallbackReason,
  ).toLowerCase()
  if (reason.includes('location')) {
    return 'location'
  }

  const missingInfo = getPlannerList(partialFrame?.missing_info || partialFrame?.missingInfo)
  if (missingInfo.length) {
    return getPlannerText(missingInfo[0]) || 'intent_evidence'
  }

  return 'intent_evidence'
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
  const partialFrame = getSearchPlanFrame(partialSearchPlan)
  const partialCandidatePlaceTypes = getFrameCandidatePlaceTypes(partialSearchPlan)
  const partialConstraints = getFrameConstraints(partialSearchPlan)
  const partialExclusions = getFrameExclusions(partialSearchPlan)
  const clarificationOptions = getClarificationOptionItems(
    plan?.clarification_options ||
    plan?.clarificationOptions ||
    partialFrame?.clarification_options ||
    partialFrame?.clarificationOptions ||
    [],
  )
  const partialConditions = [
    ...getPlannerList(
      getSearchPlanValue(partialSearchPlan, 'requestedConditions', 'requested_conditions', 'conditions') ||
      plan?.conditions ||
      [],
    ),
    ...partialConstraints,
  ].filter((condition, index, list) => condition && list.indexOf(condition) === index)

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
      place_intent_frame: partialFrame,
      placeIntentFrame: partialFrame,
      candidate_place_types: partialCandidatePlaceTypes,
      candidatePlaceTypes: partialCandidatePlaceTypes,
      constraints: partialConstraints,
      exclusions: partialExclusions,
      display_label: getFrameDisplayLabel(partialSearchPlan),
      displayLabel: getFrameDisplayLabel(partialSearchPlan),
      web_search_queries: getFrameWebSearchQueries(partialSearchPlan),
      webSearchQueries: getFrameWebSearchQueries(partialSearchPlan),
      kakaoKeywordCandidates: getPlanKakaoKeywordCandidates(partialSearchPlan),
      kakaoKeywords: getPlanKakaoKeywordCandidates(partialSearchPlan),
      intent_group: getPlannerText(getSearchPlanValue(partialSearchPlan, 'intent_group', 'intentGroup')),
      intentGroup: getPlannerText(getSearchPlanValue(partialSearchPlan, 'intent_group', 'intentGroup')),
    },
    missing_field: getClarificationStateKind(plan, partialFrame),
    clarification_kind: getClarificationStateKind(plan, partialFrame),
    clarification_question: assistantText,
    clarification_options: clarificationOptions,
    clarificationOptions,
    message: assistantText,
  }
  conversationModeStarted.value = true
  followUpInput.value = ''
  clearTopSearchInputsForClarification()
  conversationMessages.value = trimConversationMessages([
    ...conversationMessages.value,
    makeConversationMessage({
      role: 'user',
      type: 'search',
      content: userText,
      plan: partialSearchPlan,
    }),
    makeConversationMessage({
      role: 'assistant',
      type: 'clarification',
      content: assistantText,
      options: clarificationOptions,
      plan,
    }),
  ])
  syncClarificationThreadFromMessages()
  focusFollowUpInput()
}

const setDecisionConversationThread = (query, plan, message, type = 'out_of_scope') => {
  const userText = String(query || '').trim()
  const assistantText = String(message || plan?.message || '').trim()
  conversationMessages.value = trimConversationMessages([
    ...conversationMessages.value,
    makeConversationMessage({
      role: 'user',
      type: 'search',
      content: userText,
      plan: plan?.search_plan || null,
    }),
    makeConversationMessage({
      role: 'assistant',
      type,
      content: assistantText,
      plan,
    }),
  ])
  syncClarificationThreadFromMessages()
}

const clearPendingClarification = ({ preserveMessages = false } = {}) => {
  pendingClarification.value = null
  if (!preserveMessages) {
    conversationMessages.value = []
  }
  syncClarificationThreadFromMessages()
  followUpInput.value = ''
}

const shouldShowClarificationThread = computed(() => {
  return clarificationThread.value.length > 0
})

const shouldShowFollowUpInput = computed(() => {
  return Boolean(pendingClarification.value)
})

const isClarificationOnlyState = computed(() => {
  return Boolean(
    pendingClarification.value &&
    !isSearchingMap.value &&
    !displayResults.value.length &&
    !baseLocationCandidates.value.length,
  )
})

const clarificationOptions = computed(() => {
  return getClarificationOptionItems(
    pendingClarification.value?.clarification_options ||
    pendingClarification.value?.clarificationOptions ||
    [],
  )
})

const getActiveSearchBaseLabel = () => {
  const plan = activeSearchPlan.value || {}
  const explicitLocation = getTextValue(
    plan.locationQuery ||
    plan.location_query ||
    plan.baseLocationQuery ||
    plan.base_location_query ||
    getFrameAnchorLocation(plan),
  )

  if (explicitLocation) {
    return `${explicitLocation} 기준`
  }

  return '현재 위치 기준'
}

const searchConversationTitle = computed(() => {
  const query = mapSearchKeyword.value.trim() || searchKeyword.value.trim()

  if (isSearchingMap.value) {
    return query ? `“${query}”에 맞는 장소를 찾는 중이에요.` : '필요한 장소를 찾는 중이에요.'
  }

  if (pendingClarification.value) {
    return 'AI가 조건을 조금 더 확인하려고 합니다.'
  }

  if (displayResults.value.length && query) {
    return `${getActiveSearchBaseLabel()}으로 “${query}” 결과를 찾았어요.`
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
  const frameLabel = getFrameDisplayLabel(activeSearchPlan.value)
  const displayLabel = getTextValue(activeSearchPlan.value?.displayLabel || activeSearchPlan.value?.display_label)
  const intentGroupLabel = getIntentGroupDisplayLabel(
    activeSearchPlan.value?.intentGroup || activeSearchPlan.value?.intent_group || '',
  )
  const scenarioLabel = getScenarioDisplayLabel(activeSearchPlan.value?.recommendationIntent || '')
  const category = frameLabel ||
    displayLabel ||
    intentGroupLabel ||
    scenarioLabel ||
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

const aiSearchPresets = AI_SEARCH_PRESETS

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
    if (!selectedPlace.value?.id) {
      hiddenMapMarkerPlaceId.value = null
      isPlaceDetailDismissed.value = false
      isPlaceDetailCollapsed.value = false
    }

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
    handleKakaoMapLoadError(error)
  }
}

watch(
  () => [route.query.q, route.query.autoSearch],
  ([query, autoSearch]) => {
    applyRouteSearchQuery(query, autoSearch)
  },
  { immediate: true },
)

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

const applyBackendAiSearchOrigin = (data = {}, fallbackCenter = null, fallbackLabel = '') => {
  const debugPipeline = data?.debug_pipeline || {}
  const searchOrigin = debugPipeline.search_origin || {}
  const locationResolution = debugPipeline.location_resolution || {}
  const lat = toFiniteCoordinate(searchOrigin.search_lat ?? locationResolution.lat)
  const lng = toFiniteCoordinate(searchOrigin.search_lng ?? locationResolution.lng)

  if (lat === null || lng === null) {
    return false
  }

  const nextCenter = { lat, lng }
  const source = getTextValue(searchOrigin.source || locationResolution.source)
  const locationMode = getTextValue(
    searchOrigin.location_mode ||
    getFrameLocationMode(data?.search_plan || data?.place_intent_frame || {}),
  )
  const isCurrentContext = locationMode === 'current_context' || source.includes('current')
  const label = getTextValue(locationResolution.label || searchOrigin.label || fallbackLabel)
  const markerName = isCurrentContext
    ? '현재 위치'
    : `검색 기준 위치: ${label || 'AI 기준 위치'}`

  if (!isSameMapCenter(mapCenter.value, nextCenter)) {
    mapCenter.value = nextCenter
  }

  currentLocationPlace.value = [
    {
      id: isCurrentContext
        ? 'current-location'
        : `backend-location-${locationResolution.external_id || `${lat}-${lng}`}`,
      name: markerName,
      category: '',
      address: locationResolution.address || '',
      lat,
      lng,
      distance: null,
      markerColor: 'green',
      searchSource: isCurrentContext ? 'current_location' : 'base_location',
      sourceLabel: '기준',
      tags: [makeTag(isCurrentContext ? '현재위치' : '검색기준위치', 'category_rule')],
      tagSource: 'Backend AI-first location resolution',
    },
  ]

  return true
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
      place_intent_frame: activeSearchPlan.value.placeIntentFrame || activeSearchPlan.value.place_intent_frame || {},
      candidate_place_types: activeSearchPlan.value.candidatePlaceTypes || [],
      constraints: activeSearchPlan.value.constraints || [],
      exclusions: activeSearchPlan.value.exclusions || [],
      excluded_categories: activeSearchPlan.value.excludedCategories || [],
      display_label: activeSearchPlan.value.displayLabel || '',
      web_search_queries: activeSearchPlan.value.webSearchQueries || [],
      kakaoKeywordCandidates: activeSearchPlan.value.kakaoKeywordCandidates || [],
      intent_group: activeSearchPlan.value.intentGroup || '',
    },
    result_count: displayResults.value.length,
  }
}

const resolveConversationalSearchPlan = async (keyword, previousContext = null, extraPayload = {}) => {
  try {
    loadingMessage.value = '검색 의도 해석 중'
    const data = await buildConversationalSearchPlan({
      query: keyword,
      lat: mapCenter.value?.lat ?? null,
      lng: mapCenter.value?.lng ?? null,
      mapCenter: mapCenter.value || null,
      previousContext,
      ...extraPayload,
    })

    if (import.meta.env.DEV) {
      console.debug('[대화형 검색 해석]', {
        action: data?.action,
        scenario: data?.search_plan?.scenario,
        locationQuery: data?.search_plan?.locationQuery,
        targetQuery: data?.search_plan?.targetQuery,
        needsClarification: data?.needs_clarification,
        provider: data?.parser_provider,
        parserProvider: data?.parser_provider,
        parserFallback: data?.parser_fallback,
        planSource: data?.plan_source,
        executionMode: data?.execution_mode,
        fallbackReason: data?.fallback_reason,
        aiFallbackReason: data?.ai_fallback_reason,
        aiDebug: data?.ai_debug,
        ...getSearchPlanDebugSnapshot(data?.search_plan || {}, {
          rawQuery: keyword,
        }),
      })
    }

    return data && typeof data === 'object' ? data : null
  } catch (error) {
    if (import.meta.env.DEV) {
      console.warn('[대화형 검색 해석] fallback to local planner', {
        message: error?.message || '',
        status: error?.response?.status || null,
        responseData: error?.response?.data || null,
      })
    }
    return null
  }
}

const buildClarificationFollowUpPayload = (pending = null, answer = '') => {
  if (!pending) return {}

  const previousSearchPlan = pending.partial_search_plan || pending.plan?.search_plan || {}
  const pendingFrame = getSearchPlanFrame(previousSearchPlan)
  const lastResolvedLocationContext = {
    locationQuery: getResolvedSearchPlanLocationQuery(previousSearchPlan) || '',
    anchorLocation: getFrameAnchorLocation(previousSearchPlan) || '',
    locationMode: getFrameLocationMode(previousSearchPlan) || 'current_context',
    lat: mapCenter.value?.lat ?? null,
    lng: mapCenter.value?.lng ?? null,
  }
  const previousSearchContext = {
    query: pending.original_query || pending.query || '',
    search_plan: previousSearchPlan,
    pending_clarification_frame: pendingFrame,
    is_clarification_followup: true,
    clarification_answer: answer,
    pending_clarification_question: pending.clarification_question || pending.message || '',
    original_query: pending.original_query || pending.query || '',
    previous_user_query: pending.original_query || pending.query || '',
    last_resolved_location_context: lastResolvedLocationContext,
  }

  return {
    previousContext: previousSearchContext,
    previous_context: previousSearchContext,
    previous_search_context: previousSearchContext,
    previous_search_plan: previousSearchPlan,
    pending_clarification_frame: pendingFrame,
    pending_clarification_question: pending.clarification_question || pending.message || '',
    is_clarification_followup: true,
    clarification_answer: answer,
    previous_user_query: pending.original_query || pending.query || '',
    original_query: pending.original_query || pending.query || '',
    last_resolved_location_context: lastResolvedLocationContext,
  }
}

const appendClarificationAnswerMessage = (answer = '') => {
  const text = String(answer || '').trim()
  if (!text) return

  conversationMessages.value = trimConversationMessages([
    ...conversationMessages.value,
    makeConversationMessage({
      role: 'user',
      type: 'clarification_answer',
      content: text,
    }),
  ])
  syncClarificationThreadFromMessages()
}

const appendSearchSummaryMessage = (message = '') => {
  const text = String(message || '').trim()
  if (!text) return

  conversationMessages.value = trimConversationMessages([
    ...conversationMessages.value,
    makeConversationMessage({
      role: 'assistant',
      type: 'search_summary',
      content: text,
      plan: activeSearchPlan.value || null,
    }),
  ])
  syncClarificationThreadFromMessages()
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

const submitClarificationOption = async (option = '') => {
  const answer = getClarificationOptionValue(option)
  if (!answer || isSearchingMap.value) return

  followUpInput.value = answer
  await submitClarificationFollowUp()
}

const getRecommendationMatchedLabels = (place) => {
  const labels = toDisplayList(place?.matchedTagLabels || place?.matched_tag_labels)
  const baseLabels = labels.length ? labels : toDisplayList(place?.matchedTags || place?.matched_tags)
  const menuLabels = getMenuDisplayMatchedLabels(place)

  return [...new Set([...baseLabels, ...menuLabels])]
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

const getResolvedKakaoDetailUrl = (place) => {
  const lookupKey = getKakaoDetailLookupKey(place)
  return lookupKey ? resolvedKakaoDetailUrls.value[lookupKey] || '' : ''
}

const getKakaoDetailUrl = (place) => {
  return getDirectKakaoDetailUrl(place) || getResolvedKakaoDetailUrl(place)
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
  if (
    isWebEvidenceCandidateResult(place) ||
    place?.canShowOnMap === false ||
    place?.can_show_on_map === false
  ) {
    return ''
  }

  const destinationLat = toFiniteCoordinate(place?.lat)
  const destinationLng = toFiniteCoordinate(place?.lng)

  if (destinationLat === null || destinationLng === null) {
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
  if (isWebEvidenceCandidateResult(place)) {
    return getWebEvidenceUrl(place)
  }

  return getKakaoDetailUrl(place)
}

const getPlaceDetailActionText = (place) => {
  return isWebEvidenceCandidateResult(place) ? '웹에서 확인하기' : '카카오 상세 보기'
}

const getSelectedPlaceDetailLabel = (place) => {
  return isWebEvidenceCandidateResult(place) ? '선택한 참고 정보' : '선택한 장소'
}

const hasKakaoDetail = (place) => {
  return Boolean(getKakaoDetailUrl(place))
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

const getRecommendationReason = (place) => {
  if (!isRecommendationPlace(place)) {
    return ''
  }

  if (place?.recommendationReason && !shouldRewriteRecommendationReason(place.recommendationReason)) {
    return place.recommendationReason
  }

  if (place?.waitingPlacePenaltyReason || place?.waitingPlacePenalty) {
    return '일반적인 잠깐 휴식 목적과는 맞지 않을 수 있어 후순위로 반영했습니다.'
  }

  const matchedLabels = getRecommendationPreviewLabels(getRecommendationMatchedLabels(place), 2)
  const distanceText = getDistanceText(place)
  const sourceText = getPlaceSourceText(place)
  const needsVerification = getRecommendationConfidence(place) === 'low' ||
    isKakaoCandidateResult(place) ||
    isWebEvidenceCandidateResult(place)

  if (matchedLabels.length) {
    const distancePhrase = distanceText ? ` 기준 위치에서 ${distanceText} 정도로 가까운 편이에요.` : ''
    const verifyPhrase = needsVerification ? ' 세부 정보는 방문 전에 한 번 더 확인해 주세요.' : ''
    return `${matchedLabels.join(', ')} 조건과 맞아 보이는 장소예요.${distancePhrase}${verifyPhrase}`.trim()
  }

  const savedTags = [
    ...(place?.suggestedTags || []),
    ...(place?.verifiedTags || []),
  ]

  if (savedTags.length) {
    const verifyPhrase = needsVerification ? ' 다만 세부 조건은 방문 전 확인이 필요합니다.' : ''
    return `저장된 장소 정보가 검색 조건과 가까워 후보로 올렸어요.${verifyPhrase}`
  }

  if (getDistanceValue(place) !== null) {
    return `검색 기준 위치에서 ${distanceText} 정도 떨어진 후보예요.`
  }

  return `${sourceText}를 참고해 검색 조건과 가까운 장소로 정리했어요.`
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

const isWeakFrameFallbackRecommendation = (place = {}) => {
  const frameMatchStrength = getPlaceFrameMatchStrength(place)
  const scoreCapReasons = getPlaceScoreCapReasons(place)

  return (
    frameMatchStrength === 'weak' ||
    scoreCapReasons.includes('frame_weak_category_fallback') ||
    scoreCapReasons.includes('category_fallback') ||
    (
      isFrameDrivenSearch(activeSearchPlan.value || {}) &&
      isCategoryFallbackRecommendation(place)
    )
  )
}

const getFrameEvidenceSortRank = (place = {}) => {
  const searchPlan = activeSearchPlan.value || {}
  if (!isFrameDrivenSearch(searchPlan)) return 0

  const frameMatchStrength = getPlaceFrameMatchStrength(place)
  if (frameMatchStrength === 'strong') return 7
  if (frameMatchStrength === 'medium') return 5
  if (frameMatchStrength === 'weak') return 1

  const evidenceText = getStructuredPlaceEvidenceText(place)
  const targetTerms = [
    ...getFrameTargetObjects(searchPlan),
    ...getFrameResultMatchTerms(searchPlan),
  ]
  const candidateTerms = [
    ...getFrameCandidatePlaceTypes(searchPlan),
    ...getFrameCandidateCategoryCodes(searchPlan),
  ]

  if (hasNormalizedKeywordMatch(evidenceText, targetTerms)) return 6
  if (hasNormalizedKeywordMatch(evidenceText, candidateTerms)) return 4
  if (isCategoryFallbackRecommendation(place)) return 0

  return 1
}

const getRecommendationSortScore = (place) => {
  const baseScore = getRecommendScore(place)
  const weakFrameFallback = isWeakFrameFallbackRecommendation(place)
  const frameRank = getFrameEvidenceSortRank(place)
  const sourceBonus = 0
  const waitingPenalty = place?.waitingPlacePenalty || 0
  const mainPlaceScore = place?.mainPlaceScore || 0
  const ancillaryPenalty = place?.ancillaryPlacePenalty || 0
  const intentMismatchPenalty = place?.intentMismatchPenalty || 0
  const placeShapeScore = mainPlaceScore - ancillaryPenalty - intentMismatchPenalty
  const weakFramePenalty = weakFrameFallback ? 85 : 0

  if (place?.resultType === 'kakao_takeout_untagged') {
    return baseScore + sourceBonus + placeShapeScore - 35 - waitingPenalty - weakFramePenalty
  }

  if (place?.resultType === 'kakao_only') {
    return baseScore + sourceBonus + placeShapeScore - 20 - waitingPenalty - weakFramePenalty
  }

  if (place?.resultType === 'kakao_tag_weak') {
    return baseScore + sourceBonus + placeShapeScore - 12 - waitingPenalty - weakFramePenalty
  }

  if (place?.resultType === 'kakao_fallback_candidate') {
    const fallbackPenalty = frameRank >= 6
      ? 18
      : (frameRank >= 4 ? 35 : 75)
    return baseScore + sourceBonus + placeShapeScore - fallbackPenalty - waitingPenalty
  }

  return baseScore + sourceBonus + placeShapeScore - waitingPenalty - weakFramePenalty
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
  const frameRankDifference = getFrameEvidenceSortRank(secondPlace) - getFrameEvidenceSortRank(firstPlace)

  if (frameRankDifference !== 0) {
    return frameRankDifference
  }

  const shapeDifference =
    ((secondPlace.mainPlaceScore || 0) - (secondPlace.ancillaryPlacePenalty || 0) - (secondPlace.intentMismatchPenalty || 0)) -
    ((firstPlace.mainPlaceScore || 0) - (firstPlace.ancillaryPlacePenalty || 0) - (firstPlace.intentMismatchPenalty || 0))

  if (shapeDifference !== 0) {
    return shapeDifference
  }

  const distanceDifference = compareByDistance(firstPlace, secondPlace)
  if (distanceDifference !== 0) {
    return distanceDifference
  }

  return getResultSourceRank(firstPlace) - getResultSourceRank(secondPlace)
}

const compareForRecommendationSearch = (firstPlace, secondPlace) => {
  const frameRankDifference = getFrameEvidenceSortRank(secondPlace) - getFrameEvidenceSortRank(firstPlace)

  if (frameRankDifference !== 0) {
    return frameRankDifference
  }

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
  const frameRankDifference = getFrameEvidenceSortRank(secondPlace) - getFrameEvidenceSortRank(firstPlace)

  if (frameRankDifference !== 0) {
    return frameRankDifference
  }

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
    searchPlan = null,
  } = {},
) => {
  return toArray(places).map((place) => {
    const savedTagData = savedTagDataByExternalId[String(place.id)] || {}
    const rawScores = savedTagData.raw_scores || {}
    const hasTagData = hasSavedTagMatch(savedTagData)
    const recommendationIntentForScoring = getRecommendationIntentForScoring(
      recommendationIntent,
      searchPlan || {},
    )
    const recommendationData = calculateKakaoTagRecommendation({
      place,
      savedTagData,
      query,
      center,
      preferredTags,
      recommendationIntent: recommendationIntentForScoring,
    })
    const takeoutHeavy = isTakeoutHeavyCafeCandidate(place)
    const waitingSuitability = recommendationIntentForScoring === 'waiting_place'
      ? getWaitingPlaceSuitability(place, savedTagData)
      : { excluded: false, penalty: 0 }
    const walkHealingSuitability = recommendationIntentForScoring === 'walk_healing'
      ? getWalkHealingSuitability({ place, query })
      : { excluded: false, penalty: 0, bonus: 0, reason: null }
    const ancillaryAdjustment = getAncillaryPlaceAdjustment({
      place,
      query,
      categoryHint,
      recommendationIntent: recommendationIntentForScoring,
      isAncillaryIntent,
    })
    const workCafeHasEvidence = recommendationIntentForScoring === 'work_cafe'
      ? hasKakaoWorkCafeEvidence(place, savedTagData)
      : false
    const workCafeFallbackPenalty = recommendationIntentForScoring === 'work_cafe' && !workCafeHasEvidence
      ? (takeoutHeavy ? 22 : 14)
      : 0
    const fallbackScore = getKakaoFallbackCandidateScore({
      place,
      center,
      mainPlaceScore: ancillaryAdjustment.mainPlaceScore,
      ancillaryPlacePenalty: ancillaryAdjustment.ancillaryPlacePenalty,
      intentMismatchPenalty: ancillaryAdjustment.intentMismatchPenalty,
      waitingPlacePenalty: recommendationData.waitingPlacePenalty || waitingSuitability.penalty || 0,
      walkHealingPenalty: walkHealingSuitability.penalty || 0,
      walkHealingBonus: walkHealingSuitability.bonus || 0,
      workCafePenalty: workCafeFallbackPenalty,
    })
    const fallbackReason = [
      '저장 장소만으로 부족해 카카오 검색 결과도 함께 참고했어요.',
      workCafeFallbackPenalty
        ? '작업/노트북/콘센트/와이파이 같은 확인 정보가 부족해 후순위로 반영했습니다.'
        : '',
      '외부 검색 결과이므로 방문 전 세부 조건 확인이 필요합니다.',
    ].filter(Boolean).join(' ')

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
        ? '저장 장소만으로 부족해 카카오 검색 결과도 함께 참고한 장소입니다.'
        : '',
      fallback_description: fallbackCandidate
        ? '저장 장소만으로 부족해 카카오 검색 결과도 함께 참고한 장소입니다.'
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
      workCafeHasEvidence,
      workCafeFallbackPenalty,
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
    if (isPlaceExcludedByPlan(place, searchPlan || {})) return false
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

const resetAiWebSearchState = () => {
  aiWebSearchContext.value = null
  aiWebSearchAvailability.value = null
  aiWebSearchStatus.value = 'idle'
  aiWebSearchMessage.value = ''
  aiWebSearchCandidates.value = []
  webReferenceResults.value = []
  aiWebSearchLastResult.value = null
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

  if (import.meta.env.DEV) {
    console.debug('[AI 웹 검색 context]', getSearchPlanDebugSnapshot(aiWebSearchContext.value.searchPlan, {
      rawQuery: query,
      locationHint,
    }))
  }
}

const getSearchLogAuthToken = () => {
  try {
    return localStorage.getItem('authToken')
  } catch (error) {
    return ''
  }
}

const setSearchLogSaveState = ({
  status = 'idle',
  message = '',
  statusCode = null,
} = {}) => {
  searchLogSaveState.value = {
    status,
    message,
    statusCode,
  }
}

const saveSearchLogSilently = async (payload) => {
  if (!payload?.query) {
    setSearchLogSaveState({
      status: 'skipped',
      message: '검색어가 없어 검색 기록 저장을 건너뛰었습니다.',
    })
    return { status: 'skipped', reason: 'missing_query' }
  }

  if (!getSearchLogAuthToken()) {
    if (authStore.isLoggedIn) {
      const message = '로그인 상태지만 인증 토큰이 없어 검색 기록 저장을 건너뛰었습니다.'
      setSearchLogSaveState({
        status: 'failed',
        message,
      })
      console.warn('[SearchLog] save skipped', {
        reason: 'missing_auth_token',
        payload,
      })
      return { status: 'failed', reason: 'missing_auth_token' }
    }

    setSearchLogSaveState({
      status: 'skipped',
      message: '비로그인 검색이라 검색 기록 저장을 건너뛰었습니다.',
    })
    return { status: 'skipped', reason: 'anonymous_user' }
  }

  try {
    const data = await saveSearchLog(payload)
    setSearchLogSaveState({
      status: 'saved',
      message: '검색 기록을 저장했습니다.',
    })
    return { status: 'saved', data }
  } catch (error) {
    const statusCode = error?.response?.status || null
    const message = statusCode === 401
      ? '인증이 만료되어 검색 기록 저장에 실패했습니다.'
      : '검색은 완료됐지만 검색 기록 저장에 실패했습니다.'

    setSearchLogSaveState({
      status: 'failed',
      message,
      statusCode,
    })
    console.warn('[SearchLog] save failed', {
      status: statusCode || 'request_failed',
      responseData: error?.response?.data || null,
      payload,
    })
    return { status: 'failed', statusCode, error }
  }
}

const setSearchResults = ({
  results,
  sourceLabel = '검색 결과',
  messageSuffix = '',
  status = '',
  preserveBackendOrder = false,
}) => {
  const normalizedResults = Array.isArray(results) ? results : []
  resetAiWebSearchState()
  activeMenuSearchProfile.value = null
  preserveBackendResultOrder.value = Boolean(preserveBackendOrder)
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

  return convertDbPlaces(allowedPlaces, {
    requestedConditions,
    getKakaoDetailUrl,
  })
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
  searchPlan = null,
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

  const resolvedSearchPlan = searchPlan || activeSearchPlan.value || {}
  const searchKeywords = filterKeywordsByExclusions(
    [
      ...buildFrameBasedKakaoKeywords(resolvedSearchPlan, { includeWebQueries: false }),
      ...getPlannerList(kakaoKeywordCandidates),
      targetKeyword,
    ],
    resolvedSearchPlan,
  )
  const categoryHint = resolvedSearchPlan?.categoryHint || ''
  const isAncillaryIntent = resolvedSearchPlan?.isAncillaryIntent || false
  const requestedConditions = resolvedSearchPlan?.requestedConditions || []
  let kakaoPlaces = await runKakaoKeywordCandidateSearch(
    placesService,
    searchKeywords.length ? searchKeywords : [targetKeyword],
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
    fallbackKeyword: resolvedSearchPlan?.mainPlaceFallbackKeyword || '',
  })
  kakaoPlaces = filterPlacesByPlanExclusions(kakaoPlaces, resolvedSearchPlan)

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
      searchPlan: resolvedSearchPlan,
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
      .map((candidate) => scoreBaseLocationCandidate(candidate, baseKeyword, mapCenter.value)),
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
  return getResolvedSearchPlanLocationQuery(searchPlan)
}

const shouldResolveBaseLocation = (plan = {}, response = null) => {
  const responsePlan = response?.search_plan || plan?.conversationalSearchPlan?.search_plan || {}
  const locationQuery = getPlannerText(
    getResolvedSearchPlanLocationQuery(responsePlan) ||
    getResolvedSearchPlanLocationQuery(plan),
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

const runAiMapSearchAtCenter = async ({
  placesService,
  geocoder = null,
  originalQuery,
  targetQuery,
  center,
  baseLabel,
  parsedIntent = null,
  extraAiPayload = {},
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
    originalQuery,
    lat: center.lat,
    lng: center.lng,
    limit: DB_SEARCH_RESULT_COUNT,
    searchPlan: parsedIntent,
    search_plan: parsedIntent,
    place_intent_frame: parsedIntent?.placeIntentFrame || parsedIntent?.place_intent_frame || {},
    target_objects: getFrameTargetObjects(parsedIntent || {}),
    candidate_place_types: parsedIntent?.candidatePlaceTypes || parsedIntent?.candidate_place_types || [],
    constraints: parsedIntent?.constraints || [],
    exclusions: parsedIntent?.exclusions || [],
    ranking_policy: getFrameRankingPolicy(parsedIntent || {}),
    ...extraAiPayload,
  })
  if (import.meta.env.DEV) {
    console.debug('[AI 추천 API 응답]', {
      query: originalQuery,
      targetQuery,
      executionMode: data?.execution_mode,
      planSource: data?.plan_source,
      relevantResultCount: data?.relevant_result_count,
      parserProvider: data?.ai_parse?.parser_provider,
      parserFallback: data?.ai_parse?.parser_fallback,
      aiFallbackReason: data?.ai_parse?.ai_fallback_reason || data?.ai_fallback_reason,
      candidateCounts: data?.debug_pipeline?.candidate_counts,
      dbSearchTerms: data?.debug_pipeline?.evidence_terms?.db_search_terms,
      rerankerStatus: data?.debug_pipeline?.reranker?.status,
      unresolvedCount: data?.debug_pipeline?.unresolved_count,
      totalLatencyMs: data?.debug_pipeline?.total_latency_ms,
      locationResolution: data?.debug_pipeline?.location_resolution,
      searchOrigin: data?.debug_pipeline?.search_origin,
      backendMarkers: toArray(data?.markers).map((marker) => ({
        id: marker.id,
        source: marker.source,
        rank: marker.rank,
        lat: marker.lat,
        lng: marker.lng,
      })),
      locationMode: getFrameLocationMode(data?.place_intent_frame ? { place_intent_frame: data.place_intent_frame } : parsedIntent),
      anchorLocation: getFrameAnchorLocation(data?.place_intent_frame ? { place_intent_frame: data.place_intent_frame } : parsedIntent),
      locationQuery: parsedIntent?.locationQuery || parsedIntent?.location_query || '',
    })
  }
  const backendSearchPlan = data?.search_plan || data?.ai_parse?.search_plan || parsedIntent || {}
  const backendAction = data?.decision_action || data?.decisionAction || data?.ai_parse?.decision_action || ''
  const backendIsAiFirst = isBackendAiFirstResponse(data, parsedIntent)
  if (backendIsAiFirst && (!backendAction || backendAction === 'search')) {
    applyBackendAiSearchOrigin(data, center, baseLabel)
  }
  activeSearchPlan.value = backendSearchPlan
  const resultScenarioLabel = getFrameDisplayLabel(backendSearchPlan) ||
    getIntentGroupDisplayLabel(backendSearchPlan?.intentGroup || backendSearchPlan?.intent_group || '') ||
    getScenarioDisplayLabel(data?.scenario || recommendationIntent)

  mapAiParse.value = {
    ...(data.ai_parse || {
    parser_provider: data.parser_provider || '',
    parser_fallback: data.parser_fallback ?? false,
    execution_mode: data.execution_mode || '',
    plan_source: data.plan_source || '',
    place_intent_frame: data.place_intent_frame || {},
    ai_fallback_reason: data.ai_fallback_reason || '',
    }),
    parser_provider: backendIsAiFirst
      ? (data.ai_parse?.parser_provider || 'ai_intent_planner')
      : (data.ai_parse?.parser_provider || data.parser_provider || ''),
    parser_fallback: backendIsAiFirst ? false : (data.ai_parse?.parser_fallback ?? data.parser_fallback ?? false),
    execution_mode: backendIsAiFirst
      ? (data.ai_parse?.execution_mode || data.execution_mode || 'ai_first_orchestrator')
      : (data.ai_parse?.execution_mode || data.execution_mode || ''),
    ai_fallback_reason: backendIsAiFirst ? '' : (data.ai_parse?.ai_fallback_reason || data.ai_fallback_reason || ''),
    fallback_reason: backendIsAiFirst ? '' : (data.ai_parse?.fallback_reason || data.fallback_reason || ''),
  }

  if (backendAction && backendAction !== 'search') {
    clearSearchResults()
    searchResultStatus.value = backendAction === 'ask_clarification' ? 'idle' : 'error'
    selectedPlace.value = null
    showDetailPanel.value = false
    detailFrameError.value = false
    locationMessage.value = data.clarification_question ||
      data.message ||
      data.ai_parse?.user_message ||
      '요청하신 목적과 장소 추천을 연결하기 어려웠습니다.'
    const decisionPlan = {
      ...data,
      action: backendAction,
      search_plan: backendSearchPlan,
      clarification_question: data.clarification_question || '',
      clarification_options: data.clarification_options || [],
    }
    if (backendAction === 'ask_clarification') {
      setClarificationThread(originalQuery, decisionPlan, locationMessage.value)
    } else {
      setDecisionConversationThread(originalQuery, decisionPlan, locationMessage.value, backendAction)
      clearPendingClarification({ preserveMessages: true })
    }
    return
  }

  if (data.blocked || data.ai_parse?.blocked || data.ai_parse?.is_searchable === false) {
    clearSearchResults()
    searchResultStatus.value = 'error'
    selectedPlace.value = null
    showDetailPanel.value = false
    detailFrameError.value = false
    locationMessage.value = data.message || data.ai_parse?.user_message || '요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.'
    return
  }

  const dbResults = Array.isArray(data.results) ? data.results : []
  const useUnifiedBackendOrder = Boolean(data.unified_candidate_pipeline || data.frontend_should_preserve_order)
  const shouldSkipFrontendFallback = Boolean(data.frontend_should_skip_kakao_fallback || useUnifiedBackendOrder)
  preserveBackendResultOrder.value = useUnifiedBackendOrder
  if (useUnifiedBackendOrder) {
    fallbackResults.value = []
  }
  const rawRecommendationResults = convertRecommendationPlaces(dbResults, {
    preferredTags,
    recommendationIntent: getRecommendationIntentForScoring(recommendationIntent, backendSearchPlan || {}),
    requestedConditions,
    searchPlan: backendSearchPlan,
    getKakaoDetailUrl,
  })
  const frameDirectMatchCount = getFrameDirectMatchCount(rawRecommendationResults, backendSearchPlan || {})
  const recommendationResults = useUnifiedBackendOrder
    ? rawRecommendationResults
    : filterFrameDirectMatchedResults(rawRecommendationResults, backendSearchPlan || {})
  const backendExternalResultCount = recommendationResults.filter((place) => place.isExternal).length
  const backendDbResultCount = Math.max(recommendationResults.length - backendExternalResultCount, 0)
  const relevantDbResultCount = Number(
    data.external_search_triggered
      ? backendDbResultCount
      : (data.relevant_result_count ?? frameDirectMatchCount ?? backendDbResultCount),
  )
  const backendCandidateSourceCounts = data?.candidate_source_counts || data?.candidateSourceCounts || {}
  if (backendIsAiFirst) {
    const backendSearchLogCondition = getRecommendationConditionData(data)
    const backendSearchLogPlan = {
      ...(parsedIntent || {}),
      ...(backendSearchPlan || {}),
    }

    fallbackResults.value = []
    resultFilterMode.value = 'all'
    visibleCount.value = DISPLAY_BATCH_SIZE
    activeResultView.value = 'results'
    isResultListCollapsed.value = false
    resultSourceLabel.value = 'AI 검색 결과'
    resultMessageSuffix.value = getBackendResultMessageSuffix({
      dbCount: backendDbResultCount,
      externalCount: backendExternalResultCount,
      scenarioLabel: resultScenarioLabel,
    })
    placeListItemRefs.value = {}
    selectedPlace.value = null
    showDetailPanel.value = false
    detailFrameError.value = false

    if (recommendationResults.length) {
      setMainResults(recommendationResults)
      searchResultStatus.value = 'success'
      clearMainSearchErrorState()
      mapFitBoundsKey.value += 1
      locationMessage.value = data.message ||
        `${baseLabel} "${originalQuery}" 조건에 맞는 장소를 정리했어요.`
    } else {
      mainResults.value = []
      fallbackResults.value = []
      webReferenceResults.value = []
      syncLegacySearchResults()
      searchResultStatus.value = data.decision_action === 'ai_unavailable' ? 'error' : 'empty'
      locationMessage.value = data.message ||
        data.clarification_question ||
        `"${originalQuery}" 조건에 맞는 장소를 찾지 못했어요.`
    }
    loadingMessage.value = ''
    isSearchingMap.value = false
    await saveSearchLogSilently(buildSearchLogPayload({
      query: originalQuery,
      searchMode: parsedIntent?.searchMode || backendSearchPlan?.searchMode || 'recommendation_query',
      scenario: data.scenario,
      baseLabel,
      center,
      searchPlan: backendSearchLogPlan,
      condition: backendSearchLogCondition,
      results: recommendationResults,
      dbResultCount: backendCandidateSourceCounts.db ?? backendDbResultCount,
      kakaoResultCount: backendCandidateSourceCounts.kakao ?? backendExternalResultCount,
      aiWebResultCount: backendCandidateSourceCounts.web ?? 0,
    }))
    await logSearchResultState()
    return
  }

  if (recommendationResults.length) {
    setMainResults(recommendationResults)
    resultFilterMode.value = 'all'
    visibleCount.value = DISPLAY_BATCH_SIZE
    resultSourceLabel.value = 'AI 검색 결과'
    resultMessageSuffix.value = useUnifiedBackendOrder
      ? getBackendResultMessageSuffix({
        dbCount: backendDbResultCount,
        externalCount: backendExternalResultCount,
        scenarioLabel: resultScenarioLabel,
      })
      : backendExternalResultCount
      ? getBackendResultMessageSuffix({
        dbCount: backendDbResultCount,
        externalCount: backendExternalResultCount,
        scenarioLabel: resultScenarioLabel,
        unifiedOrder: false,
      })
      : getBackendResultMessageSuffix({
        dbCount: backendDbResultCount,
        scenarioLabel: resultScenarioLabel,
        unifiedOrder: false,
      })
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
  const shouldRunFallback = false
  kakaoFallbackQueries = []

  if (import.meta.env.DEV && menuSearchProfile.menuIntent) {
    console.debug('[메뉴 fallback 진입]', {
      query: targetQuery,
      scenario: data.scenario,
      isMenuSearch: menuSearchProfile.menuIntent,
      menuKeywords: menuSearchProfile.menuKeywords,
      placeTypeKeywords: menuSearchProfile.placeTypeKeywords,
      dbCount: backendDbResultCount,
      backendExternalResultCount,
      dbCategoryFallbackCount,
      directMenuMatchCount: directMenuDbMatchCount,
      shouldRunKakaoFallback: shouldRunFallback,
    })
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
        relevant_result_count: 0,
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
  resultMessageSuffix.value = useUnifiedBackendOrder
    ? getBackendResultMessageSuffix({
      dbCount: backendDbResultCount,
      externalCount: backendExternalResultCount,
      scenarioLabel: resultScenarioLabel,
    })
    : getBackendResultMessageSuffix({
      dbCount: backendDbResultCount,
      externalCount: backendExternalResultCount,
      kakaoCount: kakaoResults.length,
      scenarioLabel: resultScenarioLabel,
      unifiedOrder: false,
    })
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
      db_count: isFrameDrivenSearch(parsedIntent || {})
        ? relevantDbResultCount
        : (menuSearchProfile.menuIntent ? Math.min(directMenuDbMatchCount, backendDbResultCount) : backendDbResultCount),
      relevant_result_count: relevantDbResultCount,
      raw_db_count: backendDbResultCount,
      backend_external_count: backendExternalResultCount,
      kakao_fallback_count: kakaoResults.length,
      total_count: (
        isFrameDrivenSearch(parsedIntent || {})
          ? relevantDbResultCount
          : (menuSearchProfile.menuIntent ? Math.min(directMenuDbMatchCount, backendDbResultCount) : backendDbResultCount)
      ) + backendExternalResultCount + kakaoResults.length,
      raw_total_count: finalResults.length,
      direct_match_count: isFrameDrivenSearch(parsedIntent || {})
        ? frameDirectMatchCount
        : directMenuDbMatchCount,
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
  const externalMergeText = useUnifiedBackendOrder
    ? '저장 장소와 참고 정보를 함께 비교해 정리했어요.'
    : backendExternalResultCount
    ? '저장 장소가 부족해 참고 정보도 함께 보여드려요.'
    : (kakaoResults.length ? '저장 장소가 부족해 카카오 결과도 함께 보여드려요.' : '저장된 장소를 중심으로 정리했어요.')
  locationMessage.value = intentSummaryMessage
    ? `${intentSummaryMessage} ${externalMergeText}`
    : (
      useUnifiedBackendOrder
        ? `${baseLabel} "${originalQuery}" 조건에 맞는 장소와 참고 정보를 함께 정리했어요.`
        : backendExternalResultCount
        ? `${baseLabel} "${originalQuery}" 저장 장소가 부족해 참고 정보도 함께 보여드려요.`
        : kakaoResults.length
        ? `${baseLabel} "${originalQuery}" 저장 장소가 부족해 카카오 결과도 함께 보여드려요.`
        : `${baseLabel} "${originalQuery}" 조건에 맞는 저장 장소를 정리했어요.`
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
  const frameSearchKeywords = applyLocationToSearchKeywords(
    locationQuery,
    [
      ...buildFrameBasedKakaoKeywords(parsedIntent || {}, { includeWebQueries: false }),
      ...getFrameWebSearchQueries(parsedIntent || {}),
    ],
  )
  const searchKeywords = filterKeywordsByExclusions(
    [
      ...frameSearchKeywords,
      `${locationQuery} ${targetQuery}`.trim(),
      ...applyLocationToSearchKeywords(locationQuery, getPlannerList(parsedIntent?.kakaoKeywordCandidates)),
      `${locationQuery} ${categoryKeyword}`.trim(),
    ],
    parsedIntent || {},
  ).filter((keyword, index, keywords) => keyword && keywords.indexOf(keyword) === index)
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
  kakaoPlaces = filterPlacesByPlanExclusions(kakaoPlaces, parsedIntent || {})

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
    searchPlan: parsedIntent,
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

const searchKakaoPlaces = async ({ useMapBounds = false, searchPlanOverride = null } = {}) => {
  const keyword = mapSearchKeyword.value.trim()

  if (!keyword) {
    alert('지도에서 검색할 키워드를 입력해주세요.')
    return
  }

  try {
    await waitForKakaoServices()
  } catch (error) {
    handleKakaoMapLoadError(error)
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
        searchPlan: parsedKeyword,
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
        searchPlan: parsedKeyword,
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
      searchPlan: parsedKeyword,
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

  try {
    await waitForKakaoServices()
  } catch (error) {
    handleKakaoMapLoadError(error)
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
          searchPlan: resolvedParsedQuery,
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
  isSearchingMap.value = true
  loadingMessage.value = '검색 의도 해석 중'
  searchResultStatus.value = 'loading'
  const previousContext = getConversationalPreviousContext()
  const pendingClarificationForFollowUp = !useMapBounds && pendingClarification.value
    ? {
      ...pendingClarification.value,
      partial_search_plan: {
        ...(pendingClarification.value.partial_search_plan || {}),
      },
    }
    : null
  const previousMainResults = [...mainResults.value]
  const previousFallbackResults = [...fallbackResults.value]
  const previousWebReferenceResults = [...webReferenceResults.value]
  const clarificationFollowUpPayload = pendingClarificationForFollowUp
    ? buildClarificationFollowUpPayload(pendingClarificationForFollowUp, keyword)
    : {}
  beginMainSearch({
    preserveClarificationThread: Boolean(pendingClarificationForFollowUp),
  })

  if (!useMapBounds) {
    try {
      await waitForKakaoServices()
    } catch (error) {
      handleKakaoMapLoadError(error)
      return
    }

    if (pendingClarificationForFollowUp) {
      appendClarificationAnswerMessage(keyword)
    }

    const placesService = new window.kakao.maps.services.Places()
    const geocoder = new window.kakao.maps.services.Geocoder()
    const currentContext = await getSearchCenterForRecommendation()
    const backendOnlyPlan = {
      originalQuery: keyword,
      targetQuery: keyword,
      targetKeyword: keyword,
      searchMode: 'recommendation_query',
      recommendationIntent: '',
      backendAiOnly: true,
      parser_provider: 'backend_ai_only',
      parser_fallback: false,
      plan_source: 'ai',
      kakaoKeywordCandidates: [],
    }

    await runAiMapSearchAtCenter({
      placesService,
      geocoder,
      originalQuery: keyword,
      targetQuery: keyword,
      center: currentContext.center,
      baseLabel: currentContext.baseLabel,
      parsedIntent: backendOnlyPlan,
      extraAiPayload: {
        previousContext,
        previous_context: previousContext,
        previous_search_context: previousContext,
        ...clarificationFollowUpPayload,
      },
    })

    if (pendingClarificationForFollowUp && displayResults.value.length) {
      appendSearchSummaryMessage(locationMessage.value || resultCountText.value)
    }
    if (!baseLocationCandidates.value.length) {
      isSearchingMap.value = false
      loadingMessage.value = ''
      searchResultStatus.value = displayResults.value.length ? 'success' : searchResultStatus.value
    }
    return
  }

  let conversationalPlan = useMapBounds
    ? null
    : await resolveConversationalSearchPlan(keyword, previousContext, clarificationFollowUpPayload)

  if (pendingClarificationForFollowUp) {
    appendClarificationAnswerMessage(keyword)
  } else if (shouldAskLocationChoiceBeforeSearch({
    conversationalPlan,
    rawQuery: keyword,
    allowImplicitCurrentContext,
  })) {
    conversationalPlan = makeLocationChoiceClarificationPlan(conversationalPlan, keyword)
  }

  if (pendingClarificationForFollowUp && !conversationalPlan) {
    conversationalPlan = {
      action: 'ask_clarification',
      decision_action: 'ask_clarification',
      needs_clarification: true,
      can_search_now: false,
      message: '이전 질문에 대한 답변을 해석하지 못했습니다. 목적과 지역을 함께 다시 입력해 주세요.',
      clarification_question: '어떤 목적의 장소를 어느 지역 기준으로 찾으시나요?',
      clarification_options: [],
      search_plan: pendingClarificationForFollowUp.partial_search_plan || {},
      execution_policy: {
        run_search: false,
        allow_kakao_fallback: false,
      },
      parser_provider: 'frontend',
      parser_fallback: false,
      execution_mode: 'decision_gate',
      plan_source: 'backend_followup_unavailable',
    }
  }

  if (
    conversationalPlan?.action &&
    conversationalPlan.action !== 'search'
  ) {
    if (
      conversationalPlan.action === 'refine_previous_search' && previousContext
    ) {
      mainResults.value = previousMainResults
      fallbackResults.value = previousFallbackResults
      webReferenceResults.value = previousWebReferenceResults
      syncLegacySearchResults()
    } else {
      mainResults.value = []
      fallbackResults.value = []
      webReferenceResults.value = []
      syncLegacySearchResults()
      resultFilterMode.value = 'all'
      visibleCount.value = DISPLAY_BATCH_SIZE
      selectedPlace.value = null
      showDetailPanel.value = false
      detailFrameError.value = false
      isPlaceDetailCollapsed.value = false
      resetAiWebSearchState()
    }

    activeSearchPlan.value = adaptConversationalSearchPlan(conversationalPlan, keyword)
    mapAiParse.value = {
      parser_provider: conversationalPlan.parser_provider || '',
      parser_fallback: conversationalPlan.parser_fallback ?? null,
      execution_mode: conversationalPlan.execution_mode || '',
      plan_source: conversationalPlan.plan_source || '',
      ai_fallback_reason: conversationalPlan.ai_fallback_reason || '',
      fallback_reason: conversationalPlan.fallback_reason || '',
      place_intent_frame: conversationalPlan.search_plan?.place_intent_frame || {},
    }
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
      setDecisionConversationThread(keyword, conversationalPlan, locationMessage.value, conversationalPlan.action)
      clearPendingClarification({ preserveMessages: true })
    }
    searchResultStatus.value = displayResults.value.length ? 'success' : 'idle'
    loadingMessage.value = ''
    isSearchingMap.value = false
    return
  }

  clearPendingClarification({
    preserveMessages: Boolean(pendingClarificationForFollowUp),
  })
  const parsedKeyword = useMapBounds
    ? cloneSearchPlanForMapCenter(activeSearchPlan.value || {}, keyword)
    : conversationalPlan
      ? adaptConversationalSearchPlan(conversationalPlan, keyword)
      : buildSearchPlan(keyword)
  activeSearchPlan.value = parsedKeyword
  const searchMode = getUnifiedSearchMode(keyword, parsedKeyword, { useMapBounds })

  if (['region_search', 'recommendation_query'].includes(searchMode)) {
    sortMode.value = parsedKeyword.recommendationIntent
      ? 'recommendation'
      : 'distance'
    aiSearchKeyword.value = keyword
    if (useMapBounds) {
      try {
        await waitForKakaoServices()
      } catch (error) {
        handleKakaoMapLoadError(error)
        return
      }

      const mapCenterLat = Number(mapCenter.value?.lat)
      const mapCenterLng = Number(mapCenter.value?.lng)
      const hasMapCenter = Number.isFinite(mapCenterLat) && Number.isFinite(mapCenterLng)
      const fallbackContext = hasMapCenter ? null : await getSearchCenterForRecommendation()
      const center = hasMapCenter
        ? { lat: mapCenterLat, lng: mapCenterLng }
        : fallbackContext.center
      const placesService = new window.kakao.maps.services.Places()
      const geocoder = new window.kakao.maps.services.Geocoder()

      await runAiMapSearchAtCenter({
        placesService,
        geocoder,
        originalQuery: keyword,
        targetQuery: parsedKeyword.targetQuery || parsedKeyword.targetKeyword || keyword,
        center,
        baseLabel: '현재 지도 화면 기준',
        parsedIntent: parsedKeyword,
      })

      if (pendingClarificationForFollowUp) {
        appendSearchSummaryMessage(locationMessage.value || resultCountText.value)
      }

      if (!baseLocationCandidates.value.length) {
        isSearchingMap.value = false
        loadingMessage.value = ''
        searchResultStatus.value = displayResults.value.length ? 'success' : searchResultStatus.value
      }
      return
    }
    await searchAiRecommendationsOnMap(parsedKeyword)
    if (pendingClarificationForFollowUp) {
      appendSearchSummaryMessage(locationMessage.value || resultCountText.value)
    }
    if (!baseLocationCandidates.value.length && loadingMessage.value === '검색 의도 해석 중') {
      isSearchingMap.value = false
      loadingMessage.value = ''
      searchResultStatus.value = displayResults.value.length ? 'success' : 'idle'
    }
    return
  }

  sortMode.value = 'distance'
  await searchKakaoPlaces({ useMapBounds, searchPlanOverride: parsedKeyword })
  if (pendingClarificationForFollowUp) {
    appendSearchSummaryMessage(locationMessage.value || resultCountText.value)
  }
  if (!baseLocationCandidates.value.length && loadingMessage.value === '검색 의도 해석 중') {
    isSearchingMap.value = false
    loadingMessage.value = ''
    searchResultStatus.value = displayResults.value.length ? 'success' : 'idle'
  }
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
  searchKeyword.value = ''
  mapSearchKeyword.value = query
  activeTab.value = 'search'
  activeResultView.value = 'results'
  isResultListCollapsed.value = false
  await nextTick()
  await performUnifiedMapSearch({ allowImplicitCurrentContext: true })
}

const searchCurrentMapView = () => {
  closePlaceCard()
  showDetailPanel.value = false
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
        searchPlan: pendingSearch.parsedIntent,
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
  hiddenMapMarkerPlaceId.value = null
  showDetailPanel.value = false
  detailFrameError.value = false
  isPlaceDetailDismissed.value = false
  isPlaceDetailCollapsed.value = false
  activeResultView.value = 'results'
  isResultListCollapsed.value = false
  clearSearchResults()
  window.dispatchEvent(new CustomEvent('place-marker-fetch-clear'))
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
  hiddenMapMarkerPlaceId.value = null
  showDetailPanel.value = false
  detailFrameError.value = false
  isPlaceDetailDismissed.value = false
  isPlaceDetailCollapsed.value = false
  activeTab.value = 'search'
  activeResultView.value = 'results'
  isResultListCollapsed.value = false
  clearSearchResults()
  window.dispatchEvent(new CustomEvent('place-marker-fetch-clear'))
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
  hiddenMapMarkerPlaceId.value = null

  window.dispatchEvent(new CustomEvent('place-marker-fetch', {
    detail: {
      placeId: place?.id,
      placeName: place?.name,
      markerLabel: place?.markerLabel,
      target,
    },
  }))
}

const handleMascotFetchArrived = (event) => {
  const arrivedPlaceId = event.detail?.placeId

  if (!arrivedPlaceId || !selectedPlace.value) return
  if (String(selectedPlace.value.id) !== String(arrivedPlaceId)) return

  hiddenMapMarkerPlaceId.value = arrivedPlaceId
}

const handleMascotFetchClick = (event) => {
  const clickedPlaceId = event.detail?.placeId

  if (!clickedPlaceId || !selectedPlace.value) return
  if (String(selectedPlace.value.id) !== String(clickedPlaceId)) return

  markerChoiceRequestKey.value += 1
}

const updateMascotFetchTarget = (place, target = null) => {
  if (!selectedPlace.value || String(selectedPlace.value.id) !== String(place?.id)) return

  window.dispatchEvent(new CustomEvent('place-marker-fetch-update', {
    detail: {
      placeId: place?.id,
      placeName: place?.name,
      markerLabel: place?.markerLabel,
      target,
    },
  }))
}

const selectPlace = (place, target = null) => {
  selectedPlace.value = place
  detailFrameError.value = false
  isPlaceDetailDismissed.value = false
  isPlaceDetailCollapsed.value = false
  dispatchMascotFetch(place, target)
}

const selectPlaceFromList = (place, event) => {
  if (selectedPlace.value && String(selectedPlace.value.id) === String(place?.id)) {
    if (isPlaceDetailDismissed.value) {
      detailFrameError.value = false
      isPlaceDetailDismissed.value = false
      isPlaceDetailCollapsed.value = false
      dispatchMascotFetch(place, getListMarkerTarget(event))
      return
    }

    closePlaceCard()
    return
  }

  selectedPlace.value = place
  detailFrameError.value = false
  isPlaceDetailDismissed.value = false
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
  hiddenMapMarkerPlaceId.value = null
  detailFrameError.value = false
  isPlaceDetailDismissed.value = false
  isPlaceDetailCollapsed.value = false
  window.dispatchEvent(new CustomEvent('place-marker-fetch-clear'))
}

const dismissPlaceDetailPanel = () => {
  detailFrameError.value = false
  isPlaceDetailDismissed.value = true
  isPlaceDetailCollapsed.value = false
}

const handleDetailFrameError = () => {
  detailFrameError.value = true
}

const dispatchSearchLoadingMascotState = (isSearching = false) => {
  window.dispatchEvent(new CustomEvent('search-loading-change', {
    detail: {
      isSearching: Boolean(isSearching),
      message: loadingMessage.value || '',
    },
  }))
}

watch(isSearchingMap, (isSearching) => {
  dispatchSearchLoadingMascotState(isSearching)
})

watch(loadingMessage, () => {
  if (isSearchingMap.value) {
    dispatchSearchLoadingMascotState(true)
  }
})

onMounted(() => {
  loadSavedPlaceKeys()
  window.addEventListener('place-marker-fetch-arrived', handleMascotFetchArrived)
  window.addEventListener('place-marker-fetch-click', handleMascotFetchClick)
})

onBeforeUnmount(() => {
  dispatchSearchLoadingMascotState(false)
  window.removeEventListener('place-marker-fetch-arrived', handleMascotFetchArrived)
  window.removeEventListener('place-marker-fetch-click', handleMascotFetchClick)
})
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

          <div
            v-if="clarificationOptions.length"
            class="clarification-options"
          >
            <button
              v-for="option in clarificationOptions"
              :key="`${getClarificationOptionLabel(option)}-${getClarificationOptionValue(option)}`"
              type="button"
              :disabled="isSearchingMap"
              @click="submitClarificationOption(option)"
            >
              {{ getClarificationOptionLabel(option) }}
            </button>
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
              placeholder="예: 쉬는 곳, 먹을 곳, 산책할 곳, 서면"
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
          v-if="activeTab === 'search' && shouldShowSearchMapContent && !isClarificationOnlyState"
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
        v-if="!isClarificationOnlyState && shouldShowSearchMapContent"
        class="map-content search-reveal-area"
        :class="{
          'has-result-list': shouldShowResultPanel,
          'has-selected-place': shouldShowPlaceDetailPanel,
          'is-list-collapsed': isResultListCollapsed,
          'is-result-focused': activeResultView === 'results',
          'is-map-focused': activeResultView === 'map',
        }"
      >
        <aside
          v-if="shouldShowResultPanel"
          class="place-list-panel"
          :class="{ 'is-collapsed': isResultListCollapsed }"
        >
          <div class="place-list-top">
            <div>
              <p class="place-list-label">검색 결과</p>
              <h2>{{ resultPanelTitle }}</h2>
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
                참고 링크 {{ aiWebSearchEvidenceCandidates.length }}개
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
            검색 결과
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
            :hidden-place-id="hiddenMapMarkerPlaceId"
            :choice-request-key="markerChoiceRequestKey"
            @center-change="handleMapViewportChange"
            @select-place="selectPlace"
            @marker-target-change="updateMascotFetchTarget"
          />
        </div>

        <aside
          v-if="shouldShowPlaceDetailPanel"
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
                aria-label="상세정보 닫기"
                @click="dismissPlaceDetailPanel"
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
                    {{ getSelectedPlaceDetailLabel(selectedPlace) }}
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
                  aria-label="상세정보 닫기"
                  @click="dismissPlaceDetailPanel"
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
                v-else-if="isWebEvidenceCandidateResult(selectedPlace)"
                class="db-summary-card web-evidence-summary-card"
              >
                <div>
                  <strong>웹에서 찾은 참고 정보입니다.</strong>
                  <p>장소명과 위치는 실제 방문 전에 한 번 더 확인해 주세요.</p>
                  <a
                    v-if="getWebEvidenceUrl(selectedPlace)"
                    :href="getWebEvidenceUrl(selectedPlace)"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    원문 열기
                  </a>
                </div>
              </section>

              <div class="info-list compact-info-list">
                <div v-if="isRecommendationPlace(selectedPlace)" class="recommendation-summary">
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

              </div>

              <div class="detail-action-row">
                <button
                  type="button"
                  class="detail-action-button save"
                  :disabled="savingPlaceId === selectedPlace.id || isPlaceSaved(selectedPlace)"
                  @click="handleSavePlace(selectedPlace)"
                >
                  {{ isPlaceSaved(selectedPlace) ? '저장됨' : (savingPlaceId === selectedPlace.id ? '저장 중' : '장소 저장') }}
                </button>

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
                  {{ getPlaceDetailActionText(selectedPlace) }}
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
              <p v-if="placeSaveMessage" class="place-save-message">{{ placeSaveMessage }}</p>
            </div>
        </aside>
      </div>
    </section>

  </main>
</template>

<style scoped src="@/styles/Homeview.css"></style>
