import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { createPlaceReport } from '@/api/recommendation'
import { loadKakaoMapScript } from '@/hooks/useKakaoMapSdk'
import { useAuthStore } from '@/stores/auth'

import styles from './PlaceReportView.module.css'

const REPORT_TYPE_OPTIONS = [
  { value: 'new_place', label: '새로운 장소 제보' },
  { value: 'tag_suggestion', label: '태그 추가 제보' },
  { value: 'wrong_info', label: '잘못된 정보 제보' },
  { value: 'edit_place', label: '장소 정보 수정 제보' },
]

const TAG_OPTIONS = [
  '조용함',
  '노트북 작업 가능',
  '콘센트 있음',
  '와이파이 있음',
  '혼자 이용 좋음',
  '잠깐 쉬기 좋음',
  '산책하기 좋음',
  '야경 보기 좋음',
  '주차 가능',
  '실내 이용 가능',
]

const ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
const MAX_IMAGE_SIZE = 5 * 1024 * 1024

const normalizeCoordinate = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue.toFixed(6) : ''
}

const normalizeTagList = (selected = [], extraText = '') => {
  const extraTags = String(extraText || '')
    .split(/[,\n]/)
    .map((tag) => tag.trim())
    .filter(Boolean)

  return [...new Set([...selected, ...extraTags].map((tag) => tag.trim()).filter(Boolean))]
}

const getCategoryLabel = (categoryName = '') => {
  const parts = String(categoryName || '')
    .split('>')
    .map((part) => part.trim())
    .filter(Boolean)

  return parts.at(-1) || String(categoryName || '').trim()
}

const getSearchResultAddress = (place) => place.road_address_name || place.address_name || ''

const PlaceReportView = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const getQueryValue = useCallback((...keys) => {
    for (const key of keys) {
      const value = searchParams.get(key)
      if (value) return String(value)
    }
    return ''
  }, [searchParams])

  const initialPlaceId = getQueryValue('placeId', 'place')
  const initialName = getQueryValue('name', 'placeName', 'suggestedName')
  const initialAddress = getQueryValue('address', 'suggestedAddress')
  const initialLat = normalizeCoordinate(getQueryValue('lat', 'suggestedLat'))
  const initialLng = normalizeCoordinate(getQueryValue('lng', 'suggestedLng'))
  const hasInitialTarget = Boolean(
    initialPlaceId || initialName || initialAddress || (initialLat && initialLng),
  )
  const incomingReportType = getQueryValue('reportType', 'type')
  const isAllowedType = REPORT_TYPE_OPTIONS.some((option) => option.value === incomingReportType)

  const [reportType, setReportType] = useState(() => (
    isAllowedType ? incomingReportType : (hasInitialTarget ? 'tag_suggestion' : 'new_place')
  ))
  const [placeId, setPlaceId] = useState(initialPlaceId)
  const [suggestedName, setSuggestedName] = useState(initialName)
  const [suggestedCategory, setSuggestedCategory] = useState(
    getQueryValue('category', 'suggestedCategory'),
  )
  const [suggestedAddress, setSuggestedAddress] = useState(initialAddress)
  const [suggestedLat, setSuggestedLat] = useState(initialLat)
  const [suggestedLng, setSuggestedLng] = useState(initialLng)
  const [selectedTags, setSelectedTags] = useState([])
  const [extraTagsText, setExtraTagsText] = useState('')
  const [description, setDescription] = useState('')
  const [images, setImages] = useState([])
  const [message, setMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [mapStatusMessage, setMapStatusMessage] = useState('')
  const [placeSearchKeyword, setPlaceSearchKeyword] = useState(initialName || initialAddress || '')
  const [placeSearchResults, setPlaceSearchResults] = useState([])
  const [placeSearchMessage, setPlaceSearchMessage] = useState('')
  const [isSearchingPlace, setIsSearchingPlace] = useState(false)

  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)
  const geocoderRef = useRef(null)
  const placesRef = useRef(null)
  const pendingTimeoutsRef = useRef(new Set())
  const isDestroyedRef = useRef(false)

  // 지도 클릭 핸들러가 최신 상태를 봐야 해서 ref 로 함께 들고 있습니다.
  const stateRef = useRef({})
  stateRef.current = { placeId, suggestedAddress, reportType }

  const isNewPlaceReport = reportType === 'new_place'
  const isTagSuggestionReport = reportType === 'tag_suggestion'
  const hasTargetPlace = Boolean(
    placeId || suggestedName || suggestedAddress || (suggestedLat && suggestedLng),
  )

  const selectedTagsPreview = useMemo(
    () => normalizeTagList(selectedTags, extraTagsText),
    [selectedTags, extraTagsText],
  )

  const selectedLocationSummary = suggestedAddress
    || (suggestedLat && suggestedLng ? `선택 좌표: ${suggestedLat}, ${suggestedLng}` : '')

  const setManagedTimeout = useCallback((callback, delay) => {
    const timeoutId = window.setTimeout(() => {
      pendingTimeoutsRef.current.delete(timeoutId)
      if (isDestroyedRef.current) return
      callback()
    }, delay)

    pendingTimeoutsRef.current.add(timeoutId)
  }, [])

  const reverseGeocodeSelection = useCallback((lat, lng) => {
    if (!geocoderRef.current || !window.kakao?.maps?.services) return

    geocoderRef.current.coord2Address(lng, lat, (result, status) => {
      if (isDestroyedRef.current) return

      if (status === window.kakao.maps.services.Status.OK && result?.[0]) {
        const address = result[0].road_address?.address_name
          || result[0].address?.address_name
          || ''
        setSuggestedAddress(address)
      }
    })
  }, [])

  const setMapSelection = useCallback((latLng, { reverseGeocode = true } = {}) => {
    const lat = latLng.getLat()
    const lng = latLng.getLng()

    setSuggestedLat(normalizeCoordinate(lat))
    setSuggestedLng(normalizeCoordinate(lng))

    if (!markerRef.current) {
      markerRef.current = new window.kakao.maps.Marker({
        map: mapRef.current,
        position: latLng,
      })
    } else {
      markerRef.current.setPosition(latLng)
    }

    mapRef.current?.setCenter(latLng)

    if (reverseGeocode) {
      reverseGeocodeSelection(lat, lng)
    }
  }, [reverseGeocodeSelection])

  const initializeReportMap = useCallback(async () => {
    if (!mapContainerRef.current) return

    try {
      await loadKakaoMapScript()

      if (isDestroyedRef.current) return

      if (mapRef.current) {
        setManagedTimeout(() => mapRef.current?.relayout(), 80)
        return
      }

      const startLat = Number(suggestedLat) || 36.35
      const startLng = Number(suggestedLng) || 127.8
      const center = new window.kakao.maps.LatLng(startLat, startLng)

      mapRef.current = new window.kakao.maps.Map(mapContainerRef.current, {
        center,
        level: 4,
      })
      geocoderRef.current = new window.kakao.maps.services.Geocoder()
      placesRef.current = new window.kakao.maps.services.Places()

      window.kakao.maps.event.addListener(mapRef.current, 'click', (mouseEvent) => {
        setSuggestedAddress('')
        if (!stateRef.current.placeId && stateRef.current.reportType !== 'new_place') {
          setSuggestedName('')
        }
        setMapSelection(mouseEvent.latLng)
      })

      if (suggestedLat && suggestedLng) {
        setMapSelection(center, { reverseGeocode: !suggestedAddress })
      }

      setMapStatusMessage('')
      setManagedTimeout(() => mapRef.current?.relayout(), 80)
    } catch (error) {
      setMapStatusMessage(error.message || '지도를 불러오지 못했습니다.')
    }
    // 최초 좌표는 초기화 시점 값만 쓰므로 의존성에 넣지 않습니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setMapSelection, setManagedTimeout])

  useEffect(() => {
    if (!useAuthStore.getState().isLoggedIn) {
      navigate('/login')
      return undefined
    }

    isDestroyedRef.current = false
    initializeReportMap()

    const pendingTimeouts = pendingTimeoutsRef.current

    return () => {
      isDestroyedRef.current = true
      pendingTimeouts.forEach((timeoutId) => window.clearTimeout(timeoutId))
      pendingTimeouts.clear()
      markerRef.current?.setMap(null)
      mapRef.current = null
      markerRef.current = null
      geocoderRef.current = null
      placesRef.current = null
    }
  }, [navigate, initializeReportMap])

  // 제보 유형을 바꾸면 지도 영역이 다시 붙으므로 크기를 다시 잡아 줍니다.
  useEffect(() => {
    if (!mapRef.current) return
    setManagedTimeout(() => mapRef.current?.relayout(), 80)
  }, [reportType, setManagedTimeout])

  const toggleTag = (tag) => {
    setSelectedTags((current) => (
      current.includes(tag)
        ? current.filter((item) => item !== tag)
        : [...current, tag]
    ))
  }

  const handleImageChange = (event) => {
    const selectedFiles = Array.from(event.target.files || [])
    let nextMessage = ''

    setImages((current) => {
      const nextImages = [...current]

      for (const file of selectedFiles) {
        const extension = file.name.split('.').pop()?.toLowerCase()

        if (!ALLOWED_EXTENSIONS.includes(extension)) {
          nextMessage = 'jpg, jpeg, png, webp 이미지만 첨부할 수 있습니다.'
          continue
        }
        if (file.size > MAX_IMAGE_SIZE) {
          nextMessage = '이미지는 1개당 최대 5MB까지 첨부할 수 있습니다.'
          continue
        }
        if (nextImages.length >= 3) {
          nextMessage = '이미지는 최대 3장까지 첨부할 수 있습니다.'
          break
        }

        nextImages.push(file)
      }

      return nextImages
    })

    setMessage(nextMessage)
    event.target.value = ''
  }

  const removeImage = (index) => {
    setImages((current) => current.filter((_, itemIndex) => itemIndex !== index))
  }

  const applyPlaceSearchResult = (place) => {
    const lat = Number(place.y)
    const lng = Number(place.x)

    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      setPlaceSearchMessage('선택한 장소의 좌표를 확인할 수 없습니다.')
      return
    }

    const latLng = new window.kakao.maps.LatLng(lat, lng)
    const nextAddress = getSearchResultAddress(place)

    setPlaceId('')
    setSuggestedName((current) => place.place_name || current)
    setSuggestedCategory((current) => getCategoryLabel(place.category_name) || current)
    setSuggestedAddress(nextAddress)
    setPlaceSearchKeyword((current) => place.place_name || current)
    setPlaceSearchResults([])
    setPlaceSearchMessage('')

    setMapSelection(latLng, { reverseGeocode: !nextAddress })
  }

  const searchReportPlaces = async () => {
    const keyword = placeSearchKeyword.trim()

    if (!keyword) {
      setPlaceSearchMessage('검색할 장소명이나 주소를 입력해 주세요.')
      return
    }

    await initializeReportMap()

    if (!placesRef.current || !window.kakao?.maps?.services) {
      setPlaceSearchMessage('장소 검색을 사용할 수 없습니다.')
      return
    }

    setIsSearchingPlace(true)
    setPlaceSearchMessage('')

    const options = mapRef.current ? { location: mapRef.current.getCenter() } : {}

    placesRef.current.keywordSearch(
      keyword,
      (data, status) => {
        if (isDestroyedRef.current) return

        setIsSearchingPlace(false)

        if (status === window.kakao.maps.services.Status.OK) {
          const results = data.slice(0, 5)
          setPlaceSearchResults(results)
          setPlaceSearchMessage(results.length ? '' : '검색 결과가 없습니다.')
          return
        }

        setPlaceSearchResults([])
        setPlaceSearchMessage(
          status === window.kakao.maps.services.Status.ZERO_RESULT
            ? '검색 결과가 없습니다.'
            : '장소 검색 중 오류가 발생했습니다.',
        )
      },
      options,
    )
  }

  const buildFormData = () => {
    const formData = new FormData()
    formData.append('report_type', reportType)

    if (!isNewPlaceReport && placeId) {
      formData.append('place', placeId)
    }

    if (suggestedName) formData.append('suggested_name', suggestedName)
    if (suggestedCategory) formData.append('suggested_category', suggestedCategory)
    if (suggestedAddress) formData.append('suggested_address', suggestedAddress)
    if (suggestedLat) formData.append('suggested_lat', suggestedLat)
    if (suggestedLng) formData.append('suggested_lng', suggestedLng)
    if (description) formData.append('description', description)

    const tags = isTagSuggestionReport ? selectedTagsPreview : []
    formData.append('suggested_tags', JSON.stringify(tags))
    images.forEach((file) => formData.append('images', file))
    return formData
  }

  const validateReport = () => {
    if (isNewPlaceReport) {
      if (!suggestedName.trim()) return '새로운 장소명을 입력해 주세요.'
      if (!suggestedCategory.trim()) return '새로운 장소의 카테고리를 입력해 주세요.'
      if (!suggestedLat || !suggestedLng) {
        return '새로운 장소를 제보하려면 지도에서 위치를 선택해 주세요.'
      }
    } else if (!hasTargetPlace) {
      return '제보 대상 장소를 검색하거나 지도에서 위치를 선택해 주세요.'
    }

    if (!description.trim()) {
      return '제보 내용을 입력해 주세요.'
    }

    return ''
  }

  const submitReport = async (event) => {
    event.preventDefault()
    setMessage('')

    const validationMessage = validateReport()
    if (validationMessage) {
      setMessage(validationMessage)
      return
    }

    try {
      setIsSubmitting(true)
      await createPlaceReport(buildFormData())
      setMessage('제보가 접수되었습니다. 관리자 검토 후 반영됩니다.')
      navigate('/mypage/reports')
    } catch (error) {
      const data = error.response?.data
      setMessage(
        data?.detail
        || data?.non_field_errors?.[0]
        || Object.values(data || {})?.flat?.()?.[0]
        || '제보 접수에 실패했습니다.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  const targetPlaceTitle = suggestedName
    || (placeId ? `장소 ID ${placeId}` : '제보 대상 장소')

  return (
    <main className={styles.reportPage}>
      <section className={styles.reportContainer}>
        <header className={styles.pageTitle}>
          <Link to="/" className={styles.backLink}>홈으로 돌아가기</Link>
          <p className={styles.eyebrow}>PLACE REPORT</p>
          <h1>장소 정보 제보</h1>
          <p>제보 내용은 바로 반영되지 않고 관리자 검토 후 처리됩니다.</p>
        </header>

        <form className={`${styles.panel} ${styles.reportForm}`} onSubmit={submitReport}>
          <label className={styles.formField}>
            <span>제보 유형</span>
            <select value={reportType} onChange={(event) => setReportType(event.target.value)}>
              {REPORT_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>

          {!isNewPlaceReport ? (
            <section className={styles.targetPlaceCard}>
              <div>
                <p className={styles.sectionLabel}>제보 대상 장소</p>
                <h2>{targetPlaceTitle}</h2>
                {suggestedAddress ? (
                  <p>{suggestedAddress}</p>
                ) : placeId ? (
                  <p>선택한 DB 장소에 대한 제보입니다.</p>
                ) : (
                  <p>검색 결과 카드에서 장소 정보를 전달받지 못했습니다.</p>
                )}
              </div>
              <span className={styles.targetIdChip}>
                {placeId ? `ID ${placeId}` : '외부 후보'}
              </span>
            </section>
          ) : null}

          {isNewPlaceReport ? (
            <section className={styles.formSection}>
              <div className={styles.sectionHeading}>
                <p className={styles.sectionLabel}>새로운 장소</p>
                <h2>장소 기본 정보를 알려주세요</h2>
              </div>

              <div className={styles.fieldGrid}>
                <label className={styles.formField}>
                  <span>장소명</span>
                  <input
                    value={suggestedName}
                    onChange={(event) => setSuggestedName(event.target.value)}
                    type="text"
                    maxLength={255}
                    placeholder="예: 사상 감전천 쉼터"
                  />
                </label>
                <label className={styles.formField}>
                  <span>카테고리</span>
                  <input
                    value={suggestedCategory}
                    onChange={(event) => setSuggestedCategory(event.target.value)}
                    type="text"
                    maxLength={50}
                    placeholder="예: 카페, 공원, 쉼터"
                  />
                </label>
              </div>
            </section>
          ) : null}

          <section className={styles.mapPicker}>
            <div className={styles.sectionHeading}>
              <p className={styles.sectionLabel}>
                {isNewPlaceReport ? '새 장소 위치' : '제보 대상 장소 선택'}
              </p>
              <h2>
                {isNewPlaceReport
                  ? '장소를 검색하거나 지도를 클릭해서 새 장소 위치를 선택해 주세요'
                  : '장소를 검색하거나 지도를 클릭해서 제보 대상 위치를 보완할 수 있습니다'}
              </h2>
            </div>

            <div className={styles.placeSearchBox}>
              <input
                value={placeSearchKeyword}
                onChange={(event) => setPlaceSearchKeyword(event.target.value)}
                type="text"
                placeholder="장소명 또는 주소 검색"
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    searchReportPlaces()
                  }
                }}
              />
              <button type="button" disabled={isSearchingPlace} onClick={searchReportPlaces}>
                {isSearchingPlace ? '검색 중' : '검색'}
              </button>
            </div>

            {placeSearchResults.length ? (
              <div className={styles.placeSearchResults}>
                {placeSearchResults.map((place) => (
                  <button
                    key={place.id || `${place.place_name}-${place.x}-${place.y}`}
                    type="button"
                    className={styles.placeSearchResult}
                    onClick={() => applyPlaceSearchResult(place)}
                  >
                    <strong>{place.place_name}</strong>
                    <span>{getSearchResultAddress(place) || '주소 정보 없음'}</span>
                    {place.category_name ? (
                      <small>{getCategoryLabel(place.category_name)}</small>
                    ) : null}
                  </button>
                ))}
              </div>
            ) : null}

            {placeSearchMessage ? (
              <p className={styles.mapStatus}>{placeSearchMessage}</p>
            ) : null}

            <div
              ref={mapContainerRef}
              className={styles.reportMap}
              aria-label="제보 장소 위치 선택 지도"
            />
            {mapStatusMessage ? <p className={styles.mapStatus}>{mapStatusMessage}</p> : null}

            <label className={styles.formField}>
              <span>선택 위치</span>
              <input
                value={suggestedAddress}
                onChange={(event) => setSuggestedAddress(event.target.value)}
                type="text"
                maxLength={255}
                placeholder="지도 클릭 또는 장소 검색 후 주소가 채워집니다"
              />
            </label>

            <p className={styles.selectedLocation}>
              {selectedLocationSummary || '아직 선택된 위치가 없습니다.'}
            </p>
          </section>

          {isTagSuggestionReport ? (
            <section className={styles.formSection}>
              <div className={styles.sectionHeading}>
                <p className={styles.sectionLabel}>추천 태그</p>
                <h2>장소에 어울리는 특징을 선택해 주세요</h2>
              </div>

              <div className={styles.tagChipGrid}>
                {TAG_OPTIONS.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    className={`${styles.tagChipButton}${selectedTags.includes(tag) ? ` ${styles.selected}` : ''}`}
                    onClick={() => toggleTag(tag)}
                  >
                    {tag}
                  </button>
                ))}
              </div>

              <label className={styles.formField}>
                <span>추가로 제안할 특징</span>
                <input
                  value={extraTagsText}
                  onChange={(event) => setExtraTagsText(event.target.value)}
                  type="text"
                  placeholder="쉼표로 구분해서 입력해 주세요"
                />
              </label>

              {selectedTagsPreview.length ? (
                <p className={styles.selectedTagsPreview}>
                  선택 태그: {selectedTagsPreview.join(', ')}
                </p>
              ) : null}
            </section>
          ) : null}

          <label className={styles.formField}>
            <span>설명</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={6}
              placeholder={isNewPlaceReport
                ? '새 장소를 확인할 수 있는 설명을 적어 주세요.'
                : '검토에 필요한 근거를 적어 주세요.'}
            />
          </label>

          <label className={styles.formField}>
            <span>이미지 첨부</span>
            <input
              type="file"
              accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
              multiple
              onChange={handleImageChange}
            />
          </label>

          {images.length ? (
            <div className={styles.imageList}>
              {images.map((image, index) => (
                <span key={`${image.name}-${index}`} className={styles.imageChip}>
                  {image.name}
                  <button type="button" onClick={() => removeImage(index)}>삭제</button>
                </span>
              ))}
            </div>
          ) : null}

          {message ? <p className={styles.statusMessage}>{message}</p> : null}

          <div className={styles.formActions}>
            <Link to="/mypage/reports" className={styles.ghostButton}>내 제보 보기</Link>
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? '접수 중' : '제보 접수'}
            </button>
          </div>
        </form>
      </section>
    </main>
  )
}

export default PlaceReportView
