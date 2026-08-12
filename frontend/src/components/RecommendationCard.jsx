import styles from './RecommendationCard.module.css'

const TAG_SECTIONS = [
  { key: 'runtime_tags', label: '매칭 태그', variant: 'runtime' },
  { key: 'suggested_tags', label: '추천 태그 후보', variant: 'suggested' },
  { key: 'verified_tags', label: '검증 태그', variant: 'verified' },
  { key: 'warning_tags', label: '주의 태그', variant: 'warning' },
]

const RecommendationCard = ({ place }) => {
  const hasDistance = place.distance !== null && place.distance !== undefined
  const hasTrustRow = place.match_level || place.recommendation_confidence
  const hasScoreDetail = place.data_quality_score
    || place.raw_scores?.recommendation_ready_score
    || place.score_breakdown

  return (
    <article className={styles.card}>
      <div className={styles.cardHeader}>
        <h2>{place.name}</h2>
        <strong>{place.score}점</strong>
      </div>

      <p className={styles.meta}>
        {place.category}
        {' · '}
        <span>{hasDistance ? `${place.distance}m` : '거리 정보 없음'}</span>
      </p>

      <p className={styles.address}>{place.address}</p>

      {hasTrustRow ? (
        <div className={styles.trustRow}>
          {place.match_level ? <span>{place.match_level}</span> : null}
          {place.recommendation_confidence ? (
            <span>신뢰도 {place.recommendation_confidence}</span>
          ) : null}
        </div>
      ) : null}

      {TAG_SECTIONS.map(({ key, label, variant }) => (
        place[key]?.length ? (
          <div key={key} className={styles.tagSection}>
            <p className={styles.tagLabel}>{label}</p>
            <div className={`${styles.tags} ${styles[variant]}`}>
              {place[key].map((tag) => (
                <span key={tag}>#{tag}</span>
              ))}
            </div>
          </div>
        ) : null
      ))}

      {hasScoreDetail ? (
        <div className={styles.scoreDetail}>
          {place.data_quality_score ? (
            <p>데이터 신뢰도: {place.data_quality_score}점</p>
          ) : null}
          {place.raw_scores?.recommendation_ready_score ? (
            <p>추천 준비도: {place.raw_scores.recommendation_ready_score}점</p>
          ) : null}
          {place.score_breakdown ? (
            <p>
              점수 근거:
              {` 카테고리 ${place.score_breakdown.category},`}
              {` 태그 ${place.score_breakdown.tags},`}
              {` 거리 ${place.score_breakdown.distance},`}
              {` 품질 ${place.score_breakdown.data_quality}`}
            </p>
          ) : null}
        </div>
      ) : null}

      {place.tag_details?.length ? (
        <details className={styles.tagDetails}>
          <summary>태그 근거 보기</summary>

          <ul>
            {place.tag_details.map((tag) => (
              <li key={`${tag.name}-${tag.source}`}>
                <strong>#{tag.name}</strong>
                <span> · 신뢰도 {tag.confidence}점</span>
                <p>{tag.evidence}</p>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <p className={styles.reason}>{place.recommend_reason}</p>
      <p className={styles.caution}>{place.caution}</p>

      {place.navigation_url ? (
        <a
          href={place.navigation_url}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.navButton}
        >
          길찾기
        </a>
      ) : null}
    </article>
  )
}

export default RecommendationCard
