<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getNotifications, markAllNotificationsRead } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'

const isSidebarCollapsed = ref(false)

const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const route = useRoute()
const router = useRouter()
const notifications = ref([])
const isAccountMenuOpen = ref(false)
const isSidebarAccountMenuOpen = ref(false)
const isNotificationMenuOpen = ref(false)
const notificationMenuRef = ref(null)
const accountMenuRef = ref(null)
const sidebarProfileRef = ref(null)
let notificationTimer = null

const handleLogout = async () => {
  closeAllDropdowns()
  await authStore.logout()
  router.push('/')
}

const visibleNotifications = computed(() => {
  return notifications.value.filter(settingsStore.isNotificationVisible)
})

const unreadNotificationCount = computed(() => {
  return visibleNotifications.value.filter((notification) => !notification.is_read).length
})

const recentNotifications = computed(() => {
  return visibleNotifications.value.slice(0, 6)
})

const formatNotificationTime = (value) => {
  if (!value) {
    return ''
  }

  const createdAt = new Date(value)
  const diffMs = Date.now() - createdAt.getTime()
  const diffMinutes = Math.floor(diffMs / 60000)

  if (diffMinutes < 1) {
    return '방금 전'
  }

  if (diffMinutes < 60) {
    return `${diffMinutes}분 전`
  }

  const diffHours = Math.floor(diffMinutes / 60)

  if (diffHours < 24) {
    return `${diffHours}시간 전`
  }

  const diffDays = Math.floor(diffHours / 24)

  return `${diffDays}일 전`
}

const isCustomerCenterActive = computed(() => {
  return route.path.startsWith('/inquiries')
})

const isMypageActive = computed(() => {
  return route.path.startsWith('/mypage')
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

const markNotificationsReadLocally = () => {
  notifications.value = notifications.value.map((notification) => ({
    ...notification,
    is_read: true,
  }))
}

const openNotificationMenu = async () => {
  const willOpen = !isNotificationMenuOpen.value
  isNotificationMenuOpen.value = willOpen
  isAccountMenuOpen.value = false
  isSidebarAccountMenuOpen.value = false

  if (!willOpen || unreadNotificationCount.value === 0) {
    return
  }

  markNotificationsReadLocally()

  try {
    await markAllNotificationsRead()
  } catch (error) {
    console.error(error)
    fetchNotifications()
  }
}

const moveToNotificationTarget = (notification) => {
  closeAllDropdowns()

  if (notification.notification_type === 'inquiry_answered') {
    router.push('/inquiries/my')
    return
  }

  router.push(notification.target_route || '/')
}

const closeAllDropdowns = () => {
  isNotificationMenuOpen.value = false
  isAccountMenuOpen.value = false
  isSidebarAccountMenuOpen.value = false
}

const toggleAccountMenu = () => {
  const willOpen = !isAccountMenuOpen.value
  isAccountMenuOpen.value = willOpen
  isNotificationMenuOpen.value = false
  isSidebarAccountMenuOpen.value = false
}

const toggleSidebarAccountMenu = () => {
  const willOpen = !isSidebarAccountMenuOpen.value
  isSidebarAccountMenuOpen.value = willOpen
  isNotificationMenuOpen.value = false
  isAccountMenuOpen.value = false
}

const handleDocumentClick = (event) => {
  const target = event.target

  if (
    notificationMenuRef.value?.contains(target)
    || accountMenuRef.value?.contains(target)
    || sidebarProfileRef.value?.contains(target)
  ) {
    return
  }

  closeAllDropdowns()
}

const startNotificationPolling = () => {
  if (notificationTimer) {
    window.clearInterval(notificationTimer)
  }

  notificationTimer = window.setInterval(fetchNotifications, 30000)
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)

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
    isSidebarAccountMenuOpen.value = false

    if (notificationTimer) {
      window.clearInterval(notificationTimer)
      notificationTimer = null
    }
  },
)

watch(
  () => route.fullPath,
  () => {
    isSidebarAccountMenuOpen.value = false
    fetchNotifications()
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)

  if (notificationTimer) {
    window.clearInterval(notificationTimer)
  }
})
</script>

<template>
  <div class="app-shell" :class="{ 'is-sidebar-collapsed': isSidebarCollapsed, 'is-compact-mode': settingsStore.compactMode }">
    <aside class="app-sidebar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark">틈</span>
        <span class="brand-text">
          <strong>생활틈지도</strong>
          <span>Life Infra Map</span>
        </span>
      </RouterLink>

      <button
        type="button"
        class="sidebar-toggle"
        :aria-expanded="!isSidebarCollapsed"
        :aria-label="isSidebarCollapsed ? '사이드바 열기' : '사이드바 접기'"
        @click="isSidebarCollapsed = !isSidebarCollapsed"
      >
        <span
          class="sidebar-toggle-arrow"
          :class="{ 'is-collapsed': isSidebarCollapsed }"
          aria-hidden="true"
        ></span>
      </button>

      <nav class="side-nav" aria-label="페이지 이동">
        <RouterLink to="/" class="nav-link">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="m3 10 9-7 9 7" />
              <path d="M5 9v11h5v-6h4v6h5V9" />
            </svg>
          </span>
          <span class="nav-text">홈</span>
        </RouterLink>

        <RouterLink to="/boards/notice" class="nav-link">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M6 4h11a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
              <path d="M8 8h.01" />
              <path d="M8 12h.01" />
              <path d="M11 8h5" />
              <path d="M11 12h5" />
            </svg>
          </span>
          <span class="nav-text">공지사항</span>
        </RouterLink>

        <RouterLink to="/boards/free" class="nav-link">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M4 5h16" />
              <path d="M4 12h16" />
              <path d="M4 19h10" />
            </svg>
          </span>
          <span class="nav-text">자유게시판</span>
        </RouterLink>

        <RouterLink v-if="authStore.isLoggedIn" to="/mypage" class="nav-link">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M20 21a8 8 0 0 0-16 0" />
              <path d="M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z" />
            </svg>
          </span>
          <span class="nav-text">마이페이지</span>
        </RouterLink>

        <RouterLink v-if="authStore.isLoggedIn" to="/inquiries/my" class="nav-link">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z" />
              <path d="M8 9h8" />
              <path d="M8 13h5" />
            </svg>
          </span>
          <span class="nav-text">고객센터</span>
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

      <div v-if="authStore.isLoggedIn" ref="sidebarProfileRef" class="sidebar-profile">
        <button
          type="button"
          class="sidebar-profile-link"
          :aria-expanded="isSidebarAccountMenuOpen"
          @click="toggleSidebarAccountMenu"
        >
          <span class="sidebar-avatar">
            <img
              v-if="authStore.user?.profile_image_url"
              :src="authStore.user.profile_image_url"
              :alt="authStore.user?.nickname || authStore.user?.username"
            />
            <span v-else class="default-avatar" aria-hidden="true"></span>
          </span>
          <span class="sidebar-profile-copy">
            <strong>{{ authStore.user?.nickname || authStore.user?.username }}</strong>
            <span>Plus</span>
          </span>
        </button>

        <div v-if="isSidebarAccountMenuOpen" class="sidebar-account-dropdown">
          <RouterLink
            :to="{ path: '/mypage', query: { section: 'profile' } }"
            class="account-menu-button"
            :class="{ active: isMypageActive }"
            @click="isSidebarAccountMenuOpen = false"
          >
            <span>마이페이지</span>
          </RouterLink>

          <RouterLink
            to="/inquiries/my"
            class="account-menu-button"
            :class="{ active: isCustomerCenterActive }"
            @click="isSidebarAccountMenuOpen = false"
          >
            <span>고객센터</span>
          </RouterLink>

          <button type="button" class="account-logout-button" @click="handleLogout">
            로그아웃
          </button>
        </div>

        <div class="sidebar-profile-actions">
          <RouterLink
            to="/settings"
            class="sidebar-icon-button"
            aria-label="설정"
            title="설정"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z" />
              <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.36a1.7 1.7 0 0 0-1 .58V20a2 2 0 1 1-4 0v-.08a1.7 1.7 0 0 0-1-.58 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.64 15a1.7 1.7 0 0 0-.58-1H4a2 2 0 1 1 0-4h.08a1.7 1.7 0 0 0 .58-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.64a1.7 1.7 0 0 0 1-.58V4a2 2 0 1 1 4 0v.08a1.7 1.7 0 0 0 1 .58 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.36 9c.2.35.39.69.58 1H20a2 2 0 1 1 0 4h-.08a1.7 1.7 0 0 0-.52 1Z" />
            </svg>
          </RouterLink>

          <RouterLink
            to="/guide"
            class="sidebar-icon-button"
            aria-label="이용가이드"
            title="이용가이드"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z" />
              <path d="M12 8v5" />
              <path d="M12 16h.01" />
            </svg>
          </RouterLink>
        </div>
      </div>
    </aside>

    <div class="app-main">
      <div class="global-account-bar">
        <template v-if="authStore.isLoggedIn">
          <div ref="notificationMenuRef" class="global-notification-menu">
            <button
              type="button"
              class="global-notification-button"
              :aria-expanded="isNotificationMenuOpen"
              aria-label="알림"
              @click="openNotificationMenu"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
                <path d="M10 21h4" />
              </svg>
              <span v-if="unreadNotificationCount" class="notification-badge global-notification-badge">
                {{ unreadNotificationCount }}
              </span>
            </button>

            <div v-if="isNotificationMenuOpen" class="notification-dropdown">
              <header class="notification-dropdown-header">
                <strong>알림</strong>
              </header>

              <div v-if="recentNotifications.length" class="notification-dropdown-list">
                <article
                  v-for="notification in recentNotifications"
                  :key="notification.id"
                  class="notification-dropdown-item"
                  :class="{ unread: !notification.is_read }"
                  role="button"
                  tabindex="0"
                  @click="moveToNotificationTarget(notification)"
                  @keyup.enter="moveToNotificationTarget(notification)"
                >
                  <span class="notification-dot" aria-hidden="true"></span>
                  <div class="notification-copy">
                    <strong>{{ notification.title }}</strong>
                    <p>{{ notification.message }}</p>
                    <small>{{ formatNotificationTime(notification.created_at) }}</small>
                  </div>
                </article>
              </div>

              <p v-else class="notification-empty">알림이 없습니다.</p>
            </div>
          </div>

          <div ref="accountMenuRef" class="global-account-menu">
            <button
              type="button"
              class="global-user-link"
              :aria-expanded="isAccountMenuOpen"
              @click="toggleAccountMenu"
            >
              <span class="global-avatar">
                <img
                  v-if="authStore.user?.profile_image_url"
                  :src="authStore.user.profile_image_url"
                  :alt="authStore.user?.nickname || authStore.user?.username"
                />
                <span v-else class="default-avatar" aria-hidden="true"></span>
              </span>
              <span class="global-user-name">
                {{ authStore.user?.nickname || authStore.user?.username }}
              </span>
              <span class="global-menu-caret" aria-hidden="true">▾</span>
            </button>

            <div v-if="isAccountMenuOpen" class="account-dropdown">
              <RouterLink
                :to="{ path: '/mypage', query: { section: 'profile' } }"
                class="account-menu-button"
                :class="{ active: isMypageActive }"
                @click="isAccountMenuOpen = false"
              >
                <span>마이페이지</span>
              </RouterLink>

              <RouterLink
                to="/inquiries/my"
                class="account-menu-button"
                :class="{ active: isCustomerCenterActive }"
                @click="isAccountMenuOpen = false"
              >
                <span>고객센터</span>
              </RouterLink>

              <button type="button" class="account-logout-button" @click="handleLogout">
                로그아웃
              </button>
            </div>
          </div>
        </template>

        <template v-else>
          <RouterLink to="/login" class="global-auth-button">
            로그인
          </RouterLink>
          <RouterLink to="/signup" class="global-auth-button signup">
            회원가입
          </RouterLink>
        </template>
      </div>

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
  z-index: 60;
  height: 100vh;
  padding: 22px 16px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  border-right: 1px solid #e5e8f0;
  background: #ffffff;
  overflow: visible;
}

.brand {
  min-width: 0;
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 0 6px;
  text-decoration: none;
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
  position: absolute;
  top: 50%;
  right: -25px;
  z-index: 90;
  width: 24px;
  height: 50px;
  padding: 0;
  display: grid;
  place-items: center;
  border: 1px solid #d0d5dd;
  border-left-color: #ffffff;
  border-radius: 0 8px 8px 0;
  background: #ffffff;
  color: #2563eb;
  cursor: pointer;
  transform: translateY(-50%);
  box-shadow: 5px 0 14px rgba(20, 35, 70, 0.16);
}

.sidebar-toggle:hover {
  background: #eff6ff;
  color: #1d4ed8;
}

.sidebar-toggle-arrow {
  width: 0;
  height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-right: 6px solid currentColor;
}

.sidebar-toggle-arrow.is-collapsed {
  border-right: 0;
  border-left: 6px solid currentColor;
}

.side-nav {
  display: grid;
  gap: 8px;
}

.sidebar-profile {
  position: relative;
  margin-top: auto;
  min-height: 58px;
  padding: 8px 10px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  border-top: 1px solid #e5e8f0;
  background: #ffffff;
}

.sidebar-profile-link {
  min-width: 0;
  flex: 1 1 auto;
  padding: 0;
  display: flex;
  gap: 8px;
  align-items: center;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-decoration: none;
}

.sidebar-avatar {
  position: relative;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: 50%;
  background: #8fb8cc;
}

.sidebar-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.sidebar-profile-copy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.sidebar-profile-copy strong,
.sidebar-profile-copy span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-profile-copy strong {
  color: #111827;
  font-size: 13px;
  font-weight: 900;
}

.sidebar-profile-copy span {
  color: #667085;
  font-size: 11px;
  font-weight: 800;
}

.sidebar-profile-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 4px;
}

.sidebar-icon-button {
  width: 28px;
  height: 28px;
  padding: 0;
  display: inline-grid;
  place-items: center;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #71717a;
  cursor: pointer;
  text-decoration: none;
}

.sidebar-icon-button:hover {
  border-color: #2563eb;
  color: #2563eb;
  background: #eff6ff;
}

.sidebar-icon-button svg {
  width: 17px;
  height: 17px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.sidebar-account-dropdown {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: calc(100% + 8px);
  z-index: 95;
  padding: 10px;
  display: grid;
  gap: 6px;
  border: 1px solid #e5e8f0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18px 40px rgba(20, 35, 70, 0.18);
  backdrop-filter: blur(10px);
}

.nav-link {
  width: 100%;
  padding: 11px 12px;
  display: flex;
  justify-content: flex-start;
  gap: 8px;
  align-items: center;
  border-radius: 8px;
  color: #344054;
  font-size: 14px;
  font-weight: 800;
  text-decoration: none;
}

.nav-icon {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  color: currentColor;
}

.nav-icon svg {
  width: 21px;
  height: 21px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
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
  right: -25px;
}

.app-shell.is-sidebar-collapsed .side-nav {
  width: 100%;
}

.app-shell.is-sidebar-collapsed .sidebar-profile {
  width: 100%;
  padding: 8px;
  place-items: center;
}

.app-shell.is-sidebar-collapsed .sidebar-profile-link {
  justify-content: center;
}

.app-shell.is-sidebar-collapsed .sidebar-profile-copy,
.app-shell.is-sidebar-collapsed .sidebar-profile-actions {
  display: none;
}

.app-shell.is-sidebar-collapsed .nav-link {
  justify-content: center;
  padding: 8px;
}

.app-shell.is-sidebar-collapsed .nav-icon {
  width: 32px;
  height: 32px;
}

.app-shell.is-sidebar-collapsed .nav-icon svg {
  width: 23px;
  height: 23px;
}

.app-shell.is-sidebar-collapsed .notification-badge {
  position: absolute;
  top: 4px;
  right: 4px;
}

.app-main {
  min-width: 0;
  position: relative;
  padding-top: 68px;
}

.app-shell.is-compact-mode .board-table th,
.app-shell.is-compact-mode .board-table td,
.app-shell.is-compact-mode .inquiry-table th,
.app-shell.is-compact-mode .inquiry-table td {
  height: 26px;
  padding-right: 6px;
  padding-left: 6px;
  font-size: 12px;
}

.app-shell.is-compact-mode .board-table,
.app-shell.is-compact-mode .inquiry-table {
  font-size: 12px;
}

.app-shell.is-compact-mode .board-page,
.app-shell.is-compact-mode .page {
  padding-top: 28px;
}

.global-account-bar {
  position: fixed;
  top: 16px;
  right: 24px;
  z-index: 80;
  display: flex;
  gap: 8px;
  align-items: center;
  max-width: calc(100vw - 48px);
}

.global-notification-menu {
  position: relative;
}

.global-notification-button {
  position: relative;
  width: 42px;
  height: 42px;
  display: inline-grid;
  place-items: center;
  border: 1px solid #e5e8f0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  color: #111827;
  text-decoration: none;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.12);
  backdrop-filter: blur(8px);
  cursor: pointer;
}

.global-notification-button svg {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.global-notification-badge {
  position: absolute;
  top: -3px;
  right: -3px;
}

.notification-dropdown {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  width: min(420px, calc(100vw - 24px));
  max-height: min(620px, calc(100vh - 96px));
  overflow-y: auto;
  border: 1px solid #3f3f46;
  border-radius: 10px;
  background: #27272a;
  color: #f4f4f5;
  box-shadow: 0 22px 60px rgba(0, 0, 0, 0.35);
}

.notification-dropdown-header {
  padding: 14px 16px;
  border-bottom: 1px solid #3f3f46;
}

.notification-dropdown-header strong {
  font-size: 16px;
}

.notification-dropdown-list {
  display: grid;
}

.notification-dropdown-item {
  position: relative;
  padding: 14px 16px 14px 32px;
  display: grid;
  gap: 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  cursor: pointer;
}

.notification-dropdown-item:last-child {
  border-bottom: 0;
}

.notification-dropdown-item:hover,
.notification-dropdown-item:focus-visible {
  background: rgba(255, 255, 255, 0.06);
  outline: none;
}

.notification-dropdown-item.unread .notification-dot {
  background: #3b82f6;
}

.notification-dot {
  position: absolute;
  top: 22px;
  left: 14px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: transparent;
}

.notification-copy {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.notification-copy strong {
  color: #fafafa;
  font-size: 14px;
  line-height: 1.4;
}

.notification-copy p {
  margin: 0;
  color: #d4d4d8;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.notification-copy small,
.notification-empty {
  color: #a1a1aa;
  font-size: 12px;
  font-weight: 800;
}

.notification-empty {
  margin: 0;
  padding: 22px 16px;
  text-align: center;
}

.global-account-menu {
  position: relative;
}

.global-user-link {
  min-width: 0;
  max-width: min(280px, calc(100vw - 160px));
  height: 42px;
  padding: 4px 12px 4px 4px;
  display: inline-flex;
  gap: 8px;
  align-items: center;
  border: 1px solid #e5e8f0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  color: #344054;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
  cursor: pointer;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.12);
  backdrop-filter: blur(8px);
}

.global-user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-menu-caret {
  color: #667085;
  font-size: 12px;
}

.account-dropdown {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  width: 240px;
  padding: 10px;
  display: grid;
  gap: 6px;
  border: 1px solid #e5e8f0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18px 40px rgba(20, 35, 70, 0.18);
  backdrop-filter: blur(10px);
}

.account-menu-button,
.account-logout-button {
  width: 100%;
  min-height: 38px;
  padding: 0 10px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #344054;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
  cursor: pointer;
}

.account-menu-button:hover,
.account-menu-button.active {
  background: #eff6ff;
  color: #1d4ed8;
}

.account-logout-button {
  justify-content: flex-start;
  color: #dc2626;
}

.account-logout-button:hover {
  background: #fef2f2;
}

.global-avatar {
  position: relative;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: 50%;
  background: #8fb8cc;
}

.global-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.default-avatar {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
}

.default-avatar::before,
.default-avatar::after {
  position: absolute;
  left: 50%;
  content: "";
  transform: translateX(-50%);
  background: #c8ddea;
}

.default-avatar::before {
  top: 20%;
  width: 34%;
  height: 34%;
  border-radius: 50%;
}

.default-avatar::after {
  bottom: -10%;
  width: 72%;
  height: 48%;
  border-radius: 50% 50% 0 0;
}

.global-auth-button {
  height: 42px;
  padding: 0 14px;
  border: 1px solid #d0d5dd;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  color: #344054;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
  cursor: pointer;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.12);
  backdrop-filter: blur(8px);
}

.global-auth-button.signup {
  border-color: #2563eb;
  background: #2563eb;
  color: #ffffff;
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

  .app-main {
    padding-top: 72px;
  }

  .global-account-bar {
    top: 72px;
    right: 12px;
    max-width: calc(100vw - 24px);
  }

  .global-user-link {
    max-width: calc(100vw - 128px);
  }

  .sidebar-toggle {
    display: none;
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

  .sidebar-profile,
  .app-shell.is-sidebar-collapsed .sidebar-profile {
    display: none;
  }

  .app-shell.is-sidebar-collapsed .sidebar-toggle {
    display: none;
  }

  .side-nav {
    grid-auto-flow: column;
    grid-auto-columns: max-content;
    overflow-x: auto;
  }
}
</style>
