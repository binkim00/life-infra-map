import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { searchMapPlaces } from '@/api/recommendation'
import KakaoMap from '@/components/KakaoMap'
import { useSavedPlaceActions } from '@/hooks/useSavedPlaceActions'

import styles from './MapSearchView.module.css'

const DEFAULT_CENTER = {
  lat: 35.1796,
  lng: 129.0756,
}

const SOURCE_OPTIONS = [
  { value: 'all', label: '전체' },
  { value: 'db', label: '저장 장소' },
  { value: 'kakao', label: '카카오' },
]

const SOURCE_META = {
  db: {
    label: '저장 장소',
    color: '#2563eb',
    className: 'sourceDb',
  },
  kakao: {
    label: '카카오 장소',
    color: '#ef4444',
    className: 'sourceKakao',
  },
}

const toNumber = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

const toArray = (value) => (Array.isArray(value) ? value : [])

const getSourceMeta = (place = {}) => SOURCE_META[place?.resultSource] || SOURCE_META.db

const formatDistance = (distance) => {
  const value = Number(distance)
  if (!Number.isFinite(value)) return ''
  if (value >= 1000) return `${(value / 1000).toFixed(1)}km`
  return `${Math.round(value)}m`
}

const getAddress = (place = {}) => place.address || place.detailLocation || ''

const getDetailUrl = (place = {}) => (
  place.detailUrl || place.placeUrl || place.kakaoPlaceUrl || ''
)

const getNavigationUrl = (place = {}) => {
  if (place.navigationUrl) return place.navigationUrl
  if (!place.lat || !place.lng) return ''
  return `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`
}

const getTagName = (tag) => {
  if (typeof tag === 'string') return tag
  return tag?.name || tag?.label || ''
}

const normalizeTags = (place = {}) => {
  const tags = []
  const category = place.categoryLabel || place.category
  if (category) {
    tags.push({ name: category, source: 'category' })
  }

  toArray(place.tags).forEach((tag) => {
    const name = getTagName(tag)
    if (name && !tags.some((item) => item.name === name)) {
      tags.push({
        name,
        source: tag?.source || 'tag',
      })
    }
  })

  return tags
}

const normalizePlace = (place, index) => {
  const resultSource = place.result_source || place.resultSource || 'db'
  const sourceMeta = SOURCE_META[resultSource] || SOURCE_META.db
  const lat = toNumber(place.lat)
  const lng = toNumber(place.lng)
  const sourceId = place.external_id || place.id || index
  const id = `${resultSource}-${sourceId}`

  return {
    id,
    savedPlaceId: resultSource === 'db' ? place.id : null,
    externalId: place.external_id || '',
    resultSource,
    sourceLabel: place.source_label || sourceMeta.label,
    source: place.source || resultSource,
    sourceName: place.source_name || '',
    name: place.name || '장소명 없음',
    category: place.category_label || place.category || '',
    categoryLabel: place.category_label || '',
    address: place.address || '',
    detailLocation: place.detail_location || '',
    phone: place.phone || '',
    lat,
    lng,
    distance: place.distance ?? null,
    tags: normalizeTags(place),
    markerLabel: String(index + 1),
    markerColor: sourceMeta.color,
    searchSource: resultSource === 'kakao' ? 'kakao' : 'local_db',
    placeUrl: place.place_url || place.kakao_place_url || '',
    kakaoPlaceUrl: place.kakao_place_url || place.place_url || '',
    detailUrl: place.place_url || place.kakao_place_url || '',
    navigationUrl: lat && lng
      ? `https://map.kakao.com/link/to/${encodeURIComponent(place.name || '장소')},${lat},${lng}`
      : '',
    dataQualityStatus: place.data_quality_status || '',
    dataQualityScore: place.data_quality_score ?? null,
    duplicateCount: Number(place.duplicate_count) || 1,
  }
}

const MapSearchView = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const initialQueryRef = useRef(searchParams.get('q')?.trim() || '')
  const {
    savingPlaceId,
    saveMessage,
    isPlaceSaved,
    loadSavedPlaceKeys,
    savePlace: handleSavePlace,
  } = useSavedPlaceActions()

  const [query, setQuery] = useState(initialQueryRef.current)
  const [source, setSource] = useState('all')
  const [places, setPlaces] = useState([])
  const [selectedPlace, setSelectedPlace] = useState(null)
  const [fitBoundsKey, setFitBoundsKey] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState(
    '장소명, 주소, 업종을 빠르게 검색할 수 있어요.',
  )
  const [counts, setCounts] = useState({ db: 0, kakao: 0, db_total: 0 })
  const [droppedTokens, setDroppedTokens] = useState([])
  const [excludedTokens, setExcludedTokens] = useState([])

  // 지도 중심은 검색 파라미터로만 쓰이므로 렌더를 다시 돌릴 이유가 없습니다.
  const mapCenterRef = useRef({ ...DEFAULT_CENTER })
  const [mapCenter] = useState({ ...DEFAULT_CENTER })

  useEffect(() => {
    loadSavedPlaceKeys()
  }, [loadSavedPlaceKeys])

  const hasResults = places.length > 0
  const selectedSourceMeta = useMemo(() => getSourceMeta(selectedPlace), [selectedPlace])

  const runSearch = async (event) => {
    event?.preventDefault?.()

    setIsLoading(true)
    setSelectedPlace(null)
    setMessage('장소 데이터를 찾는 중입니다.')

    try {
      const data = await searchMapPlaces({
        q: query.trim(),
        source,
        lat: mapCenterRef.current.lat,
        lng: mapCenterRef.current.lng,
        limit: 40,
      })

      setCounts(data.candidate_counts || { db: 0, kakao: 0, db_total: 0 })
      setDroppedTokens(toArray(data.query_info?.dropped_tokens))
      setExcludedTokens(toArray(data.query_info?.exclude_tokens))

      const nextPlaces = toArray(data.results)
        .filter((place) => toNumber(place.lat) !== null && toNumber(place.lng) !== null)
        .map(normalizePlace)

      setPlaces(nextPlaces)
      setFitBoundsKey((current) => current + 1)

      let nextMessage

      if (nextPlaces.length) {
        nextMessage = `${nextPlaces.length}곳을 찾았어요.`
      } else if (!query.trim()) {
        nextMessage = '검색어를 입력하거나 지도 중심 기준으로 저장 장소를 둘러보세요.'
      } else {
        nextMessage = '조건에 맞는 장소를 찾지 못했어요. 검색어를 줄이거나 지도를 옮겨 다시 검색해 보세요.'
      }

      if (data.kakao_error) {
        nextMessage = `${nextMessage} 카카오 결과는 잠시 불러오지 못했습니다.`
      }

      setMessage(nextMessage)
    } catch (error) {
      console.error(error)
      setPlaces([])
      setCounts({ db: 0, kakao: 0, db_total: 0 })
      setDroppedTokens([])
      setExcludedTokens([])
      setMessage('지도 검색을 불러오지 못했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!initialQueryRef.current) return
    initialQueryRef.current = ''
    runSearch()
    // URL에서 전달된 최초 검색어는 화면 진입 시 한 번만 실행합니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleCenterChange = ({ center }) => {
    if (!center) return
    mapCenterRef.current = {
      lat: center.lat,
      lng: center.lng,
    }
  }

  const goToPlaceReport = (place) => {
    const queryParams = new URLSearchParams({
      reportType: place.savedPlaceId ? 'tag_suggestion' : 'new_place',
      name: place.name,
      category: place.category,
      address: getAddress(place),
    })

    if (place.savedPlaceId) {
      queryParams.set('placeId', place.savedPlaceId)
    }
    if (place.lat) {
      queryParams.set('lat', Number(place.lat).toFixed(6))
    }
    if (place.lng) {
      queryParams.set('lng', Number(place.lng).toFixed(6))
    }

    navigate(`/place-report?${queryParams.toString()}`)
  }

  return (
    <main className={styles.mapSearchPage}>
      <section className={`${styles.mapSearchShell}${selectedPlace ? ` ${styles.hasDetail}` : ''}`}>
        <aside className={styles.mapSearchPanel}>
          <header className={styles.mapSearchHeader}>
            <p>일반 지도 검색</p>
            <h1>장소 데이터 검색</h1>
            <span>AI 해석 없이 저장 장소와 카카오 장소를 그대로 찾습니다.</span>
          </header>

          <form className={styles.mapSearchForm} onSubmit={runSearch}>
            <label>
              <span>검색어</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                type="search"
                placeholder="예: 서면역 약국, 광안리 주차장, 부산시청"
              />
            </label>

            <div className={styles.mapSearchControls}>
              <label>
                <span>출처</span>
                <select value={source} onChange={(event) => setSource(event.target.value)}>
                  {SOURCE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <button type="submit" disabled={isLoading}>
              {isLoading ? '검색 중' : '현재 지도에서 검색'}
            </button>
          </form>

          <div className={styles.mapSearchStatus}>
            <strong>{message}</strong>
            {hasResults ? (
              <span>저장 장소 {counts.db || 0}곳 · 카카오 {counts.kakao || 0}곳</span>
            ) : null}
            {excludedTokens.length ? (
              <span className={styles.queryNote}>제외한 조건: {excludedTokens.join(', ')}</span>
            ) : null}
            {droppedTokens.length ? (
              <span className={styles.queryNote}>
                저장된 장소에 없는 표현이라 빼고 검색했어요: {droppedTokens.join(', ')}
              </span>
            ) : null}
          </div>

          <div className={styles.mapSourceLegend} aria-label="마커 색상 안내">
            <span><i className={`${styles.legendDot} ${styles.db}`} />저장 장소</span>
            <span><i className={`${styles.legendDot} ${styles.kakao}`} />카카오</span>
          </div>

          <section className={styles.mapResultList} aria-label="장소 검색 결과">
            {places.map((place) => (
              <article
                key={place.id}
                className={`${styles.mapResultItem}${selectedPlace?.id === place.id ? ` ${styles.active}` : ''}`}
              >
                <button type="button" onClick={() => setSelectedPlace(place)}>
                  <span className={`${styles.resultMarker} ${styles[getSourceMeta(place).className]}`}>
                    {place.markerLabel}
                  </span>
                  <span className={styles.resultMain}>
                    <span className={styles.resultTitleRow}>
                      <strong>{place.name}</strong>
                      <small className={`${styles.sourceChip} ${styles[getSourceMeta(place).className]}`}>
                        {place.sourceLabel}
                      </small>
                    </span>
                    <span className={styles.resultMeta}>
                      {place.category ? <small>{place.category}</small> : null}
                      {formatDistance(place.distance) ? (
                        <small>{formatDistance(place.distance)}</small>
                      ) : null}
                      {place.duplicateCount > 1 ? (
                        <small>같은 이름 {place.duplicateCount}곳</small>
                      ) : null}
                    </span>
                    {getAddress(place) ? (
                      <span className={styles.resultAddress}>{getAddress(place)}</span>
                    ) : null}
                  </span>
                </button>
              </article>
            ))}
          </section>
        </aside>

        <section className={styles.mapSearchMapArea}>
          <button
            type="button"
            className={styles.mapResearchButton}
            disabled={isLoading}
            onClick={runSearch}
          >
            {isLoading ? '검색 중' : '현재 지도에서 재검색'}
          </button>
          <KakaoMap
            places={places}
            center={mapCenter}
            selectedPlaceId={selectedPlace?.id || null}
            selectedPlace={selectedPlace}
            fitBoundsKey={fitBoundsKey}
            onSelectPlace={setSelectedPlace}
            onCenterChange={handleCenterChange}
          />
        </section>

        {selectedPlace ? (
          <aside className={styles.mapDetailPanel}>
            <div className={styles.mapDetailTop}>
              <div>
                <span className={`${styles.sourceChip} ${styles[selectedSourceMeta.className]}`}>
                  {selectedPlace.sourceLabel}
                </span>
                <h2>{selectedPlace.name}</h2>
              </div>
              <button type="button" onClick={() => setSelectedPlace(null)}>닫기</button>
            </div>

            {selectedPlace.tags.length ? (
              <div className={styles.mapDetailTags}>
                {selectedPlace.tags.map((tag) => (
                  <span key={`${selectedPlace.id}-${tag.name}`}>{tag.name}</span>
                ))}
              </div>
            ) : null}

            {getDetailUrl(selectedPlace) ? (
              <section className={styles.mapDetailFrame}>
                <iframe
                  src={getDetailUrl(selectedPlace)}
                  title="카카오맵 장소 상세페이지"
                  scrolling="no"
                  referrerPolicy="no-referrer-when-downgrade"
                />
              </section>
            ) : null}

            <dl className={styles.mapDetailInfo}>
              {selectedPlace.category ? (
                <div><dt>분류</dt><dd>{selectedPlace.category}</dd></div>
              ) : null}
              {getAddress(selectedPlace) ? (
                <div><dt>주소</dt><dd>{getAddress(selectedPlace)}</dd></div>
              ) : null}
              {formatDistance(selectedPlace.distance) ? (
                <div>
                  <dt>거리</dt>
                  <dd>지도 중심에서 {formatDistance(selectedPlace.distance)}</dd>
                </div>
              ) : null}
              {selectedPlace.phone ? (
                <div><dt>전화</dt><dd>{selectedPlace.phone}</dd></div>
              ) : null}
              {selectedPlace.dataQualityStatus ? (
                <div><dt>상태</dt><dd>{selectedPlace.dataQualityStatus}</dd></div>
              ) : null}
            </dl>

            <div className={styles.mapDetailActions}>
              <button
                type="button"
                className={styles.save}
                disabled={savingPlaceId === selectedPlace.id || isPlaceSaved(selectedPlace)}
                onClick={() => handleSavePlace(selectedPlace)}
              >
                {isPlaceSaved(selectedPlace)
                  ? '저장됨'
                  : savingPlaceId === selectedPlace.id ? '저장 중' : '장소 저장'}
              </button>
              <button type="button" onClick={() => goToPlaceReport(selectedPlace)}>
                정보 제보
              </button>
              {getDetailUrl(selectedPlace) ? (
                <a
                  href={getDetailUrl(selectedPlace)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  카카오맵 보기
                </a>
              ) : null}
              {getNavigationUrl(selectedPlace) ? (
                <a
                  href={getNavigationUrl(selectedPlace)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.primary}
                >
                  길찾기
                </a>
              ) : null}
            </div>
            {saveMessage ? <p className={styles.mapSaveMessage}>{saveMessage}</p> : null}
          </aside>
        ) : null}
      </section>
    </main>
  )
}

export default MapSearchView
