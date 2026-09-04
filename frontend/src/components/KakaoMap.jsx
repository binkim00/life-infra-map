import { useEffect, useMemo, useRef } from 'react'

import { loadKakaoMapScript } from '@/hooks/useKakaoMapSdk'

import styles from './KakaoMap.module.css'
import './kakaoMarkerChoice.css'

const MARKER_OVERLAP_PIXEL_THRESHOLD = 30
// 위치를 아직 받지 못한 지도는 특정 도시가 아닌 대한민국 중심을 보여줍니다.
const DEFAULT_CENTER = { lat: 36.35, lng: 127.8 }

const nextFrame = () => new Promise((resolve) => {
  if (typeof window === 'undefined' || !window.requestAnimationFrame) {
    resolve()
    return
  }

  window.requestAnimationFrame(() => resolve())
})

/**
 * 카카오 지도는 React 밖에서 DOM 을 직접 다룹니다.
 * 렌더마다 함수가 새로 만들어지면 리스너가 옛 값을 붙들게 되므로,
 * 지도 로직 전체를 컴포넌트 밖 클로저에 두고 최신 props 는 ref 로 읽습니다.
 * 지도 SDK 상태를 컴포넌트 인스턴스 안에서 관리합니다.
 */
const createMapEngine = ({ containerRef, propsRef, callbacksRef }) => {
  let map = null
  let markers = []
  let markerRecords = new Map()
  let markerGroups = []
  let activeInfoWindow = null
  let lastFitBoundsKey = null
  let markerTargetFrame = null
  let shouldSkipNextMapClickClose = false
  let isDestroyed = false
  const pendingTimeouts = new Set()

  // 정리(cleanup) 때 남은 타이머를 모두 취소하기 위해 직접 추적합니다.
  const setManagedTimeout = (callback, delay) => {
    const timeoutId = window.setTimeout(() => {
      pendingTimeouts.delete(timeoutId)
      if (isDestroyed) return
      callback()
    }, delay)

    pendingTimeouts.add(timeoutId)

    return timeoutId
  }

  const emit = (name, ...payload) => {
    if (isDestroyed) return
    callbacksRef.current?.[name]?.(...payload)
  }

  const getLatLngPayload = (latLng) => ({
    lat: latLng.getLat(),
    lng: latLng.getLng(),
  })

  const emitMapViewport = () => {
    if (!map) return

    const center = map.getCenter()
    const bounds = map.getBounds()
    const southWest = bounds.getSouthWest()
    const northEast = bounds.getNorthEast()

    emit('onCenterChange', {
      center: getLatLngPayload(center),
      bounds: {
        southWest: getLatLngPayload(southWest),
        northEast: getLatLngPayload(northEast),
      },
    })
  }

  const closeActiveInfoWindow = () => {
    if (activeInfoWindow) {
      activeInfoWindow.close()
      activeInfoWindow = null
      window.dispatchEvent(new CustomEvent('place-marker-choice-close'))
    }
  }

  const notifyChoiceMenuOpen = () => {
    window.dispatchEvent(new CustomEvent('place-marker-choice-open'))
  }

  const handleOutsideInfoWindowClick = (event) => {
    if (!activeInfoWindow) return
    if (event.target?.closest?.('.map-marker-choice')) return
    if (containerRef.current?.contains(event.target)) return

    closeActiveInfoWindow()
  }

  const clearMarkers = () => {
    closeActiveInfoWindow()

    markers.forEach((marker) => marker.setMap(null))
    markers = []
    markerRecords = new Map()
    markerGroups = []
  }

  const createNumberMarkerImage = (label, markerColor = '', overlapCount = 0) => {
    const safeLabel = String(label || '')
    const accentColor = markerColor || '#222222'
    const fontSize = safeLabel.length >= 2 ? 13 : 16
    const safeOverlapCount = Number(overlapCount)
    const shouldShowOverlapBadge = Number.isFinite(safeOverlapCount) && safeOverlapCount > 1
    const overlapText = `+${safeOverlapCount}`
    const overlapFontSize = overlapText.length >= 3 ? 10 : 12
    const imageWidth = shouldShowOverlapBadge ? 70 : 54
    const imageHeight = shouldShowOverlapBadge ? 70 : 54
    const badgeSvg = shouldShowOverlapBadge
      ? `
      <g filter="url(#badgeShadow)">
        <circle cx="49" cy="46" r="14" fill="${accentColor}" fill-opacity="0.94"/>
        <text
          x="49"
          y="46"
          text-anchor="middle"
          dominant-baseline="middle"
          font-size="${overlapFontSize}"
          font-weight="900"
          font-family="Arial, sans-serif"
          fill="#ffffff"
        >${overlapText}</text>
      </g>
    `
      : ''

    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${imageWidth}" height="${imageHeight}" viewBox="0 0 ${imageWidth} ${imageHeight}">
      <filter id="boneShadow" x="-10%" y="-20%" width="120%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="1.3" flood-color="#1f2937" flood-opacity="0.25"/>
      </filter>
      <filter id="badgeShadow" x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="2" stdDeviation="1" flood-color="#1f2937" flood-opacity="0.2"/>
      </filter>
      <g transform="rotate(-45 27 27)" filter="url(#boneShadow)">
        <path
          d="M14.6 6.2
             C16.4 2.9 20.8 1.8 24 4
             C25.7 5.1 26.7 6.8 27 8.6
             C27.3 6.8 28.3 5.1 30 4
             C33.2 1.8 37.6 2.9 39.4 6.2
             C41.4 9.8 39.8 14.2 36.3 15.8
             L36.3 38.2
             C39.8 39.8 41.4 44.2 39.4 47.8
             C37.6 51.1 33.2 52.2 30 50
             C28.3 48.9 27.3 47.2 27 45.4
             C26.7 47.2 25.7 48.9 24 50
             C20.8 52.2 16.4 51.1 14.6 47.8
             C12.6 44.2 14.2 39.8 17.7 38.2
             L17.7 15.8
             C14.2 14.2 12.6 9.8 14.6 6.2 Z"
          fill="#ffffff"
          stroke="${accentColor}"
          stroke-width="4"
          stroke-linejoin="round"
        />
      </g>
      <text
        x="27"
        y="27"
        text-anchor="middle"
        dominant-baseline="middle"
        font-size="${fontSize}"
        font-weight="900"
        font-family="Arial, sans-serif"
        fill="#222222"
        paint-order="stroke"
        stroke="#ffffff"
        stroke-width="3"
        stroke-linejoin="round"
      >${safeLabel}</text>
      <text
        x="27"
        y="27"
        text-anchor="middle"
        dominant-baseline="middle"
        font-size="${fontSize}"
        font-weight="900"
        font-family="Arial, sans-serif"
        fill="#222222"
      >${safeLabel}</text>
      ${badgeSvg}
    </svg>
  `

    const imageSrc = `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
    const imageSize = new window.kakao.maps.Size(imageWidth, imageHeight)
    const imageOption = {
      offset: new window.kakao.maps.Point(27, 44),
    }

    return new window.kakao.maps.MarkerImage(imageSrc, imageSize, imageOption)
  }

  const createInfoWindow = (place) => {
    const distanceText = place.distance ? `${place.distance}m` : ''
    const categoryText = place.category || ''
    const divider = distanceText && categoryText ? ' · ' : ''

    return new window.kakao.maps.InfoWindow({
      content: `
      <div style="padding:9px 10px;font-size:13px;min-width:150px;line-height:1.45;">
        <strong>${place.name}</strong><br />
        <span style="color:#667085;">${categoryText}${divider}${distanceText}</span>
      </div>
    `,
    })
  }

  const getMarkerLabelNumber = (place) => {
    const labelNumber = Number(place?.markerLabel)
    return Number.isFinite(labelNumber) ? labelNumber : Number.MAX_SAFE_INTEGER
  }

  const sortPlacesByMarkerLabel = (places = []) => {
    return [...places].sort((first, second) => {
      const firstLabel = getMarkerLabelNumber(first)
      const secondLabel = getMarkerLabelNumber(second)

      if (firstLabel !== secondLabel) {
        return firstLabel - secondLabel
      }

      return String(first?.id || '').localeCompare(String(second?.id || ''))
    })
  }

  const getGroupedPlaceMarkerPlace = (group) => {
    const { selectedPlace, selectedPlaceId } = propsRef.current
    const selectedId = selectedPlace?.id || selectedPlaceId
    const matchedPlace = selectedId
      ? group.places.find((place) => String(place.id) === String(selectedId))
      : null

    return matchedPlace || group.places[0]
  }

  const createPlaceSelectionInfoWindow = (group) => {
    if (group.places.length === 1) {
      return createInfoWindow(group.places[0])
    }

    const wrapper = document.createElement('div')
    wrapper.className = 'map-marker-choice'
    wrapper.innerHTML = `
    <div class="map-marker-choice-header">
      <div class="map-marker-choice-title">겹친 장소 선택</div>
      <button type="button" class="map-marker-choice-close" aria-label="겹친 장소 선택 닫기">×</button>
    </div>
    <div class="map-marker-choice-list"></div>
  `

    wrapper.querySelector('.map-marker-choice-close')?.addEventListener('click', (event) => {
      event.stopPropagation()
      closeActiveInfoWindow()
    })

    const list = wrapper.querySelector('.map-marker-choice-list')

    group.places.forEach((place) => {
      const button = document.createElement('button')
      button.type = 'button'
      button.className = 'map-marker-choice-button'
      button.innerHTML = `
      <span class="map-marker-choice-label">${place.markerLabel || ''}</span>
      <span class="map-marker-choice-copy">
        <strong></strong>
        <small></small>
      </span>
    `

      button.querySelector('strong').textContent = place.name || '장소'
      button.querySelector('small').textContent = [
        place.category || '',
        place.distance ? `${place.distance}m` : '',
      ].filter(Boolean).join(' · ')

      button.addEventListener('click', () => {
        closeActiveInfoWindow()
        emit('onSelectPlace', place, getMarkerScreenTarget(group.position))
      })

      list.appendChild(button)
    })

    return new window.kakao.maps.InfoWindow({
      content: wrapper,
    })
  }

  const getPlaceCoordinateKey = (place) => {
    const lat = Number(place?.lat)
    const lng = Number(place?.lng)

    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return ''
    }

    return `${lat.toFixed(6)}:${lng.toFixed(6)}`
  }

  const getPlaceScreenPoint = (place) => {
    if (!map || !window.kakao?.maps) return null

    const lat = Number(place?.lat)
    const lng = Number(place?.lng)

    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return null
    }

    const projection = map.getProjection()
    const position = new window.kakao.maps.LatLng(lat, lng)
    const point = typeof projection.containerPointFromCoords === 'function'
      ? projection.containerPointFromCoords(position)
      : projection.pointFromCoords(position)

    if (!point || typeof point.x !== 'number' || typeof point.y !== 'number') {
      return null
    }

    return point
  }

  const areMarkerPointsOverlapping = (firstPoint, secondPoint) => {
    if (!firstPoint || !secondPoint) return false

    return (
      Math.abs(firstPoint.x - secondPoint.x) <= MARKER_OVERLAP_PIXEL_THRESHOLD
      && Math.abs(firstPoint.y - secondPoint.y) <= MARKER_OVERLAP_PIXEL_THRESHOLD
    )
  }

  const groupPlacesByPosition = (places = []) => {
    const groups = []

    sortPlacesByMarkerLabel(places).forEach((place) => {
      const key = getPlaceCoordinateKey(place)
      const point = getPlaceScreenPoint(place)

      if (!key) return

      const group = groups.find((candidate) => {
        return candidate.key === key || areMarkerPointsOverlapping(candidate.point, point)
      })

      if (group) {
        group.places.push(place)
        group.places = sortPlacesByMarkerLabel(group.places)
        return
      }

      groups.push({
        key,
        point,
        places: [place],
      })
    })

    return groups.map((group) => group.places)
  }

  const getVisibleMarkerGroups = () => {
    const { places, hiddenPlaceId } = propsRef.current
    const groups = groupPlacesByPosition(places)

    if (!hiddenPlaceId) {
      return groups
    }

    return groups.filter((groupPlaces) => {
      return !groupPlaces.some((place) => String(place.id) === String(hiddenPlaceId))
    })
  }

  const getPlaceMarkerGroup = (placeId) => {
    if (!placeId) return null

    return groupPlacesByPosition(propsRef.current.places).find((groupPlaces) => {
      return groupPlaces.some((place) => String(place.id) === String(placeId))
    }) || null
  }

  const getPlaceLatLng = (place) => {
    if (!place?.lat || !place?.lng || !window.kakao?.maps) return null

    return new window.kakao.maps.LatLng(
      Number(place.lat),
      Number(place.lng),
    )
  }

  const getGroupRepresentativeLatLngByPlaceId = (placeId) => {
    const group = getPlaceMarkerGroup(placeId)
    const representativePlace = group?.[0]

    return getPlaceLatLng(representativePlace)
  }

  const updateGroupMarkerImages = () => {
    if (!window.kakao?.maps) return

    markerGroups.forEach((group) => {
      const markerPlace = getGroupedPlaceMarkerPlace(group)

      if (markerPlace?.markerLabel) {
        group.marker.setImage(createNumberMarkerImage(
          markerPlace.markerLabel,
          markerPlace.markerColor,
          group.places.length,
        ))
      }
    })
  }

  const getMarkerScreenTarget = (position) => {
    if (!map || !containerRef.current || !position) return null

    const projection = map.getProjection()
    const rect = containerRef.current.getBoundingClientRect()
    const point = typeof projection.containerPointFromCoords === 'function'
      ? projection.containerPointFromCoords(position)
      : projection.pointFromCoords(position)

    if (!point || typeof point.x !== 'number' || typeof point.y !== 'number') {
      return null
    }

    if (
      point.x < -120
      || point.y < -120
      || point.x > rect.width + 120
      || point.y > rect.height + 120
    ) {
      return null
    }

    return {
      clientX: rect.left + point.x,
      clientY: rect.top + point.y - 22,
    }
  }

  const openSelectedPlaceChoiceMenu = () => {
    if (!map) return

    const { selectedPlace, selectedPlaceId } = propsRef.current
    const selectedId = selectedPlace?.id || selectedPlaceId

    if (!selectedId) return

    const record = markerRecords.get(String(selectedId))

    if (record?.group?.places?.length > 1) {
      closeActiveInfoWindow()
      updateGroupMarkerImages()
      record.group.infoWindow.open(map, record.marker)
      activeInfoWindow = record.group.infoWindow
      notifyChoiceMenuOpen()
      return
    }

    const groupPlaces = getPlaceMarkerGroup(selectedId)

    if (!groupPlaces || groupPlaces.length <= 1) return

    const position = getGroupRepresentativeLatLngByPlaceId(selectedId)

    if (!position) return

    closeActiveInfoWindow()

    const group = {
      marker: null,
      infoWindow: null,
      places: groupPlaces,
      position,
    }

    group.infoWindow = createPlaceSelectionInfoWindow(group)
    group.infoWindow.setPosition(position)
    group.infoWindow.open(map)
    activeInfoWindow = group.infoWindow
    notifyChoiceMenuOpen()
  }

  const getPlaceById = (placeId) => {
    if (!placeId) return null

    const { places, selectedPlace } = propsRef.current

    if (selectedPlace && String(selectedPlace.id) === String(placeId)) {
      return selectedPlace
    }

    return places.find((place) => String(place.id) === String(placeId)) || null
  }

  const emitSelectedMarkerTarget = () => {
    const { selectedPlace, selectedPlaceId } = propsRef.current
    const selectedId = selectedPlace?.id || selectedPlaceId

    if (!selectedId) return

    const record = markerRecords.get(String(selectedId))
    const place = record?.place || getPlaceById(selectedId)
    const position = record?.position
      || getGroupRepresentativeLatLngByPlaceId(selectedId)
      || getPlaceLatLng(place)

    if (!place || !position) return

    emit('onMarkerTargetChange', place, getMarkerScreenTarget(position))
  }

  const scheduleSelectedMarkerTarget = () => {
    if (markerTargetFrame) {
      window.cancelAnimationFrame(markerTargetFrame)
    }

    markerTargetFrame = window.requestAnimationFrame(() => {
      markerTargetFrame = null
      if (isDestroyed) return
      emitSelectedMarkerTarget()
    })
  }

  const openMarkerByPlaceId = (placeId, shouldMoveMap = true) => {
    if (!map || !placeId) return

    const record = markerRecords.get(String(placeId))

    if (!record) {
      const hiddenPlacePosition = getGroupRepresentativeLatLngByPlaceId(placeId)
        || getPlaceLatLng(getPlaceById(placeId))

      if (shouldMoveMap && hiddenPlacePosition) {
        map.panTo(hiddenPlacePosition)
      }

      return
    }

    closeActiveInfoWindow()

    updateGroupMarkerImages()

    if (record.group.places.length > 1) {
      record.group.infoWindow.open(map, record.marker)
      activeInfoWindow = record.group.infoWindow
    }

    if (shouldMoveMap) {
      map.panTo(record.position)
    }
  }

  const focusSelectedPlaceOnMap = async (place) => {
    if (!map || !place?.lat || !place?.lng || !window.kakao?.maps) return

    await nextFrame()

    if (isDestroyed || !map) return

    const position = getGroupRepresentativeLatLngByPlaceId(place.id) || getPlaceLatLng(place)

    if (!position) return

    map.relayout()
    map.panTo(position)

    setManagedTimeout(() => {
      if (!map) return

      map.relayout()
      map.panTo(position)
    }, 150)
  }

  const relayoutMap = async () => {
    if (!map) return

    const center = map.getCenter()

    await nextFrame()

    if (isDestroyed || !map) return

    map.relayout()
    map.setCenter(center)
    emitMapViewport()
    emitSelectedMarkerTarget()

    setManagedTimeout(() => {
      if (!map) return

      map.relayout()
      map.setCenter(center)
      emitMapViewport()
      emitSelectedMarkerTarget()
    }, 150)

    setManagedTimeout(() => {
      if (!map) return

      emitSelectedMarkerTarget()
    }, 320)
  }

  const renderMarkers = ({ fitBounds = false } = {}) => {
    if (!map) return

    clearMarkers()

    const visibleMarkerGroups = getVisibleMarkerGroups()

    if (!visibleMarkerGroups.length) return

    const bounds = new window.kakao.maps.LatLngBounds()

    visibleMarkerGroups.forEach((groupPlaces) => {
      const representativePlace = groupPlaces[0]

      if (!representativePlace.lat || !representativePlace.lng) return

      const position = new window.kakao.maps.LatLng(
        representativePlace.lat,
        representativePlace.lng,
      )
      const markerPlace = getGroupedPlaceMarkerPlace({
        places: groupPlaces,
        position,
      })

      const markerOptions = {
        map,
        position,
        title: groupPlaces.map((place) => place.name).filter(Boolean).join(', '),
      }

      if (markerPlace.markerLabel) {
        markerOptions.image = createNumberMarkerImage(
          markerPlace.markerLabel,
          markerPlace.markerColor,
          groupPlaces.length,
        )
      }

      const marker = new window.kakao.maps.Marker(markerOptions)
      const group = {
        marker,
        infoWindow: null,
        places: groupPlaces,
        position,
      }

      group.infoWindow = createPlaceSelectionInfoWindow(group)

      markers.push(marker)
      markerGroups.push(group)

      groupPlaces.forEach((place) => {
        markerRecords.set(String(place.id), {
          marker,
          infoWindow: group.infoWindow,
          place,
          position,
          group,
        })
      })

      bounds.extend(position)

      window.kakao.maps.event.addListener(marker, 'click', () => {
        shouldSkipNextMapClickClose = true
        setManagedTimeout(() => {
          shouldSkipNextMapClickClose = false
        }, 0)

        if (groupPlaces.length === 1) {
          closeActiveInfoWindow()
          emit('onSelectPlace', representativePlace, getMarkerScreenTarget(position))
          return
        }

        closeActiveInfoWindow()
        updateGroupMarkerImages()
        group.infoWindow.open(map, marker)
        activeInfoWindow = group.infoWindow
        notifyChoiceMenuOpen()
      })
    })

    if (markers.length > 0 && fitBounds) {
      map.setBounds(bounds)
    }

    if (propsRef.current.selectedPlaceId) {
      openMarkerByPlaceId(propsRef.current.selectedPlaceId)
      scheduleSelectedMarkerTarget()
    }
  }

  const initMap = () => {
    if (isDestroyed || !containerRef.current) return

    const { center } = propsRef.current
    const centerLatLng = new window.kakao.maps.LatLng(center.lat, center.lng)

    map = new window.kakao.maps.Map(containerRef.current, {
      center: centerLatLng,
      level: 4,
    })

    window.kakao.maps.event.addListener(map, 'idle', () => {
      emitMapViewport()
      emitSelectedMarkerTarget()
    })
    window.kakao.maps.event.addListener(map, 'zoom_changed', () => {
      renderMarkers()
      scheduleSelectedMarkerTarget()
    })
    window.kakao.maps.event.addListener(map, 'click', () => {
      if (shouldSkipNextMapClickClose) {
        shouldSkipNextMapClickClose = false
        return
      }

      closeActiveInfoWindow()
    })
    emitMapViewport()

    lastFitBoundsKey = propsRef.current.fitBoundsKey
    renderMarkers({ fitBounds: true })

    document.addEventListener('click', handleOutsideInfoWindowClick, true)
    window.addEventListener('scroll', scheduleSelectedMarkerTarget, true)
    window.addEventListener('resize', scheduleSelectedMarkerTarget)
  }

  const syncPlaces = () => {
    const shouldFitBounds = propsRef.current.fitBoundsKey !== lastFitBoundsKey

    renderMarkers({ fitBounds: shouldFitBounds })

    if (shouldFitBounds) {
      lastFitBoundsKey = propsRef.current.fitBoundsKey
    }
  }

  const syncCenter = () => {
    if (!map) return

    const { center } = propsRef.current

    map.setCenter(new window.kakao.maps.LatLng(center.lat, center.lng))
  }

  const syncSelectedPlaceId = (placeId) => {
    if (propsRef.current.selectedPlace) return

    if (!placeId) {
      closeActiveInfoWindow()
      return
    }

    openMarkerByPlaceId(placeId)
    scheduleSelectedMarkerTarget()
  }

  const syncSelectedPlace = (place) => {
    if (!place) {
      closeActiveInfoWindow()
      updateGroupMarkerImages()
      return
    }

    updateGroupMarkerImages()
    openMarkerByPlaceId(place.id, false)
    focusSelectedPlaceOnMap(place)
    scheduleSelectedMarkerTarget()
  }

  const syncHiddenPlaceId = () => {
    renderMarkers()
    scheduleSelectedMarkerTarget()
  }

  const destroy = () => {
    isDestroyed = true

    document.removeEventListener('click', handleOutsideInfoWindowClick, true)
    window.removeEventListener('scroll', scheduleSelectedMarkerTarget, true)
    window.removeEventListener('resize', scheduleSelectedMarkerTarget)

    if (markerTargetFrame) {
      window.cancelAnimationFrame(markerTargetFrame)
      markerTargetFrame = null
    }

    pendingTimeouts.forEach((timeoutId) => window.clearTimeout(timeoutId))
    pendingTimeouts.clear()

    clearMarkers()
    map = null
  }

  return {
    initMap,
    syncPlaces,
    syncCenter,
    syncSelectedPlaceId,
    syncSelectedPlace,
    syncHiddenPlaceId,
    openSelectedPlaceChoiceMenu,
    relayoutMap,
    destroy,
  }
}

const KakaoMap = ({
  places = [],
  center = DEFAULT_CENTER,
  selectedPlaceId = null,
  selectedPlace = null,
  hiddenPlaceId = null,
  choiceRequestKey = null,
  fitBoundsKey = null,
  layoutKey = null,
  onSelectPlace,
  onCenterChange,
  onMarkerTargetChange,
  className = '',
}) => {
  const containerRef = useRef(null)
  const engineRef = useRef(null)

  // 최신 props/콜백을 지도 클로저에서 읽습니다.
  const propsRef = useRef({})
  propsRef.current = {
    places,
    center,
    selectedPlaceId,
    selectedPlace,
    hiddenPlaceId,
    choiceRequestKey,
    fitBoundsKey,
    layoutKey,
  }

  const callbacksRef = useRef({})
  callbacksRef.current = { onSelectPlace, onCenterChange, onMarkerTargetChange }

  /**
   * React 의 효과 의존성은 참조로 비교되므로 변경 여부를 명시적으로 판단합니다.
   * 부모가 매 렌더 새 배열을 넘겨도 마커를 다시 그리지 않도록 내용으로 서명을 만듭니다.
   */
  const placesSignature = useMemo(() => (
    (places || [])
      .map((place) => [
        place?.id,
        place?.lat,
        place?.lng,
        place?.markerLabel,
        place?.markerColor,
        place?.name,
      ].join(':'))
      .join('|')
  ), [places])

  useEffect(() => {
    const engine = createMapEngine({ containerRef, propsRef, callbacksRef })
    engineRef.current = engine
    let isCancelled = false

    loadKakaoMapScript()
      .then(() => {
        if (isCancelled) return
        engine.initMap()
      })
      .catch((error) => {
        console.error(error)
      })

    return () => {
      isCancelled = true
      engineRef.current = null
      engine.destroy()
    }
  }, [])

  // 첫 렌더는 initMap이 처리하므로 이후 변경만 반영합니다.
  const isFirstPlacesSync = useRef(true)
  useEffect(() => {
    if (isFirstPlacesSync.current) {
      isFirstPlacesSync.current = false
      return
    }

    engineRef.current?.syncPlaces()
  }, [placesSignature, fitBoundsKey])

  const isFirstCenterSync = useRef(true)
  useEffect(() => {
    if (isFirstCenterSync.current) {
      isFirstCenterSync.current = false
      return
    }

    engineRef.current?.syncCenter()
  }, [center?.lat, center?.lng])

  const isFirstSelectedIdSync = useRef(true)
  useEffect(() => {
    if (isFirstSelectedIdSync.current) {
      isFirstSelectedIdSync.current = false
      return
    }

    engineRef.current?.syncSelectedPlaceId(selectedPlaceId)
  }, [selectedPlaceId])

  const isFirstSelectedPlaceSync = useRef(true)
  useEffect(() => {
    if (isFirstSelectedPlaceSync.current) {
      isFirstSelectedPlaceSync.current = false
      return
    }

    engineRef.current?.syncSelectedPlace(selectedPlace)
  }, [selectedPlace])

  const isFirstHiddenSync = useRef(true)
  useEffect(() => {
    if (isFirstHiddenSync.current) {
      isFirstHiddenSync.current = false
      return
    }

    engineRef.current?.syncHiddenPlaceId()
  }, [hiddenPlaceId])

  const isFirstChoiceSync = useRef(true)
  useEffect(() => {
    if (isFirstChoiceSync.current) {
      isFirstChoiceSync.current = false
      return
    }

    engineRef.current?.openSelectedPlaceChoiceMenu()
  }, [choiceRequestKey])

  const isFirstLayoutSync = useRef(true)
  useEffect(() => {
    if (isFirstLayoutSync.current) {
      isFirstLayoutSync.current = false
      return
    }

    engineRef.current?.relayoutMap()
  }, [layoutKey])

  return (
    // 지도를 감싸는 화면들이 바깥에서 크기를 덮어쓰고 있어서
    // 모듈 클래스와 함께 예전 전역 클래스 이름도 남겨 둡니다.
    <section className={`${styles.mapSection} map-section ${className}`.trim()}>
      <div ref={containerRef} className={`${styles.map} map`} />
    </section>
  )
}

export default KakaoMap
