import {
  ANCILLARY_PLACE_KEYWORDS,
  DESTINATION_CATEGORY_KEYWORDS,
  TAKEOUT_HEAVY_KEYWORDS,
  WAITING_PLACE_EXCLUDE_KEYWORDS,
  WAITING_PLACE_PENALTY_KEYWORDS,
  WAITING_PLACE_PREFERRED_KEYWORDS,
  WALK_HEALING_ALLOWED_KEYWORDS,
  WALK_HEALING_CAFE_KEYWORDS,
  WALK_HEALING_EXCLUDE_KEYWORDS,
} from '@/constants/homeSearchConstants'
import {
  getDistanceMetersBetweenPlaces,
  getTagTextValues,
  hasExplicitWalkCafeIntent,
  normalizeLocationText,
} from '@/utils/homePlaceHelpers'
import {
  getMainPlaceFallbackKeywordsFromResults,
  toArray,
} from '@/utils/homeSearchPlanning'
import {
  dedupeKakaoRawPlaces,
  runKakaoKeywordCandidateSearch,
} from '@/utils/kakaoSearchHelpers'

export const makeTag = (name, source) => {
  return {
    name,
    source,
  }
}

export const makeKakaoResultTags = (place, savedTagData = {}) => {
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

export const getSavedTagNames = (savedTagData = {}) => {
  return [
    ...(savedTagData.suggested_tags || []),
    ...(savedTagData.verified_tags || []),
  ].filter(Boolean)
}

export const hasSavedTagMatch = (savedTagData = {}) => {
  return Boolean(
    savedTagData.saved_place_id ||
    getSavedTagNames(savedTagData).length ||
    (savedTagData.warning_tags || []).length,
  )
}

export const isTakeoutHeavyCafeCandidate = (place = {}) => {
  const placeText = normalizeLocationText(
    `${place.place_name || place.name || ''} ${place.category_name || place.category || ''}`,
  )

  return TAKEOUT_HEAVY_KEYWORDS.some((keyword) => {
    return placeText.includes(normalizeLocationText(keyword))
  })
}

export const getPlaceTextForRule = (place = {}, extraTags = []) => {
  return normalizeLocationText([
    place.place_name,
    place.name,
    place.category_name,
    place.category,
    place.address_name,
    place.road_address_name,
    place.address,
    place.detailLocation,
    place.__fallbackQuery,
    place.fallbackQuery,
    place.kakaoFallbackQuery,
    ...extraTags,
  ].filter(Boolean).join(' '))
}

export const getStructuredPlaceEvidenceText = (place = {}, extraTags = []) => {
  return normalizeLocationText([
    place.place_name,
    place.name,
    place.category_name,
    place.category_group_name,
    place.categoryGroupName,
    place.category,
    place.rawCategory,
    ...getTagTextValues(place.tags),
    ...getTagTextValues(place.matchedTags || place.matched_tags),
    ...getTagTextValues(place.verifiedTags || place.verified_tags),
    ...getTagTextValues(place.suggestedTags || place.suggested_tags),
    ...extraTags,
  ].filter(Boolean).join(' '))
}

export const getWaitingPlaceSuitability = (place = {}, savedTagData = {}) => {
  const text = getPlaceTextForRule(place, [
    ...(savedTagData.suggested_tags || []),
    ...(savedTagData.verified_tags || []),
    ...(savedTagData.warning_tags || []),
  ])

  const hasExcludedKeyword = WAITING_PLACE_EXCLUDE_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
  if (hasExcludedKeyword) {
    return {
      excluded: true,
      penalty: 140,
      bonus: 0,
      reason: 'limited_access_shelter',
    }
  }

  const hasPenaltyKeyword = WAITING_PLACE_PENALTY_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
  const hasPreferredKeyword = WAITING_PLACE_PREFERRED_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })

  return {
    excluded: false,
    penalty: hasPenaltyKeyword ? 65 : 0,
    bonus: hasPreferredKeyword ? 12 : 0,
    reason: hasPenaltyKeyword ? 'public_admin_penalty' : null,
  }
}

export const getAncillaryPlaceAdjustment = ({
  place = {},
  query = '',
  categoryHint = '',
  recommendationIntent = '',
  isAncillaryIntent = false,
}) => {
  const text = getPlaceTextForRule(place)
  const queryText = normalizeLocationText(query)
  const hasAncillaryKeyword = ANCILLARY_PLACE_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
  const hasDestinationKeyword = DESTINATION_CATEGORY_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
  const isDestinationCategory = ['city_park', 'tourism', 'beach'].includes(place.rawCategory || place.categoryHint || place.category)
  const normalizedName = normalizeLocationText(place.place_name || place.name || '')
  const mainPlaceScore = (
    (!hasAncillaryKeyword && (hasDestinationKeyword || isDestinationCategory)) ||
    (queryText && normalizedName === queryText)
  )
    ? 18
    : 0
  const shouldPenalizeAncillary = hasAncillaryKeyword && !isAncillaryIntent
  const walkOrNightIntent = recommendationIntent === 'walk_healing'
  const ancillaryPlacePenalty = shouldPenalizeAncillary ? (walkOrNightIntent ? 38 : 26) : 0
  const intentMismatchPenalty = shouldPenalizeAncillary && walkOrNightIntent ? 12 : 0

  return {
    mainPlaceScore,
    ancillaryPlacePenalty,
    intentMismatchPenalty,
    isAncillaryPlace: hasAncillaryKeyword,
  }
}

export const isAncillaryPlaceCandidate = (place = {}, searchContext = {}) => {
  return getAncillaryPlaceAdjustment({
    place,
    query: searchContext.query || '',
    categoryHint: searchContext.categoryHint || '',
    recommendationIntent: searchContext.recommendationIntent || '',
    isAncillaryIntent: searchContext.isAncillaryIntent || false,
  }).isAncillaryPlace
}

export const shouldTryMainPlaceFallbackSearch = (places = [], searchContext = {}) => {
  if (!places.length || searchContext.isAncillaryIntent) return false

  const hasMainPlaceCandidate = places.some((place) => {
    return !isAncillaryPlaceCandidate(place, searchContext)
  })

  return !hasMainPlaceCandidate
}

export const appendMainPlaceFallbackResults = async ({
  placesService,
  places = [],
  searchOptions = {},
  searchContext = {},
  fallbackKeyword = '',
}) => {
  if (!shouldTryMainPlaceFallbackSearch(places, searchContext)) {
    return places
  }

  const fallbackKeywords = getMainPlaceFallbackKeywordsFromResults(places, fallbackKeyword)

  if (!fallbackKeywords.length) {
    return places
  }

  const fallbackPlaces = await runKakaoKeywordCandidateSearch(
    placesService,
    fallbackKeywords,
    searchOptions,
    { maxPages: 1 },
  )

  if (!fallbackPlaces.length) {
    return places
  }

  return dedupeKakaoRawPlaces([...fallbackPlaces, ...places])
}

export const getTagConfidenceScore = (savedTagData = {}) => {
  const confidenceValues = (savedTagData.tag_details || [])
    .map((tag) => Number(tag.confidence ?? tag.score ?? tag.weight))
    .filter((value) => Number.isFinite(value))

  if (!confidenceValues.length) {
    return savedTagData.verified_tags?.length ? 8 : 4
  }

  const average = confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length
  return average <= 1 ? Math.round(average * 10) : Math.min(10, Math.round(average / 10))
}

export const getMatchedSavedTags = (savedTagData = {}, query = '', preferredTags = []) => {
  const queryText = normalizeLocationText(query)
  const tagNames = getSavedTagNames(savedTagData)
  const safePreferredTags = toArray(preferredTags)
  const preferredMatched = tagNames.filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return safePreferredTags.some((preferredTag) => {
      const preferredText = normalizeLocationText(preferredTag)
      return tagText && preferredText && (
        tagText.includes(preferredText) ||
        preferredText.includes(tagText)
      )
    })
  })
  const queryMatched = tagNames.filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return tagText && queryText && (queryText.includes(tagText) || tagText.includes(queryText))
  })
  const matched = [...new Set([...preferredMatched, ...queryMatched])]

  return matched.length ? matched : tagNames.slice(0, 4)
}

export const calculateKakaoTagRecommendation = ({
  place,
  savedTagData = {},
  query = '',
  center = null,
  preferredTags = [],
  recommendationIntent = '',
}) => {
  if (!hasSavedTagMatch(savedTagData)) {
    return {
      recommendScore: null,
      matchedTags: [],
      recommendationReason: '',
      recommendationConfidence: '',
      preferredMatchCount: 0,
    }
  }

  const matchedTags = getMatchedSavedTags(savedTagData, query, preferredTags)
  const warningTags = savedTagData.warning_tags || []
  const waitingSuitability = recommendationIntent === 'waiting_place'
    ? getWaitingPlaceSuitability(place, savedTagData)
    : { excluded: false, penalty: 0, bonus: 0, reason: null }
  const rawScores = savedTagData.raw_scores || {}
  const preferredMatchCount = matchedTags.filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return toArray(preferredTags).some((preferredTag) => {
      const preferredText = normalizeLocationText(preferredTag)
      return tagText.includes(preferredText) || preferredText.includes(tagText)
    })
  }).length
  const distance = center
    ? getDistanceMetersBetweenPlaces(
      { lat: center.lat, lng: center.lng },
      { lat: Number(place.y), lng: Number(place.x) },
    )
    : Number(place.distance || 0)
  const distanceScore = distance
    ? Math.max(0, 15 - Math.min(15, Math.floor(distance / 250)))
    : 8
  const tagMatchScore = Math.min(34, matchedTags.length * 7 + preferredMatchCount * 8)
  const confidenceScore = getTagConfidenceScore(savedTagData)
  const verifiedScore = Math.min(12, (savedTagData.verified_tags || []).length * 4)
  const warningPenalty = Math.min(20, warningTags.length * 8)
  const qualityScore = Number(savedTagData.data_quality_score || 0)
  const qualityBonus = qualityScore ? Math.min(10, Math.round(qualityScore / 10)) : 0
  const rawScoreBonus = Number.isFinite(Number(rawScores.recommendation_ready_score))
    ? Math.min(12, Math.round(Number(rawScores.recommendation_ready_score) / 8))
    : 0
  const weakWorkCafePenalty = preferredTags.length && preferredMatchCount === 0 ? 18 : 0
  const recommendScore = Math.max(
    0,
    Math.min(
      100,
      42 +
        tagMatchScore +
        distanceScore +
        confidenceScore +
        verifiedScore +
        qualityBonus +
        rawScoreBonus -
        warningPenalty -
        weakWorkCafePenalty +
        waitingSuitability.bonus -
        waitingSuitability.penalty,
    ),
  )

  const reasonParts = []
  if (preferredMatchCount > 0) {
    reasonParts.push(`${matchedTags.slice(0, 3).join(', ')} 태그가 작업 목적과 일치합니다.`)
  } else if (matchedTags.length) {
    reasonParts.push(`저장된 태그(${matchedTags.slice(0, 3).join(', ')})가 검색 조건과 연결됩니다.`)
  } else {
    reasonParts.push('DB에 저장된 장소 태그가 확인된 카카오 결과입니다.')
  }
  if (preferredTags.length && preferredMatchCount === 0) {
    reasonParts.push('작업 선호 태그와 직접 일치하는 정보는 부족해 후순위로 반영했습니다.')
  }
  if ((savedTagData.verified_tags || []).length) {
    reasonParts.push('검증 태그가 포함되어 신뢰도를 높였습니다.')
  }
  if (distance && distance <= 1000) {
    reasonParts.push('기준 위치에서 가까운 카페입니다.')
  }
  if (warningTags.length) {
    reasonParts.push(`주의 태그(${warningTags.join(', ')})가 있어 점수를 낮췄습니다.`)
  }
  if (waitingSuitability.reason) {
    reasonParts.push('일반적인 잠깐 휴식 목적과는 맞지 않을 수 있어 후순위로 반영했습니다.')
  }
  reasonParts.push('세부 태그는 후보 정보이므로 실제 이용 가능 여부는 확인이 필요합니다.')

  let recommendationConfidence = 'medium'
  if ((savedTagData.verified_tags || []).length && confidenceScore >= 7 && !warningTags.length && (!preferredTags.length || preferredMatchCount > 0)) {
    recommendationConfidence = 'high'
  } else if (warningTags.length || waitingSuitability.reason || confidenceScore <= 3 || (preferredTags.length && preferredMatchCount === 0)) {
    recommendationConfidence = 'low'
  }

  return {
    recommendScore,
    matchedTags,
    recommendationReason: reasonParts.join(' '),
    recommendationConfidence,
    preferredMatchCount,
    waitingPlacePenalty: waitingSuitability.penalty,
    waitingPlaceExcluded: waitingSuitability.excluded,
    waitingPlacePenaltyReason: waitingSuitability.reason,
  }
}

export const getWalkHealingSuitability = ({
  place = {},
  query = '',
  parsedIntent = null,
} = {}) => {
  const placeText = getPlaceTextForRule(place)
  const explicitCafeIntent = hasExplicitWalkCafeIntent(query, parsedIntent)
  const hasNatureSignal = WALK_HEALING_ALLOWED_KEYWORDS.some((keyword) => {
    return placeText.includes(normalizeLocationText(keyword))
  })
  const hasCafeSignal = WALK_HEALING_CAFE_KEYWORDS.some((keyword) => {
    return placeText.includes(normalizeLocationText(keyword))
  })
  const blockedKeywords = WALK_HEALING_EXCLUDE_KEYWORDS.filter((keyword) => {
    return placeText.includes(normalizeLocationText(keyword))
  })
  const cafeOnlyBlocked = hasCafeSignal && !hasNatureSignal && !explicitCafeIntent
  const hardBlockedKeywords = blockedKeywords.filter((keyword) => {
    return !WALK_HEALING_CAFE_KEYWORDS.includes(keyword)
  })

  if (hardBlockedKeywords.length || cafeOnlyBlocked) {
    return {
      excluded: true,
      penalty: 90,
      bonus: 0,
      reason: hardBlockedKeywords[0] || 'cafe_without_walk_signal',
    }
  }

  if (!hasNatureSignal && hasCafeSignal && explicitCafeIntent) {
    return {
      excluded: false,
      penalty: 28,
      bonus: 0,
      reason: 'auxiliary_cafe_candidate',
    }
  }

  if (!hasNatureSignal) {
    return {
      excluded: true,
      penalty: 70,
      bonus: 0,
      reason: 'missing_walk_healing_signal',
    }
  }

  return {
    excluded: false,
    penalty: 0,
    bonus: 14,
    reason: null,
  }
}
