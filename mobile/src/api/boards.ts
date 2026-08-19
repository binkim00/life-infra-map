import { apiRequest } from "./client";

export const boardsApi = {
  posts: (boardType = "free") =>
    apiRequest<unknown[]>("/boards/posts/", {
      params: { board_type: boardType },
    }),
  post: (id: string | number) =>
    apiRequest<Record<string, unknown>>(`/boards/posts/${id}/`),
  createPost: (body: unknown) =>
    apiRequest<Record<string, unknown>>("/boards/posts/", {
      method: "POST",
      body,
    }),
  updatePost: (id: string | number, body: unknown) =>
    apiRequest(`/boards/posts/${id}/`, { method: "PATCH", body }),
  deletePost: (id: string | number) =>
    apiRequest(`/boards/posts/${id}/`, { method: "DELETE" }),
  createComment: (postId: string | number, body: unknown) =>
    apiRequest(`/boards/posts/${postId}/comments/`, { method: "POST", body }),
  updateComment: (id: string | number, body: unknown) =>
    apiRequest(`/boards/comments/${id}/`, { method: "PATCH", body }),
  deleteComment: (id: string | number) =>
    apiRequest(`/boards/comments/${id}/`, { method: "DELETE" }),
  likePost: (id: string | number) =>
    apiRequest(`/boards/posts/${id}/like/`, { method: "POST" }),
  likeComment: (id: string | number) =>
    apiRequest(`/boards/comments/${id}/like/`, { method: "POST" }),
  dislikeComment: (id: string | number) =>
    apiRequest(`/boards/comments/${id}/dislike/`, { method: "POST" }),
  reportPost: (id: string | number, body: unknown) =>
    apiRequest(`/boards/posts/${id}/report/`, { method: "POST", body }),
  reportComment: (id: string | number, body: unknown) =>
    apiRequest(`/boards/comments/${id}/report/`, { method: "POST", body }),
  reports: (params: Record<string, string | number> = {}) =>
    apiRequest<unknown[]>("/boards/reports/", { params }),
  processReport: (id: string | number, body: unknown) =>
    apiRequest(`/boards/reports/${id}/process/`, { method: "POST", body }),
  mypage: () => apiRequest<Record<string, unknown>>("/accounts/mypage/"),
  updateNickname: (nickname: string) =>
    apiRequest("/accounts/me/nickname/", {
      method: "PATCH",
      body: { nickname },
    }),
  updateProfileImage: (body: FormData) =>
    apiRequest("/accounts/me/profile-image/", { method: "PATCH", body }),
  notifications: () => apiRequest<unknown[]>("/notifications/"),
  readNotification: (id: string | number) =>
    apiRequest(`/notifications/${id}/read/`, { method: "PATCH" }),
  readAllNotifications: () =>
    apiRequest("/notifications/read-all/", { method: "PATCH" }),
  createInquiry: (body: unknown) =>
    apiRequest("/inquiries/", { method: "POST", body }),
  myInquiries: () => apiRequest<unknown[]>("/inquiries/my/"),
  inquiry: (id: string | number) =>
    apiRequest<Record<string, unknown>>(`/inquiries/${id}/`),
  adminInquiries: () => apiRequest<unknown[]>("/admin/inquiries/"),
  updateAdminInquiry: (id: string | number, body: unknown) =>
    apiRequest(`/admin/inquiries/${id}/`, { method: "PATCH", body }),
  adminUsers: () => apiRequest<unknown[]>("/admin/users/"),
  adminUser: (id: string | number) =>
    apiRequest<Record<string, unknown>>(`/admin/users/${id}/`),
  createPenalty: (id: string | number, body: unknown) =>
    apiRequest(`/admin/users/${id}/penalties/`, { method: "POST", body }),
  notifyUser: (id: string | number, body: unknown) =>
    apiRequest(`/admin/users/${id}/notifications/`, { method: "POST", body }),
};
