import { create } from 'zustand'

import api, { setUnauthorizedHandler, setSessionRenewedHandler } from '@/api/axios'

const readStoredToken = () => {
  try {
    return localStorage.getItem('authToken')
  } catch (error) {
    return null
  }
}

const readStoredUser = () => {
  try {
    return JSON.parse(localStorage.getItem('authUser') || 'null')
  } catch (error) {
    return null
  }
}

const removeStoredAuth = () => {
  try {
    localStorage.removeItem('authToken')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('authUser')
  } catch (error) {
    // localStorage can be unavailable in restricted browser contexts.
  }
}

const persistAuth = (token, user, refreshToken) => {
  try {
    localStorage.setItem('authToken', token)
    if (refreshToken) localStorage.setItem('refreshToken', refreshToken)
    localStorage.setItem('authUser', JSON.stringify(user))
  } catch (error) {
    // localStorage can be unavailable in restricted browser contexts.
  }
}

export const useAuthStore = create((set, get) => ({
  token: readStoredToken(),
  user: readStoredUser(),
  isLoggedIn: Boolean(readStoredToken()),

  clearAuthState: () => {
    removeStoredAuth()
    set({ token: null, user: null, isLoggedIn: false })
  },

  // 마이페이지에서 닉네임/프로필 사진을 고치면 헤더 표시도 함께 바뀌어야 합니다.
  setUser: (user) => {
    try {
      localStorage.setItem('authUser', JSON.stringify(user))
    } catch (error) {
      // localStorage can be unavailable in restricted browser contexts.
    }

    set({ user })
  },

  signup: async (payload) => {
    const config = payload instanceof FormData ? {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    } : undefined

    const response = await api.post('/accounts/signup/', payload, config)

    // Spring 은 access_token, 이관 전 Django 는 token 으로 내려줍니다.
    const token = response.data.access_token || response.data.token
    const user = response.data.user

    persistAuth(token, user, response.data.refresh_token)
    set({ token, user, isLoggedIn: true })

    return response.data
  },

  login: async (payload) => {
    const response = await api.post('/auth/login', payload)

    const token = response.data.access_token || response.data.token
    const user = response.data.user

    persistAuth(token, user, response.data.refresh_token)
    set({ token, user, isLoggedIn: true })

    return response.data
  },

  exchangeSocialTicket: async (ticket) => {
    const response = await api.post('/auth/social/exchange', { ticket })
    const { access_token: token, refresh_token: refreshToken, user } = response.data
    persistAuth(token, user, refreshToken)
    set({ token, user, isLoggedIn: true })
    return response.data
  },

  logout: async () => {
    try {
      const refreshToken = localStorage.getItem('refreshToken')
      if (refreshToken) await api.post('/auth/logout', { refresh_token: refreshToken })
    } catch (error) {
      console.error(error)
    }

    get().clearAuthState()
  },

  fetchMe: async () => {
    if (!get().token) return undefined

    const response = await api.get('/accounts/me/')
    const user = response.data.user

    try {
      localStorage.setItem('authUser', JSON.stringify(user))
    } catch (error) {
      // localStorage can be unavailable in restricted browser contexts.
    }

    set({ user, isLoggedIn: true })

    return user
  },
}))

// 401 응답을 받으면 저장된 인증 상태를 지웁니다.
setUnauthorizedHandler(() => {
  useAuthStore.getState().clearAuthState()
})
setSessionRenewedHandler((data) => {
  useAuthStore.setState({ token: data.access_token, user: data.user, isLoggedIn: true })
})
