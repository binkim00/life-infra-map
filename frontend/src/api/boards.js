import api from '@/api/axios'

export const getPosts = (boardType = 'free') => {
  return api.get('/boards/posts/', {
    params: {
      board_type: boardType,
    },
  })
}

export const getPost = (postId) => {
  return api.get(`/boards/posts/${postId}/`)
}

export const createPost = (payload) => {
  const config = payload instanceof FormData ? {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  } : undefined

  return api.post('/boards/posts/', payload, config)
}

export const updatePost = (postId, payload) => {
  const config = payload instanceof FormData ? {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  } : undefined

  return api.patch(`/boards/posts/${postId}/`, payload, config)
}

export const deletePost = (postId) => {
  return api.delete(`/boards/posts/${postId}/`)
}

export const createComment = (postId, payload) => {
  return api.post(`/boards/posts/${postId}/comments/`, payload)
}

export const updateComment = (commentId, payload) => {
  return api.patch(`/boards/comments/${commentId}/`, payload)
}

export const deleteComment = (commentId) => {
  return api.delete(`/boards/comments/${commentId}/`)
}

export const togglePostLike = (postId) => {
  return api.post(`/boards/posts/${postId}/like/`)
}

export const toggleCommentLike = (commentId) => {
  return api.post(`/boards/comments/${commentId}/like/`)
}

export const toggleCommentDislike = (commentId) => {
  return api.post(`/boards/comments/${commentId}/dislike/`)
}

export const reportPost = (postId, payload) => {
  return api.post(`/boards/posts/${postId}/report/`, payload)
}

export const reportComment = (commentId, payload) => {
  return api.post(`/boards/comments/${commentId}/report/`, payload)
}

export const getReports = (params = {}) => {
  return api.get('/boards/reports/', { params })
}

export const processReport = (reportId, payload) => {
  return api.patch(`/boards/reports/${reportId}/process/`, payload)
}

export const getMypage = () => {
  return api.get('/accounts/mypage/')
}

export const updateNickname = (payload) => {
  return api.patch('/accounts/me/nickname/', payload)
}

export const updateProfileImage = (payload) => {
  return api.patch('/accounts/me/profile-image/', payload, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}

export const getNotifications = () => {
  return api.get('/notifications/')
}

export const markNotificationRead = (notificationId) => {
  return api.patch(`/notifications/${notificationId}/read/`)
}

export const markAllNotificationsRead = () => {
  return api.patch('/notifications/read-all/')
}

export const createInquiry = (payload) => {
  return api.post('/inquiries/', payload)
}

export const getMyInquiries = () => {
  return api.get('/inquiries/my/')
}

export const getInquiry = (inquiryId) => {
  return api.get(`/inquiries/${inquiryId}/`)
}

export const getAdminInquiries = () => {
  return api.get('/admin/inquiries/')
}

export const updateAdminInquiry = (inquiryId, payload) => {
  return api.patch(`/admin/inquiries/${inquiryId}/`, payload)
}

export const getAdminUsers = () => {
  return api.get('/admin/users/')
}

export const getAdminUser = (userId) => {
  return api.get(`/admin/users/${userId}/`)
}

export const createUserPenalty = (userId, payload) => {
  return api.post(`/admin/users/${userId}/penalties/`, payload)
}

export const createUserNotification = (userId, payload) => {
  return api.post(`/admin/users/${userId}/notifications/`, payload)
}
