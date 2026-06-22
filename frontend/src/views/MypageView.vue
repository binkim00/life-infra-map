<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { getMypage, updateNickname, updateProfileImage } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const data = ref(null)
const isLoading = ref(false)
const errorMessage = ref('')
const selectedSection = ref('profile')
const nicknameInput = ref('')
const nicknameMessage = ref('')
const isUpdatingNickname = ref(false)
const profileImageFile = ref(null)
const profileImagePreviewUrl = ref('')
const profileImageMessage = ref('')
const isUpdatingProfileImage = ref(false)

const sections = [
  { value: 'profile', label: '내 프로필' },
  { value: 'posts', label: '내가 쓴 글' },
  { value: 'comments', label: '내가 쓴 댓글' },
  { value: 'liked', label: '내가 좋아요한 글' },
  { value: 'inquiries', label: '내 문의내역' },
]

const fetchMypage = async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  try {
    isLoading.value = true
    const response = await getMypage()
    data.value = response.data
    nicknameInput.value = response.data.user.nickname || ''
    profileImagePreviewUrl.value = response.data.user.profile_image_url || ''
  } catch (error) {
    console.error(error)
    errorMessage.value = '마이페이지 정보를 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const handleProfileImageChange = (event) => {
  const file = event.target.files?.[0]

  profileImageFile.value = file || null
  profileImagePreviewUrl.value = file ? URL.createObjectURL(file) : data.value?.user?.profile_image_url || ''
}

const handleUpdateNickname = async () => {
  nicknameMessage.value = ''

  if (!nicknameInput.value.trim()) {
    nicknameMessage.value = '닉네임을 입력해주세요.'
    return
  }

  try {
    isUpdatingNickname.value = true
    const response = await updateNickname({
      nickname: nicknameInput.value,
    })

    data.value.user = response.data.user
    authStore.user = response.data.user
    localStorage.setItem('authUser', JSON.stringify(response.data.user))
    nicknameMessage.value = '닉네임이 수정되었습니다.'
  } catch (error) {
    console.error(error)
    nicknameMessage.value =
      error.response?.data?.nickname?.[0] || '닉네임 수정에 실패했습니다.'
  } finally {
    isUpdatingNickname.value = false
  }
}

const handleUpdateProfileImage = async () => {
  profileImageMessage.value = ''

  if (!profileImageFile.value) {
    profileImageMessage.value = '변경할 프로필 사진을 선택해주세요.'
    return
  }

  try {
    isUpdatingProfileImage.value = true

    const payload = new FormData()
    payload.append('profile_image', profileImageFile.value)

    const response = await updateProfileImage(payload)

    data.value.user = response.data.user
    authStore.user = response.data.user
    localStorage.setItem('authUser', JSON.stringify(response.data.user))
    profileImagePreviewUrl.value = response.data.user.profile_image_url || ''
    profileImageFile.value = null
    profileImageMessage.value = '프로필 사진이 수정되었습니다.'
  } catch (error) {
    console.error(error)
    profileImageMessage.value =
      error.response?.data?.profile_image?.[0] || '프로필 사진 수정에 실패했습니다.'
  } finally {
    isUpdatingProfileImage.value = false
  }
}

onMounted(fetchMypage)
</script>

<template>
  <main class="mypage">
    <section class="mypage-container">
      <header class="page-title">
        <p class="eyebrow">MY PAGE</p>
        <h1>마이페이지</h1>
      </header>

      <p v-if="isLoading" class="status-card">정보를 불러오는 중입니다.</p>
      <p v-else-if="errorMessage" class="status-card error">{{ errorMessage }}</p>

      <div v-else-if="data" class="mypage-layout">
        <section class="profile-card">
          <div class="profile-main">
            <span class="profile-avatar">
              <img
                v-if="data.user.profile_image_url"
                :src="data.user.profile_image_url"
                :alt="data.user.nickname"
              />
              <span v-else class="default-avatar" aria-hidden="true"></span>
            </span>
            <h2>{{ data.user.nickname }}</h2>
            <p class="profile-username">@{{ data.user.username }}</p>
            <p>{{ data.user.email || '이메일 없음' }}</p>
          </div>
        </section>

        <section class="section-control">
          <label for="mypage-section">메뉴 선택</label>
          <select id="mypage-section" v-model="selectedSection">
            <option v-for="section in sections" :key="section.value" :value="section.value">
              {{ section.label }}
            </option>
          </select>
        </section>

        <section v-if="selectedSection === 'profile'" class="panel profile-panel">
          <div class="profile-info-grid">
            <article>
              <span>닉네임</span>
              <strong>{{ data.user.nickname }}</strong>
            </article>
            <article>
              <span>아이디</span>
              <strong>{{ data.user.username }}</strong>
            </article>
            <article>
              <span>이메일</span>
              <strong>{{ data.user.email || '이메일 없음' }}</strong>
            </article>
            <article>
              <span>가입일</span>
              <strong>{{ new Date(data.user.date_joined).toLocaleDateString() }}</strong>
            </article>
            <article>
              <span>계정 유형</span>
              <strong>{{ data.user.is_staff ? '관리자 계정' : '일반 사용자' }}</strong>
            </article>
          </div>

          <form class="profile-image-form" @submit.prevent="handleUpdateProfileImage">
            <label for="profile-image">프로필 사진 수정</label>
            <div class="profile-image-editor">
              <span class="profile-avatar large">
                <img
                  v-if="profileImagePreviewUrl"
                  :src="profileImagePreviewUrl"
                  :alt="data.user.nickname"
                />
                <span v-else class="default-avatar" aria-hidden="true"></span>
              </span>

              <div class="profile-image-controls">
                <input
                  id="profile-image"
                  type="file"
                  accept="image/*"
                  @change="handleProfileImageChange"
                />
                <button type="submit" :disabled="isUpdatingProfileImage">
                  {{ isUpdatingProfileImage ? '저장 중' : '사진 저장' }}
                </button>
              </div>
            </div>
            <p v-if="profileImageMessage" class="profile-image-message">
              {{ profileImageMessage }}
            </p>
          </form>

          <form class="nickname-form" @submit.prevent="handleUpdateNickname">
            <label for="nickname">닉네임 수정</label>
            <div class="nickname-control">
              <input
                id="nickname"
                v-model="nicknameInput"
                type="text"
                maxlength="50"
                placeholder="새 닉네임"
              />
              <button type="submit" :disabled="isUpdatingNickname">
                {{ isUpdatingNickname ? '저장 중' : '저장' }}
              </button>
            </div>
            <p v-if="nicknameMessage" class="nickname-message">
              {{ nicknameMessage }}
            </p>
          </form>

          <div v-if="data.penalty.is_suspended" class="penalty-detail">
            <strong>{{ data.penalty.is_permanent_ban ? '영구밴 상태입니다.' : '활동정지 상태입니다.' }}</strong>
            <p v-if="data.penalty.reason">사유 {{ data.penalty.reason }}</p>
            <p v-if="data.penalty.suspended_until">해제일 {{ new Date(data.penalty.suspended_until).toLocaleString() }}</p>
          </div>

          <div class="summary-grid">
            <article class="summary-card">
              <strong>{{ data.posts.length }}</strong>
              <span>작성 글</span>
            </article>
            <article class="summary-card">
              <strong>{{ data.comments.length }}</strong>
              <span>작성 댓글</span>
            </article>
            <article class="summary-card">
              <strong>{{ data.liked_posts.length }}</strong>
              <span>좋아요한 글</span>
            </article>
            <article class="summary-card">
              <strong>{{ data.inquiries.length }}</strong>
              <span>문의</span>
            </article>
          </div>
        </section>

        <section v-else-if="selectedSection === 'posts'" class="panel">
          <h2>내가 쓴 글</h2>
          <RouterLink v-for="post in data.posts" :key="post.id" :to="`/boards/${post.board_type}/${post.id}`"
            class="activity-item link-item">
            <strong>{{ post.title }}</strong>
            <span>댓글 {{ post.comments_count }} · 좋아요 {{ post.likes_count }}</span>
          </RouterLink>
          <p v-if="data.posts.length === 0" class="empty">작성한 글이 없습니다.</p>
        </section>

        <section v-else-if="selectedSection === 'comments'" class="panel">
          <h2>내가 쓴 댓글</h2>
          <div v-for="comment in data.comments" :key="comment.id" class="activity-item">
            <strong>{{ comment.content }}</strong>
            <span>{{ new Date(comment.created_at).toLocaleDateString() }}</span>
          </div>
          <p v-if="data.comments.length === 0" class="empty">작성한 댓글이 없습니다.</p>
        </section>

        <section v-else-if="selectedSection === 'liked'" class="panel">
          <h2>내가 좋아요한 글</h2>
          <RouterLink v-for="post in data.liked_posts" :key="post.id" :to="`/boards/${post.board_type}/${post.id}`"
            class="activity-item link-item">
            <strong>{{ post.title }}</strong>
            <span>{{ post.author_nickname }} · 댓글 {{ post.comments_count }} · 좋아요 {{ post.likes_count }}</span>
          </RouterLink>
          <p v-if="data.liked_posts.length === 0" class="empty">좋아요한 글이 없습니다.</p>
        </section>

        <section v-else class="panel">
          <h2>내 문의내역</h2>
          <div v-for="inquiry in data.inquiries" :key="inquiry.id" class="activity-item">
            <strong>{{ inquiry.title }}</strong>
            <span>{{ inquiry.status === 'answered' ? '답변 완료' : '답변 대기' }}</span>
            <p v-if="inquiry.admin_reply">{{ inquiry.admin_reply }}</p>
          </div>
          <p v-if="data.inquiries.length === 0" class="empty">작성한 문의가 없습니다.</p>
        </section>
      </div>
    </section>
  </main>
</template>

<style scoped>
.mypage {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.mypage-container {
  max-width: 960px;
  margin: 0 auto;
}

.page-title {
  margin-bottom: 24px;
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

.mypage-layout {
  display: grid;
  gap: 14px;
}

.profile-card,
.section-control,
.summary-card,
.panel,
.status-card {
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.profile-card {
  padding: 24px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: start;
}

.profile-main h2 {
  margin-top: 10px;
  font-size: 30px;
}

.profile-main p {
  margin: 6px 0 0;
  color: #667085;
  font-weight: 700;
}

.profile-main .profile-username {
  color: #344054;
  font-size: 14px;
}

.profile-avatar {
  position: relative;
  display: inline-flex;
  width: 64px;
  height: 64px;
  overflow: hidden;
  border-radius: 50%;
  background: #8fb8cc;
  vertical-align: middle;
}

.profile-avatar.large {
  width: 96px;
  height: 96px;
  flex: 0 0 auto;
}

.profile-avatar img {
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

.section-control {
  padding: 18px;
  display: grid;
  gap: 8px;
}

.section-control label {
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

.section-control select {
  width: 100%;
  padding: 13px 14px;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  background: #ffffff;
  color: #111827;
  font-size: 15px;
  font-weight: 800;
  outline: none;
}

.panel {
  padding: 22px;
}

.profile-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.profile-info-grid article {
  padding: 14px;
  border-radius: 14px;
  background: #f9fafb;
}

.profile-info-grid span {
  display: block;
  margin-bottom: 5px;
  color: #667085;
  font-size: 12px;
  font-weight: 900;
}

.profile-info-grid strong {
  color: #111827;
}

.nickname-form {
  display: grid;
  gap: 8px;
  margin-top: 14px;
  padding: 14px;
  border-radius: 14px;
  background: #f9fafb;
}

.profile-image-form {
  display: grid;
  gap: 10px;
  margin-top: 14px;
  padding: 14px;
  border-radius: 14px;
  background: #f9fafb;
}

.profile-image-form label {
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

.profile-image-editor {
  display: flex;
  gap: 14px;
  align-items: center;
}

.profile-image-controls {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.profile-image-controls input {
  max-width: 100%;
  color: #344054;
  font-size: 13px;
}

.profile-image-controls button {
  justify-self: start;
  padding: 10px 14px;
  border: 0;
  border-radius: 12px;
  background: #2563eb;
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
}

.profile-image-controls button:disabled {
  background: #98a2b3;
  cursor: not-allowed;
}

.profile-image-message {
  margin: 0;
  color: #2563eb;
  font-size: 13px;
  font-weight: 800;
}

.nickname-form label {
  color: #344054;
  font-size: 13px;
  font-weight: 900;
}

.nickname-control {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.nickname-control input {
  width: 100%;
  padding: 12px 13px;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  background: #ffffff;
  color: #111827;
  font-size: 15px;
  outline: none;
}

.nickname-control input:focus {
  border-color: #2563eb;
}

.nickname-control button {
  padding: 0 16px;
  border: 0;
  border-radius: 12px;
  background: #2563eb;
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
}

.nickname-control button:disabled {
  background: #98a2b3;
  cursor: not-allowed;
}

.nickname-message {
  margin: 0;
  color: #2563eb;
  font-size: 13px;
  font-weight: 800;
}

.penalty-detail {
  margin-top: 14px;
  padding: 14px;
  border-radius: 14px;
  background: #fff7ed;
  color: #9a3412;
}

.penalty-detail p {
  margin: 6px 0 0;
}

.summary-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  padding: 18px;
  display: grid;
  gap: 4px;
}

.summary-card strong {
  color: #2563eb;
  font-size: 28px;
}

.summary-card span,
.activity-item span,
.empty {
  color: #667085;
  font-weight: 700;
}

.activity-item {
  display: grid;
  gap: 5px;
  margin-top: 10px;
  padding: 13px;
  border-radius: 12px;
  background: #f9fafb;
  color: #111827;
  text-decoration: none;
}

.activity-item p {
  margin: 0;
  color: #344054;
  line-height: 1.6;
  white-space: pre-wrap;
}

.link-item:hover {
  background: #eff6ff;
}

.status-card {
  padding: 32px;
  text-align: center;
}

.error {
  color: #ef4444;
}

@media (max-width: 820px) {
  .profile-card,
  .profile-info-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }
  .nickname-control {
    grid-template-columns: 1fr;
  }

  .nickname-control button {
    min-height: 42px;
  }

  .profile-image-editor {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
