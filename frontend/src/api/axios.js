import axios from 'axios'

import { isSpringPath, stripTrailingSlash } from './serviceRoutes'

// 검색은 Django, 나머지는 Spring 이 담당합니다.
const DJANGO_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
const SPRING_BASE_URL = import.meta.env.VITE_SPRING_API_BASE_URL || 'http://127.0.0.1:8081/api'

const api = axios.create({
  baseURL: DJANGO_BASE_URL,
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

  // Spring 으로 라우팅되면서 끝 슬래시가 떨어지므로 두 형태를 모두 봅니다.
  return method === 'post' && (
    url.includes('/accounts/login')
    || url.includes('/accounts/signup')
    || url.includes('/auth/login')
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
  // 담당 서비스로 보냅니다. Spring 은 경로 끝 슬래시를 받지 않습니다.
  if (isSpringPath(config.url)) {
    config.baseURL = SPRING_BASE_URL
    config.url = stripTrailingSlash(config.url)
  }

  const token = getStoredAuthToken()

  if (token) {
    config.headers = config.headers || {}
    // Spring 이 발급한 JWT 를 두 서비스가 모두 검증합니다.
    config.headers.Authorization = `Bearer ${token}`
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
