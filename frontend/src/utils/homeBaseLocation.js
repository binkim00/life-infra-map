import {
  getDistanceMetersBetweenPlaces,
  normalizeLocationText,
} from '@/utils/homePlaceHelpers'
import {
  BASE_LOCATION_POI_KEYWORDS,
  getRegionTokens,
  hasPoiHint,
  hasRegionQualifier,
} from '@/utils/homeSearchPlanning'

const BASE_LOCATION_TRANSPORT_KEYWORDS = [
  '역',
  '터미널',
  '공항',
  '정류장',
  '버스',
  '지하철',
  '전철',
]

const BASE_LOCATION_PLACE_CATEGORY_KEYWORDS = [
  '교통',
  '지하철',
  '전철',
  '터미널',
  '공항',
  '관광',
  '명소',
  '문화',
  '시설',
  '백화점',
  '시장',
  '상권',
  '도서관',
]

const BASE_LOCATION_REPRESENTATIVE_KEYWORDS = [
  '해수욕장',
  '광장',
  '공원',
  '대학교',
  '대학',
  '캠퍼스',
  '관광',
  '관광지',
  '명소',
  '문화',
  '시장',
  '백화점',
  '도서관',
]

const BASE_LOCATION_FACILITY_KEYWORDS = [
  '주차장',
  '공영주차장',
  '화장실',
  '공중화장실',
  '편의점',
  '미용실',
  '헤어',
  '카페',
  '커피',
  '음식점',
  '식당',
  '매장',
  '업체',
  '상점',
  '지점',
  '역점',
  '가맹점',
  '마트',
  '이마트24',
  '세븐일레븐',
  'cu',
  'gs25',
]

const BASE_LOCATION_REGION_KEYWORDS = [
  '동',
  '읍',
  '면',
  '리',
  '구',
  '군',
]

export const buildBaseLocationSearchQueries = (baseKeyword) => {
  const cleanedKeyword = baseKeyword.trim()
  return [
    cleanedKeyword,
    `${cleanedKeyword}역`,
    `${cleanedKeyword} 거리`,
    `${cleanedKeyword} 상권`,
    `${cleanedKeyword} 번화가`,
  ].filter((query, index, queries) => {
    return query && queries.indexOf(query) === index
  })
}

const getBaseLocationCandidateSearchText = (candidate = {}) => {
  return normalizeLocationText([
    candidate.place_name,
    candidate.category_name,
    candidate.address_name,
    candidate.road_address_name,
  ].filter(Boolean).join(' '))
}

const hasBaseLocationCandidateKeyword = (candidate = {}, keywords = []) => {
  const text = getBaseLocationCandidateSearchText(candidate)
  return keywords.some((keyword) => {
    return text.includes(normalizeLocationText(keyword))
  })
}

const isFacilityBaseLocationCandidate = (candidate = {}) => {
  return hasBaseLocationCandidateKeyword(candidate, BASE_LOCATION_FACILITY_KEYWORDS)
}

const isRegionBaseLocationCandidate = (candidate = {}) => {
  if (candidate.source === 'address') {
    const addressText = candidate.address_name || candidate.place_name || ''
    const lastToken = String(addressText).trim().split(/\s+/).pop() || ''
    return /[동읍면리구군]$/.test(lastToken)
  }

  const nameText = normalizeLocationText(candidate.place_name)
  return BASE_LOCATION_REGION_KEYWORDS.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return nameText.endsWith(normalizedKeyword)
  })
}

const isTransportBaseLocationCandidate = (candidate = {}) => {
  if (isFacilityBaseLocationCandidate(candidate)) return false

  const nameText = normalizeLocationText(candidate.place_name)
  const categoryText = normalizeLocationText(candidate.category_name)

  return BASE_LOCATION_TRANSPORT_KEYWORDS.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return nameText.includes(normalizedKeyword) || categoryText.includes(normalizedKeyword)
  })
}

const isRepresentativeBaseLocationCandidate = (candidate = {}) => {
  if (isFacilityBaseLocationCandidate(candidate)) return false
  return hasBaseLocationCandidateKeyword(candidate, BASE_LOCATION_REPRESENTATIVE_KEYWORDS)
}

const getBaseLocationCandidatePriority = (candidate = {}) => {
  if (isFacilityBaseLocationCandidate(candidate)) return 5
  if (isTransportBaseLocationCandidate(candidate)) return 1
  if (isRegionBaseLocationCandidate(candidate)) return 2
  if (isRepresentativeBaseLocationCandidate(candidate)) return 3
  return 4
}

const getBaseLocationCandidatePriorityLabel = (priority) => {
  if (priority === 1) return '역/교통'
  if (priority === 2) return '지역'
  if (priority === 3) return '대표 장소'
  if (priority === 5) return '시설/매장'
  return '장소'
}

const getBaseCandidateKind = (candidate) => {
  if (candidate.source === 'address') {
    return isRegionBaseLocationCandidate(candidate) ? '지역' : '주소'
  }

  return getBaseLocationCandidatePriorityLabel(getBaseLocationCandidatePriority(candidate))
}

const isPlaceCandidate = (candidate) => {
  return candidate?.source !== 'address'
}

const hasBasePoiSignal = (candidate) => {
  const nameText = normalizeLocationText(candidate?.place_name)
  const categoryText = normalizeLocationText(candidate?.category_name)

  return BASE_LOCATION_POI_KEYWORDS.some((keyword) => {
    const normalizedKeyword = normalizeLocationText(keyword)
    return nameText.includes(normalizedKeyword) || categoryText.includes(normalizedKeyword)
  }) || BASE_LOCATION_PLACE_CATEGORY_KEYWORDS.some((keyword) => {
    return categoryText.includes(normalizeLocationText(keyword))
  })
}

const isExactPoiMatch = (candidate, query) => {
  if (!candidate) return false

  const queryText = normalizeLocationText(query)
  const nameText = normalizeLocationText(candidate.place_name)
  const sourceQueryText = normalizeLocationText(candidate.sourceQuery)

  if (!queryText || !nameText) return false

  if (nameText === queryText) return true

  if (sourceQueryText && nameText === sourceQueryText && hasBasePoiSignal(candidate)) {
    return true
  }

  if (hasPoiHint(query) && (nameText.includes(queryText) || queryText.includes(nameText))) {
    return true
  }

  return false
}

const isBroadAdministrativeAddress = (candidate) => {
  if (candidate.source !== 'address') return false

  const addressText = candidate.address_name || candidate.place_name
  const tokens = String(addressText).trim().split(/\s+/)
  const lastToken = tokens[tokens.length - 1] || ''

  return /[시도군구읍면]$/.test(lastToken) && !/[동리]$/.test(lastToken)
}

export const normalizeKakaoBaseCandidate = (item, source, index, sourceQuery = '') => {
  const id = item.id || `${source}-${item.x}-${item.y}-${index}`
  const name = item.place_name || item.address_name || item.road_address?.address_name || item.address?.address_name || ''
  const address = item.road_address_name || item.address_name || item.address?.address_name || ''
  const lat = Number(item.y)
  const lng = Number(item.x)

  return {
    id: `base-candidate-${id}`,
    kakaoId: id,
    place_name: name,
    category_name: item.category_name || (source === 'address' ? '주소' : ''),
    address_name: address,
    road_address_name: item.road_address_name || '',
    phone: item.phone || '',
    place_url: item.place_url || '',
    x: item.x,
    y: item.y,
    lat,
    lng,
    source,
    sourceQuery,
    rank: index + 1,
    score: 0,
    scoreReasons: [],
    candidateKind: '',
  }
}

export const scoreBaseLocationCandidate = (candidate, query, center = null) => {
  const queryText = normalizeLocationText(query)
  const nameText = normalizeLocationText(candidate.place_name)
  const addressText = normalizeLocationText(candidate.address_name || candidate.road_address_name)
  const categoryText = normalizeLocationText(candidate.category_name)
  const sourceQueryText = normalizeLocationText(candidate.sourceQuery)
  const baseLocationPriority = getBaseLocationCandidatePriority(candidate)
  const reasons = []
  let score = 0

  if (baseLocationPriority === 1) {
    score += 120
    reasons.push('교통 기준점 우선')
  } else if (baseLocationPriority === 2) {
    score += 90
    reasons.push('지역 기준점 우선')
  } else if (baseLocationPriority === 3) {
    score += 70
    reasons.push('대표 장소 우선')
  } else if (baseLocationPriority === 5) {
    score -= 90
    reasons.push('시설/매장 후순위')
  }

  if (nameText === queryText) {
    score += 45
    reasons.push('장소명 정확 일치')
  } else if (nameText && (nameText.includes(queryText) || queryText.includes(nameText))) {
    score += 30
    reasons.push('장소명 유사')
  }

  if (candidate.source !== 'address' && sourceQueryText && nameText.includes(sourceQueryText)) {
    score += 18
    reasons.push('확장 장소 검색어 일치')
  }

  if (addressText.includes(queryText)) {
    score += candidate.source === 'address' ? 18 : 24
    reasons.push('주소 일치')
  }

  const regionMatches = getRegionTokens(query).filter((token) => {
    return addressText.includes(normalizeLocationText(token))
  })

  if (regionMatches.length) {
    score += Math.min(regionMatches.length * 10, 25)
    reasons.push('지역명 일치')
  }

  if (BASE_LOCATION_POI_KEYWORDS.some((keyword) => {
    return nameText.includes(normalizeLocationText(keyword)) || categoryText.includes(normalizeLocationText(keyword))
  })) {
    score += 28
    reasons.push('기준 위치 POI')
  }

  if (BASE_LOCATION_PLACE_CATEGORY_KEYWORDS.some((keyword) => {
    return categoryText.includes(normalizeLocationText(keyword))
  })) {
    score += 18
    reasons.push('장소형 카테고리')
  }

  if (candidate.source !== 'address') {
    score += 16
    reasons.push('장소 후보')
  } else {
    score -= 10
    reasons.push('주소 후보')
  }

  if (candidate.source === 'address' && (!candidate.place_name || candidate.place_name === candidate.address_name)) {
    score -= 12
    reasons.push('주소명만 있음')
  }

  if (isBroadAdministrativeAddress(candidate)) {
    score -= 18
    reasons.push('넓은 행정구역')
  }

  score += Math.max(20 - candidate.rank * 2, 2)

  const distance = getDistanceMetersBetweenPlaces(center, candidate)
  if (Number.isFinite(distance)) {
    score += Math.max(8 - distance / 50000, 0)
  }

  return {
    ...candidate,
    score: Math.round(score),
    scoreReasons: reasons,
    baseLocationPriority,
    candidateKind: getBaseCandidateKind(candidate),
  }
}

export const sortBaseLocationCandidates = (candidates = []) => {
  return [...candidates].sort((first, second) => {
    const firstPriority = first.baseLocationPriority || getBaseLocationCandidatePriority(first)
    const secondPriority = second.baseLocationPriority || getBaseLocationCandidatePriority(second)

    return (
      firstPriority - secondPriority ||
      second.score - first.score ||
      first.rank - second.rank
    )
  })
}

export const dedupeBaseLocationCandidates = (candidates = []) => {
  const deduped = []
  const seen = new Set()

  candidates.forEach((candidate) => {
    if (!Number.isFinite(candidate.lat) || !Number.isFinite(candidate.lng)) return

    const key = [
      normalizeLocationText(candidate.place_name),
      Math.round(candidate.lat * 10000),
      Math.round(candidate.lng * 10000),
    ].join(':')

    if (seen.has(key)) return

    seen.add(key)
    deduped.push(candidate)
  })

  return deduped
}

export const getAutoSelectedBaseCandidate = (candidates = [], query = '') => {
  if (!candidates.length) return null

  const [first, second] = candidates
  const queryLength = normalizeLocationText(query).length
  const shortAmbiguousQuery = (
    queryLength <= 3 &&
    !hasRegionQualifier(query) &&
    !hasPoiHint(query)
  )
  const hasAddressCandidatesFromMultipleRegions = new Set(
    candidates
      .filter((candidate) => candidate.source === 'address')
      .map((candidate) => {
        return String(candidate.address_name || candidate.place_name).split(/\s+/).slice(0, 2).join(' ')
      })
      .filter(Boolean),
  ).size > 1
  const scoreGap = second ? first.score - second.score : first.score
  const firstIsPlacePoi = isPlaceCandidate(first) && hasBasePoiSignal(first)
  const exactPoiMatch = isExactPoiMatch(first, query)
  const hasClearQuery = hasPoiHint(query) || hasRegionQualifier(query)

  const autoSelectConfidence = {
    exactPoiMatch,
    placePoiHighScore: firstIsPlacePoi && first.score >= 70,
    strongScoreGap: scoreGap >= (firstIsPlacePoi ? 10 : 18),
    clearPoiQueryMatch: hasPoiHint(query) && firstIsPlacePoi && (
      normalizeLocationText(first.place_name).includes(normalizeLocationText(query)) ||
      normalizeLocationText(query).includes(normalizeLocationText(first.place_name))
    ),
    clearRegionPlace: hasRegionQualifier(query) && firstIsPlacePoi && first.score >= 68,
  }

  if (
    shortAmbiguousQuery &&
    candidates.length > 1
  ) {
    return null
  }

  if (
    shortAmbiguousQuery &&
    hasAddressCandidatesFromMultipleRegions &&
    first.source === 'address'
  ) {
    return null
  }

  if (shortAmbiguousQuery && first.source === 'address' && first.candidateKind === '주소') {
    return null
  }

  if (
    autoSelectConfidence.exactPoiMatch &&
    firstIsPlacePoi &&
    first.score >= 62
  ) {
    return first
  }

  if (
    autoSelectConfidence.clearPoiQueryMatch &&
    autoSelectConfidence.placePoiHighScore
  ) {
    return first
  }

  if (
    autoSelectConfidence.clearRegionPlace &&
    autoSelectConfidence.strongScoreGap
  ) {
    return first
  }

  if (
    firstIsPlacePoi &&
    first.score >= (hasClearQuery ? 68 : 78) &&
    autoSelectConfidence.strongScoreGap
  ) {
    return first
  }

  return null
}
