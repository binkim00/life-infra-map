import { Fragment, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { getMyInquiries } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

import styles from './MyInquiryView.module.css'

const statusLabel = (status) => {
  if (status === 'answered') {
    return '답변완료'
  }

  return '답변대기'
}

const formatBoardDate = (value) => {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()

  if (isToday) {
    return date.toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }

  return date.toLocaleDateString('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  }).replace(/\. /g, '.').replace(/\.$/, '')
}

const MyInquiryView = () => {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)

  const [inquiries, setInquiries] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [openedInquiryId, setOpenedInquiryId] = useState(null)

  useEffect(() => {
    let isStale = false

    const fetchInquiries = async () => {
      if (!useAuthStore.getState().isLoggedIn) {
        navigate('/login')
        return
      }

      try {
        setIsLoading(true)
        setErrorMessage('')
        const response = await getMyInquiries()
        if (isStale) return
        setInquiries(response.data)
      } catch (error) {
        if (isStale) return
        console.error(error)
        setErrorMessage(error.response?.data?.detail || '문의 내역을 불러오지 못했습니다.')
      } finally {
        if (!isStale) {
          setIsLoading(false)
        }
      }
    }

    fetchInquiries()

    return () => {
      isStale = true
    }
  }, [navigate])

  const toggleInquiry = (inquiryId) => {
    setOpenedInquiryId((current) => (current === inquiryId ? null : inquiryId))
  }

  return (
    <main className={styles.page}>
      <section className={styles.container}>
        <header className={styles.pageTitle}>
          <div>
            <p className={styles.eyebrow}>CUSTOMER CENTER</p>
            <h1>내 문의</h1>
          </div>
          <Link to="/inquiries/new" className={styles.writeButton}>
            문의하기
          </Link>
        </header>

        {isLoading ? (
          <p className={styles.statusCard}>문의 내역을 불러오는 중입니다.</p>
        ) : errorMessage ? (
          <p className={`${styles.statusCard} ${styles.error}`}>{errorMessage}</p>
        ) : (
          <section className={styles.inquiryBoard}>
            <table className={styles.inquiryTable}>
              <colgroup>
                <col className={styles.colNumber} />
                <col className={styles.colCategory} />
                <col className={styles.colTitle} />
                <col className={styles.colAuthor} />
                <col className={styles.colDate} />
                <col className={styles.colStatus} />
              </colgroup>

              <thead>
                <tr>
                  <th>번호</th>
                  <th>말머리</th>
                  <th>제목</th>
                  <th>글쓴이</th>
                  <th>작성일</th>
                  <th>상태</th>
                </tr>
              </thead>

              <tbody>
                {inquiries.map((inquiry) => (
                  <Fragment key={inquiry.id}>
                    <tr
                      className={`${styles.inquiryRow}${openedInquiryId === inquiry.id ? ` ${styles.opened}` : ''}`}
                      tabIndex={0}
                      onClick={() => toggleInquiry(inquiry.id)}
                      onKeyUp={(event) => {
                        if (event.key === 'Enter') {
                          toggleInquiry(inquiry.id)
                        }
                      }}
                    >
                      <td>{inquiry.id}</td>
                      <td>
                        <span className={styles.categoryLabel}>문의</span>
                      </td>
                      <td className={styles.titleCell}>
                        <button type="button" className={styles.titleButton}>
                          {inquiry.title}
                        </button>
                      </td>
                      <td>{user?.nickname || user?.username || '나'}</td>
                      <td>{formatBoardDate(inquiry.created_at)}</td>
                      <td>
                        <span
                          className={`${styles.statusBadge}${inquiry.status === 'answered' ? ` ${styles.answered}` : ''}`}
                        >
                          {statusLabel(inquiry.status)}
                        </span>
                      </td>
                    </tr>

                    {openedInquiryId === inquiry.id ? (
                      <tr className={styles.inquiryDetailRow}>
                        <td colSpan={6}>
                          <div className={styles.inquiryDetail}>
                            <section>
                              <strong>문의 내용</strong>
                              <p>{inquiry.content}</p>
                            </section>

                            <section>
                              <strong>답변 내용</strong>
                              <p>
                                {inquiry.status === 'answered'
                                  ? (inquiry.admin_reply || '등록된 답변 내용이 없습니다.')
                                  : '아직 답변을 기다리고 있습니다.'}
                              </p>
                            </section>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>

            {inquiries.length === 0 ? (
              <p className={styles.statusCard}>작성한 문의가 없습니다.</p>
            ) : null}
          </section>
        )}
      </section>
    </main>
  )
}

export default MyInquiryView
