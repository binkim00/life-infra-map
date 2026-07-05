import {
  MAX_SEARCH_RESULT_COUNT,
  SEARCH_SIZE_PER_PAGE,
} from '@/constants/homeSearchConstants'
import { getTextValue } from '@/utils/homePlaceHelpers'

export const dedupeKakaoRawPlaces = (places = []) => {
  const seen = new Set()
  const deduped = []

  places.forEach((place) => {
    const key = String(place.id || `${place.place_name}-${place.x}-${place.y}`)
    if (seen.has(key)) return

    seen.add(key)
    deduped.push(place)
  })

  return deduped
}

export const runKakaoKeywordSearch = (placesService, keyword, options = {}) => {
  return new Promise((resolve, reject) => {
    placesService.keywordSearch(
      keyword,
      (data, status) => {
        if (status === window.kakao.maps.services.Status.OK) {
          resolve(data)
          return
        }

        if (status === window.kakao.maps.services.Status.ZERO_RESULT) {
          resolve([])
          return
        }

        reject(new Error('카카오 장소 검색 중 오류가 발생했습니다.'))
      },
      options,
    )
  })
}

export const runKakaoKeywordSearchLimited = async (
  placesService,
  keyword,
  options = {},
  {
    maxPages = Math.ceil(MAX_SEARCH_RESULT_COUNT / SEARCH_SIZE_PER_PAGE),
  } = {},
) => {
  const allResults = []
  let page = 1

  while (allResults.length < MAX_SEARCH_RESULT_COUNT && page <= maxPages) {
    const pageResults = await runKakaoKeywordSearch(
      placesService,
      keyword,
      {
        ...options,
        size: SEARCH_SIZE_PER_PAGE,
        page,
      },
    )

    if (!pageResults.length) {
      break
    }

    allResults.push(...pageResults)

    if (pageResults.length < SEARCH_SIZE_PER_PAGE) {
      break
    }

    page += 1
  }

  return allResults.slice(0, MAX_SEARCH_RESULT_COUNT)
}

export const runKakaoKeywordCandidateSearch = async (
  placesService,
  keywords = [],
  options = {},
  searchOptions = { maxPages: 1 },
) => {
  const results = []

  for (const keyword of keywords.filter(Boolean)) {
    const keywordResults = await runKakaoKeywordSearchLimited(
      placesService,
      keyword,
      options,
      searchOptions,
    )

    results.push(...keywordResults)

    if (results.length >= SEARCH_SIZE_PER_PAGE) {
      break
    }
  }

  return dedupeKakaoRawPlaces(results).slice(0, MAX_SEARCH_RESULT_COUNT)
}

export const runKakaoAddressSearch = (geocoder, keyword) => {
  return new Promise((resolve, reject) => {
    geocoder.addressSearch(keyword, (data, status) => {
      if (status === window.kakao.maps.services.Status.OK) {
        resolve(data)
        return
      }

      if (status === window.kakao.maps.services.Status.ZERO_RESULT) {
        resolve([])
        return
      }

      reject(new Error('카카오 주소 검색 중 오류가 발생했습니다.'))
    })
  })
}

export const normalizeKakaoRegionName = (name = '') => {
  return getTextValue(name)
    .replace(/특별자치시$/, '')
    .replace(/특별자치도$/, '')
    .replace(/특별시$/, '')
    .replace(/광역시$/, '')
    .replace(/자치도$/, '')
    .replace(/도$/, '')
}

export const formatKakaoRegionHint = (address = {}) => {
  const region1 = normalizeKakaoRegionName(address.region_1depth_name)
  const region2 = getTextValue(address.region_2depth_name)

  if (region1 && region2) {
    return `${region1} ${region2}`.trim()
  }

  const addressNameParts = getTextValue(address.address_name).split(/\s+/).filter(Boolean)
  if (addressNameParts.length >= 2) {
    return `${normalizeKakaoRegionName(addressNameParts[0])} ${addressNameParts[1]}`.trim()
  }

  return region1 || region2 || ''
}

export const reverseGeocodeLocationHint = (geocoder, center) => {
  if (!geocoder || !center || !Number.isFinite(Number(center.lat)) || !Number.isFinite(Number(center.lng))) {
    return Promise.resolve('')
  }

  return new Promise((resolve) => {
    geocoder.coord2Address(Number(center.lng), Number(center.lat), (data, status) => {
      if (status !== window.kakao.maps.services.Status.OK || !Array.isArray(data) || !data.length) {
        resolve('')
        return
      }

      const first = data[0] || {}
      const address = first.address || first.road_address || {}
      resolve(formatKakaoRegionHint(address))
    })
  })
}
