<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const nickname = ref('')
const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const profileImageFile = ref(null)
const profileImagePreviewUrl = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

const handleProfileImageChange = (event) => {
  const file = event.target.files?.[0]

  profileImageFile.value = file || null
  profileImagePreviewUrl.value = file ? URL.createObjectURL(file) : ''
}

const handleSignup = async () => {
  errorMessage.value = ''

  if (!username.value || !nickname.value || !password.value || !passwordConfirm.value) {
    errorMessage.value = '아이디, 닉네임, 비밀번호를 입력해주세요.'
    return
  }

  if (password.value !== passwordConfirm.value) {
    errorMessage.value = '비밀번호가 일치하지 않습니다.'
    return
  }

  try {
    isLoading.value = true

    const payload = new FormData()
    payload.append('username', username.value)
    payload.append('nickname', nickname.value)
    payload.append('email', email.value)
    payload.append('password', password.value)
    payload.append('password_confirm', passwordConfirm.value)

    if (profileImageFile.value) {
      payload.append('profile_image', profileImageFile.value)
    }

    await authStore.signup(payload)

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
        <label class="profile-image-picker">
          <span class="profile-avatar-preview">
            <img
              v-if="profileImagePreviewUrl"
              :src="profileImagePreviewUrl"
              alt="프로필 사진 미리보기"
            />
            <span v-else class="default-avatar" aria-hidden="true"></span>
          </span>
          <span>프로필 사진 선택</span>
          <input type="file" accept="image/*" @change="handleProfileImageChange" />
        </label>

        <input v-model="username" type="text" placeholder="아이디" />
        <input v-model="nickname" type="text" placeholder="닉네임" />
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

.profile-image-picker {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 14px;
  border: 1px dashed #d0d5dd;
  border-radius: 14px;
  color: #344054;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
}

.profile-image-picker input {
  width: 100%;
  padding: 0;
  border: 0;
  border-radius: 0;
  font-size: 13px;
}

.profile-avatar-preview {
  width: 96px;
  height: 96px;
  overflow: hidden;
  border-radius: 50%;
  background: #8fb8cc;
}

.profile-avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.default-avatar {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
}

.default-avatar::before,
.default-avatar::after {
  position: absolute;
  left: 50%;
  content: "";
  transform: translateX(-50%);
  background: #c8ddea;
}

.default-avatar::before {
  top: 20%;
  width: 34%;
  height: 34%;
  border-radius: 50%;
}

.default-avatar::after {
  bottom: -10%;
  width: 72%;
  height: 48%;
  border-radius: 50% 50% 0 0;
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
