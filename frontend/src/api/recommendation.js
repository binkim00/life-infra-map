import axios from 'axios'
import api from '@/api/axios'

const API_BASE_URL = 'http://127.0.0.1:8000/api'

export const aiSearchRecommendations = async ({
  query,
  lat = 37.5665,
  lng = 126.9780,
  limit = 10,
  radius = null,
  ...extraPayload
}) => {
  const response = await axios.post(`${API_BASE_URL}/recommendations/ai-search/`, {
    query,
    lat,
    lng,
    limit,
    radius,
    ...extraPayload,
  })

  return response.data
}

export const checkSearchSafety = async ({ query }) => {
  const response = await axios.post(`${API_BASE_URL}/recommendations/search-safety/`, {
    query,
  })

  return response.data
}

export const buildConversationalSearchPlan = async ({
  query,
  lat = null,
  lng = null,
  mapCenter = null,
  previousContext = null,
  ...extraPayload
}) => {
  const response = await axios.post(`${API_BASE_URL}/recommendations/conversational-search-plan/`, {
    query,
    lat,
    lng,
    map_center: mapCenter,
    previous_context: previousContext,
    previous_search_context: previousContext,
    ...extraPayload,
  })

  return response.data
}

export const runAiWebSearch = async ({
  query,
  lat = null,
  lng = null,
  locationHint = '',
  searchPlan = {},
  condition = {},
  existingResultsSummary = {},
}) => {
  const response = await axios.post(`${API_BASE_URL}/recommendations/ai-web-search/`, {
    query,
    lat,
    lng,
    location_hint: locationHint,
    search_plan: searchPlan,
    condition,
    existing_results_summary: existingResultsSummary,
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

export const searchMapPlaces = async ({
  q = '',
  source = 'all',
  lat = null,
  lng = null,
  radius = 3000,
  limit = 30,
} = {}) => {
  const response = await axios.get(`${API_BASE_URL}/recommendations/map-search/`, {
    params: {
      q,
      source,
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

export const saveSearchLog = async (payload) => {
  const response = await api.post('/recommendations/search-logs/', payload)

  return response.data
}

export const fetchSearchLogs = async ({ page = 1, pageSize = 5 } = {}) => {
  const response = await api.get('/recommendations/search-logs/', {
    params: {
      page,
      page_size: pageSize,
    },
  })

  return response.data
}

export const deleteSearchLog = async (searchLogId) => {
  const response = await api.delete(`/recommendations/search-logs/${searchLogId}/`)

  return response.data
}

export const fetchUserPreferences = async ({
  page = 1,
  pageSize = 5,
  source = '',
  type = '',
  limit = null,
} = {}) => {
  const response = await api.get('/recommendations/preferences/', {
    params: {
      ...(limit ? { limit } : { page, page_size: pageSize }),
      ...(source ? { source } : {}),
      ...(type ? { type } : {}),
    },
  })

  return response.data
}

export const fetchPreferenceTags = async () => {
  const response = await api.get('/recommendations/preference-tags/')

  return response.data
}

export const createUserPreference = async (payload) => {
  const response = await api.post('/recommendations/preferences/', payload)

  return response.data
}

export const deleteUserPreference = async (preferenceId) => {
  const response = await api.delete(`/recommendations/preferences/${preferenceId}/`)

  return response.data
}

export const rebuildUserPreferences = async () => {
  const response = await api.post('/recommendations/preferences/rebuild/')

  return response.data
}

export const createPlaceReport = async (formData) => {
  const response = await api.post('/recommendations/place-reports/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })

  return response.data
}

export const fetchMyPlaceReports = async ({ page = 1, pageSize = 5 } = {}) => {
  const response = await api.get('/recommendations/place-reports/', {
    params: {
      page,
      page_size: pageSize,
    },
  })

  return response.data
}

export const fetchAdminPlaceReports = async ({
  status = '',
  reportType = '',
  page = 1,
  pageSize = 10,
} = {}) => {
  const response = await api.get('/recommendations/admin/place-reports/', {
    params: {
      page,
      page_size: pageSize,
      ...(status ? { status } : {}),
      ...(reportType ? { report_type: reportType } : {}),
    },
  })

  return response.data
}

export const fetchAdminPlaceReportDetail = async (reportId) => {
  const response = await api.get(`/recommendations/admin/place-reports/${reportId}/`)

  return response.data
}

export const approvePlaceReport = async (reportId, payload = {}) => {
  const response = await api.post(`/recommendations/admin/place-reports/${reportId}/approve/`, payload)

  return response.data
}

export const rejectPlaceReport = async (reportId, payload = {}) => {
  const response = await api.post(`/recommendations/admin/place-reports/${reportId}/reject/`, payload)

  return response.data
}
