<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  createUserPreference,
  deleteUserPreference,
  fetchPreferenceTags,
  fetchUserPreferences,
} from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const preferenceTags = ref([])
const directPreferences = ref([])
const automaticPreferences = ref([])
const isLoading = ref(false)
const isLoadingTags = ref(false)
const message = ref('')
const tagMessage = ref('')
const updatingTagId = ref(null)
const deletingPreferenceId = ref(null)
const automaticPage = ref(1)
const automaticMeta = ref({
  count: 0,
  page: 1,
  pageSize: 5,
  totalPages: 1,
})

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

const preferenceTypeLabels = {
  menu: '메뉴',
  place_type: '장소 유형',
  condition: '조건',
  category: '카테고리',
  scenario: '상황',
  tag: '태그',
  keyword: '키워드',
}

const getPreferenceTypeLabel = (type) => preferenceTypeLabels[type] || '선호'

const getPreferenceLabel = (preference) => {
  return normalizeLabelValue(preference?.label || preference?.key)
}

const formatPreferenceScore = (score) => {
  const numericScore = Number(score)

  if (!Number.isFinite(numericScore)) return '0.0'
  return numericScore.toFixed(1)
}

const getPreferenceMeta = (preference) => {
  const searchCount = Number(preference?.search_count || 0)

  return [
    `선호도 ${formatPreferenceScore(preference?.score)}`,
    searchCount > 0 ? `최근 검색 ${searchCount}회` : '',
  ].filter(Boolean).join(' · ')
}

const selectedTagPreferenceMap = computed(() => {
  const map = new Map()

  directPreferences.value.forEach((preference) => {
    const key = normalizeLabelValue(preference.key || preference.label).toLowerCase()
    if (key) map.set(key, preference)
  })

  return map
})

const getTagKey = (tag) => {
  return normalizeLabelValue(tag?.name || tag?.display_name).toLowerCase()
}

const getSelectedPreferenceForTag = (tag) => {
  return selectedTagPreferenceMap.value.get(getTagKey(tag))
}

const isTagSelected = (tag) => Boolean(getSelectedPreferenceForTag(tag))

const tagGroups = computed(() => {
  const groups = new Map()

  preferenceTags.value.forEach((tag) => {
    const groupName = normalizeLabelValue(tag.group) || '기타'

    if (!groups.has(groupName)) {
      groups.set(groupName, [])
    }

    groups.get(groupName).push(tag)
  })

  return [...groups.entries()].map(([name, tags]) => ({
    name,
    tags,
  }))
})

const fetchTags = async () => {
  try {
    isLoadingTags.value = true
    const response = await fetchPreferenceTags()
    preferenceTags.value = response.results || []
    tagMessage.value = preferenceTags.value.length ? '' : '선택할 수 있는 태그가 아직 없습니다.'
  } catch (error) {
    preferenceTags.value = []
    tagMessage.value = '선호 태그 목록을 불러오지 못했습니다.'
  } finally {
    isLoadingTags.value = false
  }
}

const fetchDirectPreferences = async () => {
  const response = await fetchUserPreferences({
    page: 1,
    pageSize: 50,
    source: 'user_selected',
    type: 'tag',
  })
  directPreferences.value = response.results || []
}

const fetchAutomaticPreferences = async () => {
  const response = await fetchUserPreferences({
    page: automaticPage.value,
    pageSize: 5,
    source: 'search_log',
  })

  automaticPreferences.value = response.results || []
  automaticMeta.value = {
    count: response.count || 0,
    page: response.page || automaticPage.value,
    pageSize: response.page_size || 5,
    totalPages: response.total_pages || 1,
  }
}

const fetchPreferences = async () => {
  try {
    isLoading.value = true
    message.value = ''
    await Promise.all([
      fetchDirectPreferences(),
      fetchAutomaticPreferences(),
    ])
  } catch (error) {
    message.value = '선호 정보를 불러오지 못했습니다.'
  } finally {
    isLoading.value = false
  }
}

const handleToggleTag = async (tag) => {
  const selectedPreference = getSelectedPreferenceForTag(tag)

  try {
    updatingTagId.value = tag.id
    tagMessage.value = ''

    if (selectedPreference) {
      await deleteUserPreference(selectedPreference.id)
      tagMessage.value = '선호 태그 선택을 해제했습니다.'
    } else {
      await createUserPreference({
        preference_type: 'tag',
        tag_id: tag.id,
      })
      tagMessage.value = '선호 태그를 선택했습니다.'
    }

    await fetchDirectPreferences()
  } catch (error) {
    tagMessage.value = error.response?.data?.detail || '선호 태그를 저장하지 못했습니다.'
  } finally {
    updatingTagId.value = null
  }
}

const handleDeleteDirectPreference = async (preference) => {
  try {
    deletingPreferenceId.value = preference.id
    await deleteUserPreference(preference.id)
    tagMessage.value = '직접 선택한 선호 태그를 삭제했습니다.'
    await fetchDirectPreferences()
  } catch (error) {
    tagMessage.value = error.response?.data?.detail || '선호 태그를 삭제하지 못했습니다.'
  } finally {
    deletingPreferenceId.value = null
  }
}

const moveAutomaticPage = async (direction) => {
  const nextPage = automaticPage.value + direction
  if (nextPage < 1 || nextPage > automaticMeta.value.totalPages) return

  automaticPage.value = nextPage
  await fetchAutomaticPreferences()
}

onMounted(async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }

  await Promise.all([
    fetchTags(),
    fetchPreferences(),
  ])
})
</script>

<template>
  <main class="settings-page">
    <section class="settings-container">
      <header class="page-title">
        <RouterLink to="/mypage" class="back-link">마이페이지로 돌아가기</RouterLink>
        <p class="eyebrow">PREFERENCES</p>
        <h1>선호 태그 설정</h1>
        <p>추천에 더 반영하고 싶은 태그를 선택하고, 최근 검색 기반 자동 선호를 확인할 수 있습니다.</p>
      </header>

      <section class="panel">
        <div class="section-heading-row">
          <div>
            <h2>선호 태그 설정</h2>
            <p>체크한 태그는 추천 결과에 조금 더 강하게 반영됩니다.</p>
          </div>
        </div>

        <p v-if="isLoadingTags" class="empty">선호 태그 목록을 불러오는 중입니다.</p>
        <div v-else-if="tagGroups.length" class="tag-group-list">
          <div v-for="group in tagGroups" :key="group.name" class="tag-group">
            <h3>{{ group.name }}</h3>
            <div class="tag-options">
              <label
                v-for="tag in group.tags"
                :key="tag.id"
                class="tag-option"
                :class="{ 'is-selected': isTagSelected(tag) }"
              >
                <input
                  type="checkbox"
                  :checked="isTagSelected(tag)"
                  :disabled="updatingTagId === tag.id"
                  @change="handleToggleTag(tag)"
                />
                <span>{{ tag.display_name || tag.name }}</span>
              </label>
            </div>
          </div>
        </div>
        <p v-else class="empty">{{ tagMessage || '선택할 수 있는 태그가 아직 없습니다.' }}</p>
        <p v-if="tagMessage" class="status-message">{{ tagMessage }}</p>
      </section>

      <section class="panel">
        <div class="section-heading-row">
          <div>
            <h2>직접 선택한 선호 태그</h2>
            <p>사용자가 직접 체크한 태그입니다.</p>
          </div>
        </div>

        <p v-if="isLoading" class="empty">선호 정보를 불러오는 중입니다.</p>
        <div v-else-if="directPreferences.length" class="preference-chip-list">
          <span
            v-for="preference in directPreferences"
            :key="preference.id"
            class="preference-chip"
          >
            <strong>{{ getPreferenceLabel(preference) }}</strong>
            <button
              type="button"
              :disabled="deletingPreferenceId === preference.id"
              @click="handleDeleteDirectPreference(preference)"
            >
              삭제
            </button>
          </span>
        </div>
        <p v-else class="empty">직접 선택한 선호 태그가 아직 없습니다.</p>
      </section>

      <section class="panel">
        <div class="section-heading-row">
          <div>
            <h2>최근 검색 기반 자동 선호</h2>
            <p>검색 기록에서 추정된 선호입니다. 검색 기록 삭제 시 다시 계산됩니다.</p>
          </div>
        </div>

        <p v-if="isLoading" class="empty">자동 선호를 불러오는 중입니다.</p>
        <div v-else-if="automaticPreferences.length" class="preference-list">
          <article
            v-for="preference in automaticPreferences"
            :key="preference.id"
            class="preference-item"
          >
            <span class="preference-type-badge">{{ getPreferenceTypeLabel(preference.preference_type) }}</span>
            <strong>{{ getPreferenceLabel(preference) }}</strong>
            <span>{{ getPreferenceMeta(preference) }}</span>
          </article>
        </div>
        <p v-else class="empty">{{ message || '최근 검색 기반 자동 선호가 아직 없습니다.' }}</p>

        <div class="pager">
          <button
            type="button"
            :disabled="automaticPage <= 1"
            @click="moveAutomaticPage(-1)"
          >
            이전
          </button>
          <span>{{ automaticMeta.page }} / {{ automaticMeta.totalPages }}</span>
          <button
            type="button"
            :disabled="automaticPage >= automaticMeta.totalPages"
            @click="moveAutomaticPage(1)"
          >
            다음
          </button>
        </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
.settings-page {
  min-height: 100vh;
  padding: 40px 24px;
  background: #f6f7fb;
}

.settings-container {
  max-width: 960px;
  margin: 0 auto;
  display: grid;
  gap: 14px;
}

.page-title {
  display: grid;
  gap: 6px;
}

.back-link {
  width: fit-content;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  text-decoration: none;
}

.eyebrow {
  margin: 0;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
}

h1,
h2,
h3 {
  margin: 0;
  color: #111827;
}

.page-title p,
.section-heading-row p {
  margin: 0;
  color: #667085;
  font-weight: 700;
}

.panel {
  padding: 20px;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
}

.section-heading-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.tag-group-list {
  margin-top: 14px;
  display: grid;
  gap: 14px;
}

.tag-group {
  display: grid;
  gap: 8px;
}

.tag-group h3 {
  font-size: 14px;
}

.tag-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-option {
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
}

.tag-option.is-selected {
  border-color: #86efac;
  background: #dcfce7;
  color: #166534;
}

.tag-option input {
  width: 14px;
  height: 14px;
  accent-color: #16a34a;
}

.status-message,
.empty {
  margin: 12px 0 0;
  padding: 12px;
  border-radius: 12px;
  background: #f9fafb;
  color: #667085;
  font-weight: 800;
}

.status-message {
  color: #2563eb;
}

.preference-chip-list,
.preference-list {
  margin-top: 12px;
  display: grid;
  gap: 10px;
}

.preference-chip-list {
  display: flex;
  flex-wrap: wrap;
}

.preference-chip {
  padding: 8px 9px;
  display: inline-flex;
  gap: 8px;
  align-items: center;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 13px;
  font-weight: 900;
}

.preference-chip button,
.pager button {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  background: #ffffff;
  color: #344054;
  font-weight: 900;
  cursor: pointer;
}

.preference-chip button {
  border-color: #fecaca;
  color: #b91c1c;
}

.preference-chip button:disabled,
.pager button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.preference-item {
  min-width: 0;
  padding: 12px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  border-radius: 12px;
  background: #f9fafb;
}

.preference-item strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preference-item span:last-child {
  color: #667085;
  font-size: 12px;
  font-weight: 900;
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

.pager {
  margin-top: 14px;
  display: flex;
  justify-content: center;
  gap: 10px;
  align-items: center;
  color: #344054;
  font-weight: 900;
}

@media (max-width: 720px) {
  .section-heading-row {
    flex-direction: column;
  }

  .preference-item {
    grid-template-columns: 1fr;
  }
}
</style>
