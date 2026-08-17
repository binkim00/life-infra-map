import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { fetchAdminOperations } from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'

import styles from './AdminOperationsView.module.css'

const REGIONS = ['', '서울', '부산', '인천', '대구', '대전', '광주', '울산']
const CATEGORIES = ['', 'cafe', 'restaurant', 'toilet', 'parking', 'city_park', 'shelter', 'library', 'tourism', 'freewifi']
const number = (value) => Number(value || 0).toLocaleString('ko-KR')
const percent = (value) => value == null ? 'N/A' : `${(Number(value) * 100).toFixed(2)}%`
const metric = (value, suffix = '') => value == null ? 'NOT_MEASURED' : `${number(value)}${suffix}`

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
            <p className={styles.eyebrow}>ADMIN OPERATIONS</p>
            <h1>장소 데이터 운영 현황</h1>
            <p>Evidence 증가, Provider 비용, Coverage와 수집 효율을 함께 확인합니다.</p>
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
            {CATEGORIES.map((item) => <option key={item || 'all'} value={item}>{item || '전체'}</option>)}
          </select></label>
        </section>

        {loading ? <section className={styles.state}>운영 지표를 계산하고 있습니다.</section> : null}
        {error ? <section className={styles.error} role="alert">{error}</section> : null}
        {!loading && !error && !data ? <section className={styles.state}>표시할 운영 데이터가 없습니다.</section> : null}

        {data ? <>
          <section className={styles.kpiGrid} aria-label="핵심 지표">
            <KpiCard label="신규 Evidence" value={number(data.period.new_evidence)} note={`${filters.days}일 범위`} />
            <KpiCard label="신규 Active" value={number(data.period.new_active_evidence)} />
            <KpiCard label="신규 PlaceTag" value={number(data.period.new_place_tags)} />
            <KpiCard label="처리 Place" value={number(data.period.processed_places)} />
            <KpiCard label="Naver 사용률" value={percent(naver?.today_usage_rate)} note={`${number(naver?.calls)} calls`} />
            <KpiCard label="OpenAI 비용" value={openai?.estimated_cost_usd == null ? 'NOT_MEASURED' : `$${openai.estimated_cost_usd}`} note={`${number(openai?.calls)} calls`} />
          </section>

          <section className={styles.panelGrid}>
            <article className={styles.panel}>
              <h2>일별 Active Evidence 증가</h2>
              <div className={styles.chart}>
                {data.growth.map((row) => <div className={styles.barColumn} key={row.date} title={`${row.date}: ${row.new_active_evidence}`}>
                  <div className={styles.bar} style={{ height: `${Math.max(3, row.new_active_evidence / maxGrowth * 100)}%` }} />
                  <small>{row.date.slice(5)}</small>
                </div>)}
              </div>
            </article>
            <article className={styles.panel}>
              <h2>신규 Active Tag TOP 10</h2>
              <ol className={styles.rankList}>{data.top_active_tags.map((row) => <li key={row.tag}><span>{row.tag}</span><strong>+{number(row.count)}</strong></li>)}</ol>
            </article>
          </section>

          <section className={styles.panel}>
            <h2>수집 Strategy 효율</h2>
            <div className={styles.tableWrap}><table><thead><tr><th>Strategy</th><th>Place</th><th>Calls</th><th>Evidence</th><th>Active</th><th>Evidence/API</th><th>Active/API</th></tr></thead>
              <tbody>{data.strategies.map((row) => <tr key={row.strategy}><td>{row.strategy}</td><td>{number(row.places)}</td><td>{number(row.calls)}</td><td>{number(row.evidence)}</td><td>{number(row.active)}</td><td>{row.evidence_per_call}</td><td>{row.active_per_call}</td></tr>)}</tbody></table></div>
          </section>

          <section className={styles.panelGrid}>
            <article className={styles.panel}><h2>지역 Coverage</h2><CoverageTable rows={data.regions} labelKey="region" /></article>
            <article className={styles.panel}><h2>카테고리 Coverage</h2><CoverageTable rows={data.categories} labelKey="category" /></article>
          </section>

          <section className={styles.panel}>
            <h2>{data.tag_coverage_category} Canonical Tag Coverage</h2>
            {Object.entries(data.tag_coverage).map(([regionName, rows]) => <div key={regionName} className={styles.tagSection}><h3>{regionName}</h3><div className={styles.tagGrid}>{rows.map((row) => <div key={row.tag}><span>{row.tag}</span><strong>{number(row.active_places)}</strong><small>{percent(row.coverage)} · +{number(row.period_increase)}</small></div>)}</div></div>)}
          </section>

          <section className={styles.panelGrid}>
            <article className={styles.panel}><h2>Provider</h2>{data.providers.map((row) => <div className={styles.providerRow} key={row.provider}><strong>{row.provider}</strong><span>{number(row.calls)} calls</span><span>실패 {number(row.failures)} / 429 {number(row.rate_limited)}</span><span>tokens {metric(row.total_tokens)}</span></div>)}</article>
            <article className={styles.panel}><h2>Queue / Worker</h2><dl className={styles.definitionList}>{Object.entries(data.queue).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{number(value)}</dd></div>)}</dl><p className={styles.note}>Worker 최근 성공: {data.runtime.worker_last_success_at ? new Date(data.runtime.worker_last_success_at).toLocaleString('ko-KR') : '없음'}</p></article>
          </section>

          <section className={styles.panel}><h2>공식 Source Freshness</h2><div className={styles.tableWrap}><table><thead><tr><th>Source</th><th>최신 기준일</th><th>Current</th><th>Stale</th><th>Stale 비율</th><th>Refresh</th></tr></thead><tbody>{data.source_freshness.map((row) => <tr key={row.source}><td>{row.source}</td><td>{row.latest_source_date || 'UNKNOWN'}</td><td>{number(row.current_evidence)}</td><td>{number(row.stale_evidence)}</td><td>{percent(row.stale_ratio)}</td><td>{row.refresh_needed ? '필요' : '정상'}</td></tr>)}</tbody></table></div></section>
          <section className={styles.panel}><h2>검색 성능</h2><p className={styles.note}>{data.search_performance.status}: {data.search_performance.reason}</p></section>
          <section className={styles.panel}><h2>Semantic Pilot</h2><div className={styles.providerRow}>
            <strong>{data.semantic_pilot?.model || 'NOT_CONFIGURED'}</strong>
            <span>문서 {number(data.semantic_pilot?.feature_documents)}</span>
            <span>Embedding {number(data.semantic_pilot?.embedded_documents)} · {metric(data.semantic_pilot?.dimensions, 'D')}</span>
            <span>Retrieval {data.semantic_pilot?.retrieval_enabled ? 'ON' : 'OFF'} / Injection {data.semantic_pilot?.candidate_injection_enabled ? 'ON' : 'OFF'}</span>
          </div></section>
        </> : null}
      </div>
    </main>
  )
}

const CoverageTable = ({ rows, labelKey }) => <div className={styles.tableWrap}><table><thead><tr><th>{labelKey}</th><th>Place</th><th>Evidence Place</th><th>Active Place</th><th>Coverage</th><th>Stale</th><th>상태</th></tr></thead><tbody>{rows.map((row) => <tr key={row[labelKey]}><td>{row[labelKey]}</td><td>{number(row.places)}</td><td>{number(row.evidence_places)}</td><td>{number(row.active_evidence_places)}</td><td>{percent(row.place_coverage)}</td><td>{percent(row.stale_ratio)}</td><td>{row.readiness}</td></tr>)}</tbody></table></div>

export default AdminOperationsView
