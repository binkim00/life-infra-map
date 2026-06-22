<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  createComment,
  deleteComment,
  deletePost,
  getPost,
  reportComment,
  reportPost,
  toggleCommentLike,
  togglePostLike,
  updateComment,
} from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const post = ref(null)
const commentContent = ref('')
const isLoading = ref(false)
const errorMessage = ref('')
const reportTarget = ref(null)
const reportReason = ref('')
const reportMessage = ref('')
const isSubmittingReport = ref(false)
const editingCommentId = ref(null)
const editingCommentContent = ref('')

const boardType = computed(() => route.params.boardType || 'free')
const postId = computed(() => route.params.postId)

const boardTitle = computed(() => {
  if (boardType.value === 'notice') return '공지사항'
  return '자유게시판'
})

const formatDateTime = (value) => {
  if (!value) {
    return ''
  }

  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const fetchPost = async () => {
  try {
    isLoading.value = true
    errorMessage.value = ''

    const response = await getPost(postId.value)
    post.value = response.data
  } catch (error) {
    console.error(error)
    errorMessage.value = '게시글을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const handlePostLike = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  const response = await togglePostLike(post.value.id)

  post.value.is_liked = response.data.liked
  post.value.likes_count = response.data.likes_count
}

const handleCreateComment = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  if (!commentContent.value.trim()) {
    return
  }

  const response = await createComment(post.value.id, {
    content: commentContent.value,
  })

  post.value.comments.push(response.data)
  post.value.comments_count += 1
  commentContent.value = ''
}

const handleCommentLike = async (comment) => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  const response = await toggleCommentLike(comment.id)

  comment.is_liked = response.data.liked
  comment.likes_count = response.data.likes_count
}

const handleDeletePost = async () => {
  if (!confirm('게시글을 삭제하시겠습니까?')) {
    return
  }

  await deletePost(post.value.id)
  router.push(`/boards/${boardType.value}`)
}

const handleDeleteComment = async (comment) => {
  if (!confirm('댓글을 삭제하시겠습니까?')) {
    return
  }

  await deleteComment(comment.id)

  post.value.comments = post.value.comments.filter((item) => item.id !== comment.id)
  post.value.comments_count -= 1
}

const startEditComment = (comment) => {
  editingCommentId.value = comment.id
  editingCommentContent.value = comment.content
}

const cancelEditComment = () => {
  editingCommentId.value = null
  editingCommentContent.value = ''
}

const handleUpdateComment = async (comment) => {
  if (!editingCommentContent.value.trim()) {
    return
  }

  const response = await updateComment(comment.id, {
    content: editingCommentContent.value,
  })

  const index = post.value.comments.findIndex((item) => item.id === comment.id)

  if (index !== -1) {
    post.value.comments[index] = response.data
  }

  cancelEditComment()
}

const openReportModal = (type, target) => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  reportTarget.value = {
    type,
    target,
  }
  reportReason.value = ''
  reportMessage.value = ''
}

const closeReportModal = () => {
  reportTarget.value = null
  reportReason.value = ''
  reportMessage.value = ''
  isSubmittingReport.value = false
}

const submitReport = async () => {
  if (!reportTarget.value || isSubmittingReport.value) {
    return
  }

  if (!reportReason.value.trim()) {
    reportMessage.value = '신고 사유를 입력해주세요.'
    return
  }

  try {
    isSubmittingReport.value = true
    reportMessage.value = ''

    const payload = {
      reason: reportReason.value,
    }

    if (reportTarget.value.type === 'post') {
      await reportPost(reportTarget.value.target.id, payload)
    } else {
      await reportComment(reportTarget.value.target.id, payload)
    }

    alert('신고가 접수되었습니다.')
    closeReportModal()
  } catch (error) {
    console.error(error)
    reportMessage.value = error.response?.data?.detail || '신고 접수에 실패했습니다.'
  } finally {
    isSubmittingReport.value = false
  }
}

onMounted(() => {
  fetchPost()
})
</script>

<template>
  <main class="board-page">
    <section class="detail-container">
      <header class="detail-header">
        <div>
          <p class="eyebrow">DETAIL</p>
          <h1>{{ boardTitle }}</h1>
        </div>

        <RouterLink :to="`/boards/${boardType}`" class="back-button">
          목록으로
        </RouterLink>
      </header>

      <p v-if="isLoading" class="status-text">
        게시글을 불러오는 중입니다.
      </p>

      <p v-else-if="errorMessage" class="error-text">
        {{ errorMessage }}
      </p>

      <article v-else-if="post" class="post-detail-card">
        <div class="post-title-row">
          <div>
            <span class="board-badge">
              {{ post.board_type === 'notice' ? '공지' : '자유' }}
            </span>

            <h2>{{ post.title }}</h2>
          </div>

          <div v-if="authStore.user?.id === post.author" class="post-manage-buttons">
            <RouterLink :to="`/boards/${boardType}/${post.id}/edit`" class="edit-button">
              수정
            </RouterLink>

            <button type="button" class="delete-button" @click="handleDeletePost">
              삭제
            </button>
          </div>
        </div>

        <div class="post-meta">
          <span class="author-chip">
            <span class="author-avatar">
              <img
                v-if="post.author_profile_image_url"
                :src="post.author_profile_image_url"
                :alt="post.author_nickname"
              />
              <span v-else class="default-avatar" aria-hidden="true"></span>
            </span>
            {{ post.author_nickname }}
          </span>
          <span>{{ formatDateTime(post.created_at) }} <template v-if="post.is_edited">(수정됨)</template></span>
          <span>조회 {{ post.view_count }}</span>
          <span>댓글 {{ post.comments_count }}</span>
          <span>좋아요 {{ post.likes_count }}</span>
        </div>

        <img
          v-if="post.image_url"
          :src="post.image_url"
          :alt="post.title"
          class="post-image"
        />

        <div class="post-content">
          {{ post.content }}
        </div>

        <div class="reaction-box">
          <div class="reaction-stats">
            <strong class="post-like-count">
              {{ post.likes_count }}
            </strong>

            <span class="comment-count">
              💬 {{ post.comments_count }}
            </span>
          </div>

          <button type="button" class="circle-like-button" :class="{ active: post.is_liked }" @click="handlePostLike">
            <span class="star-icon">
              ★
            </span>

            <span class="circle-like-label">
              {{ post.is_liked ? '취소' : '좋아요' }}
            </span>
          </button>

          <button v-if="post.board_type === 'free'" type="button" class="report-button"
            @click="openReportModal('post', post)">
            신고하기
          </button>
        </div>

        <section class="comment-section">
          <h3>댓글 {{ post.comments_count }}</h3>

          <form class="comment-form" @submit.prevent="handleCreateComment">
            <textarea v-model="commentContent" rows="3" placeholder="댓글을 입력하세요"></textarea>

            <button type="submit">
              댓글 등록
            </button>
          </form>

          <div class="comment-list">
            <article v-for="comment in post.comments" :key="comment.id" class="comment-card">
              <div class="comment-top">
                <div class="comment-author-block">
                  <strong class="author-chip">
                    <span class="author-avatar">
                      <img
                        v-if="comment.author_profile_image_url"
                        :src="comment.author_profile_image_url"
                        :alt="comment.author_nickname"
                      />
                      <span v-else class="default-avatar" aria-hidden="true"></span>
                    </span>
                    {{ comment.author_nickname }}
                  </strong>
                  <span>{{ formatDateTime(comment.created_at) }} <template v-if="comment.is_edited">(수정됨)</template></span>
                </div>
                <span>좋아요 {{ comment.likes_count }}</span>
              </div>

              <form
                v-if="editingCommentId === comment.id"
                class="comment-edit-form"
                @submit.prevent="handleUpdateComment(comment)"
              >
                <textarea v-model="editingCommentContent" rows="3"></textarea>

                <div class="comment-edit-actions">
                  <button type="button" class="comment-cancel-button" @click="cancelEditComment">
                    취소
                  </button>

                  <button type="submit" class="comment-save-button">
                    저장
                  </button>
                </div>
              </form>

              <p v-else>{{ comment.content }}</p>

              <button type="button" class="comment-like-button" :class="{ active: comment.is_liked }"
                @click="handleCommentLike(comment)">
                {{ comment.is_liked ? '댓글 좋아요 취소' : '댓글 좋아요' }}
              </button>

              <button v-if="authStore.user?.id === comment.author" type="button" class="comment-delete-button"
                @click="handleDeleteComment(comment)">
                댓글 삭제
              </button>

              <button v-if="authStore.user?.id === comment.author" type="button" class="comment-edit-button"
                @click="startEditComment(comment)">
                댓글 수정
              </button>

              <button v-if="post.board_type === 'free'" type="button" class="comment-report-button"
                @click="openReportModal('comment', comment)">
                신고하기
              </button>
            </article>

            <p v-if="post.comments.length === 0" class="empty-text">
              아직 댓글이 없습니다.
            </p>
          </div>
        </section>
      </article>
    </section>

    <div v-if="reportTarget" class="report-modal-backdrop" @click.self="closeReportModal">
      <form class="report-modal" @submit.prevent="submitReport">
        <header>
          <div>
            <p class="modal-label">REPORT</p>
            <h2>신고 사유</h2>
          </div>

          <button type="button" class="modal-close-button" @click="closeReportModal">
            ×
          </button>
        </header>

        <p class="report-target-text">
          {{ reportTarget.type === 'post' ? '게시글' : '댓글' }}을 신고합니다.
        </p>

        <textarea v-model="reportReason" rows="5" placeholder="신고 사유를 입력하세요"></textarea>

        <p v-if="reportMessage" class="report-message">
          {{ reportMessage }}
        </p>

        <div class="modal-actions">
          <button type="button" class="modal-cancel-button" @click="closeReportModal">
            취소
          </button>

          <button type="submit" class="modal-submit-button" :disabled="isSubmittingReport">
            {{ isSubmittingReport ? '제출 중' : '제출' }}
          </button>
        </div>
      </form>
    </div>
  </main>
</template>

<style scoped>
.post-manage-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
}

.edit-button {
  display: inline-flex;
  height: 38px;
  align-items: center;
  padding: 0 14px;
  border-radius: 999px;
  background: #eef2ff;
  color: #2563eb;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
}

.comment-delete-button,
.comment-edit-button {
  margin-left: 8px;
  padding: 8px 12px;
  border: 0;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
}

.comment-delete-button {
  background: #fee2e2;
  color: #ef4444;
}

.comment-edit-button {
  background: #eef2ff;
  color: #2563eb;
}

.report-button,
.comment-report-button {
  border: 0;
  border-radius: 999px;
  background: #fff7ed;
  color: #f97316;
  font-weight: 900;
  cursor: pointer;
}

.report-button {
  padding: 10px 14px;
}

.comment-report-button {
  margin-left: 8px;
  padding: 8px 12px;
  font-size: 13px;
}

.board-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.detail-container {
  max-width: 860px;
  margin: 0 auto;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.detail-header h1 {
  margin: 0;
  color: #111827;
  font-size: 32px;
}

.back-button {
  padding: 10px 14px;
  border: 1px solid #d0d5dd;
  border-radius: 999px;
  background: #ffffff;
  color: #344054;
  font-size: 14px;
  font-weight: 800;
  text-decoration: none;
}

.post-detail-card {
  padding: 24px;
  border: 1px solid #e5e8f0;
  border-radius: 22px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.post-title-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.board-badge {
  display: inline-flex;
  margin-bottom: 12px;
  padding: 5px 9px;
  border-radius: 999px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 12px;
  font-weight: 900;
}

.post-detail-card h2 {
  margin: 0 0 12px;
  color: #111827;
  font-size: 28px;
}

.post-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  color: #667085;
  font-size: 14px;
}

.author-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #344054;
  font-weight: 800;
}

.author-avatar {
  position: relative;
  display: inline-flex;
  width: 28px;
  height: 28px;
  overflow: hidden;
  border-radius: 50%;
  background: #8fb8cc;
}

.author-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.default-avatar {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
}

.default-avatar::before,
.default-avatar::after {
  position: absolute;
  left: 50%;
  content: "";
  transform: translateX(-50%);
  background: #c8ddea;
}

.default-avatar::before {
  top: 20%;
  width: 34%;
  height: 34%;
  border-radius: 50%;
}

.default-avatar::after {
  bottom: -10%;
  width: 72%;
  height: 48%;
  border-radius: 50% 50% 0 0;
}

.post-content {
  min-height: 180px;
  margin: 28px 0;
  padding: 20px;
  border-radius: 16px;
  background: #f9fafb;
  color: #111827;
  line-height: 1.7;
  white-space: pre-wrap;
}

.post-image {
  width: 100%;
  max-height: 520px;
  margin-top: 24px;
  border-radius: 16px;
  object-fit: contain;
  background: #f9fafb;
}

.like-button,
.comment-like-button,
.delete-button,
.comment-form button {
  border: 0;
  cursor: pointer;
  font-weight: 900;
}

.reaction-box {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  margin: 26px 0 10px;
}

.reaction-stats {
  display: grid;
  gap: 4px;
  justify-items: center;
  min-width: 40px;
}

.post-like-count {
  color: #e60012;
  font-size: 18px;
  font-weight: 900;
  line-height: 1;
}

.comment-count {
  color: #344054;
  font-size: 13px;
  font-weight: 700;
}

.circle-like-button {
  width: 78px;
  height: 78px;
  border: 0;
  border-radius: 50%;
  background: #3f4fa3;
  color: #ffffff;
  box-shadow: 0 10px 22px rgba(63, 79, 163, 0.28);
  cursor: pointer;

  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 2px;

  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease,
    background 0.15s ease;
}

.circle-like-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 28px rgba(63, 79, 163, 0.34);
}

.circle-like-button.active {
  background: #1d4ed8;
}

.star-icon {
  font-size: 32px;
  line-height: 1;
}

.circle-like-label {
  font-size: 12px;
  font-weight: 900;
  line-height: 1.1;
}

.delete-button {
  height: 38px;
  padding: 0 14px;
  border-radius: 999px;
  background: #fee2e2;
  color: #ef4444;
}

.comment-section {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid #e5e8f0;
}

.comment-section h3 {
  margin: 0 0 14px;
}

.comment-form {
  display: grid;
  gap: 10px;
}

.comment-form textarea {
  padding: 14px;
  border: 1px solid #d0d5dd;
  border-radius: 14px;
  resize: vertical;
  outline: none;
}

.comment-form button {
  justify-self: end;
  padding: 11px 16px;
  border-radius: 12px;
  background: #2563eb;
  color: #ffffff;
}

.comment-list {
  display: grid;
  gap: 10px;
  margin-top: 20px;
}

.comment-card {
  padding: 16px;
  border: 1px solid #e5e8f0;
  border-radius: 16px;
  background: #ffffff;
}

.comment-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #344054;
  font-size: 14px;
}

.comment-author-block {
  display: grid;
  gap: 4px;
}

.comment-author-block span {
  color: #667085;
  font-size: 12px;
}

.comment-edit-form {
  display: grid;
  gap: 8px;
  margin: 10px 0;
}

.comment-edit-form textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  resize: vertical;
  outline: none;
}

.comment-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.comment-cancel-button,
.comment-save-button {
  padding: 8px 12px;
  border: 0;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
}

.comment-cancel-button {
  background: #f2f4f7;
  color: #344054;
}

.comment-save-button {
  background: #2563eb;
  color: #ffffff;
}

.comment-card p {
  margin: 10px 0;
  color: #111827;
  line-height: 1.6;
}

.comment-like-button {
  padding: 8px 12px;
  border-radius: 999px;
  background: #f2f4f7;
  color: #344054;
  font-size: 13px;
}

.comment-like-button.active {
  background: #2563eb;
  color: #ffffff;
}

.status-text,
.empty-text,
.error-text {
  padding: 32px;
  border-radius: 18px;
  background: #ffffff;
  text-align: center;
}

.error-text {
  color: #ef4444;
}

.report-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  padding: 24px;
  display: grid;
  place-items: center;
  background: rgba(17, 24, 39, 0.45);
}

.report-modal {
  width: min(520px, 100%);
  padding: 22px;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.24);
}

.report-modal header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.modal-label {
  margin: 0 0 4px;
  color: #f97316;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.report-modal h2 {
  margin: 0;
  color: #111827;
  font-size: 22px;
}

.modal-close-button {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 999px;
  background: #f2f4f7;
  color: #667085;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.report-target-text {
  margin: 0 0 10px;
  color: #667085;
  font-size: 14px;
}

.report-modal textarea {
  width: 100%;
  padding: 14px;
  border: 1px solid #d0d5dd;
  border-radius: 14px;
  resize: vertical;
  outline: none;
}

.report-message {
  margin: 10px 0 0;
  color: #ef4444;
  font-size: 14px;
  font-weight: 800;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}

.modal-cancel-button,
.modal-submit-button {
  padding: 10px 14px;
  border: 0;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
}

.modal-cancel-button {
  background: #f2f4f7;
  color: #344054;
}

.modal-submit-button {
  background: #f97316;
  color: #ffffff;
}

.modal-submit-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
