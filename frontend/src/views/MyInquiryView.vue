<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { getMyInquiries } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const inquiries = ref([])
const isLoading = ref(false)
const errorMessage = ref('')
const openedInquiryId = ref(null)

const statusLabel = (status) => {
  if (status === 'answered') {
    return '답변완료'
  }

  return '답변대기'
}

const formatBoardDate = (value) => {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()

  if (isToday) {
    return date.toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }

  return date.toLocaleDateString('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  }).replace(/\. /g, '.').replace(/\.$/, '')
}

const toggleInquiry = (inquiryId) => {
  openedInquiryId.value = openedInquiryId.value === inquiryId ? null : inquiryId
}

const fetchInquiries = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  try {
    isLoading.value = true
    errorMessage.value = ''
    const response = await getMyInquiries()
    inquiries.value = response.data
  } catch (error) {
    console.error(error)
    errorMessage.value = error.response?.data?.detail || '문의 내역을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchInquiries)
</script>

<template>
  <main class="page">
    <section class="container">
      <header class="page-title">
        <div>
          <p class="eyebrow">CUSTOMER CENTER</p>
          <h1>내 문의</h1>
        </div>
        <RouterLink to="/inquiries/new" class="write-button">
          문의하기
        </RouterLink>
      </header>

      <p v-if="isLoading" class="status-card">문의 내역을 불러오는 중입니다.</p>
      <p v-else-if="errorMessage" class="status-card error">{{ errorMessage }}</p>

      <section v-else class="inquiry-board">
        <table class="inquiry-table">
          <colgroup>
            <col class="col-number" />
            <col class="col-category" />
            <col class="col-title" />
            <col class="col-author" />
            <col class="col-date" />
            <col class="col-status" />
          </colgroup>

          <thead>
            <tr>
              <th>번호</th>
              <th>말머리</th>
              <th>제목</th>
              <th>글쓴이</th>
              <th>작성일</th>
              <th>상태</th>
            </tr>
          </thead>

          <tbody>
            <template v-for="inquiry in inquiries" :key="inquiry.id">
              <tr
                class="inquiry-row"
                :class="{ opened: openedInquiryId === inquiry.id }"
                tabindex="0"
                @click="toggleInquiry(inquiry.id)"
                @keyup.enter="toggleInquiry(inquiry.id)"
              >
                <td>{{ inquiry.id }}</td>
                <td>
                  <span class="category-label">문의</span>
                </td>
                <td class="title-cell">
                  <button type="button" class="title-button">
                    {{ inquiry.title }}
                  </button>
                </td>
                <td>{{ authStore.user?.nickname || authStore.user?.username || '나' }}</td>
                <td>{{ formatBoardDate(inquiry.created_at) }}</td>
                <td>
                  <span class="status-badge" :class="{ answered: inquiry.status === 'answered' }">
                    {{ statusLabel(inquiry.status) }}
                  </span>
                </td>
              </tr>

              <tr v-if="openedInquiryId === inquiry.id" class="inquiry-detail-row">
                <td colspan="6">
                  <div class="inquiry-detail">
                    <section>
                      <strong>문의 내용</strong>
                      <p>{{ inquiry.content }}</p>
                    </section>

                    <section>
                      <strong>답변 내용</strong>
                      <p>
                        {{ inquiry.status === 'answered' ? (inquiry.admin_reply || '등록된 답변 내용이 없습니다.') : '아직 답변을 기다리고 있습니다.' }}
                      </p>
                    </section>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>

        <p v-if="inquiries.length === 0" class="status-card">
          작성한 문의가 없습니다.
        </p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.container {
  max-width: 1120px;
  margin: 0 auto;
}

.page-title {
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}

.eyebrow {
  margin: 0 0 6px;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

h1,
h2 {
  margin: 0;
  color: #111827;
}

.write-button {
  min-height: 40px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  border-radius: 8px;
  background: #2563eb;
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
}

.inquiry-board,
.status-card {
  border: 1px solid #e5e8f0;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.06);
}

.inquiry-board {
  overflow: hidden;
}

.inquiry-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  color: #111827;
  font-size: 13px;
}

.inquiry-table th,
.inquiry-table td {
  height: 30px;
  padding: 0 8px;
  border-bottom: 1px solid #edf0f4;
  text-align: center;
  vertical-align: middle;
}

.inquiry-table th {
  border-bottom-color: #cfd6e2;
  background: #fbfcfe;
  font-size: 12px;
  font-weight: 900;
}

.inquiry-row {
  cursor: pointer;
}

.inquiry-row:hover,
.inquiry-row:focus-visible,
.inquiry-row.opened {
  background: #f4f7fb;
  outline: none;
}

.inquiry-table tbody tr:last-child td {
  border-bottom: 0;
}

.col-number { width: 70px; }
.col-category { width: 86px; }
.col-author { width: 120px; }
.col-date { width: 90px; }
.col-status { width: 110px; }

.title-cell {
  text-align: left;
}

.title-button {
  width: 100%;
  padding: 0;
  overflow: hidden;
  border: 0;
  background: transparent;
  color: #111827;
  font-size: 13px;
  font-weight: 800;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.inquiry-row:hover .title-button {
  color: #dc2626;
  text-decoration: underline;
}

.category-label {
  color: #2563eb;
  font-weight: 900;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: #fef3c7;
  color: #92400e;
  font-size: 11px;
  font-weight: 900;
}

.status-badge.answered {
  background: #dcfce7;
  color: #166534;
}

.inquiry-detail-row td {
  height: auto;
  padding: 0;
  background: #fbfcfe;
  text-align: left;
}

.inquiry-detail {
  padding: 16px 22px;
  display: grid;
  gap: 12px;
}

.inquiry-detail section {
  display: grid;
  gap: 6px;
}

.inquiry-detail strong {
  color: #111827;
  font-size: 14px;
}

.inquiry-detail p {
  margin: 0;
  color: #344054;
  line-height: 1.7;
  white-space: pre-wrap;
}

.status-card {
  padding: 32px;
  color: #667085;
  font-weight: 800;
  text-align: center;
}

.error {
  color: #ef4444;
}

@media (max-width: 640px) {
  .page {
    padding: 28px 16px;
  }

  .page-title {
    align-items: flex-start;
    flex-direction: column;
  }

  .inquiry-board {
    overflow-x: auto;
  }

  .inquiry-table {
    min-width: 680px;
  }
}
</style>
