import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { savePlaceInteractions } from '@/api/recommendation'
import {
  buildSavedPlacePayload,
  getSavedPlaceClientKey,
} from '@/utils/placeSavePayload'


const SESSION_STORAGE_KEY = 'lifeInfraMapInteractionSession'

const randomId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

const getSessionId = () => {
  try {
    const existing = localStorage.getItem(SESSION_STORAGE_KEY)
    if (existing) return existing
    const created = randomId()
    localStorage.setItem(SESSION_STORAGE_KEY, created)
    return created
  } catch (error) {
    return randomId()
  }
}

const shortHash = (value = '') => {
  let hash = 2166136261
  for (const character of String(value)) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

const eventKey = (searchId, eventType, seed = '') => (
  `${String(searchId).slice(0, 36)}:${eventType.slice(0, 4)}:${shortHash(seed)}`
)

const normalizeTag = (value) => {
  if (value && typeof value === 'object') {
    return String(value.label || value.name || value.tag || '').trim().replace(/^#/, '')
  }
  return String(value || '').trim().replace(/^#/, '')
}

export const normalizeRequestedTags = (values = []) => (
  [...new Set((Array.isArray(values) ? values : [values])
    .map(normalizeTag)
    .filter(Boolean))]
    .slice(0, 20)
)

const categoryText = (place = {}) => (
  String(place.categoryLabel || place.category || '').toLowerCase()
)

export const getFeedbackTagOptions = (place = {}, requestedTags = []) => {
  const category = categoryText(place)
  const defaults = category.includes('카페') || category.includes('cafe')
    ? [
      { tag: '조용한', label: '조용해요' },
      { tag: '분위기 좋은', label: '분위기 좋아요' },
      { tag: '작업하기 좋은', label: '작업하기 좋아요' },
    ]
    : category.includes('식당') || category.includes('restaurant') || category.includes('음식')
      ? [
        { tag: '조용한', label: '조용해요' },
        { tag: '분위기 좋은', label: '분위기 좋아요' },
        { tag: '혼밥하기 좋은', label: '혼밥하기 좋아요' },
      ]
      : [
        { tag: '조용한', label: '조용해요' },
        { tag: '접근하기 좋은', label: '접근하기 좋아요' },
      ]
  const requested = normalizeRequestedTags(requestedTags).map((tag) => ({
    tag,
    label: tag,
  }))
  const combined = [...requested, ...defaults]
  const seen = new Set()
  return combined.filter((option) => {
    if (!option.tag || seen.has(option.tag)) return false
    seen.add(option.tag)
    return true
  }).slice(0, 5)
}

const placePayload = (place = {}) => {
  const savedPayload = buildSavedPlacePayload(place)
  return {
    ...(savedPayload.place_id ? { place_id: savedPayload.place_id } : {}),
    place_key: getSavedPlaceClientKey(place),
    place_source: savedPayload.source,
    place_external_id: savedPayload.external_id,
    place_name: savedPayload.name,
    place_category: savedPayload.category,
  }
}

export const usePlaceInteractionTracking = ({
  query = '',
  requestedTags = [],
  places = [],
} = {}) => {
  const sessionIdRef = useRef(getSessionId())
  const activeSearchRef = useRef({ query: '', searchId: '', seenPlaces: new Set() })
  const [feedbackState, setFeedbackState] = useState({})
  const normalizedQuery = String(query || '').trim()
  const normalizedTags = useMemo(
    () => normalizeRequestedTags(requestedTags),
    [JSON.stringify(requestedTags)],
  )
  const visiblePlaces = Array.isArray(places) ? places.slice(0, 20) : []
  const placeSignature = visiblePlaces.map(getSavedPlaceClientKey).join('|')
  const tagSignature = normalizedTags.join('|')

  const sendEvents = useCallback(async (events) => {
    if (!events.length) return null
    try {
      return await savePlaceInteractions(events)
    } catch (error) {
      console.warn('[PlaceInteraction] save failed', error?.response?.status || error)
      return null
    }
  }, [])

  useEffect(() => {
    if (!normalizedQuery) return
    let active = activeSearchRef.current
    const events = []
    if (active.query !== normalizedQuery || !active.searchId) {
      active = {
        query: normalizedQuery,
        searchId: randomId(),
        seenPlaces: new Set(),
      }
      activeSearchRef.current = active
      events.push({
        event_type: 'search',
        event_key: eventKey(active.searchId, 'search', normalizedQuery),
        session_key: sessionIdRef.current,
        search_id: active.searchId,
        query: normalizedQuery,
        requested_tags: normalizedTags,
      })
    }

    visiblePlaces.forEach((place, index) => {
      const key = getSavedPlaceClientKey(place)
      if (active.seenPlaces.has(key)) return
      active.seenPlaces.add(key)
      events.push({
        event_type: 'impression',
        event_key: eventKey(active.searchId, 'impression', key),
        session_key: sessionIdRef.current,
        search_id: active.searchId,
        query: normalizedQuery,
        requested_tags: normalizedTags,
        position: index + 1,
        ...placePayload(place),
      })
    })
    void sendEvents(events)
  }, [normalizedQuery, placeSignature, tagSignature, sendEvents])

  const trackPlaceEvent = useCallback(async (eventType, place, extra = {}) => {
    if (!place) return null
    const active = activeSearchRef.current
    const key = getSavedPlaceClientKey(place)
    return sendEvents([{
      event_type: eventType,
      event_key: eventKey(
        active.searchId || sessionIdRef.current,
        eventType,
        `${key}:${extra.tag_name || randomId()}`,
      ),
      session_key: sessionIdRef.current,
      search_id: active.searchId,
      query: active.query,
      requested_tags: normalizedTags,
      ...placePayload(place),
      ...extra,
    }])
  }, [normalizedTags, sendEvents])

  const trackSearchEvent = useCallback(async (eventType, extra = {}) => {
    const active = activeSearchRef.current
    return sendEvents([{
      event_type: eventType,
      event_key: eventKey(
        active.searchId || sessionIdRef.current,
        eventType,
        `${extra.query || ''}:${randomId()}`,
      ),
      session_key: sessionIdRef.current,
      search_id: active.searchId,
      query: extra.query || active.query,
      requested_tags: normalizedTags,
      ...extra,
    }])
  }, [normalizedTags, sendEvents])

  const submitTagFeedback = useCallback(async (place, tagName, confirmed) => {
    const key = `${getSavedPlaceClientKey(place)}:${tagName}`
    setFeedbackState((current) => ({ ...current, [key]: 'sending' }))
    const result = await trackPlaceEvent(
      confirmed ? 'tag_confirm' : 'tag_reject',
      place,
      { tag_name: tagName },
    )
    setFeedbackState((current) => ({
      ...current,
      [key]: result ? (confirmed ? 'confirmed' : 'rejected') : 'failed',
    }))
    return result
  }, [trackPlaceEvent])

  const getTagFeedbackState = useCallback((place, tagName) => (
    feedbackState[`${getSavedPlaceClientKey(place)}:${tagName}`] || ''
  ), [feedbackState])

  return {
    requestedTags: normalizedTags,
    trackSearchEvent,
    trackPlaceEvent,
    submitTagFeedback,
    getTagFeedbackState,
  }
}
