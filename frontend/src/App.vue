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
const selectedNotification = ref(null)
const notificationMenuRef = ref(null)
const accountMenuRef = ref(null)
const sidebarProfileRef = ref(null)
const mascotFetchPhase = ref('')
const mascotFetchedPlaceId = ref(null)
const mascotFetchedPlaceName = ref('')
const mascotFetchedMarkerLabel = ref('')
const isMarkerChoiceMenuOpen = ref(false)
const isMascotSearchLoading = ref(false)
const mascotSearchMessage = ref('')
const mascotRunX = ref('-36vw')
const mascotRunY = ref('-17vh')
const mascotRunMidX = ref('-18vw')
const mascotRunMidY = ref('-9vh')
const mascotRunNearX = ref('-30vw')
const mascotRunNearY = ref('-14vh')
let notificationTimer = null
let mascotFetchTimer = null
const TIER_UP_NOTIFICATION_TITLE = '등급 승급 안내'
const handledTierUpNotificationIds = new Set()
const notificationDetailTypes = new Set([
  'admin_warning',
  'penalty_notice',
  'report_passed',
  'report_penalty',
])

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

const mascotTierValues = new Set([
  'iron',
  'bronze',
  'silver',
  'gold',
  'platinum',
  'diamond',
  'master',
  'challenger',
])

const currentMascotTier = computed(() => {
  const tier = String(authStore.user?.tier || '').toLowerCase()

  return mascotTierValues.has(tier) ? tier : 'iron'
})

const currentMascotImageStyle = computed(() => {
  if (!authStore.isLoggedIn) {
    return {
      '--mascot-idle-image': 'none',
      '--mascot-run-1': 'url("/mascot-run/dog-run-1.png")',
      '--mascot-run-2': 'url("/mascot-run/dog-run-2.png")',
      '--mascot-run-3': 'url("/mascot-run/dog-run-3.png")',
      '--mascot-run-4': 'url("/mascot-run/dog-run-4.png")',
      '--mascot-run-5': 'url("/mascot-run/dog-run-5.png")',
      '--mascot-run-6': 'url("/mascot-run/dog-run-6.png")',
    }
  }

  const basePath = `/mascot-tiers/${currentMascotTier.value}`

  return {
    '--mascot-idle-image': `url("${basePath}/idle.png")`,
    '--mascot-run-1': `url("${basePath}/run-1.png")`,
    '--mascot-run-2': `url("${basePath}/run-2.png")`,
    '--mascot-run-3': `url("${basePath}/run-3.png")`,
    '--mascot-run-4': `url("${basePath}/run-4.png")`,
    '--mascot-run-5': `url("${basePath}/run-5.png")`,
    '--mascot-run-6': `url("${basePath}/run-6.png")`,
  }
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

  if (isMascotSearchLoading.value) {
    return {
      key: 'searching',
      prop: '',
      message: mascotSearchMessage.value || '조건에 맞는 장소 찾는 중',
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

const getNotificationTypeLabel = (notification) => {
  const labels = {
    admin_warning: '관리자 메시지',
    penalty_notice: '제재 안내',
    report_passed: '신고 검토 결과',
    report_penalty: '신고 처리 결과',
    inquiry_answered: '문의 답변',
    post_commented: '댓글 알림',
    post_liked: '좋아요 알림',
    comment_liked: '댓글 좋아요',
    system: '시스템 알림',
  }

  return labels[notification?.notification_type] || '알림'
}

const shouldOpenNotificationDetail = (notification) => {
  return notificationDetailTypes.has(notification?.notification_type)
}

const getNotificationIconType = (notification) => {
  const type = notification?.notification_type

  if (type === 'post_commented') {
    return 'comment'
  }

  if (type === 'post_liked' || type === 'comment_liked') {
    return 'like'
  }

  if (type === 'report_passed' || type === 'report_penalty') {
    return 'report'
  }

  if (notification?.title === TIER_UP_NOTIFICATION_TITLE) {
    return 'tier-up'
  }

  if (type === 'penalty_notice') {
    return 'penalty'
  }

  if (type === 'admin_warning') {
    return 'admin'
  }

  if (type === 'inquiry_answered') {
    return 'message'
  }

  return 'system'
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
    const fetchedNotifications = response.data
    notifications.value = fetchedNotifications

    const newTierUpNotifications = fetchedNotifications.filter((notification) => {
      const notificationKey = notification.id ?? `${notification.created_at}-${notification.message}`
      return (
        !notification.is_read
        && notification.title === TIER_UP_NOTIFICATION_TITLE
        && !handledTierUpNotificationIds.has(notificationKey)
      )
    })

    if (newTierUpNotifications.length > 0) {
      newTierUpNotifications.forEach((notification) => {
        const notificationKey = notification.id ?? `${notification.created_at}-${notification.message}`
        handledTierUpNotificationIds.add(notificationKey)
      })
      await authStore.fetchMe()
    }
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

  if (shouldOpenNotificationDetail(notification)) {
    selectedNotification.value = notification
    return
  }

  if (notification.notification_type === 'inquiry_answered') {
    router.push('/inquiries/my')
    return
  }

  router.push(notification.target_route || '/')
}

const closeNotificationDetail = () => {
  selectedNotification.value = null
}

const moveToSelectedNotificationTarget = () => {
  const targetRoute = selectedNotification.value?.target_route

  closeNotificationDetail()

  if (targetRoute) {
    router.push(targetRoute)
  }
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

  notificationTimer = window.setInterval(fetchNotifications, 10000)
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

const handleSearchLoadingChange = (event) => {
  isMascotSearchLoading.value = Boolean(event.detail?.isSearching)
  mascotSearchMessage.value = event.detail?.message || ''
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
  window.addEventListener('place-marker-fetch', triggerMascotFetch)
  window.addEventListener('place-marker-fetch-update', updateMascotFetchTarget)
  window.addEventListener('place-marker-fetch-clear', clearMascotFetch)
  window.addEventListener('place-marker-choice-open', handleMarkerChoiceMenuOpen)
  window.addEventListener('place-marker-choice-close', handleMarkerChoiceMenuClose)
  window.addEventListener('search-loading-change', handleSearchLoadingChange)

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
  window.removeEventListener('search-loading-change', handleSearchLoadingChange)
  clearMascotFetch()

  if (notificationTimer) {
    window.clearInterval(notificationTimer)
  }
})
</script>

<template>
  <div
    class="app-shell"
    :class="{
      'is-compact-mode': settingsStore.compactMode,
    }"
  >
    <header class="app-header">
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

      <nav class="side-nav top-nav" aria-label="페이지 이동">
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

      <nav class="sidebar-bottom-nav top-utility-nav" aria-label="설정 및 이용가이드">
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
                  <span class="notification-icon-wrap" :class="getNotificationIconType(notification)" aria-hidden="true">
                    <svg
                      v-if="getNotificationIconType(notification) === 'comment'"
                      class="notification-comment-icon"
                      viewBox="0 0 24 24"
                    >
                      <path class="notification-comment-bubble" d="M4.7 16.1A8.5 8.5 0 0 1 3 11.1C3 6.4 7.1 2.8 12.2 2.8s9.2 3.6 9.2 8.3-4.1 8.3-9.2 8.3a10.4 10.4 0 0 1-3.7-.7 6.7 6.7 0 0 1-4.5 2l-.8-.1.5-.7a6.7 6.7 0 0 0 1-3.8Z" />
                      <path class="notification-comment-dot" d="M8.2 11.2h.1M12.2 11.2h.1M16.2 11.2h.1" />
                    </svg>
                    <span v-else-if="getNotificationIconType(notification) === 'like'" class="notification-like-icon">♥</span>
                    <svg v-else-if="getNotificationIconType(notification) === 'report'" viewBox="0 0 24 24">
                      <path d="M6 11a6 6 0 0 1 12 0v4l2 3H4l2-3v-4Z" />
                      <path d="M10 21h4" />
                      <path d="M4 6 2.5 4.5" />
                      <path d="M20 6 21.5 4.5" />
                      <path d="M9 3.5 8.2 1.8" />
                      <path d="M15 3.5l.8-1.7" />
                    </svg>
                    <svg v-else-if="getNotificationIconType(notification) === 'tier-up'" viewBox="0 0 24 24">
                      <path d="M7 12.5 4.5 10a1.6 1.6 0 0 0-2.2 2.3l4.1 4.1" />
                      <path d="M10.5 8.5 8 6a1.6 1.6 0 0 0-2.2 2.3l4.2 4.2" />
                      <path d="M14 7.5 11.5 5a1.6 1.6 0 0 0-2.2 2.3l4.2 4.2" />
                      <path d="M17.2 9.3 15.5 7.6a1.6 1.6 0 0 0-2.2 2.3l2.8 2.8" />
                      <path d="M7.5 16.5c2.8 3 6.5 3.9 9.2 1.2 1.8-1.8 2-4.4.8-6.7" />
                      <path d="M19.5 5.5 21 4" />
                      <path d="M20.8 9h2" />
                      <path d="M16.8 3.2l.5-2" />
                    </svg>
                    <svg v-else-if="getNotificationIconType(notification) === 'penalty'" viewBox="0 0 24 24">
                      <path d="M12 3 20 7v5c0 5-3.4 8-8 9-4.6-1-8-4-8-9V7l8-4Z" />
                      <path d="M9 9l6 6" />
                      <path d="M15 9l-6 6" />
                    </svg>
                    <svg v-else-if="getNotificationIconType(notification) === 'admin'" viewBox="0 0 24 24">
                      <path d="M12 3 20 7v5c0 5-3.4 8-8 9-4.6-1-8-4-8-9V7l8-4Z" />
                      <path d="M9 12h6" />
                      <path d="M12 9v6" />
                    </svg>
                    <svg v-else-if="getNotificationIconType(notification) === 'message'" viewBox="0 0 24 24">
                      <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z" />
                      <path d="M8 9h8" />
                      <path d="M8 13h5" />
                    </svg>
                    <svg v-else viewBox="0 0 24 24">
                      <path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z" />
                      <path d="M12 8v5" />
                      <path d="M12 16h.01" />
                    </svg>
                    <span v-if="!notification.is_read" class="notification-dot"></span>
                  </span>
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
    </header>

    <div
      v-if="selectedNotification"
      class="notification-detail-backdrop"
      role="presentation"
      @click.self="closeNotificationDetail"
    >
      <section
        class="notification-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="notification-detail-title"
      >
        <header class="notification-detail-header">
          <div>
            <span>{{ getNotificationTypeLabel(selectedNotification) }}</span>
            <h2 id="notification-detail-title">{{ selectedNotification.title }}</h2>
          </div>
          <button type="button" class="notification-detail-close" aria-label="알림 상세 닫기" @click="closeNotificationDetail">
            ×
          </button>
        </header>

        <p class="notification-detail-message">{{ selectedNotification.message }}</p>

        <footer class="notification-detail-footer">
          <time>{{ formatNotificationTime(selectedNotification.created_at) }}</time>
          <div class="notification-detail-actions">
            <button type="button" class="notification-detail-button secondary" @click="closeNotificationDetail">
              닫기
            </button>
            <button
              v-if="selectedNotification.target_route"
              type="button"
              class="notification-detail-button primary"
              @click="moveToSelectedNotificationTarget"
            >
              관련 글 보기
            </button>
          </div>
        </footer>
      </section>
    </div>

    <div class="app-main">
      <aside
        class="route-mascot"
        :style="{
          ...currentMascotImageStyle,
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
            'is-tier-mascot': authStore.isLoggedIn,
            'is-fetching': mascotFetchPhase === 'fetching',
            'is-carrying': mascotFetchPhase === 'carrying',
            'is-search-loading': isMascotSearchLoading && !mascotFetchPhase,
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
          <span class="mascot-collar">
            <span class="mascot-pendant"></span>
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
  position: relative;
  min-height: 100vh;
  display: block;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.18), rgba(255, 250, 241, 0.34)),
    url("/homepage-background.png") center / cover no-repeat fixed;
}

.app-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 80;
  min-height: 76px;
  padding: 10px 24px;
  display: flex;
  gap: 18px;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.34);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.34), rgba(255, 255, 255, 0.08));
  box-shadow: none;
  overflow: visible;
  backdrop-filter: blur(14px);
}

.brand {
  min-width: max-content;
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
  min-width: 0;
  display: flex;
  gap: 8px;
  align-items: center;
  overflow-x: auto;
  scrollbar-width: none;
}

.side-nav::-webkit-scrollbar {
  display: none;
}

.sidebar-bottom-nav {
  display: flex;
  gap: 6px;
  align-items: center;
}

.top-nav {
  flex: 1 1 auto;
}

.top-utility-nav {
  flex: 0 0 auto;
  padding-left: 12px;
  border-left: 1px solid #eadfcd;
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
  width: auto;
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

.app-main {
  min-width: 0;
  position: relative;
  padding-top: 96px;
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

.route-mascot.is-tier-mascot .mascot-dog {
  width: 132px;
  height: 152px;
}

.mascot-dog::before {
  position: absolute;
  inset: 0;
  z-index: 8;
  display: none;
  background-image: var(--mascot-run-1);
  background-position: center;
  background-repeat: no-repeat;
  background-size: contain;
  content: "";
}

.mascot-dog::after {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: none;
  background-image: var(--mascot-idle-image);
  background-position: center;
  background-repeat: no-repeat;
  background-size: contain;
  content: "";
  pointer-events: none;
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

.mascot-head,
.mascot-body,
.mascot-ear,
.mascot-tail,
.mascot-paw,
.mascot-collar {
  opacity: 0;
}

.route-mascot.is-tier-mascot .mascot-dog::after {
  display: block;
}

.route-mascot:not(.is-tier-mascot) .mascot-head,
.route-mascot:not(.is-tier-mascot) .mascot-body,
.route-mascot:not(.is-tier-mascot) .mascot-ear,
.route-mascot:not(.is-tier-mascot) .mascot-tail,
.route-mascot:not(.is-tier-mascot) .mascot-paw {
  opacity: 1;
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

.mascot-collar {
  position: absolute;
  top: 75px;
  left: 20px;
  z-index: 5;
  width: 96px;
  height: 74px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 180 140'%3E%3Cpath d='M28 25 C61 49 119 49 152 25 L158 48 C121 79 59 79 22 48 Z' fill='%230d47a1' stroke='%23222222' stroke-width='8' stroke-linejoin='round'/%3E%3Cpath d='M30 27 C62 48 118 48 150 27' fill='none' stroke='%23f6bf49' stroke-width='5' stroke-linecap='round'/%3E%3Cpath d='M25 48 C61 78 119 78 155 48' fill='none' stroke='%23f6bf49' stroke-width='5' stroke-linecap='round'/%3E%3Cpath d='M82 67 L98 67 L98 94 L82 94 Z' fill='%23f6bf49' stroke='%23222222' stroke-width='7' stroke-linejoin='round'/%3E%3Ccircle cx='90' cy='104' r='31' fill='%23062e6f' stroke='%23222222' stroke-width='8'/%3E%3Ccircle cx='90' cy='104' r='25' fill='%2308337b' stroke='%23f6bf49' stroke-width='5'/%3E%3Cpath d='M90 72 C95 91 104 99 123 104 C104 109 95 117 90 136 C85 117 76 109 57 104 C76 99 85 91 90 72 Z' fill='%23f6bf49' stroke='%2301183d' stroke-width='3' stroke-linejoin='round'/%3E%3Cpath d='M90 84 L101 104 L90 125 L79 104 Z' fill='%232fd7ff' stroke='%23ffffff' stroke-width='3' stroke-linejoin='round'/%3E%3Cpath d='M72 104 L90 95 L108 104 L90 113 Z' fill='%23005bd8' opacity='0.95'/%3E%3Cpath d='M90 84 L90 125 M79 104 L101 104' stroke='%2301183d' stroke-width='2' stroke-linecap='round' opacity='0.8'/%3E%3C/svg%3E");
  background-position: center;
  background-repeat: no-repeat;
  background-size: contain;
  pointer-events: none;
}

.mascot-pendant {
  display: none;
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

.route-mascot.is-search-loading {
  z-index: 64;
  animation: mascot-search-orbit 16s linear infinite;
}

.route-mascot.is-search-loading .mascot-dog {
  width: 176px;
  height: 176px;
  margin-right: -18px;
  animation: mascot-search-run-bob 1.8s ease-in-out infinite;
}

.route-mascot.is-search-loading .mascot-dog::before {
  display: block;
  animation: mascot-run-frame 0.72s steps(1, end) infinite;
}

.route-mascot.is-search-loading .mascot-dog::after {
  display: none;
}

.route-mascot.is-search-loading .mascot-dog > span {
  opacity: 0;
}

.route-mascot.is-search-loading .mascot-tail {
  animation-duration: 0.55s;
}

.route-mascot.is-search-loading .mascot-prop,
.route-mascot.is-search-loading .mascot-fetch-bone {
  display: none;
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

.route-mascot.is-fetching .mascot-dog::after {
  display: none;
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

@keyframes mascot-search-orbit {
  0% {
    transform: translate(0, 0) scale(1);
  }

  8% {
    transform: translate(-13vw, -6vh) scale(1.01);
  }

  17% {
    transform: translate(-32vw, -10vh) scale(1.03);
  }

  25% {
    transform: translate(-52vw, -19vh) scale(1.01);
  }

  33% {
    transform: translate(-66vw, -34vh) scale(0.98);
  }

  42% {
    transform: translate(-59vw, -50vh) scale(0.96);
  }

  50% {
    transform: translate(-39vw, -59vh) scale(0.97);
  }

  58% {
    transform: translate(-18vw, -54vh) scale(1);
  }

  67% {
    transform: translate(-7vw, -39vh) scale(1.02);
  }

  75% {
    transform: translate(-12vw, -23vh) scale(1.03);
  }

  84% {
    transform: translate(-25vw, -11vh) scale(1.01);
  }

  92% {
    transform: translate(-10vw, -4vh) scale(1);
  }

  100% {
    transform: translate(0, 0) scale(1);
  }
}

@keyframes mascot-search-run-bob {
  50% {
    transform: translateY(-6px) rotate(-2deg);
  }
}

@keyframes mascot-run-frame {
  0%,
  100% {
    background-image: var(--mascot-run-1);
  }

  16.67% {
    background-image: var(--mascot-run-2);
  }

  33.33% {
    background-image: var(--mascot-run-3);
  }

  50% {
    background-image: var(--mascot-run-4);
  }

  66.67% {
    background-image: var(--mascot-run-5);
  }

  83.33% {
    background-image: var(--mascot-run-6);
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
.preference-page,
.login-page,
.signup-page,
.auth-page,
.notification-page,
.admin-board-page,
.admin-report-page,
.profile-page,
.reports-page,
.history-page,
.report-page,
.place-report-page {
  background: transparent !important;
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
  position: relative;
  z-index: 1;
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
  align-items: center;
  max-width: none;
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
  padding: 14px 16px;
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
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

.notification-icon-wrap {
  position: relative;
  width: 28px;
  height: 28px;
  display: inline-grid;
  place-items: center;
  color: #d4d4d8;
}

.notification-icon-wrap svg {
  width: 23px;
  height: 23px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
  overflow: visible;
}

.notification-icon-wrap.comment svg {
  width: 24px;
  height: 24px;
}

.notification-comment-bubble {
  fill: #83c5e8;
  stroke: #25305f;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}

.notification-comment-dot {
  fill: none;
  stroke: #ffffff;
  stroke-linecap: round;
  stroke-width: 2.8;
}

.notification-like-icon {
  color: #f26f82;
  font-size: 24px;
  line-height: 1;
}

.notification-icon-wrap.report {
  color: #f97316;
}

.notification-icon-wrap.tier-up {
  color: #facc15;
}

.notification-icon-wrap.penalty {
  color: #ef4444;
}

.notification-icon-wrap.admin {
  color: #60a5fa;
}

.notification-icon-wrap.message {
  color: #34d399;
}

.notification-icon-wrap.system {
  color: #a1a1aa;
}

.notification-dot {
  position: absolute;
  top: -1px;
  right: -1px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #3b82f6;
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

.notification-detail-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(17, 24, 39, 0.46);
  backdrop-filter: blur(5px);
}

.notification-detail-modal {
  width: min(480px, 100%);
  max-height: min(560px, calc(100vh - 40px));
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
  border: 2px solid #222222;
  border-radius: 14px;
  background: #ffffff;
  color: #222222;
  box-shadow: 0 18px 0 rgba(242, 215, 176, 0.92), 0 28px 80px rgba(0, 0, 0, 0.24);
}

.notification-detail-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px 16px;
  border-bottom: 1px solid #e5e7eb;
}

.notification-detail-header span {
  display: block;
  margin-bottom: 6px;
  color: #2563eb;
  font-size: 12px;
  font-weight: 900;
}

.notification-detail-header h2 {
  margin: 0;
  color: #111827;
  font-size: 20px;
  line-height: 1.35;
  word-break: keep-all;
  overflow-wrap: anywhere;
}

.notification-detail-close {
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border: 2px solid #222222;
  border-radius: 999px;
  background: #ffffff;
  color: #222222;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.notification-detail-message {
  margin: 0;
  min-height: 120px;
  overflow-y: auto;
  padding: 20px 22px;
  color: #374151;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.notification-detail-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 16px 22px 20px;
  border-top: 1px solid #e5e7eb;
}

.notification-detail-footer time {
  color: #6b7280;
  font-size: 12px;
  font-weight: 900;
  white-space: nowrap;
}

.notification-detail-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.notification-detail-button {
  min-height: 38px;
  padding: 0 14px;
  border: 2px solid #222222;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
}

.notification-detail-button.primary {
  background: #222222;
  color: #ffffff;
}

.notification-detail-button.secondary {
  background: #ffffff;
  color: #222222;
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
  display: inline-flex;
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

.global-auth-button.signup {
  border-color: #222222;
  background: #222222;
  color: #ffffff;
}

.global-auth-button.logout {
  background: #ffffff;
  color: #222222;
}

@media (min-width: 1025px) and (max-width: 1200px) {
  .app-header {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr) auto;
    gap: 8px 14px;
    align-items: center;
  }

  .brand {
    grid-column: 1;
    grid-row: 1;
  }

  .top-nav {
    grid-column: 2;
    grid-row: 1;
    width: 100%;
  }

  .top-nav .nav-link {
    flex: 0 0 auto;
  }

  .top-utility-nav {
    grid-column: 2 / -1;
    grid-row: 2;
    justify-content: flex-start;
    padding-left: 0;
    border-left: 0;
  }

  .global-account-bar {
    grid-column: 3;
    grid-row: 1;
    justify-self: end;
  }

  .app-main {
    padding-top: 136px;
  }
}

@media (max-width: 1024px) {
  .app-shell {
    min-height: 100vh;
  }

  .app-header {
    min-height: 0;
    padding: 10px 12px;
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 8px 10px;
  }

  .app-main {
    padding-top: 178px;
  }

  .global-account-bar {
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
  }

  .top-nav {
    grid-column: 1 / -1;
    width: 100%;
    padding-bottom: 2px;
  }

  .top-utility-nav {
    grid-column: 1 / -1;
    width: 100%;
    padding-left: 0;
    border-left: 0;
    overflow-x: visible;
  }

  .global-user-link {
    max-width: calc(100vw - 128px);
  }

  .sidebar-toggle {
    display: none;
  }

  .side-nav {
    flex-wrap: wrap;
    gap: 6px;
    overflow-x: visible;
  }

  .nav-link {
    flex: 0 0 auto;
    padding: 9px 10px;
    font-size: 13px;
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

  .route-mascot.is-search-loading {
    animation: mascot-search-orbit-mobile 14s linear infinite;
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

  @keyframes mascot-search-orbit-mobile {
    0% {
      transform: translate(0, 0) scale(0.82);
    }

    12% {
      transform: translate(-18vw, -5vh) scale(0.84);
    }

    25% {
      transform: translate(-48vw, -13vh) scale(0.83);
    }

    38% {
      transform: translate(-72vw, -30vh) scale(0.8);
    }

    50% {
      transform: translate(-56vw, -54vh) scale(0.78);
    }

    63% {
      transform: translate(-24vw, -59vh) scale(0.8);
    }

    76% {
      transform: translate(-8vw, -38vh) scale(0.83);
    }

    88% {
      transform: translate(-20vw, -12vh) scale(0.84);
    }

    100% {
      transform: translate(0, 0) scale(0.82);
    }
  }
}

@media (max-width: 640px) {
  .app-main {
    padding-top: 220px;
  }

  .nav-link {
    padding: 8px 9px;
  }
}
</style>
