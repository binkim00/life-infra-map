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
const searchQuery = ref('')
const sortMode = ref('latest')
const currentPage = ref(1)
const pageSize = 10

const boardType = computed(() => route.params.boardType || 'free')

const boardTitle = computed(() => {
  if (boardType.value === 'notice') return '공지사항'
  return '전체 게시판'
})

const boardCountLabel = computed(() => {
  return `총 ${filteredPosts.value.length.toLocaleString('ko-KR')}개`
})

const filteredPosts = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase()

  if (!keyword) {
    return posts.value
  }

  return posts.value.filter((post) => {
    return [
      post.title,
      post.author_nickname,
      post.author_username,
    ].some((value) => String(value || '').toLowerCase().includes(keyword))
  })
})

const sortedPosts = computed(() => {
  const nextPosts = [...filteredPosts.value]

  nextPosts.sort((a, b) => {
    if (a.is_pinned !== b.is_pinned) {
      return Number(b.is_pinned) - Number(a.is_pinned)
    }

    if (sortMode.value === 'likes') {
      return (b.likes_count || 0) - (a.likes_count || 0)
    }

    if (sortMode.value === 'comments') {
      return (b.comments_count || 0) - (a.comments_count || 0)
    }

    return new Date(b.created_at || 0) - new Date(a.created_at || 0)
  })

  return nextPosts
})

const totalPages = computed(() => {
  return Math.max(1, Math.ceil(sortedPosts.value.length / pageSize))
})

const paginatedPosts = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return sortedPosts.value.slice(start, start + pageSize)
})

const pageNumbers = computed(() => {
  const pages = []
  const total = totalPages.value
  const current = currentPage.value

  if (total <= 7) {
    for (let page = 1; page <= total; page += 1) pages.push(page)
    return pages
  }

  pages.push(1)

  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)

  if (start > 2) pages.push('start-ellipsis')

  for (let page = start; page <= end; page += 1) pages.push(page)

  if (end < total - 1) pages.push('end-ellipsis')

  pages.push(total)
  return pages
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
    month: '2-digit',
    day: '2-digit',
  }).replace(/\. /g, '.').replace(/\.$/, '')
}

const getAuthorInitial = (post) => {
  const name = post.author_nickname || post.author_username || '?'
  return name.slice(0, 1)
}

const goToPage = (page) => {
  if (page < 1 || page > totalPages.value) {
    return
  }

  currentPage.value = page
}

const fetchPosts = async () => {
  try {
    isLoading.value = true
    errorMessage.value = ''

    const response = await getPosts(boardType.value)
    posts.value = response.data
    currentPage.value = 1
  } catch (error) {
    console.error(error)
    errorMessage.value = '게시글 목록을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

watch(boardType, fetchPosts)
watch([searchQuery, sortMode], () => {
  currentPage.value = 1
})
watch(totalPages, (nextTotalPages) => {
  if (currentPage.value > nextTotalPages) {
    currentPage.value = nextTotalPages
  }
})

onMounted(() => {
  fetchPosts()
})
</script>

<template>
  <main class="board-page">
    <section class="board-container">
      <header class="board-header">
        <div class="board-title-group">
          <h1>{{ boardTitle }}</h1>
          <span>{{ boardCountLabel }}</span>
        </div>

        <div class="board-actions">
          <label class="search-field">
            <input
              v-model="searchQuery"
              type="search"
              placeholder="제목, 작성자 검색"
            />
            <span aria-hidden="true">⌕</span>
          </label>

          <select v-model="sortMode" class="sort-select" aria-label="게시글 정렬">
            <option value="latest">최신순</option>
            <option value="comments">댓글순</option>
            <option value="likes">좋아요순</option>
          </select>

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
            <col class="col-title" />
            <col class="col-author" />
            <col class="col-date" />
            <col class="col-count" />
            <col class="col-count" />
          </colgroup>

          <thead>
            <tr>
              <th>제목</th>
              <th>작성자</th>
              <th>작성일</th>
              <th>댓글</th>
              <th>좋아요</th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="post in paginatedPosts"
              :key="post.id"
              :class="{ pinned: post.is_pinned }"
            >
              <td class="title-cell">
                <RouterLink :to="`/boards/${post.board_type}/${post.id}`" class="title-link">
                  <span
                    v-if="post.board_type === 'notice' || post.is_pinned"
                    class="notice-badge"
                  >
                    공지
                  </span>
                  <span class="title-text">{{ post.title }}</span>
                  <span v-if="post.is_pinned" class="pin-mark" aria-label="고정됨">◆</span>
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
                    <span v-else class="default-avatar" aria-hidden="true">
                      {{ getAuthorInitial(post) }}
                    </span>
                  </span>
                  <span
                    class="author-name"
                    :style="post.author_nickname_color ? { color: post.author_nickname_color } : {}"
                  >
                    {{ post.author_nickname }}
                  </span>
                  <img
                    v-if="post.author_tier"
                    :src="getTierIcon(post.author_tier)"
                    :alt="post.author_tier_label || post.author_tier"
                    class="tier-icon"
                  />
                </span>
              </td>
              <td>{{ formatBoardDate(post.created_at) }}</td>
              <td>
                <span class="metric-cell">
                  <span aria-hidden="true">♡</span>
                  {{ post.comments_count }}
                </span>
              </td>
              <td>
                <span class="metric-cell like">
                  <span aria-hidden="true">♥</span>
                  {{ post.likes_count }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>

        <p v-if="filteredPosts.length === 0" class="empty-text">
          조건에 맞는 게시글이 없습니다.
        </p>

        <nav
          v-if="filteredPosts.length > 0"
          class="pagination"
          aria-label="게시글 페이지"
        >
          <button
            type="button"
            :disabled="currentPage === 1"
            @click="goToPage(currentPage - 1)"
          >
            ‹
          </button>
          <template v-for="page in pageNumbers" :key="page">
            <span v-if="typeof page === 'string'" class="page-ellipsis">...</span>
            <button
              v-else
              type="button"
              :class="{ active: page === currentPage }"
              @click="goToPage(page)"
            >
              {{ page }}
            </button>
          </template>
          <button
            type="button"
            :disabled="currentPage === totalPages"
            @click="goToPage(currentPage + 1)"
          >
            ›
          </button>
        </nav>
      </section>
    </section>
  </main>
</template>

<style scoped>
.board-page {
  min-height: 100vh;
  padding: 40px 24px 56px;
  background: #ffffff;
}

.board-container {
  max-width: 1040px;
  margin: 0 auto;
}

.board-header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
  margin-bottom: 34px;
}

.board-title-group {
  min-width: 0;
  display: flex;
  gap: 12px;
  align-items: baseline;
}

.board-title-group h1 {
  margin: 0;
  color: #101828;
  font-size: 28px;
  font-weight: 900;
  line-height: 1.2;
}

.board-title-group span {
  color: #98a2b3;
  font-size: 15px;
  font-weight: 800;
}

.board-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  align-items: center;
}

.search-field {
  box-sizing: border-box;
  width: min(300px, 34vw);
  height: 52px;
  padding: 0 16px;
  display: flex;
  gap: 10px;
  align-items: center;
  border: 1px solid #edf0f4;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 8px 22px rgba(16, 24, 40, 0.04);
}

.search-field input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: #101828;
  font-size: 15px;
  font-weight: 700;
}

.search-field input::placeholder {
  color: #b5bdc9;
}

.search-field span {
  flex: 0 0 auto;
  color: #111827;
  font-size: 26px;
  line-height: 1;
}

.sort-select {
  height: 52px;
  padding: 0 38px 0 16px;
  border: 1px solid #edf0f4;
  border-radius: 10px;
  background: #ffffff;
  color: #101828;
  font-size: 15px;
  font-weight: 900;
  box-shadow: 0 8px 22px rgba(16, 24, 40, 0.04);
  cursor: pointer;
}

.write-button {
  min-height: 52px;
  padding: 0 18px;
  display: inline-flex;
  align-items: center;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 900;
  text-decoration: none;
  border: 0;
  background: #1f7aec;
  color: #ffffff;
}

.board-table-wrap {
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: #ffffff;
  box-shadow: none;
}

.board-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  color: #344054;
  font-size: 15px;
}

.board-table th,
.board-table td {
  height: 80px;
  padding: 0 18px;
  border-bottom: 1px solid #f0f2f5;
  vertical-align: middle;
}

.board-table th {
  height: 50px;
  border-bottom: 0;
  background: #f8f9fb;
  color: #1d2939;
  font-size: 14px;
  font-weight: 900;
  text-align: left;
}

.board-table th:not(:first-child),
.board-table td:not(.title-cell) {
  text-align: center;
}

.board-table tbody tr {
  transition: background 0.16s ease;
}

.board-table tbody tr:hover {
  background: #fbfcff;
}

.board-table tbody tr.pinned .title-text {
  font-weight: 900;
}

.board-table tbody tr:last-child td {
  border-bottom: 0;
}

.col-author { width: 190px; }
.col-date { width: 130px; }
.col-count { width: 112px; }

.title-cell {
  min-width: 0;
  text-align: left;
}

.title-link {
  min-width: 0;
  display: inline-flex;
  max-width: 100%;
  gap: 8px;
  align-items: center;
  color: #1d2939;
  font-weight: 800;
  text-decoration: none;
}

.title-text {
  min-width: 0;
  overflow: hidden;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-link:hover {
  color: #1f7aec;
}

.notice-badge {
  flex: 0 0 auto;
  padding: 4px 8px;
  border-radius: 6px;
  background: #1f7aec;
  color: #ffffff;
  font-size: 13px;
  font-weight: 900;
  line-height: 1.2;
}

.pin-mark {
  flex: 0 0 auto;
  color: #f05d6f;
  font-size: 13px;
  transform: rotate(-18deg);
}

.author-cell {
  color: #475467;
}

.author-chip {
  min-width: 0;
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 9px;
  font-weight: 800;
}

.author-avatar {
  position: relative;
  display: inline-flex;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 50%;
  background: linear-gradient(135deg, #d7efff, #b8f1d5);
  color: #1f2937;
  font-size: 13px;
  font-weight: 900;
}

.author-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.author-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tier-icon {
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  object-fit: contain;
}

.default-avatar {
  display: inline-grid;
  place-items: center;
}

.metric-cell {
  display: inline-flex;
  gap: 7px;
  align-items: center;
  justify-content: center;
  color: #475467;
  font-weight: 800;
}

.metric-cell span {
  color: #667085;
  font-size: 18px;
  line-height: 1;
}

.metric-cell.like span {
  color: #f26f82;
}

.status-text,
.empty-text,
.error-text {
  padding: 46px;
  border: 1px solid #f0f2f5;
  border-radius: 12px;
  background: #ffffff;
  color: #667085;
  font-weight: 800;
  text-align: center;
}

.empty-text {
  margin: 18px 0 0;
}

.error-text {
  color: #ef4444;
}

.pagination {
  margin-top: 34px;
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: center;
}

.pagination button {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #475467;
  font-size: 15px;
  font-weight: 900;
  cursor: pointer;
}

.pagination button:hover:not(:disabled) {
  background: #f1f5f9;
}

.pagination button.active {
  background: #1f7aec;
  color: #ffffff;
  box-shadow: 0 8px 20px rgba(31, 122, 236, 0.28);
}

.pagination button:disabled {
  color: #c0c7d2;
  cursor: not-allowed;
}

.page-ellipsis {
  color: #667085;
  font-size: 14px;
  font-weight: 900;
}

@media (max-width: 720px) {
  .board-page {
    padding: 24px 16px 42px;
  }

  .board-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .board-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .search-field {
    width: 100%;
  }

  .sort-select,
  .write-button {
    flex: 1;
    min-width: 120px;
  }

  .board-table-wrap {
    overflow-x: auto;
  }

  .board-table {
    min-width: 720px;
  }
}
</style>
