import { useSettingsStore } from '@/stores/settings'

import styles from './SettingsView.module.css'

const SettingsView = () => {
  const commentNotifications = useSettingsStore((state) => state.commentNotifications)
  const inquiryNotifications = useSettingsStore((state) => state.inquiryNotifications)
  const compactMode = useSettingsStore((state) => state.compactMode)
  const setSetting = useSettingsStore((state) => state.setSetting)

  return (
    <main className={styles.settingsPage}>
      <section className={styles.settingsContainer}>
        <header className={styles.pageHeader}>
          <div>
            <p className={styles.eyebrow}>SETTINGS</p>
            <h1>설정</h1>
          </div>
        </header>

        <section className={styles.settingsPanel}>
          <header>
            <h2>알림</h2>
            <p>서비스에서 받을 알림 방식을 관리합니다.</p>
          </header>

          <label className={styles.settingRow}>
            <span>
              <strong>새 댓글 알림</strong>
              <small>내 글에 댓글이 달리면 알려줍니다.</small>
            </span>
            <input
              type="checkbox"
              checked={commentNotifications}
              onChange={(event) => setSetting('commentNotifications', event.target.checked)}
            />
          </label>

          <label className={styles.settingRow}>
            <span>
              <strong>문의 답변 알림</strong>
              <small>고객센터 답변 등록 시 알려줍니다.</small>
            </span>
            <input
              type="checkbox"
              checked={inquiryNotifications}
              onChange={(event) => setSetting('inquiryNotifications', event.target.checked)}
            />
          </label>
        </section>

        <section className={styles.settingsPanel}>
          <header>
            <h2>화면</h2>
            <p>목록과 지도를 보는 방식을 조정합니다.</p>
          </header>

          <label className={styles.settingRow}>
            <span>
              <strong>간결한 목록 보기</strong>
              <small>게시판과 장소 목록을 더 촘촘하게 표시합니다.</small>
            </span>
            <input
              type="checkbox"
              checked={compactMode}
              onChange={(event) => setSetting('compactMode', event.target.checked)}
            />
          </label>
        </section>
      </section>
    </main>
  )
}

export default SettingsView
