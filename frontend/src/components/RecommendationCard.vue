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

    <p class="meta">{{ place.category }} · {{ place.distance }}m</p>
    <p class="address">{{ place.address }}</p>

    <div class="tags">
      <span v-for="tag in place.runtime_tags" :key="tag">
        #{{ tag }}
      </span>
    </div>

    <div v-if="place.verified_tags?.length" class="tags verified">
      <span v-for="tag in place.verified_tags" :key="tag">
        #{{ tag }}
      </span>
    </div>

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
  border-radius: 16px;
  margin-bottom: 16px;
  background: #fff;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 12px 0;
}

.tags span {
  padding: 4px 8px;
  border-radius: 999px;
  background: #f1f3f5;
  font-size: 14px;
}

.verified span {
  background: #e7f5ff;
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