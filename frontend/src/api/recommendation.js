import api from '@/api/axios'

const CONVERSATION_SESSION_KEY = 'lifeInfraMap.conversationSession.v1'
let conversationSessionPromise = null

const readConversationSession = () => {
  if (typeof window === 'undefined') return null
  try {
    const value = JSON.parse(window.sessionStorage.getItem(CONVERSATION_SESSION_KEY) || 'null')
    return value?.id ? value : null
  } catch {
    return null
  }
}

const storeConversationSession = (value) => {
  if (typeof window !== 'undefined') {
    window.sessionStorage.setItem(CONVERSATION_SESSION_KEY, JSON.stringify(value))
  }
  return value
}

export const startNewConversationSession = () => {
  conversationSessionPromise = null
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(CONVERSATION_SESSION_KEY)
  }
}

const getOrCreateConversationSession = async () => {
  const stored = readConversationSession()
  if (stored) return stored
  if (!conversationSessionPromise) {
    conversationSessionPromise = api
      .post('/recommendations/conversation-sessions/', {})
      .then(({ data }) => storeConversationSession({
        id: data.id,
        token: data.conversation_token || '',
      }))
      .finally(() => {
        conversationSessionPromise = null
      })
  }
  return conversationSessionPromise
}

const postConversationTurn = async (payload, { retry = true } = {}) => {
  const session = await getOrCreateConversationSession()
  try {
    const response = await api.post(
      `/recommendations/conversation-sessions/${session.id}/turns/`,
      payload,
      session.token ? { headers: { 'X-Conversation-Token': session.token } } : undefined,
    )
    return response.data
  } catch (error) {
    if (retry && [404, 409].includes(error?.response?.status)) {
      startNewConversationSession()
      return postConversationTurn(payload, { retry: false })
    }
    throw error
  }
}

export const aiSearchRecommendations = async ({
  query,
  lat = 37.5665,
  lng = 126.9780,
  limit = 10,
  radius = null,
  ...extraPayload
}) => {
  const payload = {
    query,
    lat,
    lng,
    limit,
    radius,
    ...extraPayload,
  }
  try {
    return await postConversationTurn(payload)
  } catch (error) {
    // Keep older deployments usable while the additive conversation API rolls out.
    if (!error?.response || [404, 405].includes(error.response.status)) {
      const response = await api.post('/recommendations/ai-search/', payload)
      return response.data
    }
    throw error
  }
}

export const aiSearchCandidateRecommendations = async ({
  query,
  lat = 37.5665,
  lng = 126.9780,
  limit = 10,
  radius = null,
  ...extraPayload
}) => {
  const response = await api.post('/recommendations/ai-search/candidates/', {
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
  const response = await api.post('/recommendations/search-safety/', {
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
  const response = await api.post('/recommendations/conversational-search-plan/', {
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
  const response = await api.post('/recommendations/ai-web-search/', {
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
  minLat = null,
  minLng = null,
  maxLat = null,
  maxLng = null,
  facilityType = '',
  verification = '',
  includeStale = false,
  limit = 100,
} = {}) => {
  const response = await api.get('/recommendations/places/', {
    params: {
      q,
      category,
      source,
      status,
      lat,
      lng,
      radius,
      min_lat: minLat,
      min_lng: minLng,
      max_lat: maxLat,
      max_lng: maxLng,
      facility_type: facilityType,
      verification,
      include_stale: includeStale,
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
  radius = null,
  limit = 30,
} = {}) => {
  const params = {
    q,
    source,
    lat,
    lng,
    limit,
  }

  if (radius !== null && radius !== undefined && radius !== '') {
    params.radius = radius
  }

  try {
    const response = await api.get('/recommendations/place-search/', { params })
    return response.data
  } catch (error) {
    // 새 일반 검색 계약이 배포되기 전 서버와도 연결을 유지합니다.
    if (![404, 405].includes(error?.response?.status)) throw error
    const response = await api.get('/recommendations/map-search/', { params })
    return response.data
  }
}

export const getKakaoPlaceTags = async (externalIds = []) => {
  const response = await api.get('/recommendations/kakao-place-tags/', {
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

export const savePlaceInteractions = async (events = []) => {
  const normalizedEvents = Array.isArray(events) ? events : [events]
  const response = await api.post('/recommendations/interactions/', {
    events: normalizedEvents,
  })

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

export const fetchUserSavedPlaces = async ({
  q = '',
  source = '',
  page = 1,
  pageSize = 10,
  limit = null,
} = {}) => {
  const response = await api.get('/recommendations/saved-places/', {
    params: {
      ...(limit ? { limit } : { page, page_size: pageSize }),
      ...(q ? { q } : {}),
      ...(source ? { source } : {}),
    },
  })

  return response.data
}

export const saveUserSavedPlace = async (payload) => {
  const response = await api.post('/recommendations/saved-places/', payload)

  return response.data
}

export const updateUserSavedPlace = async (savedPlaceId, payload) => {
  const response = await api.patch(`/recommendations/saved-places/${savedPlaceId}/`, payload)

  return response.data
}

export const deleteUserSavedPlace = async (savedPlaceId) => {
  const response = await api.delete(`/recommendations/saved-places/${savedPlaceId}/`)

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

export const fetchAdminOperations = async ({ days = 1, region = '', category = '' } = {}) => {
  const response = await api.get('/recommendations/admin/operations/', {
    params: {
      days,
      ...(region ? { region } : {}),
      ...(category ? { category } : {}),
    },
  })
  return response.data
}
