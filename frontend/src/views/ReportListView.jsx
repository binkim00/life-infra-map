import { Fragment, useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { createUserNotification, getReports, processReport } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

import styles from './ReportListView.module.css'

const PENALTY_OPTIONS = [
  ['warning', '경고만'],
  ['suspend_3_days', '3일 정지'],
  ['suspend_7_days', '7일 정지'],
  ['suspend_30_days', '30일 정지'],
  ['suspend_1_year', '1년 정지'],
  ['permanent_ban', '영구밴'],
]

const REPORT_STATUS_OPTIONS = [
  { value: 'all', label: '전체' },
  { value: 'pending', label: '대기' },
  { value: 'passed', label: '패스' },
  { value: 'penalized', label: '조치 완료' },
]

const formatTargetType = (type) => {
  if (type === 'deleted') return '삭제됨'
  return type === 'post' ? '게시글' : '댓글'
}

const formatStatus = (status) => {
  if (status === 'passed') return '패스'
  if (status === 'penalized') return '조치 완료'
  return '대기'
}

const formatDateTime = (value) => {
  if (!value) return '-'

  return new Date(value).toLocaleString('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const getUserLabel = (nickname, username, id) => {
  const displayName = nickname || username || `#${id}`
  return username && nickname ? `${displayName} (${username})` : displayName
}

const isReportProcessed = (report) => report?.status && report.status !== 'pending'

const ReportListView = () => {
  const navigate = useNavigate()

  const [reports, setReports] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [memoByReport, setMemoByReport] = useState({})
  const [reporterMessageByReport, setReporterMessageByReport] = useState({})
  const [reportedUserMessageByReport, setReportedUserMessageByReport] = useState({})
  const [penaltyByReport, setPenaltyByReport] = useState({})
  const [openedReportIds, setOpenedReportIds] = useState(() => new Set())
  const [statusFilter, setStatusFilter] = useState('all')

  const fetchReports = useCallback(async (nextStatusFilter) => {
    if (!useAuthStore.getState().isLoggedIn) {
      navigate('/login')
      return
    }

    try {
      setIsLoading(true)
      setErrorMessage('')

      const response = await getReports({ status: nextStatusFilter })
      const reportList = response.data
      setReports(reportList)

      // 입력 중이던 메모/메시지는 유지하고, 없는 항목만 기본값으로 채웁니다.
      setMemoByReport((current) => Object.fromEntries(
        reportList.map((report) => [
          report.id,
          current[report.id] ?? report.admin_memo ?? '',
        ]),
      ))
      setReporterMessageByReport((current) => Object.fromEntries(
        reportList.map((report) => [report.id, current[report.id] ?? '']),
      ))
      setReportedUserMessageByReport((current) => Object.fromEntries(
        reportList.map((report) => [report.id, current[report.id] ?? '']),
      ))
      setPenaltyByReport((current) => Object.fromEntries(
        reportList.map((report) => [report.id, current[report.id] ?? 'warning']),
      ))
    } catch (error) {
      console.error(error)

      if (error.response?.status === 403) {
        setErrorMessage('관리자만 신고 내역을 확인할 수 있습니다.')
        return
      }

      setErrorMessage('신고 내역을 불러오지 못했습니다.')
    } finally {
      setIsLoading(false)
    }
  }, [navigate])

  useEffect(() => {
    fetchReports(statusFilter)
  }, [fetchReports, statusFilter])

  const isReportOpen = (reportId) => openedReportIds.has(reportId)

  const toggleReport = (reportId) => {
    setOpenedReportIds((current) => {
      const next = new Set(current)

      if (next.has(reportId)) {
        next.delete(reportId)
      } else {
        next.add(reportId)
      }

      return next
    })
  }

  const handleProcess = async (report, action) => {
    try {
      const response = await processReport(report.id, {
        action,
        admin_memo: memoByReport[report.id] || '',
        penalty_type: penaltyByReport[report.id] || 'warning',
        penalty_reason: memoByReport[report.id] || report.reason,
      })

      const updatedReport = response.data
      setReports((current) => current.map((item) => (
        item.id === report.id ? { ...item, ...updatedReport } : item
      )))
      setMemoByReport((current) => ({
        ...current,
        [report.id]: updatedReport.admin_memo || '',
      }))
    } catch (error) {
      console.error(error)
      alert('신고 처리에 실패했습니다.')
    }
  }

  const sendReportMessage = async (userId, message) => {
    if (!userId) {
      alert('메시지를 보낼 대상이 없습니다.')
      return
    }

    if (!message?.trim()) {
      alert('메시지를 입력해주세요.')
      return
    }

    try {
      await createUserNotification(userId, {
        title: '신고 처리 안내',
        message,
      })

      alert('메시지를 보냈습니다.')
    } catch (error) {
      console.error(error)
      alert('메시지 전송에 실패했습니다.')
    }
  }

  return (
    <main className={styles.adminBoardPage}>
      <section className={styles.adminBoardContainer}>
        <header className={styles.adminBoardHeader}>
          <div>
            <p className={styles.eyebrow}>COMMUNITY ADMIN</p>
            <h1>신고 내역</h1>
            <p className={styles.headerDescription}>
              자유게시판에서 접수된 게시글·댓글 신고를 확인하고 처리합니다.
            </p>
          </div>

          <nav className={styles.adminTabs}>
            <Link to="/admin/reports" className={styles.adminTab}>신고 내역</Link>
            <Link to="/admin/place-reports" className={styles.adminTab}>장소 제보</Link>
            <Link to="/admin/users" className={styles.adminTab}>유저 관리</Link>
            <Link to="/admin/inquiries" className={styles.adminTab}>문의 관리</Link>
          </nav>
        </header>

        <section className={styles.reportToolbar}>
          <label>
            <span>처리 상태</span>
            <select
              value={statusFilter}
              disabled={isLoading}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              {REPORT_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>

          <button
            type="button"
            disabled={isLoading}
            onClick={() => fetchReports(statusFilter)}
          >
            새로고침
          </button>
        </section>

        {isLoading ? (
          <p className={styles.statusText}>신고 내역을 불러오는 중입니다.</p>
        ) : errorMessage ? (
          <p className={styles.errorText}>{errorMessage}</p>
        ) : (
          <section className={styles.adminTableWrap}>
            <table className={`${styles.adminTable} ${styles.reportTable}`}>
              <colgroup>
                <col className={styles.colNumber} />
                <col className={styles.colType} />
                <col className={styles.colTitle} />
                <col className={styles.colUser} />
                <col className={styles.colUser} />
                <col className={styles.colDate} />
                <col className={styles.colStatus} />
                <col className={styles.colAction} />
              </colgroup>

              <thead>
                <tr>
                  <th>번호</th>
                  <th>대상</th>
                  <th>신고 내용</th>
                  <th>신고자</th>
                  <th>신고당한 유저</th>
                  <th>접수일</th>
                  <th>상태</th>
                  <th>관리</th>
                </tr>
              </thead>

              <tbody>
                {reports.map((report) => (
                  <Fragment key={report.id}>
                    <tr className={isReportOpen(report.id) ? styles.opened : undefined}>
                      <td className={styles.numberCell}>{report.id}</td>
                      <td>
                        <span className={`${styles.categoryLabel} ${styles.reportTarget}`}>
                          {formatTargetType(report.target_type)}
                        </span>
                      </td>
                      <td className={styles.titleCell}>
                        <button
                          type="button"
                          className={styles.titleButton}
                          onClick={() => toggleReport(report.id)}
                        >
                          <span className={styles.titleText}>
                            {report.post_title || '삭제되었거나 제목 없음'}
                          </span>
                          <span className={styles.reasonPreview}>{report.reason}</span>
                        </button>
                      </td>
                      <td>
                        <Link to={`/admin/users/${report.reporter}`} className={styles.userLink}>
                          {getUserLabel(
                            report.reporter_nickname,
                            report.reporter_username,
                            report.reporter,
                          )}
                        </Link>
                      </td>
                      <td>
                        {report.reported_user_id ? (
                          <Link
                            to={`/admin/users/${report.reported_user_id}`}
                            className={`${styles.userLink} ${styles.danger}`}
                          >
                            {getUserLabel(
                              report.reported_nickname,
                              report.reported_username,
                              report.reported_user_id,
                            )}
                          </Link>
                        ) : (
                          <span className={styles.mutedText}>-</span>
                        )}
                      </td>
                      <td>{formatDateTime(report.created_at)}</td>
                      <td>
                        <span className={`${styles.statusBadge} ${styles[report.status || 'pending']}`}>
                          {formatStatus(report.status)}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className={styles.rowAction}
                          onClick={() => toggleReport(report.id)}
                        >
                          {isReportOpen(report.id)
                            ? '닫기'
                            : isReportProcessed(report) ? '보기' : '처리'}
                        </button>
                      </td>
                    </tr>

                    {isReportOpen(report.id) ? (
                      <tr className={styles.detailRow}>
                        <td colSpan={8}>
                          <div className={styles.detailPanel}>
                            <div className={styles.detailGrid}>
                              <section className={styles.detailBox}>
                                <strong>신고 사유</strong>
                                <p>{report.reason}</p>
                              </section>

                              <section className={styles.detailBox}>
                                <strong>대상 내용</strong>
                                <p>{report.target_content || '대상 내용이 없습니다.'}</p>
                              </section>
                            </div>

                            {report.post_id ? (
                              <Link
                                to={`/boards/free/${report.post_id}`}
                                className={styles.detailLink}
                              >
                                원문 보기
                              </Link>
                            ) : null}

                            {isReportProcessed(report) ? (
                              <section className={`${styles.processPanel} ${styles.processPanelReadonly}`}>
                                <h3>처리 내역</h3>
                                <dl className={styles.processSummaryList}>
                                  <div>
                                    <dt>상태</dt>
                                    <dd>{formatStatus(report.status)}</dd>
                                  </div>
                                  <div>
                                    <dt>처리자</dt>
                                    <dd>{report.processed_by_username || '-'}</dd>
                                  </div>
                                  <div>
                                    <dt>처리일</dt>
                                    <dd>{formatDateTime(report.processed_at)}</dd>
                                  </div>
                                </dl>
                                {report.admin_memo ? (
                                  <p className={styles.processMemo}>{report.admin_memo}</p>
                                ) : null}
                              </section>
                            ) : (
                              <section className={styles.processPanel}>
                                <h3>신고 처리</h3>
                                <textarea
                                  value={memoByReport[report.id] || ''}
                                  onChange={(event) => setMemoByReport((current) => ({
                                    ...current,
                                    [report.id]: event.target.value,
                                  }))}
                                  rows={3}
                                  placeholder="관리자 메모 또는 조치 사유"
                                />

                                <div className={styles.processControls}>
                                  <select
                                    value={penaltyByReport[report.id] || 'warning'}
                                    onChange={(event) => setPenaltyByReport((current) => ({
                                      ...current,
                                      [report.id]: event.target.value,
                                    }))}
                                  >
                                    {PENALTY_OPTIONS.map(([value, label]) => (
                                      <option key={value} value={value}>{label}</option>
                                    ))}
                                  </select>

                                  <button
                                    type="button"
                                    className={styles.passButton}
                                    onClick={() => handleProcess(report, 'passed')}
                                  >
                                    패스
                                  </button>

                                  <button
                                    type="button"
                                    className={styles.penaltyButton}
                                    onClick={() => handleProcess(report, 'penalized')}
                                  >
                                    패널티 조치
                                  </button>
                                </div>
                              </section>
                            )}

                            <section className={styles.messagePanel}>
                              <h3>관리자 메시지</h3>

                              <div className={styles.messageRow}>
                                <input
                                  value={reporterMessageByReport[report.id] || ''}
                                  onChange={(event) => setReporterMessageByReport((current) => ({
                                    ...current,
                                    [report.id]: event.target.value,
                                  }))}
                                  type="text"
                                  placeholder="신고자에게 보낼 메시지"
                                />
                                <button
                                  type="button"
                                  onClick={async () => {
                                    await sendReportMessage(
                                      report.reporter,
                                      reporterMessageByReport[report.id],
                                    )
                                    setReporterMessageByReport((current) => ({
                                      ...current,
                                      [report.id]: '',
                                    }))
                                  }}
                                >
                                  신고자에게 보내기
                                </button>
                              </div>

                              <div className={styles.messageRow}>
                                <input
                                  value={reportedUserMessageByReport[report.id] || ''}
                                  onChange={(event) => setReportedUserMessageByReport((current) => ({
                                    ...current,
                                    [report.id]: event.target.value,
                                  }))}
                                  type="text"
                                  placeholder="신고당한 유저에게 보낼 메시지"
                                />
                                <button
                                  type="button"
                                  onClick={async () => {
                                    await sendReportMessage(
                                      report.reported_user_id,
                                      reportedUserMessageByReport[report.id],
                                    )
                                    setReportedUserMessageByReport((current) => ({
                                      ...current,
                                      [report.id]: '',
                                    }))
                                  }}
                                >
                                  신고당한 유저에게 보내기
                                </button>
                              </div>
                            </section>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>

            {reports.length === 0 ? (
              <p className={styles.emptyText}>
                {statusFilter === 'pending'
                  ? '접수된 신고 내역이 없습니다.'
                  : '표시할 신고 내역이 없습니다.'}
              </p>
            ) : null}
          </section>
        )}
      </section>
    </main>
  )
}

export default ReportListView
