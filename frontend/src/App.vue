<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getNotifications, markAllNotificationsRead } from '@/api/boards'
import { getTierIcon, getTierLabel } from '@/utils/tierIcons'
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
const mascotFetchPhase = ref('')
const mascotFetchedPlaceId = ref(null)
const mascotFetchedPlaceName = ref('')
const mascotFetchedMarkerLabel = ref('')
const isMarkerChoiceMenuOpen = ref(false)
const mascotRunX = ref('-36vw')
const mascotRunY = ref('-17vh')
const mascotRunMidX = ref('-18vw')
const mascotRunMidY = ref('-9vh')
const mascotRunNearX = ref('-30vw')
const mascotRunNearY = ref('-14vh')
let notificationTimer = null
let mascotFetchTimer = null

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

const currentUserTierIcon = computed(() => {
  return getTierIcon(authStore.user?.tier)
})

const currentUserTierLabel = computed(() => {
  return authStore.user?.tier_label || getTierLabel(authStore.user?.tier)
})

const currentUserContribution = computed(() => {
  return authStore.user?.contribution ?? authStore.user?.score ?? 0
})

const currentUserNicknameStyle = computed(() => {
  return authStore.user?.nickname_color ? { color: authStore.user.nickname_color } : {}
})

const mascotState = computed(() => {
  const routeName = route.name || ''
  const path = route.path

  if (routeName === 'home') {
    return { key: 'home', prop: '⌕', message: '필요한 장소 냄새 맡는 중' }
  }

  if (routeName === 'recommendation-test') {
    return { key: 'map', prop: '⌖', message: '지도 위를 총총 탐색 중' }
  }

  if (path.startsWith('/boards')) {
    if (routeName === 'board-create' || routeName === 'board-edit') {
      return { key: 'write', prop: '✎', message: '글감을 또각또각 적는 중' }
    }

    return { key: 'board', prop: '▤', message: '게시글을 조용히 읽는 중' }
  }

  if (routeName === 'mypage') {
    return { key: 'mypage', prop: '♡', message: '프로필을 반듯하게 정리 중' }
  }

  if (routeName === 'guide' || routeName === 'upgrade-guide') {
    return { key: 'guide', prop: '?', message: '길을 콕 집어 알려주는 중' }
  }

  if (path.startsWith('/inquiries')) {
    return { key: 'inquiry', prop: '♪', message: '문의 답변을 기다리는 중' }
  }

  if (routeName === 'settings') {
    return { key: 'settings', prop: '⚙', message: '취향에 맞게 맞추는 중' }
  }

  if (path.startsWith('/admin')) {
    return { key: 'admin', prop: '!', message: '관리 화면을 지키는 중' }
  }

  if (routeName === 'login' || routeName === 'signup') {
    return { key: 'auth', prop: '•', message: '반갑게 맞이하는 중' }
  }

  return { key: 'default', prop: '·', message: '천천히 따라가는 중' }
})

const activeMascotState = computed(() => {
  if (mascotFetchPhase.value === 'fetching') {
    return { key: 'fetching', prop: '', message: '뼈다귀 마커로 달려가는 중' }
  }

  if (mascotFetchPhase.value === 'carrying') {
    return {
      key: 'carrying',
      prop: '',
      message: mascotFetchedPlaceName.value
        ? `${mascotFetchedPlaceName.value} 마커 물고 있는 중`
        : '뼈다귀 마커 물고 있는 중',
    }
  }

  return mascotState.value
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

const clearMascotFetch = () => {
  if (mascotFetchTimer) {
    window.clearTimeout(mascotFetchTimer)
    mascotFetchTimer = null
  }

  mascotFetchPhase.value = ''
  mascotFetchedPlaceId.value = null
  mascotFetchedPlaceName.value = ''
  mascotFetchedMarkerLabel.value = ''
  isMarkerChoiceMenuOpen.value = false
}

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

const setMascotRunTarget = (target) => {
  const fallbackX = Math.round(window.innerWidth * -0.36)
  const fallbackY = Math.round(window.innerHeight * -0.17)

  if (!target || typeof target.clientX !== 'number' || typeof target.clientY !== 'number') {
    mascotRunX.value = `${fallbackX}px`
    mascotRunY.value = `${fallbackY}px`
    mascotRunMidX.value = `${Math.round(fallbackX * 0.48)}px`
    mascotRunMidY.value = `${Math.round(fallbackY * 0.48 - 18)}px`
    mascotRunNearX.value = `${Math.round(fallbackX * 0.82)}px`
    mascotRunNearY.value = `${Math.round(fallbackY * 0.82 + 8)}px`
    return
  }

  const mascotElement = document.querySelector('.route-mascot')
  const mascotStyle = mascotElement ? window.getComputedStyle(mascotElement) : null
  const baseRight = Number.parseFloat(mascotStyle?.right || '28') || 28
  const baseBottom = Number.parseFloat(mascotStyle?.bottom || '24') || 24
  const baseWidth = mascotElement?.offsetWidth || 150
  const baseHeight = mascotElement?.offsetHeight || 190
  const baseLeft = window.innerWidth - baseRight - baseWidth
  const baseTop = window.innerHeight - baseBottom - baseHeight
  const fromX = baseLeft + baseWidth * 0.68
  const fromY = baseTop + baseHeight * 0.7
  const targetX = clamp(target.clientX - fromX, -(window.innerWidth - 116), 28)
  const targetY = clamp(target.clientY - fromY, -(window.innerHeight - 128), 24)

  mascotRunX.value = `${Math.round(targetX)}px`
  mascotRunY.value = `${Math.round(targetY)}px`
  mascotRunMidX.value = `${Math.round(targetX * 0.48)}px`
  mascotRunMidY.value = `${Math.round(targetY * 0.48 - 18)}px`
  mascotRunNearX.value = `${Math.round(targetX * 0.82)}px`
  mascotRunNearY.value = `${Math.round(targetY * 0.82 + 8)}px`
}

const handleMascotClick = () => {
  if (mascotFetchPhase.value !== 'carrying' || !mascotFetchedPlaceId.value) return

  window.dispatchEvent(new CustomEvent('place-marker-fetch-click', {
    detail: {
      placeId: mascotFetchedPlaceId.value,
      placeName: mascotFetchedPlaceName.value,
      markerLabel: mascotFetchedMarkerLabel.value,
    },
  }))
}

const handleMarkerChoiceMenuOpen = () => {
  isMarkerChoiceMenuOpen.value = true
}

const handleMarkerChoiceMenuClose = () => {
  isMarkerChoiceMenuOpen.value = false
}

const updateMascotFetchTarget = (event) => {
  if (!mascotFetchPhase.value) return

  mascotFetchedPlaceId.value = event.detail?.placeId || mascotFetchedPlaceId.value
  mascotFetchedPlaceName.value = event.detail?.placeName || mascotFetchedPlaceName.value
  mascotFetchedMarkerLabel.value = event.detail?.markerLabel || mascotFetchedMarkerLabel.value
  setMascotRunTarget(event.detail?.target)
}

const triggerMascotFetch = (event) => {
  if (mascotFetchTimer) {
    window.clearTimeout(mascotFetchTimer)
  }

  mascotFetchedPlaceId.value = event.detail?.placeId || null
  mascotFetchedPlaceName.value = event.detail?.placeName || ''
  mascotFetchedMarkerLabel.value = event.detail?.markerLabel || ''
  setMascotRunTarget(event.detail?.target)
  mascotFetchPhase.value = 'fetching'
  mascotFetchTimer = window.setTimeout(() => {
    mascotFetchPhase.value = 'carrying'
    mascotFetchTimer = null
    window.dispatchEvent(new CustomEvent('place-marker-fetch-arrived', {
      detail: event.detail || {},
    }))
  }, 1100)
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
  window.addEventListener('place-marker-fetch', triggerMascotFetch)
  window.addEventListener('place-marker-fetch-update', updateMascotFetchTarget)
  window.addEventListener('place-marker-fetch-clear', clearMascotFetch)
  window.addEventListener('place-marker-choice-open', handleMarkerChoiceMenuOpen)
  window.addEventListener('place-marker-choice-close', handleMarkerChoiceMenuClose)

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
    clearMascotFetch()
    fetchNotifications()
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
  window.removeEventListener('place-marker-fetch', triggerMascotFetch)
  window.removeEventListener('place-marker-fetch-update', updateMascotFetchTarget)
  window.removeEventListener('place-marker-fetch-clear', clearMascotFetch)
  window.removeEventListener('place-marker-choice-open', handleMarkerChoiceMenuOpen)
  window.removeEventListener('place-marker-choice-close', handleMarkerChoiceMenuClose)
  clearMascotFetch()

  if (notificationTimer) {
    window.clearInterval(notificationTimer)
  }
})
</script>

<template>
  <div class="app-shell" :class="{ 'is-sidebar-collapsed': isSidebarCollapsed, 'is-compact-mode': settingsStore.compactMode }">
    <aside class="app-sidebar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark" aria-hidden="true">
          <span class="brand-pin">
            <span class="brand-dog">
              <span class="brand-dog-ear left"></span>
              <span class="brand-dog-ear right"></span>
              <span class="brand-dog-eye left"></span>
              <span class="brand-dog-eye right"></span>
              <span class="brand-dog-nose"></span>
              <span class="brand-dog-mouth"></span>
              <span class="brand-dog-cheek left"></span>
              <span class="brand-dog-cheek right"></span>
            </span>
          </span>
        </span>
        <span class="brand-text">
          <strong>여기일지도</strong>
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

        <RouterLink v-if="authStore.isLoggedIn" to="/place-report" class="nav-link">
          <span class="nav-text">장소 제보</span>
        </RouterLink>

        <RouterLink v-if="authStore.user?.is_staff" to="/admin/reports" class="nav-link">
          <span class="nav-text">신고 내역</span>
        </RouterLink>

        <RouterLink v-if="authStore.user?.is_staff" to="/admin/place-reports" class="nav-link">
          <span class="nav-text">장소 제보 검증</span>
        </RouterLink>

        <RouterLink v-if="authStore.user?.is_staff" to="/admin/users" class="nav-link">
          <span class="nav-text">유저 관리</span>
        </RouterLink>

        <RouterLink v-if="authStore.user?.is_staff" to="/admin/inquiries" class="nav-link">
          <span class="nav-text">문의 관리</span>
        </RouterLink>
      </nav>

      <nav class="sidebar-bottom-nav" aria-label="설정 및 이용가이드">
        <RouterLink to="/settings" class="nav-link utility-link">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z" />
              <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.36a1.7 1.7 0 0 0-1 .58V20a2 2 0 1 1-4 0v-.08a1.7 1.7 0 0 0-1-.58 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.64 15a1.7 1.7 0 0 0-.58-1H4a2 2 0 1 1 0-4h.08a1.7 1.7 0 0 0 .58-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.64a1.7 1.7 0 0 0 1-.58V4a2 2 0 1 1 4 0v.08a1.7 1.7 0 0 0 1 .58 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.36 9c.2.35.39.69.58 1H20a2 2 0 1 1 0 4h-.08a1.7 1.7 0 0 0-.52 1Z" />
            </svg>
          </span>
          <span class="nav-text">설정</span>
        </RouterLink>

        <RouterLink to="/guide" class="nav-link utility-link">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z" />
              <path d="M12 8v5" />
              <path d="M12 16h.01" />
            </svg>
          </span>
          <span class="nav-text">이용가이드</span>
        </RouterLink>

        <RouterLink to="/upgrade-guide" class="nav-link utility-link">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M12 3 4 7l8 4 8-4-8-4Z" />
              <path d="m4 11 8 4 8-4" />
              <path d="m4 15 8 4 8-4" />
            </svg>
          </span>
          <span class="nav-text">승급가이드</span>
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
            <strong class="sidebar-nickname-line">
              <span :style="currentUserNicknameStyle">
                {{ authStore.user?.nickname || authStore.user?.username }}
              </span>
              <img
                v-if="authStore.user?.tier"
                :src="currentUserTierIcon"
                :alt="currentUserTierLabel"
                class="sidebar-tier-icon"
              />
            </strong>
            <span>{{ currentUserTierLabel }} · 기여도 {{ currentUserContribution }}</span>
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
                <span :style="currentUserNicknameStyle">
                  {{ authStore.user?.nickname || authStore.user?.username }}
                </span>
              </span>
              <img
                v-if="authStore.user?.tier"
                :src="currentUserTierIcon"
                :alt="currentUserTierLabel"
                class="global-tier-icon"
              />
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

      <aside
        class="route-mascot"
        :style="{
          '--mascot-run-x': mascotRunX,
          '--mascot-run-y': mascotRunY,
          '--mascot-run-mid-x': mascotRunMidX,
          '--mascot-run-mid-y': mascotRunMidY,
          '--mascot-run-near-x': mascotRunNearX,
          '--mascot-run-near-y': mascotRunNearY,
        }"
        :class="[
          `mascot-${activeMascotState.key}`,
          {
            'is-fetching': mascotFetchPhase === 'fetching',
            'is-carrying': mascotFetchPhase === 'carrying',
            'is-choice-menu-open': isMarkerChoiceMenuOpen,
          },
        ]"
        aria-live="polite"
      >
        <div class="mascot-speech">{{ activeMascotState.message }}</div>
        <div class="mascot-dog" aria-hidden="true" @click.stop="handleMascotClick">
          <span class="mascot-ear left"></span>
          <span class="mascot-ear right"></span>
          <span class="mascot-head">
            <span class="mascot-eye left"></span>
            <span class="mascot-eye right"></span>
            <span class="mascot-mouth"></span>
          </span>
          <span class="mascot-body">
            <span class="mascot-paw left"></span>
            <span class="mascot-paw right"></span>
          </span>
          <span class="mascot-tail"></span>
          <span class="mascot-fetch-bone">{{ mascotFetchedMarkerLabel }}</span>
          <span v-if="activeMascotState.prop" class="mascot-prop">{{ activeMascotState.prop }}</span>
        </div>
      </aside>

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
  background:
    radial-gradient(circle at 8% 10%, rgba(255, 255, 255, 0.95), transparent 30%),
    radial-gradient(circle at 88% 16%, rgba(255, 226, 187, 0.72), transparent 28%),
    linear-gradient(180deg, #fffaf1 0%, #f6f8f4 55%, #eef4ed 100%);
  color: #232323;
}

button,
input {
  font-family: inherit;
}

.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  background: transparent;
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
  border-right: 1px solid #eadfcd;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(255, 250, 241, 0.94)),
    #ffffff;
  box-shadow: 10px 0 30px rgba(49, 41, 31, 0.08);
  overflow: visible;
}

.brand {
  min-width: 0;
  display: flex;
  gap: 11px;
  align-items: center;
  padding: 0 6px;
  text-decoration: none;
}

.brand-mark {
  width: 48px;
  height: 60px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #222222;
  font-size: 14px;
  font-weight: 900;
  box-shadow: none;
}

.brand-pin {
  position: relative;
  width: 42px;
  height: 58px;
  display: grid;
  place-items: start center;
  filter: drop-shadow(0 4px 0 #dfc08f);
}

.brand-pin::before {
  position: absolute;
  top: 1px;
  left: 0;
  width: 42px;
  height: 42px;
  border: 3px solid #222222;
  border-radius: 50% 50% 50% 0;
  background: #d1a15e;
  content: "";
  transform: rotate(-45deg);
  transform-origin: 50% 50%;
}

.brand-pin::after {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 26px;
  height: 26px;
  border: 3px solid #222222;
  border-radius: 50%;
  background: #fffdf8;
  content: "";
}

.brand-dog {
  position: relative;
  z-index: 1;
  width: 22px;
  height: 22px;
  margin-top: 12px;
  border: 0;
  border-radius: 48% 48% 44% 44%;
  background: #ffffff;
}

.brand-dog-ear {
  position: absolute;
  top: -2px;
  z-index: 0;
  width: 9px;
  height: 8px;
  border: 2px solid #222222;
  border-radius: 58% 48% 58% 48%;
  background: #ffffff;
}

.brand-dog-ear.left {
  left: -5px;
  transform: rotate(-28deg);
}

.brand-dog-ear.right {
  right: -5px;
  transform: rotate(28deg);
}

.brand-dog-eye {
  position: absolute;
  top: 7px;
  z-index: 1;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #111111;
}

.brand-dog-eye.left {
  left: 6px;
}

.brand-dog-eye.right {
  right: 6px;
}

.brand-dog-nose {
  position: absolute;
  left: 50%;
  top: 12px;
  z-index: 1;
  width: 5px;
  height: 3px;
  border-radius: 50% 50% 45% 45%;
  background: #111111;
  transform: translateX(-50%);
}

.brand-dog-mouth {
  position: absolute;
  left: 50%;
  bottom: 3px;
  z-index: 1;
  width: 8px;
  height: 4px;
  border-bottom: 2px solid #111111;
  border-radius: 0 0 9px 9px;
  transform: translateX(-50%);
}

.brand-dog-cheek {
  display: none;
}

.brand-dog-cheek.left {
  left: 1px;
}

.brand-dog-cheek.right {
  right: 1px;
}

.brand-text {
  min-width: 0;
  display: block;
}

.brand strong {
  color: #222222;
  font-family:
    "Comic Sans MS",
    "Segoe Print",
    "Cafe24Ssurround",
    "BM JUA",
    "Malgun Gothic",
    sans-serif;
  font-size: 21px;
  font-weight: 900;
  line-height: 1.15;
  letter-spacing: 0;
}

.brand .brand-mark {
  color: inherit;
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
  border: 1px solid #222222;
  border-left-color: #fffaf1;
  border-radius: 0 8px 8px 0;
  background: #ffffff;
  color: #222222;
  cursor: pointer;
  transform: translateY(-50%);
  box-shadow: 5px 0 14px rgba(20, 35, 70, 0.16);
}

.sidebar-toggle:hover {
  background: #fff1d8;
  color: #222222;
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

.sidebar-bottom-nav {
  margin-top: auto;
  margin-bottom: -12px;
  padding-top: 10px;
  display: grid;
  gap: 4px;
  border-top: 1px solid #eadfcd;
}

.utility-link {
  padding-top: 9px;
  padding-bottom: 9px;
  color: #4f4a44;
}

.sidebar-profile {
  position: relative;
  margin-top: 0;
  min-height: 58px;
  padding: 8px 10px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  border-top: 1px solid #eadfcd;
  background: #fffaf1;
  border-radius: 14px;
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
  color: #222222;
  font-size: 13px;
  font-weight: 900;
}

.sidebar-nickname-line {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.sidebar-tier-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  object-fit: contain;
}

.sidebar-profile-copy span {
  color: #7b7166;
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
  border: 1px solid #eadfcd;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 18px 40px rgba(49, 41, 31, 0.14);
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
  color: #3b3834;
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
  background: #fff1d8;
  color: #222222;
}

.nav-link.router-link-active {
  background: #222222;
  color: #ffffff;
  box-shadow: 0 4px 0 #f2d7b0;
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

.app-shell.is-sidebar-collapsed .sidebar-profile-copy {
  display: none;
}

.app-shell.is-sidebar-collapsed .sidebar-bottom-nav {
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

.route-mascot {
  position: fixed;
  right: 28px;
  bottom: 24px;
  z-index: 70;
  width: 150px;
  pointer-events: none;
  transform-origin: right bottom;
  will-change: transform;
}

.mascot-speech {
  position: relative;
  margin: 0 0 8px auto;
  width: max-content;
  max-width: 190px;
  padding: 9px 12px;
  border: 2px solid #222222;
  border-radius: 14px;
  background: #ffffff;
  color: #222222;
  font-size: 12px;
  font-weight: 900;
  line-height: 1.35;
  box-shadow: 0 5px 0 #f2d7b0;
}

.mascot-speech::after {
  position: absolute;
  right: 28px;
  bottom: -9px;
  width: 14px;
  height: 14px;
  border-right: 2px solid #222222;
  border-bottom: 2px solid #222222;
  background: #ffffff;
  content: "";
  transform: rotate(45deg);
}

.mascot-dog {
  position: relative;
  width: 118px;
  height: 138px;
  margin-left: auto;
  transform-origin: 50% 88%;
  animation: mascot-idle 2.8s ease-in-out infinite;
}

.mascot-dog::before {
  position: absolute;
  inset: 0;
  z-index: 8;
  display: none;
  background-image: url("/mascot-run/dog-run-1.png");
  background-position: center;
  background-repeat: no-repeat;
  background-size: contain;
  content: "";
}

.mascot-head,
.mascot-body,
.mascot-ear,
.mascot-tail,
.mascot-paw {
  position: absolute;
  border: 4px solid #222222;
  background: #ffffff;
}

.mascot-head {
  top: 7px;
  left: 22px;
  z-index: 3;
  width: 78px;
  height: 82px;
  border-radius: 42% 46% 44% 40%;
}

.mascot-ear.left {
  top: 18px;
  left: 8px;
  z-index: 2;
  width: 42px;
  height: 26px;
  border-radius: 60% 36% 46% 52%;
  transform: rotate(-16deg);
}

.mascot-ear.right {
  top: 3px;
  right: 3px;
  z-index: 2;
  width: 52px;
  height: 30px;
  border-radius: 46% 60% 48% 42%;
  transform: rotate(17deg);
}

.mascot-eye {
  position: absolute;
  top: 33px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #222222;
}

.mascot-eye.left {
  left: 21px;
}

.mascot-eye.right {
  right: 22px;
}

.mascot-mouth {
  position: absolute;
  left: 36px;
  bottom: 19px;
  width: 18px;
  height: 12px;
  border-bottom: 3px solid #222222;
  border-radius: 0 0 12px 12px;
}

.mascot-mouth::before {
  position: absolute;
  top: -4px;
  left: 5px;
  width: 6px;
  height: 4px;
  border-radius: 50%;
  background: #222222;
  content: "";
}

.mascot-body {
  left: 31px;
  bottom: 0;
  z-index: 1;
  width: 66px;
  height: 68px;
  border-radius: 46% 44% 30% 30%;
}

.mascot-paw {
  bottom: -4px;
  z-index: 4;
  width: 18px;
  height: 27px;
  border-top: 0;
  border-radius: 0 0 12px 12px;
}

.mascot-paw.left {
  left: 45px;
}

.mascot-paw.right {
  right: 29px;
}

.mascot-tail {
  left: 8px;
  bottom: 15px;
  z-index: 0;
  width: 36px;
  height: 22px;
  border-right: 0;
  border-radius: 18px 0 0 18px;
  transform-origin: 100% 50%;
  animation: mascot-tail 0.8s ease-in-out infinite;
}

.mascot-prop {
  position: absolute;
  right: 4px;
  bottom: 42px;
  z-index: 6;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 3px solid #222222;
  border-radius: 12px;
  background: #fff1d8;
  color: #222222;
  font-size: 18px;
  font-weight: 900;
  box-shadow: 0 4px 0 #f2d7b0;
}

.mascot-fetch-bone {
  position: absolute;
  right: 7px;
  bottom: 39px;
  z-index: 7;
  display: none;
  width: 54px;
  height: 54px;
  place-items: center;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cg transform='rotate(-45 32 32)'%3E%3Cpath d='M21 18c-5.4-5.4-14.6-1.6-14.6 6.2 0 3.1 1.6 5.9 4.1 7.5-2.5 1.6-4.1 4.4-4.1 7.5 0 7.8 9.2 11.6 14.6 6.2l3.6-3.6h14.8l3.6 3.6c5.4 5.4 14.6 1.6 14.6-6.2 0-3.1-1.6-5.9-4.1-7.5 2.5-1.6 4.1-4.4 4.1-7.5 0-7.8-9.2-11.6-14.6-6.2l-3.6 3.6H24.6L21 18Z' fill='white' stroke='%23222222' stroke-width='4' stroke-linejoin='round'/%3E%3C/g%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-size: contain;
  color: #222222;
  filter: drop-shadow(0 3px 0 rgba(242, 215, 176, 0.9));
  font-family: Arial, sans-serif;
  font-size: 16px;
  font-weight: 900;
  line-height: 1;
  text-shadow:
    -1px -1px 0 #ffffff,
    1px -1px 0 #ffffff,
    -1px 1px 0 #ffffff,
    1px 1px 0 #ffffff;
  transform: rotate(-8deg);
  transform-origin: 18px 28px;
}

.route-mascot.is-fetching {
  animation: mascot-run-to-marker 1.1s cubic-bezier(0.45, 0.02, 0.22, 1) forwards;
}

.route-mascot.is-carrying {
  z-index: 2;
  transform: translate(var(--mascot-run-x, -36vw), calc(var(--mascot-run-y, -17vh) - 10px));
  transition: transform 0.16s ease-out;
}

.route-mascot.is-carrying .mascot-dog {
  cursor: pointer;
  pointer-events: auto;
}

.route-mascot.is-choice-menu-open {
  z-index: 0;
}

.route-mascot.is-choice-menu-open .mascot-dog {
  pointer-events: none;
}

.route-mascot.is-fetching .mascot-speech,
.route-mascot.is-carrying .mascot-speech {
  display: none;
}

.route-mascot.is-fetching .mascot-dog {
  width: 176px;
  height: 176px;
  margin-right: -18px;
  animation: none;
}

.route-mascot.is-carrying .mascot-dog {
  transform-origin: 100% 100%;
  animation: mascot-chew 0.72s ease-in-out infinite;
}

.route-mascot.is-fetching .mascot-dog::before {
  display: block;
  animation: mascot-run-frame 0.54s steps(1, end) infinite;
}

.route-mascot.is-fetching .mascot-dog > span {
  opacity: 0;
}

.route-mascot.is-carrying .mascot-fetch-bone {
  display: grid;
}

.route-mascot.is-carrying .mascot-fetch-bone {
  animation: mascot-bone-chew 0.48s ease-in-out infinite;
}

.route-mascot.is-fetching .mascot-prop,
.route-mascot.is-carrying .mascot-prop {
  display: none;
}

.mascot-home .mascot-dog {
  animation-name: mascot-sniff;
}

.mascot-map .mascot-dog {
  animation-name: mascot-hop;
}

.mascot-board .mascot-prop,
.mascot-guide .mascot-prop {
  background: #e9f6ff;
}

.mascot-write .mascot-prop,
.mascot-mypage .mascot-prop {
  background: #ffe8ef;
}

.mascot-settings .mascot-prop,
.mascot-admin .mascot-prop {
  background: #eeeeee;
}

.mascot-guide .mascot-paw.right,
.mascot-mypage .mascot-paw.right,
.mascot-auth .mascot-paw.right {
  animation: mascot-wave 0.9s ease-in-out infinite;
  transform-origin: 50% 0;
}

.mascot-board .mascot-head {
  animation: mascot-read 1.8s ease-in-out infinite;
}

.mascot-inquiry .mascot-ear.left {
  animation: mascot-listen 1.1s ease-in-out infinite;
}

@keyframes mascot-idle {
  50% {
    transform: translateY(-5px);
  }
}

@keyframes mascot-sniff {
  50% {
    transform: translateY(-3px) rotate(-3deg);
  }
}

@keyframes mascot-hop {
  45% {
    transform: translateY(-12px);
  }
}

@keyframes mascot-tail {
  50% {
    transform: rotate(-12deg);
  }
}

@keyframes mascot-wave {
  50% {
    transform: rotate(-22deg);
  }
}

@keyframes mascot-read {
  50% {
    transform: rotate(3deg);
  }
}

@keyframes mascot-listen {
  50% {
    transform: rotate(-24deg) translateY(2px);
  }
}

@keyframes mascot-run-to-marker {
  0% {
    transform: translate(0, 0) scale(1);
  }

  42% {
    transform: translate(var(--mascot-run-mid-x, -18vw), var(--mascot-run-mid-y, -9vh)) scale(1.04);
  }

  72% {
    transform: translate(var(--mascot-run-near-x, -30vw), var(--mascot-run-near-y, -14vh)) scale(0.98);
  }

  100% {
    transform: translate(var(--mascot-run-x, -36vw), var(--mascot-run-y, -17vh)) scale(1);
  }
}

@keyframes mascot-run-frame {
  0%,
  100% {
    background-image: url("/mascot-run/dog-run-1.png");
  }

  16.67% {
    background-image: url("/mascot-run/dog-run-2.png");
  }

  33.33% {
    background-image: url("/mascot-run/dog-run-3.png");
  }

  50% {
    background-image: url("/mascot-run/dog-run-4.png");
  }

  66.67% {
    background-image: url("/mascot-run/dog-run-5.png");
  }

  83.33% {
    background-image: url("/mascot-run/dog-run-6.png");
  }
}

@keyframes mascot-chew {
  0%,
  100% {
    transform: scale(0.5);
  }

  45% {
    transform: translateY(-5px) rotate(-2deg) scale(0.5);
  }

  70% {
    transform: translateY(-2px) rotate(2deg) scale(0.5);
  }
}

@keyframes mascot-bone-chew {
  45% {
    transform: rotate(-2deg) translate(1px, 1px);
  }

  80% {
    transform: rotate(-11deg) translate(-1px, -1px);
  }
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

.board-page,
.mypage,
.guide-page,
.upgrade-page,
.page,
.settings-page,
.login-page,
.signup-page {
  background:
    radial-gradient(circle at 12% 10%, rgba(255, 238, 209, 0.82), transparent 30%),
    radial-gradient(circle at 88% 14%, rgba(233, 246, 255, 0.72), transparent 28%),
    linear-gradient(180deg, #fffaf1 0%, #f8f6ef 100%) !important;
}

.board-container,
.mypage-container,
.guide-container,
.upgrade-container,
.page-container {
  position: relative;
}

.board-table-wrap,
.post-detail-card,
.profile-card,
.panel,
.guide-board,
.score-rule-panel,
.tier-section,
.status-card,
.board-table-wrap,
.notification-dropdown,
.account-dropdown {
  border-color: #222222 !important;
}

.board-table-wrap,
.post-detail-card,
.profile-card,
.panel,
.guide-board,
.score-rule-panel,
.tier-section,
.status-card {
  border-width: 2px !important;
  box-shadow: 0 7px 0 #f2d7b0 !important;
}

.write-button,
.back-button,
.summary-card,
.account-menu-button,
.account-logout-button {
  border-radius: 12px;
}

.write-button,
.comment-form button,
.comment-save-button,
.modal-submit-button {
  background: #222222 !important;
  color: #ffffff !important;
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
  border: 2px solid #222222;
  border-radius: 999px;
  background: #ffffff;
  color: #222222;
  text-decoration: none;
  box-shadow: 0 5px 0 #f2d7b0;
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
  border: 2px solid #222222;
  border-radius: 999px;
  background: #ffffff;
  color: #222222;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
  cursor: pointer;
  box-shadow: 0 5px 0 #f2d7b0;
  backdrop-filter: blur(8px);
}

.global-user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-tier-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  object-fit: contain;
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
  border: 1px solid rgba(255, 255, 255, 0.64);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18px 40px rgba(0, 25, 34, 0.2);
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
  border: 2px solid #222222;
  border-radius: 999px;
  background: #ffffff;
  color: #222222;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
  cursor: pointer;
  box-shadow: 0 5px 0 #f2d7b0;
  backdrop-filter: blur(8px);
}

.global-auth-button.signup {
  border-color: #222222;
  background: #222222;
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

  .sidebar-bottom-nav,
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

  .route-mascot {
    right: 12px;
    bottom: 12px;
    width: 118px;
    transform: scale(0.82);
    transform-origin: right bottom;
  }

  .route-mascot.is-fetching {
    animation-name: mascot-run-to-marker-mobile;
  }

  .route-mascot.is-carrying {
    z-index: 2;
    transform: translate(var(--mascot-run-x, -18vw), calc(var(--mascot-run-y, -13vh) - 8px)) scale(0.82);
  }

  @keyframes mascot-run-to-marker-mobile {
    0% {
      transform: translate(0, 0) scale(0.82);
    }

    48% {
      transform: translate(var(--mascot-run-mid-x, -9vw), var(--mascot-run-mid-y, -7vh)) scale(0.86);
    }

    100% {
      transform: translate(var(--mascot-run-x, -18vw), var(--mascot-run-y, -13vh)) scale(0.82);
    }
  }
}
</style>
