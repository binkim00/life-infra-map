import {
  buildFrameBasedKakaoKeywords,
  extractFoodMenuKeywords,
  filterKeywordsByExclusions,
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
  getPlannerList,
  getSearchPlanFrame,
  getTextValue,
  inferFoodPlaceTypeKeywords,
  isCafeSearchKeyword,
  isDbRecommendationResult,
  isKakaoCandidateResult,
  normalizeLocationText,
  toDisplayList,
} from '@/utils/homePlaceHelpers'

export const stripAiWebSearchRequestWords = (query = '') => {
  return getTextValue(query)
    .replace(/\s*(찾아줘|찾아주세요|추천해줘|추천해주세요|알려줘|알려주세요)\s*$/g, '')
    .replace(/\s*(먹고\s*싶어|먹고싶어|먹을래|가고\s*싶어|가고싶어)\s*$/g, '')
    .trim()
}

export const buildAiWebTargetQuery = ({
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

export const buildAiWebSearchPlanPayload = (parsedIntent = null, condition = {}, originalQuery = '') => {
  const source = parsedIntent || {}
  const placeIntentFrame = getSearchPlanFrame(source)
  const menuKeywords = getPlannerList(condition?.menu_keywords || source.menu_keywords || [])
  const placeTypeKeywords = [
    ...getPlannerList(condition?.place_type_keywords || source.place_type_keywords || []),
    ...getFrameCandidatePlaceTypes(source),
  ].filter((keyword, index, list) => keyword && list.indexOf(keyword) === index)
  const constraints = getFrameConstraints(source)
  const exclusions = getFrameExclusions(source)
  const webSearchQueries = filterKeywordsByExclusions(getFrameWebSearchQueries(source), source)
  const kakaoKeywordCandidates = buildFrameBasedKakaoKeywords(source, { includeWebQueries: false })
  const sourceRequestedConditions = Array.isArray(source.requestedConditions)
    ? source.requestedConditions
    : []
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
    requestedConditions: [
      ...sourceRequestedConditions,
      ...constraints,
    ],
    menu_keywords: menuKeywords,
    place_type_keywords: placeTypeKeywords,
    place_intent_frame: placeIntentFrame,
    target_objects: getFrameTargetObjects(source),
    candidate_place_types: getFrameCandidatePlaceTypes(source),
    constraints,
    exclusions,
    ranking_policy: getFrameRankingPolicy(source),
    display_label: getFrameDisplayLabel(source),
    web_search_queries: webSearchQueries,
    kakaoKeywordCandidates,
  }
}

export const getAiWebSearchLocationHint = (baseLabel = '', parsedIntent = null) => {
  const planLocation = parsedIntent?.locationQuery || parsedIntent?.baseLocationQuery || ''
  if (planLocation) return planLocation

  const label = getTextValue(baseLabel)
  if (!label || label.includes('현재') || label.includes('지도')) {
    return ''
  }
  return label.replace(/\s*기준\s*$/g, '').trim()
}

export const getFirstSearchLogList = (...values) => {
  for (const value of values) {
    const list = toDisplayList(value)
    if (list.length) return list
  }

  return []
}

export const getSearchLogLocationHint = ({
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

export const buildSearchPlanSnapshotForLog = (searchPlan = {}) => {
  const snapshot = {}
  const snapshotFields = [
    'locationQuery',
    'baseLocationQuery',
    'targetQuery',
    'targetType',
    'categoryHint',
    'confidence',
    'fallbackReason',
    'execution_mode',
    'executionMode',
    'plan_source',
    'planSource',
    'location_mode',
    'locationMode',
    'display_label',
    'displayLabel',
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

  const frame = getSearchPlanFrame(searchPlan)
  if (Object.keys(frame).length) {
    snapshot.place_intent_frame = {
      situation: getTextValue(frame.situation),
      display_label: getFrameDisplayLabel(searchPlan),
      anchor_location: getFrameAnchorLocation(searchPlan),
      location_mode: getFrameLocationMode(searchPlan),
      candidate_category_codes: getFrameCandidateCategoryCodes(searchPlan),
      candidate_place_types: getFrameCandidatePlaceTypes(searchPlan),
      constraints: getFrameConstraints(searchPlan),
      exclusions: getFrameExclusions(searchPlan),
      result_match_terms: getFrameResultMatchTerms(searchPlan),
    }
  }

  return snapshot
}

export const getFiniteSearchLogCount = (value, fallback = 0) => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return fallback

  return Math.max(0, Math.trunc(numericValue))
}

export const SEARCH_LOG_TEXT_LIMITS = {
  query: 255,
  searchMode: 50,
  scenario: 50,
  locationHint: 100,
  targetQuery: 255,
  categoryHint: 50,
}

export const getSearchLogText = (value, maxLength) => {
  const text = getTextValue(value)
  return maxLength ? text.slice(0, maxLength) : text
}

export const getSearchLogCoordinate = (value) => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return null

  return Number(numericValue.toFixed(6))
}

export const buildSearchLogPayload = ({
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
