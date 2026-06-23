<script setup>
import { onMounted, ref } from 'vue'
import {
  approvePlaceReport,
  fetchAdminPlaceReportDetail,
  fetchAdminPlaceReports,
  rejectPlaceReport,
} from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

const reports = ref([])
const selectedReport = ref(null)
const statusFilter = ref('pending')
const typeFilter = ref('')
const adminNote = ref('')
const message = ref('')
const isLoading = ref(false)
const isDetailLoading = ref(false)
const isReviewing = ref(false)
const page = ref(1)
const meta = ref({
  page: 1,
  pageSize: 10,
  totalPages: 1,
  count: 0,
})

const statusOptions = [
  { value: 'pending', label: '검토 대기' },
  { value: 'approved', label: '승인' },
  { value: 'rejected', label: '반려' },
  { value: '', label: '전체' },
]

const typeOptions = [
  { value: '', label: '전체 유형' },
  { value: 'new_place', label: '장소 추가' },
  { value: 'edit_place', label: '장소 수정' },
  { value: 'tag_suggestion', label: '태그 제안' },
  { value: 'wrong_info', label: '오류 제보' },
]

const fetchReports = async () => {
  try {
    isLoading.value = true
    const response = await fetchAdminPlaceReports({
      status: statusFilter.value,
      reportType: typeFilter.value,
      page: page.value,
      pageSize: 10,
    })
    reports.value = response.results || []
    meta.value = {
      count: response.count || 0,
      page: response.page || page.value,
      pageSize: response.page_size || 10,
      totalPages: response.total_pages || 1,
    }
  } catch (error) {
    reports.value = []
    message.value = '관리자 제보 목록을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const fetchDetail = async (reportId) => {
  try {
    isDetailLoading.value = true
    selectedReport.value = await fetchAdminPlaceReportDetail(reportId)
    adminNote.value = selectedReport.value.admin_note || ''
  } catch (error) {
    message.value = '제보 상세를 불러오지 못했습니다.'
  } finally {
    isDetailLoading.value = false
  }
}

const applyFilters = () => {
  page.value = 1
  selectedReport.value = null
  fetchReports()
}

const movePage = async (direction) => {
  const nextPage = page.value + direction
  if (nextPage < 1 || nextPage > meta.value.totalPages) return

  page.value = nextPage
  await fetchReports()
}

const reviewReport = async (action) => {
  if (!selectedReport.value) return

  try {
    isReviewing.value = true
    const payload = {
      admin_note: adminNote.value,
    }
    const response = action === 'approve'
      ? await approvePlaceReport(selectedReport.value.id, payload)
      : await rejectPlaceReport(selectedReport.value.id, payload)

    selectedReport.value = response.report
    message.value = action === 'approve' ? '제보를 승인했습니다.' : '제보를 반려했습니다.'
    await fetchReports()
  } catch (error) {
    message.value = error.response?.data?.detail || '제보 처리에 실패했습니다.'
  } finally {
    isReviewing.value = false
  }
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
  if (!authStore.user?.is_staff) {
    router.push('/')
    return
  }

  fetchReports()
})
</script>

<template>
  <main class="admin-report-page">
    <section class="admin-report-container">
      <header class="page-title">
        <p class="eyebrow">ADMIN</p>
        <h1>장소 제보 검증</h1>
        <p>사용자 제보를 검토하고 승인 또는 반려할 수 있습니다.</p>
      </header>

      <section class="panel filter-panel">
        <select v-model="statusFilter" @change="applyFilters">
          <option v-for="option in statusOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <select v-model="typeFilter" @change="applyFilters">
          <option v-for="option in typeOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </section>

      <div class="workspace">
        <section class="panel">
          <h2>제보 목록</h2>
          <p v-if="isLoading" class="empty">제보 목록을 불러오는 중입니다.</p>
          <div v-else-if="reports.length" class="report-list">
            <button
              v-for="report in reports"
              :key="report.id"
              type="button"
              class="report-row"
              :class="{ active: selectedReport?.id === report.id }"
              @click="fetchDetail(report.id)"
            >
              <span class="status-badge" :class="report.status">
                {{ report.status_label || report.status }}
              </span>
              <strong>{{ report.report_type_label }}</strong>
              <span>{{ report.place_name || report.suggested_name || '장소명 없음' }}</span>
              <time>{{ formatDate(report.created_at) }}</time>
            </button>
          </div>
          <p v-else class="empty">표시할 제보가 없습니다.</p>

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

        <section class="panel detail-panel">
          <h2>상세 검토</h2>
          <p v-if="isDetailLoading" class="empty">상세를 불러오는 중입니다.</p>
          <div v-else-if="selectedReport" class="detail-body">
            <div class="detail-grid">
              <span>제보자</span><strong>{{ selectedReport.user_username }}</strong>
              <span>상태</span><strong>{{ selectedReport.status_label }}</strong>
              <span>제보 유형</span><strong>{{ selectedReport.report_type_label }}</strong>
              <span>장소</span><strong>{{ selectedReport.place_name || selectedReport.suggested_name || '장소명 없음' }}</strong>
              <span>주소</span><strong>{{ selectedReport.suggested_address || '-' }}</strong>
              <span>좌표</span><strong>{{ selectedReport.suggested_lat || '-' }}, {{ selectedReport.suggested_lng || '-' }}</strong>
            </div>

            <div v-if="selectedReport.suggested_tags?.length" class="chip-row">
              <span v-for="tag in selectedReport.suggested_tags" :key="tag" class="chip">
                {{ tag }}
              </span>
            </div>

            <div class="report-block">
              <strong>설명</strong>
              <p>{{ selectedReport.description || '설명 없음' }}</p>
            </div>

            <div v-if="selectedReport.images?.length" class="image-grid">
              <a
                v-for="image in selectedReport.images"
                :key="image.id"
                :href="image.image_url"
                target="_blank"
                rel="noreferrer"
              >
                <img :src="image.image_url" :alt="image.original_name" />
              </a>
            </div>

            <label>
              <span>관리자 메모</span>
              <textarea v-model="adminNote" rows="4" placeholder="승인/반려 사유 또는 처리 메모"></textarea>
            </label>

            <p v-if="message" class="status-message">{{ message }}</p>

            <div class="review-actions">
              <button
                type="button"
                class="approve"
                :disabled="isReviewing"
                @click="reviewReport('approve')"
              >
                승인
              </button>
              <button
                type="button"
                class="reject"
                :disabled="isReviewing"
                @click="reviewReport('reject')"
              >
                반려
              </button>
            </div>
          </div>
          <p v-else class="empty">검토할 제보를 선택해 주세요.</p>
        </section>
      </div>
    </section>
  </main>
</template>

<style scoped>
.admin-report-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.admin-report-container {
  max-width: 1180px;
  margin: 0 auto;
  display: grid;
  gap: 14px;
}

.eyebrow,
.page-title p {
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

.page-title p {
  color: #667085;
  font-weight: 700;
}

.panel {
  padding: 18px;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.filter-panel {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

select,
textarea {
  padding: 10px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 10px;
  font: inherit;
}

textarea {
  width: 100%;
  resize: vertical;
}

.workspace {
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.report-list,
.detail-body {
  margin-top: 12px;
  display: grid;
  gap: 10px;
}

.report-row {
  width: 100%;
  padding: 12px;
  display: grid;
  gap: 5px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: #f9fafb;
  color: #111827;
  text-align: left;
  cursor: pointer;
}

.report-row.active,
.report-row:hover {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.report-row span,
.report-row time {
  color: #667085;
  font-size: 13px;
  font-weight: 800;
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

.detail-grid {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr);
  gap: 8px;
}

.detail-grid span {
  color: #667085;
  font-size: 13px;
  font-weight: 900;
}

.chip-row,
.review-actions,
.pager {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.chip {
  background: #e0f2fe;
  color: #075985;
}

.report-block {
  padding: 12px;
  border-radius: 12px;
  background: #f9fafb;
}

.report-block p {
  margin: 6px 0 0;
  color: #344054;
  line-height: 1.6;
  white-space: pre-wrap;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}

.image-grid img {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: 10px;
  object-fit: cover;
}

label {
  display: grid;
  gap: 6px;
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

.review-actions button,
.pager button {
  min-height: 34px;
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  color: #ffffff;
  font-weight: 900;
  cursor: pointer;
}

.review-actions .approve {
  background: #16a34a;
}

.review-actions .reject {
  background: #dc2626;
}

.pager {
  margin-top: 12px;
  justify-content: center;
  color: #344054;
  font-weight: 900;
}

.pager button {
  border: 1px solid #d0d5dd;
  background: #ffffff;
  color: #344054;
}

button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
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

@media (max-width: 920px) {
  .workspace {
    grid-template-columns: 1fr;
  }
}
</style>
