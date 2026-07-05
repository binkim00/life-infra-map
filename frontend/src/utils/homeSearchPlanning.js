import {
  ABSTRACT_TARGET_KEYWORDS,
  ANCILLARY_INTENT_CATEGORIES,
  ANCILLARY_PLACE_KEYWORDS,
  CATEGORY_KAKAO_KEYWORDS,
  CATEGORY_KEYWORD_MAP,
  GENERIC_CONDITION_TARGETS,
  INTENT_KAKAO_KEYWORD_CANDIDATES,
  INTENT_NEGATIVE_TAGS,
  INTENT_PREFERRED_TAGS,
  REQUEST_CONDITION_RULES,
  RESTAURANT_INTENT_KEYWORDS,
  SMOKING_INTENT_KEYWORDS,
  TYPO_CORRECTION_MAP,
  WAITING_PLACE_KEYWORDS,
  WALK_HEALING_KEYWORDS,
  WORK_CAFE_KEYWORDS,
  WORK_CAFE_PREFERRED_TAGS,
} from '@/constants/homeSearchConstants'
import {
  buildFrameBasedKakaoKeywords,
  filterKeywordsByExclusions,
  getExcludedTermsFromPlan,
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
  getPlanKakaoKeywordCandidates,
  getPlannerBoolean,
  getPlannerList,
  getPlannerText,
  getResolvedSearchPlanLocationQuery,
  getSearchPlanDebugSnapshot,
  getSearchPlanFrame,
  getSearchPlanValue,
  getTagDetailTextValues,
  getTagName,
  getTagTextValues,
  getTextValue,
  hasValidSearchIntentFrame,
  isFrameDrivenSearch,
  normalizeLocationText,
  syncFrameLocationToSearchPlan,
  toDisplayList,
} from '@/utils/homePlaceHelpers'

export const getRegionTokens = (query) => {
  return String(query)
    .replace(/[^\w가-힣\s]/g, ' ')
    .split(/\s+/)
    .map((token) => token.trim())
    .filter((token) => /[시도군구읍면동리]$/.test(token) && token.length >= 2)
}

export const hasRegionQualifier = (query) => {
  return getRegionTokens(query).some((token) => /[시도군구]$/.test(token))
}

export const BASE_LOCATION_POI_KEYWORDS = [
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

export const hasPoiHint = (query) => {
  const queryText = normalizeLocationText(query)
  return BASE_LOCATION_POI_KEYWORDS.some((keyword) => {
    return queryText.includes(normalizeLocationText(keyword))
  })
}

export const parseMapSearchInput = (keyword) => {
  const normalizedKeyword = keyword.replace(/\s+/g, ' ').trim()
  const currentContextPattern = /^(현재\s*위치|내\s*주변|내\s*근처|이\s*근처|이\s*주변|이\s*지도|지도|현재\s*지도)\s*(?:주변|근처|인근|가까운)?(?:에서|의)?\s*(.+)$/
  const currentContextMatched = normalizedKeyword.match(currentContextPattern)
  const currentContextPrefixPattern = /^(근처|주변|인근|가까운|가까이)(?:에|에서|의)?\s+(.+)$/
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

export const REGION_TARGET_HINT_KEYWORDS = [
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

export const NON_REGION_LOCATION_WORDS = [
  '조용한',
  '조용히',
  '가까운',
  '가까이',
  '혼자',
  '혼밥',
  '사람',
  '사람많은',
  '붐비는',
  '밖',
  '실외',
  '노트북',
  '작업',
  '공부',
  '잠깐',
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

export const isValidAroundBaseLocation = (baseKeyword = '') => {
  const baseText = normalizeLocationText(baseKeyword)

  if (!baseText) return false

  return !isNonRegionLocationText(baseText)
}

export const isNonRegionLocationText = (locationText = '') => {
  const normalizedLocationText = normalizeLocationText(locationText)

  return NON_REGION_LOCATION_WORDS.some((word) => {
    const wordText = normalizeLocationText(word)
    return (
      normalizedLocationText === wordText ||
      normalizedLocationText === `${wordText}에` ||
      normalizedLocationText === `${wordText}에서` ||
      normalizedLocationText === `${wordText}의`
    )
  })
}

export const isLikelyRegionSearchPair = (locationQuery, targetQuery) => {
  const locationText = normalizeLocationText(locationQuery)
  const targetText = normalizeLocationText(targetQuery)

  if (!locationText || !targetText) return false

  if (isNonRegionLocationText(locationText)) {
    return false
  }

  if (isRecommendationQueryText(locationQuery)) {
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

export const RECOMMENDATION_QUERY_HINTS = [
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
  '혼밥',
  '찾아줘',
  '찾아',
  '갈만한',
  '좋은곳',
  '좋은 곳',
  '식당',
  '밥집',
  '음식점',
  '맛집',
  '브런치',
  '카페',
  '쉼터',
  '쉴',
  '쉬',
  '힐링',
  '산책',
  '공원',
  '화장실',
  '주차장',
  '흡연',
  '가능',
  '가볼',
  '추천',
]

export const isRecommendationQueryText = (query = '') => {
  const queryText = normalizeLocationText(query)
  return RECOMMENDATION_QUERY_HINTS.some((keyword) => {
    return queryText.includes(normalizeLocationText(keyword))
  })
}

export const getCategoryHint = (query = '') => {
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

export const normalizeSearchQuery = (query = '') => {
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

export const getTargetType = ({ targetQuery = '', categoryHint = '' }) => {
  const targetText = normalizeLocationText(targetQuery)

  if (categoryHint) return 'category'

  if (ABSTRACT_TARGET_KEYWORDS.some((keyword) => {
    return targetText.includes(normalizeLocationText(keyword))
  })) {
    return 'abstract'
  }

  return targetQuery.trim() ? 'unknown' : 'unknown'
}

export const getRecommendationIntent = (query = '') => {
  const queryText = normalizeLocationText(query)
  const hasRestaurantKeyword = RESTAURANT_INTENT_KEYWORDS.some((keyword) => {
    return queryText.includes(normalizeLocationText(keyword))
  })
  const hasWorkCafeKeyword = WORK_CAFE_KEYWORDS.some((keyword) => {
    return queryText.includes(normalizeLocationText(keyword))
  })

  if (hasRestaurantKeyword) {
    return 'restaurant'
  }

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

export const getPreferredTagsForIntent = (intent = '') => {
  return INTENT_PREFERRED_TAGS[intent] || []
}

export const getNegativeTagsForIntent = (intent = '') => {
  return INTENT_NEGATIVE_TAGS[intent] || []
}

export const getKakaoKeywordCandidates = ({
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

export function toArray(value) {
  if (Array.isArray(value)) return value
  if (value === null || value === undefined) return []
  return [value]
}

export const hasRequestedConditionKeyword = (text = '', rule) => {
  const normalizedText = normalizeLocationText(text)
  return toArray(rule?.keywords).some((keyword) => {
    return normalizedText.includes(normalizeLocationText(keyword))
  })
}

export const cleanupConditionTargetText = (text = '', conditions = []) => {
  let cleaned = text

  toArray(conditions).forEach((condition) => {
    toArray(condition?.cleanupPatterns).forEach((pattern) => {
      cleaned = cleaned.replace(pattern, ' ')
    })
  })

  return cleaned
    .replace(/\s+/g, ' ')
    .replace(/^(?:에서|에|의)\s+/, '')
    .replace(/\s*(?:인|인 곳|인 장소|인 데)$/g, '')
    .replace(/\s*(?:있는|가능한|추천해줘|추천|찾아줘|찾아)$/g, '')
    .trim()
}

export const isGenericConditionTarget = (target = '') => {
  const normalizedTarget = normalizeLocationText(target)
  if (!normalizedTarget) return true

  return GENERIC_CONDITION_TARGETS.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return normalizedTarget === normalizedKeyword || normalizedTarget.endsWith(normalizedKeyword)
  })
}

export const extractRequestedConditions = (query = '', rawTargetQuery = '') => {
  const matchedConditions = REQUEST_CONDITION_RULES.filter((rule) => {
    return hasRequestedConditionKeyword(query, rule) || hasRequestedConditionKeyword(rawTargetQuery, rule)
  })

  if (!matchedConditions.length) {
    return {
      requestedConditions: [],
      targetQuery: rawTargetQuery,
      hasExplicitConditionTarget: false,
    }
  }

  const cleanedTargetQuery = cleanupConditionTargetText(rawTargetQuery, matchedConditions)
  const hasExplicitConditionTarget = Boolean(cleanedTargetQuery) && !isGenericConditionTarget(cleanedTargetQuery)

  return {
    requestedConditions: matchedConditions,
    targetQuery: hasExplicitConditionTarget ? cleanedTargetQuery : rawTargetQuery,
    hasExplicitConditionTarget,
  }
}

export const getRequestedConditionEvidenceText = (place = {}) => {
  const tagDetails = toDisplayList(toArray(place.tagDetails || place.tag_details).map((tag) => tag?.name))
  return [
    place.name,
    place.category,
    place.rawCategory,
    ...toArray(place.tags).map((tag) => getTagName(tag)),
    ...toArray(place.suggestedTags || place.suggested_tags),
    ...toArray(place.verifiedTags || place.verified_tags),
    ...toArray(place.warningTags || place.warning_tags),
    ...toArray(place.matchedTags || place.matched_tags),
    ...toArray(place.matchedTagLabels || place.matched_tag_labels),
    ...tagDetails,
  ].filter(Boolean).join(' ')
}

export const getRequestedConditionReview = (place = {}, requestedConditions = []) => {
  const evidenceText = normalizeLocationText(getRequestedConditionEvidenceText(place))
  const matchedLabels = []
  const missingLabels = []
  const safeConditions = toArray(requestedConditions).filter((condition) => {
    return condition && typeof condition === 'object'
  })

  safeConditions.forEach((condition) => {
    const evidenceKeywords = toArray(condition.evidenceKeywords)
    if (!evidenceKeywords.length) return

    const hasEvidence = evidenceKeywords.some((keyword) => {
      const evidenceKeyword = normalizeLocationText(keyword)
      return evidenceText.includes(evidenceKeyword)
    })

    if (hasEvidence) {
      const matchLabel = getTextValue(condition.matchLabel)
      if (matchLabel) matchedLabels.push(matchLabel)
      return
    }

    const missingLabel = getTextValue(condition.missingLabel)
    if (missingLabel) missingLabels.push(missingLabel)
  })

  return {
    matchedLabels: [...new Set(matchedLabels)],
    missingLabels: [...new Set(missingLabels)],
  }
}

export const mergeRequestedConditionReview = (place = {}, requestedConditions = []) => {
  const safeConditions = toArray(requestedConditions).filter((condition) => {
    return condition && typeof condition === 'object'
  })
  if (!safeConditions.length) return place

  const review = getRequestedConditionReview(place, safeConditions)
  const missingLabels = [...new Set([
    ...toDisplayList(place.missingTagLabels || place.missing_tag_labels),
    ...review.missingLabels,
  ])]
  const matchedLabels = [...new Set([
    ...toDisplayList(place.matchedTagLabels || place.matched_tag_labels),
    ...review.matchedLabels,
  ])]
  const caution = missingLabels.length
    ? '요청한 조건은 현재 데이터로 확인되지 않았습니다. 방문 전 확인이 필요합니다.'
    : getTextValue(place.recommendationCaution || place.caution_message || place.caution)

  return {
    ...place,
    requestedConditionIds: safeConditions.map((condition) => condition.id).filter(Boolean),
    matchedTagLabels: matchedLabels,
    matched_tag_labels: matchedLabels,
    missingTagLabels: missingLabels,
    missing_tag_labels: missingLabels,
    recommendationCaution: caution,
    caution_message: caution,
  }
}

export const getMainPlaceFallbackKeyword = (query = '') => {
  let keyword = query.trim()

  ANCILLARY_PLACE_KEYWORDS
    .slice()
    .sort((first, second) => second.length - first.length)
    .forEach((ancillaryKeyword) => {
      keyword = keyword.replace(new RegExp(`${ancillaryKeyword}$`), '').trim()
    })

  return keyword && keyword !== query.trim() ? keyword : ''
}

export const getMainPlaceKeywordFromAncillaryName = (name = '') => {
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

export const getMainPlaceFallbackKeywordsFromResults = (places = [], fallbackKeyword = '') => {
  const resultKeywords = places
    .map((place) => getMainPlaceKeywordFromAncillaryName(place.place_name || place.name || ''))
    .filter(Boolean)

  return [...new Set([fallbackKeyword, ...resultKeywords].filter(Boolean))]
}

export const buildSearchPlan = (query) => {
  const correction = normalizeSearchQuery(query)
  const parsed = parseMapSearchInput(correction.normalizedQuery)
  const rawTargetQuery = parsed.targetQuery || parsed.targetKeyword || correction.normalizedQuery
  const conditionPlan = extractRequestedConditions(correction.normalizedQuery, rawTargetQuery)
  const targetQuery = conditionPlan.targetQuery || rawTargetQuery
  const categoryHint = getCategoryHint(targetQuery)
  const recommendationIntent = conditionPlan.hasExplicitConditionTarget
    ? getRecommendationIntent(targetQuery)
    : getRecommendationIntent(`${correction.normalizedQuery} ${targetQuery}`)
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
    requestedConditions: conditionPlan.requestedConditions,
    hasExplicitConditionTarget: conditionPlan.hasExplicitConditionTarget,
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

export const cloneSearchPlanForMapCenter = (searchPlan = {}, keyword = '') => {
  const sourcePlan = searchPlan && typeof searchPlan === 'object' ? searchPlan : {}
  const fallbackPlan = buildSearchPlan(keyword)
  const basePlan = Object.keys(sourcePlan).length ? sourcePlan : fallbackPlan
  const frame = {
    ...getSearchPlanFrame(basePlan),
    anchor_location: '',
    anchorLocation: '',
    location: '',
    location_mode: 'current_context',
    locationMode: 'current_context',
  }
  const targetQuery = getPlannerText(
    getSearchPlanValue(basePlan, 'targetQuery', 'target_query') ||
    getFrameDisplayLabel(basePlan) ||
    fallbackPlan.targetQuery ||
    keyword,
  )
  const targetKeyword = getPlannerText(
    getSearchPlanValue(basePlan, 'targetKeyword', 'target_keyword') ||
    basePlan.categoryKeyword ||
    targetQuery,
  )

  return {
    ...fallbackPlan,
    ...basePlan,
    originalQuery: keyword || basePlan.originalQuery || basePlan.normalizedQuery || targetQuery,
    normalizedQuery: keyword || basePlan.normalizedQuery || basePlan.originalQuery || targetQuery,
    locationQuery: '',
    location_query: '',
    baseLocationQuery: '',
    base_location_query: '',
    anchorLocation: '',
    anchor_location: '',
    hasBaseLocation: false,
    hasExplicitLocation: false,
    has_explicit_location: false,
    locationResolutionRequired: false,
    location_resolution_required: false,
    explicitCurrentContext: true,
    searchMode: 'current_context',
    baseKeyword: '',
    targetQuery,
    target_query: targetQuery,
    targetKeyword,
    target_keyword: targetKeyword,
    locationMode: 'current_context',
    location_mode: 'current_context',
    place_intent_frame: frame,
    placeIntentFrame: frame,
  }
}

export const getPlaceExclusionText = (place = {}) => {
  return normalizeLocationText([
    place.category_name,
    place.category_group_name,
    place.categoryGroupName,
    place.category,
    place.rawCategory,
    place.place_name,
    place.name,
    ...getTagTextValues(place.tags),
    ...getTagTextValues(place.verifiedTags || place.verified_tags),
    ...getTagTextValues(place.suggestedTags || place.suggested_tags),
    ...toDisplayList(place.placeNatures || place.place_natures),
  ].filter(Boolean).join(' '))
}

export const isPlaceExcludedByPlan = (place = {}, searchPlan = {}) => {
  const excludedTerms = getExcludedTermsFromPlan(searchPlan)
  if (!excludedTerms.length) return false

  const placeText = getPlaceExclusionText(place)
  return excludedTerms.some((term) => term && placeText.includes(term))
}

export const filterPlacesByPlanExclusions = (places = [], searchPlan = {}) => {
  if (!getExcludedTermsFromPlan(searchPlan).length) return places
  return places.filter((place) => !isPlaceExcludedByPlan(place, searchPlan))
}

export const hasKakaoWorkCafeEvidence = (place = {}, savedTagData = {}) => {
  const evidenceText = normalizeLocationText([
    place.place_name,
    place.name,
    place.category_name,
    place.category,
    ...getTagTextValues(savedTagData.suggested_tags),
    ...getTagTextValues(savedTagData.verified_tags),
    ...getTagDetailTextValues(savedTagData.tag_details),
  ].filter(Boolean).join(' '))

  return [
    ...WORK_CAFE_PREFERRED_TAGS,
    '노트북',
    '작업',
    '공부',
    '조용',
    '와이파이',
    'wifi',
    'wi-fi',
    '콘센트',
    '전원',
    '충전',
    '스터디',
  ].some((keyword) => {
    return evidenceText.includes(normalizeLocationText(keyword))
  })
}

export const getFrameDirectMatchText = (place = {}) => {
  return normalizeLocationText([
    place.category,
    place.category_name,
    place.category_group_name,
    place.categoryGroupName,
    place.rawCategory,
    ...toDisplayList(place.matchedCategoryCodes || place.matched_category_codes),
    ...getTagTextValues(place.matchedTags || place.matched_tags),
    ...getTagTextValues(place.matchedTagLabels || place.matched_tag_labels),
    ...getTagTextValues(place.verifiedTags || place.verified_tags),
    ...getTagTextValues(place.suggestedTags || place.suggested_tags),
    ...getTagTextValues(place.tags),
  ].filter(Boolean).join(' '))
}

export const isFrameDirectMatchedPlace = (place = {}, searchPlan = {}) => {
  if (Number(place.relevanceScore || place.relevance_score || 0) > 0) {
    return true
  }

  if (toArray(place.matchedEvidence || place.matched_evidence).length > 0) {
    return true
  }

  const matchTerms = [
    ...getFrameCandidateCategoryCodes(searchPlan),
    ...getFrameResultMatchTerms(searchPlan),
    ...getFrameCandidatePlaceTypes(searchPlan),
  ]
  if (!matchTerms.length) return true

  const matchText = getFrameDirectMatchText(place)
  return matchTerms.some((matchTerm) => {
    const termText = normalizeLocationText(matchTerm)
    return termText && matchText.includes(termText)
  })
}

export const getFrameDirectMatchCount = (results = [], searchPlan = {}) => {
  if (!isFrameDrivenSearch(searchPlan)) return results.length
  return results.filter((place) => isFrameDirectMatchedPlace(place, searchPlan)).length
}

export const filterFrameDirectMatchedResults = (results = [], searchPlan = {}) => {
  if (!isFrameDrivenSearch(searchPlan)) return results
  return results.filter((place) => isFrameDirectMatchedPlace(place, searchPlan))
}

export const adaptConversationalSearchPlan = (conversationalPlan, originalQuery) => {
  const plan = conversationalPlan?.search_plan || {}
  const hasAiFramePlan = hasValidSearchIntentFrame(plan) &&
    conversationalPlan?.parser_fallback !== true &&
    conversationalPlan?.plan_source !== 'legacy_fallback'
  const basePlan = hasAiFramePlan
    ? {
      originalQuery,
      normalizedQuery: originalQuery,
      locationQuery: '',
      baseLocationQuery: '',
      hasBaseLocation: false,
      explicitCurrentContext: true,
      searchMode: 'current_context',
      baseKeyword: '',
      targetQuery: getFrameDisplayLabel(plan) || originalQuery,
      targetKeyword: getFrameDisplayLabel(plan) || originalQuery,
      targetType: '',
      categoryHint: '',
      categoryKeyword: '',
      recommendationIntent: getPlannerText(plan?.scenario || ''),
      requestedConditions: [],
      preferredTags: [],
      negativeTags: [],
      kakaoKeywordCandidates: [],
      mainPlaceFallbackKeyword: '',
      confidence: conversationalPlan?.confidence ?? null,
      fallbackReason: conversationalPlan?.fallback_reason || '',
    }
    : buildSearchPlan(originalQuery)

  if (!plan || typeof plan !== 'object') {
    return basePlan
  }

  const frameLocationMode = getFrameLocationMode(plan)
  const frameAnchorLocation = getFrameAnchorLocation(plan)
  const locationQuery = getPlannerText(
    getResolvedSearchPlanLocationQuery(plan) ||
    (frameLocationMode === 'explicit' ? frameAnchorLocation : ''),
  )
  const hasExplicitLocation = getPlannerBoolean(
    getSearchPlanValue(plan, 'has_explicit_location'),
    Boolean(locationQuery || frameLocationMode === 'explicit'),
  )
  const locationResolutionRequired = getPlannerBoolean(
    getSearchPlanValue(plan, 'location_resolution_required'),
    Boolean(locationQuery || frameLocationMode === 'explicit'),
  )
  const shouldUseLocationQuery = Boolean(locationQuery && hasExplicitLocation && locationResolutionRequired)
  const targetQuery = getPlannerText(
    getSearchPlanValue(plan, 'targetQuery', 'target_query') ||
    getFrameDisplayLabel(plan) ||
    basePlan.targetQuery ||
    originalQuery,
  )
  const placeIntentFrame = getSearchPlanFrame(plan)
  const candidatePlaceTypes = getFrameCandidatePlaceTypes(plan)
  const targetObjects = getFrameTargetObjects(plan)
  const frameConstraints = getFrameConstraints(plan)
  const exclusions = getFrameExclusions(plan)
  const excludedCategories = getPlannerList(
    getSearchPlanValue(placeIntentFrame, 'excluded_categories', 'excludedCategories') ||
    getSearchPlanValue(plan, 'excludedCategories', 'excluded_categories'),
  )
  const displayLabel = getFrameDisplayLabel(plan)
  const displayLabelSource = getPlannerText(
    getSearchPlanValue(placeIntentFrame, 'display_label_source', 'displayLabelSource') ||
    getSearchPlanValue(plan, 'displayLabelSource', 'display_label_source'),
  )
  const webSearchQueries = filterKeywordsByExclusions(getFrameWebSearchQueries(plan), plan)
  const intentGroup = getPlannerText(
    getSearchPlanValue(plan, 'intentGroup', 'intent_group') ||
    getSearchPlanValue(placeIntentFrame, 'intent_group', 'intentGroup', 'situation'),
  )
  const categoryCandidates = getPlannerList(
    getSearchPlanValue(plan, 'categoryCandidates', 'category_candidates'),
  )
  const categories = [
    ...getPlannerList(plan.categories),
    ...categoryCandidates,
  ].filter((category, index, list) => category && list.indexOf(category) === index)
  const categoryHint = getPlannerText(getSearchPlanValue(plan, 'categoryHint', 'category_hint')) ||
    categories[0] ||
    (hasAiFramePlan ? '' : basePlan.categoryHint)
  const categoryKeyword = CATEGORY_KAKAO_KEYWORDS[categoryHint] || basePlan.categoryKeyword
  const recommendationIntent = getPlannerText(plan.scenario) || basePlan.recommendationIntent
  const menuKeywords = getPlannerList(plan.menu_keywords)
  const placeTypeKeywords = [
    ...getPlannerList(getSearchPlanValue(plan, 'place_type_keywords', 'placeTypeKeywords')),
    ...candidatePlaceTypes,
  ].filter((keyword, index, list) => keyword && list.indexOf(keyword) === index)
  const requestedConditions = [
    ...getPlannerList(
      getSearchPlanValue(plan, 'requestedConditions', 'requested_conditions') ||
      conversationalPlan.conditions ||
      (hasAiFramePlan ? [] : basePlan.requestedConditions),
    ),
    ...frameConstraints,
  ].filter((condition, index, list) => condition && list.indexOf(condition) === index)
  const preferredTags = getPlannerList(plan.preferred_tags).length
    ? getPlannerList(plan.preferred_tags)
    : (hasAiFramePlan ? [] : basePlan.preferredTags)
  const negativeTags = getPlannerList(plan.negative_tags).length
    ? getPlannerList(plan.negative_tags)
    : (hasAiFramePlan ? [] : basePlan.negativeTags)
  const targetType = getPlannerText(getSearchPlanValue(plan, 'targetType', 'target_type')) ||
    (hasAiFramePlan ? '' : getTargetType({ targetQuery, categoryHint }))
  const fallbackKakaoKeywordCandidates = getKakaoKeywordCandidates({
    targetQuery,
    targetType,
    categoryKeyword,
    recommendationIntent,
  })
  const hasFramePlaceTypes = candidatePlaceTypes.length > 0
  const hasBackendKakaoCandidates = getPlanKakaoKeywordCandidates(plan).length > 0
  const kakaoKeywordCandidates = filterKeywordsByExclusions(
    hasFramePlaceTypes || hasBackendKakaoCandidates
      ? buildFrameBasedKakaoKeywords(plan, { includeWebQueries: false })
      : fallbackKakaoKeywordCandidates,
    plan,
  )

  const adaptedPlan = {
    ...basePlan,
    originalQuery,
    normalizedQuery: originalQuery,
    locationQuery: shouldUseLocationQuery ? locationQuery : '',
    baseLocationQuery: shouldUseLocationQuery ? locationQuery : '',
    anchorLocation: shouldUseLocationQuery ? locationQuery : frameAnchorLocation,
    anchor_location: shouldUseLocationQuery ? locationQuery : frameAnchorLocation,
    hasBaseLocation: shouldUseLocationQuery,
    hasExplicitLocation: shouldUseLocationQuery,
    locationResolutionRequired: shouldUseLocationQuery,
    explicitCurrentContext: !shouldUseLocationQuery,
    searchMode: shouldUseLocationQuery ? 'region_search' : 'current_context',
    baseKeyword: shouldUseLocationQuery ? locationQuery : '',
    targetQuery,
    targetKeyword: kakaoKeywordCandidates[0] || categoryKeyword || targetQuery,
    targetType,
    categoryHint,
    categoryKeyword,
    recommendationIntent,
    requestedConditions,
    preferredTags,
    negativeTags,
    place_intent_frame: placeIntentFrame,
    placeIntentFrame: placeIntentFrame,
    target_objects: targetObjects,
    targetObjects,
    candidate_place_types: candidatePlaceTypes,
    candidatePlaceTypes,
    constraints: frameConstraints,
    exclusions,
    excluded_categories: excludedCategories,
    excludedCategories,
    display_label: displayLabel,
    displayLabel,
    display_label_source: displayLabelSource,
    displayLabelSource,
    web_search_queries: webSearchQueries,
    webSearchQueries,
    kakaoKeywordCandidates,
    kakao_keywords: kakaoKeywordCandidates,
    kakaoKeywords: kakaoKeywordCandidates,
    categoryCandidates,
    intent_group: intentGroup,
    intentGroup,
    location_mode: frameLocationMode,
    locationMode: frameLocationMode,
    candidate_category_codes: getFrameCandidateCategoryCodes(plan),
    candidateCategoryCodes: getFrameCandidateCategoryCodes(plan),
    result_match_terms: getFrameResultMatchTerms(plan),
    resultMatchTerms: getFrameResultMatchTerms(plan),
    ranking_policy: getFrameRankingPolicy(plan),
    rankingPolicy: getFrameRankingPolicy(plan),
    decision_action: conversationalPlan?.decision_action || conversationalPlan?.action || plan?.decision_action || '',
    decisionAction: conversationalPlan?.decisionAction || conversationalPlan?.decision_action || conversationalPlan?.action || plan?.decisionAction || '',
    can_search_now: conversationalPlan?.can_search_now ?? plan?.can_search_now ?? conversationalPlan?.action === 'search',
    canSearchNow: conversationalPlan?.canSearchNow ?? conversationalPlan?.can_search_now ?? plan?.canSearchNow ?? plan?.can_search_now ?? conversationalPlan?.action === 'search',
    clarification_options: getPlannerList(conversationalPlan?.clarification_options || conversationalPlan?.clarificationOptions || plan?.clarification_options || plan?.clarificationOptions || []),
    clarificationOptions: getPlannerList(conversationalPlan?.clarification_options || conversationalPlan?.clarificationOptions || plan?.clarification_options || plan?.clarificationOptions || []),
    parser_provider: conversationalPlan?.parser_provider || plan?.parser_provider || '',
    parserProvider: conversationalPlan?.parser_provider || plan?.parserProvider || '',
    parser_fallback: conversationalPlan?.parser_fallback ?? plan?.parser_fallback ?? null,
    parserFallback: conversationalPlan?.parser_fallback ?? plan?.parserFallback ?? null,
    execution_mode: hasAiFramePlan ? 'frame' : (conversationalPlan?.execution_mode || 'legacy'),
    executionMode: hasAiFramePlan ? 'frame' : (conversationalPlan?.execution_mode || 'legacy'),
    plan_source: hasAiFramePlan ? (conversationalPlan?.plan_source || 'ai') : (conversationalPlan?.plan_source || 'legacy_fallback'),
    planSource: hasAiFramePlan ? (conversationalPlan?.plan_source || 'ai') : (conversationalPlan?.plan_source || 'legacy_fallback'),
    ai_fallback_reason: conversationalPlan?.ai_fallback_reason || plan?.ai_fallback_reason || '',
    aiFallbackReason: conversationalPlan?.ai_fallback_reason || plan?.aiFallbackReason || '',
    ai_debug: conversationalPlan?.ai_debug || plan?.ai_debug || null,
    aiDebug: conversationalPlan?.ai_debug || plan?.aiDebug || null,
    menu_keywords: menuKeywords,
    place_type_keywords: placeTypeKeywords,
    conversationalSearchPlan: conversationalPlan,
    userIntentSummary: conversationalPlan?.user_intent_summary || '',
    executionPolicy: conversationalPlan?.execution_policy || {},
    confidence: conversationalPlan?.confidence ?? basePlan.confidence,
    fallbackReason: conversationalPlan?.fallback_reason || basePlan.fallbackReason,
    aiSearchPlanApplied: true,
  }
  syncFrameLocationToSearchPlan(adaptedPlan)

  if (import.meta.env.DEV) {
    console.debug('[대화형 검색 해석 적용]', getSearchPlanDebugSnapshot(adaptedPlan, {
      rawQuery: originalQuery,
    }))
  }

  return adaptedPlan
}

export const LOCATION_CHOICE_CLARIFICATION_MESSAGE = '현재 위치 기준으로 찾아볼까요, 아니면 원하는 지역이 있나요? 예: 현재 위치, 서면, 하단역, 광안리'

export const CURRENT_CONTEXT_SEARCH_REQUEST_KEYWORDS = [
  '현재 위치',
  '현재위치',
  '내 주변',
  '내주변',
  '내 근처',
  '내근처',
  '이 근처',
  '이근처',
  '이 주변',
  '이주변',
  '근처',
  '주변',
]

export const hasExplicitCurrentContextSearchRequest = (query = '') => {
  const text = normalizeLocationText(query)
  return CURRENT_CONTEXT_SEARCH_REQUEST_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
}

export const isNaturalLanguageScenarioSearch = (searchPlan = {}, rawQuery = '') => {
  const scenario = getPlannerText(searchPlan.scenario)
  if (!['waiting_place', 'work_cafe', 'walk_healing'].includes(scenario)) return false

  const conditions = getPlannerList(
    searchPlan.requestedConditions ||
    searchPlan.requested_conditions ||
    searchPlan.conditions ||
    [],
  )

  return conditions.length > 0 || isRecommendationQueryText(rawQuery)
}

export const shouldAskLocationChoiceBeforeSearch = ({
  conversationalPlan = null,
  rawQuery = '',
  allowImplicitCurrentContext = false,
} = {}) => {
  if (allowImplicitCurrentContext) return false
  if (!conversationalPlan || conversationalPlan.action !== 'search') return false
  if (hasExplicitCurrentContextSearchRequest(rawQuery)) return false

  const searchPlan = conversationalPlan.search_plan || {}
  const locationQuery = getPlannerText(getSearchPlanValue(searchPlan, 'locationQuery', 'location_query'))
  if (locationQuery) return false
  if (getFrameAnchorLocation(searchPlan)) return false
  if (isFrameDrivenSearch(searchPlan)) {
    return getFrameLocationMode(searchPlan) === 'clarification_required'
  }

  if (getFrameCandidatePlaceTypes(searchPlan).length && !isNaturalLanguageScenarioSearch(searchPlan, rawQuery)) {
    return false
  }

  const hasExplicitLocation = getPlannerBoolean(
    getSearchPlanValue(searchPlan, 'has_explicit_location'),
    false,
  )
  if (hasExplicitLocation) return false

  return isNaturalLanguageScenarioSearch(searchPlan, rawQuery)
}

export const makeLocationChoiceClarificationPlan = (conversationalPlan = {}, rawQuery = '') => {
  const searchPlan = conversationalPlan.search_plan && typeof conversationalPlan.search_plan === 'object'
    ? { ...conversationalPlan.search_plan }
    : {}
  const conditions = getPlannerList(
    searchPlan.requestedConditions ||
    searchPlan.requested_conditions ||
    searchPlan.conditions ||
    conversationalPlan.conditions ||
    [],
  )

  return {
    ...conversationalPlan,
    action: 'ask_clarification',
    message: LOCATION_CHOICE_CLARIFICATION_MESSAGE,
    needs_clarification: true,
    clarification_question: LOCATION_CHOICE_CLARIFICATION_MESSAGE,
    search_plan: {
      ...searchPlan,
      locationQuery: '',
      baseLocationQuery: '',
      has_explicit_location: false,
      location_resolution_required: false,
      requestedConditions: conditions,
      conditions,
    },
    conditions,
    execution_policy: {
      ...(conversationalPlan.execution_policy || {}),
      run_search: false,
      preserve_explicit_location: false,
    },
    fallback_reason: 'location_choice_required',
    location_choice_required: true,
    original_query: rawQuery,
  }
}

export const getUnifiedSearchMode = (keyword, parsedKeyword, { useMapBounds = false } = {}) => {
  if (useMapBounds) {
    return 'recommendation_query'
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
