import { useEffect, useRef } from 'react'

import { getFeedbackTagOptions } from '@/hooks/usePlaceInteractionTracking'

import {
  getPlaceSourceClass,
  getPlaceSourceText,
  getRecommendationConfidence,
  getRecommendationConfidenceText,
  getRecommendationFallbackText,
  getRecommendationMetaText,
  getSortedTags,
  getTagClass,
  getTagName,
  getTagSourceText,
  getWebEvidenceUrl,
  isRecommendationPlace,
  isWebEvidenceCandidateResult,
} from '@/utils/homePlaceHelpers'

const getSelectedPlaceDetailLabel = (place) => (
  isWebEvidenceCandidateResult(place) ? '선택한 참고 정보' : '선택한 장소'
)

const getPlaceDetailActionText = (place) => (
  isWebEvidenceCandidateResult(place) ? '웹에서 확인하기' : '카카오 상세 보기'
)

const PlaceDetailPanel = ({
  place,
  isCollapsed,
  detailFrameError,
  kakaoDetailUrl,
  placeDetailUrl,
  placeNavigationUrl,
  savingPlaceId,
  saveMessage,
  isPlaceSaved,
  getRecommendationMatchedLabels,
  getRecommendationReason,
  onCollapse,
  onExpand,
  onDismiss,
  onSavePlace,
  requestedFeedbackTags,
  onTagFeedback,
  getTagFeedbackState,
  onReportPlace,
  onDetailFrameError,
}) => {
  const tagListRef = useRef(null)

  // 다른 장소를 고르면 태그 줄 스크롤을 처음으로 돌려놓습니다.
  useEffect(() => {
    if (tagListRef.current) {
      tagListRef.current.scrollLeft = 0
      tagListRef.current.scrollTop = 0
    }
  }, [place?.id])

  if (!place) return null

  const hasKakaoDetail = Boolean(kakaoDetailUrl)
  const matchedLabels = getRecommendationMatchedLabels(place)
  const isRecommendation = isRecommendationPlace(place)
  const feedbackOptions = getFeedbackTagOptions(place, requestedFeedbackTags)

  if (isCollapsed) {
    return (
      <aside className="place-detail-panel is-collapsed">
        <div className="detail-collapsed-bar">
          <button type="button" className="detail-collapsed-main" onClick={onExpand}>
            <span>상세정보</span>
            <strong>{place.name}</strong>
          </button>

          <button
            type="button"
            className="close-card-button"
            aria-label="상세정보 닫기"
            onClick={onDismiss}
          >
            ×
          </button>
        </div>
      </aside>
    )
  }

  return (
    <aside className={`place-detail-panel${hasKakaoDetail ? '' : ' is-compact-detail'}`}>
      <div className={`split-place-card${hasKakaoDetail ? ' has-kakao-detail' : ''}`}>
        <div className="split-card-top">
          <div>
            <p className="card-label">
              {getSelectedPlaceDetailLabel(place)}
              <span className={`source-badge ${getPlaceSourceClass(place)}`}>
                {getPlaceSourceText(place)}
              </span>
            </p>
            <h2>{place.name}</h2>
          </div>

          <button type="button" className="panel-toggle-button" onClick={onCollapse}>
            접기
          </button>

          <button
            type="button"
            className="close-card-button"
            aria-label="상세정보 닫기"
            onClick={onDismiss}
          >
            ×
          </button>
        </div>

        {place.tags && place.tags.length ? (
          <div className="tag-list" ref={tagListRef}>
            {getSortedTags(place.tags).map((tag) => (
              <span
                key={`${getTagName(tag)}-${typeof tag === 'string' ? 'category_rule' : tag.source}`}
                className={`tag-chip ${getTagClass(tag)}`}
              >
                #{getTagName(tag)}
                <small>{getTagSourceText(tag)}</small>
              </span>
            ))}
          </div>
        ) : null}

        {hasKakaoDetail ? (
          <section className="kakao-frame-section">
            {detailFrameError ? (
              <div className="iframe-fallback">
                <p>카카오맵 상세페이지를 현재 화면에 표시하지 못했습니다.</p>

                <a href={kakaoDetailUrl} target="_blank" rel="noopener noreferrer">
                  새창에서 열기
                </a>
              </div>
            ) : (
              <div className="kakao-frame-scroll">
                <iframe
                  src={kakaoDetailUrl}
                  className="inline-kakao-frame"
                  title="카카오맵 장소 상세페이지"
                  scrolling="no"
                  referrerPolicy="no-referrer-when-downgrade"
                  onError={onDetailFrameError}
                />
              </div>
            )}
          </section>
        ) : isWebEvidenceCandidateResult(place) ? (
          <section className="db-summary-card web-evidence-summary-card">
            <div>
              <strong>웹에서 찾은 참고 정보입니다.</strong>
              <p>장소명과 위치는 실제 방문 전에 한 번 더 확인해 주세요.</p>
              {getWebEvidenceUrl(place) ? (
                <a href={getWebEvidenceUrl(place)} target="_blank" rel="noopener noreferrer">
                  원문 열기
                </a>
              ) : null}
            </div>
          </section>
        ) : null}

        <div className="info-list compact-info-list">
          {isRecommendation ? (
            <div className="recommendation-summary">
              {getRecommendationMetaText(place) || getRecommendationConfidence(place) ? (
                <div>
                  <span>출처/신뢰도</span>
                  <strong>
                    {getRecommendationMetaText(place)
                      || getRecommendationConfidenceText(getRecommendationConfidence(place))}
                  </strong>
                </div>
              ) : null}

              {getRecommendationFallbackText(place) ? (
                <div>
                  <span>추천 방식</span>
                  <strong>{getRecommendationFallbackText(place)}</strong>
                </div>
              ) : null}
            </div>
          ) : null}

          {isRecommendation && getRecommendationReason(place) ? (
            <div className="info-row">
              <span>추천 이유</span>
              <p className="recommendation-reason-text">{getRecommendationReason(place)}</p>
            </div>
          ) : null}

          {isRecommendation && matchedLabels.length ? (
            <div className="info-row">
              <span>일치 조건</span>
              <div className="recommendation-chip-list">
                {matchedLabels.map((label, index) => (
                  <span
                    key={`detail-matched-${place.id}-${label}-${index}`}
                    className="recommendation-chip matched"
                  >
                    {label}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {place.category ? (
            <div className="info-row"><span>분류</span><p>{place.category}</p></div>
          ) : null}

          {place.address ? (
            <div className="info-row"><span>주소</span><p>{place.address}</p></div>
          ) : null}

          {place.detailLocation ? (
            <div className="info-row"><span>상세위치</span><p>{place.detailLocation}</p></div>
          ) : null}

          {place.smoking?.facility_type ? (
            <div className="info-row">
              <span>시설 유형</span>
              <p>{place.smoking.facility_type_label || place.smoking.facility_type}</p>
            </div>
          ) : null}

          {place.smoking?.verification_level ? (
            <div className="info-row">
              <span>확인 수준</span>
              <p>{place.smoking.verification_level_label || place.smoking.verification_level}</p>
            </div>
          ) : null}

          {place.smoking?.location_description ? (
            <div className="info-row">
              <span>시설 위치</span>
              <p>{place.smoking.location_description}</p>
            </div>
          ) : null}

          {place.smoking?.location_directions ? (
            <div className="info-row">
              <span>찾아가는 법</span>
              <p>{place.smoking.location_directions}</p>
            </div>
          ) : null}

          {place.distance ? (
            <div className="info-row">
              <span>거리</span>
              <p>검색 기준 위치에서 {place.distance}m</p>
            </div>
          ) : null}
        </div>

        <section className='place-tag-feedback'>
          <div className='place-tag-feedback-heading'>
            <strong>이 장소는 실제로 어떤가요?</strong>
            <small>한 번의 선택이 다음 검색 결과를 더 정확하게 만들어요.</small>
          </div>
          <div className='place-tag-feedback-list'>
            {feedbackOptions.map((option) => {
              const feedbackStatus = getTagFeedbackState?.(place, option.tag) || ''
              return (
                <div className='place-tag-feedback-row' key={option.tag}>
                  <span>#{option.label}</span>
                  <button
                    type='button'
                    className={feedbackStatus === 'confirmed' ? 'is-selected' : ''}
                    disabled={feedbackStatus === 'sending'}
                    onClick={() => onTagFeedback?.(place, option.tag, true)}
                  >
                    맞아요
                  </button>
                  <button
                    type='button'
                    className={feedbackStatus === 'rejected' ? 'is-selected is-negative' : ''}
                    disabled={feedbackStatus === 'sending'}
                    onClick={() => onTagFeedback?.(place, option.tag, false)}
                  >
                    아니에요
                  </button>
                </div>
              )
            })}
          </div>
        </section>

        <div className='detail-action-row'>
          <button
            type="button"
            className="detail-action-button save"
            disabled={savingPlaceId === place.id || isPlaceSaved(place)}
            onClick={() => onSavePlace(place)}
          >
            {isPlaceSaved(place)
              ? '저장됨'
              : savingPlaceId === place.id ? '저장 중' : '장소 저장'}
          </button>

          <button
            type="button"
            className="detail-action-button report"
            onClick={() => onReportPlace(place)}
          >
            정보 제보
          </button>

          {placeDetailUrl ? (
            <a
              href={placeDetailUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="detail-action-button secondary"
            >
              {getPlaceDetailActionText(place)}
            </a>
          ) : null}

          {placeNavigationUrl ? (
            <a
              href={placeNavigationUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="detail-action-button primary"
            >
              카카오맵 길찾기
            </a>
          ) : null}
        </div>
        {saveMessage ? <p className="place-save-message">{saveMessage}</p> : null}
      </div>
    </aside>
  )
}

export default PlaceDetailPanel
