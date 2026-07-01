<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadKakaoMapScript } from '@/composables/useKakaoMapSdk'

const props = defineProps({
  places: {
    type: Array,
    default: () => [],
  },
  center: {
    type: Object,
    default: () => ({
      lat: 37.5665,
      lng: 126.9780,
    }),
  },
  selectedPlaceId: {
    type: [String, Number, null],
    default: null,
  },
  selectedPlace: {
    type: Object,
    default: null,
  },
  hiddenPlaceId: {
    type: [String, Number, null],
    default: null,
  },
  choiceRequestKey: {
    type: [String, Number, null],
    default: null,
  },
  fitBoundsKey: {
    type: [String, Number, null],
    default: null,
  },
  layoutKey: {
    type: [String, Number, null],
    default: null,
  },
})

const emit = defineEmits(['select-place', 'center-change', 'marker-target-change'])

const mapContainer = ref(null)
const MARKER_OVERLAP_PIXEL_THRESHOLD = 30

let map = null
let markers = []
let markerRecords = new Map()
let markerGroups = []
let activeInfoWindow = null
let lastFitBoundsKey = null
let markerTargetFrame = null
let shouldSkipNextMapClickClose = false

const initMap = () => {
  const centerLatLng = new window.kakao.maps.LatLng(
    props.center.lat,
    props.center.lng,
  )

  map = new window.kakao.maps.Map(mapContainer.value, {
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

  emit('center-change', {
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
  if (mapContainer.value?.contains(event.target)) return

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

const createTransparentMarkerImage = () => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'

  return new window.kakao.maps.MarkerImage(
    `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    new window.kakao.maps.Size(1, 1),
    { offset: new window.kakao.maps.Point(0, 0) },
  )
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
  const selectedId = props.selectedPlace?.id || props.selectedPlaceId
  const selectedPlace = selectedId
    ? group.places.find((place) => String(place.id) === String(selectedId))
    : null

  return selectedPlace || group.places[0]
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
      emit('select-place', place, getMarkerScreenTarget(group.position))
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
    Math.abs(firstPoint.x - secondPoint.x) <= MARKER_OVERLAP_PIXEL_THRESHOLD &&
    Math.abs(firstPoint.y - secondPoint.y) <= MARKER_OVERLAP_PIXEL_THRESHOLD
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
  const groups = groupPlacesByPosition(props.places)

  if (!props.hiddenPlaceId) {
    return groups
  }

  return groups.filter((groupPlaces) => {
    return !groupPlaces.some((place) => String(place.id) === String(props.hiddenPlaceId))
  })
}

const getPlaceMarkerGroup = (placeId) => {
  if (!placeId) return null

  return groupPlacesByPosition(props.places).find((groupPlaces) => {
    return groupPlaces.some((place) => String(place.id) === String(placeId))
  }) || null
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

const openSelectedPlaceChoiceMenu = () => {
  if (!map) return

  const selectedId = props.selectedPlace?.id || props.selectedPlaceId

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

const getMarkerScreenTarget = (position) => {
  if (!map || !mapContainer.value || !position) return null

  const projection = map.getProjection()
  const rect = mapContainer.value.getBoundingClientRect()
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

const getPlaceLatLng = (place) => {
  if (!place?.lat || !place?.lng || !window.kakao?.maps) return null

  return new window.kakao.maps.LatLng(
    Number(place.lat),
    Number(place.lng),
  )
}

const getPlaceById = (placeId) => {
  if (!placeId) return null

  if (props.selectedPlace && String(props.selectedPlace.id) === String(placeId)) {
    return props.selectedPlace
  }

  return props.places.find((place) => String(place.id) === String(placeId)) || null
}

const emitSelectedMarkerTarget = () => {
  const selectedId = props.selectedPlace?.id || props.selectedPlaceId

  if (!selectedId) return

  const record = markerRecords.get(String(selectedId))
  const place = record?.place || getPlaceById(selectedId)
  const position = record?.position || getGroupRepresentativeLatLngByPlaceId(selectedId) || getPlaceLatLng(place)

  if (!place || !position) return

  emit('marker-target-change', place, getMarkerScreenTarget(position))
}

const scheduleSelectedMarkerTarget = () => {
  if (markerTargetFrame) {
    window.cancelAnimationFrame(markerTargetFrame)
  }

  markerTargetFrame = window.requestAnimationFrame(() => {
    markerTargetFrame = null
    emitSelectedMarkerTarget()
  })
}

const openMarkerByPlaceId = (placeId, shouldMoveMap = true) => {
  if (!map || !placeId) return

  const record = markerRecords.get(String(placeId))

  if (!record) {
    const hiddenPlacePosition = getGroupRepresentativeLatLngByPlaceId(placeId) || getPlaceLatLng(getPlaceById(placeId))

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

  await nextTick()

  const position = getGroupRepresentativeLatLngByPlaceId(place.id) || getPlaceLatLng(place)

  if (!position) return

  map.relayout()
  map.panTo(position)

  setTimeout(() => {
    if (!map) return

    map.relayout()
    map.panTo(position)
  }, 150)
}

const relayoutMap = async () => {
  if (!map) return

  const center = map.getCenter()

  await nextTick()
  map.relayout()
  map.setCenter(center)
  emitMapViewport()
  emitSelectedMarkerTarget()

  setTimeout(() => {
    if (!map) return

    map.relayout()
    map.setCenter(center)
    emitMapViewport()
    emitSelectedMarkerTarget()
  }, 150)

  setTimeout(() => {
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
      window.setTimeout(() => {
        shouldSkipNextMapClickClose = false
      }, 0)

      if (groupPlaces.length === 1) {
        closeActiveInfoWindow()
        emit('select-place', representativePlace, getMarkerScreenTarget(position))
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

  if (props.selectedPlaceId) {
    openMarkerByPlaceId(props.selectedPlaceId)
    scheduleSelectedMarkerTarget()
  }
}

onMounted(async () => {
  try {
    await loadKakaoMapScript()
    initMap()
    lastFitBoundsKey = props.fitBoundsKey
    renderMarkers({ fitBounds: true })
    document.addEventListener('click', handleOutsideInfoWindowClick, true)
    window.addEventListener('scroll', scheduleSelectedMarkerTarget, true)
    window.addEventListener('resize', scheduleSelectedMarkerTarget)
  } catch (error) {
    console.error(error)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideInfoWindowClick, true)
  window.removeEventListener('scroll', scheduleSelectedMarkerTarget, true)
  window.removeEventListener('resize', scheduleSelectedMarkerTarget)

  if (markerTargetFrame) {
    window.cancelAnimationFrame(markerTargetFrame)
    markerTargetFrame = null
  }

  clearMarkers()
})

watch(
  () => props.places,
  () => {
    const shouldFitBounds = props.fitBoundsKey !== lastFitBoundsKey

    renderMarkers({ fitBounds: shouldFitBounds })

    if (shouldFitBounds) {
      lastFitBoundsKey = props.fitBoundsKey
    }
  },
  { deep: true },
)

watch(
  () => props.center,
  () => {
    if (!map) return

    const centerLatLng = new window.kakao.maps.LatLng(
      props.center.lat,
      props.center.lng,
    )

    map.setCenter(centerLatLng)
  },
  { deep: true },
)

watch(
  () => props.selectedPlaceId,
  (placeId) => {
    if (props.selectedPlace) return

    if (!placeId) {
      closeActiveInfoWindow()
      return
    }

    openMarkerByPlaceId(placeId)
    scheduleSelectedMarkerTarget()
  },
)

watch(
  () => props.selectedPlace,
  (place) => {
    if (!place) {
      closeActiveInfoWindow()
      updateGroupMarkerImages()
      return
    }

    updateGroupMarkerImages()
    openMarkerByPlaceId(place.id, false)
    focusSelectedPlaceOnMap(place)
    scheduleSelectedMarkerTarget()
  },
  { deep: true },
)

watch(
  () => props.hiddenPlaceId,
  () => {
    renderMarkers()
    scheduleSelectedMarkerTarget()
  },
)

watch(
  () => props.choiceRequestKey,
  () => {
    openSelectedPlaceChoiceMenu()
  },
)

watch(
  () => props.layoutKey,
  () => {
    relayoutMap()
  },
)
</script>

<template>
  <section class="map-section">
    <div ref="mapContainer" class="map"></div>
  </section>
</template>

<style scoped>
.map-section {
  margin-bottom: 0;
}

.map {
  width: 100%;
  height: 360px;
  border: 1px solid #ddd;
  border-radius: 16px;
}

:global(.map-marker-choice) {
  min-width: 190px;
  padding: 10px;
  display: grid;
  gap: 8px;
  color: #222222;
  font-family: inherit;
}

:global(.map-marker-choice-header) {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

:global(.map-marker-choice-title) {
  font-size: 12px;
  font-weight: 900;
}

:global(.map-marker-choice-close) {
  width: 24px;
  height: 24px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #667085;
  font-size: 18px;
  font-weight: 900;
  line-height: 1;
  cursor: pointer;
}

:global(.map-marker-choice-close:hover) {
  background: #f3f4f6;
  color: #222222;
}

:global(.map-marker-choice-list) {
  display: grid;
  gap: 6px;
}

:global(.map-marker-choice-button) {
  width: 100%;
  padding: 7px 8px;
  display: flex;
  gap: 8px;
  align-items: center;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
  color: #222222;
  text-align: left;
  cursor: pointer;
}

:global(.map-marker-choice-button:hover) {
  border-color: #222222;
  background: #fff8e9;
}

:global(.map-marker-choice-label) {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border: 2px solid #222222;
  border-radius: 999px;
  background: #ffffff;
  font-size: 12px;
  font-weight: 900;
}

:global(.map-marker-choice-copy) {
  min-width: 0;
  display: grid;
  gap: 2px;
}

:global(.map-marker-choice-copy strong),
:global(.map-marker-choice-copy small) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.map-marker-choice-copy strong) {
  font-size: 13px;
}

:global(.map-marker-choice-copy small) {
  color: #667085;
  font-size: 11px;
}
</style>
