<script setup>
import ironIcon from '@/assets/tiers/iron.png'
import bronzeIcon from '@/assets/tiers/bronze.png'
import silverIcon from '@/assets/tiers/silver.png'
import goldIcon from '@/assets/tiers/gold.png'
import platinumIcon from '@/assets/tiers/platinum.png'
import diamondIcon from '@/assets/tiers/diamond.png'
import masterIcon from '@/assets/tiers/master.png'
import challengerIcon from '@/assets/tiers/challenger.png'

const contributionRules = [
  { label: '일일 게시글 작성', contribution: '1~5개당 기여도 +1', description: '같은 날짜에 작성한 게시글은 5개 단위 묶음으로 반영됩니다.' },
  { label: '일일 댓글 작성', contribution: '1~10개당 기여도 +1', description: '같은 날짜에 작성한 댓글은 10개 단위 묶음으로 반영됩니다.' },
  { label: '게시글/댓글 일일 제한', contribution: '하루 최대 +5', description: '게시글과 댓글로 얻는 기여도는 하루 합산 최대 5점까지 반영됩니다.' },
  { label: '태그 제보 승인', contribution: '기여도 +10', description: '관리자가 장소 태그 제보를 승인하면 반영됩니다.' },
  { label: '오류 제보 승인', contribution: '기여도 +5', description: '잘못된 장소 정보 제보가 승인되면 반영됩니다.' },
  { label: '장소 수정 제보 승인', contribution: '기여도 +5', description: '장소 정보 수정 제보가 승인되면 반영됩니다.' },
  { label: '새 장소 제보 승인', contribution: '기여도 +20', description: '새로운 장소 제보가 승인되면 반영됩니다.' },
]

const tiers = [
  {
    key: 'iron',
    name: '아이언',
    minScore: 0,
    icon: ironIcon,
    tone: 'iron',
    condition: '기본 티어',
    description: '처음 시작하는 기본 등급입니다.',
  },
  {
    key: 'bronze',
    name: '브론즈',
    minScore: 50,
    icon: bronzeIcon,
    tone: 'bronze',
    condition: '기여도 50 이상',
    description: '게시글과 댓글 활동을 시작한 사용자에게 부여됩니다.',
  },
  {
    key: 'silver',
    name: '실버',
    minScore: 100,
    icon: silverIcon,
    tone: 'silver',
    condition: '기여도 100 이상',
    description: '꾸준히 게시판 활동을 이어가는 사용자 등급입니다.',
  },
  {
    key: 'gold',
    name: '골드',
    minScore: 200,
    icon: goldIcon,
    tone: 'gold',
    condition: '기여도 200 이상',
    description: '장소 정보와 의견 공유에 적극적으로 참여한 사용자 등급입니다.',
  },
  {
    key: 'platinum',
    name: '플래티넘',
    minScore: 300,
    icon: platinumIcon,
    tone: 'platinum',
    condition: '기여도 300 이상',
    description: '서비스 커뮤니티에 안정적으로 기여한 사용자 등급입니다.',
  },
  {
    key: 'diamond',
    name: '다이아',
    minScore: 500,
    icon: diamondIcon,
    tone: 'diamond',
    condition: '기여도 500 이상',
    description: '활발한 활동으로 신뢰도 높은 사용자에게 부여되는 등급입니다.',
  },
  {
    key: 'master',
    name: '마스터',
    minScore: 700,
    icon: masterIcon,
    tone: 'master',
    condition: '기여도 700 이상',
    description: '게시판 활동과 소통이 매우 활발한 상위 등급입니다.',
  },
  {
    key: 'challenger',
    name: '챌린저',
    minScore: 1000,
    icon: challengerIcon,
    tone: 'challenger',
    condition: '기여도 1000 이상',
    description: '현재 기준 최고 등급입니다.',
  },
]
</script>

<template>
  <main class="upgrade-page">
    <section class="upgrade-container">
      <header class="upgrade-hero">
        <div>
          <p class="eyebrow">TIER GUIDE</p>
          <h1>승급가이드</h1>
          <p class="hero-description">
            게시글, 댓글, 승인된 장소 제보 기여도를 기준으로 티어가 자동 계산됩니다.
            기여도 반영 기준과 승급 조건은 추후 서비스 운영 기준에 맞춰 조정될 수 있습니다.
          </p>
        </div>
      </header>

      <section class="score-rule-panel">
        <div class="score-rule-title">
          <span class="rule-icon" aria-hidden="true">✦</span>
          <div>
            <h2>기여도 반영 기준</h2>
            <p>현재 임시 기준입니다. 추후 활동 종류가 추가되면 기여도 기준도 함께 변경할 수 있습니다.</p>
          </div>
        </div>

        <div class="score-rule-grid">
          <article v-for="rule in contributionRules" :key="rule.label" class="score-rule-card">
            <strong>{{ rule.label }}</strong>
            <span>{{ rule.contribution }}</span>
            <p>{{ rule.description }}</p>
          </article>
        </div>
      </section>

      <section class="tier-section">
        <div class="section-title-row">
          <div>
            <h2>티어별 승급 조건</h2>
            <p>아이언부터 챌린저까지 총 8단계로 구성됩니다.</p>
          </div>
        </div>

        <div class="tier-grid">
          <article
            v-for="tier in tiers"
            :key="tier.key"
            class="tier-card"
            :class="`tier-${tier.tone}`"
          >
            <div class="tier-icon-wrap">
              <img :src="tier.icon" :alt="`${tier.name} 티어 아이콘`" />
            </div>

            <div class="tier-info">
              <div class="tier-name-row">
                <h3>{{ tier.name }}</h3>
                <span>{{ tier.condition }}</span>
              </div>

              <p>{{ tier.description }}</p>

              <div class="tier-score-line">
                <strong>기여도 {{ tier.minScore }}</strong>
                <span v-if="tier.minScore === 0">부터 시작</span>
                <span v-else>이상 달성 시 승급</span>
              </div>
            </div>
          </article>
        </div>
      </section>

      <p class="upgrade-update-notice">
        적극이용자와 티어별 승급 혜택은 추후 업데이트 예정입니다.
      </p>
    </section>
  </main>
</template>

<style scoped>
.upgrade-page {
  min-height: 100vh;
  padding: 40px 24px 72px;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.12), transparent 34%),
    #f6f7fb;
}

.upgrade-container {
  max-width: 1120px;
  margin: 0 auto;
}

.upgrade-hero {
  margin-bottom: 22px;
  padding: 30px;
  border: 1px solid #dbe4ff;
  border-radius: 26px;
  background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
  box-shadow: 0 18px 50px rgba(20, 35, 70, 0.1);
}

.eyebrow {
  margin: 0 0 8px;
  color: #2563eb;
  font-size: 13px;
  font-weight: 900;
  letter-spacing: 0.1em;
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  color: #111827;
  font-size: clamp(32px, 5vw, 48px);
  letter-spacing: -0.04em;
}

.hero-description {
  max-width: 720px;
  margin-top: 12px;
  color: #475467;
  font-size: 16px;
  line-height: 1.7;
}

.score-rule-panel,
.tier-section {
  margin-top: 18px;
  padding: 24px;
  border: 1px solid #e5e8f0;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 12px 34px rgba(20, 35, 70, 0.08);
}

.score-rule-title {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.rule-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: #2563eb;
  color: #ffffff;
  font-size: 20px;
  font-weight: 900;
}

.score-rule-title h2,
.section-title-row h2 {
  color: #111827;
  font-size: 22px;
}

.score-rule-title p,
.section-title-row p {
  margin-top: 5px;
  color: #667085;
  line-height: 1.6;
}

.score-rule-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.score-rule-card {
  padding: 18px;
  display: grid;
  gap: 8px;
  border: 1px solid #e5e8f0;
  border-radius: 18px;
  background: #ffffff;
}

.score-rule-card strong {
  color: #111827;
  font-size: 15px;
}

.score-rule-card span {
  width: fit-content;
  padding: 6px 10px;
  border-radius: 999px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 14px;
  font-weight: 900;
}

.score-rule-card p {
  color: #667085;
  font-size: 14px;
  line-height: 1.6;
}

.section-title-row {
  margin-bottom: 18px;
}

.tier-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.tier-card {
  position: relative;
  overflow: hidden;
  padding: 18px;
  display: grid;
  gap: 14px;
  border: 1px solid #e5e8f0;
  border-radius: 22px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(20, 35, 70, 0.07);
}

.tier-card::before {
  position: absolute;
  inset: 0;
  content: "";
  opacity: 0.1;
  pointer-events: none;
}

.tier-icon-wrap {
  position: relative;
  z-index: 1;
  height: 132px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  background: transparent;
}

.tier-icon-wrap img {
  width: 106px;
  height: 106px;
  object-fit: contain;
  filter: drop-shadow(0 10px 14px rgba(20, 35, 70, 0.18));
}

.tier-info {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 10px;
}

.tier-name-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.tier-name-row h3 {
  color: #111827;
  font-size: 19px;
}

.tier-name-row span {
  flex: 0 0 auto;
  padding: 5px 9px;
  border-radius: 999px;
  background: #f2f4f7;
  color: #344054;
  font-size: 12px;
  font-weight: 900;
}

.tier-info p {
  min-height: 66px;
  color: #667085;
  font-size: 14px;
  line-height: 1.6;
}

.tier-score-line {
  display: flex;
  gap: 4px;
  align-items: baseline;
  color: #475467;
  font-size: 13px;
  font-weight: 800;
}

.tier-score-line strong {
  color: #111827;
  font-size: 18px;
}

.tier-iron::before { background: linear-gradient(135deg, #111827, transparent); }
.tier-bronze::before { background: linear-gradient(135deg, #92400e, transparent); }
.tier-silver::before { background: linear-gradient(135deg, #64748b, transparent); }
.tier-gold::before { background: linear-gradient(135deg, #d97706, transparent); }
.tier-platinum::before { background: linear-gradient(135deg, #93c5fd, transparent); }
.tier-diamond::before { background: linear-gradient(135deg, #06b6d4, transparent); }
.tier-master::before { background: linear-gradient(135deg, #7c3aed, transparent); }
.tier-challenger::before { background: linear-gradient(135deg, #1d4ed8, transparent); }

.upgrade-update-notice {
  margin: 18px 0 0;
  padding: 16px 18px;
  border: 2px solid #222222;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.94);
  color: #344054;
  font-size: 14px;
  font-weight: 900;
  text-align: center;
  box-shadow: 0 7px 0 #f2d7b0;
}

@media (max-width: 1040px) {
  .tier-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .upgrade-page {
    padding: 28px 16px 56px;
  }

  .upgrade-hero,
  .score-rule-panel,
  .tier-section {
    padding: 20px;
    border-radius: 20px;
  }

  .score-rule-grid,
  .tier-grid {
    grid-template-columns: 1fr;
  }

  .tier-icon-wrap {
    height: 118px;
  }

  .tier-icon-wrap img {
    width: 96px;
    height: 96px;
  }
}
</style>
