import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { fetchMyPlaceReports } from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'

import styles from './MyPlaceReportsView.module.css'

const STATUS_LABELS = {
  pending: '검토 대기',
  approved: '승인',
  rejected: '반려',
}

const getReportContributionMessage = (report) => report.processing_result || '처리 결과 확인 중'

const formatDate = (value) => {
  if (!value) return ''
  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const MyPlaceReportsView = () => {
  const navigate = useNavigate()

  const [reports, setReports] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [page, setPage] = useState(1)
  const [meta, setMeta] = useState({
    count: 0,
    page: 1,
    pageSize: 5,
    totalPages: 1,
  })

  const fetchReports = useCallback(async (targetPage) => {
    try {
      setIsLoading(true)
      setMessage('')
      const response = await fetchMyPlaceReports({
        page: targetPage,
        pageSize: 5,
      })
      const results = response.results || []
      setReports(results)
      setMeta({
        count: response.count || 0,
        page: response.page || targetPage,
        pageSize: response.page_size || 5,
        totalPages: response.total_pages || 1,
      })

      if (!results.length) {
        setMessage('아직 접수한 장소 제보가 없습니다.')
      }
    } catch (error) {
      setReports([])
      setMessage('내 제보 현황을 불러오지 못했습니다.')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!useAuthStore.getState().isLoggedIn) {
      navigate('/login')
      return
    }

    fetchReports(page)
  }, [fetchReports, navigate, page])

  const movePage = (direction) => {
    const nextPage = page + direction
    if (nextPage < 1 || nextPage > meta.totalPages) return

    setPage(nextPage)
  }

  return (
    <main className={styles.reportsPage}>
      <section className={styles.reportsContainer}>
        <header className={styles.pageTitle}>
          <Link to="/mypage" className={styles.backLink}>마이페이지로 돌아가기</Link>
          <p className={styles.eyebrow}>MY REPORTS</p>
          <h1>내 제보 현황</h1>
          <p>접수한 장소 정보 제보의 검토 상태를 확인할 수 있습니다.</p>
        </header>

        <section className={styles.panel}>
          <div className={styles.sectionHeadingRow}>
            <div>
              <h2>제보 목록</h2>
              <p>관리자 검토 전에는 데이터에 반영되지 않습니다.</p>
            </div>
            <Link to="/place-report" className={styles.primaryLink}>새 제보 작성</Link>
          </div>

          {isLoading ? (
            <p className={styles.empty}>제보 목록을 불러오는 중입니다.</p>
          ) : reports.length ? (
            <div className={styles.reportList}>
              {reports.map((report) => (
                <article key={report.id} className={styles.reportCard}>
                  <div className={styles.reportTop}>
                    <span className={`${styles.statusBadge} ${styles[report.status] || ''}`}>
                      {report.status_label || '처리 상태 확인 중'}
                    </span>
                    <time>{formatDate(report.created_at)}</time>
                  </div>
                  <strong>{report.report_type_label}</strong>
                  <p>{report.place_name || report.suggested_name || '장소명 없음'}</p>
                  <p className={`${styles.contributionNote} ${styles[report.status] || ''}`}>
                    {getReportContributionMessage(report)}
                  </p>
                  {report.suggested_tags?.length ? (
                    <div className={styles.chipRow}>
                      {report.suggested_tags.map((tag) => (
                        <span key={tag} className={styles.chip}>{tag}</span>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <p className={styles.empty}>{message}</p>
          )}

          <div className={styles.pager}>
            <button type="button" disabled={page <= 1} onClick={() => movePage(-1)}>
              이전
            </button>
            <span>{meta.page} / {meta.totalPages}</span>
            <button
              type="button"
              disabled={page >= meta.totalPages}
              onClick={() => movePage(1)}
            >
              다음
            </button>
          </div>
        </section>
      </section>
    </main>
  )
}

export default MyPlaceReportsView
