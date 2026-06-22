<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

const handleSignup = async () => {
  errorMessage.value = ''

  if (!username.value || !password.value || !passwordConfirm.value) {
    errorMessage.value = '아이디와 비밀번호를 입력해주세요.'
    return
  }

  if (password.value !== passwordConfirm.value) {
    errorMessage.value = '비밀번호가 일치하지 않습니다.'
    return
  }

  try {
    isLoading.value = true

    await authStore.signup({
      username: username.value,
      email: email.value,
      password: password.value,
      password_confirm: passwordConfirm.value,
    })

    router.push('/')
  } catch (error) {
    console.error(error)
    errorMessage.value = '회원가입에 실패했습니다.'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card">
      <h1>회원가입</h1>
      <p>생활 장소 추천 서비스를 이용하기 위한 계정을 만들어주세요.</p>

      <form @submit.prevent="handleSignup" class="auth-form">
        <input v-model="username" type="text" placeholder="아이디" />
        <input v-model="email" type="email" placeholder="이메일 선택" />
        <input v-model="password" type="password" placeholder="비밀번호" />
        <input v-model="passwordConfirm" type="password" placeholder="비밀번호 확인" />

        <p v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </p>

        <button type="submit" :disabled="isLoading">
          {{ isLoading ? '처리 중...' : '회원가입' }}
        </button>
      </form>

      <RouterLink to="/login" class="auth-link">
        이미 계정이 있으신가요? 로그인
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