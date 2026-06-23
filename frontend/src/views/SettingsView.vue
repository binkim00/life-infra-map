<script setup>
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()
</script>

<template>
  <main class="settings-page">
    <section class="settings-container">
      <header class="page-header">
        <div>
          <p class="eyebrow">SETTINGS</p>
          <h1>설정</h1>
        </div>
      </header>

      <section class="settings-panel">
        <header>
          <h2>알림</h2>
          <p>서비스에서 받을 알림 방식을 관리합니다.</p>
        </header>

        <label class="setting-row">
          <span>
            <strong>새 댓글 알림</strong>
            <small>내 글에 댓글이 달리면 알려줍니다.</small>
          </span>
          <input v-model="settingsStore.commentNotifications" type="checkbox" />
        </label>

        <label class="setting-row">
          <span>
            <strong>문의 답변 알림</strong>
            <small>고객센터 답변 등록 시 알려줍니다.</small>
          </span>
          <input v-model="settingsStore.inquiryNotifications" type="checkbox" />
        </label>
      </section>

      <section class="settings-panel">
        <header>
          <h2>화면</h2>
          <p>목록과 지도를 보는 방식을 조정합니다.</p>
        </header>

        <label class="setting-row">
          <span>
            <strong>간결한 목록 보기</strong>
            <small>게시판과 장소 목록을 더 촘촘하게 표시합니다.</small>
          </span>
          <input v-model="settingsStore.compactMode" type="checkbox" />
        </label>
      </section>
    </section>
  </main>
</template>

<style scoped>
.settings-page { min-height: 100vh; padding: 40px 24px; background: #f6f7fb; }
.settings-container { max-width: 860px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.eyebrow { margin: 0 0 6px; color: #2563eb; font-size: 13px; font-weight: 900; letter-spacing: 0.08em; }
h1, h2 { margin: 0; color: #111827; }
.settings-panel { margin-bottom: 14px; border: 1px solid #e5e8f0; border-radius: 8px; background: #fff; box-shadow: 0 10px 28px rgba(20,35,70,.06); }
.settings-panel header { padding: 18px 20px; border-bottom: 1px solid #edf0f4; }
.settings-panel h2 { font-size: 18px; }
.settings-panel p { margin: 6px 0 0; color: #667085; font-size: 14px; font-weight: 700; }
.setting-row { min-height: 68px; padding: 14px 20px; display: flex; justify-content: space-between; gap: 16px; align-items: center; border-bottom: 1px solid #edf0f4; }
.setting-row:last-child { border-bottom: 0; }
.setting-row span { display: grid; gap: 4px; }
.setting-row strong { color: #111827; font-size: 14px; }
.setting-row small { color: #667085; font-size: 13px; }
.setting-row input { width: 18px; height: 18px; accent-color: #2563eb; }
</style>
