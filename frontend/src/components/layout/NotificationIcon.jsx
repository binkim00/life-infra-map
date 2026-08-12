const TIER_UP_NOTIFICATION_TITLE = '등급 승급 안내'

export const getNotificationIconType = (notification) => {
  const type = notification?.notification_type

  if (type === 'post_commented') {
    return 'comment'
  }

  if (type === 'post_liked' || type === 'comment_liked') {
    return 'like'
  }

  if (type === 'report_received' || type === 'report_passed' || type === 'report_penalty') {
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

const NotificationIcon = ({ iconType }) => {
  if (iconType === 'comment') {
    return (
      <svg className="notification-comment-icon" viewBox="0 0 24 24">
        <path
          className="notification-comment-bubble"
          d="M4.7 16.1A8.5 8.5 0 0 1 3 11.1C3 6.4 7.1 2.8 12.2 2.8s9.2 3.6 9.2 8.3-4.1 8.3-9.2 8.3a10.4 10.4 0 0 1-3.7-.7 6.7 6.7 0 0 1-4.5 2l-.8-.1.5-.7a6.7 6.7 0 0 0 1-3.8Z"
        />
        <path className="notification-comment-dot" d="M8.2 11.2h.1M12.2 11.2h.1M16.2 11.2h.1" />
      </svg>
    )
  }

  if (iconType === 'like') {
    return <span className="notification-like-icon">♥</span>
  }

  if (iconType === 'report') {
    return (
      <svg viewBox="0 0 24 24">
        <path d="M6 11a6 6 0 0 1 12 0v4l2 3H4l2-3v-4Z" />
        <path d="M10 21h4" />
        <path d="M4 6 2.5 4.5" />
        <path d="M20 6 21.5 4.5" />
        <path d="M9 3.5 8.2 1.8" />
        <path d="M15 3.5l.8-1.7" />
      </svg>
    )
  }

  if (iconType === 'tier-up') {
    return (
      <svg viewBox="0 0 24 24">
        <path d="M7 12.5 4.5 10a1.6 1.6 0 0 0-2.2 2.3l4.1 4.1" />
        <path d="M10.5 8.5 8 6a1.6 1.6 0 0 0-2.2 2.3l4.2 4.2" />
        <path d="M14 7.5 11.5 5a1.6 1.6 0 0 0-2.2 2.3l4.2 4.2" />
        <path d="M17.2 9.3 15.5 7.6a1.6 1.6 0 0 0-2.2 2.3l2.8 2.8" />
        <path d="M7.5 16.5c2.8 3 6.5 3.9 9.2 1.2 1.8-1.8 2-4.4.8-6.7" />
        <path d="M19.5 5.5 21 4" />
        <path d="M20.8 9h2" />
        <path d="M16.8 3.2l.5-2" />
      </svg>
    )
  }

  if (iconType === 'penalty') {
    return (
      <svg viewBox="0 0 24 24">
        <path d="M12 3 20 7v5c0 5-3.4 8-8 9-4.6-1-8-4-8-9V7l8-4Z" />
        <path d="M9 9l6 6" />
        <path d="M15 9l-6 6" />
      </svg>
    )
  }

  if (iconType === 'admin') {
    return (
      <svg viewBox="0 0 24 24">
        <path d="M12 3 20 7v5c0 5-3.4 8-8 9-4.6-1-8-4-8-9V7l8-4Z" />
        <path d="M9 12h6" />
        <path d="M12 9v6" />
      </svg>
    )
  }

  if (iconType === 'message') {
    return (
      <svg viewBox="0 0 24 24">
        <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z" />
        <path d="M8 9h8" />
        <path d="M8 13h5" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24">
      <path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z" />
      <path d="M12 8v5" />
      <path d="M12 16h.01" />
    </svg>
  )
}

export default NotificationIcon
