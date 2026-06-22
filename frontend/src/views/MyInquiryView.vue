<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { getMyInquiries } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const inquiries = ref([])
const isLoading = ref(false)
const errorMessage = ref('')

const statusLabel = (status) => {
  if (status === 'answered') {
    return '답변완료'
  }

  return '답변대기'
}

const fetchInquiries = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  try {
    isLoading.value = true
    errorMessage.value = ''
    const response = await getMyInquiries()
    inquiries.value = response.data
  } catch (error) {
    console.error(error)
    errorMessage.value = error.response?.data?.detail || '문의 내역을 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchInquiries)
</script>

<template>
  <main class="page">
    <section class="container">
      <header class="page-title">
        <div>
          <p class="eyebrow">CUSTOMER CENTER</p>
          <h1>내 문의</h1>
        </div>
        <RouterLink to="/inquiries/new" class="write-button">
          문의하기
        </RouterLink>
      </header>

      <p v-if="isLoading" class="status-card">문의 내역을 불러오는 중입니다.</p>
      <p v-else-if="errorMessage" class="status-card error">{{ errorMessage }}</p>

      <section v-else class="inquiry-list">
        <article v-for="inquiry in inquiries" :key="inquiry.id" class="inquiry-card">
          <div class="inquiry-header">
            <div>
              <h2>{{ inquiry.title }}</h2>
              <p>{{ new Date(inquiry.created_at).toLocaleString() }}</p>
            </div>
            <span class="status-badge" :class="{ answered: inquiry.status === 'answered' }">
              {{ statusLabel(inquiry.status) }}
            </span>
          </div>

          <p class="inquiry-content">{{ inquiry.content }}</p>

          <div v-if="inquiry.status === 'answered'" class="reply-box">
            <strong>답변 내용</strong>
            <p>{{ inquiry.admin_reply || '등록된 답변 내용이 없습니다.' }}</p>
          </div>
        </article>

        <p v-if="inquiries.length === 0" class="status-card">
          작성한 문의가 없습니다.
        </p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.container {
  max-width: 880px;
  margin: 0 auto;
}

.page-title {
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
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

.write-button {
  min-height: 40px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  border-radius: 8px;
  background: #2563eb;
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
  text-decoration: none;
}

.inquiry-list {
  display: grid;
  gap: 12px;
}

.inquiry-card,
.status-card {
  border: 1px solid #e5e8f0;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.inquiry-card {
  padding: 20px;
  display: grid;
  gap: 14px;
}

.inquiry-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.inquiry-header h2 {
  font-size: 20px;
  line-height: 1.35;
}

.inquiry-header p {
  margin: 5px 0 0;
  color: #667085;
  font-size: 13px;
  font-weight: 700;
}

.status-badge {
  flex: 0 0 auto;
  padding: 6px 10px;
  border-radius: 999px;
  background: #fef3c7;
  color: #92400e;
  font-size: 12px;
  font-weight: 900;
}

.status-badge.answered {
  background: #dcfce7;
  color: #166534;
}

.inquiry-content {
  margin: 0;
  color: #344054;
  line-height: 1.7;
  white-space: pre-wrap;
}

.reply-box {
  padding: 14px;
  display: grid;
  gap: 6px;
  border-radius: 8px;
  background: #f9fafb;
}

.reply-box strong {
  color: #111827;
  font-size: 14px;
}

.reply-box p {
  margin: 0;
  color: #344054;
  line-height: 1.7;
  white-space: pre-wrap;
}

.status-card {
  padding: 32px;
  color: #667085;
  font-weight: 800;
  text-align: center;
}

.error {
  color: #ef4444;
}

@media (max-width: 640px) {
  .page {
    padding: 28px 16px;
  }

  .page-title {
    align-items: flex-start;
    flex-direction: column;
  }

  .inquiry-header {
    align-items: stretch;
    flex-direction: column;
  }

  .status-badge {
    width: fit-content;
  }
}
</style>
