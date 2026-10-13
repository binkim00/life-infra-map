import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { fetchAdminOperations } from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'
import { placeCategoryLabel } from '@/utils/placeCategoryLabel'

import styles from './AdminOperationsView.module.css'

const REGIONS = ['', '서울', '부산', '인천', '대구', '대전', '광주', '울산']
const CATEGORIES = ['', 'cafe', 'restaurant', 'toilet', 'parking', 'city_park', 'shelter', 'library', 'tourism', 'freewifi']
const number = (value) => Number(value || 0).toLocaleString('ko-KR')
const percent = (value) => value == null ? '집계 없음' : `${(Number(value) * 100).toFixed(2)}%`
const metric = (value, suffix = '') => value == null ? '집계 없음' : `${number(value)}${suffix}`
const QUEUE_LABELS = { queued: '대기', processing: '처리 중', retry: '재시도', failed: '실패', completed_period: '기간 내 완료' }
const READINESS_LABELS = { READY: '준비됨', PARTIAL: '일부 준비', NOT_READY: '준비 필요' }
const STRATEGY_LABELS = { candidate_hint: '후보 단서', category_seed: '카테고리 기반', nearby_expansion: '주변 확장' }
const SCOPE_LABELS = { OPERATING_JSON_DOCUMENT_REGISTRY: '운영 문서 저장소', ISOLATED_NOT_OPERATING: '별도 시험 환경' }

const KpiCard = ({ label, value, note }) => (
  <article className={styles.kpiCard}>
    <span>{label}</span>
    <strong>{value}</strong>
    {note ? <small>{note}</small> : null}
  </article>
)

const AdminOperationsView = () => {
  const navigate = useNavigate()
  const [filters, setFilters] = useState({ days: 1, region: '', category: '' })
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!useAuthStore.getState().user?.is_staff) {
      navigate('/', { replace: true })
      return
    }
    setLoading(true)
    setError('')
    try {
      setData(await fetchAdminOperations(filters))
    } catch (requestError) {
      setData(null)
      setError(requestError.response?.data?.detail || '운영 지표를 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }, [filters, navigate])

  useEffect(() => { load() }, [load])

  const naver = useMemo(() => data?.providers?.find((row) => row.provider === 'naver_search'), [data])
  const openai = useMemo(() => data?.providers?.find((row) => row.provider === 'openai_evidence'), [data])
  const maxGrowth = Math.max(1, ...(data?.growth || []).map((row) => row.new_active_evidence))

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>관리자 운영 현황</p>
            <h1>장소 데이터 운영 현황</h1>
            <p>수집 근거, 외부 서비스 사용량, 장소 정보 범위와 수집 효율을 확인합니다.</p>
          </div>
          <nav className={styles.tabs} aria-label="관리자 메뉴">
            <Link to="/admin/operations" className={styles.activeTab}>운영 현황</Link>
            <Link to="/admin/reports">신고</Link>
            <Link to="/admin/place-reports">장소 제보</Link>
            <Link to="/admin/users">사용자</Link>
            <Link to="/admin/inquiries">문의</Link>
          </nav>
        </header>

        <section className={styles.filters} aria-label="운영 지표 필터">
          <label>기간<select aria-label="기간" value={filters.days} onChange={(event) => setFilters((current) => ({ ...current, days: Number(event.target.value) }))}>
            <option value={1}>오늘</option><option value={7}>7일</option><option value={30}>30일</option>
          </select></label>
          <label>지역<select aria-label="지역" value={filters.region} onChange={(event) => setFilters((current) => ({ ...current, region: event.target.value }))}>
            {REGIONS.map((item) => <option key={item || 'all'} value={item}>{item || '전체'}</option>)}
          </select></label>
          <label>카테고리<select aria-label="카테고리" value={filters.category} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value }))}>
            {CATEGORIES.map((item) => <option key={item || 'all'} value={item}>{item ? placeCategoryLabel({ category: item }) : '전체'}</option>)}
          </select></label>
        </section>

        {loading ? <section className={styles.state}>운영 지표를 계산하고 있습니다.</section> : null}
        {error ? <section className={styles.error} role="alert">{error}</section> : null}
        {!loading && !error && !data ? <section className={styles.state}>표시할 운영 데이터가 없습니다.</section> : null}

        {data ? <>
          <section className={styles.panel} aria-label="현재 집중 지역">
            <h2>현재 집중 지역: {data.focus_region?.region || '미설정'}</h2>
            <div className={styles.providerRow}>
              <strong>{data.focus_region?.state || '상태 확인 필요'}</strong>
              {Object.entries(data.focus_region?.categories || {}).map(([name, row]) => <span key={name}>
                {placeCategoryLabel({ category: name })} {number(row.active_evidence_places)} / {number(row.places)} ({percent(row.place_coverage)}) · 오늘 처리 {number(row.processed_period)}
              </span>)}
            </div>
          </section>
          <section className={styles.kpiGrid} aria-label="핵심 지표">
            <KpiCard label="신규 근거" value={number(data.period.new_evidence)} note={`${filters.days}일 범위`} />
            <KpiCard label="신규 사용 가능 근거" value={number(data.period.new_active_evidence)} />
            <KpiCard label="새 장소 태그" value={number(data.period.new_place_tags)} />
            <KpiCard label="처리한 장소" value={number(data.period.processed_places)} />
            <KpiCard label="네이버 사용률" value={percent(naver?.today_usage_rate)} note={`${number(naver?.calls)}회 호출`} />
            <KpiCard label="OpenAI 예상 비용" value={openai?.estimated_cost_usd == null ? '집계 없음' : `$${openai.estimated_cost_usd}`} note={`${number(openai?.calls)}회 호출`} />
          </section>

          <section className={styles.panelGrid}>
            <article className={styles.panel}>
              <h2>일별 사용 가능 근거 증가</h2>
              <div className={styles.chart}>
                {data.growth.map((row) => <div className={styles.barColumn} key={row.date} title={`${row.date}: ${row.new_active_evidence}`}>
                  <div className={styles.bar} style={{ height: `${Math.max(3, row.new_active_evidence / maxGrowth * 100)}%` }} />
                  <small>{row.date.slice(5)}</small>
                </div>)}
              </div>
            </article>
            <article className={styles.panel}>
              <h2>새로 확인된 태그 상위 10개</h2>
              <ol className={styles.rankList}>{data.top_active_tags.map((row) => <li key={row.tag}><span>{row.tag}</span><strong>+{number(row.count)}</strong></li>)}</ol>
            </article>
          </section>

          <section className={styles.panel}>
            <h2>수집 방식별 효율</h2>
            <div className={styles.tableWrap}><table><thead><tr><th>수집 방식</th><th>장소</th><th>호출</th><th>근거</th><th>사용 가능</th><th>호출당 근거</th><th>호출당 사용 가능</th></tr></thead>
              <tbody>{data.strategies.map((row) => <tr key={row.strategy}><td>{STRATEGY_LABELS[row.strategy] || '기타 수집 방식'}</td><td>{number(row.places)}</td><td>{number(row.calls)}</td><td>{number(row.evidence)}</td><td>{number(row.active)}</td><td>{row.evidence_per_call}</td><td>{row.active_per_call}</td></tr>)}</tbody></table></div>
          </section>

          <section className={styles.panelGrid}>
            <article className={styles.panel}><h2>지역별 정보 범위</h2><CoverageTable rows={data.regions} labelKey="region" /></article>
            <article className={styles.panel}><h2>카테고리별 정보 범위</h2><CoverageTable rows={data.categories} labelKey="category" /></article>
          </section>

          <section className={styles.panel}>
            <h2>{placeCategoryLabel({ category: data.tag_coverage_category })} 태그 정보 범위</h2>
            {Object.entries(data.tag_coverage).map(([regionName, rows]) => <div key={regionName} className={styles.tagSection}><h3>{regionName}</h3><div className={styles.tagGrid}>{rows.map((row) => <div key={row.tag}><span>{row.tag}</span><strong>{number(row.active_places)}</strong><small>{percent(row.coverage)} · +{number(row.period_increase)}</small></div>)}</div></div>)}
          </section>

          <section className={styles.panelGrid}>
            <article className={styles.panel}><h2>외부 서비스 사용량</h2>{data.providers.map((row) => <div className={styles.providerRow} key={row.provider}><strong>{row.provider === 'naver_search' ? '네이버 검색' : row.provider === 'openai_evidence' ? 'OpenAI 근거 분석' : '기타 서비스'}</strong><span>{number(row.calls)}회 호출</span><span>실패 {number(row.failures)} / 요청 제한 {number(row.rate_limited)}</span><span>사용 토큰 {metric(row.total_tokens)}</span></div>)}</article>
            <article className={styles.panel}><h2>수집 작업 상태</h2><dl className={styles.definitionList}>{Object.entries(data.queue).map(([key, value]) => <div key={key}><dt>{QUEUE_LABELS[key] || '기타 작업'}</dt><dd>{number(value)}</dd></div>)}</dl><p className={styles.note}>최근 수집 성공: {data.runtime.worker_last_success_at ? new Date(data.runtime.worker_last_success_at).toLocaleString('ko-KR') : '없음'}</p></article>
          </section>

          <section className={styles.panel}><h2>공식 자료 최신성</h2><div className={styles.tableWrap}><table><thead><tr><th>자료 출처</th><th>최신 기준일</th><th>현재 근거</th><th>오래된 근거</th><th>오래된 비율</th><th>갱신</th></tr></thead><tbody>{data.source_freshness.map((row) => <tr key={row.source}><td>{placeCategoryLabel({ category: row.source })}</td><td>{row.latest_source_date || '기준일 없음'}</td><td>{number(row.current_evidence)}</td><td>{number(row.stale_evidence)}</td><td>{percent(row.stale_ratio)}</td><td>{row.refresh_needed ? '필요' : '정상'}</td></tr>)}</tbody></table></div></section>
          <section className={styles.panel}><h2>검색 성능</h2><p className={styles.note}>{data.search_performance.status === 'NOT_AVAILABLE' ? '검색 응답 시간 집계가 없습니다.' : data.search_performance.reason || '상태 확인 필요'}</p></section>
          <section className={styles.panel}><h2>의미 검색 시험 현황</h2><div className={styles.providerRow}>
            <strong>{data.semantic_pilot?.model || '모델 미설정'}</strong>
            <span>문서 {number(data.semantic_pilot?.feature_documents)}</span>
            <span>임베딩 {number(data.semantic_pilot?.embedded_documents)}건 · {metric(data.semantic_pilot?.dimensions, '차원')}</span>
            <span>검색 {data.semantic_pilot?.retrieval_enabled ? '사용' : '사용 안 함'} / 후보 반영 {data.semantic_pilot?.candidate_injection_enabled ? '사용' : '사용 안 함'}</span>
            <span>운영 범위 {SCOPE_LABELS[data.semantic_pilot?.operating_scope] || '확인 필요'} / 벡터 검색 시험 {SCOPE_LABELS[data.semantic_pilot?.pgvector_staging_scope] || '확인 필요'}</span>
          </div></section>
        </> : null}
      </div>
    </main>
  )
}

const CoverageTable = ({ rows, labelKey }) => <div className={styles.tableWrap}><table><thead><tr><th>{labelKey === 'region' ? '지역' : '카테고리'}</th><th>장소</th><th>근거가 있는 장소</th><th>사용 가능 근거 장소</th><th>정보 범위</th><th>오래된 비율</th><th>상태</th></tr></thead><tbody>{rows.map((row) => <tr key={row[labelKey]}><td>{labelKey === 'category' ? placeCategoryLabel({ category: row[labelKey] }) : row[labelKey]}</td><td>{number(row.places)}</td><td>{number(row.evidence_places)}</td><td>{number(row.active_evidence_places)}</td><td>{percent(row.place_coverage)}</td><td>{percent(row.stale_ratio)}</td><td>{READINESS_LABELS[row.readiness] || '확인 필요'}</td></tr>)}</tbody></table></div>

export default AdminOperationsView
