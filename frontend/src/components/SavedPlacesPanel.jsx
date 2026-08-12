import styles from './SavedPlacesPanel.module.css'

const getSavedPlaceDetailUrl = (place = {}) => {
  return place.detail_url || place.kakao_place_url || ''
}

const getSavedPlaceNavigationUrl = (place = {}) => {
  const lat = Number(place.lat)
  const lng = Number(place.lng)
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return ''

  return `https://map.kakao.com/link/to/${encodeURIComponent(place.name || '장소')},${lat},${lng}`
}

const formatSavedPlaceMeta = (place = {}) => {
  return [
    place.source_label || '',
    place.category || '',
    place.address || '',
  ].filter(Boolean).join(' · ')
}

const SavedPlacesPanel = ({
  places = [],
  isLoading = false,
  message = '',
  editingPlaceId = null,
  memoInput = '',
  updatingPlaceId = null,
  onRefresh,
  onStartMemoEdit,
  onCancelMemoEdit,
  onSaveMemo,
  onDeletePlace,
  onMemoInputChange,
}) => {
  return (
    <section className={styles.panel}>
      <div className={styles.sectionHeadingRow}>
        <div>
          <h2>저장한 장소</h2>
          <p>다시 확인하고 싶은 장소와 개인 메모를 관리합니다.</p>
        </div>
        <button
          type="button"
          className={styles.refreshHistoryButton}
          onClick={() => onRefresh?.()}
        >
          새로고침
        </button>
      </div>

      {isLoading ? (
        <p className={styles.empty}>저장한 장소를 불러오는 중입니다.</p>
      ) : places.length ? (
        <div className={styles.savedPlaceList}>
          {places.map((place) => {
            const detailUrl = getSavedPlaceDetailUrl(place)
            const navigationUrl = getSavedPlaceNavigationUrl(place)
            const meta = formatSavedPlaceMeta(place)
            const isEditing = editingPlaceId === place.id
            const isUpdating = updatingPlaceId === place.id

            return (
              <article key={place.id} className={styles.savedPlaceItem}>
                <div className={styles.savedPlaceMain}>
                  <span className={styles.preferenceSourceBadge}>
                    {place.source_label || '저장 장소'}
                  </span>
                  <strong>{place.name}</strong>
                  {meta ? <span className={styles.savedPlaceMeta}>{meta}</span> : null}
                  {place.memo && !isEditing ? (
                    <p className={styles.savedPlaceMemo}>{place.memo}</p>
                  ) : null}

                  {isEditing ? (
                    <form
                      className={styles.savedPlaceMemoForm}
                      onSubmit={(event) => {
                        event.preventDefault()
                        onSaveMemo?.(place)
                      }}
                    >
                      <textarea
                        value={memoInput}
                        rows={3}
                        maxLength={2000}
                        placeholder="이 장소에 대한 메모를 남겨보세요."
                        onChange={(event) => onMemoInputChange?.(event.target.value)}
                      />
                      <span className={styles.savedPlaceActions}>
                        <button type="submit" disabled={isUpdating}>
                          {isUpdating ? '저장 중' : '메모 저장'}
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => onCancelMemoEdit?.()}
                        >
                          취소
                        </button>
                      </span>
                    </form>
                  ) : null}
                </div>

                <div className={styles.savedPlaceActions}>
                  {!isEditing ? (
                    <button type="button" onClick={() => onStartMemoEdit?.(place)}>
                      메모
                    </button>
                  ) : null}
                  {detailUrl ? (
                    <a href={detailUrl} target="_blank" rel="noopener noreferrer">
                      상세
                    </a>
                  ) : null}
                  {navigationUrl ? (
                    <a href={navigationUrl} target="_blank" rel="noopener noreferrer">
                      길찾기
                    </a>
                  ) : null}
                  <button
                    type="button"
                    className={styles.danger}
                    disabled={isUpdating}
                    onClick={() => onDeletePlace?.(place)}
                  >
                    삭제
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      ) : (
        <p className={styles.empty}>{message}</p>
      )}

      {message && places.length ? (
        <p className={`${styles.empty} ${styles.savedPlaceStatus}`}>{message}</p>
      ) : null}
    </section>
  )
}

export default SavedPlacesPanel
