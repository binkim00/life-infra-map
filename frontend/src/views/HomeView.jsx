import { useEffect, useRef } from 'react'

import KakaoMap from '@/components/KakaoMap'
import {
  AI_SEARCH_PRESETS,
  RESULT_FILTER_OPTIONS,
  RESULT_SORT_OPTIONS,
} from '@/constants/homeViewUiConstants'
import { useHomeSearch } from '@/hooks/useHomeSearch'
import { usePlaceInteractionTracking } from '@/hooks/usePlaceInteractionTracking'
import { useSavedPlaceActions } from '@/hooks/useSavedPlaceActions'
import {
  getClarificationOptionItems,
  getClarificationOptionLabel,
  getClarificationOptionValue,
  getFrameDisplayLabel,
  getIntentGroupDisplayLabel,
  getRecommendationMissingLabels,
  getScenarioDisplayLabel,
  getTextValue,
} from '@/utils/homePlaceHelpers'

import AiWebSearchPanel from './home/AiWebSearchPanel'
import PlaceDetailPanel from './home/PlaceDetailPanel'
import PlaceResultList from './home/PlaceResultList'

import '@/styles/Homeview.css'

const isNoResultLocationMessage = (message = '') => (
  ['찾지 못했습니다', '결과가 없습니다'].some((pattern) => String(message || '').includes(pattern))
)

const isSearchErrorMessage = (message = '') => {
  const text = getTextValue(message)
  return text.includes('오류가 발생했습니다') || text.includes('다시 시도해 주세요')
}

const HomeView = ({ initialTab = 'search' }) => {
  const home = useHomeSearch({ initialTab })
  const { state: s, setStateValue } = home

  const {
    savingPlaceId,
    saveMessage: placeSaveMessage,
    isPlaceSaved,
    loadSavedPlaceKeys,
    savePlace: handleSavePlace,
  } = useSavedPlaceActions()

  const primarySearchInputRef = useRef(null)
  const followUpInputRef = useRef(null)

  useEffect(() => {
    loadSavedPlaceKeys()
  }, [loadSavedPlaceKeys])

  const displayResults = home.displayResults()
  const filteredSearchResults = home.filteredSearchResults()
  const searchedPlaces = home.searchedPlaces()
  const mapPlaces = home.mapPlaces()
  const resultCountText = home.getResultCountText()
  const activeSearchPlan = s.activeSearchPlan || {}
  const interactionQuery = getTextValue(
    activeSearchPlan.originalQuery
    || activeSearchPlan.original_query
    || activeSearchPlan.normalizedQuery
    || activeSearchPlan.normalized_query
    || s.mapSearchKeyword,
  )
  const interactionRequestedTags = [
    ...(Array.isArray(activeSearchPlan.preferredTags) ? activeSearchPlan.preferredTags : []),
    ...(Array.isArray(activeSearchPlan.preferred_tags) ? activeSearchPlan.preferred_tags : []),
    ...(Array.isArray(activeSearchPlan.requestedConditions) ? activeSearchPlan.requestedConditions : []),
    ...(Array.isArray(activeSearchPlan.requested_conditions) ? activeSearchPlan.requested_conditions : []),
    ...(Array.isArray(activeSearchPlan.constraints) ? activeSearchPlan.constraints : []),
  ]
  const placeInteractions = usePlaceInteractionTracking({
    query: interactionQuery,
    requestedTags: interactionRequestedTags,
    places: searchedPlaces,
  })

  const handleTrackedPlaceSelect = (place, event) => {
    void placeInteractions.trackPlaceEvent('click', place)
    home.selectPlaceFromList(place, event)
  }

  const handleTrackedMapPlaceSelect = (place, target) => {
    void placeInteractions.trackPlaceEvent('click', place)
    home.selectPlace(place, target)
  }

  const handleTrackedPlaceSave = async (place) => {
    const result = await handleSavePlace(place)
    if (result?.status === 'saved') {
      await placeInteractions.trackPlaceEvent('save', place)
    }
    return result
  }

  const handleResultDismiss = (place) => {
    void placeInteractions.trackPlaceEvent('dismiss', place)
  }

  const handleTrackedClarificationOption = (option) => {
    const answer = getClarificationOptionValue(option) || getClarificationOptionLabel(option)
    void placeInteractions.trackSearchEvent('clarification', {
      query: answer,
      requested_tags: [...placeInteractions.requestedTags, answer].filter(Boolean),
      context: {
        answer,
        question: getTextValue(s.pendingClarification?.clarification_question),
        answer_type: 'option',
      },
    })
    home.submitClarificationOption(option)
  }

  const handleTrackedClarificationFollowUp = () => {
    const answer = s.followUpInput.trim()
    if (answer) {
      void placeInteractions.trackSearchEvent('clarification', {
        query: answer,
        requested_tags: [...placeInteractions.requestedTags, answer],
        context: {
          answer,
          question: getTextValue(s.pendingClarification?.clarification_question),
          answer_type: 'free_text',
        },
      })
    }
    home.submitClarificationFollowUp()
  }

  // 선택한 장소가 바뀌면 목록에서 그 항목이 보이도록 스크롤합니다.
  useEffect(() => {
    if (!s.selectedPlace?.id) return

    const targetElement = home.placeListItemRefs.current[s.selectedPlace.id]
    targetElement?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [s.selectedPlace?.id, home.placeListItemRefs])

  const hasSearchExperienceContent = Boolean(
    s.mapSearchKeyword.trim()
    || s.pendingClarification
    || s.clarificationThread.length
    || displayResults.length
    || s.isSearchingMap
    || s.baseLocationCandidates.length,
  )

  const shouldSuggestAiWebSearch = home.shouldSuggestAiWebSearch()
  const shouldShowAiWebSearchPanel = Boolean(
    s.aiWebSearchContext && !s.isSearchingMap && !s.isResultListCollapsed && shouldSuggestAiWebSearch,
  )
  const shouldShowResultPanel = Boolean(
    (!s.isSearchingMap || s.isAiReranking) && (displayResults.length || shouldShowAiWebSearchPanel),
  )
  const shouldShowSearchMapContent = Boolean(
    s.activeTab === 'map'
    || s.isSearchingMap
    || displayResults.length
    || shouldShowAiWebSearchPanel
    || s.baseLocationCandidates.length,
  )
  const hasMapExperienceContent = Boolean(
    (s.activeTab === 'map' || s.activeTab === 'search')
    && (hasSearchExperienceContent || s.currentLocationPlace.length),
  )
  const isConversationMode = Boolean(
    s.conversationModeStarted
    || s.clarificationThread.length
    || s.pendingClarification
    || s.isSearchingMap
    || displayResults.length
    || s.baseLocationCandidates.length,
  )
  const isClarificationOnlyState = Boolean(
    s.pendingClarification
    && !s.isSearchingMap
    && !displayResults.length
    && !s.baseLocationCandidates.length,
  )
  const shouldShowPlaceDetailPanel = Boolean(s.selectedPlace && !s.isPlaceDetailDismissed)

  const clarificationOptions = getClarificationOptionItems(
    s.pendingClarification?.clarification_options
    || s.pendingClarification?.clarificationOptions
    || [],
  )

  const getActiveSearchBaseLabel = () => {
    const plan = s.activeSearchPlan || {}
    const explicitLocation = getTextValue(
      plan.locationQuery
      || plan.location_query
      || plan.baseLocationQuery
      || plan.base_location_query,
    )

    return explicitLocation ? `${explicitLocation} 기준` : '현재 위치 기준'
  }

  const searchQueryText = s.mapSearchKeyword.trim() || s.searchKeyword.trim()

  const searchConversationTitle = (() => {
    if (s.isAiReranking && displayResults.length) {
      return '빠른 후보를 먼저 보여드리고 있어요.'
    }

    if (s.isSearchingMap) {
      return searchQueryText
        ? `“${searchQueryText}”에 맞는 장소를 찾는 중이에요.`
        : '필요한 장소를 찾는 중이에요.'
    }

    if (s.pendingClarification) {
      return 'AI가 조건을 조금 더 확인하려고 합니다.'
    }

    if (displayResults.length && searchQueryText) {
      return `${getActiveSearchBaseLabel()}으로 “${searchQueryText}” 결과를 찾았어요.`
    }

    if (searchQueryText) {
      return `“${searchQueryText}” 검색을 준비했어요.`
    }

    return '상황을 입력하면 지도와 결과를 함께 정리해드려요.'
  })()

  const searchConversationDetail = (() => {
    if (s.isAiReranking && displayResults.length) {
      return s.loadingMessage || 'AI가 적합도 순서를 다듬고 있습니다.'
    }

    if (s.isSearchingMap) {
      return s.loadingMessage || '검색 조건을 확인하고 있습니다.'
    }

    if (displayResults.length) {
      if (
        s.locationMessage
        && !isSearchErrorMessage(s.locationMessage)
        && !isNoResultLocationMessage(s.locationMessage)
      ) {
        return s.locationMessage
      }

      return `${s.resultSourceLabel} ${filteredSearchResults.length}개를 확인했습니다.`
    }

    if (s.searchErrorMessage) {
      return s.searchErrorMessage
    }

    if (s.locationMessage) {
      return s.locationMessage
    }

    return '검색 결과가 부족하면 웹 검색 참고 링크를 보조로 확인할 수 있어요.'
  })()

  const searchConversationChips = (() => {
    const chips = []
    const target = getTextValue(s.activeSearchPlan?.targetQuery || s.activeSearchPlan?.targetKeyword)
    const frameLabel = getFrameDisplayLabel(s.activeSearchPlan)
    const displayLabel = getTextValue(s.activeSearchPlan?.displayLabel || s.activeSearchPlan?.display_label)
    const intentGroupLabel = getIntentGroupDisplayLabel(
      s.activeSearchPlan?.intentGroup || s.activeSearchPlan?.intent_group || '',
    )
    const scenarioLabel = getScenarioDisplayLabel(s.activeSearchPlan?.recommendationIntent || '')
    const category = frameLabel
      || displayLabel
      || intentGroupLabel
      || scenarioLabel
      || getTextValue(s.activeSearchPlan?.categoryKeyword || s.activeSearchPlan?.categoryHint)
    const query = s.mapSearchKeyword.trim()

    if (query) chips.push({ label: '검색어', value: query })
    if (target && target !== query) chips.push({ label: '대상', value: target })
    if (category) chips.push({ label: '분류', value: category })
    if (displayResults.length) {
      chips.push({ label: '결과', value: `${filteredSearchResults.length}개` })
    }

    return chips.slice(0, 4)
  })()

  const searchConversationNotice = (() => {
    const missingLabels = [
      ...new Set(displayResults.flatMap((place) => getRecommendationMissingLabels(place))),
    ]

    if (missingLabels.length) {
      return `“${missingLabels.slice(0, 2).join(', ')}”는 현재 데이터로 확인되지 않아 방문 전 확인이 필요합니다.`
    }

    if (shouldShowAiWebSearchPanel) {
      return '웹 검색 참고 결과도 함께 확인할 수 있어요.'
    }

    return ''
  })()

  const mapParserStatus = (() => {
    if (!s.mapAiParse) return null
    if (
      !displayResults.length
      && !s.isSearchingMap
      && ['empty', 'error', 'idle'].includes(s.searchResultStatus)
    ) {
      return null
    }

    const parserProvider = getTextValue(s.mapAiParse.parser_provider)
    const parserFallback = s.mapAiParse.parser_fallback === true
    const executionMode = getTextValue(
      s.mapAiParse.execution_mode
      || s.activeSearchPlan?.execution_mode
      || s.activeSearchPlan?.executionMode,
    )
    const planSource = getTextValue(
      s.mapAiParse.plan_source
      || s.activeSearchPlan?.plan_source
      || s.activeSearchPlan?.planSource,
    )
    const hasAiFrame = executionMode === 'frame' && planSource !== 'legacy_fallback'
    const isAiFirstParser = executionMode === 'ai_first_orchestrator'
      || parserProvider === 'ai_intent_planner'
      || parserProvider === 'backend_ai_only'
    const isAiProviderParser = ['openai', 'gms', 'ai'].includes(parserProvider)

    if (!parserFallback && (isAiProviderParser || hasAiFrame || isAiFirstParser)) {
      return {
        label: '조건 정리 완료',
        detail: '말씀하신 내용을 장소와 조건으로 정리했어요.',
        className: 'ai',
      }
    }

    const fallbackReason = getTextValue(
      s.mapAiParse.ai_fallback_reason
      || s.mapAiParse.fallback_reason
      || s.activeSearchPlan?.fallbackReason,
    )

    return {
      label: '기본 검색 기준 적용',
      detail: fallbackReason
        ? `입력한 표현에서 바로 찾을 수 있는 조건을 우선 적용했어요. (${fallbackReason})`
        : '입력한 표현에서 바로 찾을 수 있는 조건을 우선 적용했어요.',
      className: 'fallback',
    }
  })()

  const searchPlanStatus = s.activeSearchPlan?.correctionApplied
    ? {
      label: '검색어 보정',
      detail: `'${s.activeSearchPlan.normalizedQuery}'로 이해했어요.`,
      className: 'fallback',
    }
    : null

  const resultPanelTitle = (() => {
    if (resultCountText) return resultCountText
    if (['empty', 'filtered_empty'].includes(s.searchResultStatus)) {
      return '조건에 맞는 장소를 찾지 못했어요'
    }
    if (s.searchResultStatus === 'error') return '검색 결과를 표시하지 못했어요'
    return '검색 결과'
  })()

  const mapLayoutKey = [
    searchedPlaces.length > 0 ? 'has-results' : 'no-results',
    shouldShowPlaceDetailPanel ? 'has-detail' : 'no-detail',
    s.isResultListCollapsed ? 'list-collapsed' : 'list-expanded',
    s.isPlaceDetailCollapsed ? 'detail-collapsed' : 'detail-expanded',
  ].join(':')

  const hasMoreResults = s.visibleCount < filteredSearchResults.length

  const mainClassName = [
    'home-page',
    s.activeTab === 'search' ? 'is-search-tab' : '',
    s.activeTab === 'map' ? 'is-map-tab' : '',
    s.activeTab === 'search' && !hasSearchExperienceContent ? 'is-idle-experience' : '',
    s.activeTab === 'search' && hasSearchExperienceContent ? 'has-search-results' : '',
    isConversationMode ? 'is-conversation-mode' : '',
  ].filter(Boolean).join(' ')

  const isIdleLanding = s.activeTab === 'search' && !hasSearchExperienceContent

  return (
    <main className={mainClassName}>
      {isIdleLanding ? (
        <section className="search-section search-experience is-idle">
          <div className="intro">
            <p className="eyebrow">상황 기반 장소 추천 지도 서비스</p>
            <h1>지금 필요한 장소를 검색해보세요</h1>
            <p className="description">
              예: 조용히 노트북 할 카페, 근처 화장실, 산책하기 좋은 곳
            </p>
          </div>

          <div className="search-box">
            <input
              ref={primarySearchInputRef}
              value={s.searchKeyword}
              onChange={(event) => setStateValue('searchKeyword', event.target.value)}
              type="text"
              placeholder="지금 어떤 장소가 필요하신가요?"
              onKeyUp={(event) => {
                if (event.key === 'Enter') {
                  home.handleSearch()
                }
              }}
            />

            <button type="button" onClick={home.handleSearch}>검색</button>
          </div>

          <div className="landing-preset-buttons">
            {AI_SEARCH_PRESETS.map((preset) => (
              <button
                key={`landing-${preset.label}`}
                type="button"
                onClick={() => home.runLandingPresetSearch(preset.query)}
              >
                {preset.label}
              </button>
            ))}
          </div>

          <p className="search-idle-hint">
            검색하면 지도와 추천 결과를 한 화면에서 함께 보여드릴게요.
          </p>
        </section>
      ) : (
        <section
          className={[
            'map-section-wrap search-experience',
            s.activeTab === 'search' && hasSearchExperienceContent ? 'has-results' : '',
            s.activeTab === 'map' ? 'is-map-tab-view' : '',
          ].filter(Boolean).join(' ')}
        >
          <section
            className={[
              'conversation-search-card search-hero-card',
              hasMapExperienceContent ? 'has-results' : '',
              isConversationMode ? 'is-conversation-mode' : '',
            ].filter(Boolean).join(' ')}
          >
            <div className="conversation-card-top">
              <div className="conversation-copy">
                <p className="eyebrow">대화형 장소 추천 지도</p>
                <h1>
                  {hasMapExperienceContent
                    ? '필요한 장소를 계속 찾아볼까요?'
                    : '지도에서 바로 찾아볼까요?'}
                </h1>
              </div>

              <div className="map-header-actions">
                <button
                  type="button"
                  className="map-location-button"
                  disabled={s.isSearchingMap || s.isLocating}
                  onClick={home.openMapWithCurrentLocation}
                >
                  {s.isLocating ? '확인 중...' : '현재 위치'}
                </button>

                <button
                  type="button"
                  className="map-reset-button map-header-reset"
                  disabled={s.isSearchingMap}
                  onClick={home.resetMapSearch}
                >
                  초기화
                </button>
              </div>
            </div>

            {isConversationMode ? (
              <div className="conversation-compact-bar">
                <span>현재 대화형 검색 중</span>
                <button
                  type="button"
                  disabled={s.isSearchingMap}
                  onClick={home.startNewConversationSearch}
                >
                  새 검색
                </button>
              </div>
            ) : null}

            <form
              className={`map-search-box ai-search-box search-panel${isConversationMode ? ' search-panel--compact' : ''}`}
              onSubmit={(event) => {
                event.preventDefault()
                home.performUnifiedMapSearch()
              }}
            >
              <label htmlFor="map-keyword-search">상황을 입력해 주세요</label>
              <input
                id="map-keyword-search"
                ref={primarySearchInputRef}
                value={s.mapSearchKeyword}
                onChange={(event) => setStateValue('mapSearchKeyword', event.target.value)}
                type="text"
                placeholder="예: 소금빵 맛집, 조용히 작업할 카페, 비 오는데 쉴 곳"
              />

              <button
                type="submit"
                className="map-ai-button"
                disabled={s.isSearchingMap || !s.mapSearchKeyword.trim()}
              >
                {s.isSearchingMap ? '검색 중...' : '검색'}
              </button>

              <div className="ai-preset-buttons">
                {AI_SEARCH_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    disabled={s.isSearchingMap}
                    onClick={() => home.runAiPresetSearch(preset.query)}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </form>

            <div className="conversation-status">
              <div>
                <strong>{searchConversationTitle}</strong>
                <p>{searchConversationDetail}</p>
              </div>

              {s.clarificationThread.length ? (
                <div className="clarification-thread" aria-live="polite">
                  {s.clarificationThread.map((item) => (
                    <div
                      key={`${item.role}-${item.text}`}
                      className={`clarification-bubble is-${item.role}`}
                    >
                      <span>{item.label}</span>
                      <p>{item.text}</p>
                    </div>
                  ))}
                </div>
              ) : null}

              {clarificationOptions.length ? (
                <div className="clarification-options">
                  {clarificationOptions.map((option) => (
                    <button
                      key={`${getClarificationOptionLabel(option)}-${getClarificationOptionValue(option)}`}
                      type="button"
                      disabled={s.isSearchingMap}
                      onClick={() => handleTrackedClarificationOption(option)}
                    >
                      {getClarificationOptionLabel(option)}
                    </button>
                  ))}
                </div>
              ) : null}

              {s.pendingClarification ? (
                <form
                  className="clarification-follow-up"
                  onSubmit={(event) => {
                    event.preventDefault()
                    handleTrackedClarificationFollowUp()
                  }}
                >
                  <input
                    ref={followUpInputRef}
                    value={s.followUpInput}
                    onChange={(event) => setStateValue('followUpInput', event.target.value)}
                    type="text"
                    placeholder="예: 쉬는 곳, 먹을 곳, 산책할 곳, 서면"
                    disabled={s.isSearchingMap}
                    onKeyDown={(event) => event.stopPropagation()}
                  />
                  <button
                    type="submit"
                    disabled={s.isSearchingMap || !s.followUpInput.trim()}
                  >
                    보내기
                  </button>
                </form>
              ) : null}

              {searchConversationChips.length ? (
                <div className="conversation-chip-list">
                  {searchConversationChips.map((chip) => (
                    <span key={`${chip.label}-${chip.value}`}>
                      {chip.label}: {chip.value}
                    </span>
                  ))}
                </div>
              ) : null}

              {searchConversationNotice ? (
                <p className="conversation-notice">{searchConversationNotice}</p>
              ) : null}
            </div>

            {s.activeTab === 'search' && shouldShowSearchMapContent && !isClarificationOnlyState ? (
              <div
                className={`view-switch${s.activeResultView === 'map' ? ' is-map-active' : ''}`}
                aria-label="결과와 지도 보기 전환"
              >
                <button
                  type="button"
                  className={s.activeResultView === 'results' ? 'active' : undefined}
                  onClick={() => home.setResultViewMode('results')}
                >
                  결과 보기
                </button>

                <button
                  type="button"
                  className={s.activeResultView === 'map' ? 'active' : undefined}
                  onClick={() => home.setResultViewMode('map')}
                >
                  지도 보기
                </button>
              </div>
            ) : null}
          </section>

          {mapParserStatus ? (
            <div className={`map-parser-status ${mapParserStatus.className}`}>
              <strong>{mapParserStatus.label}</strong>
              <span>{mapParserStatus.detail}</span>
            </div>
          ) : null}

          {searchPlanStatus ? (
            <div className={`map-parser-status ${searchPlanStatus.className}`}>
              <strong>{searchPlanStatus.label}</strong>
              <span>{searchPlanStatus.detail}</span>
            </div>
          ) : null}

          {s.baseLocationCandidates.length ? (
            <section className="base-location-candidates">
              <div className="candidate-header">
                <div>
                  <strong>기준 위치가 여러 곳으로 검색되었습니다.</strong>
                  <p>원하는 지역을 선택해 주세요.</p>
                </div>

                <button
                  type="button"
                  className="candidate-cancel-button"
                  onClick={home.clearBaseLocationCandidateSelection}
                >
                  취소
                </button>
              </div>

              <div className="candidate-list">
                {s.baseLocationCandidates.map((candidate) => (
                  <button
                    key={candidate.id}
                    type="button"
                    className="candidate-button"
                    onClick={() => home.selectBaseLocationCandidate(candidate)}
                  >
                    <span>
                      <strong>{candidate.place_name}</strong>
                      <small>{candidate.address_name || candidate.road_address_name}</small>
                    </span>
                    <small className="candidate-kind">
                      {candidate.candidateKind || '기준 위치'}
                      {candidate.category_name ? <span> · {candidate.category_name}</span> : null}
                    </small>
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          {!isClarificationOnlyState && shouldShowSearchMapContent ? (
            <div
              className={[
                'map-content search-reveal-area',
                shouldShowResultPanel ? 'has-result-list' : '',
                shouldShowPlaceDetailPanel ? 'has-selected-place' : '',
                s.isResultListCollapsed ? 'is-list-collapsed' : '',
                s.activeResultView === 'results' ? 'is-result-focused' : '',
                s.activeResultView === 'map' ? 'is-map-focused' : '',
              ].filter(Boolean).join(' ')}
            >
              {shouldShowResultPanel ? (
                <aside className={`place-list-panel${s.isResultListCollapsed ? ' is-collapsed' : ''}`}>
                  <div className="place-list-top">
                    <div>
                      <p className="place-list-label">검색 결과</p>
                      <h2>{resultPanelTitle}</h2>
                    </div>

                    <button
                      type="button"
                      className="panel-toggle-button"
                      onClick={home.toggleResultListPanel}
                    >
                      {s.isResultListCollapsed ? '펼치기' : '접기'}
                    </button>
                  </div>

                  {displayResults.length && (!s.isSearchingMap || s.isAiReranking) && !s.isResultListCollapsed ? (
                    <div className="result-controls">
                      <div className="result-filter-buttons" aria-label="결과 필터">
                        {RESULT_FILTER_OPTIONS.map((filterOption) => (
                          <button
                            key={filterOption.value}
                            type="button"
                            className={`result-filter-button${s.resultFilterMode === filterOption.value ? ' active' : ''}`}
                            onClick={() => home.setResultFilterMode(filterOption.value)}
                          >
                            {filterOption.label}
                          </button>
                        ))}
                      </div>

                      <label className="result-sort-select">
                        <span>정렬</span>
                        <select
                          value={s.sortMode}
                          onChange={(event) => home.setSortMode(event.target.value)}
                        >
                          {RESULT_SORT_OPTIONS.map((sortOption) => (
                            <option key={sortOption.value} value={sortOption.value}>
                              {sortOption.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                  ) : null}

                  {shouldShowAiWebSearchPanel ? (
                    <AiWebSearchPanel
                      status={s.aiWebSearchStatus}
                      message={s.aiWebSearchMessage}
                      availability={s.aiWebSearchAvailability}
                      candidates={s.aiWebSearchCandidates}
                      lastResult={s.aiWebSearchLastResult}
                      onSearch={home.searchAiWebCandidatesManually}
                    />
                  ) : null}

                  {s.isResultListCollapsed ? (
                    <div className="collapsed-panel-summary">검색 결과</div>
                  ) : (
                    <>
                      <PlaceResultList
                        places={searchedPlaces}
                        displayResultCount={displayResults.length}
                        isSearching={s.isSearchingMap && !s.isAiReranking}
                        selectedPlace={s.selectedPlace}
                        placeListItemRefs={home.placeListItemRefs}
                        getRecommendationMatchedLabels={home.getRecommendationMatchedLabels}
                        getRecommendationReasonSummary={home.getRecommendationReasonSummary}
                        onSelectPlace={handleTrackedPlaceSelect}
                        onDismissPlace={handleResultDismiss}
                        onReportPlace={home.goToPlaceReport}
                      />

                      {hasMoreResults ? (
                        <div className="show-more-wrap">
                          <button
                            type="button"
                            className="show-more-button"
                            onClick={home.showMoreResults}
                          >
                            더보기
                          </button>
                        </div>
                      ) : null}
                    </>
                  )}
                </aside>
              ) : null}

              <div className="map-area">
                {s.mapSearchKeyword.trim() ? (
                  <button
                    type="button"
                    className="map-overlay-research-button"
                    disabled={s.isSearchingMap}
                    onClick={home.searchCurrentMapView}
                  >
                    현재 지도에서 재검색
                  </button>
                ) : null}

                {s.isSearchingMap && !s.isAiReranking ? (
                  <div className="map-loading-overlay">
                    <div className="map-loading-box">
                      <span className="loading-spinner" />
                      <strong>{s.loadingMessage || '검색 중'}</strong>
                    </div>
                  </div>
                ) : null}

                <KakaoMap
                  center={s.mapCenter}
                  places={mapPlaces}
                  fitBoundsKey={s.mapFitBoundsKey}
                  layoutKey={mapLayoutKey}
                  selectedPlaceId={s.selectedPlace?.id || null}
                  selectedPlace={s.selectedPlace}
                  hiddenPlaceId={s.hiddenMapMarkerPlaceId}
                  choiceRequestKey={s.markerChoiceRequestKey}
                  onCenterChange={home.handleMapViewportChange}
                  onSelectPlace={handleTrackedMapPlaceSelect}
                  onMarkerTargetChange={home.updateMascotFetchTarget}
                />
              </div>

              {shouldShowPlaceDetailPanel ? (
                <PlaceDetailPanel
                  place={s.selectedPlace}
                  isCollapsed={s.isPlaceDetailCollapsed}
                  detailFrameError={s.detailFrameError}
                  kakaoDetailUrl={home.getKakaoDetailUrl(s.selectedPlace)}
                  placeDetailUrl={home.getPlaceDetailUrl(s.selectedPlace)}
                  placeNavigationUrl={home.getPlaceNavigationUrl(s.selectedPlace)}
                  savingPlaceId={savingPlaceId}
                  saveMessage={placeSaveMessage}
                  isPlaceSaved={isPlaceSaved}
                  getRecommendationMatchedLabels={home.getRecommendationMatchedLabels}
                  getRecommendationReason={home.getRecommendationReason}
                  onCollapse={() => setStateValue('isPlaceDetailCollapsed', true)}
                  onExpand={() => setStateValue('isPlaceDetailCollapsed', false)}
                  onDismiss={home.dismissPlaceDetailPanel}
                  onSavePlace={handleTrackedPlaceSave}
                  requestedFeedbackTags={placeInteractions.requestedTags}
                  onTagFeedback={placeInteractions.submitTagFeedback}
                  getTagFeedbackState={placeInteractions.getTagFeedbackState}
                  onReportPlace={home.goToPlaceReport}
                  onDetailFrameError={() => setStateValue('detailFrameError', true)}
                />
              ) : null}
            </div>
          ) : null}
        </section>
      )}
    </main>
  )
}

export default HomeView
