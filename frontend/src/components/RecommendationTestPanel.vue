<script setup>
import { computed, onMounted, ref } from 'vue'
import { aiSearchRecommendations, getRecommendations } from '@/api/recommendation'
import RecommendationCard from '@/components/RecommendationCard.vue'
import KakaoMap from '@/components/KakaoMap.vue'

const selectedScenario = ref('work_cafe')
const scenario = ref('')
const keyword = ref('')
const results = ref([])
const loading = ref(false)
const error = ref('')
const naturalQuery = ref('조용하고 콘센트 있는 작업하기 좋은 카페')
const aiParse = ref(null)
const searchMode = ref('scenario')
const position = ref({
  lat: 35.1556,
  lng: 129.0641,
  label: '기본 테스트 위치: 서면/전포',
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

const parserStatus = computed(() => {
  if (searchMode.value === 'scenario' || !aiParse.value) {
    return {
      label: 'AI 미사용',
      detail: '시나리오 버튼 추천은 자연어 해석 없이 DB 추천 조건을 바로 사용합니다.',
      className: 'manual',
    }
  }

  if (!aiParse.value.parser_fallback && aiParse.value.parser_provider === 'gms') {
    return {
      label: 'AI 사용',
      detail: 'GMS가 자연어를 scenario/categories/tags 조건으로 해석했습니다.',
      className: 'ai',
    }
  }

  if (!aiParse.value.parser_fallback && aiParse.value.parser_provider === 'openai') {
    return {
      label: 'AI 사용',
      detail: 'OpenAI가 자연어를 추천 조건으로 해석했습니다.',
      className: 'ai',
    }
  }

  return {
    label: '규칙 기반 파서 사용',
    detail: 'AI 호출이 없거나 실패해서 키워드 규칙으로 추천 조건을 해석했습니다.',
    className: 'fallback',
  }
})

const applyResponse = (data) => {
  scenario.value = data.scenario
  keyword.value = data.keyword
  results.value = data.results || []
  aiParse.value = data.ai_parse || null
}

const fetchRecommendations = async () => {
  loading.value = true
  error.value = ''
  aiParse.value = null
  searchMode.value = 'scenario'

  try {
    const data = await getRecommendations({
      scenario: selectedScenario.value,
      lat: position.value.lat,
      lng: position.value.lng,
    })

    applyResponse(data)
  } catch (err) {
    error.value = '추천 결과를 불러오지 못했습니다. 백엔드 서버 실행 상태를 확인해 주세요.'
    console.error(err)
  } finally {
    loading.value = false
  }
}

const searchByNaturalQuery = async () => {
  if (!naturalQuery.value.trim()) {
    error.value = '찾고 싶은 상황을 입력해 주세요.'
    return
  }

  loading.value = true
  error.value = ''
  searchMode.value = 'natural'

  try {
    const data = await aiSearchRecommendations({
      query: naturalQuery.value,
      lat: position.value.lat,
      lng: position.value.lng,
    })

    selectedScenario.value = data.scenario
    applyResponse(data)
  } catch (err) {
    error.value = '자연어 추천 결과를 불러오지 못했습니다. 백엔드 서버 실행 상태를 확인해 주세요.'
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
  <section class="recommendation-panel">
    <header class="panel-header">
      <p class="eyebrow">추천 로직 테스트</p>
      <h1>DB 기반 추천과 자연어 해석을 확인합니다</h1>
      <p>
        실제 장소 결과는 DB의 Place, Tag, PlaceTag에서만 가져오고, 자연어 해석은 추천 조건을 만드는 데만 사용합니다.
      </p>
    </header>

    <section class="controls">
      <form class="natural-search" @submit.prevent="searchByNaturalQuery">
        <input
          v-model="naturalQuery"
          type="text"
          placeholder="예: 비 오는데 잠깐 실내에서 쉴 곳"
        />
        <button type="submit">자연어 추천</button>
      </form>

      <div class="scenario-buttons">
        <button
          v-for="item in scenarios"
          :key="item.code"
          type="button"
          :class="{ active: selectedScenario === item.code }"
          @click="selectScenario(item.code)"
        >
          {{ item.label }}
        </button>
      </div>

      <button type="button" class="location-button" @click="useCurrentLocation">
        현재 위치로 다시 추천받기
      </button>
    </section>

    <section class="info">
      <div class="parser-status" :class="parserStatus.className">
        <strong>{{ parserStatus.label }}</strong>
        <span>{{ parserStatus.detail }}</span>
      </div>

      <p>위치 기준: {{ position.label }}</p>
      <p>좌표: {{ position.lat }}, {{ position.lng }}</p>
      <p v-if="scenario">선택 상황: {{ scenario }}</p>
      <p v-if="keyword">검색 기준: {{ keyword }}</p>
      <p v-if="aiParse">자연어 해석: {{ aiParse.situation_summary }}</p>
      <p v-if="aiParse">
        파서 정보: {{ aiParse.parser_provider }} / fallback {{ aiParse.parser_fallback ? '사용' : '미사용' }}
      </p>
    </section>

    <section v-if="loading" class="message">
      현재 위치와 상황에 맞는 장소를 찾는 중입니다.
    </section>

    <section v-else-if="error" class="message error">
      {{ error }}
    </section>

    <section v-else class="results">
      <p v-if="results.length === 0" class="empty">
        현재 위치 주변에서 추천 가능한 장소를 찾지 못했습니다.<br />
        다른 상황을 선택하거나 위치를 바꿔 다시 확인해 주세요.
      </p>

      <KakaoMap :places="results" :center="position" />

      <RecommendationCard
        v-for="place in results"
        :key="place.id || place.name"
        :place="place"
      />
    </section>
  </section>
</template>

<style scoped>
.recommendation-panel {
  max-width: 960px;
  margin: 28px auto 0;
  color: #222;
}

.panel-header {
  margin-bottom: 20px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #2563eb;
  font-size: 14px;
  font-weight: 800;
}

.panel-header h1 {
  margin: 0 0 10px;
  color: #111827;
  font-size: 28px;
  line-height: 1.3;
}

.panel-header p {
  margin: 0;
  color: #667085;
  line-height: 1.6;
}

.controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.natural-search {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.natural-search input {
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  font-size: 14px;
}

.scenario-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

button {
  padding: 9px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  background: #fff;
  color: #344054;
  cursor: pointer;
  font-weight: 700;
}

button.active {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}

.location-button {
  width: fit-content;
}

.info,
.message,
.empty {
  padding: 14px;
  border-radius: 8px;
  background: #f8f9fa;
  color: #555;
  line-height: 1.6;
}

.info {
  margin-bottom: 16px;
  font-size: 14px;
}

.info p {
  margin: 4px 0;
}

.parser-status {
  margin-bottom: 10px;
  padding: 10px 12px;
  display: grid;
  gap: 3px;
  border-radius: 8px;
}

.parser-status strong {
  font-size: 14px;
}

.parser-status span {
  font-size: 13px;
}

.parser-status.ai {
  background: #e7f5ff;
  color: #1864ab;
}

.parser-status.fallback {
  background: #fff3bf;
  color: #8d6b00;
}

.parser-status.manual {
  background: #edf2ff;
  color: #364fc7;
}

.error {
  color: #c92a2a;
}

.empty {
  border: 1px dashed #d0d5dd;
}

.results {
  display: grid;
  gap: 16px;
}

@media (max-width: 560px) {
  .natural-search {
    grid-template-columns: 1fr;
  }
}
</style>
