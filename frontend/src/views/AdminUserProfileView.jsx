import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { createUserNotification, createUserPenalty, getAdminUser } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

import styles from './AdminUserProfileView.module.css'

const PENALTY_OPTIONS = [
  ['warning', '경고만'],
  ['suspend_3_days', '3일 활동정지'],
  ['suspend_7_days', '7일 활동정지'],
  ['suspend_30_days', '30일 활동정지'],
  ['suspend_1_year', '1년 사용정지'],
  ['permanent_ban', '영구밴'],
]

const normalizeAdminProfile = (payload = {}) => ({
  user: payload.user || payload,
  posts: Array.isArray(payload.posts) ? payload.posts : [],
  comments: Array.isArray(payload.comments) ? payload.comments : [],
  penalties: Array.isArray(payload.penalties) ? payload.penalties : [],
})

const AdminUserProfileView = () => {
  const navigate = useNavigate()
  const { userId } = useParams()

  const [profile, setProfile] = useState(null)
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState('')
  const [selectedPenalty, setSelectedPenalty] = useState('warning')
  const [errorMessage, setErrorMessage] = useState('')

  const fetchProfile = useCallback(async () => {
    const { isLoggedIn, user: currentUser, fetchMe } = useAuthStore.getState()

    if (isLoggedIn && !currentUser?.is_staff) {
      await fetchMe()
    }

    if (!useAuthStore.getState().user?.is_staff) {
      navigate('/')
      return
    }

    try {
      const response = await getAdminUser(userId)
      setProfile(normalizeAdminProfile(response.data))
    } catch (error) {
      console.error(error)
      setErrorMessage('유저 프로필을 불러오지 못했습니다.')
    }
  }, [navigate, userId])

  useEffect(() => {
    fetchProfile()
  }, [fetchProfile])

  const user = profile?.user

  const applyPenalty = async () => {
    if (!reason.trim()) {
      alert('제재 사유를 입력해주세요.')
      return
    }

    await createUserPenalty(user.id, {
      penalty_type: selectedPenalty,
      reason,
    })
    setReason('')
    await fetchProfile()
  }

  const sendMessage = async () => {
    if (!message.trim()) {
      alert('관리자 메시지를 입력해주세요.')
      return
    }

    await createUserNotification(user.id, {
      title: '관리자 메시지',
      message,
    })
    setMessage('')
    alert('메시지를 보냈습니다.')
  }

  return (
    <main className={styles.profilePage}>
      <section className={styles.profileContainer}>
        {errorMessage ? (
          <p className={`${styles.statusCard} ${styles.error}`}>{errorMessage}</p>
        ) : profile ? (
          <>
            <header className={styles.profileHeader}>
              <div>
                <p className={styles.eyebrow}>USER PROFILE</p>
                <h1>#{user.id} {user.username}</h1>
                <p>{user.email || '이메일 없음'}</p>
              </div>
              <Link to="/admin/users" className={styles.backLink}>유저 목록</Link>
            </header>

            <section className={styles.summaryGrid}>
              <article className={styles.summaryCard}>
                <strong>{user.posts_count}</strong><span>작성 글</span>
              </article>
              <article className={styles.summaryCard}>
                <strong>{user.comments_count}</strong><span>작성 댓글</span>
              </article>
              <article className={styles.summaryCard}>
                <strong>{user.received_reports_count}</strong><span>받은 신고</span>
              </article>
              <article className={styles.summaryCard}>
                <strong>{user.is_staff ? '관리자' : '일반'}</strong><span>권한</span>
              </article>
            </section>

            <section className={`${styles.panel}${user.current_penalty ? ` ${styles.warning}` : ''}`}>
              <h2>현재 제재 상태</h2>
              {user.current_penalty ? (
                <p>{user.current_penalty.penalty_type} / {user.current_penalty.reason}</p>
              ) : (
                <p>현재 활성 제재가 없습니다.</p>
              )}
            </section>

            <section className={styles.panel}>
              <h2>제재/메시지</h2>
              <select
                value={selectedPenalty}
                onChange={(event) => setSelectedPenalty(event.target.value)}
              >
                {PENALTY_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                type="text"
                placeholder="제재 사유"
              />
              <button type="button" onClick={applyPenalty}>제재 적용</button>
              <input
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                type="text"
                placeholder="관리자 메시지"
              />
              <button type="button" className={styles.messageButton} onClick={sendMessage}>
                메시지 보내기
              </button>
            </section>

            <section className={styles.panel}>
              <h2>최근 제재 이력</h2>
              {profile.penalties.map((penalty) => (
                <article key={penalty.id} className={styles.item}>
                  <strong>{penalty.penalty_type}</strong>
                  <p>{penalty.reason}</p>
                </article>
              ))}
              {profile.penalties.length === 0 ? (
                <p className={styles.muted}>제재 이력이 없습니다.</p>
              ) : null}
            </section>

            <section className={styles.panel}>
              <h2>작성한 게시글</h2>
              {profile.posts.map((post) => (
                <Link
                  key={post.id}
                  to={`/boards/${post.board_type}/${post.id}`}
                  className={`${styles.item} ${styles.linkItem}`}
                >
                  {post.title}
                </Link>
              ))}
              {profile.posts.length === 0 ? (
                <p className={styles.muted}>작성한 게시글이 없습니다.</p>
              ) : null}
            </section>

            <section className={styles.panel}>
              <h2>작성한 댓글</h2>
              {profile.comments.map((comment) => (
                <article key={comment.id} className={styles.item}>
                  {comment.content}
                </article>
              ))}
              {profile.comments.length === 0 ? (
                <p className={styles.muted}>작성한 댓글이 없습니다.</p>
              ) : null}
            </section>
          </>
        ) : null}
      </section>
    </main>
  )
}

export default AdminUserProfileView
