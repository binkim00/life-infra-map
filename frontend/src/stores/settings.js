import { create } from 'zustand'

const STORAGE_KEY = 'lifeInfraSettings'

const defaultSettings = {
  commentNotifications: true,
  inquiryNotifications: true,
  compactMode: false,
}

const loadSettings = () => {
  try {
    return {
      ...defaultSettings,
      ...JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'),
    }
  } catch {
    return defaultSettings
  }
}

const persistSettings = (settings) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      commentNotifications: settings.commentNotifications,
      inquiryNotifications: settings.inquiryNotifications,
      compactMode: settings.compactMode,
    }))
  } catch (error) {
    // localStorage can be unavailable in restricted browser contexts.
  }
}

export const useSettingsStore = create((set, get) => ({
  ...loadSettings(),

  setSetting: (key, value) => {
    set({ [key]: value })
    persistSettings(get())
  },

  toggleSetting: (key) => {
    set({ [key]: !get()[key] })
    persistSettings(get())
  },
}))

/**
 * 알림 종류별 노출 여부입니다. 렌더링 중에도 부르므로 구독 없이 현재 값을 읽습니다.
 */
export const isNotificationVisible = (notification) => {
  const { commentNotifications, inquiryNotifications } = useSettingsStore.getState()

  if (notification?.notification_type === 'post_commented') {
    return commentNotifications
  }

  if (notification?.notification_type === 'inquiry_answered') {
    return inquiryNotifications
  }

  return true
}
