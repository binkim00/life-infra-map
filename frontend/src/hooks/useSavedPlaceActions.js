import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  fetchUserSavedPlaces,
  saveUserSavedPlace,
} from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'
import {
  buildSavedPlacePayload,
  getSavedPlaceClientKey,
} from '@/utils/placeSavePayload'

const toArray = (value) => (Array.isArray(value) ? value : [])

export const useSavedPlaceActions = () => {
  const navigate = useNavigate()
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn)
  const [savedPlaceKeys, setSavedPlaceKeys] = useState(() => new Set())
  const [savingPlaceId, setSavingPlaceId] = useState('')
  const [saveMessage, setSaveMessage] = useState('')

  // isPlaceSaved 는 렌더 중에도 불리므로 최신 Set 을 ref 로도 들고 있습니다.
  const savedPlaceKeysRef = useRef(savedPlaceKeys)
  const isLoggedInRef = useRef(isLoggedIn)
  isLoggedInRef.current = isLoggedIn

  const applySavedPlaceKeys = useCallback((nextKeys) => {
    savedPlaceKeysRef.current = nextKeys
    setSavedPlaceKeys(nextKeys)
  }, [])

  const isPlaceSaved = useCallback((place = {}) => {
    if (!place?.id) return false
    return Boolean(place.savedRecordId)
      || savedPlaceKeysRef.current.has(getSavedPlaceClientKey(place))
  }, [])

  const loadSavedPlaceKeys = useCallback(async () => {
    if (!isLoggedInRef.current) {
      applySavedPlaceKeys(new Set())
      return
    }

    try {
      const response = await fetchUserSavedPlaces({ limit: 100 })
      applySavedPlaceKeys(new Set(
        toArray(response.results).map((place) => place.place_key).filter(Boolean),
      ))
    } catch (error) {
      applySavedPlaceKeys(new Set())
    }
  }, [applySavedPlaceKeys])

  const savePlace = useCallback(async (place) => {
    if (!place?.id) return

    if (!isLoggedInRef.current) {
      navigate('/login')
      return { status: 'login_required' }
    }

    try {
      setSavingPlaceId(place.id)
      setSaveMessage('')
      const response = await saveUserSavedPlace(buildSavedPlacePayload(place))
      const savedPlace = response.saved_place || {}
      // 호출부가 place 객체를 그대로 들고 있으므로 저장 결과를 붙여 줍니다.
      place.savedRecordId = savedPlace.id
      applySavedPlaceKeys(new Set([
        ...savedPlaceKeysRef.current,
        savedPlace.place_key || getSavedPlaceClientKey(place),
      ]))
      setSaveMessage(response.message === 'saved place updated'
        ? '이미 저장된 장소를 최신 정보로 갱신했습니다.'
        : '장소를 저장했습니다.')
      return { status: 'saved', savedPlace }
    } catch (error) {
      setSaveMessage(error.response?.data?.detail || '장소를 저장하지 못했습니다.')
      return { status: 'failed', error }
    } finally {
      setSavingPlaceId('')
    }
  }, [applySavedPlaceKeys, navigate])

  return {
    savedPlaceKeys,
    savingPlaceId,
    saveMessage,
    setSaveMessage,
    isPlaceSaved,
    loadSavedPlaceKeys,
    savePlace,
  }
}
