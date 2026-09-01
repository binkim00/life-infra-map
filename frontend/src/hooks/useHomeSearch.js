import { useCallback, useEffect, useReducer, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import {
  aiSearchCandidateRecommendations,
  aiSearchRecommendations,
  buildConversationalSearchPlan,
  checkSearchSafety,
  getKakaoPlaceTags,
  getSavedPlaces,
  runAiWebSearch,
  saveSearchLog,
  startNewConversationSession,
} from '@/api/recommendation'
import {
  AI_WEB_SEARCH_MIN_DB_RESULTS,
  AI_WEB_SEARCH_MIN_TOTAL_RESULTS,
  AI_WEB_SEARCH_SUFFICIENT_TOTAL_RESULTS,
  DB_MARKER_ALLOWED_CATEGORIES,
  DB_SEARCH_RESULT_COUNT,
  DEFAULT_CENTER,
  DISPLAY_BATCH_SIZE,
  KAKAO_DETAIL_LOOKUP_RADIUS_M,
  KAKAO_FALLBACK_MIN_RESULTS,
  MAX_VIEWPORT_SEARCH_RADIUS,
  MIN_VIEWPORT_SEARCH_RADIUS,
  SEARCH_RADIUS,
} from '@/constants/homeSearchConstants'
import { NO_RESULT_MESSAGE_PATTERNS } from '@/constants/homeViewUiConstants'
import { loadKakaoMapScript as waitForKakaoServices } from '@/hooks/useKakaoMapSdk'
import { useAuthStore } from '@/stores/auth'
import {
  dedupeAiWebSearchCandidates,
} from '@/utils/aiWebCandidateHelpers'
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
  buildBaseLocationSearchQueries,
  dedupeBaseLocationCandidates,
  getAutoSelectedBaseCandidate,
  normalizeKakaoBaseCandidate,
  scoreBaseLocationCandidate,
  sortBaseLocationCandidates,
} from '@/utils/homeBaseLocation'
import {
  buildFrameBasedKakaoKeywords,
  compareLowConfidenceFallback,
  filterKeywordsByExclusions,
  getClarificationOptionItems,
  getClarificationOptionValue,
  getConfidenceRank,
  getDirectMenuDbMatchCount,
  getDirectMenuMatchText,
  getDistanceMetersBetweenPlaces,
  getDistanceValue,
  getFrameAnchorLocation,
  getFrameCandidateCategoryCodes,
  getFrameCandidatePlaceTypes,
  getFrameConstraints,
  getFrameDisplayLabel,
  getFrameExclusions,
  getFrameLocationMode,
  getFrameRankingPolicy,
  getFrameResultMatchTerms,
  getFrameTargetObjects,
  getFrameWebSearchQueries,
  getIntentGroupDisplayLabel,
  getKakaoDetailLookupKey,
  getKakaoDetailPlaceCoordinates,
  getKakaoFallbackCandidateScore,
  getMenuSearchProfile,
  getPersonalizationBoost,
  getPlaceFrameMatchStrength,
  getPlaceScoreCapReasons,
  getPlanKakaoKeywordCandidates,
  getPlannerBoolean,
  getPlannerList,
  getPlannerText,
  getRecommendScore,
  getRecommendationConditionData,
  getRecommendationConfidence,
  getRecommendationIntentForScoring,
  getRecommendationMissingLabels,
  getRecommendationPreviewLabels,
  getResolvedSearchPlanLocationQuery,
  getResultSourceRank,
  getScenarioDisplayLabel,
  getSearchPlanDebugSnapshot,
  getSearchPlanFrame,
  getSearchPlanValue,
  getSpecificPlaceTypeTerms,
  getTextValue,
  getWebEvidenceUrl,
  hasNormalizedKeywordMatch,
  isBackendAiFirstResponse,
  isCafeSearchKeyword,
  isCategoryFallbackRecommendation,
  isDbPlace,
  isFrameDrivenSearch,
  isKakaoCandidateResult,
  isRecommendationPlace,
  isWebEvidenceCandidateResult,
  buildKakaoDetailLookupQueries,
  debugKakaoDetailLog,
  dedupeSearchResults,
  getBestKakaoDetailCandidate,
  getDirectKakaoDetailUrl,
  getDistanceText,
  getPlaceSourceText,
  getRecommendationFallbackText,
  normalizeLocationText,
  shouldAppendDbPlaces,
  shouldRewriteRecommendationReason,
  toDisplayList,
  applyLocationToSearchKeywords,
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
  isPlaceExcludedByPlan,
  isRecommendationQueryText,
  makeLocationChoiceClarificationPlan,
  mergeRequestedConditionReview,
  shouldAskLocationChoiceBeforeSearch,
  toArray,
} from '@/utils/homeSearchPlanning'
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
  reverseGeocodeLocationHint,
  runKakaoAddressSearch,
  runKakaoKeywordCandidateSearch,
  runKakaoKeywordSearchLimited,
} from '@/utils/kakaoSearchHelpers'
import {
  convertDbPlaces,
  convertRecommendationPlaces,
} from '@/utils/placeResultConverters'
import {
  getPlacesCenter,
  getRegionSearchCoreKeyword,
  groupKakaoPlacesByRegion,
  makeRegionCandidateFromGroup,
  shouldAskRegionCandidateSelection,
} from '@/utils/regionSearchHelpers'
import {
  buildAiWebSearchPlanPayload,
  buildSearchLogPayload,
  getAiWebSearchLocationHint,
  getSearchLogLocationHint,
} from '@/utils/searchPayloadBuilders'

import {
  canShowPlaceOnMap,
  createHomeSearchState,
  getDisplayResults,
  getFilteredSearchResults,
  getResultFilterLabel,
  getSearchedPlaces,
  isSearchErrorMessage,
} from './homeSearchState'

const IS_DEV = import.meta.env.DEV

// SDK 기본 오류 문구와 일치시킵니다.
const KAKAO_MAP_LOAD_ERROR_MESSAGE = '카카오맵 SDK를 불러오지 못했습니다.'

const normalizeTab = (tab) => (['search', 'map'].includes(tab) ? tab : 'search')

const toFiniteCoordinate = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

const isSameMapCenter = (firstCenter, secondCenter) => {
  if (!firstCenter || !secondCenter) return false

  return (
    Math.abs(Number(firstCenter.lat) - Number(secondCenter.lat)) < 0.000001
    && Math.abs(Number(firstCenter.lng) - Number(secondCenter.lng)) < 0.000001
  )
}

const formatSearchRadius = (radius) => {
  if (radius >= 1000) {
    return `${Number((radius / 1000).toFixed(1))}km`
  }

  return `${radius}m`
}

const requestBrowserLocation = () => new Promise((resolve, reject) => {
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

export const useHomeSearch = ({ initialTab = 'search' } = {}) => {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [, forceRender] = useReducer((version) => version + 1, 0)

  const stateRef = useRef(null)
  if (!stateRef.current) {
    stateRef.current = {
      ...createHomeSearchState(),
      activeTab: normalizeTab(initialTab),
    }
  }

  const s = stateRef.current
  const isMountedRef = useRef(true)
  const lastRouteAutoSearchKeyRef = useRef('')
  const placeListItemRefs = useRef({})

  const commit = useCallback(() => {
    if (!isMountedRef.current) return
    forceRender()
  }, [])

  useEffect(() => {
    isMountedRef.current = true

    return () => {
      isMountedRef.current = false
    }
  }, [])

  // ---------------------------------------------------------------- 파생 값

  const displayResults = () => getDisplayResults(s)
  const filteredSearchResults = () => getFilteredSearchResults(s)

  const syncLegacySearchResults = () => {
    s.allSearchResults = displayResults()
  }

  // ---------------------------------------------------------------- 정렬

  const isWeakFrameFallbackRecommendation = (place = {}) => {
    const frameMatchStrength = getPlaceFrameMatchStrength(place)
    const scoreCapReasons = getPlaceScoreCapReasons(place)

    return (
      frameMatchStrength === 'weak'
      || scoreCapReasons.includes('frame_weak_category_fallback')
      || scoreCapReasons.includes('category_fallback')
      || (
        isFrameDrivenSearch(s.activeSearchPlan || {})
        && isCategoryFallbackRecommendation(place)
      )
    )
  }

  const getFrameEvidenceSortRank = (place = {}) => {
    const searchPlan = s.activeSearchPlan || {}
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

  const getMenuDisplayMatchedLabels = (place = {}) => {
    const menuProfile = s.activeMenuSearchProfile
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

  const getRecommendationMatchedLabels = (place) => {
    const labels = toDisplayList(place?.matchedTagLabels || place?.matched_tag_labels)
    const baseLabels = labels.length ? labels : toDisplayList(place?.matchedTags || place?.matched_tags)
    const menuLabels = getMenuDisplayMatchedLabels(place)
    const conditionLabels = toDisplayList(place?.matchedConditions || place?.matched_conditions)

    return [...new Set([...conditionLabels, ...baseLabels, ...menuLabels])]
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

  const getMenuSearchSortRank = (place = {}) => {
    const menuProfile = s.activeMenuSearchProfile
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
      place.resultType === 'kakao_fallback_candidate'
      && (
        hasNormalizedKeywordMatch(fallbackQueryText, menuTerms)
        || hasNormalizedKeywordMatch(fallbackQueryText, strongPlaceTypeTerms)
      )
    )
    const hasTagMatch = (
      !isCategoryFallbackRecommendation(place)
      && (
        getRecommendationMatchedLabels(place).length > 0
        || (place.matchedTags || []).length > 0
        || ['db_verified', 'db_candidate'].includes(getTextValue(place.recommendationSourceType || place.source_type))
      )
    )
    const rawMatchedLabels = [
      ...toDisplayList(place.matchedTagLabels || place.matched_tag_labels),
      ...toDisplayList(place.matchedTags || place.matched_tags),
    ]
    const hasVerifiedMenuMatch = (
      hasMenuMatch
      && (
        rawMatchedLabels.length > 0
        || (place.matchedTags || []).length > 0
        || getTextValue(place.recommendationSourceType || place.source_type) === 'db_verified'
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
      firstDistance !== null
      && secondDistance !== null
      && firstDistance !== secondDistance
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

    const shapeDifference = ((secondPlace.mainPlaceScore || 0) - (secondPlace.ancillaryPlacePenalty || 0) - (secondPlace.intentMismatchPenalty || 0))
      - ((firstPlace.mainPlaceScore || 0) - (firstPlace.ancillaryPlacePenalty || 0) - (firstPlace.intentMismatchPenalty || 0))

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

    const scoreDifference = getRecommendationSortScore(secondPlace) - getRecommendationSortScore(firstPlace)

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

    const scoreDifference = getRecommendationSortScore(secondPlace) - getRecommendationSortScore(firstPlace)

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

      if (s.sortMode === 'recommendation') {
        return compareForRecommendationSearch(firstPlace, secondPlace)
      }

      if (s.sortMode === 'confidence') {
        return compareForConfidenceSearch(firstPlace, secondPlace)
      }

      return compareForGeneralSearch(firstPlace, secondPlace)
    })

    return sortedResults.map(({ originalOrder, ...place }) => place)
  }

  const searchedPlaces = () => getSearchedPlaces(s, sortSearchResults)

  const mapPlaces = () => [
    ...s.currentLocationPlace,
    ...searchedPlaces().filter((place) => canShowPlaceOnMap(place)),
  ]

  // ------------------------------------------------------- 상태 메시지 헬퍼

  const isNoResultLocationMessage = (message = '') => {
    return NO_RESULT_MESSAGE_PATTERNS.some((pattern) => String(message || '').includes(pattern))
  }

  const clearNoResultLocationMessage = () => {
    if (isNoResultLocationMessage(s.locationMessage)) {
      s.locationMessage = ''
    }
  }

  const resetSearchStatusMessage = (message = '검색 조건을 확인하는 중입니다.') => {
    s.locationMessage = message
  }

  const clearMainSearchErrorState = () => {
    s.searchErrorMessage = ''
    s.aiSearchError = ''

    if (isSearchErrorMessage(s.locationMessage)) {
      s.locationMessage = ''
    }
  }

  const setMainSearchError = (message) => {
    if (displayResults().length > 0) {
      s.searchResultStatus = 'success'
      clearMainSearchErrorState()
      return
    }

    const fallbackMessage = message || '검색 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'
    s.searchResultStatus = 'error'
    s.searchErrorMessage = fallbackMessage
    s.aiSearchError = fallbackMessage
    s.locationMessage = fallbackMessage
  }

  const setMainResults = (results = []) => {
    s.mainResults = Array.isArray(results) ? results : []
    syncLegacySearchResults()

    if (displayResults().length > 0) {
      s.searchResultStatus = 'success'
      clearMainSearchErrorState()
    }
  }

  const setFallbackResults = (results = []) => {
    s.fallbackResults = Array.isArray(results) ? results : []
    syncLegacySearchResults()

    if (displayResults().length > 0) {
      s.searchResultStatus = 'success'
      clearMainSearchErrorState()
    }
  }

  const logSearchResultState = async () => {
    if (!IS_DEV) return

    console.debug('[검색 결과 상태]', {
      mainCount: s.mainResults.length,
      fallbackCount: s.fallbackResults.length,
      displayCount: displayResults().length,
      webReferenceCount: s.webReferenceResults.length,
      status: s.searchResultStatus,
      errorMessage: s.searchErrorMessage,
      locationMessage: s.locationMessage,
    })
  }

  // --------------------------------------------------------- 대화형 상태

  const displayUserName = () => {
    const user = useAuthStore.getState().user || {}
    return user.profile?.nickname || user.nickname || user.username || '사용자'
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
      label: role === 'user' ? displayUserName() : 'AI',
      options: getPlannerList(options),
      plan,
      createdAt: new Date().toISOString(),
    }
  }

  const syncClarificationThreadFromMessages = () => {
    s.clarificationThread = s.conversationMessages.filter((message) => {
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
      plan?.fallback_reason
      || plan?.fallbackReason
      || plan?.ai_fallback_reason
      || plan?.aiFallbackReason,
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
      message
      || plan?.clarification_question
      || plan?.message
      || '지역과 목적을 함께 입력해 주세요.',
    ).trim()
    const partialSearchPlan = plan?.search_plan && typeof plan.search_plan === 'object'
      ? { ...plan.search_plan }
      : {}
    const partialFrame = getSearchPlanFrame(partialSearchPlan)
    const partialCandidatePlaceTypes = getFrameCandidatePlaceTypes(partialSearchPlan)
    const partialConstraints = getFrameConstraints(partialSearchPlan)
    const partialExclusions = getFrameExclusions(partialSearchPlan)
    const clarificationOptionItems = getClarificationOptionItems(
      plan?.clarification_options
      || plan?.clarificationOptions
      || partialFrame?.clarification_options
      || partialFrame?.clarificationOptions
      || [],
    )
    const partialConditions = [
      ...getPlannerList(
        getSearchPlanValue(partialSearchPlan, 'requestedConditions', 'requested_conditions', 'conditions')
        || plan?.conditions
        || [],
      ),
      ...partialConstraints,
    ].filter((condition, index, list) => condition && list.indexOf(condition) === index)

    s.pendingClarification = {
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
      clarification_options: clarificationOptionItems,
      clarificationOptions: clarificationOptionItems,
      message: assistantText,
    }
    s.conversationModeStarted = true
    s.followUpInput = ''
    s.searchKeyword = ''
    s.mapSearchKeyword = ''
    s.conversationMessages = trimConversationMessages([
      ...s.conversationMessages,
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
        options: clarificationOptionItems,
        plan,
      }),
    ])
    syncClarificationThreadFromMessages()
    commit()
  }

  const setDecisionConversationThread = (query, plan, message, type = 'out_of_scope') => {
    const userText = String(query || '').trim()
    const assistantText = String(message || plan?.message || '').trim()
    s.conversationMessages = trimConversationMessages([
      ...s.conversationMessages,
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
    commit()
  }

  const clearPendingClarification = ({ preserveMessages = false } = {}) => {
    s.pendingClarification = null
    if (!preserveMessages) {
      s.conversationMessages = []
    }
    syncClarificationThreadFromMessages()
    s.followUpInput = ''
  }

  const appendClarificationAnswerMessage = (answer = '') => {
    const text = String(answer || '').trim()
    if (!text) return

    s.conversationMessages = trimConversationMessages([
      ...s.conversationMessages,
      makeConversationMessage({
        role: 'user',
        type: 'clarification_answer',
        content: text,
      }),
    ])
    syncClarificationThreadFromMessages()
    commit()
  }

  const appendSearchSummaryMessage = (message = '') => {
    const text = String(message || '').trim()
    if (!text) return

    s.conversationMessages = trimConversationMessages([
      ...s.conversationMessages,
      makeConversationMessage({
        role: 'assistant',
        type: 'search_summary',
        content: text,
        plan: s.activeSearchPlan || null,
      }),
    ])
    syncClarificationThreadFromMessages()
    commit()
  }

  // ------------------------------------------------------------- 결과 세팅

  const resetAiWebSearchState = () => {
    s.aiWebSearchContext = null
    s.aiWebSearchAvailability = null
    s.aiWebSearchStatus = 'idle'
    s.aiWebSearchMessage = ''
    s.aiWebSearchCandidates = []
    s.webReferenceResults = []
    s.aiWebSearchLastResult = null
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
    s.activeMenuSearchProfile = null
    s.preserveBackendResultOrder = Boolean(preserveBackendOrder)
    s.mainResults = normalizedResults
    s.fallbackResults = []
    syncLegacySearchResults()
    s.resultFilterMode = 'all'
    s.visibleCount = DISPLAY_BATCH_SIZE
    s.searchResultStatus = displayResults().length ? 'success' : (status || 'empty')
    if (displayResults().length) {
      clearMainSearchErrorState()
    }
    s.resultSourceLabel = sourceLabel
    s.resultMessageSuffix = messageSuffix
    placeListItemRefs.current = {}
    s.mapFitBoundsKey += 1
    s.activeResultView = displayResults().length ? 'results' : s.activeResultView
    s.isResultListCollapsed = false

    if (displayResults().length > 0) {
      clearNoResultLocationMessage()
      if (isSearchErrorMessage(s.locationMessage)) {
        s.locationMessage = ''
      }
    }

    commit()
  }

  const clearSearchResults = () => {
    setSearchResults({
      results: [],
      sourceLabel: '검색 결과',
      messageSuffix: '',
    })
  }

  const beginMainSearch = ({ preserveClarificationThread = false } = {}) => {
    s.mainResults = []
    s.fallbackResults = []
    s.webReferenceResults = []
    s.preserveBackendResultOrder = false
    s.pendingClarification = null
    if (!preserveClarificationThread) {
      s.clarificationThread = []
    }
    s.baseLocationCandidates = []
    s.pendingBaseLocationSearch = null
    syncLegacySearchResults()
    s.searchResultStatus = 'loading'
    clearMainSearchErrorState()
    commit()
  }

  const handleKakaoMapLoadError = (error) => {
    console.error(error)
    s.baseLocationCandidates = []
    s.pendingBaseLocationSearch = null
    s.selectedPlace = null
    s.showDetailPanel = false
    s.detailFrameError = false
    s.isSearchingMap = false
    s.loadingMessage = ''
    setMainSearchError(KAKAO_MAP_LOAD_ERROR_MESSAGE)
    commit()
  }

  // ------------------------------------------------------- 카카오 상세 URL

  const getResolvedKakaoDetailUrl = (place) => {
    const lookupKey = getKakaoDetailLookupKey(place)
    return lookupKey ? s.resolvedKakaoDetailUrls[lookupKey] || '' : ''
  }

  const getKakaoDetailUrl = (place) => {
    return getDirectKakaoDetailUrl(place) || getResolvedKakaoDetailUrl(place)
  }

  const shouldLookupKakaoDetailUrl = (place) => {
    if (!isDbPlace(place) || getDirectKakaoDetailUrl(place)) {
      return false
    }

    const lookupKey = getKakaoDetailLookupKey(place)
    if (!lookupKey || s.resolvedKakaoDetailUrls[lookupKey]) {
      return false
    }

    const status = s.kakaoDetailLookupStatus[lookupKey]
    if (['loading', 'success', 'failed'].includes(status)) {
      return false
    }

    return Boolean(
      buildKakaoDetailLookupQueries(place).length
      && getKakaoDetailPlaceCoordinates(place),
    )
  }

  const resolveKakaoDetailUrlForPlace = async (place) => {
    if (!shouldLookupKakaoDetailUrl(place)) {
      return
    }

    if (!window.kakao?.maps?.services) {
      return
    }

    const lookupKey = getKakaoDetailLookupKey(place)
    const placeCoordinates = getKakaoDetailPlaceCoordinates(place)
    const lookupQueries = buildKakaoDetailLookupQueries(place)

    s.kakaoDetailLookupStatus = {
      ...s.kakaoDetailLookupStatus,
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
        // eslint-disable-next-line no-await-in-loop
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
        s.kakaoDetailLookupStatus = {
          ...s.kakaoDetailLookupStatus,
          [lookupKey]: 'failed',
        }
        debugKakaoDetailLog('[카카오 상세 매칭 결과]', {
          success: false,
          dbPlaceName: place?.name,
          lookupQueries,
          reason: 'no_reliable_candidate',
        })
        commit()
        return
      }

      s.resolvedKakaoDetailUrls = {
        ...s.resolvedKakaoDetailUrls,
        [lookupKey]: matchedCandidate.url,
      }
      s.kakaoDetailLookupStatus = {
        ...s.kakaoDetailLookupStatus,
        [lookupKey]: 'success',
      }

      if (s.selectedPlace && getKakaoDetailLookupKey(s.selectedPlace) === lookupKey) {
        s.detailFrameError = false
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
      commit()
    } catch (error) {
      s.kakaoDetailLookupStatus = {
        ...s.kakaoDetailLookupStatus,
        [lookupKey]: 'failed',
      }
      debugKakaoDetailLog('[카카오 상세 매칭 결과]', {
        success: false,
        dbPlaceName: place?.name,
        lookupQueries,
        reason: error?.message || 'lookup_error',
      })
      commit()
    }
  }

  // ------------------------------------------------------------ 장소 링크

  const getCurrentLocationNavigationOrigin = () => {
    const currentPlace = s.currentLocationPlace.find((place) => {
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
      isWebEvidenceCandidateResult(place)
      || place?.canShowOnMap === false
      || place?.can_show_on_map === false
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
      place?.navigationUrl
      || place?.navigation_url
      || `https://map.kakao.com/link/to/${destinationName},${destinationLat},${destinationLng}`
    )
  }

  const getPlaceDetailUrl = (place) => {
    if (isWebEvidenceCandidateResult(place)) {
      return getWebEvidenceUrl(place)
    }

    return getKakaoDetailUrl(place)
  }

  const hasKakaoDetail = (place) => Boolean(getKakaoDetailUrl(place))

  // ------------------------------------------------------------ 추천 문구

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
    const needsVerification = getRecommendationConfidence(place) === 'low'
      || isKakaoCandidateResult(place)
      || isWebEvidenceCandidateResult(place)

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

  // ------------------------------------------------------------ AI 웹 검색

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

  const getAiWebSearchLowConfidenceCount = (results = []) => results.filter((place) => {
    const confidence = getTextValue(
      place?.recommendationConfidence
      || place?.confidence
      || getRecommendationConfidence(place),
    ).toLowerCase()
    return confidence === 'low'
  }).length

  const getAiWebSearchStrongEvidenceCount = (results = []) => (
    results.filter((place) => hasAiWebSearchStrongEvidence(place)).length
  )

  const shouldSuggestAiWebSearch = () => {
    const context = s.aiWebSearchContext
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
    const explicitRequest = Boolean(summary.explicit_web_request)
      || hasExplicitAiWebSearchRequest(context.query, context.condition, searchPlan)
    const infraTopic = Boolean(summary.infra_blocked_topic)
      || isAiWebSearchInfraBlockedTopic(context.query, context.condition, searchPlan)
    const helpfulTopic = Boolean(summary.web_helpful_topic)
      || isAiWebSearchHelpfulTopic(context.query, context.condition, searchPlan)

    if (
      infraTopic
      && !explicitRequest
      && strongEvidenceCount > 0
      && totalCount >= AI_WEB_SEARCH_MIN_TOTAL_RESULTS
      && lowConfidenceCount < Math.max(1, Math.ceil(totalCount / 2))
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
      strongEvidenceCount > 0
      && dbCount >= AI_WEB_SEARCH_MIN_DB_RESULTS
      && totalCount >= AI_WEB_SEARCH_MIN_TOTAL_RESULTS
      && lowConfidenceCount < Math.max(1, Math.ceil(totalCount / 2))
    ) {
      return false
    }

    const lacksEnoughResults = (
      totalCount === 0
      || dbCount < AI_WEB_SEARCH_MIN_DB_RESULTS
      || (menuIntent && directMatchCount < KAKAO_FALLBACK_MIN_RESULTS)
    )
    const kakaoOnlyOrWeak = kakaoFallbackCount > 0 && strongEvidenceCount === 0
    const lowQualityMajority = totalCount > 0 && (
      lowConfidenceCount >= Math.max(1, Math.ceil(totalCount / 2))
      || weakMatchCount >= Math.max(1, Math.ceil(totalCount / 2))
    )

    return (
      lacksEnoughResults
      || kakaoOnlyOrWeak
      || lowQualityMajority
      || (hasAiWebSearchDetailCondition(context.query, context.condition, searchPlan) && strongEvidenceCount === 0)
    )
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
    s.aiWebSearchContext = {
      query,
      lat: center?.lat ?? null,
      lng: center?.lng ?? null,
      locationHint,
      searchPlan: searchPlan || {},
      condition: condition || {},
      existingResultsSummary: existingResultsSummary || {},
    }
    s.aiWebSearchAvailability = aiWebSearchStatusData || {
      enabled: false,
      supported: false,
    }
    s.aiWebSearchStatus = 'idle'
    s.aiWebSearchMessage = ''
    s.aiWebSearchCandidates = []
    s.webReferenceResults = []
    s.aiWebSearchLastResult = null

    if (IS_DEV) {
      console.debug('[AI 웹 검색 context]', getSearchPlanDebugSnapshot(s.aiWebSearchContext.searchPlan, {
        rawQuery: query,
        locationHint,
      }))
    }

    commit()
  }

  const applyAiWebSearchResult = (aiWebSearch = {}) => {
    const candidates = Array.isArray(aiWebSearch.candidates)
      ? dedupeAiWebSearchCandidates(aiWebSearch.candidates)
      : []
    s.aiWebSearchLastResult = aiWebSearch
    const hasMainResults = displayResults().length > 0

    if (!aiWebSearch.enabled || !aiWebSearch.supported) {
      s.aiWebSearchStatus = 'disabled'
      s.aiWebSearchCandidates = []
      s.webReferenceResults = []
      s.aiWebSearchMessage = getAiWebSearchStatusMessage(aiWebSearch)
      commit()
      return
    }

    if (aiWebSearch.reason === 'manual_required') {
      s.aiWebSearchStatus = 'idle'
      s.aiWebSearchCandidates = []
      s.webReferenceResults = []
      s.aiWebSearchMessage = ''
      commit()
      return
    }

    if (aiWebSearch.error === 'incomplete_response') {
      s.aiWebSearchStatus = 'empty'
      s.aiWebSearchCandidates = []
      s.webReferenceResults = []
      s.aiWebSearchMessage = getAiWebSearchStatusMessage(aiWebSearch)
      commit()
      return
    }

    if (aiWebSearch.error && !candidates.length) {
      s.aiWebSearchStatus = hasMainResults ? 'empty' : 'error'
      s.aiWebSearchCandidates = []
      s.webReferenceResults = []
      s.aiWebSearchMessage = hasMainResults ? '' : getAiWebSearchStatusMessage(aiWebSearch)
      commit()
      return
    }

    s.aiWebSearchCandidates = candidates
    s.webReferenceResults = candidates
    s.aiWebSearchStatus = candidates.length ? 'success' : 'empty'
    s.aiWebSearchMessage = getAiWebSearchStatusMessage(aiWebSearch)
    commit()
  }

  const searchAiWebCandidatesManually = async () => {
    const context = s.aiWebSearchContext
    if (!context || s.aiWebSearchStatus === 'loading') return

    if (!s.aiWebSearchAvailability?.enabled || !s.aiWebSearchAvailability?.supported) {
      applyAiWebSearchResult({
        ...(s.aiWebSearchAvailability || {}),
        candidates: [],
      })
      return
    }

    const requestKey = getAiWebSearchRequestKey(context)
    const cachedResult = s.aiWebSearchClientCache[requestKey]
    if (cachedResult) {
      if (IS_DEV) {
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

    s.aiWebSearchStatus = 'loading'
    s.aiWebSearchMessage = 'AI 웹 검색 중입니다...'
    s.aiWebSearchLastResult = null
    commit()

    if (IS_DEV) {
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
      s.aiWebSearchClientCache = {
        ...s.aiWebSearchClientCache,
        [requestKey]: aiWebSearch,
      }
      if (IS_DEV) {
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
      s.aiWebSearchCandidates = []
      s.webReferenceResults = []
      if (displayResults().length) {
        s.aiWebSearchStatus = 'empty'
        s.aiWebSearchMessage = ''
        commit()
        return
      }

      s.aiWebSearchStatus = 'error'
      s.aiWebSearchMessage = 'AI 웹 검색 중 오류가 발생했습니다.'
      commit()
    }
  }

  // ------------------------------------------------------------ 검색 기록

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
    s.searchLogSaveState = { status, message, statusCode }
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
      if (useAuthStore.getState().isLoggedIn) {
        const message = '로그인 상태지만 인증 토큰이 없어 검색 기록 저장을 건너뛰었습니다.'
        setSearchLogSaveState({ status: 'failed', message })
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

      setSearchLogSaveState({ status: 'failed', message, statusCode })
      console.warn('[SearchLog] save failed', {
        status: statusCode || 'request_failed',
        responseData: error?.response?.data || null,
        payload,
      })
      return { status: 'failed', statusCode, error }
    }
  }

  // --------------------------------------------------------- 카카오 변환

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
              recommendationData.recommendScore
              ?? rawScores.recommendation_ready_score
              ?? savedTagData.data_quality_score
              ?? null
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

  // --------------------------------------------------------- 위치/지도 기준

  const makeCurrentLocationMarker = ({ lat, lng }) => ({
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
  })

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
      searchOrigin.location_mode
      || getFrameLocationMode(data?.search_plan || data?.place_intent_frame || {}),
    )
    const isCurrentContext = locationMode === 'current_context' || source.includes('current')
    const label = getTextValue(locationResolution.label || searchOrigin.label || fallbackLabel)
    const markerName = isCurrentContext
      ? '현재 위치'
      : `검색 기준 위치: ${label || 'AI 기준 위치'}`

    if (!isSameMapCenter(s.mapCenter, nextCenter)) {
      s.mapCenter = nextCenter
    }

    s.currentLocationPlace = [
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

  const resolveCurrentContextCenter = async ({ updateMessage = true } = {}) => {
    if (updateMessage) {
      s.isLocating = true
      s.loadingMessage = '현재 위치 확인 중'
      commit()
    }

    try {
      const currentCenter = await requestBrowserLocation()
      s.mapCenter = currentCenter
      s.currentLocationPlace = [makeCurrentLocationMarker(currentCenter)]

      if (updateMessage) {
        s.locationMessage = '현재 위치 기준으로 검색합니다.'
      }

      return {
        center: currentCenter,
        baseLabel: '현재 위치 기준',
        source: 'current_location',
      }
    } catch (error) {
      if (updateMessage) {
        s.locationMessage = '현재 위치를 가져오지 못해 현재 지도 중심 기준으로 검색합니다.'
      }

      return {
        center: s.mapCenter,
        baseLabel: '현재 지도 중심 기준',
        source: 'map_center',
      }
    } finally {
      if (updateMessage) {
        s.isLocating = false
        s.loadingMessage = ''
        commit()
      }
    }
  }

  const getSearchCenterForRecommendation = async ({ updateMessage = true } = {}) => {
    const currentContext = await resolveCurrentContextCenter({ updateMessage })
    const center = currentContext?.center || s.mapCenter || DEFAULT_CENTER

    return {
      center,
      baseLabel: currentContext?.baseLabel || '현재 지도 중심 기준',
      source: currentContext?.source || 'map_center',
    }
  }

  const setBaseLocationFromKakaoPlace = (basePlace) => {
    const baseCenter = {
      lat: Number(basePlace.y ?? basePlace.lat),
      lng: Number(basePlace.x ?? basePlace.lng),
    }

    s.mapCenter = baseCenter

    s.currentLocationPlace = [
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

  const collectBaseLocationCandidates = async ({ placesService, geocoder, baseKeyword }) => {
    s.loadingMessage = '기준 위치 후보 확인 중'
    commit()
    const keywordQueries = buildBaseLocationSearchQueries(baseKeyword)

    const [keywordResultGroups, addressResults] = await Promise.all([
      Promise.all(
        keywordQueries.map((query) => runKakaoKeywordSearchLimited(placesService, query, {
          sort: window.kakao.maps.services.SortBy.ACCURACY,
        }).then((results) => ({ query, results }))),
      ),
      runKakaoAddressSearch(geocoder, baseKeyword),
    ])

    const candidates = [
      ...keywordResultGroups.flatMap((group) => group.results.map((item, index) => (
        normalizeKakaoBaseCandidate(item, 'keyword', index, group.query)
      ))),
      ...addressResults.map((item, index) => normalizeKakaoBaseCandidate(item, 'address', index, baseKeyword)),
    ]

    return sortBaseLocationCandidates(
      dedupeBaseLocationCandidates(candidates)
        .map((candidate) => scoreBaseLocationCandidate(candidate, baseKeyword, s.mapCenter)),
    ).slice(0, 8)
  }

  const resolveBaseLocation = async ({ placesService, geocoder, baseKeyword }) => {
    const candidates = await collectBaseLocationCandidates({ placesService, geocoder, baseKeyword })

    if (!candidates.length) {
      clearSearchResults()
      s.currentLocationPlace = []
      s.selectedPlace = null
      s.showDetailPanel = false
      s.locationMessage = `"${baseKeyword}" 위치를 찾지 못했습니다.`
      commit()
      return null
    }

    const selectedCandidate = getAutoSelectedBaseCandidate(candidates, baseKeyword)

    if (selectedCandidate) {
      s.baseLocationCandidates = []
      s.pendingBaseLocationSearch = null
      return setBaseLocationFromKakaoPlace(selectedCandidate)
    }

    s.baseLocationCandidates = candidates
    s.loadingMessage = '기준 위치 선택 대기 중'
    s.locationMessage = '기준 위치가 여러 곳으로 검색되었습니다. 원하는 지역을 선택해 주세요.'
    commit()
    return null
  }

  const shouldResolveBaseLocation = (plan = {}, response = null) => {
    const responsePlan = response?.search_plan || plan?.conversationalSearchPlan?.search_plan || {}
    const locationQuery = getPlannerText(
      getResolvedSearchPlanLocationQuery(responsePlan)
      || getResolvedSearchPlanLocationQuery(plan),
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

    const locationQuery = getResolvedSearchPlanLocationQuery(parsedIntent)

    if (!locationQuery) {
      return null
    }

    s.pendingBaseLocationSearch = {
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

    const resolvedBase = await resolveBaseLocation({ placesService, geocoder, baseKeyword: locationQuery })

    if (IS_DEV) {
      console.debug('[Location resolve]', {
        locationQuery,
        resolved: Boolean(resolvedBase),
        fallbackReason: resolvedBase ? '' : 'location_query_not_resolved',
      })
    }

    if (!resolvedBase) {
      if (!s.baseLocationCandidates.length) {
        s.locationMessage = `"${locationQuery}" 위치를 찾지 못해 검색을 진행하지 않았습니다. 지역명이나 장소명을 다시 확인해 주세요.`
        s.pendingBaseLocationSearch = null
        commit()
      }
      return null
    }

    s.pendingBaseLocationSearch = null

    return {
      ...resolvedBase,
      label: `${locationQuery} 기준`,
      locationQuery,
    }
  }

  // ------------------------------------------------------------ 지도 뷰포트

  const handleMapViewportChange = ({ center, bounds } = {}) => {
    const nextCenter = {
      lat: toFiniteCoordinate(center?.lat),
      lng: toFiniteCoordinate(center?.lng),
    }

    if (nextCenter.lat === null || nextCenter.lng === null) {
      return
    }

    if (!isSameMapCenter(s.mapCenter, nextCenter)) {
      s.mapCenter = nextCenter
    }

    const southWest = bounds?.southWest
    const northEast = bounds?.northEast

    if (!southWest || !northEast) {
      s.mapViewportBounds = null
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
      nextBounds.southWest.lat === null
      || nextBounds.southWest.lng === null
      || nextBounds.northEast.lat === null
      || nextBounds.northEast.lng === null
    ) {
      s.mapViewportBounds = null
      return
    }

    s.mapViewportBounds = nextBounds
  }

  const getSearchBoundsFromViewport = () => {
    if (!window.kakao?.maps || !s.mapViewportBounds) {
      return null
    }

    const { southWest, northEast } = s.mapViewportBounds

    return new window.kakao.maps.LatLngBounds(
      new window.kakao.maps.LatLng(southWest.lat, southWest.lng),
      new window.kakao.maps.LatLng(northEast.lat, northEast.lng),
    )
  }

  const getViewportSearchRadius = (center = s.mapCenter) => {
    if (!s.mapViewportBounds) {
      return SEARCH_RADIUS
    }

    const { southWest, northEast } = s.mapViewportBounds
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

  // ---------------------------------------------------------- 검색 실행부

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
    s.loadingMessage = '주변 장소 검색 중'
    commit()
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

    const resolvedSearchPlan = searchPlan || s.activeSearchPlan || {}
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
        ? searchSavedPlaces({ targetKeyword, center, radius, requestedConditions })
        : Promise.resolve([]),
    ])
    const kakaoResults = convertKakaoPlaces(kakaoPlaces, savedTagDataByExternalId, {
      query: targetKeyword,
      center,
      preferredTags,
      recommendationIntent,
      categoryHint,
      isAncillaryIntent,
      requestedConditions,
      searchPlan: resolvedSearchPlan,
    })
    const dedupedResults = shouldUseDbPlaces
      ? dedupeSearchResults(kakaoResults, dbPlaces)
      : kakaoResults
    const saveAroundCenterSearchLog = ({
      results = dedupedResults,
      dbCount = null,
      kakaoCount = kakaoResults.length,
    } = {}) => {
      saveSearchLogSilently(buildSearchLogPayload({
        query: s.activeSearchPlan?.originalQuery || s.mapSearchKeyword.trim() || targetKeyword,
        searchMode: bounds ? 'map_bounds_search' : (s.activeSearchPlan?.searchMode || 'keyword_search'),
        locationHint: getSearchLogLocationHint({
          searchPlan: s.activeSearchPlan,
          baseLabel,
        }),
        baseLabel,
        center,
        searchPlan: s.activeSearchPlan,
        condition: s.activeSearchPlan || {},
        results,
        dbResultCount: dbCount,
        kakaoResultCount: kakaoCount,
        aiWebResultCount: 0,
      }))
    }

    if (!dedupedResults.length) {
      clearSearchResults()
      s.selectedPlace = null
      s.showDetailPanel = false
      s.locationMessage = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 검색 결과가 없습니다.`
      commit()
      saveAroundCenterSearchLog({ results: [], dbCount: 0, kakaoCount: 0 })
      return
    }

    const enrichedCount = kakaoResults.filter((place) => place.savedPlaceId).length

    if (isCafeSearchKeyword(targetKeyword)) {
      setSearchResults({
        results: dedupedResults,
        sourceLabel: '카카오 결과',
        messageSuffix: enrichedCount ? `태그 보강 카페 ${enrichedCount}개` : '',
      })
      s.locationMessage = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 카카오 검색 결과를 표시했습니다.`
      commit()
      saveAroundCenterSearchLog({
        results: dedupedResults,
        dbCount: 0,
        kakaoCount: kakaoResults.length,
      })
      return
    }

    if (shouldUseDbPlaces) {
      const displayedDbCount = dedupedResults.filter((place) => place.searchSource === 'local_db').length

      setSearchResults({
        results: dedupedResults,
        sourceLabel: '검색 결과',
        messageSuffix: `카카오 ${kakaoResults.length}개, DB ${displayedDbCount}개`,
      })
      s.locationMessage = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 검색 결과를 표시했습니다.`
      commit()
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
    s.locationMessage = `${baseLabel} ${formatSearchRadius(radius)} 이내 "${targetKeyword}" 카카오 검색 결과를 표시했습니다.`
    commit()
    saveAroundCenterSearchLog({
      results: dedupedResults,
      dbCount: 0,
      kakaoCount: kakaoResults.length,
    })
  }

  const applySearchSafetyBlock = (data = {}) => {
    const aiParse = data.ai_parse || null
    const blocked = data.blocked || aiParse?.blocked || data.is_searchable === false || aiParse?.is_searchable === false

    if (!blocked) return false

    s.mapAiParse = aiParse
    clearSearchResults()
    s.selectedPlace = null
    s.showDetailPanel = false
    s.detailFrameError = false
    s.isSearchingMap = false
    s.loadingMessage = ''
    s.locationMessage = data.message || aiParse?.user_message || '요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.'
    commit()
    return true
  }

  const ensureSearchSafety = async (query) => {
    const trimmedQuery = (query || '').trim()

    if (!trimmedQuery) return true

    s.loadingMessage = '요청 안전 확인 중'
    commit()

    try {
      const data = await checkSearchSafety({ query: trimmedQuery })
      return !applySearchSafetyBlock(data)
    } catch (error) {
      if (IS_DEV) {
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
    s.loadingMessage = '상황 해석 중'
    s.isAiReranking = false
    s.sortMode = 'recommendation'
    commit()
    const recommendationIntent = parsedIntent?.recommendationIntent || getRecommendationIntent(`${originalQuery} ${targetQuery}`)
    const preferredTags = parsedIntent?.preferredTags || getPreferredTagsForIntent(recommendationIntent)
    const requestedConditions = parsedIntent?.requestedConditions || []
    const searchPayload = {
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
    }
    const previewTask = aiSearchCandidateRecommendations(searchPayload)
      .then((value) => ({ kind: 'preview', value }))
      .catch((error) => ({ kind: 'preview', error }))
    const finalTask = aiSearchRecommendations(searchPayload)
      .then((value) => ({ kind: 'final', value }))
      .catch((error) => ({ kind: 'final', error }))
    const firstOutcome = await Promise.race([previewTask, finalTask])
    let finalOutcome = firstOutcome.kind === 'final' ? firstOutcome : null

    if (firstOutcome.kind === 'preview' && !firstOutcome.error) {
      const previewData = firstOutcome.value || {}
      const previewResults = convertRecommendationPlaces(
        Array.isArray(previewData.results) ? previewData.results : [],
        {
          preferredTags,
          recommendationIntent: getRecommendationIntentForScoring(recommendationIntent, parsedIntent || {}),
          requestedConditions,
          searchPlan: parsedIntent || {},
          getKakaoDetailUrl,
        },
      )

      if (previewResults.length) {
        s.preserveBackendResultOrder = true
        s.fallbackResults = []
        s.resultFilterMode = 'all'
        s.visibleCount = DISPLAY_BATCH_SIZE
        s.activeResultView = 'results'
        s.isResultListCollapsed = false
        s.resultSourceLabel = '빠른 후보'
        s.resultMessageSuffix = 'AI가 적합도 순서를 확인하고 있어요.'
        s.selectedPlace = null
        s.showDetailPanel = false
        s.detailFrameError = false
        setMainResults(previewResults)
        s.searchResultStatus = 'success'
        clearMainSearchErrorState()
        s.mapFitBoundsKey += 1
        s.locationMessage = `${baseLabel} 후보를 먼저 보여드리고 있어요.`
        s.loadingMessage = 'AI가 후보 순서를 다듬는 중'
        s.isAiReranking = true
        commit()
      }
    }

    if (!finalOutcome) {
      finalOutcome = await finalTask
    }
    s.isAiReranking = false
    if (finalOutcome.error) {
      throw finalOutcome.error
    }
    const data = finalOutcome.value

    if (IS_DEV) {
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
      })
    }

    const backendSearchPlan = data?.search_plan || data?.ai_parse?.search_plan || parsedIntent || {}
    const backendAction = data?.decision_action || data?.decisionAction || data?.ai_parse?.decision_action || ''
    const backendIsAiFirst = isBackendAiFirstResponse(data, parsedIntent)
    if (backendIsAiFirst && (!backendAction || backendAction === 'search')) {
      applyBackendAiSearchOrigin(data, center, baseLabel)
    }
    s.activeSearchPlan = backendSearchPlan
    const resultScenarioLabel = getFrameDisplayLabel(backendSearchPlan)
      || getIntentGroupDisplayLabel(backendSearchPlan?.intentGroup || backendSearchPlan?.intent_group || '')
      || getScenarioDisplayLabel(data?.scenario || recommendationIntent)

    s.mapAiParse = {
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
      s.searchResultStatus = backendAction === 'ask_clarification' ? 'idle' : 'error'
      s.selectedPlace = null
      s.showDetailPanel = false
      s.detailFrameError = false
      s.locationMessage = data.clarification_question
        || data.message
        || data.ai_parse?.user_message
        || '요청하신 목적과 장소 추천을 연결하기 어려웠습니다.'
      const decisionPlan = {
        ...data,
        action: backendAction,
        search_plan: backendSearchPlan,
        clarification_question: data.clarification_question || '',
        clarification_options: data.clarification_options || [],
      }
      if (backendAction === 'ask_clarification') {
        setClarificationThread(originalQuery, decisionPlan, s.locationMessage)
      } else {
        setDecisionConversationThread(originalQuery, decisionPlan, s.locationMessage, backendAction)
        clearPendingClarification({ preserveMessages: true })
      }
      commit()
      return
    }

    if (data.blocked || data.ai_parse?.blocked || data.ai_parse?.is_searchable === false) {
      clearSearchResults()
      s.searchResultStatus = 'error'
      s.selectedPlace = null
      s.showDetailPanel = false
      s.detailFrameError = false
      s.locationMessage = data.message || data.ai_parse?.user_message || '요청하신 목적은 장소 추천으로 도와드리기 어렵습니다.'
      commit()
      return
    }

    const dbResults = Array.isArray(data.results) ? data.results : []
    const useUnifiedBackendOrder = Boolean(data.unified_candidate_pipeline || data.frontend_should_preserve_order)
    s.preserveBackendResultOrder = useUnifiedBackendOrder
    if (useUnifiedBackendOrder) {
      s.fallbackResults = []
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

      s.fallbackResults = []
      s.resultFilterMode = 'all'
      s.visibleCount = DISPLAY_BATCH_SIZE
      s.activeResultView = 'results'
      s.isResultListCollapsed = false
      s.resultSourceLabel = 'AI 검색 결과'
      s.resultMessageSuffix = getBackendResultMessageSuffix({
        dbCount: backendDbResultCount,
        externalCount: backendExternalResultCount,
        scenarioLabel: resultScenarioLabel,
      })
      placeListItemRefs.current = {}
      s.selectedPlace = null
      s.showDetailPanel = false
      s.detailFrameError = false

      if (recommendationResults.length) {
        setMainResults(recommendationResults)
        s.searchResultStatus = 'success'
        clearMainSearchErrorState()
        s.mapFitBoundsKey += 1
        s.locationMessage = data.message
          || `${baseLabel} "${originalQuery}" 조건에 맞는 장소를 정리했어요.`
      } else {
        s.mainResults = []
        s.fallbackResults = []
        s.webReferenceResults = []
        syncLegacySearchResults()
        s.searchResultStatus = data.decision_action === 'ai_unavailable' ? 'error' : 'empty'
        s.locationMessage = data.message
          || data.clarification_question
          || `"${originalQuery}" 조건에 맞는 장소를 찾지 못했어요.`
      }
      s.loadingMessage = ''
      s.isSearchingMap = false
      commit()
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
      s.resultFilterMode = 'all'
      s.visibleCount = DISPLAY_BATCH_SIZE
      s.resultSourceLabel = 'AI 검색 결과'
      s.resultMessageSuffix = useUnifiedBackendOrder
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
      placeListItemRefs.current = {}
      s.mapFitBoundsKey += 1
      s.activeResultView = 'results'
      s.isResultListCollapsed = false
    }

    // 카카오 fallback 은 백엔드 통합 파이프라인으로 옮겨져 현재는 돌지 않습니다. (원본과 동일)
    const kakaoResults = []
    const menuSearchProfile = getMenuSearchProfile({ query: targetQuery, data })
    const directMenuDbMatchCount = getDirectMenuDbMatchCount(recommendationResults, menuSearchProfile)

    s.loadingMessage = '추천 결과 정리 중'
    commit()
    setFallbackResults(kakaoResults)
    const finalResults = displayResults()
    const hasAnyResults = finalResults.length > 0
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

    if (!hasAnyResults) {
      clearSearchResults()
      s.searchResultStatus = 'empty'
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
        s.locationMessage = `${baseText} 산책 후보를 찾지 못했습니다. 지도 범위를 넓히거나 주변 공원, 강변, 산책로 같은 표현으로 다시 검색해 주세요.`
      } else {
        s.locationMessage = parsedIntent?.userIntentSummary
          ? `${parsedIntent.userIntentSummary} 조건에 맞는 추천 결과가 없습니다.`
          : `"${originalQuery}" 조건에 맞는 추천 결과가 없습니다.`
      }
      commit()
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

    s.resultFilterMode = 'all'
    s.visibleCount = DISPLAY_BATCH_SIZE
    s.searchResultStatus = 'success'
    clearMainSearchErrorState()
    s.resultSourceLabel = 'AI 검색 결과'
    s.resultMessageSuffix = useUnifiedBackendOrder
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
    placeListItemRefs.current = {}
    s.mapFitBoundsKey += 1
    s.activeResultView = 'results'
    s.isResultListCollapsed = false
    await logSearchResultState()
    s.activeMenuSearchProfile = menuSearchProfile.menuIntent ? menuSearchProfile : null
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
        weak_match_count: recommendationResults.filter((place) => (
          !getRecommendationMatchedLabels(place).length
          || place.recommendationSourceType === 'db_category_fallback'
          || place.matchLevel === 'category_distance_fallback'
        )).length,
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
    s.locationMessage = intentSummaryMessage
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
    commit()
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

  const runRegionMapSearch = async ({
    placesService,
    originalQuery,
    locationQuery,
    targetQuery,
    parsedIntent = null,
  }) => {
    s.loadingMessage = '지역 장소 검색 중'
    commit()
    const allowed = await ensureSearchSafety(originalQuery)

    if (!allowed) return

    s.loadingMessage = '지역 장소 검색 중'
    commit()
    const recommendationIntent = parsedIntent?.recommendationIntent || getRecommendationIntent(`${originalQuery} ${targetQuery}`)
    const preferredTags = parsedIntent?.preferredTags || getPreferredTagsForIntent(recommendationIntent)
    const requestedConditions = parsedIntent?.requestedConditions || []
    const categoryHint = parsedIntent?.categoryHint || ''
    const isAncillaryIntent = parsedIntent?.isAncillaryIntent || false
    s.sortMode = recommendationIntent ? 'recommendation' : 'distance'
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
      s.locationMessage = `"${originalQuery}" 검색 결과가 없습니다. 더 구체적인 지역명을 입력해 주세요.`
      commit()
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
      s.baseLocationCandidates = groups
        .slice(0, 6)
        .map((group) => {
          const groupIds = new Set(group.places.map((place) => String(place.id)))
          const groupResults = convertedResults.filter((place) => groupIds.has(String(place.kakaoPlaceId)))

          return makeRegionCandidateFromGroup(group, groupResults)
        })
        .filter((candidate) => Number.isFinite(candidate.lat) && Number.isFinite(candidate.lng))

      s.pendingBaseLocationSearch = {
        type: 'region_results',
        originalQuery,
        targetQuery,
      }
      s.loadingMessage = '지역 선택 대기 중'
      s.locationMessage = '검색 결과가 여러 지역으로 나뉘었습니다. 원하는 지역을 선택해 주세요.'
      commit()
      return
    }

    const dominantGroup = groups[0]
    const regionDisplayResults = dominantGroup
      ? convertedResults.filter((place) => dominantGroup.places.some((rawPlace) => String(rawPlace.id) === String(place.kakaoPlaceId)))
      : convertedResults
    const nextCenter = dominantGroup?.center || getPlacesCenter(kakaoPlaces)

    if (nextCenter) {
      s.mapCenter = nextCenter
    }

    setSearchResults({
      results: regionDisplayResults,
      sourceLabel: '지역 검색 결과',
      messageSuffix: `${locationQuery} · 카카오 ${regionDisplayResults.length}개`,
    })
    s.locationMessage = parsedIntent?.userIntentSummary
      ? `${parsedIntent.userIntentSummary} 지역 검색 결과를 표시했습니다.`
      : `"${originalQuery}" 지역 검색 결과를 표시했습니다.`
    commit()
    saveSearchLogSilently(buildSearchLogPayload({
      query: originalQuery,
      searchMode: 'region_search',
      locationHint: locationQuery,
      center: nextCenter,
      searchPlan: parsedIntent,
      condition: parsedIntent || {},
      results: regionDisplayResults,
      dbResultCount: 0,
      kakaoResultCount: regionDisplayResults.length,
      aiWebResultCount: 0,
    }))
  }

  const searchKakaoPlaces = async ({ useMapBounds = false, searchPlanOverride = null } = {}) => {
    const keyword = s.mapSearchKeyword.trim()

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

    s.isSearchingMap = true
    s.loadingMessage = '요청 안전 확인 중'
    commit()
    const allowed = await ensureSearchSafety(keyword)

    if (!allowed) return

    s.isSearchingMap = true
    s.loadingMessage = '주변 장소 검색 중'
    resetSearchStatusMessage('주변 장소를 검색하는 중입니다.')
    s.sortMode = 'distance'
    s.mapAiParse = null
    s.selectedPlace = null
    s.showDetailPanel = false
    s.detailFrameError = false
    commit()

    const placesService = new window.kakao.maps.services.Places()
    const geocoder = new window.kakao.maps.services.Geocoder()
    const parsedKeyword = searchPlanOverride || buildSearchPlan(keyword)
    s.activeSearchPlan = parsedKeyword
    const targetKeyword = parsedKeyword.targetKeyword
    const searchBounds = useMapBounds ? getSearchBoundsFromViewport() : null
    const searchRadius = useMapBounds ? getViewportSearchRadius(s.mapCenter) : SEARCH_RADIUS

    try {
      if (useMapBounds) {
        s.currentLocationPlace = [
          {
            id: 'map-view-center',
            name: '현재 지도 중심',
            lat: s.mapCenter.lat,
            lng: s.mapCenter.lng,
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
          center: s.mapCenter,
          bounds: searchBounds,
          radius: searchRadius,
          baseLabel: '현재 지도 화면 기준',
          searchPlan: parsedKeyword,
        })

        return
      }

      s.baseLocationCandidates = []
      s.pendingBaseLocationSearch = null

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

      s.pendingBaseLocationSearch = {
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
      s.pendingBaseLocationSearch = null
    } catch (error) {
      console.error(error)
      clearSearchResults()
      s.selectedPlace = null
      s.showDetailPanel = false
      s.locationMessage = '장소 검색 중 오류가 발생했습니다.'
    } finally {
      if (!s.baseLocationCandidates.length) {
        s.isSearchingMap = false
        s.loadingMessage = ''
      }
      commit()
    }
  }

  const searchAiRecommendationsOnMap = async (searchPlanOverride = null) => {
    const query = s.aiSearchKeyword.trim()

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

    s.isSearchingMap = true
    s.loadingMessage = '상황 해석 중'
    resetSearchStatusMessage('AI 추천 조건을 확인하는 중입니다.')
    s.selectedPlace = null
    s.showDetailPanel = false
    s.detailFrameError = false
    commit()

    try {
      const placesService = new window.kakao.maps.services.Places()
      const geocoder = new window.kakao.maps.services.Geocoder()
      const parsedQuery = searchPlanOverride || buildSearchPlan(query)
      s.activeSearchPlan = parsedQuery
      let resolvedSearchCenter = s.mapCenter
      let baseLabel = '현재 지도 중심 기준'

      s.baseLocationCandidates = []
      s.pendingBaseLocationSearch = null

      const explicitLocationQuery = shouldResolveBaseLocation(parsedQuery)
        ? getResolvedSearchPlanLocationQuery(parsedQuery)
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
        s.pendingBaseLocationSearch = {
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
        s.pendingBaseLocationSearch = null
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
      if (displayResults().length) {
        s.searchResultStatus = 'success'
        clearMainSearchErrorState()
        commit()
        return
      }

      s.mapAiParse = null
      clearSearchResults()
      setMainSearchError('검색 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.')
      s.selectedPlace = null
      s.showDetailPanel = false
    } finally {
      if (!s.baseLocationCandidates.length) {
        s.isSearchingMap = false
        s.loadingMessage = ''
      }
      commit()
    }
  }

  const getConversationalPreviousContext = () => {
    if (!s.activeSearchPlan || !displayResults().length) {
      return null
    }

    const previousUserQuery = getPlannerText(
      s.activeSearchPlan.originalQuery
      || s.activeSearchPlan.original_query
      || s.activeSearchPlan.normalizedQuery
      || s.activeSearchPlan.normalized_query
      || s.mapSearchKeyword
      || s.searchKeyword,
    )
    const previousFrame = s.activeSearchPlan.placeIntentFrame
      || s.activeSearchPlan.place_intent_frame
      || {}

    return {
      query: previousUserQuery,
      previous_user_query: previousUserQuery,
      original_query: previousUserQuery,
      place_intent_frame: previousFrame,
      last_resolved_location_context: {
        locationQuery: s.activeSearchPlan.locationQuery || s.activeSearchPlan.location_query || '',
        anchorLocation: getFrameAnchorLocation(s.activeSearchPlan) || '',
        locationMode: getFrameLocationMode(s.activeSearchPlan) || 'current_context',
        lat: s.mapCenter?.lat ?? null,
        lng: s.mapCenter?.lng ?? null,
      },
      search_plan: {
        locationQuery: s.activeSearchPlan.locationQuery || '',
        baseLocationQuery: s.activeSearchPlan.baseLocationQuery || '',
        targetQuery: s.activeSearchPlan.targetQuery || '',
        scenario: s.activeSearchPlan.recommendationIntent || '',
        categoryHint: s.activeSearchPlan.categoryHint || '',
        menu_keywords: s.activeSearchPlan.menu_keywords || [],
        place_type_keywords: s.activeSearchPlan.place_type_keywords || [],
        requestedConditions: s.activeSearchPlan.requestedConditions || [],
        place_intent_frame: previousFrame,
        candidate_place_types: s.activeSearchPlan.candidatePlaceTypes || [],
        constraints: s.activeSearchPlan.constraints || [],
        exclusions: s.activeSearchPlan.exclusions || [],
        excluded_categories: s.activeSearchPlan.excludedCategories || [],
        display_label: s.activeSearchPlan.displayLabel || '',
        web_search_queries: s.activeSearchPlan.webSearchQueries || [],
        kakaoKeywordCandidates: s.activeSearchPlan.kakaoKeywordCandidates || [],
        intent_group: s.activeSearchPlan.intentGroup || '',
      },
      result_count: displayResults().length,
    }
  }

  const resolveConversationalSearchPlan = async (keyword, previousContext = null, extraPayload = {}) => {
    try {
      s.loadingMessage = '검색 의도 해석 중'
      commit()
      const data = await buildConversationalSearchPlan({
        query: keyword,
        lat: s.mapCenter?.lat ?? null,
        lng: s.mapCenter?.lng ?? null,
        mapCenter: s.mapCenter || null,
        previousContext,
        ...extraPayload,
      })

      return data && typeof data === 'object' ? data : null
    } catch (error) {
      if (IS_DEV) {
        console.warn('[대화형 검색 해석] fallback to local planner', {
          message: error?.message || '',
          status: error?.response?.status || null,
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
      lat: s.mapCenter?.lat ?? null,
      lng: s.mapCenter?.lng ?? null,
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

  const getResultCountText = () => {
    if (!displayResults().length) {
      return ''
    }

    if (s.isResultListCollapsed) {
      return '검색 결과'
    }

    const suffix = s.resultMessageSuffix ? ` · ${s.resultMessageSuffix}` : ''

    if (s.resultFilterMode !== 'all') {
      return `${getResultFilterLabel(s.resultFilterMode)} ${searchedPlaces().length}개를 보여드려요${suffix}`
    }

    return `${searchedPlaces().length}개를 찾았어요${suffix}`
  }

  const performUnifiedMapSearch = async ({
    useMapBounds = false,
    allowImplicitCurrentContext = false,
  } = {}) => {
    const keyword = s.mapSearchKeyword.trim()

    if (!keyword) {
      alert('검색어를 입력해주세요.')
      return
    }

    s.conversationModeStarted = true
    s.isSearchingMap = true
    s.loadingMessage = '검색 의도 해석 중'
    s.searchResultStatus = 'loading'
    commit()
    const previousContext = getConversationalPreviousContext()
    const pendingClarificationForFollowUp = !useMapBounds && s.pendingClarification
      ? {
        ...s.pendingClarification,
        partial_search_plan: { ...(s.pendingClarification.partial_search_plan || {}) },
      }
      : null
    const previousMainResults = [...s.mainResults]
    const previousFallbackResults = [...s.fallbackResults]
    const previousWebReferenceResults = [...s.webReferenceResults]
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
      const localLocationPlan = buildSearchPlan(keyword)
      const explicitLocationQuery = shouldResolveBaseLocation(localLocationPlan)
        ? getResolvedSearchPlanLocationQuery(localLocationPlan)
        : ''
      const currentContext = explicitLocationQuery
        ? {
          center: s.mapCenter,
          baseLabel: `${explicitLocationQuery} 기준`,
        }
        : await getSearchCenterForRecommendation()
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

      if (pendingClarificationForFollowUp && displayResults().length) {
        appendSearchSummaryMessage(s.locationMessage || getResultCountText())
      } else if (
        !pendingClarificationForFollowUp
        && !s.pendingClarification
        && ['success', 'empty'].includes(s.searchResultStatus)
      ) {
        setDecisionConversationThread(
          keyword,
          { search_plan: s.activeSearchPlan || {} },
          s.locationMessage || getResultCountText() || '검색 결과를 확인해 주세요.',
          'search_summary',
        )
      }
      if (!s.baseLocationCandidates.length) {
        s.isSearchingMap = false
        s.loadingMessage = ''
        s.searchResultStatus = displayResults().length ? 'success' : s.searchResultStatus
      }
      commit()
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

    if (conversationalPlan?.action && conversationalPlan.action !== 'search') {
      if (conversationalPlan.action === 'refine_previous_search' && previousContext) {
        s.mainResults = previousMainResults
        s.fallbackResults = previousFallbackResults
        s.webReferenceResults = previousWebReferenceResults
        syncLegacySearchResults()
      } else {
        s.mainResults = []
        s.fallbackResults = []
        s.webReferenceResults = []
        syncLegacySearchResults()
        s.resultFilterMode = 'all'
        s.visibleCount = DISPLAY_BATCH_SIZE
        s.selectedPlace = null
        s.showDetailPanel = false
        s.detailFrameError = false
        s.isPlaceDetailCollapsed = false
        resetAiWebSearchState()
      }

      s.activeSearchPlan = adaptConversationalSearchPlan(conversationalPlan, keyword)
      s.mapAiParse = {
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
      s.locationMessage = conversationalPlan.message
        || conversationalPlan.clarification_question
        || fallbackMessage
      if (conversationalPlan.action === 'ask_clarification') {
        setClarificationThread(keyword, conversationalPlan, s.locationMessage)
      } else {
        setDecisionConversationThread(keyword, conversationalPlan, s.locationMessage, conversationalPlan.action)
        clearPendingClarification({ preserveMessages: true })
      }
      s.searchResultStatus = displayResults().length ? 'success' : 'idle'
      s.loadingMessage = ''
      s.isSearchingMap = false
      commit()
      return
    }

    clearPendingClarification({
      preserveMessages: Boolean(pendingClarificationForFollowUp),
    })
    const parsedKeyword = useMapBounds
      ? cloneSearchPlanForMapCenter(s.activeSearchPlan || {}, keyword)
      : conversationalPlan
        ? adaptConversationalSearchPlan(conversationalPlan, keyword)
        : buildSearchPlan(keyword)
    s.activeSearchPlan = parsedKeyword
    const searchMode = getUnifiedSearchMode(keyword, parsedKeyword, { useMapBounds })

    if (['region_search', 'recommendation_query'].includes(searchMode)) {
      s.sortMode = parsedKeyword.recommendationIntent ? 'recommendation' : 'distance'
      s.aiSearchKeyword = keyword
      if (useMapBounds) {
        try {
          await waitForKakaoServices()
        } catch (error) {
          handleKakaoMapLoadError(error)
          return
        }

        const mapCenterLat = Number(s.mapCenter?.lat)
        const mapCenterLng = Number(s.mapCenter?.lng)
        const hasMapCenter = Number.isFinite(mapCenterLat) && Number.isFinite(mapCenterLng)
        const fallbackContext = hasMapCenter ? null : await getSearchCenterForRecommendation()
        const center = hasMapCenter ? { lat: mapCenterLat, lng: mapCenterLng } : fallbackContext.center
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
          appendSearchSummaryMessage(s.locationMessage || getResultCountText())
        }

        if (!s.baseLocationCandidates.length) {
          s.isSearchingMap = false
          s.loadingMessage = ''
          s.searchResultStatus = displayResults().length ? 'success' : s.searchResultStatus
        }
        commit()
        return
      }
      await searchAiRecommendationsOnMap(parsedKeyword)
      if (pendingClarificationForFollowUp) {
        appendSearchSummaryMessage(s.locationMessage || getResultCountText())
      }
      if (!s.baseLocationCandidates.length && s.loadingMessage === '검색 의도 해석 중') {
        s.isSearchingMap = false
        s.loadingMessage = ''
        s.searchResultStatus = displayResults().length ? 'success' : 'idle'
      }
      commit()
      return
    }

    s.sortMode = 'distance'
    await searchKakaoPlaces({ useMapBounds, searchPlanOverride: parsedKeyword })
    if (pendingClarificationForFollowUp) {
      appendSearchSummaryMessage(s.locationMessage || getResultCountText())
    }
    if (!s.baseLocationCandidates.length && s.loadingMessage === '검색 의도 해석 중') {
      s.isSearchingMap = false
      s.loadingMessage = ''
      s.searchResultStatus = displayResults().length ? 'success' : 'idle'
    }
    commit()
  }

  // ---------------------------------------------------------------- 액션

  const handleSearch = async () => {
    if (!s.searchKeyword.trim()) {
      alert('검색어를 입력해주세요.')
      return
    }

    s.conversationModeStarted = true
    s.mapSearchKeyword = s.searchKeyword.trim()
    s.activeTab = 'search'
    s.activeResultView = 'results'
    s.isResultListCollapsed = false
    commit()

    try {
      await waitForKakaoServices()
      await performUnifiedMapSearch()
    } catch (error) {
      handleKakaoMapLoadError(error)
    }
  }

  const submitClarificationFollowUp = async () => {
    const answer = s.followUpInput.trim()

    if (!answer || s.isSearchingMap) return

    s.followUpInput = ''
    s.mapSearchKeyword = answer
    s.activeTab = 'search'
    s.activeResultView = 'results'
    s.isResultListCollapsed = false
    commit()

    await performUnifiedMapSearch()
  }

  const submitClarificationOption = async (option = '') => {
    const answer = getClarificationOptionValue(option)
    if (!answer || s.isSearchingMap) return

    s.followUpInput = answer
    commit()
    await submitClarificationFollowUp()
  }

  const runAiPresetSearch = async (query) => {
    s.conversationModeStarted = true
    s.mapSearchKeyword = query
    s.activeResultView = 'results'
    s.isResultListCollapsed = false
    commit()
    await performUnifiedMapSearch({ allowImplicitCurrentContext: true })
  }

  const runLandingPresetSearch = async (query) => {
    s.conversationModeStarted = true
    s.searchKeyword = ''
    s.mapSearchKeyword = query
    s.activeTab = 'search'
    s.activeResultView = 'results'
    s.isResultListCollapsed = false
    commit()
    await performUnifiedMapSearch({ allowImplicitCurrentContext: true })
  }

  const openMapWithCurrentLocation = () => {
    s.activeTab = 'map'
    s.activeResultView = 'map'
    s.isResultListCollapsed = true
    s.isLocating = true
    s.locationMessage = '현재 위치를 확인하는 중입니다.'
    commit()

    requestBrowserLocation()
      .then((currentCenter) => {
        s.mapCenter = currentCenter
        s.currentLocationPlace = [makeCurrentLocationMarker(currentCenter)]
        s.locationMessage = '현재 위치 기준으로 지도를 표시하고 있습니다.'
      })
      .catch((error) => {
        s.mapCenter = DEFAULT_CENTER
        s.currentLocationPlace = []

        if (error.code === error.PERMISSION_DENIED) {
          s.locationMessage = '위치 권한이 거부되어 기본 위치로 지도를 표시합니다.'
        } else if (error.code === error.TIMEOUT) {
          s.locationMessage = '현재 위치 확인 시간이 초과되어 기본 위치로 지도를 표시합니다.'
        } else {
          s.locationMessage = '현재 위치를 가져오지 못해 기본 위치로 지도를 표시합니다.'
        }
      })
      .finally(() => {
        s.isLocating = false
        commit()
      })
  }

  const clearBaseLocationCandidateSelection = () => {
    s.baseLocationCandidates = []
    s.pendingBaseLocationSearch = null
    s.isSearchingMap = false
    s.loadingMessage = ''
    commit()
  }

  const selectBaseLocationCandidate = async (candidate) => {
    const pendingSearch = s.pendingBaseLocationSearch

    if (!pendingSearch) {
      clearBaseLocationCandidateSelection()
      return
    }

    s.isSearchingMap = true
    s.loadingMessage = '주변 장소 검색 중'
    s.baseLocationCandidates = []
    s.pendingBaseLocationSearch = null
    commit()

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
        s.locationMessage = `${resolvedBase.label} "${pendingSearch.originalQuery}" 지역 검색 결과를 표시했습니다.`
        commit()
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
      s.selectedPlace = null
      s.showDetailPanel = false
      s.locationMessage = '선택한 기준 위치로 검색하는 중 오류가 발생했습니다.'
    } finally {
      s.isSearchingMap = false
      s.loadingMessage = ''
      commit()
    }
  }

  const resetMapSearch = () => {
    s.conversationModeStarted = false
    s.mapSearchKeyword = ''
    s.aiSearchKeyword = ''
    s.mapAiParse = null
    s.activeSearchPlan = null
    clearPendingClarification()
    s.baseLocationCandidates = []
    s.pendingBaseLocationSearch = null
    s.loadingMessage = ''
    s.isSearchingMap = false
    s.currentLocationPlace = []
    s.selectedPlace = null
    s.hiddenMapMarkerPlaceId = null
    s.showDetailPanel = false
    s.detailFrameError = false
    s.isPlaceDetailDismissed = false
    s.isPlaceDetailCollapsed = false
    s.activeResultView = 'results'
    s.isResultListCollapsed = false
    clearSearchResults()
    window.dispatchEvent(new CustomEvent('place-marker-fetch-clear'))
    s.locationMessage = '검색이 초기화되었습니다. 검색어를 입력하거나 지도를 이동한 뒤 다시 검색해보세요.'
    commit()
  }

  const startNewConversationSearch = async () => {
    startNewConversationSession()
    s.conversationModeStarted = false
    s.searchKeyword = ''
    s.mapSearchKeyword = ''
    s.aiSearchKeyword = ''
    s.mapAiParse = null
    s.activeSearchPlan = null
    s.activeMenuSearchProfile = null
    clearPendingClarification()
    s.baseLocationCandidates = []
    s.pendingBaseLocationSearch = null
    s.loadingMessage = ''
    s.isSearchingMap = false
    s.selectedPlace = null
    s.hiddenMapMarkerPlaceId = null
    s.showDetailPanel = false
    s.detailFrameError = false
    s.isPlaceDetailDismissed = false
    s.isPlaceDetailCollapsed = false
    s.activeTab = 'search'
    s.activeResultView = 'results'
    s.isResultListCollapsed = false
    clearSearchResults()
    window.dispatchEvent(new CustomEvent('place-marker-fetch-clear'))
    s.locationMessage = '새 검색어를 입력해 주세요.'
    commit()
  }

  // -------------------------------------------------------------- 장소 선택

  const dispatchMascotFetch = (place, target = null) => {
    s.hiddenMapMarkerPlaceId = null

    window.dispatchEvent(new CustomEvent('place-marker-fetch', {
      detail: {
        placeId: place?.id,
        placeName: place?.name,
        markerLabel: place?.markerLabel,
        target,
      },
    }))
  }

  const updateMascotFetchTarget = (place, target = null) => {
    if (!s.selectedPlace || String(s.selectedPlace.id) !== String(place?.id)) return

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
    s.selectedPlace = place
    s.detailFrameError = false
    s.isPlaceDetailDismissed = false
    s.isPlaceDetailCollapsed = false
    dispatchMascotFetch(place, target)
    commit()
    resolveKakaoDetailUrlForPlace(place)
  }

  const closePlaceCard = () => {
    s.selectedPlace = null
    s.hiddenMapMarkerPlaceId = null
    s.detailFrameError = false
    s.isPlaceDetailDismissed = false
    s.isPlaceDetailCollapsed = false
    window.dispatchEvent(new CustomEvent('place-marker-fetch-clear'))
    commit()
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

  const selectPlaceFromList = (place, event) => {
    if (s.selectedPlace && String(s.selectedPlace.id) === String(place?.id)) {
      if (s.isPlaceDetailDismissed) {
        s.detailFrameError = false
        s.isPlaceDetailDismissed = false
        s.isPlaceDetailCollapsed = false
        dispatchMascotFetch(place, getListMarkerTarget(event))
        commit()
        return
      }

      closePlaceCard()
      return
    }

    selectPlace(place, getListMarkerTarget(event))
  }

  const searchCurrentMapView = () => {
    closePlaceCard()
    s.showDetailPanel = false
    performUnifiedMapSearch({ useMapBounds: true })
  }

  const getPlaceReportQuery = (place) => {
    const query = new URLSearchParams({ reportType: 'tag_suggestion' })

    if (isDbPlace(place) && place?.id) {
      query.set('placeId', place.id)
    }

    const name = getTextValue(place?.name)
    const category = getTextValue(place?.category)
    const address = getTextValue(place?.address || place?.detailLocation || place?.roadAddress)
    const lat = Number(place?.lat)
    const lng = Number(place?.lng)

    if (name) query.set('name', name)
    if (category) query.set('category', category)
    if (address) query.set('address', address)
    if (Number.isFinite(lat)) query.set('lat', lat.toFixed(6))
    if (Number.isFinite(lng)) query.set('lng', lng.toFixed(6))

    return query.toString()
  }

  const goToPlaceReport = (place) => {
    navigate(`/place-report?${getPlaceReportQuery(place)}`)
  }

  const dismissPlaceDetailPanel = () => {
    s.detailFrameError = false
    s.isPlaceDetailDismissed = true
    s.isPlaceDetailCollapsed = false
    commit()
  }

  const setStateValue = (key, value) => {
    s[key] = value
    commit()
  }

  const setResultFilterMode = (filterMode) => {
    s.resultFilterMode = filterMode
    s.visibleCount = DISPLAY_BATCH_SIZE
    s.mapFitBoundsKey += 1

    // 필터 때문에 선택한 장소가 목록에서 빠지면 상세도 닫습니다.
    if (s.selectedPlace?.id) {
      const stillVisible = filteredSearchResults().some((place) => place.id === s.selectedPlace.id)

      if (!stillVisible) {
        s.selectedPlace = null
        s.showDetailPanel = false
        s.detailFrameError = false
        s.isPlaceDetailCollapsed = false
      }
    }

    commit()
  }

  const setSortMode = (nextSortMode) => {
    s.sortMode = nextSortMode
    s.visibleCount = DISPLAY_BATCH_SIZE
    s.mapFitBoundsKey += 1
    commit()
  }

  const showMoreResults = () => {
    s.visibleCount = Math.min(s.visibleCount + DISPLAY_BATCH_SIZE, displayResults().length)
    commit()
  }

  const setResultViewMode = (mode) => {
    s.activeResultView = mode === 'map' ? 'map' : 'results'
    s.isResultListCollapsed = s.activeResultView === 'map'
    commit()
  }

  const toggleResultListPanel = () => {
    s.isResultListCollapsed = !s.isResultListCollapsed
    s.activeResultView = s.isResultListCollapsed ? 'map' : 'results'
    commit()
  }

  // -------------------------------------------------------- 마스코트 연동

  const dispatchSearchLoadingMascotState = (isSearching = false) => {
    window.dispatchEvent(new CustomEvent('search-loading-change', {
      detail: {
        isSearching: Boolean(isSearching),
        message: s.loadingMessage || '',
      },
    }))
  }

  const lastMascotSearchStateRef = useRef({ isSearching: false, message: '' })
  useEffect(() => {
    const previous = lastMascotSearchStateRef.current

    if (previous.isSearching !== s.isSearchingMap || (s.isSearchingMap && previous.message !== s.loadingMessage)) {
      lastMascotSearchStateRef.current = {
        isSearching: s.isSearchingMap,
        message: s.loadingMessage,
      }
      dispatchSearchLoadingMascotState(s.isSearchingMap)
    }
  })

  useEffect(() => {
    const handleMascotFetchArrived = (event) => {
      const arrivedPlaceId = event.detail?.placeId

      if (!arrivedPlaceId || !s.selectedPlace) return
      if (String(s.selectedPlace.id) !== String(arrivedPlaceId)) return

      s.hiddenMapMarkerPlaceId = arrivedPlaceId
      commit()
    }

    const handleMascotFetchClick = (event) => {
      const clickedPlaceId = event.detail?.placeId

      if (!clickedPlaceId || !s.selectedPlace) return
      if (String(s.selectedPlace.id) !== String(clickedPlaceId)) return

      s.markerChoiceRequestKey += 1
      commit()
    }

    window.addEventListener('place-marker-fetch-arrived', handleMascotFetchArrived)
    window.addEventListener('place-marker-fetch-click', handleMascotFetchClick)

    return () => {
      dispatchSearchLoadingMascotState(false)
      window.removeEventListener('place-marker-fetch-arrived', handleMascotFetchArrived)
      window.removeEventListener('place-marker-fetch-click', handleMascotFetchClick)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ------------------------------------------------------- 라우트 쿼리 반영

  const routeQuery = searchParams.get('q') || ''
  const routeAutoSearch = searchParams.get('autoSearch') || ''

  useEffect(() => {
    const normalizedQuery = String(routeQuery || '').trim()

    if (!normalizedQuery) return

    s.searchKeyword = normalizedQuery
    s.mapSearchKeyword = normalizedQuery
    s.activeTab = 'search'
    commit()

    if (routeAutoSearch !== '1') {
      lastRouteAutoSearchKeyRef.current = ''
      return
    }

    if (lastRouteAutoSearchKeyRef.current === normalizedQuery) return
    lastRouteAutoSearchKeyRef.current = normalizedQuery

    // autoSearch 플래그는 한 번만 쓰고 주소에서 지웁니다.
    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete('autoSearch')
    setSearchParams(nextParams, { replace: true })

    handleSearch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeQuery, routeAutoSearch])

  useEffect(() => {
    s.activeTab = normalizeTab(initialTab)
    commit()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTab])

  return {
    state: s,
    commit,
    setStateValue,
    placeListItemRefs,

    // 파생 값
    displayResults,
    filteredSearchResults,
    searchedPlaces,
    mapPlaces,
    getResultCountText,
    shouldSuggestAiWebSearch,
    getRecommendationMatchedLabels,
    getRecommendationReason,
    getRecommendationReasonSummary,
    getMenuDisplayMatchedLabels,

    // 장소 정보
    getKakaoDetailUrl,
    getPlaceDetailUrl,
    getPlaceNavigationUrl,
    hasKakaoDetail,

    // 액션
    handleSearch,
    performUnifiedMapSearch,
    runAiPresetSearch,
    runLandingPresetSearch,
    submitClarificationFollowUp,
    submitClarificationOption,
    searchAiWebCandidatesManually,
    openMapWithCurrentLocation,
    resetMapSearch,
    startNewConversationSearch,
    searchCurrentMapView,
    selectPlace,
    selectPlaceFromList,
    closePlaceCard,
    dismissPlaceDetailPanel,
    goToPlaceReport,
    selectBaseLocationCandidate,
    clearBaseLocationCandidateSelection,
    setResultFilterMode,
    setSortMode,
    showMoreResults,
    setResultViewMode,
    toggleResultListPanel,
    handleMapViewportChange,
    updateMascotFetchTarget,
  }
}
