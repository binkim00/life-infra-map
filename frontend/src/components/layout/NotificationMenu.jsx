import { formatNotificationTime } from '@/utils/notificationFormat'

import NotificationIcon, { getNotificationIconType } from './NotificationIcon'

const NotificationMenu = ({
  isOpen,
  unreadCount,
  recentNotifications,
  onToggle,
  onMarkAllRead,
  onSelectNotification,
}) => {
  return (
    <>
      <button
        type="button"
        className="global-notification-button"
        aria-expanded={isOpen}
        aria-label="알림"
        onClick={onToggle}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
          <path d="M10 21h4" />
        </svg>
        {unreadCount ? (
          <span className="notification-badge global-notification-badge">
            {unreadCount}
          </span>
        ) : null}
      </button>

      {isOpen ? (
        <div className="notification-dropdown">
          <header className="notification-dropdown-header">
            <strong>알림</strong>
            {unreadCount ? (
              <button
                type="button"
                className="notification-read-all-button"
                onClick={(event) => {
                  event.stopPropagation()
                  onMarkAllRead()
                }}
              >
                전체 읽음
              </button>
            ) : null}
          </header>

          {recentNotifications.length ? (
            <div className="notification-dropdown-list">
              {recentNotifications.map((notification) => {
                const iconType = getNotificationIconType(notification)

                return (
                  <article
                    key={notification.id}
                    className={`notification-dropdown-item${notification.is_read ? '' : ' unread'}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => onSelectNotification(notification)}
                    onKeyUp={(event) => {
                      if (event.key === 'Enter') {
                        onSelectNotification(notification)
                      }
                    }}
                  >
                    <span className={`notification-icon-wrap ${iconType}`} aria-hidden="true">
                      <NotificationIcon iconType={iconType} />
                      {!notification.is_read ? <span className="notification-dot" /> : null}
                    </span>
                    <div className="notification-copy">
                      <strong>{notification.title}</strong>
                      <p>{notification.message}</p>
                      <small>{formatNotificationTime(notification.created_at)}</small>
                    </div>
                  </article>
                )
              })}
            </div>
          ) : (
            <p className="notification-empty">알림이 없습니다.</p>
          )}
        </div>
      ) : null}
    </>
  )
}

export default NotificationMenu
