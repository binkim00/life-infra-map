import { normalizeLocationText } from '@/utils/homePlaceHelpers'

export const getRegionSearchCoreKeyword = (targetQuery) => {
  const targetText = normalizeLocationText(targetQuery)

  const rules = [
    ['카페', '카페'],
    ['커피', '카페'],
    ['맛집', '맛집'],
    ['식당', '식당'],
    ['흡연', '흡연구역'],
    ['산책', '공원'],
    ['쉴', '쉼터'],
    ['쉬', '쉼터'],
    ['공원', '공원'],
    ['해수욕장', '해수욕장'],
    ['도서관', '도서관'],
    ['주차', '주차장'],
    ['화장실', '화장실'],
  ]

  const matched = rules.find(([keyword]) => {
    return targetText.includes(normalizeLocationText(keyword))
  })

  return matched?.[1] || targetQuery
}

export const getKakaoResultRegionKey = (place) => {
  const address = place.road_address_name || place.address_name || ''
  const tokens = address.split(/\s+/).filter(Boolean)

  if (tokens.length >= 2) {
    return tokens.slice(0, 2).join(' ')
  }

  return tokens[0] || '지역 미상'
}

export const getPlacesCenter = (places) => {
  const validPlaces = places
    .map((place) => ({
      lat: Number(place.y ?? place.lat),
      lng: Number(place.x ?? place.lng),
    }))
    .filter((place) => Number.isFinite(place.lat) && Number.isFinite(place.lng))

  if (!validPlaces.length) {
    return null
  }

  return {
    lat: validPlaces.reduce((sum, place) => sum + place.lat, 0) / validPlaces.length,
    lng: validPlaces.reduce((sum, place) => sum + place.lng, 0) / validPlaces.length,
  }
}

export const groupKakaoPlacesByRegion = (places) => {
  const groupsByKey = new Map()

  places.forEach((place) => {
    const key = getKakaoResultRegionKey(place)
    const group = groupsByKey.get(key) || {
      key,
      places: [],
    }

    group.places.push(place)
    groupsByKey.set(key, group)
  })

  return [...groupsByKey.values()]
    .map((group) => ({
      ...group,
      center: getPlacesCenter(group.places),
    }))
    .sort((first, second) => second.places.length - first.places.length)
}

export const shouldAskRegionCandidateSelection = (groups, totalCount) => {
  if (groups.length <= 1) return false

  const [first, second] = groups
  if (!first || !second) return false

  const topRatio = first.places.length / Math.max(totalCount, 1)
  return topRatio < 0.6 || first.places.length - second.places.length <= 2
}

export const makeRegionCandidateFromGroup = (group, convertedResults) => {
  const center = group.center

  return {
    id: `region-candidate-${group.key}`,
    place_name: group.key,
    category_name: '지역',
    address_name: `${group.places.length}개 결과`,
    road_address_name: '',
    lat: center?.lat,
    lng: center?.lng,
    y: center?.lat,
    x: center?.lng,
    source: 'region',
    candidateKind: '지역',
    score: group.places.length,
    regionResults: convertedResults,
  }
}
