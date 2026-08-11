import {
  CAFE_SEARCH_KEYWORDS,
  INFRA_SEARCH_KEYWORDS,
  SCENARIO_DISPLAY_LABELS,
  WALK_HEALING_FALLBACK_RADII,
  WALK_HEALING_FALLBACK_QUERIES,
  WALK_HEALING_ALLOWED_KEYWORDS,
  WALK_HEALING_LOCATION_QUERY_KEYWORDS,
  WALK_HEALING_CAFE_KEYWORDS,
  FOOD_CAFE_KEYWORDS,
  FOOD_BAKERY_KEYWORDS,
  FOOD_MENU_PATTERN_SUFFIXES,
  FOOD_MENU_KNOWN_KEYWORDS,
  KAKAO_FALLBACK_MAX_SCORE,
  KAKAO_FALLBACK_KEYWORD_RULES,
  INTENT_KAKAO_KEYWORD_CANDIDATES,
  INTENT_GROUP_DISPLAY_LABELS,
  CATEGORY_KAKAO_KEYWORDS,
  AI_SCENARIO_KAKAO_KEYWORDS,
  KAKAO_DETAIL_MATCH_DISTANCE_M,
  KAKAO_DETAIL_WIDE_MATCH_DISTANCE_M,
  KAKAO_DETAIL_WIDE_CATEGORIES,
  KAKAO_DETAIL_WIDE_NAME_KEYWORDS,
  KAKAO_DETAIL_NAME_SIMILARITY_MIN,
  KAKAO_DETAIL_MAX_QUERY_COUNT,
  KAKAO_DETAIL_GENERIC_NAMES,
  KAKAO_DETAIL_SUFFIX_BOUNDARY_WORDS,
} from '@/constants/homeSearchConstants'

export const getTagName = (tag) => {
  if (typeof tag === 'string') {
    return tag
  }

  return tag.name
}

export const getTagClass = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source

  if (source === 'blog_search') {
    return 'tag-blog'
  }

  if (source === 'user_verified') {
    return 'tag-user'
  }

  if (source === 'warning_tags') {
    return 'tag-warning'
  }

  return 'tag-default'
}

export const getTagSourceText = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source

  if (source === 'external_data') {
    return 'DB'
  }

  if (source === 'field_rule') {
    return '필드'
  }

  if (source === 'keyword_rule') {
    return '키워드'
  }

  if (source === 'checked') {
    return '검수'
  }

  if (source === 'blog_search') {
    return '블로그'
  }

  if (source === 'user_verified') {
    return '사용자검증'
  }

  if (source === 'warning_tags') {
    return '주의'
  }

  return '기본'
}

export const getTagSortOrder = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source

  if (source === 'blog_search') {
    return 1
  }

  if (source === 'user_verified') {
    return 2
  }

  if (source === 'warning_tags') {
    return 3
  }

  if (source === 'category_rule') {
    return 99
  }

  return 50
}

export const getSortedTags = (tags = []) => {
  return [...tags].sort((a, b) => {
    return getTagSortOrder(a) - getTagSortOrder(b)
  })
}

export const normalizeLabelValue = (item) => {
  if (typeof item === 'string') return item.trim()
  if (typeof item === 'number' && Number.isFinite(item)) return String(item)
  if (!item || typeof item !== 'object') return ''

  const labelKeys = ['label', 'name', 'display_name', 'displayName', 'value', 'text']
  for (const key of labelKeys) {
    const label = normalizeLabelValue(item[key])
    if (label) return label
  }

  return ''
}

export const toDisplayList = (value) => {
  if (!Array.isArray(value)) {
    return []
  }

  return [...new Set(
    value
      .map(normalizeLabelValue)
      .filter((item) => item && item !== '[object Object]'),
  )]
}

export const getTextValue = (value) => String(value || '').trim()

export const getScenarioDisplayLabel = (scenario) => {
  const value = getTextValue(scenario)
  return SCENARIO_DISPLAY_LABELS[value] || value
}

export const getPersonalizationBoost = (place) => {
  const boost = Number(place?.personalizationBoost ?? place?.personalization_boost ?? 0)

  return Number.isFinite(boost) ? boost : 0
}

export const getPersonalizationReasons = (place) => {
  return toDisplayList(place?.personalizationReasons || place?.personalization_reasons)
}

export const getPersonalizationBoostText = (place) => {
  const boost = getPersonalizationBoost(place)

  if (boost <= 0) return ''
  return `개인화 +${boost.toFixed(1)}`
}

export const getRecommendationPreviewLabels = (labels = [], limit = 3) => {
  return toDisplayList(labels).slice(0, limit)
}

export const normalizeSearchText = (text = '') => {
  return text.toLowerCase().replace(/\s+/g, '')
}

export const isCafeSearchKeyword = (keyword) => {
  const normalizedKeyword = normalizeSearchText(keyword)

  return CAFE_SEARCH_KEYWORDS.some((word) => {
    return normalizedKeyword.includes(normalizeSearchText(word))
  })
}

export const isInfraSearchKeyword = (keyword) => {
  const normalizedKeyword = normalizeSearchText(keyword)

  return INFRA_SEARCH_KEYWORDS.some((word) => {
    return normalizedKeyword.includes(normalizeSearchText(word))
  })
}

export const shouldAppendDbPlaces = (keyword) => {
  return !isCafeSearchKeyword(keyword) && isInfraSearchKeyword(keyword)
}

export const normalizePlaceName = (name = '') => {
  return String(name || '')
    .toLowerCase()
    .replace(/\([^)]*\)/g, '')
    .replace(/\[[^\]]*\]/g, '')
    .replace(/본점$/g, '')
    .replace(/지점$/g, '')
    .replace(/\s+[가-힣a-z0-9]{1,8}점$/g, '')
    .replace(/점$/g, '')
    .replace(/\s+/g, '')
    .replace(/[^0-9a-z가-힣]/g, '')
}

export const getPlaceNameSimilarity = (firstName, secondName) => {
  const first = normalizePlaceName(firstName)
  const second = normalizePlaceName(secondName)

  if (!first || !second) return 0
  if (first === second) return 1
  if (first.includes(second) || second.includes(first)) return 0.92

  const makeBigrams = (text) => {
    if (text.length <= 1) return [text]

    return Array.from({ length: text.length - 1 }, (_, index) => text.slice(index, index + 2))
  }
  const firstBigrams = makeBigrams(first)
  const secondBigrams = makeBigrams(second)
  const secondCounts = secondBigrams.reduce((counts, bigram) => {
    counts[bigram] = (counts[bigram] || 0) + 1
    return counts
  }, {})
  let intersection = 0

  firstBigrams.forEach((bigram) => {
    if (!secondCounts[bigram]) return

    intersection += 1
    secondCounts[bigram] -= 1
  })

  return (2 * intersection) / (firstBigrams.length + secondBigrams.length)
}

export const getDistanceMetersBetweenPlaces = (firstPlace, secondPlace) => {
  const lat1 = Number(firstPlace.lat)
  const lng1 = Number(firstPlace.lng)
  const lat2 = Number(secondPlace.lat)
  const lng2 = Number(secondPlace.lng)

  if ([lat1, lng1, lat2, lng2].some((value) => Number.isNaN(value))) {
    return Number.POSITIVE_INFINITY
  }

  const radius = 6371000
  const toRadians = (degree) => degree * (Math.PI / 180)
  const deltaLat = toRadians(lat2 - lat1)
  const deltaLng = toRadians(lng2 - lng1)

  const a =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) *
    Math.cos(toRadians(lat2)) *
    Math.sin(deltaLng / 2) ** 2

  return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

export const getTagKey = (tag) => {
  const source = typeof tag === 'string' ? 'category_rule' : tag.source
  return `${getTagName(tag)}-${source}`
}

export const mergeTags = (firstTags = [], secondTags = []) => {
  const mergedTags = []
  const seen = new Set()

    ;[...firstTags, ...secondTags].forEach((tag) => {
      const key = getTagKey(tag)

      if (seen.has(key)) {
        return
      }

      seen.add(key)
      mergedTags.push(tag)
    })

  return mergedTags
}

export const getAddressOverlapMatched = (firstAddress = '', secondAddress = '') => {
  const first = normalizePlaceName(firstAddress)
  const second = normalizePlaceName(secondAddress)

  if (!first || !second) return false

  return first.includes(second.slice(0, 8)) || second.includes(first.slice(0, 8))
}

export const getDbKakaoMergeDecision = (kakaoPlace, dbPlace) => {
  const idMatched = Boolean(
    dbPlace.source === 'kakao_local' &&
    dbPlace.externalId &&
    kakaoPlace.kakaoPlaceId &&
    String(dbPlace.externalId) === String(kakaoPlace.kakaoPlaceId),
  )
  const nameSimilarity = getPlaceNameSimilarity(kakaoPlace.name, dbPlace.name)
  const nameMatched = nameSimilarity >= 0.72
  const distanceMeters = getDistanceMetersBetweenPlaces(kakaoPlace, dbPlace)
  const distanceMatched = distanceMeters <= 30
  const addressMatched = getAddressOverlapMatched(kakaoPlace.address, dbPlace.address)

  if (idMatched) {
    return {
      matched: true,
      reason: 'external_id_matched',
      nameSimilarity,
      distanceMeters,
      addressMatched,
    }
  }

  if (nameMatched && distanceMatched) {
    return {
      matched: true,
      reason: 'name_and_distance_matched',
      nameSimilarity,
      distanceMeters,
      addressMatched,
    }
  }

  if (nameMatched && addressMatched) {
    return {
      matched: true,
      reason: 'name_and_address_matched',
      nameSimilarity,
      distanceMeters,
      addressMatched,
    }
  }

  const reason = !nameMatched
    ? 'name_not_similar'
    : (!distanceMatched && !addressMatched ? 'distance_and_address_not_matched' : 'unknown')

  return {
    matched: false,
    reason,
    nameSimilarity,
    distanceMeters,
    addressMatched,
  }
}

export const getBestKakaoMergeCandidate = (kakaoResults, dbPlace) => {
  let bestCandidate = null

  kakaoResults.forEach((kakaoPlace) => {
    const decision = getDbKakaoMergeDecision(kakaoPlace, dbPlace)

    if (decision.matched) {
      const score =
        (decision.reason === 'external_id_matched' ? 100 : 0) +
        (decision.nameSimilarity || 0) * 20 +
        (Number.isFinite(decision.distanceMeters) ? Math.max(0, 30 - decision.distanceMeters) : 0) +
        (decision.addressMatched ? 10 : 0)

      if (!bestCandidate || score > bestCandidate.score) {
        bestCandidate = {
          kakaoPlace,
          decision,
          score,
        }
      }

      return
    }
  })

  return bestCandidate
}

export const mergeDbDataIntoKakaoPlace = (kakaoPlace, dbPlace) => {
  const hasRecommendationData =
    dbPlace?.sourceLabel === 'DB추천' || dbPlace?.tagSource === 'DB 추천 결과'

  return {
    ...kakaoPlace,
    savedPlaceId: kakaoPlace.savedPlaceId || dbPlace.savedPlaceId,
    source: dbPlace.source || kakaoPlace.source,
    sourceName: dbPlace.sourceName || kakaoPlace.sourceName,
    externalId: kakaoPlace.externalId || dbPlace.externalId,
    kakaoPlaceId:
      kakaoPlace.kakaoPlaceId ||
      dbPlace.kakaoPlaceId ||
      (
        hasKakaoSourceHint(dbPlace) && isKakaoPlaceId(dbPlace.externalId)
          ? dbPlace.externalId
          : null
      ),
    placeUrl: kakaoPlace.placeUrl || dbPlace.placeUrl,
    kakaoPlaceUrl: kakaoPlace.kakaoPlaceUrl || dbPlace.kakaoPlaceUrl || '',
    kakaoUrl: kakaoPlace.kakaoUrl || dbPlace.kakaoUrl || '',
    detailUrl: kakaoPlace.detailUrl || dbPlace.detailUrl || '',
    navigationUrl: kakaoPlace.navigationUrl || dbPlace.navigationUrl,
    tags: mergeTags(kakaoPlace.tags, dbPlace.tags),
    tagSource: hasRecommendationData
      ? `${kakaoPlace.tagSource} + DB 추천 데이터`
      : `${kakaoPlace.tagSource} + DB 저장 데이터`,
    sourceLabel: '카카오+DB',
    dataQualityStatus: kakaoPlace.dataQualityStatus || dbPlace.dataQualityStatus,
    dataQualityScore: kakaoPlace.dataQualityScore ?? dbPlace.dataQualityScore,
    recommendScore: dbPlace.recommendScore ?? kakaoPlace.recommendScore,
    recommendationReason:
      dbPlace.recommendationReason || kakaoPlace.recommendationReason,
    matchedTags: dbPlace.matchedTags?.length
      ? dbPlace.matchedTags
      : (kakaoPlace.matchedTags || []),
    matchedTagLabels: dbPlace.matchedTagLabels?.length
      ? dbPlace.matchedTagLabels
      : (kakaoPlace.matchedTagLabels || []),
    missingTagLabels: dbPlace.missingTagLabels?.length
      ? dbPlace.missingTagLabels
      : (kakaoPlace.missingTagLabels || []),
    recommendationSourceLabel:
      dbPlace.recommendationSourceLabel || kakaoPlace.recommendationSourceLabel || '',
    recommendationConfidenceLabel:
      dbPlace.recommendationConfidenceLabel || kakaoPlace.recommendationConfidenceLabel || '',
    recommendationFallbackLabel:
      dbPlace.recommendationFallbackLabel || kakaoPlace.recommendationFallbackLabel || '',
    recommendationFallbackDescription:
      dbPlace.recommendationFallbackDescription || kakaoPlace.recommendationFallbackDescription || '',
    recommendationCaution:
      dbPlace.recommendationCaution || kakaoPlace.recommendationCaution || '',
    suggestedTags: dbPlace.suggestedTags?.length
      ? dbPlace.suggestedTags
      : (kakaoPlace.suggestedTags || []),
    verifiedTags: dbPlace.verifiedTags?.length
      ? dbPlace.verifiedTags
      : (kakaoPlace.verifiedTags || []),
    warningTags: dbPlace.warningTags?.length
      ? dbPlace.warningTags
      : (kakaoPlace.warningTags || []),
    tagDetails: dbPlace.tagDetails?.length
      ? dbPlace.tagDetails
      : (kakaoPlace.tagDetails || []),
    matchLevel: dbPlace.matchLevel || kakaoPlace.matchLevel,
    recommendationConfidence:
      dbPlace.recommendationConfidence || kakaoPlace.recommendationConfidence,
  }
}

export const dedupeSearchResults = (kakaoResults, dbPlaces) => {
  const mergedKakaoResults = [...kakaoResults]
  const additionalDbPlaces = []

  dbPlaces.forEach((dbPlace) => {
    const bestCandidate = getBestKakaoMergeCandidate(mergedKakaoResults, dbPlace)

    if (!bestCandidate) {
      additionalDbPlaces.push(dbPlace)
      return
    }

    const duplicateIndex = mergedKakaoResults.findIndex((kakaoPlace) => {
      return kakaoPlace.id === bestCandidate.kakaoPlace.id
    })

    if (duplicateIndex === -1) {
      additionalDbPlaces.push(dbPlace)
      return
    }

    mergedKakaoResults[duplicateIndex] = mergeDbDataIntoKakaoPlace(
      mergedKakaoResults[duplicateIndex],
      dbPlace,
    )
  })

  return [...mergedKakaoResults, ...additionalDbPlaces]
}

export const SOURCE_LABEL_TEXT = {
  DB추천: '저장 장소',
  'DB 후보': '저장 장소',
  '카카오 후보': '카카오 참고',
  카카오: '카카오 참고',
  '웹 근거 후보': '웹 참고',
  '웹 검색 근거 후보, 세부 정보 확인 필요': '웹 참고',
  '카카오 검색 근거 후보, 세부 정보 확인 필요': '카카오 참고',
  '카카오+DB': '카카오+DB',
}

export const getPlaceSourceText = (place) => {
  const label = getTextValue(place?.sourceLabel || place?.source_label)
  return SOURCE_LABEL_TEXT[label] || label || '장소'
}

export const getPlaceSourceClass = (place) => {
  if (place.searchSource === 'web') {
    return 'source-web'
  }

  if (place.searchSource === 'local_db') {
    return 'source-db'
  }

  if (place.searchSource === 'kakao') {
    return 'source-kakao'
  }

  return 'source-base'
}

export const isDbPlace = (place) => {
  return place?.searchSource === 'local_db'
}

export const KAKAO_PLACE_ID_PATTERN = /^\d{5,20}$/

export const normalizeKakaoDetailUrl = (url) => {
  const cleanedUrl = getTextValue(url)

  if (!cleanedUrl) {
    return ''
  }

  const candidateUrl = cleanedUrl.startsWith('place.map.kakao.com/')
    ? `https://${cleanedUrl}`
    : cleanedUrl

  try {
    const parsedUrl = new URL(candidateUrl)
    const [placeId] = parsedUrl.pathname.split('/').filter(Boolean)

    if (
      parsedUrl.hostname !== 'place.map.kakao.com' ||
      !KAKAO_PLACE_ID_PATTERN.test(placeId)
    ) {
      return ''
    }

    return `https://place.map.kakao.com/${placeId}`
  } catch (error) {
    return ''
  }
}

export const isKakaoPlaceId = (value) => {
  return KAKAO_PLACE_ID_PATTERN.test(getTextValue(value))
}

export const hasKakaoSourceHint = (place) => {
  const sourceText = [
    place?.source,
    place?.rawSource,
    place?.sourceName,
    place?.source_name,
  ]
    .map((value) => getTextValue(value).toLowerCase())
    .join(' ')

  return sourceText.includes('kakao')
}

export const getKakaoDetailLookupKey = (place) => {
  if (!place) {
    return ''
  }

  const stableId = place.id || place.savedPlaceId || place.externalId || place.external_id
  if (stableId) {
    return String(stableId)
  }

  return [
    getTextValue(place.name),
    getTextValue(place.lat),
    getTextValue(place.lng),
  ].join(':')
}

export const getDirectKakaoDetailUrl = (place) => {
  const explicitUrl = [
    place?.kakaoPlaceUrl,
    place?.kakao_place_url,
    place?.kakaoUrl,
    place?.kakao_url,
    place?.placeUrl,
    place?.place_url,
    place?.detailUrl,
    place?.detail_url,
  ]
    .map(normalizeKakaoDetailUrl)
    .find(Boolean)

  if (explicitUrl) {
    return explicitUrl
  }

  const kakaoPlaceId = getTextValue(place?.kakaoPlaceId || place?.kakao_place_id)
  if (isKakaoPlaceId(kakaoPlaceId)) {
    return `https://place.map.kakao.com/${kakaoPlaceId}`
  }

  const externalId = getTextValue(place?.externalId || place?.external_id)
  if (hasKakaoSourceHint(place) && isKakaoPlaceId(externalId)) {
    return `https://place.map.kakao.com/${externalId}`
  }

  return ''
}

export const debugKakaoDetailLog = (label, payload = {}) => {
  if (!import.meta.env.DEV) {
    return
  }

  console.debug(label, payload)
}

export const getKakaoDetailPlaceCoordinates = (place) => {
  const lat = Number(place?.lat ?? place?.y)
  const lng = Number(place?.lng ?? place?.x)

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return null
  }

  return { lat, lng }
}

export const getKakaoDetailCandidateCoordinates = (candidate) => {
  const lat = Number(candidate?.y ?? candidate?.lat)
  const lng = Number(candidate?.x ?? candidate?.lng)

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return null
  }

  return { lat, lng }
}

export const escapeKakaoDetailRegExp = (value) => {
  return getTextValue(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export const removeKakaoDetailBracketContent = (name = '') => {
  return getTextValue(name)
    .replace(/\([^)]*\)/g, ' ')
    .replace(/\[[^\]]*\]/g, ' ')
    .replace(/\{[^}]*\}/g, ' ')
}

export const removeKakaoDetailBracketCharacters = (name = '') => {
  return getTextValue(name).replace(/[()[\]{}]/g, ' ')
}

export const replaceKakaoDetailSpecialCharacters = (name = '') => {
  return getTextValue(name).replace(/[^\p{L}\p{N}]+/gu, ' ')
}

export const normalizeKakaoDetailWhitespace = (name = '') => {
  return getTextValue(name).replace(/\s+/g, ' ').trim()
}

export const insertKakaoDetailNameBoundaries = (name = '') => {
  let spacedName = normalizeKakaoDetailWhitespace(name)

  KAKAO_DETAIL_SUFFIX_BOUNDARY_WORDS.forEach((word) => {
    const escapedWord = escapeKakaoDetailRegExp(word)

    if (!escapedWord) {
      return
    }

    spacedName = spacedName.replace(new RegExp(`(${escapedWord})(?=\\S)`, 'g'), '$1 ')
  })

  return normalizeKakaoDetailWhitespace(spacedName)
}

export const normalizeKakaoMatchName = (name = '') => {
  return replaceKakaoDetailSpecialCharacters(removeKakaoDetailBracketContent(name))
    .toLowerCase()
    .replace(/\s+/g, '')
}

export const normalizeKakaoLookupQueryKey = (query = '') => {
  return replaceKakaoDetailSpecialCharacters(query)
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

export const isGenericKakaoMatchName = (name = '') => {
  const normalizedName = normalizeKakaoMatchName(name)

  return !normalizedName || normalizedName.length <= 2 || KAKAO_DETAIL_GENERIC_NAMES.has(normalizedName)
}

export const getUniqueKakaoDetailValues = (values = [], getKey = normalizeKakaoLookupQueryKey) => {
  const seen = new Set()
  const uniqueValues = []

  values.forEach((value) => {
    const textValue = normalizeKakaoDetailWhitespace(value)
    const key = getKey(textValue)

    if (!textValue || !key || seen.has(key)) {
      return
    }

    seen.add(key)
    uniqueValues.push(textValue)
  })

  return uniqueValues
}

export const buildKakaoDetailLookupQueries = (place) => {
  const placeName = getTextValue(place?.name)

  if (!placeName) {
    return []
  }

  const bracketCharactersRemoved = removeKakaoDetailBracketCharacters(placeName)
  const bracketContentRemoved = removeKakaoDetailBracketContent(placeName)
  const specialCharactersReplaced = replaceKakaoDetailSpecialCharacters(placeName)
  const queryCandidates = [
    placeName,
    bracketCharactersRemoved,
    bracketContentRemoved,
    specialCharactersReplaced,
    insertKakaoDetailNameBoundaries(placeName),
    insertKakaoDetailNameBoundaries(bracketCharactersRemoved),
    insertKakaoDetailNameBoundaries(bracketContentRemoved),
    insertKakaoDetailNameBoundaries(specialCharactersReplaced),
  ]

  return getUniqueKakaoDetailValues(queryCandidates)
    .filter((query) => !isGenericKakaoMatchName(query))
    .slice(0, KAKAO_DETAIL_MAX_QUERY_COUNT)
}

export const getKakaoMatchNameVariants = (name = '') => {
  const sourceName = getTextValue(name)

  if (!sourceName) {
    return []
  }

  return getUniqueKakaoDetailValues(
    [
      sourceName,
      removeKakaoDetailBracketCharacters(sourceName),
      removeKakaoDetailBracketContent(sourceName),
      replaceKakaoDetailSpecialCharacters(sourceName),
      insertKakaoDetailNameBoundaries(sourceName),
      insertKakaoDetailNameBoundaries(removeKakaoDetailBracketCharacters(sourceName)),
      insertKakaoDetailNameBoundaries(removeKakaoDetailBracketContent(sourceName)),
    ],
    normalizeKakaoMatchName,
  )
    .map(normalizeKakaoMatchName)
    .filter(Boolean)
}

export const getKakaoNormalizedNameSimilarity = (firstName = '', secondName = '') => {
  if (!firstName || !secondName) {
    return 0
  }

  if (firstName === secondName) {
    return 1
  }

  if (firstName.includes(secondName) || secondName.includes(firstName)) {
    return 0.92
  }

  const makeBigrams = (text) => {
    if (text.length <= 1) {
      return [text]
    }

    return Array.from({ length: text.length - 1 }, (_, index) => text.slice(index, index + 2))
  }
  const firstBigrams = makeBigrams(firstName)
  const secondBigrams = makeBigrams(secondName)
  const secondCounts = secondBigrams.reduce((counts, bigram) => {
    counts[bigram] = (counts[bigram] || 0) + 1
    return counts
  }, {})
  let intersection = 0

  firstBigrams.forEach((bigram) => {
    if (!secondCounts[bigram]) {
      return
    }

    intersection += 1
    secondCounts[bigram] -= 1
  })

  return (2 * intersection) / (firstBigrams.length + secondBigrams.length)
}

export const getKakaoDetailNameEvaluation = (placeName, candidateName) => {
  const placeVariants = getKakaoMatchNameVariants(placeName)
  const candidateVariants = getKakaoMatchNameVariants(candidateName)
  const hasGenericName = isGenericKakaoMatchName(placeName) || isGenericKakaoMatchName(candidateName)
  let exactMatched = false
  let containmentMatched = false
  let bestSimilarity = 0

  placeVariants.forEach((placeVariant) => {
    candidateVariants.forEach((candidateVariant) => {
      if (placeVariant === candidateVariant && placeVariant.length >= 3) {
        exactMatched = true
      }

      const shorterLength = Math.min(placeVariant.length, candidateVariant.length)
      if (
        shorterLength >= 4 &&
        !hasGenericName &&
        (placeVariant.includes(candidateVariant) || candidateVariant.includes(placeVariant))
      ) {
        containmentMatched = true
      }

      bestSimilarity = Math.max(
        bestSimilarity,
        getKakaoNormalizedNameSimilarity(placeVariant, candidateVariant),
      )
    })
  })

  if (!placeVariants.length || !candidateVariants.length) {
    return {
      passed: false,
      reason: 'missing_name',
      similarity: 0,
      exactMatched: false,
      containmentMatched: false,
    }
  }

  if (hasGenericName) {
    return {
      passed: false,
      reason: 'generic_name',
      similarity: bestSimilarity,
      exactMatched,
      containmentMatched: false,
    }
  }

  const similarityMatched = bestSimilarity >= KAKAO_DETAIL_NAME_SIMILARITY_MIN
  const passed = exactMatched || containmentMatched || similarityMatched

  return {
    passed,
    reason: passed ? 'name_matched' : 'name_mismatch',
    similarity: bestSimilarity,
    exactMatched,
    containmentMatched,
  }
}

export const getKakaoDetailMaxDistance = (place) => {
  const categoryText = [
    place?.rawCategory,
    place?.category,
  ]
    .map((value) => getTextValue(value))
    .filter(Boolean)

  const searchText = [
    ...categoryText,
    place?.name,
  ]
    .map((value) => getTextValue(value))
    .join(' ')
  const isWidePlace = (
    categoryText.some((category) => KAKAO_DETAIL_WIDE_CATEGORIES.has(category)) ||
    KAKAO_DETAIL_WIDE_NAME_KEYWORDS.some((keyword) => searchText.includes(keyword))
  )

  return isWidePlace
    ? KAKAO_DETAIL_WIDE_MATCH_DISTANCE_M
    : KAKAO_DETAIL_MATCH_DISTANCE_M
}

export const getKakaoDetailCandidateUrl = (candidate) => {
  const candidateUrl = normalizeKakaoDetailUrl(candidate?.place_url || candidate?.placeUrl)

  if (candidateUrl) {
    return candidateUrl
  }

  const candidateId = getTextValue(candidate?.id)

  return isKakaoPlaceId(candidateId)
    ? `https://place.map.kakao.com/${candidateId}`
    : ''
}

export const evaluateKakaoDetailCandidate = (place, candidate, query = '') => {
  const placeCoordinates = getKakaoDetailPlaceCoordinates(place)
  const maxDistance = getKakaoDetailMaxDistance(place)
  const candidateCoordinates = getKakaoDetailCandidateCoordinates(candidate)
  const url = getKakaoDetailCandidateUrl(candidate)
  const nameEvaluation = getKakaoDetailNameEvaluation(place?.name, candidate?.place_name)
  const rejectReasons = []
  let distance = null

  if (!placeCoordinates) {
    rejectReasons.push('missing_db_coordinates')
  }

  if (!candidateCoordinates) {
    rejectReasons.push('missing_candidate_coordinates')
  }

  if (placeCoordinates && candidateCoordinates) {
    distance = getDistanceMetersBetweenPlaces(placeCoordinates, candidateCoordinates)

    if (!Number.isFinite(distance)) {
      rejectReasons.push('invalid_distance')
    } else if (distance > maxDistance) {
      rejectReasons.push('distance_over_limit')
    }
  }

  if (!nameEvaluation.passed) {
    rejectReasons.push(nameEvaluation.reason)
  }

  if (!url) {
    rejectReasons.push('missing_url')
  }

  return {
    candidate,
    url,
    query,
    distance,
    maxDistance,
    nameSimilarity: nameEvaluation.similarity,
    nameEvaluation,
    hasUrl: Boolean(url),
    distanceMatched: Number.isFinite(distance) && distance <= maxDistance,
    nameMatched: nameEvaluation.passed,
    passed: rejectReasons.length === 0,
    rejectReasons,
  }
}

export const getBestKakaoDetailCandidate = (place, candidates = [], query = '') => {
  return candidates
    .map((candidate) => evaluateKakaoDetailCandidate(place, candidate, query))
    .map((evaluation) => {
      debugKakaoDetailLog('[카카오 상세 후보 평가]', {
        query: evaluation.query,
        dbPlaceName: place?.name,
        candidateName: evaluation.candidate?.place_name,
        candidateCoordinates: getKakaoDetailCandidateCoordinates(evaluation.candidate),
        distance: evaluation.distance,
        maxDistance: evaluation.maxDistance,
        nameSimilarity: evaluation.nameSimilarity,
        nameMatched: evaluation.nameMatched,
        distanceMatched: evaluation.distanceMatched,
        hasUrl: evaluation.hasUrl,
        passed: evaluation.passed,
        rejectReasons: evaluation.rejectReasons,
      })

      return evaluation
    })
    .filter((evaluation) => evaluation.passed)
    .sort((first, second) => {
      if (Number(second.nameEvaluation.exactMatched) !== Number(first.nameEvaluation.exactMatched)) {
        return Number(second.nameEvaluation.exactMatched) - Number(first.nameEvaluation.exactMatched)
      }

      if (Number(second.nameEvaluation.containmentMatched) !== Number(first.nameEvaluation.containmentMatched)) {
        return Number(second.nameEvaluation.containmentMatched) - Number(first.nameEvaluation.containmentMatched)
      }

      if (second.nameSimilarity !== first.nameSimilarity) {
        return second.nameSimilarity - first.nameSimilarity
      }

      return first.distance - second.distance
    })[0] || null
}

export const getPlannerText = (value = '') => {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number') return String(value)
  if (!value || typeof value !== 'object') return ''

  return String(
    value.label ||
    value.name ||
    value.display_name ||
    value.displayName ||
    value.value ||
    value.text ||
    '',
  ).trim()
}

export const getPlannerList = (value = []) => {
  const items = Array.isArray(value) ? value : (value ? [value] : [])
  return [...new Set(items.map(getPlannerText).filter((item) => item && item !== '[object Object]'))]
}

export const getClarificationOptionItems = (value = []) => {
  const items = Array.isArray(value) ? value : (value ? [value] : [])
  const seen = new Set()
  return items.map((item) => {
    if (item && typeof item === 'object') {
      const label = getPlannerText(item.label || item.text || item.name || item.value)
      const optionValue = getPlannerText(item.value || item.answer || item.text || item.label)
      return {
        label,
        value: optionValue || label,
      }
    }
    const text = getPlannerText(item)
    return {
      label: text,
      value: text,
    }
  }).filter((item) => {
    const key = `${item.label}::${item.value}`
    if (!item.label || !item.value || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export const getClarificationOptionLabel = (option = '') => {
  if (option && typeof option === 'object') {
    return getPlannerText(option.label || option.text || option.name || option.value)
  }
  return getPlannerText(option)
}

export const getClarificationOptionValue = (option = '') => {
  if (option && typeof option === 'object') {
    return getPlannerText(option.value || option.answer || option.text || option.label)
  }
  return getPlannerText(option)
}

export const isBackendAiFirstResponse = (data = {}, parsedIntent = {}) => {
  return Boolean(
    parsedIntent?.backendAiOnly ||
    data?.unified_candidate_pipeline ||
    data?.frontend_should_skip_kakao_fallback ||
    data?.execution_mode === 'ai_first_orchestrator' ||
    data?.ai_parse?.execution_mode === 'ai_first_orchestrator',
  )
}

export const getSearchPlanValue = (searchPlan = {}, ...keys) => {
  for (const key of keys) {
    const value = searchPlan?.[key]
    if (value === true || value === false) {
      return value
    }
    if (Array.isArray(value) ? value.length : getPlannerText(value)) {
      return value
    }
  }

  return ''
}

export const getPlannerBoolean = (value, fallback = null) => {
  if (value === true || value === false) return value
  if (value === 'true') return true
  if (value === 'false') return false
  if (value === 1 || value === '1') return true
  if (value === 0 || value === '0') return false
  return fallback
}

export const getSearchPlanFrame = (searchPlan = {}) => {
  const frame = searchPlan?.place_intent_frame || searchPlan?.placeIntentFrame || {}
  return frame && typeof frame === 'object' && !Array.isArray(frame) ? frame : {}
}

export const getFrameCandidatePlaceTypes = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  const frameCandidates = getPlannerList(
    getSearchPlanValue(frame, 'candidate_place_types', 'candidatePlaceTypes'),
  )
  if (frameCandidates.length) return frameCandidates

  return getPlannerList(
    getSearchPlanValue(searchPlan, 'candidatePlaceTypes', 'candidate_place_types') ||
    getSearchPlanValue(searchPlan, 'categoryCandidates', 'category_candidates') ||
    getSearchPlanValue(searchPlan, 'place_type_keywords', 'placeTypeKeywords'),
  )
}

export const getFrameTargetObjects = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  const frameTargets = getPlannerList(
    getSearchPlanValue(frame, 'target_objects', 'targetObjects'),
  )
  if (frameTargets.length) return frameTargets

  return getPlannerList(
    getSearchPlanValue(searchPlan, 'targetObjects', 'target_objects'),
  )
}

export const getFrameConstraints = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  const frameConstraints = getPlannerList(
    getSearchPlanValue(frame, 'constraints', 'required_conditions', 'requiredConditions'),
  )
  if (frameConstraints.length) return frameConstraints

  return getPlannerList(
    getSearchPlanValue(searchPlan, 'constraints', 'requiredConditions', 'required_conditions'),
  )
}

export const getFrameExclusions = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  const frameExclusions = getPlannerList(
    getSearchPlanValue(frame, 'exclusions', 'excluded_categories', 'excludedCategories'),
  )
  if (frameExclusions.length) return frameExclusions

  return getPlannerList(
    getSearchPlanValue(searchPlan, 'exclusions', 'excludedCategories', 'excluded_categories'),
  )
}

export const getFrameAnchorLocation = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  return getPlannerText(
    getSearchPlanValue(frame, 'anchor_location', 'anchorLocation', 'location') ||
    getSearchPlanValue(searchPlan, 'anchorLocation', 'anchor_location', 'locationQuery', 'baseLocationQuery'),
  )
}

export const getResolvedSearchPlanLocationQuery = (searchPlan = {}) => {
  return getPlannerText(
    getSearchPlanValue(searchPlan, 'locationQuery', 'location_query', 'baseLocationQuery', 'base_location_query') ||
    getFrameAnchorLocation(searchPlan) ||
    searchPlan.baseKeyword,
  )
}

export const syncFrameLocationToSearchPlan = (searchPlan = {}) => {
  if (!searchPlan || typeof searchPlan !== 'object') return searchPlan

  const frame = getSearchPlanFrame(searchPlan)
  const frameAnchor = getPlannerText(getSearchPlanValue(frame, 'anchor_location', 'anchorLocation'))
  if (!frameAnchor) return searchPlan

  frame.anchor_location = frameAnchor
  frame.anchorLocation = frameAnchor
  frame.location_mode = 'explicit'
  frame.locationMode = 'explicit'

  searchPlan.place_intent_frame = frame
  searchPlan.placeIntentFrame = frame
  searchPlan.locationQuery = frameAnchor
  searchPlan.location_query = frameAnchor
  searchPlan.baseLocationQuery = frameAnchor
  searchPlan.base_location_query = frameAnchor
  searchPlan.anchorLocation = frameAnchor
  searchPlan.anchor_location = frameAnchor
  searchPlan.locationMode = 'explicit'
  searchPlan.location_mode = 'explicit'
  searchPlan.hasBaseLocation = true
  searchPlan.hasExplicitLocation = true
  searchPlan.has_explicit_location = true
  searchPlan.locationResolutionRequired = true
  searchPlan.location_resolution_required = true
  searchPlan.explicitCurrentContext = false
  searchPlan.searchMode = 'region_search'
  searchPlan.baseKeyword = frameAnchor

  return searchPlan
}

export const getFrameDisplayLabel = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  return getPlannerText(
    getSearchPlanValue(frame, 'display_label', 'displayLabel') ||
    getSearchPlanValue(searchPlan, 'displayLabel', 'display_label'),
  )
}

export const getFrameWebSearchQueries = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  const frameQueries = getPlannerList(
    getSearchPlanValue(frame, 'search_queries', 'searchQueries', 'web_search_queries', 'webSearchQueries'),
  )
  if (frameQueries.length) return frameQueries

  return getPlannerList(
    getSearchPlanValue(searchPlan, 'webSearchQueries', 'web_search_queries'),
  )
}

export const getFrameResultMatchTerms = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  return [...new Set([
    ...getFrameTargetObjects(searchPlan),
    ...getPlannerList(
    getSearchPlanValue(frame, 'result_match_terms', 'resultMatchTerms'),
    ),
  ].filter(Boolean))]
}

export const getFrameRankingPolicy = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  return getPlannerText(
    getSearchPlanValue(frame, 'ranking_policy', 'rankingPolicy') ||
    getSearchPlanValue(searchPlan, 'rankingPolicy', 'ranking_policy'),
  )
}

export const getFrameCandidateCategoryCodes = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  return getPlannerList(
    getSearchPlanValue(frame, 'candidate_category_codes', 'candidateCategoryCodes') ||
    getSearchPlanValue(searchPlan, 'candidateCategoryCodes', 'candidate_category_codes'),
  )
}

export const getFrameLocationMode = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  return getPlannerText(
    getSearchPlanValue(frame, 'location_mode', 'locationMode') ||
    getSearchPlanValue(searchPlan, 'locationMode', 'location_mode'),
  )
}

export const hasValidSearchIntentFrame = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  if (!Object.keys(frame).length) return false

  const locationMode = getFrameLocationMode(searchPlan)
  const hasLocationMode = ['explicit', 'current_context', 'clarification_required'].includes(locationMode)
  const hasGoal = Boolean(getPlannerText(frame.user_goal || frame.userGoal))
  const hasLabel = Boolean(getFrameDisplayLabel(searchPlan))
  const hasSearchTarget = Boolean(
    getFrameCandidatePlaceTypes(searchPlan).length ||
    getFrameWebSearchQueries(searchPlan).length,
  )
  const hasExplicitAnchor = locationMode !== 'explicit' || Boolean(getFrameAnchorLocation(searchPlan))

  return hasGoal && hasLabel && hasSearchTarget && hasLocationMode && hasExplicitAnchor
}

export const getIntentGroupDisplayLabel = (intentGroup = '') => {
  const value = getTextValue(intentGroup)
  return INTENT_GROUP_DISPLAY_LABELS[value] || value
}

export const getPlanKakaoKeywordCandidates = (searchPlan = {}) => {
  return getPlannerList(
    getSearchPlanValue(searchPlan, 'kakaoKeywordCandidates', 'kakao_keyword_candidates') ||
    getSearchPlanValue(searchPlan, 'kakaoKeywords', 'kakao_keywords'),
  )
}

export const getScenarioFallbackKakaoKeyword = (searchPlan = {}) => {
  const scenario = getPlannerText(searchPlan?.scenario || searchPlan?.recommendationIntent)
  return scenario ? AI_SCENARIO_KAKAO_KEYWORDS[scenario] || '' : ''
}

export const isFrameDrivenSearch = (searchPlan = {}) => {
  return Boolean(
    hasValidSearchIntentFrame(searchPlan) ||
    searchPlan?.executionMode === 'frame' ||
    searchPlan?.execution_mode === 'frame',
  )
}

export const getScenarioFallbackKeywordSet = (searchPlan = {}) => {
  const scenario = getPlannerText(searchPlan?.scenario || searchPlan?.recommendationIntent)
  return new Set([
    ...(scenario && INTENT_KAKAO_KEYWORD_CANDIDATES[scenario]
      ? INTENT_KAKAO_KEYWORD_CANDIDATES[scenario]
      : []),
    getScenarioFallbackKakaoKeyword(searchPlan),
  ].filter(Boolean).map(normalizeLocationText))
}

export const isOnlyScenarioFallbackKeyword = (keywords = [], searchPlan = {}) => {
  const scenarioKeyword = getScenarioFallbackKakaoKeyword(searchPlan)
  if (!scenarioKeyword || keywords.length !== 1) return false

  return normalizeLocationText(keywords[0]) === normalizeLocationText(scenarioKeyword)
}

export const isLocationOnlyKeyword = (keyword = '', searchPlan = {}) => {
  const keywordText = normalizeLocationText(keyword)
  if (!keywordText) return false

  return [
    getFrameAnchorLocation(searchPlan),
    searchPlan?.locationQuery,
    searchPlan?.location_query,
    searchPlan?.baseLocationQuery,
    searchPlan?.base_location_query,
    searchPlan?.baseKeyword,
  ].some((location) => {
    const locationText = normalizeLocationText(location)
    return locationText && keywordText === locationText
  })
}

export const normalizePlanExclusionTerm = (value = '') => {
  return getTextValue(value)
    .replace(/(?:제외해줘|제외한|제외|빼고|말고|아닌|아님|금지)/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export const getExcludedTermsFromPlan = (searchPlan = {}) => {
  const frame = getSearchPlanFrame(searchPlan)
  const excludedCategories = getPlannerList(
    getSearchPlanValue(frame, 'excluded_categories', 'excludedCategories') ||
    getSearchPlanValue(searchPlan, 'excludedCategories', 'excluded_categories'),
  )
  const categoryTerms = excludedCategories.flatMap((category) => {
    return [
      category,
      CATEGORY_KAKAO_KEYWORDS[category],
    ].filter(Boolean)
  })
  const exclusionTerms = [
    ...getFrameExclusions(searchPlan),
    ...categoryTerms,
  ]

  return [...new Set(
    exclusionTerms
      .map(normalizePlanExclusionTerm)
      .filter(Boolean)
      .map((term) => normalizeLocationText(term)),
  )]
}

export const keywordMatchesExclusions = (keyword = '', excludedTerms = []) => {
  const keywordText = normalizeLocationText(keyword)
  if (!keywordText) return false

  return excludedTerms.some((term) => {
    return term && keywordText.includes(term)
  })
}

export const filterKeywordsByExclusions = (keywords = [], searchPlan = {}) => {
  const excludedTerms = getExcludedTermsFromPlan(searchPlan)
  const uniqueKeywords = [...new Set(
    getPlannerList(keywords)
      .map(getTextValue)
      .filter(Boolean),
  )]

  if (!excludedTerms.length) return uniqueKeywords

  return uniqueKeywords.filter((keyword) => {
    return !keywordMatchesExclusions(keyword, excludedTerms)
  })
}

export const buildFrameBasedKakaoKeywords = (
  searchPlan = {},
  {
    includeWebQueries = false,
  } = {},
) => {
  if (isFrameDrivenSearch(searchPlan)) {
    const locationQuery = getResolvedSearchPlanLocationQuery(searchPlan)
    const searchQueries = getFrameWebSearchQueries(searchPlan)
    const targetAndResultTerms = [
      ...getFrameTargetObjects(searchPlan),
      ...getFrameResultMatchTerms(searchPlan),
    ]
    const candidatePlaceTypes = getFrameCandidatePlaceTypes(searchPlan)
    const candidates = [
      ...searchQueries,
      ...applyLocationToSearchKeywords(locationQuery, targetAndResultTerms),
      ...applyLocationToSearchKeywords(locationQuery, candidatePlaceTypes),
      ...targetAndResultTerms,
      ...candidatePlaceTypes,
    ]

    return filterKeywordsByExclusions(
      [...new Set(candidates.map(getTextValue).filter(Boolean))],
      searchPlan,
    )
  }

  const planKakaoKeywords = getPlanKakaoKeywordCandidates(searchPlan)
  const frameCandidates = getFrameCandidatePlaceTypes(searchPlan)
  const frameSearchQueries = isFrameDrivenSearch(searchPlan)
    ? getFrameWebSearchQueries(searchPlan)
    : []
  const frameCandidateSet = new Set(frameCandidates.map(normalizeLocationText))
  const scenarioFallbackKeywordSet = getScenarioFallbackKeywordSet(searchPlan)
  const deferScenarioFallback = isOnlyScenarioFallbackKeyword(planKakaoKeywords, searchPlan) &&
    frameCandidates.length > 0
  const candidates = [
    ...frameSearchQueries,
    ...(deferScenarioFallback ? frameCandidates : planKakaoKeywords),
    ...(deferScenarioFallback ? planKakaoKeywords : frameCandidates),
    ...(includeWebQueries && !isFrameDrivenSearch(searchPlan) ? getFrameWebSearchQueries(searchPlan) : []),
  ]

  const filteredCandidates = isFrameDrivenSearch(searchPlan)
    ? candidates.filter((keyword) => {
      const keywordText = normalizeLocationText(keyword)
      if (!keywordText) return false
      if (frameCandidates.length && isLocationOnlyKeyword(keyword, searchPlan)) return false
      if (
        frameCandidates.length &&
        scenarioFallbackKeywordSet.has(keywordText) &&
        !frameCandidateSet.has(keywordText)
      ) {
        return false
      }
      return true
    })
    : candidates

  return filterKeywordsByExclusions(filteredCandidates, searchPlan)
}

export const applyLocationToSearchKeywords = (locationQuery = '', keywords = []) => {
  const locationText = getTextValue(locationQuery)

  return getPlannerList(keywords).map((keyword) => {
    const keywordText = getTextValue(keyword)
    if (!locationText || normalizeLocationText(keywordText).includes(normalizeLocationText(locationText))) {
      return keywordText
    }

    return `${locationText} ${keywordText}`.trim()
  })
}

export const getSearchPlanDebugSnapshot = (searchPlan = {}, extra = {}) => {
  return {
    ...extra,
    parserProvider: searchPlan?.parser_provider || searchPlan?.parserProvider || '',
    parserFallback: searchPlan?.parser_fallback ?? searchPlan?.parserFallback ?? null,
    planSource: searchPlan?.plan_source || searchPlan?.planSource || '',
    executionMode: searchPlan?.execution_mode || searchPlan?.executionMode || '',
    locationMode: getFrameLocationMode(searchPlan) || searchPlan?.location_mode || searchPlan?.locationMode || '',
    anchorLocation: getFrameAnchorLocation(searchPlan),
    locationQuery: getResolvedSearchPlanLocationQuery(searchPlan),
    aiFallbackReason: searchPlan?.ai_fallback_reason || searchPlan?.aiFallbackReason || '',
    aiDebug: searchPlan?.ai_debug || searchPlan?.aiDebug || null,
    targetQuery: searchPlan?.targetQuery || searchPlan?.target_query || '',
    recommendationIntent: searchPlan?.recommendationIntent || searchPlan?.scenario || '',
    displayLabel: getFrameDisplayLabel(searchPlan) || searchPlan?.displayLabel || searchPlan?.display_label || '',
    placeIntentFrame: getSearchPlanFrame(searchPlan),
    targetObjects: getFrameTargetObjects(searchPlan),
    candidatePlaceTypes: getFrameCandidatePlaceTypes(searchPlan),
    constraints: getFrameConstraints(searchPlan),
    exclusions: getFrameExclusions(searchPlan),
    rankingPolicy: getFrameRankingPolicy(searchPlan),
    kakaoKeywordCandidates: buildFrameBasedKakaoKeywords(searchPlan, { includeWebQueries: false }),
    webSearchQueries: filterKeywordsByExclusions(getFrameWebSearchQueries(searchPlan), searchPlan),
  }
}

export const getRecommendationIntentForScoring = (recommendationIntent = '', searchPlan = {}) => {
  if (isFrameDrivenSearch(searchPlan)) {
    return getFramePolicyRecommendationIntent(searchPlan)
  }

  return recommendationIntent
}

export const getFramePolicyRecommendationIntent = (searchPlan = {}) => {
  const frameText = normalizeLocationText([
    searchPlan?.scenario,
    searchPlan?.recommendationIntent,
    searchPlan?.intentGroup,
    searchPlan?.intent_group,
    getSearchPlanFrame(searchPlan)?.situation,
    getFrameDisplayLabel(searchPlan),
    ...getFrameCandidateCategoryCodes(searchPlan),
    ...getFrameCandidatePlaceTypes(searchPlan),
    ...getFrameConstraints(searchPlan),
    ...getFrameResultMatchTerms(searchPlan),
  ].filter(Boolean).join(' '))

  if (
    (frameText.includes('cafe') || frameText.includes('카페')) &&
    ['작업', '노트북', '콘센트', '와이파이', 'wifi', '공부', '스터디'].some((keyword) => {
      return frameText.includes(normalizeLocationText(keyword))
    })
  ) {
    return 'work_cafe'
  }

  if (['산책', '힐링', '걷기', 'walkhealing'].some((keyword) => {
    return frameText.includes(normalizeLocationText(keyword))
  })) {
    return 'walk_healing'
  }

  if (['쉴', '쉼', '휴식', '휴게', '조용'].some((keyword) => {
    return frameText.includes(normalizeLocationText(keyword))
  })) {
    return 'waiting_place'
  }

  return ''
}

export const hasNormalizedKeywordMatch = (text = '', keywords = []) => {
  return keywords.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return normalizedKeyword && text.includes(normalizedKeyword)
  })
}

export const normalizeLocationText = (text = '') => {
  return String(text).toLowerCase().replace(/\s+/g, '')
}


export const getRecommendationMissingLabels = (place) => {
  return toDisplayList(place?.missingTagLabels || place?.missing_tag_labels)
}

export const getRecommendationMetaText = (place) => {
  if (!isRecommendationPlace(place)) {
    return ''
  }

  const sourceLabel = getPlaceSourceText(place)
  const confidence = getRecommendationConfidenceText(getRecommendationConfidence(place))
  const metaParts = [
    sourceLabel,
    confidence ? `신뢰도 ${confidence}` : '',
  ].filter(Boolean)

  return metaParts.join(' · ')
}

export const getRecommendationFallbackText = (place) => {
  if (isLowConfidenceWalkHealingFallback(place)) {
    return '낮은 신뢰도 후보'
  }

  return getTextValue(place?.recommendationFallbackLabel || place?.fallback_label)
}

export const getDistanceValue = (place) => {
  const distance = Number(place.distance)

  return Number.isFinite(distance) ? distance : null
}

export const getDistanceText = (place) => {
  const distance = getDistanceValue(place)

  if (distance === null) {
    return ''
  }

  if (distance >= 1000) {
    return `${Number((distance / 1000).toFixed(1))}km`
  }

  return `${Math.round(distance)}m`
}

export const isRecommendationPlace = (place) => {
  return (
    toDisplayList(place?.requestedConditionIds).length > 0 ||
    place?.sourceLabel === 'DB추천' ||
    place?.sourceLabel === '카카오+DB' ||
    place?.recommendationSourceType === 'kakao_candidate' ||
    place?.recommendationSourceType === 'web_evidence_candidate' ||
    place?.recommendationSourceType === 'web_reference' ||
    place?.source_type === 'kakao_candidate' ||
    place?.source_type === 'web_evidence_candidate' ||
    place?.source_type === 'web_reference' ||
    place?.resultType === 'kakao_fallback_candidate' ||
    place?.resultType === 'web_evidence_candidate' ||
    place?.tagSource === 'DB 추천 결과' ||
    place?.tagSource?.includes('DB 추천 결과')
  )
}

export const isDbRecommendationResult = (place = {}) => {
  const sourceType = getTextValue(place.recommendationSourceType || place.source_type)
  const dbSourceTypes = ['db_verified', 'db_candidate', 'db_category_fallback']

  return (
    dbSourceTypes.includes(sourceType) ||
    place.sourceLabel === 'DB추천' ||
    place.sourceLabel === '카카오+DB' ||
    place.searchSource === 'local_db' ||
    Boolean(place.savedPlaceId)
  )
}

export const isKakaoCandidateResult = (place = {}) => {
  const sourceType = getTextValue(place.recommendationSourceType || place.source_type)

  return (
    ['kakao_candidate', 'kakao_with_db_tags'].includes(sourceType) ||
    place.sourceLabel === '카카오' ||
    place.sourceLabel === '카카오+DB' ||
    place.searchSource === 'kakao' ||
    String(place.resultType || '').startsWith('kakao_') ||
    Boolean(place.kakaoPlaceId)
  )
}

export const isWebEvidenceCandidateResult = (place = {}) => {
  const sourceType = getTextValue(place.recommendationSourceType || place.source_type)

  return (
    ['web_evidence_candidate', 'web_reference'].includes(sourceType) ||
    place.searchSource === 'web' ||
    place.sourceLabel === '웹 근거 후보' ||
    place.sourceLabel === '웹 참고'
  )
}

export const getWebEvidenceUrl = (place = {}) => {
  if (!isWebEvidenceCandidateResult(place)) {
    return ''
  }

  return getTextValue(
    place.detailUrl ||
    place.detail_url ||
    place.placeUrl ||
    place.place_url ||
    place.externalUrl ||
    place.external_url,
  )
}

export const matchesResultFilter = (place, filterMode = 'all') => {
  if (filterMode === 'db') {
    return isDbRecommendationResult(place)
  }

  if (filterMode === 'kakao') {
    return isKakaoCandidateResult(place)
  }

  if (filterMode === 'web') {
    return isWebEvidenceCandidateResult(place)
  }

  return true
}

export const shouldRewriteRecommendationReason = (reason = '') => {
  const text = getTextValue(reason)
  if (!text) return true

  return (
    /collected candidate|compatible evidence|details need verification|candidate type|candidate is|frames require|evidence_level|semantic_score|retrieval_query|pre_ai|matching with|within target type/i.test(text) ||
    (/[A-Za-z]{3,}/.test(text) && !/[가-힣]/.test(text)) ||
    text.includes('추천 근거 높음') ||
    text.includes('DB 후보') ||
    text.includes('카카오 검색 근거 후보') ||
    text.includes('웹 검색 근거 후보')
  )
}

export const getRecommendationConfidence = (place) => {
  if (!isRecommendationPlace(place)) {
    return ''
  }

  const baseScore = getRecommendScore(place)
  const rawConfidence = getTextValue(
    place?.recommendationConfidence ||
    place?.confidence ||
    place?.recommendationConfidenceLabel ||
    place?.confidence_label,
  ).toLowerCase()

  const capConfidenceByScore = (confidence) => {
    if (baseScore > 0 && baseScore < 40) {
      return 'low'
    }

    if (baseScore > 0 && baseScore < 60 && confidence === 'high') {
      return 'medium'
    }

    return confidence
  }

  if (['high', 'medium', 'low'].includes(rawConfidence)) {
    return capConfidenceByScore(rawConfidence)
  }

  if (rawConfidence.includes('높') || rawConfidence.includes('strong') || rawConfidence.includes('verified')) {
    return capConfidenceByScore('high')
  }

  if (rawConfidence.includes('낮') || rawConfidence.includes('부족') || rawConfidence.includes('weak') || rawConfidence.includes('확인')) {
    return 'low'
  }

  if ((place?.warningTags || []).length) {
    return 'low'
  }

  if ((place?.verifiedTags || []).length || (place?.matchedTags || []).length) {
    return capConfidenceByScore('medium')
  }

  if ((place?.suggestedTags || []).length) {
    return 'low'
  }

  return capConfidenceByScore('medium')
}

export const getRecommendationConfidenceText = (confidence) => {
  const confidenceMap = {
    high: '높음',
    medium: '보통',
    low: '확인 필요',
  }

  return confidenceMap[confidence] || confidence || ''
}

export const getRecommendScore = (place) => {
  const score = Number(
    place.recommendScore ??
    place.score ??
    place.dataQualityScore ??
    0,
  )

  return Number.isFinite(score) ? score : 0
}

export const getPlaceFrameMatchStrength = (place = {}) => {
  return getTextValue(place.frameMatchStrength || place.frame_match_strength).toLowerCase()
}

export const getPlaceScoreCapReasons = (place = {}) => {
  return toDisplayList(place.scoreCapReasons || place.score_cap_reasons || place.score_breakdown?.score_cap_reasons)
}

export const isLowConfidenceWalkHealingFallback = (place = {}) => {
  if (place?.recommendationIntent !== 'walk_healing') return false

  const score = getRecommendScore(place)
  return isCategoryFallbackRecommendation(place) || score < 40
}

export const compareLowConfidenceFallback = (firstPlace, secondPlace) => {
  return Number(isLowConfidenceWalkHealingFallback(firstPlace)) -
    Number(isLowConfidenceWalkHealingFallback(secondPlace))
}

export const getConfidenceRank = (place) => {
  const confidence = getTextValue(
    place?.recommendationConfidence ||
    place?.confidence ||
    getRecommendationConfidence(place),
  ).toLowerCase()
  const confidenceRankMap = {
    high: 3,
    medium: 2,
    low: 1,
  }

  return confidenceRankMap[confidence] || 0
}

export const getResultSourceRank = (place) => {
  if (place?.sourceLabel === '카카오+DB') {
    return 0
  }

  if (place?.sourceLabel === 'DB추천' || place?.searchSource === 'local_db') {
    return 1
  }

  return 2
}

export const getSpecificPlaceTypeTerms = (menuProfile = {}) => {
  return (menuProfile.placeTypeTerms || []).filter((term) => {
    const normalizedTerm = normalizeLocationText(term)
    return !['카페', '식당', '음식점', '맛집'].includes(normalizedTerm)
  })
}

export const getTagDetailTextValues = (tagDetails = []) => {
  return (Array.isArray(tagDetails) ? tagDetails : []).flatMap((tag) => {
    if (typeof tag === 'string') return [tag]

    return [
      tag?.name,
      tag?.display_name,
      tag?.displayName,
      tag?.label,
    ].filter(Boolean)
  })
}

export const getTagTextValues = (tags = []) => {
  return (Array.isArray(tags) ? tags : []).flatMap((tag) => {
    if (typeof tag === 'string') return [tag]

    return [
      tag?.name,
      tag?.display_name,
      tag?.displayName,
      tag?.label,
    ].filter(Boolean)
  })
}

export const getDirectMenuMatchText = (place = {}) => {
  const fallbackTerms = place.resultType === 'kakao_fallback_candidate'
    ? [
      place.fallbackQuery,
      place.kakaoFallbackQuery,
      ...(place.matchedSearchKeywords || []),
    ]
    : []

  return normalizeLocationText([
    place.name,
    place.category,
    place.category_name,
    place.rawCategory,
    ...getTagTextValues(place.matchedTags || place.matched_tags),
    ...getTagTextValues(place.matchedTagLabels || place.matched_tag_labels),
    ...getTagTextValues(place.suggestedTags || place.suggested_tags),
    ...getTagTextValues(place.suggestedTagLabels || place.suggested_tag_labels),
    ...getTagTextValues(place.verifiedTags || place.verified_tags),
    ...getTagTextValues(place.verifiedTagLabels || place.verified_tag_labels),
    ...getTagDetailTextValues(place.tagDetails || place.tag_details),
    ...getTagTextValues(place.tags),
    ...fallbackTerms,
  ].filter(Boolean).join(' '))
}

export const isCategoryFallbackRecommendation = (place = {}) => {
  const sourceType = getTextValue(place.recommendationSourceType || place.source_type)
  return (
    sourceType === 'db_category_fallback' ||
    place.matchLevel === 'category_distance_fallback' ||
    place.fallbackLevel >= 3
  )
}

export const getKakaoFallbackCandidateScore = ({
  place,
  center = null,
  mainPlaceScore = 0,
  ancillaryPlacePenalty = 0,
  intentMismatchPenalty = 0,
  waitingPlacePenalty = 0,
  walkHealingPenalty = 0,
  walkHealingBonus = 0,
  workCafePenalty = 0,
} = {}) => {
  const distance = center
    ? getDistanceMetersBetweenPlaces(
      { lat: center.lat, lng: center.lng },
      { lat: Number(place?.y ?? place?.lat), lng: Number(place?.x ?? place?.lng) },
    )
    : Number(place?.distance || 0)
  const distanceBonus = Number.isFinite(distance)
    ? (
      distance <= 500
        ? 8
        : distance <= 1000
        ? 5
        : distance <= 3000
        ? 2
        : 0
    )
    : 0
  const shapeScore = Math.max(
    -12,
    Math.min(8, mainPlaceScore - ancillaryPlacePenalty - intentMismatchPenalty),
  )
  const penalty = Math.min(
    32,
    Math.round((waitingPlacePenalty + walkHealingPenalty) / 10) + workCafePenalty,
  )

  return Math.max(
    40,
    Math.min(
      KAKAO_FALLBACK_MAX_SCORE,
      45 + distanceBonus + shapeScore + walkHealingBonus - penalty,
    ),
  )
}

export const getRecommendationConditionData = (data = {}) => {
  return {
    ...(data?.ai_parse || {}),
    ...(data?.recommendation_condition || {}),
    ...(data?.condition || {}),
    ...(data?.conditions || {}),
  }
}

export const cleanFoodMenuKeyword = (value = '') => {
  return getTextValue(value)
    .replace(/^(근처에|근처|주변에|주변|가까운|가까이|여기서|지금)\s*/g, '')
    .replace(/(추천|찾아줘|찾아|좋은|괜찮은|먹고\s*싶어|먹고싶어)$/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 40)
}

export const extractFoodMenuKeywords = (query = '') => {
  const text = getTextValue(query)
  const menuKeywords = []

  FOOD_MENU_PATTERN_SUFFIXES.forEach((suffix) => {
    const index = text.indexOf(suffix)
    if (index > 0) {
      const menu = cleanFoodMenuKeyword(text.slice(0, index))
      if (menu) menuKeywords.push(menu)
    }
  })

  const compactText = normalizeLocationText(text)
  FOOD_MENU_KNOWN_KEYWORDS.forEach((keyword) => {
    if (compactText.includes(normalizeLocationText(keyword))) {
      menuKeywords.push(keyword)
    }
  })

  return [...new Set(menuKeywords)].slice(0, 3)
}

export const inferFoodPlaceTypeKeywords = ({ query = '', menuKeywords = [], conditionPlaceTypes = [] } = {}) => {
  const explicitPlaceTypes = toDisplayList(conditionPlaceTypes)
  if (explicitPlaceTypes.length) {
    return explicitPlaceTypes
  }

  const text = normalizeLocationText([query, ...menuKeywords].join(' '))

  if (FOOD_BAKERY_KEYWORDS.some((keyword) => text.includes(normalizeLocationText(keyword)))) {
    return ['베이커리', '빵집', '카페']
  }

  if (FOOD_CAFE_KEYWORDS.some((keyword) => text.includes(normalizeLocationText(keyword)))) {
    return ['카페']
  }

  return ['식당', '음식점']
}

export const compactKeyword = (keyword = '') => normalizeLocationText(keyword)

export const getPrimaryMenuKeywords = (menuKeywords = []) => {
  const uniqueKeywords = [...new Set(menuKeywords.filter(Boolean))]

  return uniqueKeywords.filter((keyword) => {
    const normalizedKeyword = compactKeyword(keyword)
    if (normalizedKeyword.length > 2) return true

    return !uniqueKeywords.some((otherKeyword) => {
      const normalizedOther = compactKeyword(otherKeyword)
      return (
        normalizedOther !== normalizedKeyword &&
        normalizedOther.length > normalizedKeyword.length &&
        normalizedOther.includes(normalizedKeyword)
      )
    })
  })
}

export const getMenuSearchProfile = ({ query = '', data = {} } = {}) => {
  const condition = getRecommendationConditionData(data)
  const menuKeywords = getPrimaryMenuKeywords([
    ...toDisplayList(condition?.menu_keywords),
    ...extractFoodMenuKeywords(query),
  ].filter((keyword, index, keywords) => keyword && keywords.indexOf(keyword) === index))
  const placeTypeKeywords = inferFoodPlaceTypeKeywords({
    query,
    menuKeywords,
    conditionPlaceTypes: condition?.place_type_keywords,
  })
  const purposeKeywords = [
    ...toDisplayList(condition?.purpose_keywords),
    ...(normalizeLocationText(query).includes(normalizeLocationText('맛집')) ? ['맛집'] : []),
  ].filter((keyword, index, keywords) => keyword && keywords.indexOf(keyword) === index)

  return {
    menuIntent: Boolean(menuKeywords.length || purposeKeywords.length),
    menuKeywords,
    placeTypeKeywords,
    purposeKeywords,
    directMenuTerms: [...new Set(menuKeywords.filter(Boolean))],
    placeTypeTerms: [...new Set(placeTypeKeywords.filter(Boolean))],
    directTerms: [...new Set(menuKeywords.filter(Boolean))],
  }
}

export const getRecommendationDirectMatchText = (place = {}) => {
  return getDirectMenuMatchText(place)
}

export const isDirectMenuDbMatch = (place = {}, menuProfile = {}) => {
  if (!menuProfile.menuIntent) return true

  const directTerms = [
    ...(menuProfile.directTerms || []),
    ...getSpecificPlaceTypeTerms(menuProfile),
  ]
  const directMatchText = getRecommendationDirectMatchText(place)
  const hasDirectTermMatch = directTerms.some((term) => {
    return directMatchText.includes(normalizeLocationText(term))
  })

  return hasDirectTermMatch
}

export const getDirectMenuDbMatchCount = (dbResults = [], menuProfile = {}) => {
  if (!menuProfile.menuIntent) {
    return dbResults.length
  }

  return dbResults.filter((place) => isDirectMenuDbMatch(place, menuProfile)).length
}

export const hasExplicitWalkCafeIntent = (query = '', parsedIntent = null) => {
  const text = normalizeLocationText([
    query,
    parsedIntent?.targetQuery,
    parsedIntent?.targetKeyword,
    ...toDisplayList(parsedIntent?.place_type_keywords),
    ...toDisplayList(parsedIntent?.kakaoKeywordCandidates),
  ].filter(Boolean).join(' '))

  return WALK_HEALING_CAFE_KEYWORDS.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
}

