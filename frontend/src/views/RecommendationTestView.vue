<script setup>
import { ref, onMounted } from 'vue'
import { getRecommendationTest } from '@/api/recommendation'
import RecommendationCard from '@/components/RecommendationCard.vue'

const scenario = ref('')
const results = ref([])
const loading = ref(false)
const error = ref('')

const fetchRecommendations = async () => {
  loading.value = true
  error.value = ''

  try {
    const data = await getRecommendationTest('work_cafe')
    scenario.value = data.scenario
    results.value = data.results
  } catch (err) {
    error.value = '추천 결과를 불러오지 못했습니다.'
    console.error(err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchRecommendations()
})
</script>

<template>
  <main class="page">
    <section class="header">
      <h1>추천 API 테스트</h1>
      <p>Django 추천 목업 API 응답을 Vue에서 받아오는 테스트 화면입니다.</p>
    </section>

    <section v-if="loading">
      추천 결과를 불러오는 중입니다.
    </section>

    <section v-else-if="error">
      {{ error }}
    </section>

    <section v-else>
      <p class="scenario">시나리오: {{ scenario }}</p>

      <RecommendationCard
        v-for="place in results"
        :key="place.name"
        :place="place"
      />
    </section>
  </main>
</template>

<style scoped>
.page {
  max-width: 720px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header {
  margin-bottom: 32px;
}

.scenario {
  margin-bottom: 16px;
  font-weight: 600;
}
</style>