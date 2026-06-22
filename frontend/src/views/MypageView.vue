<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { getMypage } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const data = ref(null)
const isLoading = ref(false)
const errorMessage = ref('')
const selectedSection = ref('profile')

const sections = [
  { value: 'profile', label: '내 프로필' },
  { value: 'posts', label: '내가 쓴 글' },
  { value: 'comments', label: '내가 쓴 댓글' },
  { value: 'liked', label: '내가 좋아요한 글' },
  { value: 'inquiries', label: '내 문의내역' },
]

const unreadCount = computed(() => {
  return data.value?.notifications?.filter((notification) => !notification.is_read).length || 0
})

const statusLabel = computed(() => {
  if (!data.value?.penalty?.is_suspended) return '정상 이용 가능'
  return data.value.penalty.is_permanent_ban ? '영구밴' : '활동정지'
})

const fetchMypage = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  try {
    isLoading.value = true
    const response = await getMypage()
    data.value = response.data
  } catch (error) {
    console.error(error)
    errorMessage.value = '마이페이지 정보를 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchMypage)
</script>

<template>
  <main class="mypage">
    <section class="mypage-container">
      <header class="page-title">
        <p class="eyebrow">MY PAGE</p>
        <h1>마이페이지</h1>
      </header>

      <p v-if="isLoading" class="status-card">정보를 불러오는 중입니다.</p>
      <p v-else-if="errorMessage" class="status-card error">{{ errorMessage }}</p>

      <div v-else-if="data" class="mypage-layout">
        <section class="profile-card">
          <div class="profile-main">
            <span class="status-badge" :class="{ warning: data.penalty.is_suspended }">
              {{ statusLabel }}
            </span>
            <h2>{{ data.user.username }}</h2>
            <p>{{ data.user.email || '이메일 없음' }}</p>
          </div>

          <div class="profile-actions">
            <RouterLink to="/notifications" class="secondary-action">
              알림 {{ unreadCount ? unreadCount : '' }}
            </RouterLink>
            <RouterLink to="/inquiries/new" class="primary-action">
              문의하기
            </RouterLink>
          </div>
        </section>

        <section class="section-control">
          <label for="mypage-section">메뉴 선택</label>
          <select id="mypage-section" v-model="selectedSection">
            <option v-for="section in sections" :key="section.value" :value="section.value">
              {{ section.label }}
            </option>
          </select>
        </section>

        <section v-if="selectedSection === 'profile'" class="panel profile-panel">
          <div class="profile-info-grid">
            <article>
              <span>아이디</span>
              <strong>{{ data.user.username }}</strong>
            </article>
            <article>
              <span>이메일</span>
              <strong>{{ data.user.email || '이메일 없음' }}</strong>
            </article>
            <article>
              <span>가입일</span>
              <strong>{{ new Date(data.user.date_joined).toLocaleDateString() }}</strong>
            </article>
            <article>
              <span>계정 유형</span>
              <strong>{{ data.user.is_staff ? '관리자 계정' : '일반 사용자' }}</strong>
            </article>
          </div>

          <div v-if="data.penalty.is_suspended" class="penalty-detail">
            <strong>{{ data.penalty.is_permanent_ban ? '영구밴 상태입니다.' : '활동정지 상태입니다.' }}</strong>
            <p v-if="data.penalty.reason">사유 {{ data.penalty.reason }}</p>
            <p v-if="data.penalty.suspended_until">해제일 {{ new Date(data.penalty.suspended_until).toLocaleString() }}</p>
          </div>

          <div class="summary-grid">
            <article class="summary-card">
              <strong>{{ data.posts.length }}</strong>
              <span>작성 글</span>
            </article>
            <article class="summary-card">
              <strong>{{ data.comments.length }}</strong>
              <span>작성 댓글</span>
            </article>
            <article class="summary-card">
              <strong>{{ data.liked_posts.length }}</strong>
              <span>좋아요한 글</span>
            </article>
            <article class="summary-card">
              <strong>{{ data.inquiries.length }}</strong>
              <span>문의</span>
            </article>
          </div>
        </section>

        <section v-else-if="selectedSection === 'posts'" class="panel">
          <h2>내가 쓴 글</h2>
          <RouterLink v-for="post in data.posts" :key="post.id" :to="`/boards/${post.board_type}/${post.id}`"
            class="activity-item link-item">
            <strong>{{ post.title }}</strong>
            <span>댓글 {{ post.comments_count }} · 좋아요 {{ post.likes_count }}</span>
          </RouterLink>
          <p v-if="data.posts.length === 0" class="empty">작성한 글이 없습니다.</p>
        </section>

        <section v-else-if="selectedSection === 'comments'" class="panel">
          <h2>내가 쓴 댓글</h2>
          <div v-for="comment in data.comments" :key="comment.id" class="activity-item">
            <strong>{{ comment.content }}</strong>
            <span>{{ new Date(comment.created_at).toLocaleDateString() }}</span>
          </div>
          <p v-if="data.comments.length === 0" class="empty">작성한 댓글이 없습니다.</p>
        </section>

        <section v-else-if="selectedSection === 'liked'" class="panel">
          <h2>내가 좋아요한 글</h2>
          <RouterLink v-for="post in data.liked_posts" :key="post.id" :to="`/boards/${post.board_type}/${post.id}`"
            class="activity-item link-item">
            <strong>{{ post.title }}</strong>
            <span>{{ post.author_username }} · 댓글 {{ post.comments_count }} · 좋아요 {{ post.likes_count }}</span>
          </RouterLink>
          <p v-if="data.liked_posts.length === 0" class="empty">좋아요한 글이 없습니다.</p>
        </section>

        <section v-else class="panel">
          <h2>내 문의내역</h2>
          <div v-for="inquiry in data.inquiries" :key="inquiry.id" class="activity-item">
            <strong>{{ inquiry.title }}</strong>
            <span>{{ inquiry.status === 'answered' ? '답변 완료' : '답변 대기' }}</span>
            <p v-if="inquiry.admin_reply">{{ inquiry.admin_reply }}</p>
          </div>
          <p v-if="data.inquiries.length === 0" class="empty">작성한 문의가 없습니다.</p>
        </section>
      </div>
    </section>
  </main>
</template>

<style scoped>
.mypage {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.mypage-container {
  max-width: 960px;
  margin: 0 auto;
}

.page-title {
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

h1,
h2 {
  margin: 0;
  color: #111827;
}

.mypage-layout {
  display: grid;
  gap: 14px;
}

.profile-card,
.section-control,
.summary-card,
.panel,
.status-card {
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.profile-card {
  padding: 24px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: start;
}

.profile-main h2 {
  margin-top: 10px;
  font-size: 30px;
}

.profile-main p {
  margin: 6px 0 0;
  color: #667085;
  font-weight: 700;
}

.status-badge {
  display: inline-flex;
  padding: 6px 10px;
  border-radius: 999px;
  background: #dbeafe;
  color: #2563eb;
  font-size: 12px;
  font-weight: 900;
}

.status-badge.warning {
  background: #fff7ed;
  color: #f97316;
}

.profile-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.primary-action,
.secondary-action {
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
}

.primary-action {
  background: #2563eb;
  color: #ffffff;
}

.secondary-action {
  border: 1px solid #d0d5dd;
  background: #ffffff;
  color: #344054;
}

.section-control {
  padding: 18px;
  display: grid;
  gap: 8px;
}

.section-control label {
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

.section-control select {
  width: 100%;
  padding: 13px 14px;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  background: #ffffff;
  color: #111827;
  font-size: 15px;
  font-weight: 800;
  outline: none;
}

.panel {
  padding: 22px;
}

.profile-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.profile-info-grid article {
  padding: 14px;
  border-radius: 14px;
  background: #f9fafb;
}

.profile-info-grid span {
  display: block;
  margin-bottom: 5px;
  color: #667085;
  font-size: 12px;
  font-weight: 900;
}

.profile-info-grid strong {
  color: #111827;
}

.penalty-detail {
  margin-top: 14px;
  padding: 14px;
  border-radius: 14px;
  background: #fff7ed;
  color: #9a3412;
}

.penalty-detail p {
  margin: 6px 0 0;
}

.summary-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  padding: 18px;
  display: grid;
  gap: 4px;
}

.summary-card strong {
  color: #2563eb;
  font-size: 28px;
}

.summary-card span,
.activity-item span,
.empty {
  color: #667085;
  font-weight: 700;
}

.activity-item {
  display: grid;
  gap: 5px;
  margin-top: 10px;
  padding: 13px;
  border-radius: 12px;
  background: #f9fafb;
  color: #111827;
  text-decoration: none;
}

.activity-item p {
  margin: 0;
  color: #344054;
  line-height: 1.6;
  white-space: pre-wrap;
}

.link-item:hover {
  background: #eff6ff;
}

.status-card {
  padding: 32px;
  text-align: center;
}

.error {
  color: #ef4444;
}

@media (max-width: 820px) {
  .profile-card,
  .profile-info-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .profile-actions {
    justify-content: flex-start;
  }
}
</style>
