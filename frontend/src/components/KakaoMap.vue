<script setup>
import { onMounted, watch, ref } from 'vue'

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
})

const emit = defineEmits(['select-place'])

const mapContainer = ref(null)
let map = null
let markers = []
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

    const existingScript = document.querySelector('script[data-kakao-map-sdk="true"]')

    if (existingScript) {
      existingScript.addEventListener('load', () => {
        window.kakao.maps.load(() => resolve())
      })
      return
    }

    const script = document.createElement('script')
    script.dataset.kakaoMapSdk = 'true'
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
  const centerLatLng = new window.kakao.maps.LatLng(props.center.lat, props.center.lng)

  map = new window.kakao.maps.Map(mapContainer.value, {
    center: centerLatLng,
    level: 4,
  })
}

const clearMarkers = () => {
  if (activeInfoWindow) {
    activeInfoWindow.close()
    activeInfoWindow = null
  }

  markers.forEach((marker) => marker.setMap(null))
  markers = []
}

const createRedMarkerImage = () => {
  const svg = `
    <svg width="34" height="42" viewBox="0 0 34 42" xmlns="http://www.w3.org/2000/svg">
      <path d="M17 0C7.6 0 0 7.6 0 17c0 12.8 17 25 17 25s17-12.2 17-25C34 7.6 26.4 0 17 0z" fill="#ef4444"/>
      <circle cx="17" cy="17" r="7" fill="white"/>
    </svg>
  `

  const imageSrc = `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
  const imageSize = new window.kakao.maps.Size(34, 42)
  const imageOption = {
    offset: new window.kakao.maps.Point(17, 42),
  }

  return new window.kakao.maps.MarkerImage(imageSrc, imageSize, imageOption)
}

const renderMarkers = () => {
  if (!map) return

  clearMarkers()

  if (!props.places.length) return

  const bounds = new window.kakao.maps.LatLngBounds()
  const redMarkerImage = createRedMarkerImage()

  props.places.forEach((place) => {
    if (!place.lat || !place.lng) return

    const position = new window.kakao.maps.LatLng(place.lat, place.lng)

    const markerOptions = {
      map,
      position,
      title: place.name,
    }

    if (place.markerColor === 'red') {
      markerOptions.image = redMarkerImage
    }

    const marker = new window.kakao.maps.Marker(markerOptions)

    markers.push(marker)
    bounds.extend(position)

    const infoWindow = new window.kakao.maps.InfoWindow({
      content: `
        <div style="padding:10px;font-size:13px;min-width:160px;line-height:1.5;">
          <strong>${place.name}</strong>
        </div>
      `,
    })

    window.kakao.maps.event.addListener(marker, 'click', () => {
      if (activeInfoWindow) {
        activeInfoWindow.close()
      }

      infoWindow.open(map, marker)
      activeInfoWindow = infoWindow

      emit('select-place', place)
    })
  })

  if (markers.length > 0) {
    map.setBounds(bounds)
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

    const centerLatLng = new window.kakao.maps.LatLng(props.center.lat, props.center.lng)
    map.setCenter(centerLatLng)
  },
  { deep: true },
)
</script>

<template>
  <section class="map-section">
    <div ref="mapContainer" class="map"></div>
  </section>
</template>

<style scoped>
.map-section {
  width: 100%;
}

.map {
  width: 100%;
  height: 360px;
  border: 1px solid #ddd;
  border-radius: 16px;
}
</style>