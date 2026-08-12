import { Fragment, useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { createUserNotification, createUserPenalty, getAdminUsers } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

import styles from './AdminUserView.module.css'

const PENALTIES = [
  ['suspend_3_days', '3일 활동정지'],
  ['suspend_7_days', '7일 활동정지'],
  ['suspend_30_days', '30일 활동정지'],
  ['suspend_1_year', '1년 사용정지'],
  ['permanent_ban', '영구밴'],
]

const PENALTY_LABELS = {
  warning: '경고',
  suspend_3_days: '3일 정지',
  suspend_7_days: '7일 정지',
  suspend_30_days: '30일 정지',
  suspend_1_year: '1년 정지',
  permanent_ban: '영구밴',
}

const formatUserName = (user) => {
  if (!user) return '-'
  const displayName = user.nickname || user.username || `#${user.id}`
  return user.nickname ? `${displayName} (${user.username})` : displayName
}

const formatPenalty = (penalty) => {
  if (!penalty) return '정상'

  return PENALTY_LABELS[penalty.penalty_type] || penalty.penalty_type
}

const AdminUserView = () => {
  const navigate = useNavigate()

  const [users, setUsers] = useState([])
  const [reasonByUser, setReasonByUser] = useState({})
  const [messageByUser, setMessageByUser] = useState({})
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [openedUserIds, setOpenedUserIds] = useState(() => new Set())

  const fetchUsers = useCallback(async () => {
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

      const response = await getAdminUsers()
      setUsers(response.data)
    } catch (error) {
      console.error(error)
      setErrorMessage('유저 목록을 불러오지 못했습니다.')
    } finally {
      setIsLoading(false)
    }
  }, [navigate])

  useEffect(() => {
    fetchUsers()
  }, [fetchUsers])

  const isUserOpen = (userId) => openedUserIds.has(userId)

  const toggleUser = (userId) => {
    setOpenedUserIds((current) => {
      const next = new Set(current)

      if (next.has(userId)) {
        next.delete(userId)
      } else {
        next.add(userId)
      }

      return next
    })
  }

  const applyPenalty = async (user, penaltyType) => {
    const reason = reasonByUser[user.id]?.trim()
    if (!reason) {
      alert('조치 사유를 입력해주세요.')
      return
    }

    try {
      await createUserPenalty(user.id, { penalty_type: penaltyType, reason })
      setReasonByUser((current) => ({ ...current, [user.id]: '' }))
      await fetchUsers()
    } catch (error) {
      console.error(error)
      alert('제재 처리에 실패했습니다.')
    }
  }

  const sendMessage = async (user) => {
    const message = messageByUser[user.id]?.trim()
    if (!message) {
      alert('메시지를 입력해주세요.')
      return
    }

    try {
      await createUserNotification(user.id, {
        title: '관리자 메시지',
        message,
      })
      setMessageByUser((current) => ({ ...current, [user.id]: '' }))
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
            <h1>유저 관리</h1>
            <p className={styles.headerDescription}>
              신고 누적 수와 활동 내역을 기준으로 유저를 확인하고 조치합니다.
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
          <p className={styles.statusText}>유저 목록을 불러오는 중입니다.</p>
        ) : errorMessage ? (
          <p className={styles.errorText}>{errorMessage}</p>
        ) : (
          <section className={styles.adminTableWrap}>
            <table className={`${styles.adminTable} ${styles.userTable}`}>
              <colgroup>
                <col className={styles.colNumber} />
                <col className={styles.colUserMain} />
                <col className={styles.colEmail} />
                <col className={styles.colCount} />
                <col className={styles.colCount} />
                <col className={styles.colCount} />
                <col className={styles.colStatus} />
                <col className={styles.colAction} />
              </colgroup>

              <thead>
                <tr>
                  <th>ID</th>
                  <th>유저</th>
                  <th>이메일</th>
                  <th>신고</th>
                  <th>글</th>
                  <th>댓글</th>
                  <th>상태</th>
                  <th>관리</th>
                </tr>
              </thead>

              <tbody>
                {users.map((user) => (
                  <Fragment key={user.id}>
                    <tr className={isUserOpen(user.id) ? styles.opened : undefined}>
                      <td className={styles.numberCell}>{user.id}</td>
                      <td className={styles.userMainCell}>
                        <Link to={`/admin/users/${user.id}`} className={styles.userLink}>
                          {formatUserName(user)}
                        </Link>
                      </td>
                      <td className={styles.emailCell}>{user.email || '-'}</td>
                      <td>
                        <span className={`${styles.countChip} ${styles.danger}`}>
                          {user.received_reports_count}
                        </span>
                      </td>
                      <td><span className={styles.countChip}>{user.posts_count}</span></td>
                      <td><span className={styles.countChip}>{user.comments_count}</span></td>
                      <td>
                        <span
                          className={`${styles.statusBadge} ${user.current_penalty ? styles.blocked : styles.normal}`}
                        >
                          {formatPenalty(user.current_penalty)}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className={styles.rowAction}
                          onClick={() => toggleUser(user.id)}
                        >
                          {isUserOpen(user.id) ? '닫기' : '관리'}
                        </button>
                      </td>
                    </tr>

                    {isUserOpen(user.id) ? (
                      <tr className={styles.detailRow}>
                        <td colSpan={8}>
                          <div className={styles.detailPanel}>
                            {user.current_penalty ? (
                              <section className={styles.penaltyBox}>
                                <strong>현재 제재</strong>
                                <p>
                                  {formatPenalty(user.current_penalty)} / {user.current_penalty.reason}
                                </p>
                              </section>
                            ) : null}

                            <section className={styles.actionPanel}>
                              <h3>제재 조치</h3>
                              <input
                                value={reasonByUser[user.id] || ''}
                                onChange={(event) => setReasonByUser((current) => ({
                                  ...current,
                                  [user.id]: event.target.value,
                                }))}
                                type="text"
                                placeholder="조치 사유"
                              />
                              <div className={styles.penaltyActions}>
                                {PENALTIES.map(([value, label]) => (
                                  <button
                                    key={value}
                                    type="button"
                                    onClick={() => applyPenalty(user, value)}
                                  >
                                    {label}
                                  </button>
                                ))}
                              </div>
                            </section>

                            <section className={styles.actionPanel}>
                              <h3>관리자 메시지</h3>
                              <div className={styles.messageRow}>
                                <input
                                  value={messageByUser[user.id] || ''}
                                  onChange={(event) => setMessageByUser((current) => ({
                                    ...current,
                                    [user.id]: event.target.value,
                                  }))}
                                  type="text"
                                  placeholder="관리자 메시지"
                                />
                                <button
                                  type="button"
                                  className={styles.messageButton}
                                  onClick={() => sendMessage(user)}
                                >
                                  메시지 보내기
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

            {users.length === 0 ? (
              <p className={styles.emptyText}>표시할 유저가 없습니다.</p>
            ) : null}
          </section>
        )}
      </section>
    </main>
  )
}

export default AdminUserView
