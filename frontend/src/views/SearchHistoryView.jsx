import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { deleteSearchLog, fetchSearchLogs } from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'
import { normalizeLabelList, normalizeLabelValue } from '@/utils/labelNormalizers'

import styles from './SearchHistoryView.module.css'

const SCENARIO_LABELS = {
  work_cafe: '조용히 작업할 곳',
  waiting_place: '잠깐 쉴 곳',
  walk_healing: '산책/힐링',
  smoking_area: '흡연 가능한 곳',
  restaurant: '식당/맛집',
  blocked: '검색 불가',
}

const CATEGORY_LABELS = {
  cafe: '카페',
  restaurant: '식당',
  food: '음식',
  toilet: '공중화장실',
  freewifi: '무료 와이파이',
  smoking_area: '흡연구역',
  beach: '해수욕장',
  parking: '주차장',
  city_park: '공원',
  tourism: '관광지',
}

const getMappedLabel = (value, labelMap = {}) => {
  const label = normalizeLabelValue(value)
  const key = label.toLowerCase()

  return labelMap[key] || labelMap[label] || label
}

const getSearchLogCategoryLabel = (log) => {
  return getMappedLabel(log.category_hint, CATEGORY_LABELS)
    || getMappedLabel(log.scenario, SCENARIO_LABELS)
}

const getSearchLogMeta = (log) => {
  return [
    normalizeLabelValue(log.location_hint),
    getSearchLogCategoryLabel(log),
    `결과 ${log.result_count || 0}개`,
  ].filter(Boolean).join(' · ')
}

const getSearchLogChips = (log) => {
  return normalizeLabelList([
    ...normalizeLabelList(log.menu_keywords),
    ...normalizeLabelList(log.place_type_keywords),
    ...normalizeLabelList(log.requested_conditions),
    ...normalizeLabelList(log.preferred_tags),
  ]).slice(0, 3)
}

const formatSearchLogDate = (value) => {
  if (!value) return ''

  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const SearchHistoryView = () => {
  const navigate = useNavigate()

  const [searchLogs, setSearchLogs] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [deletingLogId, setDeletingLogId] = useState(null)
  const [page, setPage] = useState(1)
  const [meta, setMeta] = useState({
    count: 0,
    page: 1,
    pageSize: 5,
    totalPages: 1,
  })

  const fetchLogs = useCallback(async (targetPage) => {
    try {
      setIsLoading(true)
      setMessage('')
      const response = await fetchSearchLogs({
        page: targetPage,
        pageSize: 5,
      })

      const results = response.results || []
      setSearchLogs(results)
      setMeta({
        count: response.count || 0,
        page: response.page || targetPage,
        pageSize: response.page_size || 5,
        totalPages: response.total_pages || 1,
      })

      if (!results.length) {
        setMessage('저장된 검색 기록이 없습니다.')
      }
    } catch (error) {
      setSearchLogs([])
      setMessage('검색 기록을 불러오지 못했습니다.')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!useAuthStore.getState().isLoggedIn) {
      navigate('/login')
      return
    }

    fetchLogs(page)
  }, [fetchLogs, navigate, page])

  const rerunSearchLog = (log) => {
    if (!log?.query) return

    navigate(`/?q=${encodeURIComponent(log.query)}&autoSearch=1`)
  }

  const handleDeleteSearchLog = async (log) => {
    if (!log?.id) return

    try {
      setDeletingLogId(log.id)
      await deleteSearchLog(log.id)

      // 마지막 한 건을 지웠으면 앞 페이지로 물러납니다.
      const nextPage = searchLogs.length === 1 && page > 1 ? page - 1 : page

      setMessage('검색 기록을 삭제했습니다. 자동 선호도 다시 계산되었습니다.')

      if (nextPage !== page) {
        setPage(nextPage)
      } else {
        await fetchLogs(page)
        setMessage('검색 기록을 삭제했습니다. 자동 선호도 다시 계산되었습니다.')
      }
    } catch (error) {
      setMessage(error.response?.data?.detail || '검색 기록을 삭제하지 못했습니다.')
    } finally {
      setDeletingLogId(null)
    }
  }

  const movePage = (direction) => {
    const nextPage = page + direction
    if (nextPage < 1 || nextPage > meta.totalPages) return

    setPage(nextPage)
  }

  return (
    <main className={styles.historyPage}>
      <section className={styles.historyContainer}>
        <header className={styles.pageTitle}>
          <Link to="/mypage" className={styles.backLink}>마이페이지로 돌아가기</Link>
          <p className={styles.eyebrow}>SEARCH HISTORY</p>
          <h1>검색 기록 관리</h1>
          <p>최근 검색 기록을 확인하고 삭제할 수 있습니다. 삭제하면 검색 기반 자동 선호가 다시 계산됩니다.</p>
        </header>

        <section className={styles.panel}>
          <div className={styles.sectionHeadingRow}>
            <div>
              <h2>검색 기록</h2>
              <p>5개씩 표시됩니다.</p>
            </div>
          </div>

          {isLoading ? (
            <p className={styles.empty}>검색 기록을 불러오는 중입니다.</p>
          ) : searchLogs.length ? (
            <div className={styles.historyList}>
              {searchLogs.map((log) => {
                const chips = getSearchLogChips(log)

                return (
                  <article key={log.id} className={styles.historyItem}>
                    <div className={styles.historyMain}>
                      <strong>{log.query}</strong>
                      <span>{getSearchLogMeta(log)}</span>
                      <time>{formatSearchLogDate(log.created_at)}</time>
                      {chips.length ? (
                        <span className={styles.chipRow}>
                          {chips.map((chip) => (
                            <span key={chip} className={styles.chip}>{chip}</span>
                          ))}
                        </span>
                      ) : null}
                    </div>
                    <div className={styles.historyActions}>
                      <button type="button" onClick={() => rerunSearchLog(log)}>
                        다시 검색
                      </button>
                      <button
                        type="button"
                        className={styles.danger}
                        disabled={deletingLogId === log.id}
                        onClick={() => handleDeleteSearchLog(log)}
                      >
                        {deletingLogId === log.id ? '삭제 중' : '삭제'}
                      </button>
                    </div>
                  </article>
                )
              })}
            </div>
          ) : (
            <p className={styles.empty}>{message || '저장된 검색 기록이 없습니다.'}</p>
          )}

          {message && searchLogs.length ? (
            <p className={styles.statusMessage}>{message}</p>
          ) : null}

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

export default SearchHistoryView
