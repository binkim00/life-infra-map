<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { fetchMyPlaceReports } from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const reports = ref([])
const isLoading = ref(false)
const message = ref('')
const page = ref(1)
const meta = ref({
  count: 0,
  page: 1,
  pageSize: 5,
  totalPages: 1,
})

const statusLabels = {
  pending: '검토 대기',
  approved: '승인',
  rejected: '반려',
}

const reportContributionRewards = {
  tag_suggestion: 10,
  wrong_info: 5,
  edit_place: 5,
  new_place: 20,
}

const getReportContributionMessage = (report) => {
  if (report.status === 'approved') {
    const contribution = reportContributionRewards[report.report_type] || 0
    return contribution
      ? `승인됨 · 기여도 +${contribution} 반영`
      : '승인됨 · 기여도 반영 대상이 아닙니다.'
  }

  if (report.status === 'pending') {
    return '검토 대기 · 승인되면 기여도에 반영됩니다.'
  }

  if (report.status === 'rejected') {
    return '반려됨 · 기여도 반영 없음'
  }

  return ''
}

const fetchReports = async () => {
  try {
    isLoading.value = true
    message.value = ''
    const response = await fetchMyPlaceReports({
      page: page.value,
      pageSize: 5,
    })
    reports.value = response.results || []
    meta.value = {
      count: response.count || 0,
      page: response.page || page.value,
      pageSize: response.page_size || 5,
      totalPages: response.total_pages || 1,
    }

    if (!reports.value.length) {
      message.value = '아직 접수한 장소 제보가 없습니다.'
    }
  } catch (error) {
    reports.value = []
    message.value = '내 제보 현황을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const movePage = async (direction) => {
  const nextPage = page.value + direction
  if (nextPage < 1 || nextPage > meta.value.totalPages) return

  page.value = nextPage
  await fetchReports()
}

const formatDate = (value) => {
  if (!value) return ''
  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(() => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  fetchReports()
})
</script>

<template>
  <main class="reports-page">
    <section class="reports-container">
      <header class="page-title">
        <RouterLink to="/mypage" class="back-link">마이페이지로 돌아가기</RouterLink>
        <p class="eyebrow">MY REPORTS</p>
        <h1>내 제보 현황</h1>
        <p>접수한 장소 정보 제보의 검토 상태를 확인할 수 있습니다.</p>
      </header>

      <section class="panel">
        <div class="section-heading-row">
          <div>
            <h2>제보 목록</h2>
            <p>관리자 검토 전에는 데이터에 반영되지 않습니다.</p>
          </div>
          <RouterLink to="/place-report" class="primary-link">새 제보 작성</RouterLink>
        </div>

        <p v-if="isLoading" class="empty">제보 목록을 불러오는 중입니다.</p>
        <div v-else-if="reports.length" class="report-list">
          <article v-for="report in reports" :key="report.id" class="report-card">
            <div class="report-top">
              <span class="status-badge" :class="report.status">
                {{ report.status_label || statusLabels[report.status] || report.status }}
              </span>
              <time>{{ formatDate(report.created_at) }}</time>
            </div>
            <strong>{{ report.report_type_label }}</strong>
            <p>{{ report.place_name || report.suggested_name || '장소명 없음' }}</p>
            <p class="contribution-note" :class="report.status">
              {{ getReportContributionMessage(report) }}
            </p>
            <div v-if="report.suggested_tags?.length" class="chip-row">
              <span v-for="tag in report.suggested_tags" :key="tag" class="chip">
                {{ tag }}
              </span>
            </div>
            <p v-if="report.admin_note" class="admin-note">{{ report.admin_note }}</p>
          </article>
        </div>
        <p v-else class="empty">{{ message }}</p>

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
.reports-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.reports-container {
  max-width: 920px;
  margin: 0 auto;
  display: grid;
  gap: 14px;
}

.page-title {
  display: grid;
  gap: 6px;
}

.back-link,
.primary-link {
  width: fit-content;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  text-decoration: none;
}

.primary-link {
  min-height: 34px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  border-radius: 8px;
  background: #2563eb;
  color: #ffffff;
}

.eyebrow,
.page-title p,
.section-heading-row p,
.report-card p {
  margin: 0;
}

.eyebrow {
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

.section-heading-row,
.report-top,
.pager {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.report-list {
  margin-top: 14px;
  display: grid;
  gap: 10px;
}

.report-card {
  padding: 14px;
  display: grid;
  gap: 8px;
  border-radius: 12px;
  background: #f9fafb;
}

.status-badge,
.chip {
  width: fit-content;
  padding: 4px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #475569;
  font-size: 12px;
  font-weight: 900;
}

.status-badge.approved {
  background: #dcfce7;
  color: #166534;
}

.status-badge.rejected {
  background: #fee2e2;
  color: #991b1b;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  background: #e0f2fe;
  color: #075985;
}

.admin-note {
  padding: 10px;
  border-radius: 10px;
  background: #ffffff;
  color: #344054;
  font-size: 13px;
  line-height: 1.5;
}

.contribution-note {
  width: fit-content;
  padding: 7px 10px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 12px;
  font-weight: 900;
}

.contribution-note.pending {
  background: #fff7ed;
  color: #9a3412;
}

.contribution-note.approved {
  background: #dcfce7;
  color: #166534;
}

.contribution-note.rejected {
  background: #fee2e2;
  color: #991b1b;
}

.empty {
  margin: 12px 0 0;
  padding: 12px;
  border-radius: 12px;
  background: #f9fafb;
  color: #667085;
  font-weight: 800;
}

.pager {
  margin-top: 14px;
  justify-content: center;
  color: #344054;
  font-weight: 900;
}

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

.pager button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

@media (max-width: 720px) {
  .section-heading-row,
  .report-top {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
