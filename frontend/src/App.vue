<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getNotifications } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const isSidebarCollapsed = ref(false)

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
  <div class="app-shell" :class="{ 'is-sidebar-collapsed': isSidebarCollapsed }">
    <aside class="app-sidebar">
      <div class="brand">
        <span class="brand-mark">틈</span>
        <span class="brand-text">
          <strong>생활틈지도</strong>
          <span>Life Infra Map</span>
        </span>
      </div>

      <button
        type="button"
        class="sidebar-toggle"
        :aria-expanded="!isSidebarCollapsed"
        @click="isSidebarCollapsed = !isSidebarCollapsed"
      >
        {{ isSidebarCollapsed ? '열기' : '접기' }}
      </button>

      <nav class="side-nav" aria-label="페이지 이동">
        <RouterLink to="/" class="nav-link">
          <span class="nav-icon">홈</span>
          <span class="nav-text">서비스 홈</span>
        </RouterLink>

        <RouterLink to="/" class="nav-link">
          <span class="nav-icon">맵</span>
          <span class="nav-text">지도</span>
        </RouterLink>

        <RouterLink to="/boards/free" class="nav-link">
          <span class="nav-text">게시판</span>
        </RouterLink>

        <RouterLink v-if="authStore.isLoggedIn" to="/mypage" class="nav-link">
          <span class="nav-text">마이페이지</span>
        </RouterLink>

        <RouterLink v-if="authStore.isLoggedIn" to="/notifications" class="nav-link notification-link">
          <span class="nav-text">알림</span>
          <span v-if="unreadNotificationCount" class="notification-badge">
            {{ unreadNotificationCount }}
          </span>
        </RouterLink>

        <RouterLink v-if="authStore.isLoggedIn" to="/inquiries/new" class="nav-link">
          <span class="nav-text">문의하기</span>
        </RouterLink>

        <RouterLink v-if="authStore.user?.is_staff" to="/admin/reports" class="nav-link">
          <span class="nav-text">신고 내역</span>
        </RouterLink>

        <RouterLink v-if="authStore.user?.is_staff" to="/admin/users" class="nav-link">
          <span class="nav-text">유저 관리</span>
        </RouterLink>

        <RouterLink v-if="authStore.user?.is_staff" to="/admin/inquiries" class="nav-link">
          <span class="nav-text">문의 관리</span>
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
  transition: grid-template-columns 0.2s ease;
}

.app-shell.is-sidebar-collapsed {
  grid-template-columns: 72px minmax(0, 1fr);
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
  min-width: 0;
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 0 6px;
}

.brand-mark {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: #2563eb;
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
}

.brand-text {
  min-width: 0;
  display: grid;
  gap: 4px;
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

.sidebar-toggle {
  min-height: 36px;
  border: 0;
  border-radius: 10px;
  background: #f2f4f7;
  color: #344054;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
}

.sidebar-toggle:hover {
  background: #e5e7eb;
  color: #111827;
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

.nav-icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: #eef2ff;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 900;
}

.nav-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-link:hover {
  background: #f2f4f7;
}

.nav-link.router-link-active {
  background: #2563eb;
  color: #ffffff;
}

.nav-link.router-link-active .nav-icon {
  background: rgba(255, 255, 255, 0.18);
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

.app-shell.is-sidebar-collapsed .app-sidebar {
  padding: 22px 10px;
  align-items: center;
}

.app-shell.is-sidebar-collapsed .brand {
  padding: 0;
}

.app-shell.is-sidebar-collapsed .brand-text,
.app-shell.is-sidebar-collapsed .nav-text {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.app-shell.is-sidebar-collapsed .sidebar-toggle {
  width: 100%;
  padding: 0;
  font-size: 11px;
}

.app-shell.is-sidebar-collapsed .side-nav {
  width: 100%;
}

.app-shell.is-sidebar-collapsed .nav-link {
  justify-content: center;
  padding: 8px;
}

.app-shell.is-sidebar-collapsed .nav-icon {
  width: 32px;
  height: 32px;
}

.app-shell.is-sidebar-collapsed .notification-badge {
  position: absolute;
  top: 4px;
  right: 4px;
}

.app-main {
  min-width: 0;
}

@media (max-width: 820px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .app-shell.is-sidebar-collapsed {
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

  .app-shell.is-sidebar-collapsed .app-sidebar {
    padding: 12px 16px;
    align-items: center;
  }

  .app-shell.is-sidebar-collapsed .brand-text {
    position: static;
    width: auto;
    height: auto;
    overflow: visible;
    clip: auto;
    white-space: normal;
  }

  .app-shell.is-sidebar-collapsed .side-nav {
    display: none;
  }

  .app-shell.is-sidebar-collapsed .sidebar-toggle {
    width: auto;
    padding: 0 12px;
    font-size: 13px;
  }

  .side-nav {
    grid-auto-flow: column;
    grid-auto-columns: max-content;
    overflow-x: auto;
  }
}
</style>