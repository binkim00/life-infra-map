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

const mapContainer = ref(null)
let map = null
let markers = []

const loadKakaoMapScript = () => {
  return new Promise((resolve, reject) => {
    if (window.kakao && window.kakao.maps) {
      resolve()
      return
    }

    const kakaoKey = import.meta.env.VITE_KAKAO_JAVASCRIPT_KEY

    if (!kakaoKey) {
      reject(new Error('VITE_KAKAO_JAVASCRIPT_KEY가 설정되지 않았습니다.'))
      return
    }

    const script = document.createElement('script')
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${kakaoKey}&autoload=false`
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
  markers.forEach((marker) => marker.setMap(null))
  markers = []
}

const renderMarkers = () => {
  if (!map || !props.places.length) return

  clearMarkers()

  const bounds = new window.kakao.maps.LatLngBounds()

  props.places.forEach((place) => {
    if (!place.lat || !place.lng) return

    const position = new window.kakao.maps.LatLng(place.lat, place.lng)

    const marker = new window.kakao.maps.Marker({
      map,
      position,
      title: place.name,
    })

    markers.push(marker)
    bounds.extend(position)

    const infoWindow = new window.kakao.maps.InfoWindow({
      content: `
        <div style="padding:8px;font-size:13px;min-width:150px;">
          <strong>${place.name}</strong><br />
          ${place.distance ?? '-'}m · ${place.score ?? '-'}점
        </div>
      `,
    })

    window.kakao.maps.event.addListener(marker, 'click', () => {
      infoWindow.open(map, marker)
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
  margin-bottom: 24px;
}

.map {
  width: 100%;
  height: 360px;
  border: 1px solid #ddd;
  border-radius: 16px;
}
</style>