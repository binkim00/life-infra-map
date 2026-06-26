<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getNotifications, markAllNotificationsRead, markNotificationRead } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const notifications = ref([])
const isLoading = ref(false)
const errorMessage = ref('')

const unreadCount = computed(() => notifications.value.filter((item) => !item.is_read).length)

const notificationTypeLabels = {
  admin_warning: '관리자 메시지',
  penalty_notice: '제재 안내',
  report_received: '신고 접수',
  report_passed: '신고 검토 결과',
  report_penalty: '신고 처리 결과',
  inquiry_answered: '문의 답변',
  post_commented: '댓글 알림',
  post_liked: '좋아요 알림',
  comment_liked: '댓글 좋아요',
  system: '시스템 알림',
}

const getNotificationTypeLabel = (notification) => {
  return notificationTypeLabels[notification?.notification_type] || '알림'
}

const fetchNotifications = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  try {
    isLoading.value = true
    const response = await getNotifications()
    notifications.value = response.data
  } catch (error) {
    console.error(error)
    errorMessage.value = '알림을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const markNotificationReadLocally = (notificationId) => {
  notifications.value = notifications.value.map((notification) => (
    String(notification.id) === String(notificationId)
      ? { ...notification, is_read: true }
      : notification
  ))
}

const markNotificationAsRead = async (notification) => {
  if (!notification?.id || notification.is_read) return

  markNotificationReadLocally(notification.id)

  try {
    await markNotificationRead(notification.id)
  } catch (error) {
    console.error(error)
    await fetchNotifications()
  }
}

const markAllVisibleNotificationsRead = async () => {
  if (unreadCount.value === 0) return

  notifications.value = notifications.value.map((notification) => ({
    ...notification,
    is_read: true,
  }))

  try {
    await markAllNotificationsRead()
  } catch (error) {
    console.error(error)
    await fetchNotifications()
  }
}

const handleNotificationClick = async (notification) => {
  await markNotificationAsRead(notification)
  await router.push(notification.target_route || '/notifications')
}

onMounted(() => {
  fetchNotifications()
})
</script>

<template>
  <main class="notification-page">
    <section class="notification-container">
      <header class="notification-header">
        <div>
          <p class="eyebrow">NOTIFICATIONS</p>
          <h1>알림</h1>
        </div>

        <div class="notification-header-actions">
          <span v-if="unreadCount" class="unread-summary">
            새 알림 {{ unreadCount }}개
          </span>
          <button
            v-if="unreadCount"
            type="button"
            class="mark-all-read-button"
            @click="markAllVisibleNotificationsRead"
          >
            전체 읽음
          </button>
        </div>
      </header>

      <p v-if="isLoading" class="status-card">알림을 불러오는 중입니다.</p>
      <p v-else-if="errorMessage" class="status-card error">{{ errorMessage }}</p>

      <section v-else class="notification-list">
        <article v-for="notification in notifications" :key="notification.id" class="notification-card"
          :class="{ unread: !notification.is_read, clickable: notification.target_route }"
          role="button"
          tabindex="0"
          @click="handleNotificationClick(notification)"
          @keyup.enter="handleNotificationClick(notification)">
          <div>
            <span class="type-badge">{{ getNotificationTypeLabel(notification) }}</span>
            <h2>{{ notification.title }}</h2>
            <p>{{ notification.message }}</p>
            <small>{{ new Date(notification.created_at).toLocaleString() }}</small>
          </div>
        </article>

        <p v-if="notifications.length === 0" class="status-card">알림이 없습니다.</p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.notification-page { min-height: 100vh; padding: 40px 24px; background: #f6f7fb; }
.notification-container { max-width: 860px; margin: 0 auto; }
.notification-header { display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 24px; }
.eyebrow { margin: 0 0 6px; color: #2563eb; font-size: 13px; font-weight: 900; letter-spacing: .08em; }
h1, h2 { margin: 0; color: #111827; }
.notification-header-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; align-items: center; }
.unread-summary { padding: 8px 12px; border-radius: 999px; background: #ef4444; color: #fff; font-size: 13px; font-weight: 900; }
.mark-all-read-button { min-height: 34px; padding: 0 12px; border: 1px solid #bfdbfe; border-radius: 8px; background: #ffffff; color: #2563eb; font-weight: 900; cursor: pointer; }
.mark-all-read-button:hover, .mark-all-read-button:focus-visible { border-color: #2563eb; outline: none; }
.notification-list { display: grid; gap: 12px; }
.notification-card, .status-card { padding: 18px; border: 1px solid #e5e8f0; border-radius: 18px; background: #fff; box-shadow: 0 10px 28px rgba(20,35,70,.08); }
.notification-card { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.notification-card.clickable { cursor: pointer; }
.notification-card.clickable:hover, .notification-card.clickable:focus-visible { border-color: #2563eb; outline: none; }
.notification-card.unread { border-color: #93c5fd; background: #eff6ff; }
.type-badge { display: inline-flex; margin-bottom: 8px; padding: 5px 9px; border-radius: 999px; background: #dbeafe; color: #2563eb; font-size: 12px; font-weight: 900; }
.notification-card p { color: #344054; line-height: 1.6; white-space: pre-wrap; }
.notification-card small { color: #667085; font-weight: 700; }
.error { color: #ef4444; }
@media (max-width: 720px) { .notification-header, .notification-card { flex-direction: column; } }
</style>
