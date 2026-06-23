<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { deleteSearchLog, fetchSearchLogs } from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const searchLogs = ref([])
const isLoading = ref(false)
const message = ref('')
const deletingLogId = ref(null)
const page = ref(1)
const meta = ref({
  count: 0,
  page: 1,
  pageSize: 5,
  totalPages: 1,
})

const normalizeLabelValue = (item) => {
  if (typeof item === 'string') return item.trim()
  if (typeof item === 'number' && Number.isFinite(item)) return String(item)
  if (!item || typeof item !== 'object') return ''

  const labelKeys = ['label', 'name', 'display_name', 'displayName', 'value', 'text']
  for (const key of labelKeys) {
    const label = normalizeLabelValue(item[key])
    if (label) return label
  }

  return ''
}

const normalizeLabelList = (items) => {
  if (!Array.isArray(items)) return []

  return [...new Set(
    items
      .map(normalizeLabelValue)
      .filter((item) => item && item !== '[object Object]'),
  )]
}

const scenarioLabels = {
  work_cafe: '조용히 작업할 곳',
  waiting_place: '잠깐 쉴 곳',
  walk_healing: '산책/힐링',
  smoking_area: '흡연 가능한 곳',
  restaurant: '식당/맛집',
  blocked: '검색 불가',
}

const categoryLabels = {
  cafe: '카페',
  restaurant: '식당',
  food: '음식',
  toilet: '공중화장실',
  freewifi: '무료 와이파이',
  smoking_area: '흡연구역',
  beach: '해수욕장',
  parking: '주차장',
  city_park: '공원',
  tourism: '관광지',
}

const getMappedLabel = (value, labelMap = {}) => {
  const label = normalizeLabelValue(value)
  const key = label.toLowerCase()

  return labelMap[key] || labelMap[label] || label
}

const getSearchLogCategoryLabel = (log) => {
  return getMappedLabel(log.category_hint, categoryLabels) || getMappedLabel(log.scenario, scenarioLabels)
}

const getSearchLogMeta = (log) => {
  return [
    normalizeLabelValue(log.location_hint),
    getSearchLogCategoryLabel(log),
    `결과 ${log.result_count || 0}개`,
  ].filter(Boolean).join(' · ')
}

const getSearchLogChips = (log) => {
  return normalizeLabelList([
    ...normalizeLabelList(log.menu_keywords),
    ...normalizeLabelList(log.place_type_keywords),
    ...normalizeLabelList(log.requested_conditions),
    ...normalizeLabelList(log.preferred_tags),
  ]).slice(0, 3)
}

const formatSearchLogDate = (value) => {
  if (!value) return ''

  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const fetchLogs = async () => {
  try {
    isLoading.value = true
    message.value = ''
    const response = await fetchSearchLogs({
      page: page.value,
      pageSize: 5,
    })

    searchLogs.value = response.results || []
    meta.value = {
      count: response.count || 0,
      page: response.page || page.value,
      pageSize: response.page_size || 5,
      totalPages: response.total_pages || 1,
    }

    if (!searchLogs.value.length) {
      message.value = '저장된 검색 기록이 없습니다.'
    }
  } catch (error) {
    searchLogs.value = []
    message.value = '검색 기록을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const rerunSearchLog = (log) => {
  if (!log?.query) return

  router.push({
    name: 'home',
    query: {
      q: log.query,
    },
  })
}

const handleDeleteSearchLog = async (log) => {
  if (!log?.id) return

  try {
    deletingLogId.value = log.id
    await deleteSearchLog(log.id)

    if (searchLogs.value.length === 1 && page.value > 1) {
      page.value -= 1
    }

    message.value = '검색 기록을 삭제했습니다. 자동 선호도 다시 계산되었습니다.'
    await fetchLogs()
  } catch (error) {
    message.value = error.response?.data?.detail || '검색 기록을 삭제하지 못했습니다.'
  } finally {
    deletingLogId.value = null
  }
}

const movePage = async (direction) => {
  const nextPage = page.value + direction
  if (nextPage < 1 || nextPage > meta.value.totalPages) return

  page.value = nextPage
  await fetchLogs()
}

onMounted(() => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  fetchLogs()
})
</script>

<template>
  <main class="history-page">
    <section class="history-container">
      <header class="page-title">
        <RouterLink to="/mypage" class="back-link">마이페이지로 돌아가기</RouterLink>
        <p class="eyebrow">SEARCH HISTORY</p>
        <h1>검색 기록 관리</h1>
        <p>최근 검색 기록을 확인하고 삭제할 수 있습니다. 삭제하면 검색 기반 자동 선호가 다시 계산됩니다.</p>
      </header>

      <section class="panel">
        <div class="section-heading-row">
          <div>
            <h2>검색 기록</h2>
            <p>5개씩 표시됩니다.</p>
          </div>
        </div>

        <p v-if="isLoading" class="empty">검색 기록을 불러오는 중입니다.</p>
        <div v-else-if="searchLogs.length" class="history-list">
          <article
            v-for="log in searchLogs"
            :key="log.id"
            class="history-item"
          >
            <div class="history-main">
              <strong>{{ log.query }}</strong>
              <span>{{ getSearchLogMeta(log) }}</span>
              <time>{{ formatSearchLogDate(log.created_at) }}</time>
              <span v-if="getSearchLogChips(log).length" class="chip-row">
                <span v-for="chip in getSearchLogChips(log)" :key="chip" class="chip">
                  {{ chip }}
                </span>
              </span>
            </div>
            <div class="history-actions">
              <button type="button" @click="rerunSearchLog(log)">
                다시 검색
              </button>
              <button
                type="button"
                class="danger"
                :disabled="deletingLogId === log.id"
                @click="handleDeleteSearchLog(log)"
              >
                {{ deletingLogId === log.id ? '삭제 중' : '삭제' }}
              </button>
            </div>
          </article>
        </div>
        <p v-else class="empty">{{ message || '저장된 검색 기록이 없습니다.' }}</p>
        <p v-if="message && searchLogs.length" class="status-message">{{ message }}</p>

        <div class="pager">
          <button type="button" :disabled="page <= 1" @click="movePage(-1)">
            이전
          </button>
          <span>{{ meta.page }} / {{ meta.totalPages }}</span>
          <button type="button" :disabled="page >= meta.totalPages" @click="movePage(1)">
            다음
          </button>
        </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
.history-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.history-container {
  max-width: 920px;
  margin: 0 auto;
  display: grid;
  gap: 14px;
}

.page-title {
  display: grid;
  gap: 6px;
}

.back-link {
  width: fit-content;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  text-decoration: none;
}

.eyebrow {
  margin: 0;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
}

h1,
h2 {
  margin: 0;
  color: #111827;
}

.page-title p,
.section-heading-row p {
  margin: 0;
  color: #667085;
  font-weight: 700;
}

.panel {
  padding: 20px;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.history-list {
  margin-top: 14px;
  display: grid;
  gap: 10px;
}

.history-item {
  padding: 14px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  border-radius: 12px;
  background: #f9fafb;
}

.history-main {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.history-main strong {
  color: #111827;
}

.history-main span,
.history-main time {
  color: #667085;
  font-size: 13px;
  font-weight: 800;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  max-width: 100%;
  padding: 4px 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #e0f2fe;
  color: #075985;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-actions,
.pager {
  display: flex;
  gap: 8px;
  align-items: center;
}

.history-actions button,
.pager button {
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  background: #ffffff;
  color: #344054;
  font-weight: 900;
  cursor: pointer;
}

.history-actions .danger {
  border-color: #fecaca;
  color: #b91c1c;
}

.history-actions button:disabled,
.pager button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.pager {
  margin-top: 14px;
  justify-content: center;
  color: #344054;
  font-weight: 900;
}

.empty,
.status-message {
  margin: 12px 0 0;
  padding: 12px;
  border-radius: 12px;
  background: #f9fafb;
  color: #667085;
  font-weight: 800;
}

.status-message {
  color: #2563eb;
}

@media (max-width: 720px) {
  .history-item {
    grid-template-columns: 1fr;
  }

  .history-actions {
    flex-wrap: wrap;
  }
}
</style>
