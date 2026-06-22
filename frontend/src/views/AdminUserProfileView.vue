<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { createUserNotification, createUserPenalty, getAdminUser } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const profile = ref(null)
const reason = ref('')
const message = ref('')
const selectedPenalty = ref('warning')
const errorMessage = ref('')

const penaltyOptions = [
  ['warning', '경고만'],
  ['suspend_3_days', '3일 활동정지'],
  ['suspend_7_days', '7일 활동정지'],
  ['suspend_30_days', '30일 활동정지'],
  ['suspend_1_year', '1년 사용정지'],
  ['permanent_ban', '영구밴'],
]

const user = computed(() => profile.value?.user)

const fetchProfile = async () => {
  if (authStore.isLoggedIn && !authStore.user?.is_staff) {
    await authStore.fetchMe()
  }

  if (!authStore.user?.is_staff) {
    router.push('/')
    return
  }

  try {
    const response = await getAdminUser(route.params.userId)
    profile.value = response.data
  } catch (error) {
    console.error(error)
    errorMessage.value = '유저 프로필을 불러오지 못했습니다.'
  }
}

const applyPenalty = async () => {
  if (!reason.value.trim()) {
    alert('제재 사유를 입력해주세요.')
    return
  }

  await createUserPenalty(user.value.id, {
    penalty_type: selectedPenalty.value,
    reason: reason.value,
  })
  reason.value = ''
  await fetchProfile()
}

const sendMessage = async () => {
  if (!message.value.trim()) {
    alert('관리자 메시지를 입력해주세요.')
    return
  }

  await createUserNotification(user.value.id, {
    title: '관리자 메시지',
    message: message.value,
  })
  message.value = ''
  alert('메시지를 보냈습니다.')
}

onMounted(fetchProfile)
</script>

<template>
  <main class="profile-page">
    <section class="profile-container">
      <p v-if="errorMessage" class="status-card error">{{ errorMessage }}</p>

      <template v-else-if="profile">
        <header class="profile-header">
          <div>
            <p class="eyebrow">USER PROFILE</p>
            <h1>#{{ user.id }} {{ user.username }}</h1>
            <p>{{ user.email || '이메일 없음' }}</p>
          </div>
          <RouterLink to="/admin/users" class="back-link">유저 목록</RouterLink>
        </header>

        <section class="summary-grid">
          <article class="summary-card"><strong>{{ user.posts_count }}</strong><span>작성 글</span></article>
          <article class="summary-card"><strong>{{ user.comments_count }}</strong><span>작성 댓글</span></article>
          <article class="summary-card"><strong>{{ user.received_reports_count }}</strong><span>받은 신고</span></article>
          <article class="summary-card"><strong>{{ user.is_staff ? '관리자' : '일반' }}</strong><span>권한</span></article>
        </section>

        <section class="panel" :class="{ warning: user.current_penalty }">
          <h2>현재 제재 상태</h2>
          <p v-if="user.current_penalty">{{ user.current_penalty.penalty_type }} / {{ user.current_penalty.reason }}</p>
          <p v-else>현재 활성 제재가 없습니다.</p>
        </section>

        <section class="panel">
          <h2>제재/메시지</h2>
          <select v-model="selectedPenalty">
            <option v-for="[value, label] in penaltyOptions" :key="value" :value="value">{{ label }}</option>
          </select>
          <input v-model="reason" type="text" placeholder="제재 사유" />
          <button type="button" @click="applyPenalty">제재 적용</button>
          <input v-model="message" type="text" placeholder="관리자 메시지" />
          <button type="button" class="message-button" @click="sendMessage">메시지 보내기</button>
        </section>

        <section class="panel">
          <h2>최근 제재 이력</h2>
          <article v-for="penalty in profile.penalties" :key="penalty.id" class="item">
            <strong>{{ penalty.penalty_type }}</strong>
            <p>{{ penalty.reason }}</p>
          </article>
          <p v-if="profile.penalties.length === 0" class="muted">제재 이력이 없습니다.</p>
        </section>

        <section class="panel">
          <h2>작성한 게시글</h2>
          <RouterLink v-for="post in profile.posts" :key="post.id" :to="`/boards/${post.board_type}/${post.id}`" class="item link-item">
            {{ post.title }}
          </RouterLink>
          <p v-if="profile.posts.length === 0" class="muted">작성한 게시글이 없습니다.</p>
        </section>

        <section class="panel">
          <h2>작성한 댓글</h2>
          <article v-for="comment in profile.comments" :key="comment.id" class="item">
            {{ comment.content }}
          </article>
          <p v-if="profile.comments.length === 0" class="muted">작성한 댓글이 없습니다.</p>
        </section>
      </template>
    </section>
  </main>
</template>

<style scoped>
.profile-page { min-height: 100vh; padding: 40px 24px; background: #f6f7fb; }
.profile-container { max-width: 1040px; margin: 0 auto; }
.profile-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 20px; }
.eyebrow { margin: 0 0 6px; color: #2563eb; font-size: 13px; font-weight: 900; letter-spacing: .08em; }
h1, h2 { margin: 0; color: #111827; }
.profile-header p { color: #667085; font-weight: 700; }
.back-link, button { border: 0; border-radius: 999px; background: #2563eb; color: #fff; padding: 10px 14px; font-weight: 900; text-decoration: none; cursor: pointer; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.summary-card, .panel, .status-card { padding: 18px; border: 1px solid #e5e8f0; border-radius: 18px; background: #fff; box-shadow: 0 10px 28px rgba(20,35,70,.08); }
.summary-card { display: grid; gap: 4px; }
.summary-card strong { color: #2563eb; font-size: 24px; }
.summary-card span, .muted { color: #667085; font-weight: 700; }
.panel { margin-bottom: 14px; }
.panel.warning { border-color: #f97316; background: #fff7ed; }
select, input { width: 100%; margin-top: 10px; padding: 12px; border: 1px solid #d0d5dd; border-radius: 12px; outline: none; }
button { margin-top: 10px; }
.message-button { background: #111827; }
.item { display: block; margin-top: 10px; padding: 12px; border-radius: 12px; background: #f9fafb; color: #111827; text-decoration: none; }
.error { color: #ef4444; }
@media (max-width: 720px) { .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .profile-header { flex-direction: column; } }
</style>
