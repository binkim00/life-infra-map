import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api',
})

let unauthorizedHandler = null
let isHandlingUnauthorized = false

export const setUnauthorizedHandler = (handler) => {
  unauthorizedHandler = typeof handler === 'function' ? handler : null
}

const getStoredAuthToken = () => {
  try {
    return localStorage.getItem('authToken')
  } catch (error) {
    return ''
  }
}

const clearStoredAuth = () => {
  try {
    localStorage.removeItem('authToken')
    localStorage.removeItem('authUser')
  } catch (error) {
    // localStorage can be unavailable in restricted browser contexts.
  }
}

const getAuthorizationHeader = (headers = {}) => {
  if (typeof headers.get === 'function') {
    return headers.get('Authorization') || headers.get('authorization') || ''
  }

  return headers.Authorization || headers.authorization || ''
}

const isAuthEntryRequest = (config = {}) => {
  const method = String(config.method || '').toLowerCase()
  const url = String(config.url || '')

  return method === 'post' && (
    url.includes('/accounts/login/')
    || url.includes('/accounts/signup/')
  )
}

const handleUnauthorizedResponse = (error) => {
  if (isHandlingUnauthorized) return

  isHandlingUnauthorized = true
  clearStoredAuth()

  try {
    unauthorizedHandler?.(error)
  } finally {
    const releaseHandlingLock = () => {
      isHandlingUnauthorized = false
    }

    if (typeof window !== 'undefined' && typeof window.setTimeout === 'function') {
      window.setTimeout(releaseHandlingLock, 0)
    } else {
      Promise.resolve().then(releaseHandlingLock)
    }
  }
}

api.interceptors.request.use((config) => {
  const token = getStoredAuthToken()

  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Token ${token}`
  }

  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const config = error?.config || {}
    const hadAuthCredential = Boolean(
      getAuthorizationHeader(config.headers) || getStoredAuthToken(),
    )

    if (status === 401 && hadAuthCredential && !isAuthEntryRequest(config)) {
      handleUnauthorizedResponse(error)
    }

    return Promise.reject(error)
  },
)

export default api
