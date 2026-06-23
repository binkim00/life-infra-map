<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getPosts } from '@/api/boards'
import { getTierIcon } from '@/utils/tierIcons'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()

const posts = ref([])
const isLoading = ref(false)
const errorMessage = ref('')

const boardType = computed(() => route.params.boardType || 'free')

const boardTitle = computed(() => {
  if (boardType.value === 'notice') return '공지사항'
  return '자유게시판'
})

const canWritePost = computed(() => {
  if (!authStore.isLoggedIn) {
    return false
  }

  return boardType.value !== 'notice' || authStore.user?.is_staff
})

const formatBoardDate = (value) => {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()

  if (isToday) {
    return date.toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }

  return date.toLocaleDateString('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  }).replace(/\. /g, '.').replace(/\.$/, '')
}

const fetchPosts = async () => {
  try {
    isLoading.value = true
    errorMessage.value = ''

    const response = await getPosts(boardType.value)
    posts.value = response.data
  } catch (error) {
    console.error(error)
    errorMessage.value = '게시글 목록을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

watch(boardType, fetchPosts)

onMounted(() => {
  fetchPosts()
})
</script>

<template>
  <main class="board-page">
    <section class="board-container">
      <header class="board-header">
        <div>
          <p class="eyebrow">COMMUNITY</p>
          <h1>{{ boardTitle }}</h1>
        </div>

        <div class="board-actions">
          <RouterLink
            v-if="canWritePost"
            :to="`/boards/${boardType}/write`"
            class="write-button"
          >
            글쓰기
          </RouterLink>

          <RouterLink
            v-else-if="boardType !== 'notice'"
            to="/login"
            class="write-button"
          >
            로그인
          </RouterLink>
        </div>
      </header>

      <p v-if="isLoading" class="status-text">
        게시글을 불러오는 중입니다.
      </p>

      <p v-else-if="errorMessage" class="error-text">
        {{ errorMessage }}
      </p>

      <section v-else class="board-table-wrap">
        <table class="board-table">
          <colgroup>
            <col class="col-number" />
            <col class="col-category" />
            <col class="col-title" />
            <col class="col-author" />
            <col class="col-date" />
            <col class="col-count" />
            <col class="col-count" />
          </colgroup>

          <thead>
            <tr>
              <th>번호</th>
              <th>말머리</th>
              <th>제목</th>
              <th>글쓴이</th>
              <th>작성일</th>
              <th>조회</th>
              <th>추천</th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="post in posts"
              :key="post.id"
              :class="{ pinned: post.is_pinned }"
            >
              <td class="number-cell">{{ post.is_pinned ? '-' : post.id }}</td>
              <td>
                <span class="category-label" :class="post.board_type">
                  <span v-if="post.is_pinned" class="pin-dot">!</span>
                  {{ post.board_type === 'notice' ? '공지' : '일반' }}
                </span>
              </td>
              <td class="title-cell">
                <RouterLink :to="`/boards/${post.board_type}/${post.id}`" class="title-link">
                  <span class="title-text">{{ post.title }}</span>
                  <span v-if="post.comments_count" class="comment-count">[{{ post.comments_count }}]</span>
                  <span v-if="post.is_edited" class="edited-mark">수정됨</span>
                </RouterLink>
              </td>
              <td class="author-cell">
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
                  <img
                    v-if="post.author_tier"
                    :src="getTierIcon(post.author_tier)"
                    :alt="post.author_tier_label || post.author_tier"
                    class="tier-icon"
                  />
                </span>
              </td>
              <td>{{ formatBoardDate(post.created_at) }}</td>
              <td>{{ post.view_count }}</td>
              <td>{{ post.likes_count }}</td>
            </tr>
          </tbody>
        </table>

        <p v-if="posts.length === 0" class="empty-text">
          아직 등록된 글이 없습니다.
        </p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.board-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.board-container {
  max-width: 1120px;
  margin: 0 auto;
}

.board-header {
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

.board-header h1 {
  margin: 0;
  color: #111827;
  font-size: 32px;
}

.board-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.write-button {
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 800;
  text-decoration: none;
}

.write-button {
  border: 1px solid #2563eb;
  background: #2563eb;
  color: #ffffff;
}

.board-table-wrap {
  overflow: hidden;
  border: 1px solid #d7dce5;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.06);
}

.board-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  color: #111827;
  font-size: 13px;
}

.board-table th,
.board-table td {
  height: 30px;
  padding: 0 8px;
  border-bottom: 1px solid #edf0f4;
  vertical-align: middle;
}

.board-table th {
  border-bottom-color: #cfd6e2;
  background: #fbfcfe;
  color: #111827;
  font-size: 12px;
  font-weight: 900;
  text-align: center;
}

.board-table tbody tr:hover {
  background: #f4f7fb;
}

.board-table tbody tr.pinned {
  background: #f8fafc;
}

.board-table tbody tr:last-child td {
  border-bottom: 0;
}

.col-number { width: 64px; }
.col-category { width: 86px; }
.col-author { width: 150px; }
.col-date { width: 90px; }
.col-count { width: 60px; }

.board-table td:not(.title-cell) {
  text-align: center;
  white-space: nowrap;
}

.number-cell {
  color: #667085;
}

.title-cell {
  min-width: 0;
  text-align: left;
}

.title-link {
  min-width: 0;
  display: inline-flex;
  max-width: 100%;
  gap: 4px;
  align-items: center;
  color: #111827;
  font-weight: 800;
  text-decoration: none;
}

.title-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-link:hover {
  color: #dc2626;
  text-decoration: underline;
}

.title-link::first-letter {
  text-transform: none;
}

.comment-count {
  flex: 0 0 auto;
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
}

.edited-mark {
  flex: 0 0 auto;
  color: #94a3b8;
  font-size: 11px;
}

.category-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #344054;
  font-weight: 800;
}

.category-label.notice {
  color: #dc2626;
}

.category-label.free {
  color: #344054;
}

.pin-dot {
  width: 16px;
  height: 16px;
  display: inline-grid;
  place-items: center;
  border-radius: 50%;
  background: #f97316;
  color: #ffffff;
  font-size: 11px;
  font-weight: 900;
}

.author-cell {
  color: #344054;
}

.author-chip {
  min-width: 0;
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 5px;
  font-weight: 800;
}

.author-avatar {
  position: relative;
  display: inline-flex;
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: 50%;
  background: #8fb8cc;
}

.author-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tier-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  object-fit: contain;
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

@media (max-width: 720px) {
  .board-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .board-actions {
    justify-content: flex-start;
  }

  .board-table-wrap {
    overflow-x: auto;
  }

  .board-table {
    min-width: 760px;
  }
}
</style>
