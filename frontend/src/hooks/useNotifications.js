import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '@/api/boards'
import { useAuthStore } from '@/stores/auth'
import { isNotificationVisible, useSettingsStore } from '@/stores/settings'

const TIER_UP_NOTIFICATION_TITLE = '등급 승급 안내'
const POLL_INTERVAL_MS = 10000

const getNotificationKey = (notification) => (
  notification.id ?? `${notification.created_at}-${notification.message}`
)

export const useNotifications = () => {
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn)
  const fetchMe = useAuthStore((state) => state.fetchMe)
  // 알림 필터는 설정값에 따라 달라지므로 설정이 바뀌면 다시 계산되게 구독합니다.
  const commentNotifications = useSettingsStore((state) => state.commentNotifications)
  const inquiryNotifications = useSettingsStore((state) => state.inquiryNotifications)

  const [notifications, setNotifications] = useState([])
  const [selectedNotification, setSelectedNotification] = useState(null)
  const handledTierUpIdsRef = useRef(new Set())
  const isLoggedInRef = useRef(isLoggedIn)
  isLoggedInRef.current = isLoggedIn

  const fetchNotifications = useCallback(async () => {
    if (!isLoggedInRef.current) {
      setNotifications([])
      return
    }

    try {
      const response = await getNotifications()
      const fetchedNotifications = response.data
      setNotifications(fetchedNotifications)

      const newTierUpNotifications = fetchedNotifications.filter((notification) => (
        !notification.is_read
        && notification.title === TIER_UP_NOTIFICATION_TITLE
        && !handledTierUpIdsRef.current.has(getNotificationKey(notification))
      ))

      if (newTierUpNotifications.length > 0) {
        newTierUpNotifications.forEach((notification) => {
          handledTierUpIdsRef.current.add(getNotificationKey(notification))
        })
        // 승급 알림이 오면 사용자 등급 표시를 갱신합니다.
        await fetchMe()
      }
    } catch (error) {
      console.error(error)
    }
  }, [fetchMe])

  const visibleNotifications = useMemo(() => (
    notifications.filter(isNotificationVisible)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ), [notifications, commentNotifications, inquiryNotifications])

  const unreadNotificationCount = useMemo(() => (
    visibleNotifications.filter((notification) => !notification.is_read).length
  ), [visibleNotifications])

  const recentNotifications = useMemo(() => (
    visibleNotifications.slice(0, 6)
  ), [visibleNotifications])

  const markNotificationReadLocally = useCallback((notificationId) => {
    setNotifications((current) => current.map((notification) => (
      String(notification.id) === String(notificationId)
        ? { ...notification, is_read: true }
        : notification
    )))

    setSelectedNotification((current) => (
      current && String(current.id) === String(notificationId)
        ? { ...current, is_read: true }
        : current
    ))
  }, [])

  const markNotificationAsRead = useCallback(async (notification) => {
    const notificationId = notification?.id
    if (!notificationId || notification.is_read) return

    markNotificationReadLocally(notificationId)

    try {
      await markNotificationRead(notificationId)
    } catch (error) {
      console.error(error)
      fetchNotifications()
    }
  }, [fetchNotifications, markNotificationReadLocally])

  const markAllVisibleNotificationsAsRead = useCallback(async () => {
    if (unreadNotificationCount === 0) return

    setNotifications((current) => current.map((notification) => ({
      ...notification,
      is_read: true,
    })))

    try {
      await markAllNotificationsRead()
    } catch (error) {
      console.error(error)
      fetchNotifications()
    }
  }, [fetchNotifications, unreadNotificationCount])

  const findNotificationById = useCallback((notificationId) => (
    notifications.find((notification) => (
      String(notification.id) === String(notificationId)
    )) || null
  ), [notifications])

  // 로그인 상태가 바뀔 때마다 알림을 다시 받고 폴링을 다시 겁니다.
  useEffect(() => {
    if (!isLoggedIn) {
      setNotifications([])
      return undefined
    }

    fetchNotifications()
    const timerId = window.setInterval(fetchNotifications, POLL_INTERVAL_MS)

    return () => {
      window.clearInterval(timerId)
    }
  }, [isLoggedIn, fetchNotifications])

  return {
    notifications,
    visibleNotifications,
    recentNotifications,
    unreadNotificationCount,
    selectedNotification,
    setSelectedNotification,
    fetchNotifications,
    markNotificationAsRead,
    markAllVisibleNotificationsAsRead,
    findNotificationById,
  }
}
