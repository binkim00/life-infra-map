<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { createInquiry } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const title = ref('')
const content = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)

const submitInquiry = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  try {
    isSubmitting.value = true
    errorMessage.value = ''
    await createInquiry({ title: title.value, content: content.value })
    router.push('/mypage')
  } catch (error) {
    console.error(error)
    errorMessage.value = error.response?.data?.detail || '문의 등록에 실패했습니다.'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="page">
    <form class="form-card" @submit.prevent="submitInquiry">
      <p class="eyebrow">INQUIRY</p>
      <h1>문의하기</h1>
      <input v-model="title" type="text" placeholder="문의 제목" />
      <textarea v-model="content" rows="8" placeholder="문의 내용을 입력하세요"></textarea>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
      <button type="submit" :disabled="isSubmitting">{{ isSubmitting ? '등록 중' : '문의 등록' }}</button>
    </form>
  </main>
</template>

<style scoped>
.page { min-height: 100vh; padding: 40px 24px; background: #f6f7fb; }
.form-card { max-width: 720px; margin: 0 auto; padding: 24px; display: grid; gap: 14px; border: 1px solid #e5e8f0; border-radius: 18px; background: #fff; box-shadow: 0 10px 28px rgba(20,35,70,.08); }
.eyebrow { margin: 0; color: #2563eb; font-size: 13px; font-weight: 900; letter-spacing: .08em; }
h1 { margin: 0; color: #111827; }
input, textarea { width: 100%; padding: 14px; border: 1px solid #d0d5dd; border-radius: 14px; outline: none; }
button { justify-self: end; border: 0; border-radius: 12px; background: #2563eb; color: #fff; padding: 11px 16px; font-weight: 900; cursor: pointer; }
button:disabled { opacity: .6; cursor: not-allowed; }
.error { color: #ef4444; font-weight: 800; }
</style>
