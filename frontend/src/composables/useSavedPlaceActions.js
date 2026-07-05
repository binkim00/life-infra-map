import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchUserSavedPlaces,
  saveUserSavedPlace,
} from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'
import {
  buildSavedPlacePayload,
  getSavedPlaceClientKey,
} from '@/utils/placeSavePayload'

const toArray = (value) => Array.isArray(value) ? value : []

export const useSavedPlaceActions = () => {
  const router = useRouter()
  const authStore = useAuthStore()
  const savedPlaceKeys = ref(new Set())
  const savingPlaceId = ref('')
  const saveMessage = ref('')

  const isPlaceSaved = (place = {}) => {
    if (!place?.id) return false
    return Boolean(place.savedRecordId) || savedPlaceKeys.value.has(getSavedPlaceClientKey(place))
  }

  const loadSavedPlaceKeys = async () => {
    if (!authStore.isLoggedIn) {
      savedPlaceKeys.value = new Set()
      return
    }

    try {
      const response = await fetchUserSavedPlaces({ limit: 100 })
      savedPlaceKeys.value = new Set(
        toArray(response.results).map((place) => place.place_key).filter(Boolean),
      )
    } catch (error) {
      savedPlaceKeys.value = new Set()
    }
  }

  const savePlace = async (place) => {
    if (!place?.id) return

    if (!authStore.isLoggedIn) {
      router.push({ name: 'login' })
      return
    }

    try {
      savingPlaceId.value = place.id
      saveMessage.value = ''
      const response = await saveUserSavedPlace(buildSavedPlacePayload(place))
      const savedPlace = response.saved_place || {}
      place.savedRecordId = savedPlace.id
      savedPlaceKeys.value = new Set([
        ...savedPlaceKeys.value,
        savedPlace.place_key || getSavedPlaceClientKey(place),
      ])
      saveMessage.value = response.message === 'saved place updated'
        ? '이미 저장된 장소를 최신 정보로 갱신했습니다.'
        : '장소를 저장했습니다.'
    } catch (error) {
      saveMessage.value =
        error.response?.data?.detail || '장소를 저장하지 못했습니다.'
    } finally {
      savingPlaceId.value = ''
    }
  }

  return {
    savedPlaceKeys,
    savingPlaceId,
    saveMessage,
    isPlaceSaved,
    loadSavedPlaceKeys,
    savePlace,
  }
}
