<script setup>
defineProps({
  place: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <article class="card">
    <div class="card-header">
      <h2>{{ place.name }}</h2>
      <strong>{{ place.score }}점</strong>
    </div>

    <p class="meta">
      {{ place.category }} ·
      <span v-if="place.distance !== null && place.distance !== undefined">
        {{ place.distance }}m
      </span>
      <span v-else>
        거리 정보 없음
      </span>
    </p>

    <p class="address">{{ place.address }}</p>

    <div v-if="place.match_level || place.recommendation_confidence" class="trust-row">
      <span v-if="place.match_level">
        {{ place.match_level }}
      </span>
      <span v-if="place.recommendation_confidence">
        신뢰도 {{ place.recommendation_confidence }}
      </span>
    </div>

    <div v-if="place.runtime_tags?.length" class="tag-section">
      <p class="tag-label">매칭 태그</p>
      <div class="tags runtime">
        <span v-for="tag in place.runtime_tags" :key="tag">
          #{{ tag }}
        </span>
      </div>
    </div>

    <div v-if="place.suggested_tags?.length" class="tag-section">
      <p class="tag-label">추천 태그 후보</p>
      <div class="tags suggested">
        <span v-for="tag in place.suggested_tags" :key="tag">
          #{{ tag }}
        </span>
      </div>
    </div>

    <div v-if="place.verified_tags?.length" class="tag-section">
      <p class="tag-label">검증 태그</p>
      <div class="tags verified">
        <span v-for="tag in place.verified_tags" :key="tag">
          #{{ tag }}
        </span>
      </div>
    </div>

    <div v-if="place.warning_tags?.length" class="tag-section">
      <p class="tag-label">주의 태그</p>
      <div class="tags warning">
        <span v-for="tag in place.warning_tags" :key="tag">
          #{{ tag }}
        </span>
      </div>
    </div>

    <div
      v-if="place.data_quality_score || place.raw_scores?.recommendation_ready_score || place.score_breakdown"
      class="score-detail"
    >
      <p v-if="place.data_quality_score">
        데이터 신뢰도: {{ place.data_quality_score }}점
      </p>
      <p v-if="place.raw_scores?.recommendation_ready_score">
        추천 준비도: {{ place.raw_scores.recommendation_ready_score }}점
      </p>
      <p v-if="place.score_breakdown">
        점수 근거:
        카테고리 {{ place.score_breakdown.category }},
        태그 {{ place.score_breakdown.tags }},
        거리 {{ place.score_breakdown.distance }},
        품질 {{ place.score_breakdown.data_quality }}
      </p>
    </div>

    <details v-if="place.tag_details?.length" class="tag-details">
      <summary>태그 근거 보기</summary>

      <ul>
        <li v-for="tag in place.tag_details" :key="`${tag.name}-${tag.source}`">
          <strong>#{{ tag.name }}</strong>
          <span> · 신뢰도 {{ tag.confidence }}점</span>
          <p>{{ tag.evidence }}</p>
        </li>
      </ul>
    </details>

    <p class="reason">{{ place.recommend_reason }}</p>
    <p class="caution">{{ place.caution }}</p>

    <a
      v-if="place.navigation_url"
      :href="place.navigation_url"
      target="_blank"
      rel="noopener noreferrer"
      class="nav-button"
    >
      길찾기
    </a>
  </article>
</template>

<style scoped>
.card {
  padding: 20px;
  border: 1px solid #ddd;
  border-radius: 8px;
  margin-bottom: 16px;
  background: #fff;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.card-header h2 {
  margin: 0;
}

.meta {
  margin-top: 8px;
  color: #555;
}

.address {
  color: #666;
}

.trust-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.trust-row span {
  padding: 4px 8px;
  border-radius: 999px;
  background: #e7f5ff;
  color: #1864ab;
  font-size: 13px;
  font-weight: 800;
}

.tag-section {
  margin-top: 12px;
}

.tag-label {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 700;
  color: #555;
}

.tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tags span {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 14px;
}

.runtime span {
  background: #f1f3f5;
}

.suggested span {
  background: #fff3bf;
}

.verified span {
  background: #d3f9d8;
}

.warning span {
  background: #ffe3e3;
}

.score-detail {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8f9fa;
  font-size: 13px;
  color: #555;
}

.score-detail p {
  margin: 2px 0;
}

.tag-details {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8f9fa;
  font-size: 13px;
}

.tag-details summary {
  cursor: pointer;
  font-weight: 700;
}

.tag-details ul {
  margin: 8px 0 0;
  padding-left: 18px;
}

.tag-details li {
  margin-bottom: 8px;
}

.tag-details p {
  margin: 4px 0 0;
  color: #666;
}

.reason {
  margin-top: 16px;
  font-weight: 500;
}

.caution {
  color: #777;
  font-size: 14px;
}

.nav-button {
  display: inline-block;
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #222;
  color: white;
  text-decoration: none;
}
</style>
