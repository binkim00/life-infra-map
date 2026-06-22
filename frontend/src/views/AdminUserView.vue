<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { createUserNotification, createUserPenalty, getAdminUsers } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const users = ref([])
const reasonByUser = ref({})
const messageByUser = ref({})
const errorMessage = ref('')

const penalties = [
  ['suspend_3_days', '3일 활동정지'],
  ['suspend_7_days', '7일 활동정지'],
  ['suspend_30_days', '30일 활동정지'],
  ['suspend_1_year', '1년 사용정지'],
  ['permanent_ban', '영구밴'],
]

const fetchUsers = async () => {
  if (authStore.isLoggedIn && !authStore.user?.is_staff) {
    await authStore.fetchMe()
  }

  if (!authStore.user?.is_staff) {
    router.push('/')
    return
  }

  try {
    const response = await getAdminUsers()
    users.value = response.data
  } catch (error) {
    console.error(error)
    errorMessage.value = '유저 목록을 불러오지 못했습니다.'
  }
}

const applyPenalty = async (user, penaltyType) => {
  const reason = reasonByUser.value[user.id]?.trim()
  if (!reason) {
    alert('조치 사유를 입력해주세요.')
    return
  }

  await createUserPenalty(user.id, { penalty_type: penaltyType, reason })
  await fetchUsers()
}

const sendMessage = async (user) => {
  const message = messageByUser.value[user.id]?.trim()
  if (!message) {
    alert('메시지를 입력해주세요.')
    return
  }

  await createUserNotification(user.id, {
    title: '관리자 메시지',
    message,
  })
  messageByUser.value[user.id] = ''
  alert('메시지를 보냈습니다.')
}

onMounted(fetchUsers)
</script>

<template>
  <main class="page">
    <section class="container">
      <p class="eyebrow">ADMIN</p>
      <h1>유저 관리</h1>
      <p v-if="errorMessage" class="status-card error">{{ errorMessage }}</p>

      <article v-for="user in users" :key="user.id" class="card">
        <div class="top">
          <RouterLink :to="`/admin/users/${user.id}`" class="user-link">
            #{{ user.id }} {{ user.username }}
          </RouterLink>
          <span>{{ user.email || '-' }}</span>
          <span>신고 {{ user.received_reports_count }}</span>
          <span>글 {{ user.posts_count }}</span>
          <span>댓글 {{ user.comments_count }}</span>
        </div>
        <p v-if="user.current_penalty" class="penalty">
          현재 제재: {{ user.current_penalty.penalty_type }} / {{ user.current_penalty.reason }}
        </p>
        <input v-model="reasonByUser[user.id]" type="text" placeholder="조치 사유" />
        <div class="actions">
          <button v-for="[value, label] in penalties" :key="value" type="button" @click="applyPenalty(user, value)">
            {{ label }}
          </button>
        </div>
        <input v-model="messageByUser[user.id]" type="text" placeholder="관리자 메시지" />
        <button type="button" class="message-button" @click="sendMessage(user)">메시지 보내기</button>
      </article>
    </section>
  </main>
</template>

<style scoped>
.page { min-height: 100vh; padding: 40px 24px; background: #f6f7fb; }
.container { max-width: 1100px; margin: 0 auto; }
.eyebrow { margin: 0 0 6px; color: #f97316; font-size: 13px; font-weight: 900; letter-spacing: .08em; }
h1 { margin: 0 0 20px; color: #111827; }
.card, .status-card { margin-bottom: 14px; padding: 20px; border: 1px solid #e5e8f0; border-radius: 18px; background: #fff; box-shadow: 0 10px 28px rgba(20,35,70,.08); }
.top, .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.top { color: #667085; font-size: 14px; }
.top strong { color: #111827; }
.user-link { color: #111827; font-weight: 900; text-decoration: none; }
.user-link:hover { color: #2563eb; }
.penalty { padding: 10px 12px; border-radius: 12px; background: #fff7ed; color: #f97316; font-weight: 900; }
input { width: 100%; margin-top: 10px; padding: 12px; border: 1px solid #d0d5dd; border-radius: 12px; outline: none; }
button { border: 0; border-radius: 999px; background: #f97316; color: #fff; padding: 9px 12px; font-weight: 900; cursor: pointer; }
.actions { margin-top: 10px; }
.message-button { margin-top: 10px; background: #2563eb; }
.error { color: #ef4444; }
</style>
