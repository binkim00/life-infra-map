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
    label: '조용히 작업할 곳',
  },
  {
    code: 'waiting_place',
    label: '잠깐 머물 곳',
  },
  {
    code: 'walk_healing',
    label: '산책하기 좋은 곳',
  },
  {
    code: 'smoking_area',
    label: '가까운 흡연구역',
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
    error.value = '추천 결과를 불러오지 못했습니다. 서버 실행 상태와 API 키 설정을 확인해 주세요.'
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
      <p class="eyebrow">상황 기반 장소 추천</p>
      <h1>지금 필요한 장소를 추천해드립니다</h1>
      <p>
        현재 위치와 선택한 상황을 기준으로 가까운 생활 장소를 추천하고,
        추천 결과를 지도와 목록에서 함께 확인합니다.
      </p>
    </section>

    <section class="controls">
      <div class="scenario-buttons">
        <button v-for="item in scenarios" :key="item.code" type="button"
          :class="{ active: selectedScenario === item.code }" @click="selectScenario(item.code)">
          {{ item.label }}
        </button>
      </div>

      <button type="button" class="location-button" @click="useCurrentLocation">
        현재 위치로 다시 추천받기
      </button>
    </section>

    <section class="info">
      <p>위치 기준: {{ position.label }}</p>
      <p>좌표: {{ position.lat }}, {{ position.lng }}</p>
      <p v-if="scenario">선택 상황: {{ scenario }}</p>
      <p v-if="keyword">검색 기준: {{ keyword }}</p>
    </section>

    <section v-if="loading" class="message">
       현재 위치와 상황에 맞는 장소를 찾는 중입니다.
    </section>

    <section v-else-if="error" class="message error">
      {{ error }}
    </section>

    <section v-else>
      <p v-if="results.length === 0" class="empty">
        현재 위치 주변 1km 이내에서 추천 가능한 장소를 찾지 못했습니다.<br />
        다른 상황을 선택하거나 위치를 변경해서 다시 확인해 주세요.
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

.eyebrow {
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #555;
}

.header h1 {
  margin: 0 0 12px;
  font-size: 32px;
  line-height: 1.25;
}

.header p {
  color: #555;
  line-height: 1.6;
}

.message,
.empty {
  padding: 20px;
  border-radius: 12px;
  background: #f8f9fa;
  color: #555;
  line-height: 1.6;
}

.error {
  color: #c92a2a;
}
</style>