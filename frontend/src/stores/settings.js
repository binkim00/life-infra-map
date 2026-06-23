import { ref, watch } from 'vue'
import { defineStore } from 'pinia'

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

export const useSettingsStore = defineStore('settings', () => {
  const savedSettings = loadSettings()

  const commentNotifications = ref(savedSettings.commentNotifications)
  const inquiryNotifications = ref(savedSettings.inquiryNotifications)
  const compactMode = ref(savedSettings.compactMode)

  const isNotificationVisible = (notification) => {
    if (notification.notification_type === 'post_commented') {
      return commentNotifications.value
    }

    if (notification.notification_type === 'inquiry_answered') {
      return inquiryNotifications.value
    }

    return true
  }

  watch(
    [commentNotifications, inquiryNotifications, compactMode],
    () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        commentNotifications: commentNotifications.value,
        inquiryNotifications: inquiryNotifications.value,
        compactMode: compactMode.value,
      }))
    },
    { deep: true },
  )

  return {
    commentNotifications,
    inquiryNotifications,
    compactMode,
    isNotificationVisible,
  }
})
