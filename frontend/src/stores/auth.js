import { ref } from 'vue'
import { defineStore } from 'pinia'
import api, { setUnauthorizedHandler } from '@/api/axios'

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
    localStorage.removeItem('authUser')
  } catch (error) {
    // localStorage can be unavailable in restricted browser contexts.
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(readStoredToken())
  const user = ref(readStoredUser())

  const isLoggedIn = ref(!!token.value)

  const clearAuthState = () => {
    token.value = null
    user.value = null
    isLoggedIn.value = false

    removeStoredAuth()
  }

  setUnauthorizedHandler(() => {
    clearAuthState()
  })

  const signup = async (payload) => {
    const config = payload instanceof FormData ? {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    } : undefined

    const response = await api.post('/accounts/signup/', payload, config)

    token.value = response.data.token
    user.value = response.data.user
    isLoggedIn.value = true

    localStorage.setItem('authToken', response.data.token)
    localStorage.setItem('authUser', JSON.stringify(response.data.user))

    return response.data
  }

  const login = async (payload) => {
    const response = await api.post('/accounts/login/', payload)

    token.value = response.data.token
    user.value = response.data.user
    isLoggedIn.value = true

    localStorage.setItem('authToken', response.data.token)
    localStorage.setItem('authUser', JSON.stringify(response.data.user))

    return response.data
  }

  const logout = async () => {
    try {
      if (token.value) {
        await api.post('/accounts/logout/')
      }
    } catch (error) {
      console.error(error)
    }

    clearAuthState()
  }

  const fetchMe = async () => {
    if (!token.value) return

    const response = await api.get('/accounts/me/')

    user.value = response.data.user
    isLoggedIn.value = true

    localStorage.setItem('authUser', JSON.stringify(response.data.user))

    return response.data.user
  }

  return {
    token,
    user,
    isLoggedIn,
    signup,
    login,
    logout,
    fetchMe,
    clearAuthState,
  }
})
