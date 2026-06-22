<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getPost, updatePost } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const boardType = computed(() => route.params.boardType || 'free')
const postId = computed(() => route.params.postId)

const title = ref('')
const content = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

const boardTitle = computed(() => {
  if (boardType.value === 'notice') return '공지사항'
  return '자유게시판'
})

const fetchPost = async () => {
  try {
    const response = await getPost(postId.value)
    const post = response.data

    if (authStore.user?.id !== post.author) {
      alert('작성자만 수정할 수 있습니다.')
      router.push(`/boards/${boardType.value}/${postId.value}`)
      return
    }

    title.value = post.title
    content.value = post.content
  } catch (error) {
    console.error(error)
    errorMessage.value = '게시글을 불러오지 못했습니다.'
  }
}

const handleSubmit = async () => {
  errorMessage.value = ''

  if (!title.value.trim() || !content.value.trim()) {
    errorMessage.value = '제목과 내용을 입력해주세요.'
    return
  }

  try {
    isLoading.value = true

    const response = await updatePost(postId.value, {
      title: title.value,
      content: content.value,
      board_type: boardType.value,
    })

    router.push(`/boards/${response.data.board_type}/${response.data.id}`)
  } catch (error) {
    console.error(error)
    errorMessage.value =
      error.response?.data?.detail || '게시글 수정에 실패했습니다.'
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  fetchPost()
})
</script>

<template>
  <main class="board-page">
    <section class="write-container">
      <header class="write-header">
        <div>
          <p class="eyebrow">EDIT</p>
          <h1>{{ boardTitle }} 글 수정</h1>
        </div>

        <RouterLink :to="`/boards/${boardType}/${postId}`" class="back-button">
          상세로
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
          {{ isLoading ? '수정 중...' : '수정하기' }}
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