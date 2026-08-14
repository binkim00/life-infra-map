import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { getMypage, updateNickname, updateProfileImage } from '@/api/boards'
import {
  deleteSearchLog,
  deleteUserSavedPlace,
  fetchSearchLogs,
  fetchUserPreferences,
  fetchUserSavedPlaces,
  updateUserSavedPlace,
} from '@/api/recommendation'
import SavedPlacesPanel from '@/components/SavedPlacesPanel'
import { useAuthStore } from '@/stores/auth'
import { normalizeLabelList, normalizeLabelValue } from '@/utils/labelNormalizers'
import { getTierIcon } from '@/utils/tierIcons'

import styles from './MypageView.module.css'

const SECTION_VALUES = ['profile', 'saved', 'posts', 'comments', 'liked']

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

const SEARCH_MODE_LABELS = {
  recommendation_query: '추천 검색',
  region_search: '지역 검색',
  keyword_search: '키워드 검색',
  map_bounds_search: '지도 검색',
  current_context: '현재 위치 검색',
}

const PREFERENCE_TYPE_LABELS = {
  menu: '메뉴',
  place_type: '장소 유형',
  condition: '조건',
  category: '카테고리',
  scenario: '상황',
  tag: '태그',
  keyword: '키워드',
}

const getMappedLabel = (value, labelMap = {}) => {
  const label = normalizeLabelValue(value)
  const key = label.toLowerCase()

  return labelMap[key] || labelMap[label] || label
}

const getUserContribution = (user) => user?.contribution ?? user?.score ?? 0

const normalizeMypageData = (payload = {}) => ({
  ...payload,
  user: payload.user || {},
  posts: Array.isArray(payload.posts) ? payload.posts : [],
  comments: Array.isArray(payload.comments) ? payload.comments : [],
  liked_posts: Array.isArray(payload.liked_posts) ? payload.liked_posts : [],
  notifications: Array.isArray(payload.notifications) ? payload.notifications : [],
  inquiries: Array.isArray(payload.inquiries) ? payload.inquiries : [],
  penalty: payload.penalty || {
    is_suspended: false,
    suspended_until: null,
    is_permanent_ban: false,
    reason: '',
    penalty_type: '',
  },
})

const getNicknameColorStyle = (user) => {
  return user?.nickname_color ? { color: user.nickname_color } : undefined
}

const getSearchLogCategoryLabel = (log) => (
  getMappedLabel(log.category_hint, CATEGORY_LABELS)
  || getMappedLabel(log.scenario, SCENARIO_LABELS)
  || getMappedLabel(log.search_mode, SEARCH_MODE_LABELS)
)

const getSearchLogMeta = (log) => [
  normalizeLabelValue(log.location_hint),
  getSearchLogCategoryLabel(log),
  `결과 ${log.result_count || 0}개`,
].filter(Boolean).join(' · ')

const getSearchLogChips = (log) => normalizeLabelList([
  ...normalizeLabelList(log.menu_keywords),
  ...normalizeLabelList(log.place_type_keywords),
  ...normalizeLabelList(log.requested_conditions),
  ...normalizeLabelList(log.preferred_tags),
]).slice(0, 5)

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

const getPreferenceTypeLabel = (type) => PREFERENCE_TYPE_LABELS[type] || '선호'

const isUserSelectedPreference = (preference) => preference?.source === 'user_selected'

const getPreferenceSourceLabel = (preference) => (
  isUserSelectedPreference(preference) ? '직접 선택' : '자동'
)

const getPreferenceLabel = (preference) => {
  const rawLabel = preference?.label || preference?.key

  if (preference?.preference_type === 'scenario') {
    return getMappedLabel(rawLabel, SCENARIO_LABELS)
  }

  if (preference?.preference_type === 'category') {
    return getMappedLabel(rawLabel, CATEGORY_LABELS)
  }

  return normalizeLabelValue(rawLabel)
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

const MypageView = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const setUser = useAuthStore((state) => state.setUser)

  const sectionParam = searchParams.get('section')
  const selectedSection = SECTION_VALUES.includes(sectionParam) ? sectionParam : 'profile'

  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [nicknameInput, setNicknameInput] = useState('')
  const [nicknameMessage, setNicknameMessage] = useState('')
  const [isEditingNickname, setIsEditingNickname] = useState(false)
  const [isUpdatingNickname, setIsUpdatingNickname] = useState(false)
  const [profileImageFile, setProfileImageFile] = useState(null)
  const [profileImagePreviewUrl, setProfileImagePreviewUrl] = useState('')
  const [profileImageMessage, setProfileImageMessage] = useState('')
  const [isUpdatingProfileImage, setIsUpdatingProfileImage] = useState(false)
  const [searchLogs, setSearchLogs] = useState([])
  const [isLoadingSearchLogs, setIsLoadingSearchLogs] = useState(false)
  const [searchLogMessage, setSearchLogMessage] = useState('')
  const [userPreferences, setUserPreferences] = useState([])
  const [isLoadingPreferences, setIsLoadingPreferences] = useState(false)
  const [preferenceMessage, setPreferenceMessage] = useState('')
  const [savedPlaces, setSavedPlaces] = useState([])
  const [savedPlaceCount, setSavedPlaceCount] = useState(0)
  const [isLoadingSavedPlaces, setIsLoadingSavedPlaces] = useState(false)
  const [savedPlaceMessage, setSavedPlaceMessage] = useState('')
  const [editingSavedPlaceId, setEditingSavedPlaceId] = useState(null)
  const [savedPlaceMemoInput, setSavedPlaceMemoInput] = useState('')
  const [updatingSavedPlaceId, setUpdatingSavedPlaceId] = useState(null)

  const profileImageInputRef = useRef(null)

  const fetchPreferences = useCallback(async () => {
    if (!useAuthStore.getState().isLoggedIn) {
      setUserPreferences([])
      setPreferenceMessage('로그인 후 선호 키워드를 확인할 수 있습니다.')
      return
    }

    try {
      setIsLoadingPreferences(true)
      setPreferenceMessage('')
      const response = await fetchUserPreferences({ page: 1, pageSize: 5 })
      const results = (response.results || []).filter(
        (preference) => normalizeLabelValue(preference.label),
      )
      setUserPreferences(results)

      if (!results.length) {
        setPreferenceMessage('검색하거나 직접 선호를 추가하면 이곳에 표시됩니다.')
      }
    } catch (error) {
      setUserPreferences([])

      if ([401, 403].includes(error.response?.status)) {
        setPreferenceMessage('로그인 후 선호 키워드를 확인할 수 있습니다.')
      } else {
        setPreferenceMessage('선호 키워드를 불러오지 못했습니다.')
      }

      if (import.meta.env.DEV) {
        console.debug('[UserPreferences] fetch failed', {
          status: error.response?.status || 'request_failed',
        })
      }
    } finally {
      setIsLoadingPreferences(false)
    }
  }, [])

  const fetchSavedPlaces = useCallback(async () => {
    if (!useAuthStore.getState().isLoggedIn) {
      setSavedPlaces([])
      setSavedPlaceMessage('로그인 후 저장한 장소를 확인할 수 있습니다.')
      return
    }

    try {
      setIsLoadingSavedPlaces(true)
      setSavedPlaceMessage('')
      const response = await fetchUserSavedPlaces({ page: 1, pageSize: 10 })
      const results = response.results || []
      setSavedPlaces(results)
      setSavedPlaceCount(response.count ?? results.length)

      if (!results.length) {
        setSavedPlaceMessage('아직 저장한 장소가 없습니다.')
      }
    } catch (error) {
      setSavedPlaces([])
      setSavedPlaceCount(0)
      setSavedPlaceMessage([401, 403].includes(error.response?.status)
        ? '로그인 후 저장한 장소를 확인할 수 있습니다.'
        : '저장한 장소를 불러오지 못했습니다.')
    } finally {
      setIsLoadingSavedPlaces(false)
    }
  }, [])

  const fetchRecentSearchLogs = useCallback(async () => {
    if (!useAuthStore.getState().isLoggedIn) {
      setSearchLogs([])
      setSearchLogMessage('로그인 후 검색 기록을 확인할 수 있습니다.')
      return
    }

    try {
      setIsLoadingSearchLogs(true)
      setSearchLogMessage('')
      const response = await fetchSearchLogs({ page: 1, pageSize: 5 })
      const results = response.results || []
      setSearchLogs(results)

      if (!results.length) {
        setSearchLogMessage('아직 저장된 검색 기록이 없습니다.')
      }
    } catch (error) {
      setSearchLogs([])

      if ([401, 403].includes(error.response?.status)) {
        setSearchLogMessage('로그인 후 검색 기록을 확인할 수 있습니다.')
      } else {
        setSearchLogMessage('검색 기록을 불러오지 못했습니다.')
      }

      if (import.meta.env.DEV) {
        console.debug('[SearchLogs] fetch failed', {
          status: error.response?.status || 'request_failed',
        })
      }
    } finally {
      setIsLoadingSearchLogs(false)
    }
  }, [])

  useEffect(() => {
    const fetchMypage = async () => {
      if (!useAuthStore.getState().isLoggedIn) {
        navigate('/login')
        return
      }

      try {
        setIsLoading(true)
        const response = await getMypage()
        const mypageData = normalizeMypageData(response.data)
        setData(mypageData)
        setNicknameInput(mypageData.user.nickname || '')
        setProfileImagePreviewUrl(mypageData.user.profile_image_url || '')
        fetchRecentSearchLogs()
        fetchPreferences()
        fetchSavedPlaces()
      } catch (error) {
        console.error(error)
        setErrorMessage('마이페이지 정보를 불러오지 못했습니다.')
      } finally {
        setIsLoading(false)
      }
    }

    fetchMypage()
  }, [navigate, fetchRecentSearchLogs, fetchPreferences, fetchSavedPlaces])

  const startSavedPlaceMemoEdit = (place) => {
    setEditingSavedPlaceId(place.id)
    setSavedPlaceMemoInput(place.memo || '')
  }

  const cancelSavedPlaceMemoEdit = () => {
    setEditingSavedPlaceId(null)
    setSavedPlaceMemoInput('')
  }

  const handleUpdateSavedPlaceMemo = async (place) => {
    if (!place?.id) return

    try {
      setUpdatingSavedPlaceId(place.id)
      const response = await updateUserSavedPlace(place.id, {
        memo: savedPlaceMemoInput,
      })
      const updatedPlace = response.saved_place || {}
      setSavedPlaces((current) => current.map((item) => (
        item.id === place.id ? { ...item, ...updatedPlace } : item
      )))
      setSavedPlaceMessage('메모를 저장했습니다.')
      cancelSavedPlaceMemoEdit()
    } catch (error) {
      setSavedPlaceMessage(error.response?.data?.detail || '메모를 저장하지 못했습니다.')
    } finally {
      setUpdatingSavedPlaceId(null)
    }
  }

  const handleDeleteSavedPlace = async (place) => {
    if (!place?.id) return

    try {
      setUpdatingSavedPlaceId(place.id)
      await deleteUserSavedPlace(place.id)
      setSavedPlaces((current) => current.filter((item) => item.id !== place.id))
      setSavedPlaceCount((current) => Math.max(0, current - 1))
      setSavedPlaceMessage('저장한 장소를 삭제했습니다.')
    } catch (error) {
      setSavedPlaceMessage(error.response?.data?.detail || '저장한 장소를 삭제하지 못했습니다.')
    } finally {
      setUpdatingSavedPlaceId(null)
    }
  }

  const handleDeleteSearchLog = async (log) => {
    if (!log?.id) return

    try {
      await deleteSearchLog(log.id)
      setSearchLogMessage('검색 기록을 삭제했습니다.')
      await fetchRecentSearchLogs()
      await fetchPreferences()
    } catch (error) {
      setSearchLogMessage(error.response?.data?.detail || '검색 기록을 삭제하지 못했습니다.')
    }
  }

  const rerunSearchLog = (log) => {
    if (!log?.query) return

    navigate(`/?q=${encodeURIComponent(log.query)}`)
  }

  const handleProfileImageChange = (event) => {
    const file = event.target.files?.[0]

    setProfileImageMessage('')
    setProfileImageFile(file || null)
    setProfileImagePreviewUrl(file
      ? URL.createObjectURL(file)
      : data?.user?.profile_image_url || '')

    event.target.value = ''
  }

  const startNicknameEdit = () => {
    setNicknameInput(data?.user?.nickname || '')
    setNicknameMessage('')
    setIsEditingNickname(true)
  }

  const cancelNicknameEdit = () => {
    setNicknameInput(data?.user?.nickname || '')
    setNicknameMessage('')
    setIsEditingNickname(false)
  }

  const cancelProfileImageEdit = () => {
    setProfileImageFile(null)
    setProfileImagePreviewUrl(data?.user?.profile_image_url || '')
    setProfileImageMessage('')
  }

  const handleUpdateNickname = async (event) => {
    event.preventDefault()
    setNicknameMessage('')

    if (!nicknameInput.trim()) {
      setNicknameMessage('닉네임을 입력해주세요.')
      return
    }

    try {
      setIsUpdatingNickname(true)
      const response = await updateNickname({ nickname: nicknameInput })

      setData((current) => ({ ...current, user: response.data.user }))
      setUser(response.data.user)
      setNicknameMessage('닉네임이 수정되었습니다.')
      setIsEditingNickname(false)
    } catch (error) {
      console.error(error)
      setNicknameMessage(error.response?.data?.nickname?.[0] || '닉네임 수정에 실패했습니다.')
    } finally {
      setIsUpdatingNickname(false)
    }
  }

  const handleUpdateProfileImage = async () => {
    setProfileImageMessage('')

    if (!profileImageFile) {
      setProfileImageMessage('변경할 프로필 사진을 선택해주세요.')
      return
    }

    try {
      setIsUpdatingProfileImage(true)

      const payload = new FormData()
      payload.append('profile_image', profileImageFile)

      const response = await updateProfileImage(payload)

      setData((current) => ({ ...current, user: response.data.user }))
      setUser(response.data.user)
      setProfileImagePreviewUrl(response.data.user.profile_image_url || '')
      setProfileImageFile(null)
      setProfileImageMessage('프로필 사진이 수정되었습니다.')
    } catch (error) {
      console.error(error)
      setProfileImageMessage(
        error.response?.data?.profile_image?.[0] || '프로필 사진 수정에 실패했습니다.',
      )
    } finally {
      setIsUpdatingProfileImage(false)
    }
  }

  return (
    <main className={styles.mypage}>
      <section className={styles.mypageContainer}>
        <header className={styles.pageTitle}>
          <p className={styles.eyebrow}>MY PAGE</p>
          <h1>마이페이지</h1>
        </header>

        {isLoading ? (
          <p className={styles.statusCard}>정보를 불러오는 중입니다.</p>
        ) : errorMessage ? (
          <p className={`${styles.statusCard} ${styles.error}`}>{errorMessage}</p>
        ) : data ? (
          <div className={styles.mypageLayout}>
            <section className={styles.profileCard}>
              <div className={styles.profileMain}>
                <div className={styles.avatarEditRow}>
                  <div className={styles.avatarEditor}>
                    <span className={styles.profileAvatar}>
                      {profileImagePreviewUrl ? (
                        <img src={profileImagePreviewUrl} alt={data.user.nickname} />
                      ) : (
                        <span className={styles.defaultAvatar} aria-hidden="true" />
                      )}
                    </span>
                    <button
                      type="button"
                      className={`${styles.iconEditButton} ${styles.cameraButton}`}
                      aria-label="프로필 사진 수정"
                      disabled={isUpdatingProfileImage}
                      onClick={() => profileImageInputRef.current?.click()}
                    >
                      <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M14.5 4.5 16 7h3a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h3l1.5-2.5h5Z" />
                        <circle cx="12" cy="13" r="3.5" />
                      </svg>
                    </button>
                    <input
                      ref={profileImageInputRef}
                      className={styles.hiddenFileInput}
                      type="file"
                      accept="image/*"
                      onChange={handleProfileImageChange}
                    />
                  </div>

                  <div className={styles.profileImageSide}>
                    {profileImageFile ? (
                      <div className={styles.imageActionButtons}>
                        <button
                          type="button"
                          disabled={isUpdatingProfileImage}
                          onClick={handleUpdateProfileImage}
                        >
                          {isUpdatingProfileImage ? '저장 중' : '저장'}
                        </button>
                        <button
                          type="button"
                          className={styles.ghostButton}
                          disabled={isUpdatingProfileImage}
                          onClick={cancelProfileImageEdit}
                        >
                          취소
                        </button>
                      </div>
                    ) : null}
                    {profileImageMessage ? (
                      <p className={styles.profileImageMessage}>{profileImageMessage}</p>
                    ) : null}
                  </div>
                </div>

                <div className={styles.nicknameEditor}>
                  {isEditingNickname ? (
                    <form className={styles.inlineNicknameForm} onSubmit={handleUpdateNickname}>
                      <input
                        value={nicknameInput}
                        onChange={(event) => setNicknameInput(event.target.value)}
                        type="text"
                        maxLength={50}
                        aria-label="닉네임"
                        autoFocus
                      />
                      <button type="submit" disabled={isUpdatingNickname}>저장</button>
                      <button
                        type="button"
                        className={styles.ghostButton}
                        onClick={cancelNicknameEdit}
                      >
                        취소
                      </button>
                      {nicknameMessage ? (
                        <p className={styles.nicknameMessage}>{nicknameMessage}</p>
                      ) : null}
                    </form>
                  ) : (
                    <div className={styles.nicknameDisplayRow}>
                      <h2>
                        <span style={getNicknameColorStyle(data.user)}>
                          {data.user.nickname}
                        </span>
                        {data.user.tier ? (
                          <img
                            src={getTierIcon(data.user.tier)}
                            alt={data.user.tier_label || data.user.tier}
                            className={styles.profileTierIcon}
                          />
                        ) : null}
                        <button
                          type="button"
                          className={`${styles.iconEditButton} ${styles.pencilButton}`}
                          aria-label="닉네임 수정"
                          onClick={startNicknameEdit}
                        >
                          <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0 0-3l-.5-.5a2.1 2.1 0 0 0-3 0l-10 10L4 20Z" />
                            <path d="m13.5 6.5 4 4" />
                          </svg>
                        </button>
                      </h2>
                      {nicknameMessage ? (
                        <p className={styles.nicknameMessage}>{nicknameMessage}</p>
                      ) : null}
                    </div>
                  )}
                </div>
                <p className={styles.profileUsername}>@{data.user.username}</p>
                <p>{data.user.email || '이메일 없음'}</p>
              </div>
            </section>

            {selectedSection === 'profile' ? (
              <section className={`${styles.panel} ${styles.profilePanel}`}>
                <div className={styles.profileInfoGrid}>
                  <article>
                    <span>닉네임</span>
                    <strong className={styles.profileTierName}>
                      <span style={getNicknameColorStyle(data.user)}>
                        {data.user.nickname}
                      </span>
                      {data.user.tier ? (
                        <img
                          src={getTierIcon(data.user.tier)}
                          alt={data.user.tier_label || data.user.tier}
                          className={styles.infoTierIcon}
                        />
                      ) : null}
                    </strong>
                  </article>
                  <article>
                    <span>내 기여도</span>
                    <strong>
                      기여도 {getUserContribution(data.user)} · 현재 티어 {data.user.tier_label || '아이언'}
                    </strong>
                  </article>
                  <article>
                    <span>아이디</span>
                    <strong>{data.user.username}</strong>
                  </article>
                  <article>
                    <span>이메일</span>
                    <strong>{data.user.email || '이메일 없음'}</strong>
                  </article>
                  <article>
                    <span>가입일</span>
                    <strong>{new Date(data.user.date_joined).toLocaleDateString()}</strong>
                  </article>
                  <article>
                    <span>계정 유형</span>
                    <strong>{data.user.is_staff ? '관리자 계정' : '일반 사용자'}</strong>
                  </article>
                </div>

                <p className={styles.contributionHelp}>
                  게시글, 댓글, 승인된 장소 제보가 기여도에 반영됩니다.
                </p>

                {data.penalty.is_suspended ? (
                  <div className={styles.penaltyDetail}>
                    <strong>
                      {data.penalty.is_permanent_ban ? '영구밴 상태입니다.' : '활동정지 상태입니다.'}
                    </strong>
                    {data.penalty.reason ? <p>사유 {data.penalty.reason}</p> : null}
                    {data.penalty.suspended_until ? (
                      <p>해제일 {new Date(data.penalty.suspended_until).toLocaleString()}</p>
                    ) : null}
                  </div>
                ) : null}

                <div className={styles.summaryGrid}>
                  <Link to="/mypage?section=saved" className={styles.summaryCard}>
                    <strong>{savedPlaceCount}</strong>
                    <span>저장장소</span>
                  </Link>
                  <Link to="/mypage?section=posts" className={styles.summaryCard}>
                    <strong>{data.posts.length}</strong>
                    <span>작성글</span>
                  </Link>
                  <Link to="/mypage?section=comments" className={styles.summaryCard}>
                    <strong>{data.comments.length}</strong>
                    <span>작성댓글</span>
                  </Link>
                  <Link to="/mypage?section=liked" className={styles.summaryCard}>
                    <strong>{data.liked_posts.length}</strong>
                    <span>좋아요한글</span>
                  </Link>
                </div>

                <section className={styles.searchHistorySection}>
                  <div className={styles.sectionHeadingRow}>
                    <div>
                      <h2>최근 검색 기록</h2>
                      <p>이전에 찾았던 장소 조건을 다시 검색할 수 있습니다.</p>
                    </div>
                    <div className={styles.sectionActionRow}>
                      <Link to="/mypage/search-history" className={styles.refreshHistoryButton}>
                        검색 기록 관리
                      </Link>
                      <button
                        type="button"
                        className={styles.refreshHistoryButton}
                        onClick={fetchRecentSearchLogs}
                      >
                        새로고침
                      </button>
                    </div>
                  </div>

                  {isLoadingSearchLogs ? (
                    <p className={`${styles.empty} ${styles.searchHistoryStatus}`}>
                      검색 기록을 불러오는 중입니다.
                    </p>
                  ) : searchLogs.length ? (
                    <div className={styles.searchHistoryList}>
                      {searchLogs.map((log) => {
                        const chips = getSearchLogChips(log)

                        return (
                          <article key={log.id} className={styles.searchHistoryItem}>
                            <strong>{log.query}</strong>
                            <span>{getSearchLogMeta(log)}</span>
                            <time>{formatSearchLogDate(log.created_at)}</time>
                            {chips.length ? (
                              <span className={styles.searchLogChipRow}>
                                {chips.map((chip) => (
                                  <span key={chip} className={styles.searchLogChip}>{chip}</span>
                                ))}
                              </span>
                            ) : null}
                            <span className={styles.searchHistoryActions}>
                              <button type="button" onClick={() => rerunSearchLog(log)}>
                                다시 검색
                              </button>
                              <button
                                type="button"
                                className={styles.danger}
                                onClick={() => handleDeleteSearchLog(log)}
                              >
                                삭제
                              </button>
                            </span>
                          </article>
                        )
                      })}
                    </div>
                  ) : (
                    <div className={`${styles.empty} ${styles.searchHistoryStatus}`}>
                      <p>{searchLogMessage}</p>
                      {searchLogMessage === '아직 저장된 검색 기록이 없습니다.' ? (
                        <p>장소를 검색하면 최근 검색 기록이 이곳에 표시됩니다.</p>
                      ) : null}
                    </div>
                  )}
                </section>

                <section className={styles.preferenceSection}>
                  <div className={styles.sectionHeadingRow}>
                    <div>
                      <h2>내 선호 요약</h2>
                      <p>추천에 반영되는 선호를 간단히 확인할 수 있습니다.</p>
                    </div>
                    <Link to="/mypage/preferences" className={styles.refreshHistoryButton}>
                      선호 태그 설정하기
                    </Link>
                  </div>

                  {isLoadingPreferences ? (
                    <p className={`${styles.empty} ${styles.preferenceStatus}`}>
                      선호 키워드를 불러오는 중입니다.
                    </p>
                  ) : userPreferences.length ? (
                    <div className={styles.preferenceList}>
                      {userPreferences.map((preference) => (
                        <article key={preference.id} className={styles.preferenceItem}>
                          <span className={styles.preferenceBadgeRow}>
                            <span
                              className={`${styles.preferenceSourceBadge} ${
                                isUserSelectedPreference(preference)
                                  ? styles.isUserSelected
                                  : styles.isSearchLog
                              }`}
                            >
                              {getPreferenceSourceLabel(preference)}
                            </span>
                            <span className={styles.preferenceTypeBadge}>
                              {getPreferenceTypeLabel(preference.preference_type)}
                            </span>
                          </span>
                          <strong>{getPreferenceLabel(preference)}</strong>
                          <span className={styles.preferenceMeta}>
                            {getPreferenceMeta(preference)}
                          </span>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className={`${styles.empty} ${styles.preferenceStatus}`}>
                      {preferenceMessage || '검색하거나 선호 태그를 선택하면 이곳에 표시됩니다.'}
                    </p>
                  )}
                </section>

                <section className={styles.preferenceSection}>
                  <div className={styles.sectionHeadingRow}>
                    <div>
                      <h2>장소 정보 제보</h2>
                      <p>장소 정보나 태그 오류를 제보하고 검토 상태를 확인할 수 있습니다.</p>
                    </div>
                    <div className={styles.sectionActionRow}>
                      <Link to="/place-report" className={styles.refreshHistoryButton}>
                        제보 작성
                      </Link>
                      <Link to="/mypage/reports" className={styles.refreshHistoryButton}>
                        내 제보 현황
                      </Link>
                    </div>
                  </div>
                </section>
              </section>
            ) : selectedSection === 'saved' ? (
              <SavedPlacesPanel
                places={savedPlaces}
                isLoading={isLoadingSavedPlaces}
                message={savedPlaceMessage}
                editingPlaceId={editingSavedPlaceId}
                memoInput={savedPlaceMemoInput}
                updatingPlaceId={updatingSavedPlaceId}
                onRefresh={fetchSavedPlaces}
                onStartMemoEdit={startSavedPlaceMemoEdit}
                onCancelMemoEdit={cancelSavedPlaceMemoEdit}
                onSaveMemo={handleUpdateSavedPlaceMemo}
                onDeletePlace={handleDeleteSavedPlace}
                onMemoInputChange={setSavedPlaceMemoInput}
              />
            ) : selectedSection === 'posts' ? (
              <section className={styles.panel}>
                <h2>내가 쓴 글</h2>
                {data.posts.map((post) => (
                  <Link
                    key={post.id}
                    to={`/boards/${post.board_type}/${post.id}`}
                    className={`${styles.activityItem} ${styles.linkItem}`}
                  >
                    <strong>{post.title}</strong>
                    <span>댓글 {post.comments_count} · 좋아요 {post.likes_count}</span>
                  </Link>
                ))}
                {data.posts.length === 0 ? (
                  <p className={styles.empty}>작성한 글이 없습니다.</p>
                ) : null}
              </section>
            ) : selectedSection === 'comments' ? (
              <section className={styles.panel}>
                <h2>내가 쓴 댓글</h2>
                {data.comments.map((comment) => (
                  <Link
                    key={comment.id}
                    to={`/boards/${comment.post_board_type}/${comment.post}#comment-${comment.id}`}
                    className={`${styles.activityItem} ${styles.linkItem}`}
                  >
                    <strong>{comment.content}</strong>
                    <span>
                      {comment.post_title} · {new Date(comment.created_at).toLocaleDateString()}
                    </span>
                  </Link>
                ))}
                {data.comments.length === 0 ? (
                  <p className={styles.empty}>작성한 댓글이 없습니다.</p>
                ) : null}
              </section>
            ) : selectedSection === 'liked' ? (
              <section className={styles.panel}>
                <h2>내가 좋아요한 글</h2>
                {data.liked_posts.map((post) => (
                  <Link
                    key={post.id}
                    to={`/boards/${post.board_type}/${post.id}`}
                    className={`${styles.activityItem} ${styles.linkItem}`}
                  >
                    <strong>{post.title}</strong>
                    <span className={styles.activityMetaLine}>
                      {post.author_nickname}
                      {post.author_tier ? (
                        <img
                          src={getTierIcon(post.author_tier)}
                          alt={post.author_tier_label || post.author_tier}
                          className={styles.activityTierIcon}
                        />
                      ) : null}
                      {` · 댓글 ${post.comments_count} · 좋아요 ${post.likes_count}`}
                    </span>
                  </Link>
                ))}
                {data.liked_posts.length === 0 ? (
                  <p className={styles.empty}>좋아요한 글이 없습니다.</p>
                ) : null}
              </section>
            ) : (
              <section className={styles.panel}>
                <h2>내 문의내역</h2>
                {data.inquiries.map((inquiry) => (
                  <div key={inquiry.id} className={styles.activityItem}>
                    <strong>{inquiry.title}</strong>
                    <span>{inquiry.status === 'answered' ? '답변 완료' : '답변 대기'}</span>
                    {inquiry.admin_reply ? <p>{inquiry.admin_reply}</p> : null}
                  </div>
                ))}
                {data.inquiries.length === 0 ? (
                  <p className={styles.empty}>작성한 문의가 없습니다.</p>
                ) : null}
              </section>
            )}
          </div>
        ) : null}
      </section>
    </main>
  )
}

export default MypageView
