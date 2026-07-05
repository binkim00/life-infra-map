const toFiniteNumber = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

const toText = (value) => {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

const isLocalDbPlace = (place = {}) => {
  const resultSource = toText(place.resultSource || place.result_source)
  const searchSource = toText(place.searchSource || place.search_source)
  const source = toText(place.source)

  return Boolean(place.savedPlaceId) ||
    resultSource === 'db' ||
    searchSource === 'local_db' ||
    source === 'local_db'
}

export const buildSavedPlacePayload = (place = {}, extra = {}) => {
  const lat = toFiniteNumber(place.lat)
  const lng = toFiniteNumber(place.lng)
  const placeId = place.savedPlaceId || (isLocalDbPlace(place) ? place.id : null)
  const source = isLocalDbPlace(place)
    ? 'local_db'
    : (toText(place.resultSource || place.searchSource || place.source) || 'other')
  const externalId = toText(
    place.externalId ||
    place.external_id ||
    (!placeId ? place.id : ''),
  )
  const detailUrl = toText(
    place.detailUrl ||
    place.detail_url ||
    place.placeUrl ||
    place.place_url ||
    place.kakaoPlaceUrl ||
    place.kakao_place_url,
  )

  return {
    ...(placeId ? { place_id: placeId } : {}),
    source: source === 'db' ? 'local_db' : source,
    external_id: externalId,
    name: toText(place.name),
    category: toText(place.categoryLabel || place.category),
    address: toText(place.address || place.detailLocation || place.roadAddress || place.road_address),
    lat,
    lng,
    detail_url: detailUrl,
    kakao_place_url: toText(place.kakaoPlaceUrl || place.kakao_place_url || detailUrl),
    phone: toText(place.phone),
    raw: {
      source_label: toText(place.sourceLabel || place.source_label),
      result_source: toText(place.resultSource || place.result_source),
    },
    ...extra,
  }
}

export const getSavedPlaceClientKey = (place = {}) => {
  const payload = buildSavedPlacePayload(place)

  if (payload.place_id) return `place:${payload.place_id}`
  if (payload.external_id) return `${payload.source}:${payload.external_id}`

  return `snapshot:${payload.source}:${payload.name}:${payload.lat || ''}:${payload.lng || ''}`
}
