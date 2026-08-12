import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import {
  approvePlaceReport,
  fetchAdminPlaceReportDetail,
  fetchAdminPlaceReports,
  rejectPlaceReport,
} from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'

import styles from './AdminPlaceReportsView.module.css'

const STATUS_OPTIONS = [
  { value: '', label: '전체' },
  { value: 'pending', label: '검토 대기' },
  { value: 'approved', label: '승인' },
  { value: 'rejected', label: '반려' },
]

const TYPE_OPTIONS = [
  { value: '', label: '전체 유형' },
  { value: 'new_place', label: '장소 추가' },
  { value: 'edit_place', label: '장소 수정' },
  { value: 'tag_suggestion', label: '태그 제안' },
  { value: 'wrong_info', label: '오류 제보' },
]

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

const AdminPlaceReportsView = () => {
  const navigate = useNavigate()

  const [reports, setReports] = useState([])
  const [selectedReport, setSelectedReport] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [adminNote, setAdminNote] = useState('')
  const [message, setMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isDetailLoading, setIsDetailLoading] = useState(false)
  const [isReviewing, setIsReviewing] = useState(false)
  const [page, setPage] = useState(1)
  const [meta, setMeta] = useState({
    page: 1,
    pageSize: 10,
    totalPages: 1,
    count: 0,
  })

  const fetchReports = useCallback(async () => {
    try {
      setIsLoading(true)
      const response = await fetchAdminPlaceReports({
        status: statusFilter,
        reportType: typeFilter,
        page,
        pageSize: 10,
      })
      setReports(response.results || [])
      setMeta({
        count: response.count || 0,
        page: response.page || page,
        pageSize: response.page_size || 10,
        totalPages: response.total_pages || 1,
      })
    } catch (error) {
      setReports([])
      setMessage('관리자 제보 목록을 불러오지 못했습니다.')
    } finally {
      setIsLoading(false)
    }
  }, [statusFilter, typeFilter, page])

  useEffect(() => {
    if (!useAuthStore.getState().user?.is_staff) {
      navigate('/')
      return
    }

    fetchReports()
  }, [fetchReports, navigate])

  const fetchDetail = async (reportId) => {
    try {
      setIsDetailLoading(true)
      const detail = await fetchAdminPlaceReportDetail(reportId)
      setSelectedReport(detail)
      setAdminNote(detail.admin_note || '')
    } catch (error) {
      setMessage('제보 상세를 불러오지 못했습니다.')
    } finally {
      setIsDetailLoading(false)
    }
  }

  const applyStatusFilter = (value) => {
    setStatusFilter(value)
    setPage(1)
    setSelectedReport(null)
  }

  const applyTypeFilter = (value) => {
    setTypeFilter(value)
    setPage(1)
    setSelectedReport(null)
  }

  const movePage = (direction) => {
    const nextPage = page + direction
    if (nextPage < 1 || nextPage > meta.totalPages) return

    setPage(nextPage)
  }

  const reviewReport = async (action) => {
    if (!selectedReport) return

    try {
      setIsReviewing(true)
      const payload = { admin_note: adminNote }
      const response = action === 'approve'
        ? await approvePlaceReport(selectedReport.id, payload)
        : await rejectPlaceReport(selectedReport.id, payload)

      setSelectedReport(response.report)
      setMessage(action === 'approve' ? '제보를 승인했습니다.' : '제보를 반려했습니다.')
      await fetchReports()
    } catch (error) {
      setMessage(error.response?.data?.detail || '제보 처리에 실패했습니다.')
    } finally {
      setIsReviewing(false)
    }
  }

  const isSelectedReportPending = selectedReport?.status === 'pending'

  return (
    <main className={styles.adminReportPage}>
      <section className={styles.adminReportContainer}>
        <header className={styles.pageTitle}>
          <div>
            <p className={styles.eyebrow}>ADMIN</p>
            <h1>장소 제보 검증</h1>
            <p>사용자 제보를 검토하고 승인 또는 반려할 수 있습니다.</p>
          </div>

          <nav className={styles.adminTabs}>
            <Link to="/admin/reports" className={styles.adminTab}>신고 내역</Link>
            <Link to="/admin/place-reports" className={styles.adminTab}>장소 제보</Link>
            <Link to="/admin/users" className={styles.adminTab}>유저 관리</Link>
            <Link to="/admin/inquiries" className={styles.adminTab}>문의 관리</Link>
          </nav>
        </header>

        <section className={`${styles.panel} ${styles.filterPanel}`}>
          <select
            value={statusFilter}
            onChange={(event) => applyStatusFilter(event.target.value)}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <select
            value={typeFilter}
            onChange={(event) => applyTypeFilter(event.target.value)}
          >
            {TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </section>

        <div className={styles.workspace}>
          <section className={styles.panel}>
            <h2>제보 목록</h2>
            {isLoading ? (
              <p className={styles.empty}>제보 목록을 불러오는 중입니다.</p>
            ) : reports.length ? (
              <div className={styles.reportList}>
                {reports.map((report) => (
                  <button
                    key={report.id}
                    type="button"
                    className={`${styles.reportRow}${selectedReport?.id === report.id ? ` ${styles.active}` : ''}`}
                    onClick={() => fetchDetail(report.id)}
                  >
                    <span className={`${styles.statusBadge} ${styles[report.status] || ''}`}>
                      {report.status_label || report.status}
                    </span>
                    <strong>{report.report_type_label}</strong>
                    <span>{report.place_name || report.suggested_name || '장소명 없음'}</span>
                    <time>{formatDate(report.created_at)}</time>
                  </button>
                ))}
              </div>
            ) : (
              <p className={styles.empty}>표시할 제보가 없습니다.</p>
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

          <section className={`${styles.panel} ${styles.detailPanel}`}>
            <h2>상세 검토</h2>
            {isDetailLoading ? (
              <p className={styles.empty}>상세를 불러오는 중입니다.</p>
            ) : selectedReport ? (
              <div className={styles.detailBody}>
                <div className={styles.detailGrid}>
                  <span>제보자</span><strong>{selectedReport.user_username}</strong>
                  <span>상태</span><strong>{selectedReport.status_label}</strong>
                  <span>제보 유형</span><strong>{selectedReport.report_type_label}</strong>
                  <span>장소</span>
                  <strong>
                    {selectedReport.place_name || selectedReport.suggested_name || '장소명 없음'}
                  </strong>
                  <span>주소</span><strong>{selectedReport.suggested_address || '-'}</strong>
                  <span>좌표</span>
                  <strong>
                    {selectedReport.suggested_lat || '-'}, {selectedReport.suggested_lng || '-'}
                  </strong>
                </div>

                {selectedReport.suggested_tags?.length ? (
                  <div className={styles.chipRow}>
                    {selectedReport.suggested_tags.map((tag) => (
                      <span key={tag} className={styles.chip}>{tag}</span>
                    ))}
                  </div>
                ) : null}

                <div className={styles.reportBlock}>
                  <strong>설명</strong>
                  <p>{selectedReport.description || '설명 없음'}</p>
                </div>

                {selectedReport.images?.length ? (
                  <div className={styles.imageGrid}>
                    {selectedReport.images.map((image) => (
                      <a
                        key={image.id}
                        href={image.image_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <img src={image.image_url} alt={image.original_name} />
                      </a>
                    ))}
                  </div>
                ) : null}

                <label>
                  <span>관리자 메모</span>
                  <textarea
                    value={adminNote}
                    onChange={(event) => setAdminNote(event.target.value)}
                    rows={4}
                    placeholder="승인/반려 사유 또는 처리 메모"
                  />
                </label>

                {message ? <p className={styles.statusMessage}>{message}</p> : null}

                {!isSelectedReportPending ? (
                  <p className={styles.statusMessage}>이미 처리된 제보입니다.</p>
                ) : (
                  <div className={styles.reviewActions}>
                    <button
                      type="button"
                      className={styles.approve}
                      disabled={isReviewing}
                      onClick={() => reviewReport('approve')}
                    >
                      승인
                    </button>
                    <button
                      type="button"
                      className={styles.reject}
                      disabled={isReviewing}
                      onClick={() => reviewReport('reject')}
                    >
                      반려
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <p className={styles.empty}>검토할 제보를 선택해 주세요.</p>
            )}
          </section>
        </div>
      </section>
    </main>
  )
}

export default AdminPlaceReportsView
