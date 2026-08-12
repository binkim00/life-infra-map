import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { resolveRouteName } from '@/router/routeNames'
import { useAuthStore } from '@/stores/auth'

const MASCOT_TIER_VALUES = new Set([
  'iron',
  'bronze',
  'silver',
  'gold',
  'platinum',
  'diamond',
  'master',
  'challenger',
])

const FETCH_RUN_DURATION_MS = 1100

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

const getRouteMascotState = (routeName, path) => {
  if (routeName === 'home') {
    return { key: 'home', prop: '⌕', message: '필요한 장소 냄새 맡는 중' }
  }

  if (routeName === 'map-search') {
    return { key: 'map', prop: '⌖', message: '지도 위를 총총 탐색 중' }
  }

  if (path.startsWith('/boards')) {
    if (routeName === 'board-create' || routeName === 'board-edit') {
      return { key: 'write', prop: '✎', message: '글감을 또각또각 적는 중' }
    }

    return { key: 'board', prop: '▤', message: '게시글을 조용히 읽는 중' }
  }

  if (routeName === 'mypage') {
    return { key: 'mypage', prop: '♡', message: '프로필을 반듯하게 정리 중' }
  }

  if (routeName === 'guide' || routeName === 'upgrade-guide') {
    return { key: 'guide', prop: '?', message: '길을 콕 집어 알려주는 중' }
  }

  if (path.startsWith('/inquiries')) {
    return { key: 'inquiry', prop: '♪', message: '문의 답변을 기다리는 중' }
  }

  if (routeName === 'settings') {
    return { key: 'settings', prop: '⚙', message: '취향에 맞게 맞추는 중' }
  }

  if (path.startsWith('/admin')) {
    return { key: 'admin', prop: '!', message: '관리 화면을 지키는 중' }
  }

  if (routeName === 'login' || routeName === 'signup') {
    return { key: 'auth', prop: '•', message: '반갑게 맞이하는 중' }
  }

  return { key: 'default', prop: '·', message: '천천히 따라가는 중' }
}

const DEFAULT_RUN_POSITION = {
  x: '-36vw',
  y: '-17vh',
  midX: '-18vw',
  midY: '-9vh',
  nearX: '-30vw',
  nearY: '-14vh',
}

/**
 * 마스코트는 지도 마커 쪽으로 뛰어가는 연출을 위해 window 커스텀 이벤트로 좌표를 받습니다.
 * 리스너와 타이머가 남으면 라우트를 옮긴 뒤에도 연출이 되살아나므로 정리를 붙였습니다.
 */
export const useRouteMascot = () => {
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn)

  const [fetchPhase, setFetchPhase] = useState('')
  const [fetchedPlaceId, setFetchedPlaceId] = useState(null)
  const [fetchedPlaceName, setFetchedPlaceName] = useState('')
  const [fetchedMarkerLabel, setFetchedMarkerLabel] = useState('')
  const [isMarkerChoiceMenuOpen, setIsMarkerChoiceMenuOpen] = useState(false)
  const [isSearchLoading, setIsSearchLoading] = useState(false)
  const [searchMessage, setSearchMessage] = useState('')
  const [runPosition, setRunPosition] = useState(DEFAULT_RUN_POSITION)

  const fetchTimerRef = useRef(null)
  const fetchPhaseRef = useRef('')
  fetchPhaseRef.current = fetchPhase
  const fetchedPlaceIdRef = useRef(null)
  fetchedPlaceIdRef.current = fetchedPlaceId
  const fetchedPlaceNameRef = useRef('')
  fetchedPlaceNameRef.current = fetchedPlaceName
  const fetchedMarkerLabelRef = useRef('')
  fetchedMarkerLabelRef.current = fetchedMarkerLabel

  const clearFetchTimer = useCallback(() => {
    if (fetchTimerRef.current) {
      window.clearTimeout(fetchTimerRef.current)
      fetchTimerRef.current = null
    }
  }, [])

  const clearMascotFetch = useCallback(() => {
    clearFetchTimer()
    setFetchPhase('')
    setFetchedPlaceId(null)
    setFetchedPlaceName('')
    setFetchedMarkerLabel('')
    setIsMarkerChoiceMenuOpen(false)
  }, [clearFetchTimer])

  const setMascotRunTarget = useCallback((target) => {
    const fallbackX = Math.round(window.innerWidth * -0.36)
    const fallbackY = Math.round(window.innerHeight * -0.17)

    if (!target || typeof target.clientX !== 'number' || typeof target.clientY !== 'number') {
      setRunPosition({
        x: `${fallbackX}px`,
        y: `${fallbackY}px`,
        midX: `${Math.round(fallbackX * 0.48)}px`,
        midY: `${Math.round(fallbackY * 0.48 - 18)}px`,
        nearX: `${Math.round(fallbackX * 0.82)}px`,
        nearY: `${Math.round(fallbackY * 0.82 + 8)}px`,
      })
      return
    }

    const mascotElement = document.querySelector('.route-mascot')
    const mascotStyle = mascotElement ? window.getComputedStyle(mascotElement) : null
    const baseRight = Number.parseFloat(mascotStyle?.right || '28') || 28
    const baseBottom = Number.parseFloat(mascotStyle?.bottom || '24') || 24
    const baseWidth = mascotElement?.offsetWidth || 150
    const baseHeight = mascotElement?.offsetHeight || 190
    const baseLeft = window.innerWidth - baseRight - baseWidth
    const baseTop = window.innerHeight - baseBottom - baseHeight
    const fromX = baseLeft + baseWidth * 0.68
    const fromY = baseTop + baseHeight * 0.7
    const targetX = clamp(target.clientX - fromX, -(window.innerWidth - 116), 28)
    const targetY = clamp(target.clientY - fromY, -(window.innerHeight - 128), 24)

    setRunPosition({
      x: `${Math.round(targetX)}px`,
      y: `${Math.round(targetY)}px`,
      midX: `${Math.round(targetX * 0.48)}px`,
      midY: `${Math.round(targetY * 0.48 - 18)}px`,
      nearX: `${Math.round(targetX * 0.82)}px`,
      nearY: `${Math.round(targetY * 0.82 + 8)}px`,
    })
  }, [])

  const handleMascotClick = useCallback(() => {
    if (fetchPhaseRef.current !== 'carrying' || !fetchedPlaceIdRef.current) return

    window.dispatchEvent(new CustomEvent('place-marker-fetch-click', {
      detail: {
        placeId: fetchedPlaceIdRef.current,
        placeName: fetchedPlaceNameRef.current,
        markerLabel: fetchedMarkerLabelRef.current,
      },
    }))
  }, [])

  useEffect(() => {
    const triggerMascotFetch = (event) => {
      clearFetchTimer()

      setFetchedPlaceId(event.detail?.placeId || null)
      setFetchedPlaceName(event.detail?.placeName || '')
      setFetchedMarkerLabel(event.detail?.markerLabel || '')
      setMascotRunTarget(event.detail?.target)
      setFetchPhase('fetching')

      fetchTimerRef.current = window.setTimeout(() => {
        setFetchPhase('carrying')
        fetchTimerRef.current = null
        window.dispatchEvent(new CustomEvent('place-marker-fetch-arrived', {
          detail: event.detail || {},
        }))
      }, FETCH_RUN_DURATION_MS)
    }

    const updateMascotFetchTarget = (event) => {
      if (!fetchPhaseRef.current) return

      if (event.detail?.placeId) setFetchedPlaceId(event.detail.placeId)
      if (event.detail?.placeName) setFetchedPlaceName(event.detail.placeName)
      if (event.detail?.markerLabel) setFetchedMarkerLabel(event.detail.markerLabel)
      setMascotRunTarget(event.detail?.target)
    }

    const handleMarkerChoiceMenuOpen = () => setIsMarkerChoiceMenuOpen(true)
    const handleMarkerChoiceMenuClose = () => setIsMarkerChoiceMenuOpen(false)

    const handleSearchLoadingChange = (event) => {
      setIsSearchLoading(Boolean(event.detail?.isSearching))
      setSearchMessage(event.detail?.message || '')
    }

    window.addEventListener('place-marker-fetch', triggerMascotFetch)
    window.addEventListener('place-marker-fetch-update', updateMascotFetchTarget)
    window.addEventListener('place-marker-fetch-clear', clearMascotFetch)
    window.addEventListener('place-marker-choice-open', handleMarkerChoiceMenuOpen)
    window.addEventListener('place-marker-choice-close', handleMarkerChoiceMenuClose)
    window.addEventListener('search-loading-change', handleSearchLoadingChange)

    return () => {
      window.removeEventListener('place-marker-fetch', triggerMascotFetch)
      window.removeEventListener('place-marker-fetch-update', updateMascotFetchTarget)
      window.removeEventListener('place-marker-fetch-clear', clearMascotFetch)
      window.removeEventListener('place-marker-choice-open', handleMarkerChoiceMenuOpen)
      window.removeEventListener('place-marker-choice-close', handleMarkerChoiceMenuClose)
      window.removeEventListener('search-loading-change', handleSearchLoadingChange)
      clearFetchTimer()
    }
  }, [clearFetchTimer, clearMascotFetch, setMascotRunTarget])

  // 화면을 옮기면 물고 있던 마커 연출을 접습니다.
  useEffect(() => {
    clearMascotFetch()
  }, [location.pathname, location.search, clearMascotFetch])

  const mascotTier = useMemo(() => {
    const tier = String(user?.tier || '').toLowerCase()

    return MASCOT_TIER_VALUES.has(tier) ? tier : 'iron'
  }, [user?.tier])

  const mascotImageStyle = useMemo(() => {
    if (!isLoggedIn) {
      return {
        '--mascot-idle-image': 'none',
        '--mascot-run-1': 'url("/mascot-run/dog-run-1.png")',
        '--mascot-run-2': 'url("/mascot-run/dog-run-2.png")',
        '--mascot-run-3': 'url("/mascot-run/dog-run-3.png")',
        '--mascot-run-4': 'url("/mascot-run/dog-run-4.png")',
        '--mascot-run-5': 'url("/mascot-run/dog-run-5.png")',
        '--mascot-run-6': 'url("/mascot-run/dog-run-6.png")',
      }
    }

    const basePath = `/mascot-tiers/${mascotTier}`

    return {
      '--mascot-idle-image': `url("${basePath}/idle.png")`,
      '--mascot-run-1': `url("${basePath}/run-1.png")`,
      '--mascot-run-2': `url("${basePath}/run-2.png")`,
      '--mascot-run-3': `url("${basePath}/run-3.png")`,
      '--mascot-run-4': `url("${basePath}/run-4.png")`,
      '--mascot-run-5': `url("${basePath}/run-5.png")`,
      '--mascot-run-6': `url("${basePath}/run-6.png")`,
    }
  }, [isLoggedIn, mascotTier])

  const activeMascotState = useMemo(() => {
    if (fetchPhase === 'fetching') {
      return { key: 'fetching', prop: '', message: '뼈다귀 마커로 달려가는 중' }
    }

    if (fetchPhase === 'carrying') {
      return {
        key: 'carrying',
        prop: '',
        message: fetchedPlaceName
          ? `${fetchedPlaceName} 마커 물고 있는 중`
          : '뼈다귀 마커 물고 있는 중',
      }
    }

    if (isSearchLoading) {
      return {
        key: 'searching',
        prop: '',
        message: searchMessage || '조건에 맞는 장소 찾는 중',
      }
    }

    return getRouteMascotState(resolveRouteName(location.pathname), location.pathname)
  }, [fetchPhase, fetchedPlaceName, isSearchLoading, searchMessage, location.pathname])

  return {
    activeMascotState,
    mascotImageStyle,
    runPosition,
    fetchPhase,
    fetchedMarkerLabel,
    isMarkerChoiceMenuOpen,
    isSearchLoading,
    handleMascotClick,
  }
}
