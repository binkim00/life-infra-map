import styles from './GuideView.module.css'

const GUIDE_ROWS = [
  {
    title: '1. 장소 찾기',
    description: '홈에서 필요한 상황을 입력하면 주변 생활 인프라를 추천받을 수 있습니다.',
  },
  {
    title: '2. 게시판 이용',
    description: '자유게시판에서 이용 팁을 공유하고, 공지사항에서 운영 안내를 확인할 수 있습니다.',
  },
  {
    title: '3. 문의하기',
    description: '고객센터에서 문의를 남기면 답변 등록 시 알림으로 안내됩니다.',
  },
  {
    title: '4. 신고와 제재',
    description: '부적절한 게시글이나 댓글은 신고할 수 있으며, 운영자가 검토 후 조치합니다.',
  },
]

const GuideView = () => {
  return (
    <main className={styles.guidePage}>
      <section className={styles.guideContainer}>
        <header className={styles.pageHeader}>
          <div>
            <p className={styles.eyebrow}>GUIDE</p>
            <h1>이용가이드</h1>
          </div>
        </header>

        <section className={styles.guideBoard}>
          {GUIDE_ROWS.map((row) => (
            <article key={row.title} className={styles.guideRow}>
              <strong>{row.title}</strong>
              <p>{row.description}</p>
            </article>
          ))}
        </section>
      </section>
    </main>
  )
}

export default GuideView
