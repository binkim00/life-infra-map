<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { createUserNotification, getReports, processReport } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const reports = ref([])
const isLoading = ref(false)
const errorMessage = ref('')
const memoByReport = ref({})
const reporterMessageByReport = ref({})
const reportedUserMessageByReport = ref({})
const penaltyByReport = ref({})

const penaltyOptions = [
  ['warning', '경고만'],
  ['suspend_3_days', '3일 정지'],
  ['suspend_7_days', '7일 정지'],
  ['suspend_30_days', '30일 정지'],
  ['suspend_1_year', '1년 정지'],
  ['permanent_ban', '영구밴'],
]

const formatTargetType = (type) => {
  if (type === 'deleted') return '삭제됨'
  return type === 'post' ? '게시글' : '댓글'
}

const fetchPendingReports = async () => {
  const response = await getReports({ status: 'pending' })
  reports.value = response.data
  memoByReport.value = Object.fromEntries(response.data.map((report) => [report.id, '']))
  reporterMessageByReport.value = Object.fromEntries(response.data.map((report) => [report.id, '']))
  reportedUserMessageByReport.value = Object.fromEntries(response.data.map((report) => [report.id, '']))
  penaltyByReport.value = Object.fromEntries(response.data.map((report) => [report.id, 'warning']))
}

const fetchReports = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  try {
    isLoading.value = true
    errorMessage.value = ''

    await fetchPendingReports()
  } catch (error) {
    console.error(error)

    if (error.response?.status === 403) {
      errorMessage.value = '관리자만 신고 내역을 확인할 수 있습니다.'
      return
    }

    errorMessage.value = '신고 내역을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const handleProcess = async (report, action) => {
  await processReport(report.id, {
    action,
    admin_memo: memoByReport.value[report.id] || '',
    penalty_type: penaltyByReport.value[report.id] || 'warning',
    penalty_reason: memoByReport.value[report.id] || report.reason,
  })
  reports.value = reports.value.filter((item) => item.id !== report.id)
}

const sendReportMessage = async (userId, message) => {
  if (!userId) {
    alert('메시지를 보낼 대상이 없습니다.')
    return
  }

  if (!message.trim()) {
    alert('메시지를 입력해주세요.')
    return
  }

  await createUserNotification(userId, {
    title: '신고 처리 안내',
    message,
  })

  alert('메시지를 보냈습니다.')
}

onMounted(() => {
  fetchReports()
})
</script>

<template>
  <main class="report-page">
    <section class="report-container">
      <header class="report-header">
        <div>
          <p class="eyebrow">ADMIN</p>
          <h1>신고 내역</h1>
        </div>

        <RouterLink to="/boards/free" class="back-button">
          자유게시판
        </RouterLink>
      </header>

      <p v-if="isLoading" class="status-text">
        신고 내역을 불러오는 중입니다.
      </p>

      <p v-else-if="errorMessage" class="error-text">
        {{ errorMessage }}
      </p>

      <section v-else class="report-list">
        <article v-for="report in reports" :key="report.id" class="report-card">
          <div class="report-top">
            <span class="target-badge">
              {{ formatTargetType(report.target_type) }}
            </span>

            <span class="report-date">
              {{ new Date(report.created_at).toLocaleString() }}
            </span>
          </div>

          <h2>{{ report.post_title }}</h2>

          <div class="report-meta">
            <span>신고 #{{ report.id }}</span>
            <span>상태 {{ report.status }}</span>
            <RouterLink :to="`/admin/users/${report.reporter}`" class="user-link">
              신고자 #{{ report.reporter }} {{ report.reporter_username }}
            </RouterLink>
            <RouterLink v-if="report.reported_user_id" :to="`/admin/users/${report.reported_user_id}`" class="user-link">
              신고당한 유저 #{{ report.reported_user_id }} {{ report.reported_username }}
            </RouterLink>
            <span>대상 ID {{ report.target_id }}</span>
          </div>

          <div class="report-block">
            <strong>신고 사유</strong>
            <p>{{ report.reason }}</p>
          </div>

          <div class="report-block">
            <strong>대상 내용</strong>
            <p>{{ report.target_content }}</p>
          </div>

          <RouterLink v-if="report.post_id" :to="`/boards/free/${report.post_id}`" class="detail-link">
            원문 보기
          </RouterLink>

          <div class="process-box">
            <textarea v-model="memoByReport[report.id]" rows="3" placeholder="관리자 메모 또는 조치 사유"></textarea>

            <select v-model="penaltyByReport[report.id]">
              <option v-for="[value, label] in penaltyOptions" :key="value" :value="value">
                {{ label }}
              </option>
            </select>

            <div class="process-actions">
              <button type="button" class="pass-button" @click="handleProcess(report, 'passed')">
                패스
              </button>

              <button type="button" class="penalty-button" @click="handleProcess(report, 'penalized')">
                패널티 조치
              </button>
            </div>
          </div>

          <div class="message-box">
            <div class="message-row">
              <input v-model="reporterMessageByReport[report.id]" type="text" placeholder="신고자에게 보낼 메시지" />
              <button type="button"
                @click="sendReportMessage(report.reporter, reporterMessageByReport[report.id]); reporterMessageByReport[report.id] = ''">
                신고자에게 보내기
              </button>
            </div>

            <div class="message-row">
              <input v-model="reportedUserMessageByReport[report.id]" type="text" placeholder="신고당한 유저에게 보낼 메시지" />
              <button type="button"
                @click="sendReportMessage(report.reported_user_id, reportedUserMessageByReport[report.id]); reportedUserMessageByReport[report.id] = ''">
                신고당한 유저에게 보내기
              </button>
            </div>
          </div>
        </article>

        <p v-if="reports.length === 0" class="empty-text">
          접수된 신고 내역이 없습니다.
        </p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.report-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.report-container {
  max-width: 960px;
  margin: 0 auto;
}

.report-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #f97316;
  font-size: 13px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.report-header h1 {
  margin: 0;
  color: #111827;
  font-size: 32px;
}

.back-button,
.detail-link {
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
}

.back-button {
  border: 1px solid #d0d5dd;
  background: #ffffff;
  color: #344054;
}

.report-list {
  display: grid;
  gap: 14px;
}

.report-card {
  padding: 20px;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.report-top,
.report-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.report-top {
  justify-content: space-between;
  margin-bottom: 12px;
}

.target-badge {
  padding: 5px 9px;
  border-radius: 999px;
  background: #fff7ed;
  color: #f97316;
  font-size: 12px;
  font-weight: 900;
}

.report-date,
.report-meta {
  color: #667085;
  font-size: 13px;
  font-weight: 700;
}

.user-link {
  color: #2563eb;
  font-weight: 900;
  text-decoration: none;
}

.user-link:hover {
  text-decoration: underline;
}

.report-card h2 {
  margin: 0 0 10px;
  color: #111827;
  font-size: 20px;
}

.report-block {
  margin-top: 14px;
  padding: 14px;
  border-radius: 14px;
  background: #f9fafb;
}

.report-block strong {
  display: block;
  margin-bottom: 6px;
  color: #344054;
  font-size: 13px;
}

.report-block p {
  margin: 0;
  color: #111827;
  line-height: 1.6;
  white-space: pre-wrap;
}

.detail-link {
  display: inline-flex;
  margin-top: 14px;
  background: #2563eb;
  color: #ffffff;
}

.process-box {
  margin-top: 14px;
  display: grid;
  gap: 8px;
}

.process-box textarea,
.process-box select {
  width: 100%;
  padding: 12px;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  outline: none;
}

.process-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.process-actions button {
  border: 0;
  border-radius: 999px;
  padding: 10px 14px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
}

.message-box {
  margin-top: 14px;
  display: grid;
  gap: 8px;
}

.message-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.message-row input {
  min-width: 0;
  padding: 12px;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  outline: none;
}

.message-row button {
  border: 0;
  border-radius: 999px;
  background: #2563eb;
  color: #ffffff;
  padding: 10px 14px;
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
}

.pass-button {
  background: #344054;
}

.penalty-button {
  background: #f97316;
}

.status-text,
.empty-text,
.error-text {
  padding: 32px;
  border-radius: 18px;
  background: #ffffff;
  text-align: center;
}

.error-text {
  color: #ef4444;
}

@media (max-width: 720px) {
  .report-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .message-row {
    grid-template-columns: 1fr;
  }
}
</style>
