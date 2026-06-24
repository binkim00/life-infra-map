<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

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

let map = null
let markers = []
let markerRecords = new Map()
let activeInfoWindow = null
let lastFitBoundsKey = null
let markerTargetFrame = null

const loadKakaoMapScript = () => {
  return new Promise((resolve, reject) => {
    if (window.kakao && window.kakao.maps && window.kakao.maps.services) {
      resolve()
      return
    }

    const kakaoKey = import.meta.env.VITE_KAKAO_JAVASCRIPT_KEY

    if (!kakaoKey) {
      reject(new Error('VITE_KAKAO_JAVASCRIPT_KEY가 설정되지 않았습니다.'))
      return
    }

    const script = document.createElement('script')
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${kakaoKey}&autoload=false&libraries=services`
    script.async = true

    script.onload = () => {
      window.kakao.maps.load(() => {
        resolve()
      })
    }

    script.onerror = () => {
      reject(new Error('카카오맵 SDK를 불러오지 못했습니다.'))
    }

    document.head.appendChild(script)
  })
}

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
  }
}

const clearMarkers = () => {
  closeActiveInfoWindow()

  markers.forEach((marker) => marker.setMap(null))
  markers = []
  markerRecords = new Map()
}

const createNumberMarkerImage = (label) => {
  const safeLabel = String(label || '')
  const fontSize = safeLabel.length >= 2 ? 13 : 16

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="54" height="54" viewBox="0 0 54 54">
      <filter id="boneShadow" x="-10%" y="-20%" width="120%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="1.3" flood-color="#1f2937" flood-opacity="0.25"/>
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
          stroke="#222222"
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
    </svg>
  `

  const imageSrc = `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
  const imageSize = new window.kakao.maps.Size(54, 54)
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

const emitSelectedMarkerTarget = () => {
  const selectedId = props.selectedPlace?.id || props.selectedPlaceId

  if (!selectedId) return

  const record = markerRecords.get(String(selectedId))

  if (!record) return

  emit('marker-target-change', record.place, getMarkerScreenTarget(record.position))
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

  if (!record) return

  closeActiveInfoWindow()

  record.infoWindow.open(map, record.marker)
  activeInfoWindow = record.infoWindow

  if (shouldMoveMap) {
    map.panTo(record.position)
  }
}

const focusSelectedPlaceOnMap = async (place) => {
  if (!map || !place?.lat || !place?.lng || !window.kakao?.maps) return

  await nextTick()

  const position = new window.kakao.maps.LatLng(
    Number(place.lat),
    Number(place.lng),
  )

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

  setTimeout(() => {
    if (!map) return

    map.relayout()
    map.setCenter(center)
    emitMapViewport()
  }, 150)
}

const renderMarkers = ({ fitBounds = false } = {}) => {
  if (!map) return

  clearMarkers()

  if (!props.places.length) return

  const bounds = new window.kakao.maps.LatLngBounds()

  props.places.forEach((place) => {
    if (!place.lat || !place.lng) return

    const position = new window.kakao.maps.LatLng(place.lat, place.lng)

    const markerOptions = {
      map,
      position,
      title: place.name,
    }

    if (place.markerLabel) {
      markerOptions.image = createNumberMarkerImage(
        place.markerLabel,
        place.markerColor,
      )
    }

    const marker = new window.kakao.maps.Marker(markerOptions)
    const infoWindow = createInfoWindow(place)

    markers.push(marker)
    markerRecords.set(String(place.id), {
      marker,
      infoWindow,
      place,
      position,
    })

    bounds.extend(position)

    window.kakao.maps.event.addListener(marker, 'click', () => {
      openMarkerByPlaceId(place.id, false)
      emit('select-place', place, getMarkerScreenTarget(position))
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
    window.addEventListener('scroll', scheduleSelectedMarkerTarget, true)
    window.addEventListener('resize', scheduleSelectedMarkerTarget)
  } catch (error) {
    console.error(error)
  }
})

onBeforeUnmount(() => {
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
      return
    }

    openMarkerByPlaceId(place.id, false)
    focusSelectedPlaceOnMap(place)
    scheduleSelectedMarkerTarget()
  },
  { deep: true },
)

watch(
  () => props.layoutKey,
  () => {
    relayoutMap()
    scheduleSelectedMarkerTarget()
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
</style>
