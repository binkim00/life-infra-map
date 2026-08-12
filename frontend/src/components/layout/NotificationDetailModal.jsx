import { formatNotificationTime, getNotificationTypeLabel } from '@/utils/notificationFormat'

const NotificationDetailModal = ({ notification, onClose, onMoveToTarget }) => {
  if (!notification) return null

  return (
    <div
      className="notification-detail-backdrop"
      role="presentation"
      onClick={(event) => {
        // 배경을 눌렀을 때만 닫습니다.
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <section
        className="notification-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="notification-detail-title"
      >
        <header className="notification-detail-header">
          <div>
            <span>{getNotificationTypeLabel(notification)}</span>
            <h2 id="notification-detail-title">{notification.title}</h2>
          </div>
          <button
            type="button"
            className="notification-detail-close"
            aria-label="알림 상세 닫기"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <p className="notification-detail-message">{notification.message}</p>

        <footer className="notification-detail-footer">
          <time>{formatNotificationTime(notification.created_at)}</time>
          <div className="notification-detail-actions">
            <button
              type="button"
              className="notification-detail-button secondary"
              onClick={onClose}
            >
              닫기
            </button>
            {notification.target_route ? (
              <button
                type="button"
                className="notification-detail-button primary"
                onClick={onMoveToTarget}
              >
                관련 글 보기
              </button>
            ) : null}
          </div>
        </footer>
      </section>
    </div>
  )
}

export default NotificationDetailModal
