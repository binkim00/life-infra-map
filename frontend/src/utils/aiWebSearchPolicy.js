import {
  AI_WEB_SEARCH_DETAIL_KEYWORDS,
  AI_WEB_SEARCH_EXPLICIT_KEYWORDS,
  AI_WEB_SEARCH_HELPFUL_CATEGORIES,
  AI_WEB_SEARCH_HELPFUL_KEYWORDS,
  AI_WEB_SEARCH_INFRA_BLOCK_CATEGORIES,
} from '@/constants/homeSearchConstants'
import {
  getFrameAnchorLocation,
  getFrameCandidatePlaceTypes,
  getFrameConstraints,
  getFrameDisplayLabel,
  getFrameExclusions,
  getFrameWebSearchQueries,
  getPlanKakaoKeywordCandidates,
  getSearchPlanFrame,
  getTextValue,
  normalizeLocationText,
} from '@/utils/homePlaceHelpers'

export const getAiWebSearchSignalParts = (query = '', condition = {}, searchPlan = {}) => {
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
    searchPlan?.displayLabel,
    searchPlan?.display_label,
    searchPlan?.intentGroup,
    searchPlan?.intent_group,
    getFrameDisplayLabel(searchPlan),
    getFrameAnchorLocation(searchPlan),
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
    ...getFrameCandidatePlaceTypes(searchPlan),
    ...getFrameConstraints(searchPlan),
    ...getFrameExclusions(searchPlan),
    ...getFrameWebSearchQueries(searchPlan),
    ...getPlanKakaoKeywordCandidates(searchPlan),
  ]
}

export const getAiWebSearchSignalText = (query = '', condition = {}, searchPlan = {}) => {
  return normalizeLocationText(getAiWebSearchSignalParts(query, condition, searchPlan).filter(Boolean).join(' '))
}

export const hasAiWebSearchKeyword = (keywords = [], query = '', condition = {}, searchPlan = {}) => {
  const text = getAiWebSearchSignalText(query, condition, searchPlan)
  return keywords.some((keyword) => text.includes(normalizeLocationText(keyword)))
}

export const hasAiWebSearchDetailCondition = (query = '', condition = {}, searchPlan = {}) => {
  return hasAiWebSearchKeyword(AI_WEB_SEARCH_DETAIL_KEYWORDS, query, condition, searchPlan)
}

export const hasExplicitAiWebSearchRequest = (query = '', condition = {}, searchPlan = {}) => {
  return hasAiWebSearchKeyword(AI_WEB_SEARCH_EXPLICIT_KEYWORDS, query, condition, searchPlan)
}

export const getAiWebSearchCategories = (condition = {}, searchPlan = {}) => {
  return [
    condition?.category,
    condition?.categoryHint,
    condition?.category_hint,
    condition?.scenario,
    searchPlan?.categoryHint,
    searchPlan?.category_hint,
    searchPlan?.intentGroup,
    searchPlan?.intent_group,
    getSearchPlanFrame(searchPlan)?.situation,
  ].map((value) => getTextValue(value))
}

export const isAiWebSearchHelpfulTopic = (query = '', condition = {}, searchPlan = {}) => {
  if (getAiWebSearchCategories(condition, searchPlan).some((category) => {
    return AI_WEB_SEARCH_HELPFUL_CATEGORIES.has(category)
  })) {
    return true
  }

  return hasAiWebSearchKeyword(AI_WEB_SEARCH_HELPFUL_KEYWORDS, query, condition, searchPlan)
}

export const isAiWebSearchInfraBlockedTopic = (query = '', condition = {}, searchPlan = {}) => {
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
    getFrameDisplayLabel(searchPlan),
    ...getFrameCandidatePlaceTypes(searchPlan),
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

export const getBackendResultMessageSuffix = ({
  dbCount = 0,
  externalCount = 0,
  kakaoCount = 0,
  scenarioLabel = '',
  unifiedOrder = true,
} = {}) => {
  const parts = []

  if (dbCount > 0) {
    parts.push(`저장 장소 ${dbCount}개`)
  }

  if (externalCount > 0) {
    parts.push(`참고 정보 ${externalCount}개`)
  }

  if (!unifiedOrder && kakaoCount > 0) {
    parts.push(`카카오 ${kakaoCount}개`)
  }

  if (!parts.length) {
    parts.push('조건에 맞는 후보')
  }

  parts.push('추천순')

  if (scenarioLabel && /[가-힣]/.test(scenarioLabel) && !/_/.test(scenarioLabel)) {
    parts.push(scenarioLabel)
  }

  return parts.join(' · ')
}

export const stableStringify = (value) => {
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

export const getAiWebSearchRequestKey = (context) => {
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

export const getAiWebSearchStatusMessage = (result = {}) => {
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
