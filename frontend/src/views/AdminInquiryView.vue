<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getAdminInquiries, updateAdminInquiry } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const inquiries = ref([])
const replies = ref({})
const errorMessage = ref('')

const fetchInquiries = async () => {
  if (authStore.isLoggedIn && !authStore.user?.is_staff) {
    await authStore.fetchMe()
  }

  if (!authStore.user?.is_staff) {
    router.push('/')
    return
  }

  try {
    const response = await getAdminInquiries()
    inquiries.value = response.data
    replies.value = Object.fromEntries(response.data.map((item) => [item.id, item.admin_reply || '']))
  } catch (error) {
    console.error(error)
    errorMessage.value = '문의 목록을 불러오지 못했습니다.'
  }
}

const submitReply = async (inquiry) => {
  const response = await updateAdminInquiry(inquiry.id, {
    status: 'answered',
    admin_reply: replies.value[inquiry.id],
  })
  Object.assign(inquiry, response.data)
}

onMounted(fetchInquiries)
</script>

<template>
  <main class="page">
    <section class="container">
      <header class="header">
        <div>
          <p class="eyebrow">ADMIN</p>
          <h1>문의 관리</h1>
        </div>
      </header>

      <p v-if="errorMessage" class="status-card error">{{ errorMessage }}</p>

      <article v-for="inquiry in inquiries" :key="inquiry.id" class="card">
        <div class="top">
          <span class="badge">{{ inquiry.status === 'answered' ? '답변 완료' : '대기' }}</span>
          <span>{{ inquiry.author_username }}</span>
          <span>{{ new Date(inquiry.created_at).toLocaleString() }}</span>
        </div>
        <h2>{{ inquiry.title }}</h2>
        <p class="content">{{ inquiry.content }}</p>
        <div v-if="inquiry.status === 'answered' || inquiry.status === 'closed'" class="reply-box">
          <strong>관리자 답변</strong>
          <p>{{ inquiry.admin_reply || '등록된 답변이 없습니다.' }}</p>
        </div>
        <template v-else>
          <textarea v-model="replies[inquiry.id]" rows="4" placeholder="관리자 답변"></textarea>
          <button type="button" @click="submitReply(inquiry)">답변 저장</button>
        </template>
      </article>

      <p v-if="inquiries.length === 0" class="status-card">등록된 문의가 없습니다.</p>
    </section>
  </main>
</template>

<style scoped>
.page { min-height: 100vh; padding: 40px 24px; background: #f6f7fb; }
.container { max-width: 960px; margin: 0 auto; }
.header { margin-bottom: 20px; }
.eyebrow { margin: 0 0 6px; color: #f97316; font-size: 13px; font-weight: 900; letter-spacing: .08em; }
h1, h2 { margin: 0; color: #111827; }
.card, .status-card { margin-bottom: 14px; padding: 20px; border: 1px solid #e5e8f0; border-radius: 18px; background: #fff; box-shadow: 0 10px 28px rgba(20,35,70,.08); }
.top { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; color: #667085; font-size: 13px; font-weight: 800; }
.badge { padding: 5px 9px; border-radius: 999px; background: #fff7ed; color: #f97316; }
.content { padding: 14px; border-radius: 14px; background: #f9fafb; white-space: pre-wrap; }
.reply-box { margin-top: 12px; padding: 14px; border-radius: 14px; background: #eff6ff; color: #1d4ed8; }
.reply-box p { margin: 6px 0 0; color: #344054; white-space: pre-wrap; }
textarea { width: 100%; padding: 14px; border: 1px solid #d0d5dd; border-radius: 14px; outline: none; }
button { margin-top: 10px; border: 0; border-radius: 12px; background: #2563eb; color: #fff; padding: 10px 14px; font-weight: 900; cursor: pointer; }
.error { color: #ef4444; }
</style>
