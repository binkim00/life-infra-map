const NOTIFICATION_TYPE_LABELS = {
  admin_warning: '관리자 메시지',
  penalty_notice: '제재 안내',
  report_received: '신고 접수',
  report_passed: '신고 검토 결과',
  report_penalty: '신고 처리 결과',
  inquiry_answered: '문의 답변',
  post_commented: '댓글 알림',
  post_liked: '좋아요 알림',
  comment_liked: '댓글 좋아요',
  system: '시스템 알림',
}

// 상세 모달로 열어야 하는 알림 종류입니다. 나머지는 대상 화면으로 바로 이동합니다.
const NOTIFICATION_DETAIL_TYPES = new Set([
  'admin_warning',
  'penalty_notice',
  'report_received',
  'report_passed',
  'report_penalty',
])

export const formatNotificationTime = (value) => {
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

export const getNotificationTypeLabel = (notification) => {
  return NOTIFICATION_TYPE_LABELS[notification?.notification_type] || '알림'
}

export const shouldOpenNotificationDetail = (notification) => {
  return NOTIFICATION_DETAIL_TYPES.has(notification?.notification_type)
}
