type NotificationSettings = {
  commentNotifications: boolean;
  inquiryNotifications: boolean;
};

export const isNotificationVisible = (
  type: string | undefined,
  settings: NotificationSettings,
) => type === "post_commented" ? settings.commentNotifications
  : type === "inquiry_answered" ? settings.inquiryNotifications : true;
