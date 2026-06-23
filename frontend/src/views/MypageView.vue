<script setup>
import { onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { getMypage, updateNickname, updateProfileImage } from '@/api/boards'
import {
  deleteSearchLog,
  fetchSearchLogs,
  fetchUserPreferences,
} from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const data = ref(null)
const isLoading = ref(false)
const errorMessage = ref('')
const selectedSection = ref('profile')
const nicknameInput = ref('')
const nicknameMessage = ref('')
const isEditingNickname = ref(false)
const isUpdatingNickname = ref(false)
const profileImageFile = ref(null)
const profileImageInput = ref(null)
const profileImagePreviewUrl = ref('')
const profileImageMessage = ref('')
const isUpdatingProfileImage = ref(false)
const searchLogs = ref([])
const isLoadingSearchLogs = ref(false)
const searchLogMessage = ref('')
const userPreferences = ref([])
const isLoadingPreferences = ref(false)
const preferenceMessage = ref('')

const sectionValues = ['profile', 'posts', 'comments', 'liked']

const normalizeLabelValue = (item) => {
  if (typeof item === 'string') return item.trim()
  if (typeof item === 'number' && Number.isFinite(item)) return String(item)
  if (!item || typeof item !== 'object') return ''

  const labelKeys = ['label', 'name', 'display_name', 'displayName', 'value', 'text']
  for (const key of labelKeys) {
    const label = normalizeLabelValue(item[key])
    if (label) return label
  }

  return ''
}

const normalizeLabelList = (items) => {
  if (!Array.isArray(items)) return []

  return [...new Set(
    items
      .map(normalizeLabelValue)
      .filter((item) => item && item !== '[object Object]'),
  )]
}

const scenarioLabels = {
  work_cafe: '조용히 작업할 곳',
  waiting_place: '잠깐 쉴 곳',
  walk_healing: '산책/힐링',
  smoking_area: '흡연 가능한 곳',
  restaurant: '식당/맛집',
  blocked: '검색 불가',
}

const categoryLabels = {
  cafe: '카페',
  restaurant: '식당',
  food: '음식',
  toilet: '공중화장실',
  freewifi: '무료 와이파이',
  smoking_area: '흡연구역',
  beach: '해수욕장',
  parking: '주차장',
  city_park: '공원',
  tourism: '관광지',
}

const searchModeLabels = {
  recommendation_query: '추천 검색',
  region_search: '지역 검색',
  keyword_search: '키워드 검색',
  map_bounds_search: '지도 검색',
  current_context: '현재 위치 검색',
}

const getMappedLabel = (value, labelMap = {}) => {
  const label = normalizeLabelValue(value)
  const key = label.toLowerCase()

  return labelMap[key] || labelMap[label] || label
}

const syncSelectedSection = () => {
  const section = route.query.section
  selectedSection.value = sectionValues.includes(section) ? section : 'profile'
}

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
    fetchRecentSearchLogs()
    fetchPreferences()
  } catch (error) {
    console.error(error)
    errorMessage.value = '마이페이지 정보를 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const fetchPreferences = async () => {
  if (!authStore.isLoggedIn) {
    userPreferences.value = []
    preferenceMessage.value = '로그인 후 선호 키워드를 확인할 수 있습니다.'
    return
  }

  try {
    isLoadingPreferences.value = true
    preferenceMessage.value = ''
    const response = await fetchUserPreferences({ page: 1, pageSize: 5 })
    userPreferences.value = (response.results || []).filter((preference) => {
      return normalizeLabelValue(preference.label)
    })

    if (!userPreferences.value.length) {
      preferenceMessage.value = '검색하거나 직접 선호를 추가하면 이곳에 표시됩니다.'
    }
  } catch (error) {
    userPreferences.value = []

    if ([401, 403].includes(error.response?.status)) {
      preferenceMessage.value = '로그인 후 선호 키워드를 확인할 수 있습니다.'
    } else {
      preferenceMessage.value = '선호 키워드를 불러오지 못했습니다.'
    }

    if (import.meta.env.DEV) {
      console.debug('[UserPreferences] fetch failed', {
        status: error.response?.status || 'request_failed',
      })
    }
  } finally {
    isLoadingPreferences.value = false
  }
}

const fetchRecentSearchLogs = async () => {
  if (!authStore.isLoggedIn) {
    searchLogs.value = []
    searchLogMessage.value = '로그인 후 검색 기록을 확인할 수 있습니다.'
    return
  }

  try {
    isLoadingSearchLogs.value = true
    searchLogMessage.value = ''
    const response = await fetchSearchLogs({ page: 1, pageSize: 5 })
    searchLogs.value = response.results || []

    if (!searchLogs.value.length) {
      searchLogMessage.value = '아직 저장된 검색 기록이 없습니다.'
    }
  } catch (error) {
    searchLogs.value = []

    if ([401, 403].includes(error.response?.status)) {
      searchLogMessage.value = '로그인 후 검색 기록을 확인할 수 있습니다.'
    } else {
      searchLogMessage.value = '검색 기록을 불러오지 못했습니다.'
    }

    if (import.meta.env.DEV) {
      console.debug('[SearchLogs] fetch failed', {
        status: error.response?.status || 'request_failed',
      })
    }
  } finally {
    isLoadingSearchLogs.value = false
  }
}

const handleDeleteSearchLog = async (log) => {
  if (!log?.id) return

  try {
    await deleteSearchLog(log.id)
    searchLogMessage.value = '검색 기록을 삭제했습니다.'
    await fetchRecentSearchLogs()
    await fetchPreferences()
  } catch (error) {
    searchLogMessage.value =
      error.response?.data?.detail || '검색 기록을 삭제하지 못했습니다.'
  }
}

const formatSearchLogDate = (value) => {
  if (!value) return ''

  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const getSearchLogCategoryLabel = (log) => {
  return (
    getMappedLabel(log.category_hint, categoryLabels) ||
    getMappedLabel(log.scenario, scenarioLabels) ||
    getMappedLabel(log.search_mode, searchModeLabels)
  )
}

const getSearchLogMeta = (log) => {
  return [
    normalizeLabelValue(log.location_hint),
    getSearchLogCategoryLabel(log),
    `결과 ${log.result_count || 0}개`,
  ].filter(Boolean).join(' · ')
}

const getSearchLogChips = (log) => {
  return normalizeLabelList([
    ...normalizeLabelList(log.menu_keywords),
    ...normalizeLabelList(log.place_type_keywords),
    ...normalizeLabelList(log.requested_conditions),
    ...normalizeLabelList(log.preferred_tags),
  ]).slice(0, 5)
}

const rerunSearchLog = (log) => {
  if (!log?.query) return

  router.push({
    name: 'home',
    query: {
      q: log.query,
    },
  })
}

const preferenceTypeLabels = {
  menu: '메뉴',
  place_type: '장소 유형',
  condition: '조건',
  category: '카테고리',
  scenario: '상황',
  tag: '태그',
  keyword: '키워드',
}

const getPreferenceTypeLabel = (type) => {
  return preferenceTypeLabels[type] || '선호'
}

const isUserSelectedPreference = (preference) => {
  return preference?.source === 'user_selected'
}

const getPreferenceSourceLabel = (preference) => {
  return isUserSelectedPreference(preference) ? '직접 선택' : '자동'
}

const getPreferenceSourceClass = (preference) => {
  return isUserSelectedPreference(preference) ? 'is-user-selected' : 'is-search-log'
}

const getPreferenceLabel = (preference) => {
  const rawLabel = preference?.label || preference?.key

  if (preference?.preference_type === 'scenario') {
    return getMappedLabel(rawLabel, scenarioLabels)
  }

  if (preference?.preference_type === 'category') {
    return getMappedLabel(rawLabel, categoryLabels)
  }

  return normalizeLabelValue(rawLabel)
}

const formatPreferenceScore = (score) => {
  const numericScore = Number(score)

  if (!Number.isFinite(numericScore)) return '0.0'
  return numericScore.toFixed(1)
}

const getPreferenceMeta = (preference) => {
  const searchCount = Number(preference?.search_count || 0)
  const countText = searchCount > 0 ? `최근 검색 ${searchCount}회` : ''

  return [
    `선호도 ${formatPreferenceScore(preference?.score)}`,
    countText,
  ].filter(Boolean).join(' · ')
}

const handleProfileImageChange = (event) => {
  const file = event.target.files?.[0]

  profileImageMessage.value = ''
  profileImageFile.value = file || null
  profileImagePreviewUrl.value = file ? URL.createObjectURL(file) : data.value?.user?.profile_image_url || ''

  event.target.value = ''
}

const triggerProfileImagePicker = () => {
  profileImageInput.value?.click()
}

const startNicknameEdit = () => {
  nicknameInput.value = data.value?.user?.nickname || ''
  nicknameMessage.value = ''
  isEditingNickname.value = true
}

const cancelNicknameEdit = () => {
  nicknameInput.value = data.value?.user?.nickname || ''
  nicknameMessage.value = ''
  isEditingNickname.value = false
}

const cancelProfileImageEdit = () => {
  profileImageFile.value = null
  profileImagePreviewUrl.value = data.value?.user?.profile_image_url || ''
  profileImageMessage.value = ''
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
    isEditingNickname.value = false
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

watch(() => route.query.section, syncSelectedSection)

onMounted(() => {
  syncSelectedSection()
  fetchMypage()
})
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
            <div class="avatar-edit-row">
              <div class="avatar-editor">
                <span class="profile-avatar">
                  <img
                    v-if="profileImagePreviewUrl"
                    :src="profileImagePreviewUrl"
                    :alt="data.user.nickname"
                  />
                  <span v-else class="default-avatar" aria-hidden="true"></span>
                </span>
                <button
                  type="button"
                  class="icon-edit-button camera-button"
                  aria-label="프로필 사진 수정"
                  :disabled="isUpdatingProfileImage"
                  @click="triggerProfileImagePicker"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M14.5 4.5 16 7h3a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h3l1.5-2.5h5Z" />
                    <circle cx="12" cy="13" r="3.5" />
                  </svg>
                </button>
                <input
                  ref="profileImageInput"
                  class="hidden-file-input"
                  type="file"
                  accept="image/*"
                  @change="handleProfileImageChange"
                />
              </div>

              <div class="profile-image-side">
                <div v-if="profileImageFile" class="image-action-buttons">
                  <button type="button" :disabled="isUpdatingProfileImage" @click="handleUpdateProfileImage">
                    {{ isUpdatingProfileImage ? '저장 중' : '저장' }}
                  </button>
                  <button type="button" class="ghost-button" :disabled="isUpdatingProfileImage" @click="cancelProfileImageEdit">
                    취소
                  </button>
                </div>
                <p v-if="profileImageMessage" class="profile-image-message">{{ profileImageMessage }}</p>
              </div>
            </div>

            <div class="nickname-editor">
              <form v-if="isEditingNickname" class="inline-nickname-form" @submit.prevent="handleUpdateNickname">
                <input
                  v-model="nicknameInput"
                  type="text"
                  maxlength="50"
                  aria-label="닉네임"
                  autofocus
                />
                <button type="submit" :disabled="isUpdatingNickname">저장</button>
                <button type="button" class="ghost-button" @click="cancelNicknameEdit">취소</button>
                <p v-if="nicknameMessage" class="nickname-message">{{ nicknameMessage }}</p>
              </form>

              <div v-else class="nickname-display-row">
                <h2>
                  {{ data.user.nickname }}
                  <button
                    type="button"
                    class="icon-edit-button pencil-button"
                    aria-label="닉네임 수정"
                    @click="startNicknameEdit"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0 0-3l-.5-.5a2.1 2.1 0 0 0-3 0l-10 10L4 20Z" />
                      <path d="m13.5 6.5 4 4" />
                    </svg>
                  </button>
                </h2>
                <p v-if="nicknameMessage" class="nickname-message">{{ nicknameMessage }}</p>
              </div>
            </div>
            <p class="profile-username">@{{ data.user.username }}</p>
            <p>{{ data.user.email || '이메일 없음' }}</p>
          </div>
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

          <div v-if="data.penalty.is_suspended" class="penalty-detail">
            <strong>{{ data.penalty.is_permanent_ban ? '영구밴 상태입니다.' : '활동정지 상태입니다.' }}</strong>
            <p v-if="data.penalty.reason">사유 {{ data.penalty.reason }}</p>
            <p v-if="data.penalty.suspended_until">해제일 {{ new Date(data.penalty.suspended_until).toLocaleString() }}</p>
          </div>

          <div class="summary-grid">
            <RouterLink :to="{ path: '/mypage', query: { section: 'posts' } }" class="summary-card">
              <strong>{{ data.posts.length }}</strong>
              <span>작성글</span>
            </RouterLink>
            <RouterLink :to="{ path: '/mypage', query: { section: 'comments' } }" class="summary-card">
              <strong>{{ data.comments.length }}</strong>
              <span>작성댓글</span>
            </RouterLink>
            <RouterLink :to="{ path: '/mypage', query: { section: 'liked' } }" class="summary-card">
              <strong>{{ data.liked_posts.length }}</strong>
              <span>좋아요한글</span>
            </RouterLink>
          </div>

          <section class="search-history-section">
            <div class="section-heading-row">
              <div>
                <h2>최근 검색 기록</h2>
                <p>이전에 찾았던 장소 조건을 다시 검색할 수 있습니다.</p>
              </div>
              <div class="section-action-row">
                <RouterLink to="/mypage/search-history" class="refresh-history-button">
                  검색 기록 관리
                </RouterLink>
                <button type="button" class="refresh-history-button" @click="fetchRecentSearchLogs">
                  새로고침
                </button>
              </div>
            </div>

            <p v-if="isLoadingSearchLogs" class="empty search-history-status">검색 기록을 불러오는 중입니다.</p>
            <div v-else-if="searchLogs.length" class="search-history-list">
              <article
                v-for="log in searchLogs"
                :key="log.id"
                class="search-history-item"
              >
                <strong>{{ log.query }}</strong>
                <span>{{ getSearchLogMeta(log) }}</span>
                <time>{{ formatSearchLogDate(log.created_at) }}</time>
                <span v-if="getSearchLogChips(log).length" class="search-log-chip-row">
                  <span v-for="chip in getSearchLogChips(log)" :key="chip" class="search-log-chip">
                    {{ chip }}
                  </span>
                </span>
                <span class="search-history-actions">
                  <button type="button" @click="rerunSearchLog(log)">
                    다시 검색
                  </button>
                  <button type="button" class="danger" @click="handleDeleteSearchLog(log)">
                    삭제
                  </button>
                </span>
              </article>
            </div>
            <div v-else class="empty search-history-status">
              <p>{{ searchLogMessage }}</p>
              <p v-if="searchLogMessage === '아직 저장된 검색 기록이 없습니다.'">
                장소를 검색하면 최근 검색 기록이 이곳에 표시됩니다.
              </p>
            </div>
          </section>

          <section class="preference-section">
            <div class="section-heading-row">
              <div>
                <h2>내 선호 요약</h2>
                <p>추천에 반영되는 선호를 간단히 확인할 수 있습니다.</p>
              </div>
              <RouterLink to="/mypage/preferences" class="refresh-history-button">
                선호 태그 설정하기
              </RouterLink>
            </div>

            <p v-if="isLoadingPreferences" class="empty preference-status">선호 키워드를 불러오는 중입니다.</p>
            <div v-else-if="userPreferences.length" class="preference-list">
              <article
                v-for="preference in userPreferences"
                :key="preference.id"
                class="preference-item"
              >
                <span class="preference-badge-row">
                  <span
                    class="preference-source-badge"
                    :class="getPreferenceSourceClass(preference)"
                  >
                    {{ getPreferenceSourceLabel(preference) }}
                  </span>
                  <span class="preference-type-badge">
                    {{ getPreferenceTypeLabel(preference.preference_type) }}
                  </span>
                </span>
                <strong>{{ getPreferenceLabel(preference) }}</strong>
                <span class="preference-meta">{{ getPreferenceMeta(preference) }}</span>
              </article>
            </div>
            <p v-else class="empty preference-status">
              {{ preferenceMessage || '검색하거나 선호 태그를 선택하면 이곳에 표시됩니다.' }}
            </p>
          </section>

          <section class="preference-section">
            <div class="section-heading-row">
              <div>
                <h2>장소 정보 제보</h2>
                <p>장소 정보나 태그 오류를 제보하고 검토 상태를 확인할 수 있습니다.</p>
              </div>
              <div class="section-action-row">
                <RouterLink to="/place-report" class="refresh-history-button">
                  제보 작성
                </RouterLink>
                <RouterLink to="/mypage/reports" class="refresh-history-button">
                  내 제보 현황
                </RouterLink>
              </div>
            </div>
          </section>
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
          <RouterLink
            v-for="comment in data.comments"
            :key="comment.id"
            :to="`/boards/${comment.post_board_type}/${comment.post}#comment-${comment.id}`"
            class="activity-item link-item"
          >
            <strong>{{ comment.content }}</strong>
            <span>{{ comment.post_title }} · {{ new Date(comment.created_at).toLocaleDateString() }}</span>
          </RouterLink>
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
  position: relative;
  width: fit-content;
  margin-top: 10px;
  padding-right: 28px;
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

.avatar-edit-row {
  display: flex;
  gap: 18px;
  align-items: center;
}

.avatar-editor {
  position: relative;
  width: 64px;
  height: 64px;
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

.profile-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hidden-file-input {
  display: none;
}

.icon-edit-button {
  width: 30px;
  height: 30px;
  padding: 0;
  display: inline-grid;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  background: rgba(33, 37, 41, 0.9);
  color: #ffffff;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(17, 24, 39, 0.18);
}

.icon-edit-button:hover {
  background: #111827;
}

.icon-edit-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.icon-edit-button svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2.2;
}

.camera-button {
  position: absolute;
  right: -8px;
  bottom: -8px;
}

.profile-image-side {
  min-height: 36px;
  display: flex;
  gap: 12px;
  align-items: center;
}

.image-action-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
}

.image-action-buttons button {
  min-height: 34px;
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  background: #2563eb;
  color: #ffffff;
  font-weight: 900;
  cursor: pointer;
}

.image-action-buttons .ghost-button {
  border: 1px solid #d0d5dd;
  background: #ffffff;
  color: #344054;
}

.image-action-buttons button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.nickname-editor {
  min-width: 0;
}

.nickname-display-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.pencil-button {
  position: absolute;
  right: -10px;
  bottom: 0;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  color: #ffffff;
}

.pencil-button svg {
  width: 18px;
  height: 18px;
}

.inline-nickname-form {
  max-width: 420px;
  margin-top: 10px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: 8px;
  align-items: center;
}

.inline-nickname-form input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  color: #111827;
  font-size: 18px;
  font-weight: 800;
  outline: none;
}

.inline-nickname-form input:focus {
  border-color: #2563eb;
}

.inline-nickname-form button {
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  background: #2563eb;
  color: #ffffff;
  font-weight: 900;
  cursor: pointer;
}

.inline-nickname-form .ghost-button {
  border: 1px solid #d0d5dd;
  background: #ffffff;
  color: #344054;
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

.profile-image-message {
  margin: 0;
  color: #2563eb;
  font-size: 13px;
  font-weight: 800;
  white-space: nowrap;
}

.nickname-message {
  margin: 0;
  color: #2563eb;
  font-size: 13px;
  font-weight: 800;
  white-space: nowrap;
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  padding: 18px;
  display: grid;
  gap: 4px;
  color: inherit;
  text-decoration: none;
  transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
}

.summary-card:hover {
  border-color: #bfdbfe;
  box-shadow: 0 14px 32px rgba(20, 35, 70, 0.12);
  transform: translateY(-1px);
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

.search-history-section {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid #e5e8f0;
}

.section-heading-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
}

.section-heading-row p {
  margin: 6px 0 0;
  color: #667085;
  font-weight: 700;
}

.section-action-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.refresh-history-button {
  min-height: 34px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  background: #ffffff;
  color: #344054;
  font-weight: 900;
  text-decoration: none;
  cursor: pointer;
}

.refresh-history-button:hover {
  border-color: #bfdbfe;
  color: #2563eb;
}

.search-history-list {
  margin-top: 12px;
  display: grid;
  gap: 10px;
}

.search-history-item {
  width: 100%;
  padding: 14px;
  display: grid;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: #f9fafb;
  color: #111827;
  text-align: left;
  transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease;
}

.search-history-item:hover {
  border-color: #bfdbfe;
  background: #eff6ff;
  transform: translateY(-1px);
}

.search-history-item strong {
  font-size: 15px;
}

.search-history-item span,
.search-history-item time {
  color: #667085;
  font-size: 13px;
  font-weight: 800;
}

.search-log-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.search-log-chip {
  max-width: 100%;
  padding: 4px 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #e0f2fe;
  color: #075985;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-history-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.search-history-actions button {
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  background: #ffffff;
  color: #344054;
  font-size: 12px;
  font-weight: 900;
  cursor: pointer;
}

.search-history-actions button:hover {
  border-color: #bfdbfe;
  color: #2563eb;
}

.search-history-actions .danger {
  border-color: #fecaca;
  color: #b91c1c;
}

.search-history-actions .danger:hover {
  background: #fef2f2;
  color: #991b1b;
}

.search-history-status {
  margin: 12px 0 0;
  padding: 14px;
  border-radius: 12px;
  background: #f9fafb;
}

.search-history-status p {
  margin: 0;
}

.search-history-status p + p {
  margin-top: 4px;
}

.preference-section {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid #e5e8f0;
}

.preference-form-message {
  margin: 8px 0 0;
  color: #2563eb;
  font-size: 13px;
  font-weight: 800;
}

.preference-tag-picker,
.preference-subsection {
  margin-top: 16px;
  padding: 14px;
  border: 1px solid #e5e8f0;
  border-radius: 14px;
  background: #ffffff;
}

.preference-subheading h3,
.preference-tag-group h4 {
  margin: 0;
  color: #111827;
}

.preference-subheading p {
  margin: 5px 0 0;
  color: #667085;
  font-size: 13px;
  font-weight: 700;
}

.preference-tag-group-list {
  margin-top: 12px;
  display: grid;
  gap: 12px;
}

.preference-tag-group {
  display: grid;
  gap: 8px;
}

.preference-tag-group h4 {
  font-size: 13px;
}

.preference-tag-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preference-tag-option {
  min-height: 36px;
  padding: 0 11px;
  display: inline-flex;
  gap: 7px;
  align-items: center;
  border: 1px solid #d0d5dd;
  border-radius: 999px;
  background: #ffffff;
  color: #344054;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.preference-tag-option:hover {
  border-color: #bfdbfe;
  color: #2563eb;
}

.preference-tag-option.is-selected {
  border-color: #86efac;
  background: #dcfce7;
  color: #166534;
}

.preference-tag-option input {
  width: 14px;
  height: 14px;
  accent-color: #16a34a;
}

.preference-list {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.preference-item {
  min-width: 0;
  padding: 12px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  border-radius: 12px;
  background: #f9fafb;
}

.preference-badge-row {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.preference-item strong {
  overflow: hidden;
  color: #111827;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preference-meta {
  color: #667085;
  font-size: 12px;
  font-weight: 900;
}

.preference-delete-button {
  grid-column: 2;
  grid-row: 2 / span 2;
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #ffffff;
  color: #b91c1c;
  font-weight: 900;
  cursor: pointer;
}

.preference-delete-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.preference-delete-button:hover {
  background: #fef2f2;
}

.preference-type-badge {
  padding: 4px 7px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 11px;
  font-weight: 900;
  white-space: nowrap;
}

.preference-source-badge {
  padding: 4px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 900;
  white-space: nowrap;
}

.preference-source-badge.is-search-log {
  background: #f1f5f9;
  color: #475569;
}

.preference-source-badge.is-user-selected {
  background: #dcfce7;
  color: #166534;
}

.preference-status {
  margin: 12px 0 0;
  padding: 14px;
  border-radius: 12px;
  background: #f9fafb;
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
  .summary-grid,
  .preference-list {
    grid-template-columns: 1fr;
  }

  .avatar-edit-row,
  .nickname-display-row,
  .profile-image-side,
  .section-heading-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .inline-nickname-form {
    grid-template-columns: 1fr;
  }

  .profile-image-message,
  .nickname-message {
    white-space: normal;
  }

  .preference-item {
    grid-template-columns: minmax(0, 1fr);
  }

  .preference-delete-button {
    grid-column: 1 / -1;
    grid-row: auto;
  }
}
</style>
