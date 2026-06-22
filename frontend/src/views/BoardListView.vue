<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getPosts } from '@/api/boards'
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
          <RouterLink to="/" class="sub-button">
            홈
          </RouterLink>

          <RouterLink to="/boards/free" class="sub-button">
            자유게시판
          </RouterLink>

          <RouterLink to="/boards/notice" class="sub-button">
            공지사항
          </RouterLink>

          <RouterLink
            v-if="authStore.isLoggedIn"
            :to="`/boards/${boardType}/write`"
            class="write-button"
          >
            글쓰기
          </RouterLink>

          <RouterLink
            v-else
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

      <section v-else class="post-list">
        <article
          v-for="post in posts"
          :key="post.id"
          class="post-card"
        >
          <RouterLink
            :to="`/boards/${post.board_type}/${post.id}`"
            class="post-link"
          >
            <div class="post-top">
              <span class="board-badge">
                {{ post.board_type === 'notice' ? '공지' : '자유' }}
              </span>

              <span v-if="post.is_pinned" class="pin-badge">
                고정
              </span>
            </div>

            <h2>{{ post.title }}</h2>

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
              <span>댓글 {{ post.comments_count }}</span>
              <span>좋아요 {{ post.likes_count }}</span>
              <span>조회 {{ post.view_count }}</span>
            </div>
          </RouterLink>
        </article>

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
  max-width: 960px;
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

.sub-button,
.write-button {
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 800;
  text-decoration: none;
}

.sub-button {
  border: 1px solid #d0d5dd;
  background: #ffffff;
  color: #344054;
}

.write-button {
  border: 1px solid #2563eb;
  background: #2563eb;
  color: #ffffff;
}

.post-list {
  display: grid;
  gap: 12px;
}

.post-card {
  overflow: hidden;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.post-link {
  display: block;
  padding: 20px;
  color: inherit;
  text-decoration: none;
}

.post-top {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.board-badge,
.pin-badge {
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 900;
}

.board-badge {
  background: #eff6ff;
  color: #2563eb;
}

.pin-badge {
  background: #fff7ed;
  color: #f97316;
}

.post-card h2 {
  margin: 0 0 12px;
  color: #111827;
  font-size: 20px;
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
}
</style>
