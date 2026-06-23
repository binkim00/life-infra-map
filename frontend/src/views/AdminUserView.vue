<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { createUserNotification, createUserPenalty, getAdminUsers } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const users = ref([])
const reasonByUser = ref({})
const messageByUser = ref({})
const errorMessage = ref('')
const isLoading = ref(false)
const openedUserIds = ref(new Set())

const penalties = [
  ['suspend_3_days', '3일 활동정지'],
  ['suspend_7_days', '7일 활동정지'],
  ['suspend_30_days', '30일 활동정지'],
  ['suspend_1_year', '1년 사용정지'],
  ['permanent_ban', '영구밴'],
]

const formatUserName = (user) => {
  if (!user) return '-'
  const displayName = user.nickname || user.username || `#${user.id}`
  return user.nickname ? `${displayName} (${user.username})` : displayName
}

const formatPenalty = (penalty) => {
  if (!penalty) return '정상'

  const labels = {
    warning: '경고',
    suspend_3_days: '3일 정지',
    suspend_7_days: '7일 정지',
    suspend_30_days: '30일 정지',
    suspend_1_year: '1년 정지',
    permanent_ban: '영구밴',
  }

  return labels[penalty.penalty_type] || penalty.penalty_type
}

const isUserOpen = (userId) => openedUserIds.value.has(userId)

const toggleUser = (userId) => {
  const next = new Set(openedUserIds.value)

  if (next.has(userId)) {
    next.delete(userId)
  } else {
    next.add(userId)
  }

  openedUserIds.value = next
}

const fetchUsers = async () => {
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

    const response = await getAdminUsers()
    users.value = response.data
  } catch (error) {
    console.error(error)
    errorMessage.value = '유저 목록을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const applyPenalty = async (user, penaltyType) => {
  const reason = reasonByUser.value[user.id]?.trim()
  if (!reason) {
    alert('조치 사유를 입력해주세요.')
    return
  }

  try {
    await createUserPenalty(user.id, { penalty_type: penaltyType, reason })
    reasonByUser.value[user.id] = ''
    await fetchUsers()
  } catch (error) {
    console.error(error)
    alert('제재 처리에 실패했습니다.')
  }
}

const sendMessage = async (user) => {
  const message = messageByUser.value[user.id]?.trim()
  if (!message) {
    alert('메시지를 입력해주세요.')
    return
  }

  try {
    await createUserNotification(user.id, {
      title: '관리자 메시지',
      message,
    })
    messageByUser.value[user.id] = ''
    alert('메시지를 보냈습니다.')
  } catch (error) {
    console.error(error)
    alert('메시지 전송에 실패했습니다.')
  }
}

onMounted(fetchUsers)
</script>

<template>
  <main class="admin-board-page">
    <section class="admin-board-container">
      <header class="admin-board-header">
        <div>
          <p class="eyebrow">COMMUNITY ADMIN</p>
          <h1>유저 관리</h1>
          <p class="header-description">
            신고 누적 수와 활동 내역을 기준으로 유저를 확인하고 조치합니다.
          </p>
        </div>

        <nav class="admin-tabs">
          <RouterLink to="/admin/reports" class="admin-tab">신고 내역</RouterLink>
          <RouterLink to="/admin/users" class="admin-tab">유저 관리</RouterLink>
          <RouterLink to="/admin/inquiries" class="admin-tab">문의 관리</RouterLink>
        </nav>
      </header>

      <p v-if="isLoading" class="status-text">
        유저 목록을 불러오는 중입니다.
      </p>

      <p v-else-if="errorMessage" class="error-text">
        {{ errorMessage }}
      </p>

      <section v-else class="admin-table-wrap">
        <table class="admin-table user-table">
          <colgroup>
            <col class="col-number" />
            <col class="col-user-main" />
            <col class="col-email" />
            <col class="col-count" />
            <col class="col-count" />
            <col class="col-count" />
            <col class="col-status" />
            <col class="col-action" />
          </colgroup>

          <thead>
            <tr>
              <th>ID</th>
              <th>유저</th>
              <th>이메일</th>
              <th>신고</th>
              <th>글</th>
              <th>댓글</th>
              <th>상태</th>
              <th>관리</th>
            </tr>
          </thead>

          <tbody>
            <template v-for="user in users" :key="user.id">
              <tr :class="{ opened: isUserOpen(user.id) }">
                <td class="number-cell">{{ user.id }}</td>
                <td class="user-main-cell">
                  <RouterLink :to="`/admin/users/${user.id}`" class="user-link">
                    {{ formatUserName(user) }}
                  </RouterLink>
                </td>
                <td class="email-cell">{{ user.email || '-' }}</td>
                <td>
                  <span class="count-chip danger">{{ user.received_reports_count }}</span>
                </td>
                <td>
                  <span class="count-chip">{{ user.posts_count }}</span>
                </td>
                <td>
                  <span class="count-chip">{{ user.comments_count }}</span>
                </td>
                <td>
                  <span class="status-badge" :class="{ normal: !user.current_penalty, blocked: user.current_penalty }">
                    {{ formatPenalty(user.current_penalty) }}
                  </span>
                </td>
                <td>
                  <button type="button" class="row-action" @click="toggleUser(user.id)">
                    {{ isUserOpen(user.id) ? '닫기' : '관리' }}
                  </button>
                </td>
              </tr>

              <tr v-if="isUserOpen(user.id)" class="detail-row">
                <td colspan="8">
                  <div class="detail-panel">
                    <section v-if="user.current_penalty" class="penalty-box">
                      <strong>현재 제재</strong>
                      <p>{{ formatPenalty(user.current_penalty) }} / {{ user.current_penalty.reason }}</p>
                    </section>

                    <section class="action-panel">
                      <h3>제재 조치</h3>
                      <input v-model="reasonByUser[user.id]" type="text" placeholder="조치 사유" />
                      <div class="penalty-actions">
                        <button v-for="[value, label] in penalties" :key="value" type="button" @click="applyPenalty(user, value)">
                          {{ label }}
                        </button>
                      </div>
                    </section>

                    <section class="action-panel">
                      <h3>관리자 메시지</h3>
                      <div class="message-row">
                        <input v-model="messageByUser[user.id]" type="text" placeholder="관리자 메시지" />
                        <button type="button" class="message-button" @click="sendMessage(user)">
                          메시지 보내기
                        </button>
                      </div>
                    </section>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>

        <p v-if="users.length === 0" class="empty-text">
          표시할 유저가 없습니다.
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
.col-user-main { width: 230px; }
.col-email { width: auto; }
.col-count { width: 80px; }
.col-status { width: 120px; }
.col-action { width: 80px; }

.number-cell {
  color: #98a2b3;
  font-size: 13px;
  font-weight: 900;
  text-align: center;
}

.user-link {
  color: #111827;
  font-weight: 900;
  text-decoration: none;
}

.user-link:hover {
  color: #f59e0b;
  text-decoration: underline;
}

.email-cell {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.count-chip,
.status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  padding: 5px 9px;
  border-radius: 999px;
  background: #f2f4f7;
  color: #344054;
  font-size: 12px;
  font-weight: 900;
}

.count-chip.danger {
  background: #fee2e2;
  color: #ef4444;
}

.status-badge.normal {
  background: #ecfdf3;
  color: #039855;
}

.status-badge.blocked {
  background: #fff7ed;
  color: #f97316;
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

.penalty-box,
.action-panel {
  padding: 16px;
  border: 1px solid #eadcc5;
  border-radius: 16px;
  background: #ffffff;
}

.penalty-box strong,
.action-panel h3 {
  display: block;
  margin: 0 0 8px;
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

.penalty-box p {
  margin: 0;
  color: #f97316;
  font-weight: 900;
}

.action-panel input {
  width: 100%;
  min-width: 0;
  padding: 12px;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  outline: none;
}

.penalty-actions,
.message-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.message-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
}

.penalty-actions button,
.message-button {
  border: 0;
  border-radius: 999px;
  color: #ffffff;
  padding: 10px 14px;
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
}

.penalty-actions button {
  background: #f97316;
}

.message-button {
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
    min-width: 900px;
  }

  .message-row {
    grid-template-columns: 1fr;
  }
}
</style>
