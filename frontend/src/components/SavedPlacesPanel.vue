<script setup>
const props = defineProps({
  places: {
    type: Array,
    default: () => [],
  },
  isLoading: {
    type: Boolean,
    default: false,
  },
  message: {
    type: String,
    default: '',
  },
  editingPlaceId: {
    type: [Number, String],
    default: null,
  },
  memoInput: {
    type: String,
    default: '',
  },
  updatingPlaceId: {
    type: [Number, String],
    default: null,
  },
})

const emit = defineEmits([
  'refresh',
  'start-memo-edit',
  'cancel-memo-edit',
  'save-memo',
  'delete-place',
  'update:memoInput',
])

const getSavedPlaceDetailUrl = (place = {}) => {
  return place.detail_url || place.kakao_place_url || ''
}

const getSavedPlaceNavigationUrl = (place = {}) => {
  const lat = Number(place.lat)
  const lng = Number(place.lng)
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return ''

  return `https://map.kakao.com/link/to/${encodeURIComponent(place.name || '장소')},${lat},${lng}`
}

const formatSavedPlaceMeta = (place = {}) => {
  return [
    place.source_label || '',
    place.category || '',
    place.address || '',
  ].filter(Boolean).join(' · ')
}
</script>

<template>
  <section class="panel">
    <div class="section-heading-row">
      <div>
        <h2>저장한 장소</h2>
        <p>다시 확인하고 싶은 장소와 개인 메모를 관리합니다.</p>
      </div>
      <button type="button" class="refresh-history-button" @click="emit('refresh')">
        새로고침
      </button>
    </div>

    <p v-if="props.isLoading" class="empty">저장한 장소를 불러오는 중입니다.</p>
    <div v-else-if="props.places.length" class="saved-place-list">
      <article
        v-for="place in props.places"
        :key="place.id"
        class="saved-place-item"
      >
        <div class="saved-place-main">
          <span class="preference-source-badge">{{ place.source_label || '저장 장소' }}</span>
          <strong>{{ place.name }}</strong>
          <span v-if="formatSavedPlaceMeta(place)" class="saved-place-meta">
            {{ formatSavedPlaceMeta(place) }}
          </span>
          <p v-if="place.memo && props.editingPlaceId !== place.id" class="saved-place-memo">
            {{ place.memo }}
          </p>

          <form
            v-if="props.editingPlaceId === place.id"
            class="saved-place-memo-form"
            @submit.prevent="emit('save-memo', place)"
          >
            <textarea
              :value="props.memoInput"
              rows="3"
              maxlength="2000"
              placeholder="이 장소에 대한 메모를 남겨보세요."
              @input="emit('update:memoInput', $event.target.value)"
            ></textarea>
            <span class="saved-place-actions">
              <button type="submit" :disabled="props.updatingPlaceId === place.id">
                {{ props.updatingPlaceId === place.id ? '저장 중' : '메모 저장' }}
              </button>
              <button type="button" class="ghost-button" @click="emit('cancel-memo-edit')">
                취소
              </button>
            </span>
          </form>
        </div>

        <div class="saved-place-actions">
          <button
            v-if="props.editingPlaceId !== place.id"
            type="button"
            @click="emit('start-memo-edit', place)"
          >
            메모
          </button>
          <a
            v-if="getSavedPlaceDetailUrl(place)"
            :href="getSavedPlaceDetailUrl(place)"
            target="_blank"
            rel="noopener noreferrer"
          >
            상세
          </a>
          <a
            v-if="getSavedPlaceNavigationUrl(place)"
            :href="getSavedPlaceNavigationUrl(place)"
            target="_blank"
            rel="noopener noreferrer"
          >
            길찾기
          </a>
          <button
            type="button"
            class="danger"
            :disabled="props.updatingPlaceId === place.id"
            @click="emit('delete-place', place)"
          >
            삭제
          </button>
        </div>
      </article>
    </div>
    <p v-else class="empty">{{ props.message }}</p>
    <p v-if="props.message && props.places.length" class="empty saved-place-status">
      {{ props.message }}
    </p>
  </section>
</template>

<style scoped>
.panel {
  padding: 22px;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.08);
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

.empty {
  color: #667085;
  font-weight: 700;
}

.preference-source-badge {
  width: fit-content;
  padding: 4px 7px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 11px;
  font-weight: 900;
  white-space: nowrap;
}

.saved-place-list {
  margin-top: 14px;
  display: grid;
  gap: 12px;
}

.saved-place-item {
  padding: 14px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  border: 1px solid #e5e8f0;
  border-radius: 12px;
  background: #f9fafb;
}

.saved-place-main {
  min-width: 0;
  display: grid;
  gap: 7px;
}

.saved-place-main strong {
  color: #111827;
  font-size: 16px;
}

.saved-place-meta,
.saved-place-memo {
  margin: 0;
  color: #667085;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.5;
}

.saved-place-memo {
  color: #344054;
  white-space: pre-line;
}

.saved-place-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.saved-place-actions button,
.saved-place-actions a {
  min-height: 32px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  background: #ffffff;
  color: #344054;
  font-size: 12px;
  font-weight: 900;
  text-decoration: none;
  cursor: pointer;
}

.saved-place-actions .danger {
  border-color: #fecaca;
  color: #b91c1c;
}

.saved-place-memo-form {
  display: grid;
  gap: 8px;
}

.saved-place-memo-form textarea {
  width: 100%;
  padding: 10px;
  resize: vertical;
  border: 1px solid #d0d5dd;
  border-radius: 10px;
  background: #ffffff;
  color: #111827;
  font: inherit;
}

.saved-place-status {
  margin-top: 12px;
  color: #047857;
}

@media (max-width: 820px) {
  .section-heading-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .saved-place-item {
    grid-template-columns: 1fr;
  }

  .saved-place-actions {
    justify-content: flex-start;
  }
}
</style>
