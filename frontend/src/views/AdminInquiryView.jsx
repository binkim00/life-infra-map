import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { getAdminInquiries, updateAdminInquiry } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

import styles from './AdminInquiryView.module.css'

const getAuthorKey = (inquiry) => String(
  inquiry.author || inquiry.author_username || inquiry.author_nickname || `guest-${inquiry.id}`,
)

const getAuthorLabel = (inquiry) => {
  const nickname = inquiry.author_nickname
  const username = inquiry.author_username

  if (nickname && username) return `${nickname} (${username})`
  return nickname || username || '-'
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

const formatStatus = (status) => {
  if (status === 'answered') return '답변 완료'
  if (status === 'closed') return '종료'
  return '대기'
}

const getStatusClass = (status) => {
  if (status === 'answered') return 'answered'
  if (status === 'closed') return 'closed'
  return 'pending'
}

const getGroupStatusText = (group) => {
  if (group.pendingCount > 0) return `대기 ${group.pendingCount}건`
  if (group.closedCount === group.totalCount) return '전체 종료'
  return '전체 답변 완료'
}

const getGroupStatusClass = (group) => {
  if (group.pendingCount > 0) return 'pending'
  if (group.closedCount === group.totalCount) return 'closed'
  return 'answered'
}

const AdminInquiryView = () => {
  const navigate = useNavigate()

  const [inquiries, setInquiries] = useState([])
  const [replies, setReplies] = useState({})
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [openedUserKeys, setOpenedUserKeys] = useState(() => new Set())

  const fetchInquiries = useCallback(async () => {
    const { isLoggedIn, user, fetchMe } = useAuthStore.getState()

    if (isLoggedIn && !user?.is_staff) {
      await fetchMe()
    }

    if (!useAuthStore.getState().user?.is_staff) {
      navigate('/')
      return
    }

    try {
      setIsLoading(true)
      setErrorMessage('')

      const response = await getAdminInquiries()
      setInquiries(response.data)
      setReplies(Object.fromEntries(
        response.data.map((item) => [item.id, item.admin_reply || '']),
      ))
    } catch (error) {
      console.error(error)
      setErrorMessage('문의 목록을 불러오지 못했습니다.')
    } finally {
      setIsLoading(false)
    }
  }, [navigate])

  useEffect(() => {
    fetchInquiries()
  }, [fetchInquiries])

  const submitReply = async (inquiry) => {
    if (!replies[inquiry.id]?.trim()) {
      alert('답변 내용을 입력해주세요.')
      return
    }

    try {
      const response = await updateAdminInquiry(inquiry.id, {
        status: 'answered',
        admin_reply: replies[inquiry.id],
      })

      setInquiries((current) => current.map((item) => (
        item.id === inquiry.id ? { ...item, ...response.data } : item
      )))
    } catch (error) {
      console.error(error)
      alert('답변 저장에 실패했습니다.')
    }
  }

  const inquiryGroups = useMemo(() => {
    const groupMap = new Map()

    inquiries.forEach((inquiry) => {
      const key = getAuthorKey(inquiry)

      if (!groupMap.has(key)) {
        groupMap.set(key, {
          key,
          authorLabel: getAuthorLabel(inquiry),
          inquiries: [],
        })
      }

      groupMap.get(key).inquiries.push(inquiry)
    })

    return Array.from(groupMap.values())
      .map((group) => {
        const sortedInquiries = [...group.inquiries].sort((a, b) => (
          new Date(b.created_at || 0) - new Date(a.created_at || 0)
        ))

        return {
          ...group,
          inquiries: sortedInquiries,
          latestInquiry: sortedInquiries[0],
          pendingCount: sortedInquiries.filter((item) => item.status === 'pending').length,
          answeredCount: sortedInquiries.filter((item) => item.status === 'answered').length,
          closedCount: sortedInquiries.filter((item) => item.status === 'closed').length,
          totalCount: sortedInquiries.length,
        }
      })
      .sort((a, b) => (
        new Date(b.latestInquiry?.created_at || 0) - new Date(a.latestInquiry?.created_at || 0)
      ))
  }, [inquiries])

  const toggleUserGroup = (userKey) => {
    setOpenedUserKeys((current) => {
      const next = new Set(current)

      if (next.has(userKey)) {
        next.delete(userKey)
      } else {
        next.add(userKey)
      }

      return next
    })
  }

  const isUserGroupOpen = (userKey) => openedUserKeys.has(userKey)

  return (
    <main className={styles.adminBoardPage}>
      <section className={styles.adminBoardContainer}>
        <header className={styles.adminBoardHeader}>
          <div>
            <p className={styles.eyebrow}>COMMUNITY ADMIN</p>
            <h1>문의 관리</h1>
            <p className={styles.headerDescription}>
              같은 사용자의 문의를 하나의 칸에 묶어서 확인하고 답변을 관리합니다.
            </p>
          </div>

          <nav className={styles.adminTabs}>
            <Link to="/admin/reports" className={styles.adminTab}>신고 내역</Link>
            <Link to="/admin/place-reports" className={styles.adminTab}>장소 제보</Link>
            <Link to="/admin/users" className={styles.adminTab}>유저 관리</Link>
            <Link to="/admin/inquiries" className={styles.adminTab}>문의 관리</Link>
          </nav>
        </header>

        {isLoading ? (
          <p className={styles.statusText}>문의 목록을 불러오는 중입니다.</p>
        ) : errorMessage ? (
          <p className={styles.errorText}>{errorMessage}</p>
        ) : (
          <section className={styles.adminTableWrap}>
            <table className={`${styles.adminTable} ${styles.inquiryTable}`}>
              <colgroup>
                <col className={styles.colNumber} />
                <col className={styles.colStatus} />
                <col className={styles.colUser} />
                <col className={styles.colTitle} />
                <col className={styles.colCount} />
                <col className={styles.colDate} />
                <col className={styles.colAction} />
              </colgroup>

              <thead>
                <tr>
                  <th>번호</th>
                  <th>상태</th>
                  <th>사용자</th>
                  <th>최근 문의</th>
                  <th>문의 수</th>
                  <th>최근 문의일</th>
                  <th>관리</th>
                </tr>
              </thead>

              <tbody>
                {inquiryGroups.map((group, index) => (
                  <Fragment key={group.key}>
                    <tr className={isUserGroupOpen(group.key) ? styles.opened : undefined}>
                      <td className={styles.numberCell}>{index + 1}</td>
                      <td>
                        <span className={`${styles.statusBadge} ${styles[getGroupStatusClass(group)]}`}>
                          {getGroupStatusText(group)}
                        </span>
                      </td>
                      <td className={styles.authorCell}>{group.authorLabel}</td>
                      <td className={styles.titleCell}>
                        <button
                          type="button"
                          className={styles.titleButton}
                          onClick={() => toggleUserGroup(group.key)}
                        >
                          <span className={styles.titleText}>
                            {group.latestInquiry?.title || '-'}
                          </span>
                          <span className={styles.contentPreview}>
                            {group.latestInquiry?.content || '-'}
                          </span>
                        </button>
                      </td>
                      <td>
                        <div className={styles.countStack}>
                          <span className={styles.countChip}>전체 {group.totalCount}</span>
                          {group.pendingCount ? (
                            <span className={`${styles.countChip} ${styles.pendingCount}`}>
                              대기 {group.pendingCount}
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td>{formatDateTime(group.latestInquiry?.created_at)}</td>
                      <td>
                        <button
                          type="button"
                          className={styles.rowAction}
                          onClick={() => toggleUserGroup(group.key)}
                        >
                          {isUserGroupOpen(group.key) ? '닫기' : '확인'}
                        </button>
                      </td>
                    </tr>

                    {isUserGroupOpen(group.key) ? (
                      <tr className={styles.detailRow}>
                        <td colSpan={7}>
                          <div className={styles.detailPanel}>
                            <section className={styles.userSummaryBox}>
                              <div>
                                <strong>{group.authorLabel}</strong>
                                <p>
                                  {`전체 문의 ${group.totalCount}건 · 대기 ${group.pendingCount}건 · 답변 완료 ${group.answeredCount}건 · 종료 ${group.closedCount}건`}
                                </p>
                              </div>
                            </section>

                            {group.inquiries.map((inquiry) => (
                              <article key={inquiry.id} className={styles.inquiryCard}>
                                <header className={styles.inquiryCardHeader}>
                                  <div className={styles.inquiryTitleArea}>
                                    <span className={`${styles.statusBadge} ${styles[getStatusClass(inquiry.status)]}`}>
                                      {formatStatus(inquiry.status)}
                                    </span>
                                    <strong>#{inquiry.id} {inquiry.title}</strong>
                                  </div>
                                  <span className={styles.inquiryDate}>
                                    {formatDateTime(inquiry.created_at)}
                                  </span>
                                </header>

                                <section className={styles.detailBox}>
                                  <strong>문의 내용</strong>
                                  <p>{inquiry.content}</p>
                                </section>

                                {inquiry.status === 'answered' || inquiry.status === 'closed' ? (
                                  <section className={styles.replyBox}>
                                    <strong>관리자 답변</strong>
                                    <p>{inquiry.admin_reply || '등록된 답변이 없습니다.'}</p>
                                  </section>
                                ) : (
                                  <section className={styles.replyFormBox}>
                                    <h3>답변 작성</h3>
                                    <textarea
                                      value={replies[inquiry.id] || ''}
                                      onChange={(event) => setReplies((current) => ({
                                        ...current,
                                        [inquiry.id]: event.target.value,
                                      }))}
                                      rows={4}
                                      placeholder="관리자 답변"
                                    />
                                    <button type="button" onClick={() => submitReply(inquiry)}>
                                      답변 저장
                                    </button>
                                  </section>
                                )}
                              </article>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>

            {inquiries.length === 0 ? (
              <p className={styles.emptyText}>등록된 문의가 없습니다.</p>
            ) : null}
          </section>
        )}
      </section>
    </main>
  )
}

export default AdminInquiryView
