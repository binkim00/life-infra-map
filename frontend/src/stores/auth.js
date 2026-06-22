import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '@/api/axios'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('authToken'))
  const user = ref(JSON.parse(localStorage.getItem('authUser') || 'null'))

  const isLoggedIn = ref(!!token.value)

  const signup = async (payload) => {
    const response = await api.post('/accounts/signup/', payload)

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

    token.value = null
    user.value = null
    isLoggedIn.value = false

    localStorage.removeItem('authToken')
    localStorage.removeItem('authUser')
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
  }
})