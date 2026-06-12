<script setup>
import { onMounted, ref, watch } from 'vue'

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
})

const emit = defineEmits(['select-place'])

const mapContainer = ref(null)

let map = null
let markers = []
let markerRecords = new Map()
let activeInfoWindow = null

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
  const fontSize = safeLabel.length >= 2 ? 12 : 15

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="38" height="42" viewBox="0 0 38 42">
      <path
        d="M19 1 C9.6 1 2 8.6 2 18 C2 30.3 19 41 19 41 C19 41 36 30.3 36 18 C36 8.6 28.4 1 19 1 Z"
        fill="#ffffff"
        stroke="#ef4444"
        stroke-width="3"
      />
      <circle cx="19" cy="18" r="12" fill="#ffffff" />
      <text
        x="19"
        y="23"
        text-anchor="middle"
        font-size="${fontSize}"
        font-weight="900"
        font-family="Arial, sans-serif"
        fill="#ef4444"
      >${safeLabel}</text>
    </svg>
  `

  const imageSrc = `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
  const imageSize = new window.kakao.maps.Size(38, 42)
  const imageOption = {
    offset: new window.kakao.maps.Point(19, 41),
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

const renderMarkers = () => {
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
      markerOptions.image = createNumberMarkerImage(place.markerLabel)
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
      emit('select-place', place)
    })
  })

  if (markers.length > 0) {
    map.setBounds(bounds)
  }

  if (props.selectedPlaceId) {
    openMarkerByPlaceId(props.selectedPlaceId)
  }
}

onMounted(async () => {
  try {
    await loadKakaoMapScript()
    initMap()
    renderMarkers()
  } catch (error) {
    console.error(error)
  }
})

watch(
  () => props.places,
  () => {
    renderMarkers()
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
    if (!placeId) {
      closeActiveInfoWindow()
      return
    }

    openMarkerByPlaceId(placeId)
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
