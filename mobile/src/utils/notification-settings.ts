import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "lifeInfraSettings";
export const DEFAULT_NOTIFICATION_SETTINGS = {
  commentNotifications: true,
  inquiryNotifications: true,
};

export type NotificationSettings = typeof DEFAULT_NOTIFICATION_SETTINGS;

export const readNotificationSettings = async (): Promise<NotificationSettings> => {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) return DEFAULT_NOTIFICATION_SETTINGS;
  try {
    const stored = JSON.parse(raw) as Partial<NotificationSettings>;
    return {
      commentNotifications: stored.commentNotifications !== false,
      inquiryNotifications: stored.inquiryNotifications !== false,
    };
  } catch {
    return DEFAULT_NOTIFICATION_SETTINGS;
  }
};

export const writeNotificationSettings = (settings: NotificationSettings) =>
  AsyncStorage.setItem(KEY, JSON.stringify(settings));
