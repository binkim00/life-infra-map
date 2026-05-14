<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <header class="app-header">
    <nav>
      <RouterLink to="/">Home</RouterLink>
      <RouterLink to="/recommendation-test">추천 API 테스트</RouterLink>
    </nav>
  </header>

  <RouterView />
</template>

<style scoped>
.app-header {
  padding: 16px 24px;
  border-bottom: 1px solid #eee;
}

nav {
  display: flex;
  gap: 16px;
}

a {
  color: #333;
  text-decoration: none;
}

.router-link-active {
  font-weight: 700;
}
</style>