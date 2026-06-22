<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getNotifications } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const route = useRoute()
const notifications = ref([])
let notificationTimer = null

const unreadNotificationCount = computed(() => {
  return notifications.value.filter((notification) => !notification.is_read).length
})

const fetchNotifications = async () => {
  if (!authStore.isLoggedIn) {
    notifications.value = []
    return
  }

  try {
    const response = await getNotifications()
    notifications.value = response.data
  } catch (error) {
    console.error(error)
  }
}

const startNotificationPolling = () => {
  if (notificationTimer) {
    window.clearInterval(notificationTimer)
  }

  notificationTimer = window.setInterval(fetchNotifications, 30000)
}

onMounted(() => {
  authStore.fetchMe()
    .then(() => {
      fetchNotifications()
      startNotificationPolling()
    })
    .catch(() => {
      authStore.logout()
    })
})

watch(
  () => authStore.isLoggedIn,
  (isLoggedIn) => {
    if (isLoggedIn) {
      fetchNotifications()
      startNotificationPolling()
      return
    }

    notifications.value = []

    if (notificationTimer) {
      window.clearInterval(notificationTimer)
      notificationTimer = null
    }
  },
)

watch(
  () => route.fullPath,
  () => {
    fetchNotifications()
  },
)

onBeforeUnmount(() => {
  if (notificationTimer) {
    window.clearInterval(notificationTimer)
  }
})
</script>

<template>
  <div class="app-shell">
    <aside class="app-sidebar">
      <div class="brand">
        <strong>생활틈지도</strong>
        <span>Life Infra Map</span>
      </div>

      <nav class="side-nav" aria-label="페이지 이동">
        <RouterLink to="/" class="nav-link">
          서비스 홈
        </RouterLink>
        <RouterLink to="/recommendation-test" class="nav-link">
          추천 테스트
        </RouterLink>
        <RouterLink to="/boards/free" class="nav-link">
          게시판
        </RouterLink>
        <RouterLink v-if="authStore.isLoggedIn" to="/mypage" class="nav-link">
          마이페이지
        </RouterLink>
        <RouterLink v-if="authStore.isLoggedIn" to="/notifications" class="nav-link notification-link">
          <span>알림</span>
          <span v-if="unreadNotificationCount" class="notification-badge">
            {{ unreadNotificationCount }}
          </span>
        </RouterLink>
        <RouterLink v-if="authStore.isLoggedIn" to="/inquiries/new" class="nav-link">
          문의하기
        </RouterLink>
        <RouterLink v-if="authStore.user?.is_staff" to="/admin/reports" class="nav-link">
          신고 내역
        </RouterLink>
        <RouterLink v-if="authStore.user?.is_staff" to="/admin/users" class="nav-link">
          유저 관리
        </RouterLink>
        <RouterLink v-if="authStore.user?.is_staff" to="/admin/inquiries" class="nav-link">
          문의 관리
        </RouterLink>
      </nav>
    </aside>

    <div class="app-main">
      <RouterView />
    </div>
  </div>
</template>

<style>
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family:
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif;
  background: #f6f7fb;
  color: #222;
}

button,
input {
  font-family: inherit;
}

.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  background: #f6f7fb;
}

.app-sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 22px 16px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  border-right: 1px solid #e5e8f0;
  background: #ffffff;
}

.brand {
  display: grid;
  gap: 4px;
  padding: 0 6px;
}

.brand strong {
  color: #111827;
  font-size: 18px;
  line-height: 1.3;
}

.brand span {
  color: #667085;
  font-size: 12px;
  font-weight: 700;
}

.side-nav {
  display: grid;
  gap: 8px;
}

.nav-link {
  padding: 11px 12px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  border-radius: 8px;
  color: #344054;
  font-size: 14px;
  font-weight: 800;
  text-decoration: none;
}

.nav-link:hover {
  background: #f2f4f7;
}

.nav-link.router-link-active {
  background: #2563eb;
  color: #ffffff;
}

.notification-badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: inline-grid;
  place-items: center;
  border-radius: 999px;
  background: #ef4444;
  color: #ffffff;
  font-size: 11px;
  font-weight: 900;
  line-height: 1;
}

.app-main {
  min-width: 0;
}

@media (max-width: 820px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .app-sidebar {
    position: sticky;
    z-index: 20;
    height: auto;
    padding: 12px 16px;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    border-right: 0;
    border-bottom: 1px solid #e5e8f0;
  }

  .side-nav {
    grid-auto-flow: column;
    grid-auto-columns: max-content;
    overflow-x: auto;
  }
}
</style>
