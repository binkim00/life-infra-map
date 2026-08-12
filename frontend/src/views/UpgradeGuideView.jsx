import { tierIconMap } from '@/utils/tierIcons'

import styles from './UpgradeGuideView.module.css'

const CONTRIBUTION_RULES = [
  { label: '일일 게시글 작성', contribution: '1~5개당 기여도 +1', description: '같은 날짜에 작성한 게시글은 5개 단위 묶음으로 반영됩니다.' },
  { label: '일일 댓글 작성', contribution: '1~10개당 기여도 +1', description: '같은 날짜에 작성한 댓글은 10개 단위 묶음으로 반영됩니다.' },
  { label: '게시글/댓글 일일 제한', contribution: '하루 최대 +5', description: '게시글과 댓글로 얻는 기여도는 하루 합산 최대 5점까지 반영됩니다.' },
  { label: '태그 제보 승인', contribution: '기여도 +10', description: '관리자가 장소 태그 제보를 승인하면 반영됩니다.' },
  { label: '오류 제보 승인', contribution: '기여도 +5', description: '잘못된 장소 정보 제보가 승인되면 반영됩니다.' },
  { label: '장소 수정 제보 승인', contribution: '기여도 +5', description: '장소 정보 수정 제보가 승인되면 반영됩니다.' },
  { label: '새 장소 제보 승인', contribution: '기여도 +20', description: '새로운 장소 제보가 승인되면 반영됩니다.' },
]

const TIERS = [
  {
    key: 'iron',
    name: '아이언',
    minScore: 0,
    tone: 'iron',
    condition: '기본 티어',
    description: '처음 시작하는 기본 등급입니다.',
  },
  {
    key: 'bronze',
    name: '브론즈',
    minScore: 50,
    tone: 'bronze',
    condition: '기여도 50 이상',
    description: '게시글과 댓글 활동을 시작한 사용자에게 부여됩니다.',
  },
  {
    key: 'silver',
    name: '실버',
    minScore: 100,
    tone: 'silver',
    condition: '기여도 100 이상',
    description: '꾸준히 게시판 활동을 이어가는 사용자 등급입니다.',
  },
  {
    key: 'gold',
    name: '골드',
    minScore: 200,
    tone: 'gold',
    condition: '기여도 200 이상',
    description: '장소 정보와 의견 공유에 적극적으로 참여한 사용자 등급입니다.',
  },
  {
    key: 'platinum',
    name: '플래티넘',
    minScore: 300,
    tone: 'platinum',
    condition: '기여도 300 이상',
    description: '서비스 커뮤니티에 안정적으로 기여한 사용자 등급입니다.',
  },
  {
    key: 'diamond',
    name: '다이아',
    minScore: 500,
    tone: 'diamond',
    condition: '기여도 500 이상',
    description: '활발한 활동으로 신뢰도 높은 사용자에게 부여되는 등급입니다.',
  },
  {
    key: 'master',
    name: '마스터',
    minScore: 700,
    tone: 'master',
    condition: '기여도 700 이상',
    description: '게시판 활동과 소통이 매우 활발한 상위 등급입니다.',
  },
  {
    key: 'challenger',
    name: '챌린저',
    minScore: 1000,
    tone: 'challenger',
    condition: '기여도 1000 이상',
    description: '현재 기준 최고 등급입니다.',
  },
]

const UpgradeGuideView = () => {
  return (
    <main className={styles.upgradePage}>
      <section className={styles.upgradeContainer}>
        <header className={styles.upgradeHero}>
          <div>
            <p className={styles.eyebrow}>TIER GUIDE</p>
            <h1>승급가이드</h1>
            <p className={styles.heroDescription}>
              게시글, 댓글, 승인된 장소 제보 기여도를 기준으로 티어가 자동 계산됩니다.
              기여도 반영 기준과 승급 조건은 추후 서비스 운영 기준에 맞춰 조정될 수 있습니다.
            </p>
          </div>
        </header>

        <section className={styles.scoreRulePanel}>
          <div className={styles.scoreRuleTitle}>
            <span className={styles.ruleIcon} aria-hidden="true">✦</span>
            <div>
              <h2>기여도 반영 기준</h2>
              <p>현재 임시 기준입니다. 추후 활동 종류가 추가되면 기여도 기준도 함께 변경할 수 있습니다.</p>
            </div>
          </div>

          <div className={styles.scoreRuleGrid}>
            {CONTRIBUTION_RULES.map((rule) => (
              <article key={rule.label} className={styles.scoreRuleCard}>
                <strong>{rule.label}</strong>
                <span>{rule.contribution}</span>
                <p>{rule.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.tierSection}>
          <div className={styles.sectionTitleRow}>
            <div>
              <h2>티어별 승급 조건</h2>
              <p>아이언부터 챌린저까지 총 8단계로 구성됩니다.</p>
            </div>
          </div>

          <div className={styles.tierGrid}>
            {TIERS.map((tier) => (
              <article
                key={tier.key}
                className={`${styles.tierCard} ${styles[`tier-${tier.tone}`] || ''}`}
              >
                <div className={styles.tierIconWrap}>
                  <img src={tierIconMap[tier.key]} alt={`${tier.name} 티어 아이콘`} />
                </div>

                <div className={styles.tierInfo}>
                  <div className={styles.tierNameRow}>
                    <h3>{tier.name}</h3>
                    <span>{tier.condition}</span>
                  </div>

                  <p>{tier.description}</p>

                  <div className={styles.tierScoreLine}>
                    <strong>기여도 {tier.minScore}</strong>
                    <span>{tier.minScore === 0 ? '부터 시작' : '이상 달성 시 승급'}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <p className={styles.upgradeUpdateNotice}>
          적극이용자와 티어별 승급 혜택은 추후 업데이트 예정입니다.
        </p>
      </section>
    </main>
  )
}

export default UpgradeGuideView
