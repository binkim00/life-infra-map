import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import {
  createUserPreference,
  deleteUserPreference,
  fetchPreferenceTags,
  fetchUserPreferences,
} from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'
import { normalizeLabelValue } from '@/utils/labelNormalizers'

import styles from './PreferenceSettingsView.module.css'

const PREFERENCE_TYPE_LABELS = {
  menu: '메뉴',
  place_type: '장소 유형',
  condition: '조건',
  category: '카테고리',
  scenario: '상황',
  tag: '태그',
  keyword: '키워드',
}

const getPreferenceTypeLabel = (type) => PREFERENCE_TYPE_LABELS[type] || '선호'

const getPreferenceLabel = (preference) => {
  return normalizeLabelValue(preference?.label || preference?.key)
}

const formatPreferenceScore = (score) => {
  const numericScore = Number(score)

  if (!Number.isFinite(numericScore)) return '0.0'
  return numericScore.toFixed(1)
}

const getPreferenceMeta = (preference) => {
  const searchCount = Number(preference?.search_count || 0)

  return [
    `선호도 ${formatPreferenceScore(preference?.score)}`,
    searchCount > 0 ? `최근 검색 ${searchCount}회` : '',
  ].filter(Boolean).join(' · ')
}

const getTagKey = (tag) => {
  return normalizeLabelValue(tag?.name || tag?.display_name).toLowerCase()
}

const PreferenceSettingsView = () => {
  const navigate = useNavigate()

  const [preferenceTags, setPreferenceTags] = useState([])
  const [directPreferences, setDirectPreferences] = useState([])
  const [automaticPreferences, setAutomaticPreferences] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingTags, setIsLoadingTags] = useState(false)
  const [message, setMessage] = useState('')
  const [tagMessage, setTagMessage] = useState('')
  const [updatingTagId, setUpdatingTagId] = useState(null)
  const [deletingPreferenceId, setDeletingPreferenceId] = useState(null)
  const [automaticPage, setAutomaticPage] = useState(1)
  const [automaticMeta, setAutomaticMeta] = useState({
    count: 0,
    page: 1,
    pageSize: 5,
    totalPages: 1,
  })

  const fetchTags = useCallback(async () => {
    try {
      setIsLoadingTags(true)
      const response = await fetchPreferenceTags()
      const results = response.results || []
      setPreferenceTags(results)
      setTagMessage(results.length ? '' : '선택할 수 있는 태그가 아직 없습니다.')
    } catch (error) {
      setPreferenceTags([])
      setTagMessage('선호 태그 목록을 불러오지 못했습니다.')
    } finally {
      setIsLoadingTags(false)
    }
  }, [])

  const fetchDirectPreferences = useCallback(async () => {
    const response = await fetchUserPreferences({
      page: 1,
      pageSize: 50,
      source: 'user_selected',
      type: 'tag',
    })
    setDirectPreferences(response.results || [])
  }, [])

  const fetchAutomaticPreferences = useCallback(async (targetPage) => {
    const response = await fetchUserPreferences({
      page: targetPage,
      pageSize: 5,
      source: 'search_log',
    })

    setAutomaticPreferences(response.results || [])
    setAutomaticMeta({
      count: response.count || 0,
      page: response.page || targetPage,
      pageSize: response.page_size || 5,
      totalPages: response.total_pages || 1,
    })
  }, [])

  useEffect(() => {
    if (!useAuthStore.getState().isLoggedIn) {
      navigate('/login')
      return
    }

    fetchTags()
  }, [fetchTags, navigate])

  useEffect(() => {
    if (!useAuthStore.getState().isLoggedIn) return

    const fetchPreferences = async () => {
      try {
        setIsLoading(true)
        setMessage('')
        await Promise.all([
          fetchDirectPreferences(),
          fetchAutomaticPreferences(automaticPage),
        ])
      } catch (error) {
        setMessage('선호 정보를 불러오지 못했습니다.')
      } finally {
        setIsLoading(false)
      }
    }

    fetchPreferences()
  }, [fetchDirectPreferences, fetchAutomaticPreferences, automaticPage])

  const selectedTagPreferenceMap = useMemo(() => {
    const map = new Map()

    directPreferences.forEach((preference) => {
      const key = normalizeLabelValue(preference.key || preference.label).toLowerCase()
      if (key) map.set(key, preference)
    })

    return map
  }, [directPreferences])

  const getSelectedPreferenceForTag = useCallback((tag) => {
    return selectedTagPreferenceMap.get(getTagKey(tag))
  }, [selectedTagPreferenceMap])

  const isTagSelected = useCallback(
    (tag) => Boolean(getSelectedPreferenceForTag(tag)),
    [getSelectedPreferenceForTag],
  )

  const tagGroups = useMemo(() => {
    const groups = new Map()

    preferenceTags.forEach((tag) => {
      const groupName = normalizeLabelValue(tag.group) || '기타'

      if (!groups.has(groupName)) {
        groups.set(groupName, [])
      }

      groups.get(groupName).push(tag)
    })

    return [...groups.entries()].map(([name, tags]) => ({ name, tags }))
  }, [preferenceTags])

  const handleToggleTag = async (tag) => {
    const selectedPreference = getSelectedPreferenceForTag(tag)

    try {
      setUpdatingTagId(tag.id)
      setTagMessage('')

      if (selectedPreference) {
        await deleteUserPreference(selectedPreference.id)
        setTagMessage('선호 태그 선택을 해제했습니다.')
      } else {
        await createUserPreference({
          preference_type: 'tag',
          tag_id: tag.id,
        })
        setTagMessage('선호 태그를 선택했습니다.')
      }

      await fetchDirectPreferences()
    } catch (error) {
      setTagMessage(error.response?.data?.detail || '선호 태그를 저장하지 못했습니다.')
    } finally {
      setUpdatingTagId(null)
    }
  }

  const handleDeleteDirectPreference = async (preference) => {
    try {
      setDeletingPreferenceId(preference.id)
      await deleteUserPreference(preference.id)
      setTagMessage('직접 선택한 선호 태그를 삭제했습니다.')
      await fetchDirectPreferences()
    } catch (error) {
      setTagMessage(error.response?.data?.detail || '선호 태그를 삭제하지 못했습니다.')
    } finally {
      setDeletingPreferenceId(null)
    }
  }

  const moveAutomaticPage = (direction) => {
    const nextPage = automaticPage + direction
    if (nextPage < 1 || nextPage > automaticMeta.totalPages) return

    setAutomaticPage(nextPage)
  }

  return (
    <main className={styles.settingsPage}>
      <section className={styles.settingsContainer}>
        <header className={styles.pageTitle}>
          <Link to="/mypage" className={styles.backLink}>마이페이지로 돌아가기</Link>
          <p className={styles.eyebrow}>PREFERENCES</p>
          <h1>선호 태그 설정</h1>
          <p>추천에 더 반영하고 싶은 태그를 선택하고, 최근 검색 기반 자동 선호를 확인할 수 있습니다.</p>
        </header>

        <section className={styles.panel}>
          <div className={styles.sectionHeadingRow}>
            <div>
              <h2>선호 태그 설정</h2>
              <p>체크한 태그는 추천 결과에 조금 더 강하게 반영됩니다.</p>
            </div>
          </div>

          {isLoadingTags ? (
            <p className={styles.empty}>선호 태그 목록을 불러오는 중입니다.</p>
          ) : tagGroups.length ? (
            <div className={styles.tagGroupList}>
              {tagGroups.map((group) => (
                <div key={group.name} className={styles.tagGroup}>
                  <h3>{group.name}</h3>
                  <div className={styles.tagOptions}>
                    {group.tags.map((tag) => (
                      <label
                        key={tag.id}
                        className={`${styles.tagOption}${isTagSelected(tag) ? ` ${styles.isSelected}` : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={isTagSelected(tag)}
                          disabled={updatingTagId === tag.id}
                          onChange={() => handleToggleTag(tag)}
                        />
                        <span>{tag.display_name || tag.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className={styles.empty}>
              {tagMessage || '선택할 수 있는 태그가 아직 없습니다.'}
            </p>
          )}
          {tagMessage ? <p className={styles.statusMessage}>{tagMessage}</p> : null}
        </section>

        <section className={styles.panel}>
          <div className={styles.sectionHeadingRow}>
            <div>
              <h2>직접 선택한 선호 태그</h2>
              <p>사용자가 직접 체크한 태그입니다.</p>
            </div>
          </div>

          {isLoading ? (
            <p className={styles.empty}>선호 정보를 불러오는 중입니다.</p>
          ) : directPreferences.length ? (
            <div className={styles.preferenceChipList}>
              {directPreferences.map((preference) => (
                <span key={preference.id} className={styles.preferenceChip}>
                  <strong>{getPreferenceLabel(preference)}</strong>
                  <button
                    type="button"
                    disabled={deletingPreferenceId === preference.id}
                    onClick={() => handleDeleteDirectPreference(preference)}
                  >
                    삭제
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <p className={styles.empty}>직접 선택한 선호 태그가 아직 없습니다.</p>
          )}
        </section>

        <section className={styles.panel}>
          <div className={styles.sectionHeadingRow}>
            <div>
              <h2>최근 검색 기반 자동 선호</h2>
              <p>검색 기록에서 추정된 선호입니다. 검색 기록 삭제 시 다시 계산됩니다.</p>
            </div>
          </div>

          {isLoading ? (
            <p className={styles.empty}>자동 선호를 불러오는 중입니다.</p>
          ) : automaticPreferences.length ? (
            <div className={styles.preferenceList}>
              {automaticPreferences.map((preference) => (
                <article key={preference.id} className={styles.preferenceItem}>
                  <span className={styles.preferenceTypeBadge}>
                    {getPreferenceTypeLabel(preference.preference_type)}
                  </span>
                  <strong>{getPreferenceLabel(preference)}</strong>
                  <span>{getPreferenceMeta(preference)}</span>
                </article>
              ))}
            </div>
          ) : (
            <p className={styles.empty}>
              {message || '최근 검색 기반 자동 선호가 아직 없습니다.'}
            </p>
          )}

          <div className={styles.pager}>
            <button
              type="button"
              disabled={automaticPage <= 1}
              onClick={() => moveAutomaticPage(-1)}
            >
              이전
            </button>
            <span>{automaticMeta.page} / {automaticMeta.totalPages}</span>
            <button
              type="button"
              disabled={automaticPage >= automaticMeta.totalPages}
              onClick={() => moveAutomaticPage(1)}
            >
              다음
            </button>
          </div>
        </section>
      </section>
    </main>
  )
}

export default PreferenceSettingsView
