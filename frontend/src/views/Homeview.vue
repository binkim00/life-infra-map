<template>
  <main class="home">
    <h1>상황 기반 장소 추천 지도 서비스</h1>
    <p>홈 화면입니다.</p>

    <RouterLink to="/recommendation-test">
      추천 API 테스트 화면으로 이동
    </RouterLink>
  </main>
</template>

<style scoped>
.home {
  max-width: 720px;
  margin: 0 auto;
  padding: 40px 20px;
}

h1 {
  margin-bottom: 12px;
}

a {
  display: inline-block;
  margin-top: 16px;
}
</style>