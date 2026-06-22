<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createPost } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const boardType = computed(() => route.params.boardType || 'free')

const boardTitle = computed(() => {
  if (boardType.value === 'notice') return '공지사항'
  return '자유게시판'
})

const title = ref('')
const content = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

const handleSubmit = async () => {
  errorMessage.value = ''

  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  if (!title.value.trim() || !content.value.trim()) {
    errorMessage.value = '제목과 내용을 입력해주세요.'
    return
  }

  try {
    isLoading.value = true

    const response = await createPost({
      board_type: boardType.value,
      title: title.value,
      content: content.value,
    })

    router.push(`/boards/${response.data.board_type}/${response.data.id}`)
  } catch (error) {
    console.error(error)
    errorMessage.value =
      error.response?.data?.detail || '게시글 작성에 실패했습니다.'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="board-page">
    <section class="write-container">
      <header class="write-header">
        <div>
          <p class="eyebrow">WRITE</p>
          <h1>{{ boardTitle }} 글쓰기</h1>
        </div>

        <RouterLink :to="`/boards/${boardType}`" class="back-button">
          목록으로
        </RouterLink>
      </header>

      <form class="write-form" @submit.prevent="handleSubmit">
        <input
          v-model="title"
          type="text"
          placeholder="제목을 입력하세요"
        />

        <textarea
          v-model="content"
          rows="12"
          placeholder="내용을 입력하세요"
        ></textarea>

        <p v-if="errorMessage" class="error-text">
          {{ errorMessage }}
        </p>

        <button type="submit" :disabled="isLoading">
          {{ isLoading ? '작성 중...' : '등록하기' }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.board-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.write-container {
  max-width: 860px;
  margin: 0 auto;
}

.write-header {
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

.write-header h1 {
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

.write-form {
  display: grid;
  gap: 14px;
  padding: 24px;
  border: 1px solid #e5e8f0;
  border-radius: 22px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.write-form input,
.write-form textarea {
  width: 100%;
  padding: 15px 16px;
  border: 1px solid #d0d5dd;
  border-radius: 14px;
  font-size: 15px;
  outline: none;
}

.write-form textarea {
  resize: vertical;
  line-height: 1.6;
}

.write-form input:focus,
.write-form textarea:focus {
  border-color: #2563eb;
}

.write-form button {
  padding: 15px 16px;
  border: 0;
  border-radius: 14px;
  background: #2563eb;
  color: #ffffff;
  font-size: 16px;
  font-weight: 900;
  cursor: pointer;
}

.write-form button:disabled {
  background: #98a2b3;
  cursor: not-allowed;
}

.error-text {
  margin: 0;
  color: #ef4444;
  font-size: 14px;
}
</style>