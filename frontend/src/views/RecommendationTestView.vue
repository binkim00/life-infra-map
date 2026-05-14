<script setup>
import { ref, onMounted } from 'vue'
import { getRecommendations } from '@/api/recommendation'
import RecommendationCard from '@/components/RecommendationCard.vue'
import KakaoMap from '@/components/KakaoMap.vue'

const selectedScenario = ref('work_cafe')
const scenario = ref('')
const keyword = ref('')
const results = ref([])
const loading = ref(false)
const error = ref('')
const position = ref({
  lat: 37.5665,
  lng: 126.9780,
  label: '기본 위치: 서울시청',
})

const scenarios = [
  {
    code: 'work_cafe',
    label: '작업 카페',
  },
  {
    code: 'waiting_place',
    label: '약속 전 시간 때우기',
  },
  {
    code: 'walk_healing',
    label: '산책/힐링',
  },
  {
    code: 'smoking_area',
    label: '흡연구역',
  },
]

const fetchRecommendations = async () => {
  loading.value = true
  error.value = ''

  try {
    const data = await getRecommendations({
      scenario: selectedScenario.value,
      lat: position.value.lat,
      lng: position.value.lng,
    })

    scenario.value = data.scenario
    keyword.value = data.keyword
    results.value = data.results
  } catch (err) {
    error.value = '추천 결과를 불러오지 못했습니다.'
    console.error(err)
  } finally {
    loading.value = false
  }
}

const selectScenario = async (scenarioCode) => {
  selectedScenario.value = scenarioCode
  await fetchRecommendations()
}

const useCurrentLocation = () => {
  if (!navigator.geolocation) {
    error.value = '현재 브라우저에서 위치 정보를 사용할 수 없습니다.'
    return
  }

  navigator.geolocation.getCurrentPosition(
    async (currentPosition) => {
      position.value = {
        lat: currentPosition.coords.latitude,
        lng: currentPosition.coords.longitude,
        label: '현재 위치',
      }

      await fetchRecommendations()
    },
    (err) => {
      error.value = '현재 위치를 가져오지 못했습니다. 기본 위치로 테스트합니다.'
      console.error(err)
    },
  )
}

onMounted(() => {
  fetchRecommendations()
})
</script>

<template>
  <main class="page">
    <section class="header">
      <h1>추천 API 테스트</h1>
      <p>카카오 장소 검색 결과에 임시 태그와 추천 이유를 붙이는 테스트 화면입니다.</p>
    </section>

    <section class="controls">
      <div class="scenario-buttons">
        <button v-for="item in scenarios" :key="item.code" type="button"
          :class="{ active: selectedScenario === item.code }" @click="selectScenario(item.code)">
          {{ item.label }}
        </button>
      </div>

      <button type="button" class="location-button" @click="useCurrentLocation">
        현재 위치로 테스트
      </button>
    </section>

    <section class="info">
      <p>위치 기준: {{ position.label }}</p>
      <p>lat: {{ position.lat }}, lng: {{ position.lng }}</p>
      <p v-if="scenario">시나리오: {{ scenario }}</p>
      <p v-if="keyword">검색 키워드: {{ keyword }}</p>
    </section>

    <section v-if="loading">
      추천 결과를 불러오는 중입니다.
    </section>

    <section v-else-if="error">
      {{ error }}
    </section>

    <section v-else>
      <p v-if="results.length === 0" class="empty">
        추천 결과가 없습니다. 이 시나리오는 지도 API만으로 결과 확보가 어려울 수 있습니다.
      </p>

      <KakaoMap :places="results" :center="position" />

      <RecommendationCard v-for="place in results" :key="place.name" :place="place" />
    </section>
  </main>
</template>

<style scoped>
.page {
  max-width: 760px;
  margin: 0 auto;
  padding: 40px 20px;
  color: #222;
}

.header {
  margin-bottom: 24px;
}

.controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.scenario-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

button {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}

button.active {
  background: #222;
  color: #fff;
  border-color: #222;
}

.location-button {
  width: fit-content;
}

.info {
  padding: 12px;
  border-radius: 12px;
  background: #f8f9fa;
  margin-bottom: 20px;
  font-size: 14px;
}

.info p {
  margin: 4px 0;
}

.empty {
  padding: 20px;
  border: 1px dashed #ccc;
  border-radius: 12px;
  color: #666;
}
</style>