import axios from 'axios'

const API_BASE_URL = 'http://127.0.0.1:8000/api'

export const getRecommendations = async ({
  scenario = 'work_cafe',
  lat = 37.5665,
  lng = 126.9780,
  limit = 10,
  radius = null,
}) => {
  const response = await axios.get(`${API_BASE_URL}/recommendations/search/`, {
    params: {
      scenario,
      lat,
      lng,
      limit,
      radius,
    },
  })

  return response.data
}

export const aiSearchRecommendations = async ({
  query,
  lat = 37.5665,
  lng = 126.9780,
  limit = 10,
  radius = null,
}) => {
  const response = await axios.post(`${API_BASE_URL}/recommendations/ai-search/`, {
    query,
    lat,
    lng,
    limit,
    radius,
  })

  return response.data
}

export const getSavedPlaces = async ({
  q = '',
  category = '',
  source = '',
  status = '',
  lat = null,
  lng = null,
  radius = null,
  limit = 100,
} = {}) => {
  const response = await axios.get(`${API_BASE_URL}/recommendations/places/`, {
    params: {
      q,
      category,
      source,
      status,
      lat,
      lng,
      radius,
      limit,
    },
  })

  return response.data
}

export const getKakaoPlaceTags = async (externalIds = []) => {
  const response = await axios.get(`${API_BASE_URL}/recommendations/kakao-place-tags/`, {
    params: {
      external_ids: externalIds.join(','),
    },
  })

  return response.data
}
