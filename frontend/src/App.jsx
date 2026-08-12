import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import AppHeader from '@/components/layout/AppHeader'
import NotificationDetailModal from '@/components/layout/NotificationDetailModal'
import RouteMascot from '@/components/layout/RouteMascot'
import { useNotifications } from '@/hooks/useNotifications'
import { useRouteMascot } from '@/hooks/useRouteMascot'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'
import { shouldOpenNotificationDetail } from '@/utils/notificationFormat'

import '@/styles/app.css'

const App = () => {
  const location = useLocation()
  const navigate = useNavigate()

  const user = useAuthStore((state) => state.user)
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn)
  const logout = useAuthStore((state) => state.logout)
  const fetchMe = useAuthStore((state) => state.fetchMe)
  const clearAuthState = useAuthStore((state) => state.clearAuthState)
  const compactMode = useSettingsStore((state) => state.compactMode)

  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false)
  const [isNotificationMenuOpen, setIsNotificationMenuOpen] = useState(false)

  const notificationMenuRef = useRef(null)
  const accountMenuRef = useRef(null)
  const sidebarProfileRef = useRef(null)

  const {
    recentNotifications,
    unreadNotificationCount,
    selectedNotification,
    setSelectedNotification,
    fetchNotifications,
    markNotificationAsRead,
    markAllVisibleNotificationsAsRead,
    findNotificationById,
  } = useNotifications()

  const mascot = useRouteMascot()

  const closeAllDropdowns = useCallback(() => {
    setIsNotificationMenuOpen(false)
    setIsAccountMenuOpen(false)
  }, [])

  const toggleNotificationMenu = useCallback(() => {
    setIsNotificationMenuOpen((current) => !current)
    setIsAccountMenuOpen(false)
  }, [])

  const toggleAccountMenu = useCallback(() => {
    setIsAccountMenuOpen((current) => !current)
    setIsNotificationMenuOpen(false)
  }, [])

  const handleLogout = useCallback(async () => {
    closeAllDropdowns()
    await logout()
    navigate('/')
  }, [closeAllDropdowns, logout, navigate])

  const moveToNotificationTarget = useCallback(async (notification) => {
    closeAllDropdowns()
    await markNotificationAsRead(notification)
    const currentNotification = findNotificationById(notification?.id) || notification

    if (shouldOpenNotificationDetail(currentNotification)) {
      setSelectedNotification(currentNotification)
      return
    }

    if (currentNotification.notification_type === 'inquiry_answered') {
      navigate('/inquiries/my')
      return
    }

    navigate(currentNotification.target_route || '/')
  }, [closeAllDropdowns, findNotificationById, markNotificationAsRead, navigate, setSelectedNotification])

  const moveToSelectedNotificationTarget = useCallback(async () => {
    const notification = selectedNotification
    const targetRoute = notification?.target_route

    await markNotificationAsRead(notification)
    setSelectedNotification(null)

    if (targetRoute) {
      navigate(targetRoute)
    }
  }, [markNotificationAsRead, navigate, selectedNotification, setSelectedNotification])

  // 헤더 드롭다운 바깥을 누르면 닫습니다.
  useEffect(() => {
    const handleDocumentClick = (event) => {
      const target = event.target

      if (
        notificationMenuRef.current?.contains(target)
        || accountMenuRef.current?.contains(target)
        || sidebarProfileRef.current?.contains(target)
      ) {
        return
      }

      closeAllDropdowns()
    }

    document.addEventListener('click', handleDocumentClick)

    return () => {
      document.removeEventListener('click', handleDocumentClick)
    }
  }, [closeAllDropdowns])

  // 새로고침으로 들어와도 저장된 토큰으로 사용자 정보를 복구합니다.
  useEffect(() => {
    fetchMe().catch(() => {
      clearAuthState()
    })
  }, [fetchMe, clearAuthState])

  // 화면을 옮길 때마다 알림을 다시 확인합니다.
  useEffect(() => {
    fetchNotifications()
  }, [location.pathname, location.search, fetchNotifications])

  return (
    <div className={`app-shell${compactMode ? ' is-compact-mode' : ''}`}>
      <AppHeader
        user={user}
        isLoggedIn={isLoggedIn}
        isMypageActive={location.pathname.startsWith('/mypage')}
        isCustomerCenterActive={location.pathname.startsWith('/inquiries')}
        isNotificationMenuOpen={isNotificationMenuOpen}
        isAccountMenuOpen={isAccountMenuOpen}
        unreadNotificationCount={unreadNotificationCount}
        recentNotifications={recentNotifications}
        notificationMenuRef={notificationMenuRef}
        accountMenuRef={accountMenuRef}
        onToggleNotificationMenu={toggleNotificationMenu}
        onToggleAccountMenu={toggleAccountMenu}
        onCloseAccountMenu={() => setIsAccountMenuOpen(false)}
        onMarkAllNotificationsRead={markAllVisibleNotificationsAsRead}
        onSelectNotification={moveToNotificationTarget}
        onLogout={handleLogout}
      />

      <NotificationDetailModal
        notification={selectedNotification}
        onClose={() => setSelectedNotification(null)}
        onMoveToTarget={moveToSelectedNotificationTarget}
      />

      <div className="app-main">
        <RouteMascot
          activeMascotState={mascot.activeMascotState}
          mascotImageStyle={mascot.mascotImageStyle}
          runPosition={mascot.runPosition}
          fetchPhase={mascot.fetchPhase}
          fetchedMarkerLabel={mascot.fetchedMarkerLabel}
          isMarkerChoiceMenuOpen={mascot.isMarkerChoiceMenuOpen}
          isSearchLoading={mascot.isSearchLoading}
          isLoggedIn={isLoggedIn}
          onMascotClick={mascot.handleMascotClick}
        />

        <Outlet />
      </div>
    </div>
  )
}

export default App
