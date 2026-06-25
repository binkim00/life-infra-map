<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { getAdminInquiries, updateAdminInquiry } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const inquiries = ref([])
const replies = ref({})
const errorMessage = ref('')
const isLoading = ref(false)
const openedUserKeys = ref(new Set())

const fetchInquiries = async () => {
  if (authStore.isLoggedIn && !authStore.user?.is_staff) {
    await authStore.fetchMe()
  }

  if (!authStore.user?.is_staff) {
    router.push('/')
    return
  }

  try {
    isLoading.value = true
    errorMessage.value = ''

    const response = await getAdminInquiries()
    inquiries.value = response.data
    replies.value = Object.fromEntries(response.data.map((item) => [item.id, item.admin_reply || '']))
  } catch (error) {
    console.error(error)
    errorMessage.value = '문의 목록을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const submitReply = async (inquiry) => {
  if (!replies.value[inquiry.id]?.trim()) {
    alert('답변 내용을 입력해주세요.')
    return
  }

  try {
    const response = await updateAdminInquiry(inquiry.id, {
      status: 'answered',
      admin_reply: replies.value[inquiry.id],
    })
    Object.assign(inquiry, response.data)
  } catch (error) {
    console.error(error)
    alert('답변 저장에 실패했습니다.')
  }
}

const getAuthorKey = (inquiry) => {
  return String(inquiry.author || inquiry.author_username || inquiry.author_nickname || `guest-${inquiry.id}`)
}

const getAuthorLabel = (inquiry) => {
  const nickname = inquiry.author_nickname
  const username = inquiry.author_username

  if (nickname && username) return `${nickname} (${username})`
  return nickname || username || '-'
}

const inquiryGroups = computed(() => {
  const groupMap = new Map()

  inquiries.value.forEach((inquiry) => {
    const key = getAuthorKey(inquiry)

    if (!groupMap.has(key)) {
      groupMap.set(key, {
        key,
        authorLabel: getAuthorLabel(inquiry),
        inquiries: [],
      })
    }

    groupMap.get(key).inquiries.push(inquiry)
  })

  return Array.from(groupMap.values())
    .map((group) => {
      const sortedInquiries = [...group.inquiries].sort((a, b) => {
        return new Date(b.created_at || 0) - new Date(a.created_at || 0)
      })

      const pendingCount = sortedInquiries.filter((item) => item.status === 'pending').length
      const answeredCount = sortedInquiries.filter((item) => item.status === 'answered').length
      const closedCount = sortedInquiries.filter((item) => item.status === 'closed').length

      return {
        ...group,
        inquiries: sortedInquiries,
        latestInquiry: sortedInquiries[0],
        pendingCount,
        answeredCount,
        closedCount,
        totalCount: sortedInquiries.length,
      }
    })
    .sort((a, b) => {
      return new Date(b.latestInquiry?.created_at || 0) - new Date(a.latestInquiry?.created_at || 0)
    })
})

const toggleUserGroup = (userKey) => {
  const next = new Set(openedUserKeys.value)

  if (next.has(userKey)) {
    next.delete(userKey)
  } else {
    next.add(userKey)
  }

  openedUserKeys.value = next
}

const isUserGroupOpen = (userKey) => openedUserKeys.value.has(userKey)

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

const formatStatus = (status) => {
  if (status === 'answered') return '답변 완료'
  if (status === 'closed') return '종료'
  return '대기'
}

const getStatusClass = (status) => {
  if (status === 'answered') return 'answered'
  if (status === 'closed') return 'closed'
  return 'pending'
}

const getGroupStatusText = (group) => {
  if (group.pendingCount > 0) return `대기 ${group.pendingCount}건`
  if (group.closedCount === group.totalCount) return '전체 종료'
  return '전체 답변 완료'
}

const getGroupStatusClass = (group) => {
  if (group.pendingCount > 0) return 'pending'
  if (group.closedCount === group.totalCount) return 'closed'
  return 'answered'
}

onMounted(fetchInquiries)
</script>

<template>
  <main class="admin-board-page">
    <section class="admin-board-container">
      <header class="admin-board-header">
        <div>
          <p class="eyebrow">COMMUNITY ADMIN</p>
          <h1>문의 관리</h1>
          <p class="header-description">
            같은 사용자의 문의를 하나의 칸에 묶어서 확인하고 답변을 관리합니다.
          </p>
        </div>

        <nav class="admin-tabs">
          <RouterLink to="/admin/reports" class="admin-tab">신고 내역</RouterLink>
          <RouterLink to="/admin/place-reports" class="admin-tab">장소 제보</RouterLink>
          <RouterLink to="/admin/users" class="admin-tab">유저 관리</RouterLink>
          <RouterLink to="/admin/inquiries" class="admin-tab">문의 관리</RouterLink>
        </nav>
      </header>

      <p v-if="isLoading" class="status-text">
        문의 목록을 불러오는 중입니다.
      </p>

      <p v-else-if="errorMessage" class="error-text">
        {{ errorMessage }}
      </p>

      <section v-else class="admin-table-wrap">
        <table class="admin-table inquiry-table">
          <colgroup>
            <col class="col-number" />
            <col class="col-status" />
            <col class="col-user" />
            <col class="col-title" />
            <col class="col-count" />
            <col class="col-date" />
            <col class="col-action" />
          </colgroup>

          <thead>
            <tr>
              <th>번호</th>
              <th>상태</th>
              <th>사용자</th>
              <th>최근 문의</th>
              <th>문의 수</th>
              <th>최근 문의일</th>
              <th>관리</th>
            </tr>
          </thead>

          <tbody>
            <template v-for="(group, index) in inquiryGroups" :key="group.key">
              <tr :class="{ opened: isUserGroupOpen(group.key) }">
                <td class="number-cell">{{ index + 1 }}</td>
                <td>
                  <span class="status-badge" :class="getGroupStatusClass(group)">
                    {{ getGroupStatusText(group) }}
                  </span>
                </td>
                <td class="author-cell">{{ group.authorLabel }}</td>
                <td class="title-cell">
                  <button type="button" class="title-button" @click="toggleUserGroup(group.key)">
                    <span class="title-text">{{ group.latestInquiry?.title || '-' }}</span>
                    <span class="content-preview">{{ group.latestInquiry?.content || '-' }}</span>
                  </button>
                </td>
                <td>
                  <div class="count-stack">
                    <span class="count-chip">전체 {{ group.totalCount }}</span>
                    <span v-if="group.pendingCount" class="count-chip pending-count">대기 {{ group.pendingCount }}</span>
                  </div>
                </td>
                <td>{{ formatDateTime(group.latestInquiry?.created_at) }}</td>
                <td>
                  <button type="button" class="row-action" @click="toggleUserGroup(group.key)">
                    {{ isUserGroupOpen(group.key) ? '닫기' : '확인' }}
                  </button>
                </td>
              </tr>

              <tr v-if="isUserGroupOpen(group.key)" class="detail-row">
                <td colspan="7">
                  <div class="detail-panel">
                    <section class="user-summary-box">
                      <div>
                        <strong>{{ group.authorLabel }}</strong>
                        <p>
                          전체 문의 {{ group.totalCount }}건 · 대기 {{ group.pendingCount }}건 · 답변 완료 {{ group.answeredCount }}건 · 종료 {{ group.closedCount }}건
                        </p>
                      </div>
                    </section>

                    <article v-for="inquiry in group.inquiries" :key="inquiry.id" class="inquiry-card">
                      <header class="inquiry-card-header">
                        <div class="inquiry-title-area">
                          <span class="status-badge" :class="getStatusClass(inquiry.status)">
                            {{ formatStatus(inquiry.status) }}
                          </span>
                          <strong>#{{ inquiry.id }} {{ inquiry.title }}</strong>
                        </div>
                        <span class="inquiry-date">{{ formatDateTime(inquiry.created_at) }}</span>
                      </header>

                      <section class="detail-box">
                        <strong>문의 내용</strong>
                        <p>{{ inquiry.content }}</p>
                      </section>

                      <section v-if="inquiry.status === 'answered' || inquiry.status === 'closed'" class="reply-box">
                        <strong>관리자 답변</strong>
                        <p>{{ inquiry.admin_reply || '등록된 답변이 없습니다.' }}</p>
                      </section>

                      <section v-else class="reply-form-box">
                        <h3>답변 작성</h3>
                        <textarea v-model="replies[inquiry.id]" rows="4" placeholder="관리자 답변"></textarea>
                        <button type="button" @click="submitReply(inquiry)">답변 저장</button>
                      </section>
                    </article>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>

        <p v-if="inquiries.length === 0" class="empty-text">
          등록된 문의가 없습니다.
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
.col-status { width: 120px; }
.col-user { width: 170px; }
.col-title { width: auto; }
.col-count { width: 120px; }
.col-date { width: 140px; }
.col-action { width: 80px; }

.number-cell {
  color: #98a2b3;
  font-size: 13px;
  font-weight: 900;
  text-align: center;
}

.status-badge,
.count-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 900;
  white-space: nowrap;
}

.status-badge.pending {
  background: #fff7ed;
  color: #f97316;
}

.status-badge.answered {
  background: #ecfdf3;
  color: #039855;
}

.status-badge.closed {
  background: #f2f4f7;
  color: #667085;
}

.count-stack {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.count-chip {
  background: #fff7ed;
  color: #f59e0b;
}

.pending-count {
  background: #fff7ed;
  color: #f97316;
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

.content-preview {
  overflow: hidden;
  color: #667085;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.author-cell {
  overflow: hidden;
  color: #111827;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.user-summary-box,
.inquiry-card,
.detail-box,
.reply-box,
.reply-form-box {
  padding: 16px;
  border: 1px solid #eadcc5;
  border-radius: 16px;
  background: #ffffff;
}

.user-summary-box {
  background: #fffbeb;
}

.user-summary-box strong {
  display: block;
  color: #111827;
  font-size: 15px;
  font-weight: 900;
}

.user-summary-box p {
  margin: 6px 0 0;
  color: #667085;
  font-size: 13px;
  font-weight: 800;
}

.inquiry-card {
  display: grid;
  gap: 12px;
}

.inquiry-card-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.inquiry-title-area {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.inquiry-title-area strong {
  overflow: hidden;
  color: #111827;
  font-size: 15px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inquiry-date {
  flex: 0 0 auto;
  color: #98a2b3;
  font-size: 12px;
  font-weight: 800;
}

.detail-box strong,
.reply-box strong,
.reply-form-box h3 {
  display: block;
  margin: 0 0 8px;
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

.detail-box p,
.reply-box p {
  margin: 0;
  color: #111827;
  line-height: 1.6;
  white-space: pre-wrap;
}

.reply-box {
  background: #fff7ed;
  color: #b45309;
}

.reply-box p {
  margin-top: 6px;
  color: #344054;
}

.reply-form-box textarea {
  width: 100%;
  padding: 14px;
  border: 1px solid #d0d5dd;
  border-radius: 14px;
  outline: none;
}

.reply-form-box button {
  margin-top: 10px;
  border: 0;
  border-radius: 999px;
  background: #f59e0b;
  color: #ffffff;
  padding: 10px 14px;
  font-weight: 900;
  cursor: pointer;
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
}
</style>
