<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const errorMessage = ref('')
const penaltyInfo = ref(null)
const isLoading = ref(false)

const handleLogin = async () => {
  errorMessage.value = ''
  penaltyInfo.value = null

  if (!username.value || !password.value) {
    errorMessage.value = '아이디와 비밀번호를 입력해주세요.'
    return
  }

  try {
    isLoading.value = true

    await authStore.login({
      username: username.value,
      password: password.value,
    })

    router.push('/')
  } catch (error) {
    console.error(error)
    if (error.response?.data?.penalty) {
      errorMessage.value = error.response.data.detail
      penaltyInfo.value = error.response.data.penalty
    } else {
      errorMessage.value = '아이디 또는 비밀번호가 올바르지 않습니다.'
    }
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card">
      <h1>로그인</h1>
      <p>저장한 장소와 개인화 추천 기능을 이용할 수 있습니다.</p>

      <form @submit.prevent="handleLogin" class="auth-form">
        <input v-model="username" type="text" placeholder="아이디" />
        <input v-model="password" type="password" placeholder="비밀번호" />

        <p v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </p>

        <div v-if="penaltyInfo" class="penalty-box">
          <strong>
            {{ penaltyInfo.is_permanent_ban ? '현재 계정은 영구밴 상태입니다.' : '현재 계정은 활동정지 상태입니다.' }}
          </strong>
          <p v-if="penaltyInfo.reason">사유: {{ penaltyInfo.reason }}</p>
          <p v-if="penaltyInfo.message">관리자 메시지: {{ penaltyInfo.message }}</p>
          <p v-if="penaltyInfo.end_at">정지 해제일: {{ new Date(penaltyInfo.end_at).toLocaleString() }}</p>
        </div>

        <button type="submit" :disabled="isLoading">
          {{ isLoading ? '로그인 중...' : '로그인' }}
        </button>
      </form>

      <RouterLink to="/signup" class="auth-link">
        계정이 없으신가요? 회원가입
      </RouterLink>
    </section>
  </main>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: #f6f7fb;
}

.auth-card {
  width: min(420px, 100%);
  padding: 32px;
  background: #ffffff;
  border: 1px solid #e5e8f0;
  border-radius: 24px;
  box-shadow: 0 18px 48px rgba(20, 35, 70, 0.12);
}

.auth-card h1 {
  margin: 0;
  color: #111827;
  font-size: 30px;
}

.auth-card p {
  margin: 10px 0 24px;
  color: #667085;
  line-height: 1.5;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.auth-form input {
  padding: 15px 16px;
  border: 1px solid #d0d5dd;
  border-radius: 14px;
  font-size: 15px;
  outline: none;
}

.auth-form input:focus {
  border-color: #2563eb;
}

.auth-form button {
  margin-top: 8px;
  padding: 15px 16px;
  border: 0;
  border-radius: 14px;
  background: #2563eb;
  color: #ffffff;
  font-size: 16px;
  font-weight: 800;
  cursor: pointer;
}

.auth-form button:disabled {
  background: #98a2b3;
  cursor: not-allowed;
}

.error-message {
  margin: 0 !important;
  color: #ef4444 !important;
  font-size: 14px;
}

.penalty-box {
  padding: 12px;
  border-radius: 12px;
  background: #fff7ed;
  color: #9a3412;
}

.penalty-box p {
  margin: 6px 0 0;
  color: #9a3412;
  font-size: 13px;
}

.auth-link {
  margin-top: 18px;
  display: block;
  color: #2563eb;
  font-size: 14px;
  font-weight: 800;
  text-align: center;
  text-decoration: none;
}
</style>
