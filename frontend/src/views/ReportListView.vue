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
const openedReportIds = ref(new Set())
const statusFilter = ref('all')

const penaltyOptions = [
  ['warning', '경고만'],
  ['suspend_3_days', '3일 정지'],
  ['suspend_7_days', '7일 정지'],
  ['suspend_30_days', '30일 정지'],
  ['suspend_1_year', '1년 정지'],
  ['permanent_ban', '영구밴'],
]

const reportStatusOptions = [
  { value: 'all', label: '전체' },
  { value: 'pending', label: '대기' },
  { value: 'passed', label: '패스' },
  { value: 'penalized', label: '조치 완료' },
]

const formatTargetType = (type) => {
  if (type === 'deleted') return '삭제됨'
  return type === 'post' ? '게시글' : '댓글'
}

const formatStatus = (status) => {
  if (status === 'passed') return '패스'
  if (status === 'penalized') return '조치 완료'
  return '대기'
}

const formatDateTime = (value) => {
  if (!value) return '-'

  return new Date(value).toLocaleString('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const getUserLabel = (nickname, username, id) => {
  const displayName = nickname || username || `#${id}`
  return username && nickname ? `${displayName} (${username})` : displayName
}

const isReportOpen = (reportId) => openedReportIds.value.has(reportId)

const isReportProcessed = (report) => report?.status && report.status !== 'pending'

const toggleReport = (reportId) => {
  const next = new Set(openedReportIds.value)

  if (next.has(reportId)) {
    next.delete(reportId)
  } else {
    next.add(reportId)
  }

  openedReportIds.value = next
}

const initializeReportState = (reportList) => {
  memoByReport.value = Object.fromEntries(
    reportList.map((report) => [report.id, memoByReport.value[report.id] ?? report.admin_memo ?? '']),
  )
  reporterMessageByReport.value = Object.fromEntries(
    reportList.map((report) => [report.id, reporterMessageByReport.value[report.id] ?? '']),
  )
  reportedUserMessageByReport.value = Object.fromEntries(
    reportList.map((report) => [report.id, reportedUserMessageByReport.value[report.id] ?? '']),
  )
  penaltyByReport.value = Object.fromEntries(
    reportList.map((report) => [report.id, penaltyByReport.value[report.id] ?? 'warning']),
  )
}

const fetchReportList = async () => {
  const response = await getReports({ status: statusFilter.value })
  reports.value = response.data
  initializeReportState(response.data)
}

const fetchReports = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  try {
    isLoading.value = true
    errorMessage.value = ''

    await fetchReportList()
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
  try {
    const response = await processReport(report.id, {
      action,
      admin_memo: memoByReport.value[report.id] || '',
      penalty_type: penaltyByReport.value[report.id] || 'warning',
      penalty_reason: memoByReport.value[report.id] || report.reason,
    })

    const updatedReport = response.data
    reports.value = reports.value.map((item) => (
      item.id === report.id ? { ...item, ...updatedReport } : item
    ))
    memoByReport.value = {
      ...memoByReport.value,
      [report.id]: updatedReport.admin_memo || '',
    }
  } catch (error) {
    console.error(error)
    alert('신고 처리에 실패했습니다.')
  }
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

  try {
    await createUserNotification(userId, {
      title: '신고 처리 안내',
      message,
    })

    alert('메시지를 보냈습니다.')
  } catch (error) {
    console.error(error)
    alert('메시지 전송에 실패했습니다.')
  }
}

onMounted(() => {
  fetchReports()
})
</script>

<template>
  <main class="admin-board-page">
    <section class="admin-board-container">
      <header class="admin-board-header">
        <div>
          <p class="eyebrow">COMMUNITY ADMIN</p>
          <h1>신고 내역</h1>
          <p class="header-description">
            자유게시판에서 접수된 게시글·댓글 신고를 확인하고 처리합니다.
          </p>
        </div>

        <nav class="admin-tabs">
          <RouterLink to="/admin/reports" class="admin-tab">신고 내역</RouterLink>
          <RouterLink to="/admin/place-reports" class="admin-tab">장소 제보</RouterLink>
          <RouterLink to="/admin/users" class="admin-tab">유저 관리</RouterLink>
          <RouterLink to="/admin/inquiries" class="admin-tab">문의 관리</RouterLink>
        </nav>
      </header>

      <section class="report-toolbar">
        <label>
          <span>처리 상태</span>
          <select v-model="statusFilter" :disabled="isLoading" @change="fetchReports">
            <option
              v-for="option in reportStatusOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>

        <button type="button" :disabled="isLoading" @click="fetchReports">
          새로고침
        </button>
      </section>

      <p v-if="isLoading" class="status-text">
        신고 내역을 불러오는 중입니다.
      </p>

      <p v-else-if="errorMessage" class="error-text">
        {{ errorMessage }}
      </p>

      <section v-else class="admin-table-wrap">
        <table class="admin-table report-table">
          <colgroup>
            <col class="col-number" />
            <col class="col-type" />
            <col class="col-title" />
            <col class="col-user" />
            <col class="col-user" />
            <col class="col-date" />
            <col class="col-status" />
            <col class="col-action" />
          </colgroup>

          <thead>
            <tr>
              <th>번호</th>
              <th>대상</th>
              <th>신고 내용</th>
              <th>신고자</th>
              <th>신고당한 유저</th>
              <th>접수일</th>
              <th>상태</th>
              <th>관리</th>
            </tr>
          </thead>

          <tbody>
            <template v-for="report in reports" :key="report.id">
              <tr :class="{ opened: isReportOpen(report.id) }">
                <td class="number-cell">{{ report.id }}</td>
                <td>
                  <span class="category-label report-target">
                    {{ formatTargetType(report.target_type) }}
                  </span>
                </td>
                <td class="title-cell">
                  <button type="button" class="title-button" @click="toggleReport(report.id)">
                    <span class="title-text">
                      {{ report.post_title || '삭제되었거나 제목 없음' }}
                    </span>
                    <span class="reason-preview">{{ report.reason }}</span>
                  </button>
                </td>
                <td>
                  <RouterLink :to="`/admin/users/${report.reporter}`" class="user-link">
                    {{ getUserLabel(report.reporter_nickname, report.reporter_username, report.reporter) }}
                  </RouterLink>
                </td>
                <td>
                  <RouterLink
                    v-if="report.reported_user_id"
                    :to="`/admin/users/${report.reported_user_id}`"
                    class="user-link danger"
                  >
                    {{ getUserLabel(report.reported_nickname, report.reported_username, report.reported_user_id) }}
                  </RouterLink>
                  <span v-else class="muted-text">-</span>
                </td>
                <td>{{ formatDateTime(report.created_at) }}</td>
                <td>
                  <span :class="['status-badge', report.status || 'pending']">
                    {{ formatStatus(report.status) }}
                  </span>
                </td>
                <td>
                  <button type="button" class="row-action" @click="toggleReport(report.id)">
                    {{ isReportOpen(report.id) ? '닫기' : (isReportProcessed(report) ? '보기' : '처리') }}
                  </button>
                </td>
              </tr>

              <tr v-if="isReportOpen(report.id)" class="detail-row">
                <td colspan="8">
                  <div class="detail-panel">
                    <div class="detail-grid">
                      <section class="detail-box">
                        <strong>신고 사유</strong>
                        <p>{{ report.reason }}</p>
                      </section>

                      <section class="detail-box">
                        <strong>대상 내용</strong>
                        <p>{{ report.target_content || '대상 내용이 없습니다.' }}</p>
                      </section>
                    </div>

                    <RouterLink v-if="report.post_id" :to="`/boards/free/${report.post_id}`" class="detail-link">
                      원문 보기
                    </RouterLink>

                    <section v-if="isReportProcessed(report)" class="process-panel process-panel-readonly">
                      <h3>처리 내역</h3>
                      <dl class="process-summary-list">
                        <div>
                          <dt>상태</dt>
                          <dd>{{ formatStatus(report.status) }}</dd>
                        </div>
                        <div>
                          <dt>처리자</dt>
                          <dd>{{ report.processed_by_username || '-' }}</dd>
                        </div>
                        <div>
                          <dt>처리일</dt>
                          <dd>{{ formatDateTime(report.processed_at) }}</dd>
                        </div>
                      </dl>
                      <p v-if="report.admin_memo" class="process-memo">
                        {{ report.admin_memo }}
                      </p>
                    </section>

                    <section v-else class="process-panel">
                      <h3>신고 처리</h3>
                      <textarea v-model="memoByReport[report.id]" rows="3" placeholder="관리자 메모 또는 조치 사유"></textarea>

                      <div class="process-controls">
                        <select v-model="penaltyByReport[report.id]">
                          <option v-for="[value, label] in penaltyOptions" :key="value" :value="value">
                            {{ label }}
                          </option>
                        </select>

                        <button type="button" class="pass-button" @click="handleProcess(report, 'passed')">
                          패스
                        </button>

                        <button type="button" class="penalty-button" @click="handleProcess(report, 'penalized')">
                          패널티 조치
                        </button>
                      </div>
                    </section>

                    <section class="message-panel">
                      <h3>관리자 메시지</h3>

                      <div class="message-row">
                        <input v-model="reporterMessageByReport[report.id]" type="text" placeholder="신고자에게 보낼 메시지" />
                        <button
                          type="button"
                          @click="sendReportMessage(report.reporter, reporterMessageByReport[report.id]); reporterMessageByReport[report.id] = ''"
                        >
                          신고자에게 보내기
                        </button>
                      </div>

                      <div class="message-row">
                        <input v-model="reportedUserMessageByReport[report.id]" type="text" placeholder="신고당한 유저에게 보낼 메시지" />
                        <button
                          type="button"
                          @click="sendReportMessage(report.reported_user_id, reportedUserMessageByReport[report.id]); reportedUserMessageByReport[report.id] = ''"
                        >
                          신고당한 유저에게 보내기
                        </button>
                      </div>
                    </section>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>

        <p v-if="reports.length === 0" class="empty-text">
          {{ statusFilter === 'pending' ? '접수된 신고 내역이 없습니다.' : '표시할 신고 내역이 없습니다.' }}
        </p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.admin-board-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #fff8ed;
}

.admin-board-container {
  max-width: 1180px;
  margin: 0 auto;
}

.admin-board-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-end;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #f59e0b;
  font-size: 13px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.admin-board-header h1 {
  margin: 0;
  color: #111827;
  font-size: 32px;
}

.header-description {
  margin: 8px 0 0;
  color: #667085;
  font-size: 14px;
  line-height: 1.5;
}

.admin-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.admin-tab {
  padding: 10px 14px;
  border: 1px solid #d0d5dd;
  border-radius: 999px;
  background: #ffffff;
  color: #344054;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
}

.admin-tab.router-link-active {
  border-color: #f59e0b;
  background: #fff7ed;
  color: #f59e0b;
}

.report-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  align-items: end;
  margin-bottom: 14px;
}

.report-toolbar label {
  display: grid;
  gap: 6px;
  color: #667085;
  font-size: 12px;
  font-weight: 900;
}

.report-toolbar select,
.report-toolbar button {
  min-height: 40px;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  background: #ffffff;
  color: #344054;
  padding: 0 12px;
  font: inherit;
  font-weight: 900;
}

.report-toolbar button {
  border-color: #f59e0b;
  color: #f59e0b;
  cursor: pointer;
}

.admin-table-wrap {
  overflow: hidden;
  border: 1px solid #eadcc5;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(146, 64, 14, 0.08);
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.admin-table th,
.admin-table td {
  padding: 14px 12px;
  border-bottom: 1px solid #f3e7d3;
  color: #344054;
  font-size: 14px;
  vertical-align: middle;
}

.admin-table th {
  background: #ffffff;
  color: #667085;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.04em;
  text-align: left;
}

.admin-table tbody tr:hover:not(.detail-row) {
  background: #fffbeb;
}

.admin-table tbody tr.opened {
  background: #fff7ed;
}

.col-number { width: 70px; }
.col-type { width: 90px; }
.col-title { width: auto; }
.col-user { width: 160px; }
.col-date { width: 140px; }
.col-status { width: 90px; }
.col-action { width: 80px; }

.number-cell {
  color: #98a2b3;
  font-size: 13px;
  font-weight: 900;
  text-align: center;
}

.category-label,
.status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 900;
  white-space: nowrap;
}

.report-target {
  background: #fff7ed;
  color: #f59e0b;
}

.status-badge.pending {
  background: #fff7ed;
  color: #f97316;
}

.status-badge.passed {
  background: #ecfdf3;
  color: #027a48;
}

.status-badge.penalized {
  background: #fef3f2;
  color: #b42318;
}

.title-cell {
  min-width: 0;
}

.title-button {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.title-text {
  overflow: hidden;
  color: #111827;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reason-preview {
  overflow: hidden;
  color: #667085;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-link {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  color: #f59e0b;
  font-weight: 900;
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-link.danger {
  color: #ef4444;
}

.user-link:hover {
  text-decoration: underline;
}

.muted-text {
  color: #98a2b3;
}

.row-action {
  border: 0;
  border-radius: 999px;
  background: #f59e0b;
  color: #ffffff;
  padding: 8px 11px;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
}

.detail-row td {
  padding: 0;
  background: #fffbeb;
}

.detail-panel {
  display: grid;
  gap: 14px;
  padding: 20px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-box {
  padding: 14px;
  border: 1px solid #eadcc5;
  border-radius: 14px;
  background: #ffffff;
}

.detail-box strong,
.process-panel h3,
.message-panel h3 {
  display: block;
  margin: 0 0 8px;
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

.detail-box p {
  margin: 0;
  color: #111827;
  line-height: 1.6;
  white-space: pre-wrap;
}

.detail-link {
  justify-self: start;
  padding: 10px 14px;
  border-radius: 999px;
  background: #f59e0b;
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
}

.process-panel,
.message-panel {
  padding: 16px;
  border: 1px solid #eadcc5;
  border-radius: 16px;
  background: #ffffff;
}

.process-panel-readonly {
  background: #f9fafb;
}

.process-summary-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.process-summary-list div {
  display: grid;
  gap: 4px;
}

.process-summary-list dt {
  color: #98a2b3;
  font-size: 12px;
  font-weight: 900;
}

.process-summary-list dd {
  margin: 0;
  color: #344054;
  font-weight: 900;
}

.process-memo {
  margin: 12px 0 0;
  color: #344054;
  line-height: 1.6;
  white-space: pre-wrap;
}

.process-panel textarea,
.process-panel select,
.message-row input {
  width: 100%;
  min-width: 0;
  padding: 12px;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  outline: none;
}

.process-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.process-controls select {
  width: 180px;
}

.process-controls button,
.message-row button {
  border: 0;
  border-radius: 999px;
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

.message-panel {
  display: grid;
  gap: 8px;
}

.message-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.message-row button {
  background: #f59e0b;
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

@media (max-width: 920px) {
  .admin-board-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .admin-tabs {
    justify-content: flex-start;
  }

  .admin-table-wrap {
    overflow-x: auto;
  }

  .admin-table {
    min-width: 920px;
  }

  .detail-grid,
  .message-row,
  .process-summary-list {
    grid-template-columns: 1fr;
  }
}
</style>
