import {
  getDistanceText,
  getPersonalizationBoost,
  getPersonalizationBoostText,
  getPersonalizationReasons,
  getPlaceSourceClass,
  getPlaceSourceText,
  getRecommendationFallbackText,
  getRecommendationMissingLabels,
  getRecommendationMetaText,
  getRecommendationPreviewLabels,
  isRecommendationPlace,
} from '@/utils/homePlaceHelpers'

const PlaceResultList = ({
  places,
  displayResultCount,
  isSearching,
  selectedPlace,
  placeListItemRefs,
  getRecommendationMatchedLabels,
  getRecommendationReasonSummary,
  onSelectPlace,
  onDismissPlace,
  onReportPlace,
}) => {
  if (isSearching) {
    return (
      <div className="place-list">
        <div className="skeleton-list">
          {[1, 2, 3, 4, 5].map((index) => (
            <article key={`skeleton-${index}`} className="skeleton-card">
              <span className="skeleton-marker" />
              <span className="skeleton-main">
                <span className="skeleton-line skeleton-title" />
                <span className="skeleton-line skeleton-meta" />
                <span className="skeleton-line skeleton-address" />
              </span>
            </article>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="place-list">
      {!places.length && displayResultCount ? (
        <div className="filtered-empty-message">선택한 필터에 맞는 결과가 없습니다.</div>
      ) : null}

      {places.map((place) => {
        const isRecommendation = isRecommendationPlace(place)
        const personalizationBoost = getPersonalizationBoost(place)
        const metaText = getRecommendationMetaText(place)
        const fallbackText = getRecommendationFallbackText(place)
        const reasonSummary = getRecommendationReasonSummary(place)
        const personalizationReasons = getPersonalizationReasons(place)
        const matchedLabels = getRecommendationMatchedLabels(place)
        const missingLabels = getRecommendationMissingLabels(place)

        return (
          <article
            key={place.id}
            ref={(element) => {
              if (element) {
                placeListItemRefs.current[place.id] = element
              }
            }}
            className={`place-list-item${selectedPlace && selectedPlace.id === place.id ? ' active' : ''}`}
          >
            <button
              type="button"
              className="place-list-select-button"
              onClick={(event) => onSelectPlace(place, event)}
            >
              <span className={`place-list-marker ${getPlaceSourceClass(place)}`}>
                {place.markerLabel}
              </span>

              <span className="place-list-main">
                <span className="place-list-name-row">
                  <span className="place-list-name">{place.name}</span>

                  <span className={`source-badge ${getPlaceSourceClass(place)}`}>
                    {getPlaceSourceText(place)}
                  </span>
                </span>

                <span className="place-list-meta">
                  {place.category ? <small>{place.category}</small> : null}
                  {getDistanceText(place) ? <small>{getDistanceText(place)}</small> : null}
                  {isRecommendation && personalizationBoost > 0 ? (
                    <small>{getPersonalizationBoostText(place)}</small>
                  ) : null}
                </span>

                {isRecommendation && (metaText || fallbackText) ? (
                  <span className="place-list-recommend-meta">
                    {metaText ? <small>{metaText}</small> : null}
                    {fallbackText ? <small>{fallbackText}</small> : null}
                  </span>
                ) : null}

                {isRecommendation && personalizationBoost > 0 ? (
                  <span className="place-list-personalization personalization-badge">
                    최근 선호 반영
                  </span>
                ) : null}

                {isRecommendation && reasonSummary ? (
                  <span className="place-list-reason">{reasonSummary}</span>
                ) : null}

                {isRecommendation && personalizationReasons.length ? (
                  <span className="personalization-reasons">
                    <span className="personalization-reasons-label">최근 선호</span>
                    {getRecommendationPreviewLabels(personalizationReasons, 3).map((reason) => (
                      <span
                        key={`personalization-${place.id}-${reason}`}
                        className="personalization-reason-chip"
                      >
                        {reason.replace(/^최근 자주 찾은\s*/, '')}
                      </span>
                    ))}
                  </span>
                ) : null}

                {isRecommendation && matchedLabels.length ? (
                  <span className="place-list-condition-group">
                    <span className="place-list-condition-label">일치 조건</span>
                    {getRecommendationPreviewLabels(matchedLabels, 3).map((label, index) => (
                      <span
                        key={`matched-${place.id}-${label}-${index}`}
                        className="place-list-condition-chip matched"
                      >
                        {label}
                      </span>
                    ))}
                  </span>
                ) : null}

                {isRecommendation && missingLabels.length ? (
                  <span className="place-list-condition-group">
                    <span className="place-list-condition-label">확인 필요</span>
                    {getRecommendationPreviewLabels(missingLabels, 2).map((label, index) => (
                      <span
                        key={`missing-${place.id}-${label}-${index}`}
                        className="place-list-condition-chip missing"
                      >
                        {label}
                      </span>
                    ))}
                  </span>
                ) : null}

                {place.address || place.detailLocation ? (
                  <span
                    className="place-list-address"
                    title={place.address || place.detailLocation}
                  >
                    {place.address || place.detailLocation}
                  </span>
                ) : null}

                {place.phone ? (
                  <span className="place-list-phone">전화 {place.phone}</span>
                ) : null}
              </span>
            </button>
            <button
              type='button'
              className='place-result-dismiss-button'
              onClick={(event) => {
                event.stopPropagation()
                onDismissPlace?.(place)
              }}
            >
              이 결과는 아니에요
            </button>
            <button
              type="button"
              className="place-report-link-button"
              onClick={(event) => {
                event.stopPropagation()
                onReportPlace(place)
              }}
            >
              정보 제보
            </button>
          </article>
        )
      })}
    </div>
  )
}

export default PlaceResultList
