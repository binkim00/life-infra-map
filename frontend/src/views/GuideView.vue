<template>
  <main class="guide-page">
    <section class="guide-container">
      <header class="page-header">
        <div>
          <p class="eyebrow">GUIDE</p>
          <h1>이용가이드</h1>
        </div>
      </header>

      <section class="guide-board">
        <article class="guide-row">
          <strong>1. 장소 찾기</strong>
          <p>홈에서 필요한 상황을 입력하면 주변 생활 인프라를 추천받을 수 있습니다.</p>
        </article>

        <article class="guide-row">
          <strong>2. 게시판 이용</strong>
          <p>자유게시판에서 이용 팁을 공유하고, 공지사항에서 운영 안내를 확인할 수 있습니다.</p>
        </article>

        <article class="guide-row">
          <strong>3. 문의하기</strong>
          <p>고객센터에서 문의를 남기면 답변 등록 시 알림으로 안내됩니다.</p>
        </article>

        <article class="guide-row">
          <strong>4. 신고와 제재</strong>
          <p>부적절한 게시글이나 댓글은 신고할 수 있으며, 운영자가 검토 후 조치합니다.</p>
        </article>
      </section>
    </section>
  </main>
</template>

<style scoped>
.guide-page { min-height: 100vh; padding: 40px 24px; background: #f6f7fb; }
.guide-container { max-width: 860px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.eyebrow { margin: 0 0 6px; color: #2563eb; font-size: 13px; font-weight: 900; letter-spacing: 0.08em; }
h1 { margin: 0; color: #111827; }
.guide-board { overflow: hidden; border: 1px solid #e5e8f0; border-radius: 8px; background: #fff; box-shadow: 0 10px 28px rgba(20,35,70,.06); }
.guide-row { padding: 18px 20px; display: grid; gap: 8px; border-bottom: 1px solid #edf0f4; }
.guide-row:last-child { border-bottom: 0; }
.guide-row strong { color: #111827; font-size: 15px; }
.guide-row p { margin: 0; color: #344054; line-height: 1.7; }
</style>
