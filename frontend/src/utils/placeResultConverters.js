import {
  isKakaoPlaceId,
  getTextValue,
  normalizeLocationText,
  toDisplayList,
} from '@/utils/homePlaceHelpers'
import {
  getAncillaryPlaceAdjustment,
  makeTag,
} from '@/utils/kakaoPlaceRecommendation'
import {
  isPlaceExcludedByPlan,
  mergeRequestedConditionReview,
  toArray,
} from '@/utils/homeSearchPlanning'

const toFiniteCoordinate = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

const getMarkerLabel = (index) => String(index + 1)

export const getDbCategoryText = (category) => {
  const categoryMap = {
    toilet: '화장실',
    freewifi: '무료 와이파이',
    smoking_area: '흡연구역',
    beach: '해수욕장',
    shelter: '쉼터',
    parking: '주차장',
    city_park: '공원',
    citypark: '공원',
    tourism: '관광지',
  }

  return categoryMap[category] || category || ''
}

export const makeDbTags = (place) => {
  const tags = [
    makeTag('DB저장데이터', 'external_data'),
  ]

  const categoryText = getDbCategoryText(place.category)

  if (categoryText) {
    tags.push(makeTag(categoryText, 'category_rule'))
  }

  toArray(place.tags).forEach((tag) => {
    tags.push(makeTag(tag.name, tag.source))
  })

  return tags
}

export const convertDbPlaces = (places, {
  requestedConditions = [],
  getKakaoDetailUrl = () => '',
} = {}) => {
  return toArray(places).map((place) => {
    const externalId = place.external_id || place.externalId || null
    const isKakaoLocal = place.source === 'kakao_local'
    const sourceName = place.source_name || place.sourceName || ''
    const kakaoPlaceId = isKakaoLocal && isKakaoPlaceId(externalId) ? externalId : null
    const kakaoDetailUrl = getKakaoDetailUrl({
      ...place,
      externalId,
      sourceName,
      kakaoPlaceId,
    })
    const ancillaryAdjustment = getAncillaryPlaceAdjustment({
      place: {
        ...place,
        rawCategory: place.category,
      },
      query: place.name || '',
    })

    return mergeRequestedConditionReview({
      id: `db-${place.id}`,
      savedPlaceId: place.id,
      source: place.source,
      sourceName,
      externalId,
      kakaoPlaceId,
      rawCategory: place.category,
      name: place.name,
      category: getDbCategoryText(place.category),
      address: place.address,
      detailLocation: place.detail_location,
      lat: Number(place.lat),
      lng: Number(place.lng),
      distance: place.distance ?? null,
      phone: '',
      placeUrl: kakaoDetailUrl,
      kakaoPlaceUrl: getTextValue(place.kakao_place_url || place.kakaoPlaceUrl),
      kakaoUrl: getTextValue(place.kakao_url || place.kakaoUrl),
      detailUrl: getTextValue(place.detail_url || place.detailUrl),
      navigationUrl: `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`,
      markerColor: 'blue',
      searchSource: 'local_db',
      sourceLabel: 'DB추천',
      tags: makeDbTags(place),
      tagSource: 'DB 저장 데이터',
      dataQualityStatus: place.data_quality_status,
      dataQualityScore: place.data_quality_score,
      rawScores: place.raw?.scores || {},
      suggestedTags: place.suggested_tags || [],
      verifiedTags: place.verified_tags || [],
      warningTags: place.warning_tags || [],
      tagDetails: place.tag_details || [],
      matchedTagLabels: toDisplayList(place.matched_tag_labels),
      matchedSearchKeywords: toDisplayList(place.matched_search_keywords || place.matchedSearchKeywords),
      missingTagLabels: toDisplayList(place.missing_tag_labels),
      recommendationSourceLabel: getTextValue(place.source_label),
      recommendationConfidenceLabel: getTextValue(place.confidence_label),
      recommendationFallbackLabel: getTextValue(place.fallback_label),
      recommendationFallbackDescription: getTextValue(place.fallback_description),
      recommendationCaution: getTextValue(place.caution_message || place.caution),
      recommendationReason: getTextValue(
        place.recommendation_reason || place.recommend_reason || place.reason,
      ),
      personalizationBoost: Number(place.personalization_boost || 0),
      personalizationReasons: toDisplayList(place.personalization_reasons),
      recommendScore:
        place.raw?.scores?.recommendation_ready_score ??
        place.data_quality_score ??
        null,
      mainPlaceScore: ancillaryAdjustment.mainPlaceScore,
      ancillaryPlacePenalty: ancillaryAdjustment.ancillaryPlacePenalty,
      intentMismatchPenalty: ancillaryAdjustment.intentMismatchPenalty,
      isAncillaryPlace: ancillaryAdjustment.isAncillaryPlace,
    }, requestedConditions)
  })
}

export const getBackendRecommendationSourceType = (place = {}) => {
  return getTextValue(place.source_type || place.recommendationSourceType)
}

export const getBackendRecommendationSourceLabel = (place = {}) => {
  const sourceType = getBackendRecommendationSourceType(place)

  if (sourceType === 'kakao_candidate') {
    return '카카오 후보'
  }

  if (sourceType === 'web_evidence_candidate') {
    return '웹 참고'
  }

  if (sourceType === 'web_reference') {
    return '웹 참고'
  }

  return 'DB추천'
}

export const getBackendRecommendationSearchSource = (place = {}) => {
  const sourceType = getBackendRecommendationSourceType(place)

  if (sourceType === 'kakao_candidate') {
    return 'kakao'
  }

  if (['web_evidence_candidate', 'web_reference'].includes(sourceType)) {
    return 'web'
  }

  return 'local_db'
}

export const getBackendRecommendationMarkerColor = (place = {}) => {
  const sourceType = getBackendRecommendationSourceType(place)

  if (sourceType === 'kakao_candidate') {
    return 'red'
  }

  if (['web_evidence_candidate', 'web_reference'].includes(sourceType)) {
    return '#64748b'
  }

  return '#7c3aed'
}

export const makeBackendRecommendationTags = (place = {}) => {
  const sourceLabel = getBackendRecommendationSourceLabel(place)
  const tags = [
    makeTag(sourceLabel, 'external_data'),
  ]
  const categoryText = getDbCategoryText(place.category)

  if (categoryText) {
    tags.push(makeTag(categoryText, 'category_rule'))
  }

  ;toArray(place.matched_tags || place.runtime_tags).forEach((tagName) => {
    tags.push(makeTag(tagName, 'checked'))
  })

  toArray(place.suggested_tags).forEach((tagName) => {
    tags.push(makeTag(tagName, 'blog_search'))
  })

  toArray(place.verified_tags).forEach((tagName) => {
    tags.push(makeTag(tagName, 'user_verified'))
  })

  toArray(place.warning_tags).forEach((tagName) => {
    tags.push(makeTag(tagName, 'warning_tags'))
  })

  return tags
}

export const getPreferredTagMatchCount = (tagNames = [], preferredTags = []) => {
  const safePreferredTags = toArray(preferredTags)

  return toArray(tagNames).filter((tagName) => {
    const tagText = normalizeLocationText(tagName)
    return safePreferredTags.some((preferredTag) => {
      const preferredText = normalizeLocationText(preferredTag)
      return tagText.includes(preferredText) || preferredText.includes(tagText)
    })
  }).length
}

export const convertRecommendationPlaces = (
  places,
  {
    preferredTags = [],
    recommendationIntent = '',
    requestedConditions = [],
    searchPlan = null,
    getKakaoDetailUrl = () => '',
  } = {},
) => {
  return toArray(places).map((place) => {
    try {
    const externalId = place.external_id || place.externalId || null
    const sourceType = getBackendRecommendationSourceType(place)
    const isBackendKakaoCandidate = sourceType === 'kakao_candidate'
    const isBackendWebCandidate = ['web_evidence_candidate', 'web_reference'].includes(sourceType)
    const isExternalCandidate = Boolean(place.is_external || isBackendKakaoCandidate || isBackendWebCandidate)
    const sourceLabel = getBackendRecommendationSourceLabel(place)
    const searchSource = getBackendRecommendationSearchSource(place)
    const normalizedLat = toFiniteCoordinate(place.lat)
    const normalizedLng = toFiniteCoordinate(place.lng)
    const canShowOnMap = (
      !isBackendWebCandidate &&
      place.can_show_on_map !== false &&
      place.canShowOnMap !== false &&
      normalizedLat !== null &&
      normalizedLng !== null
    )
    const isKakaoLocal = place.source === 'kakao_local' || isBackendKakaoCandidate
    const sourceName = place.source_name || place.sourceName || ''
    const kakaoPlaceId = isKakaoLocal && isKakaoPlaceId(externalId) ? externalId : null
    const kakaoDetailUrl = getKakaoDetailUrl({
      ...place,
      externalId,
      sourceName,
      kakaoPlaceId,
    })
    const placeExternalUrl = getTextValue(
      place.external_url ||
      place.externalUrl ||
      place.place_url ||
      place.placeUrl ||
      place.kakao_place_url ||
      place.kakaoPlaceUrl,
    )
    const detailUrl = isBackendWebCandidate
      ? placeExternalUrl
      : (kakaoDetailUrl || placeExternalUrl)
    const ancillaryAdjustment = getAncillaryPlaceAdjustment({
      place: {
        ...place,
        rawCategory: place.category,
      },
      query: place.name || '',
      recommendationIntent,
    })
    const preferredMatchCount = getPreferredTagMatchCount(
      [
        ...toArray(place.matched_tags),
        ...toArray(place.runtime_tags),
        ...toArray(place.suggested_tags),
        ...toArray(place.verified_tags),
      ],
      preferredTags,
    )

    return mergeRequestedConditionReview({
      id: `recommendation-${place.id}`,
      savedPlaceId: isExternalCandidate ? null : place.id,
      source: place.source,
      sourceName,
      externalId,
      kakaoPlaceId,
      rawCategory: place.category,
      name: place.name,
      category: getDbCategoryText(place.category),
      address: place.address,
      detailLocation: place.detail_location || place.road_address,
      lat: normalizedLat,
      lng: normalizedLng,
      distance: place.distance ?? place.distance_m ?? null,
      phone: '',
      placeUrl: detailUrl,
      kakaoPlaceUrl: getTextValue(place.kakao_place_url || place.kakaoPlaceUrl),
      kakaoUrl: getTextValue(place.kakao_url || place.kakaoUrl),
      detailUrl: getTextValue(place.detail_url || place.detailUrl || detailUrl),
      navigationUrl: canShowOnMap
        ? `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`
        : '',
      markerColor: getBackendRecommendationMarkerColor(place),
      searchSource,
      sourceLabel,
      tags: makeBackendRecommendationTags(place),
      tagSource: isExternalCandidate ? `${sourceLabel} · 응답 단위 임시 후보` : 'DB 추천 결과',
      isExternal: isExternalCandidate,
      is_external: isExternalCandidate,
      canShowOnMap,
      can_show_on_map: canShowOnMap,
      dataQualityStatus: place.data_quality_status,
      dataQualityScore: place.data_quality_score,
      rawScores: place.raw_scores || {},
      suggestedTags: toArray(place.suggested_tags),
      verifiedTags: toArray(place.verified_tags),
      warningTags: toArray(place.warning_tags),
      tagDetails: toArray(place.tag_details),
      matchedTagLabels: toDisplayList(place.matched_tag_labels),
      missingTagLabels: toDisplayList(place.missing_tag_labels),
      matchedConditions: toDisplayList(place.matched_conditions),
      unverifiedConditions: toDisplayList(place.unverified_conditions),
      missingConditions: toDisplayList(place.missing_conditions),
      resultTier: getTextValue(place.result_tier),
      resultTierLabel: getTextValue(place.result_tier_label),
      relaxationApplied: Boolean(place.relaxation_applied),
      relaxedConditions: toDisplayList(place.relaxed_conditions),
      matchedEvidence: toArray(place.matched_evidence),
      backendRank: Number(place.backend_rank || place.backendRank || place.unified_rank || 0),
      unifiedRank: Number(place.unified_rank || place.unifiedRank || place.backend_rank || 0),
      semanticScore: Number(place.semantic_score || place.semanticScore || 0),
      evidenceLevel: getTextValue(place.evidence_level || place.evidenceLevel),
      matchedCategoryCodes: toDisplayList(place.matched_category_codes),
      relevanceScore: Number(place.relevance_score || 0),
      relevanceSource: getTextValue(place.relevance_source),
      frameMatchStrength: getTextValue(place.frame_match_strength || place.frameMatchStrength),
      frame_match_strength: getTextValue(place.frame_match_strength || place.frameMatchStrength),
      scoreCapReasons: toDisplayList(place.score_breakdown?.score_cap_reasons),
      score_cap_reasons: toDisplayList(place.score_breakdown?.score_cap_reasons),
      executionMode: getTextValue(place.execution_mode),
      planSource: getTextValue(place.plan_source),
      placeNatures: toDisplayList(place.place_natures),
      recommendationSourceLabel: getTextValue(place.source_label),
      recommendationConfidenceLabel: getTextValue(place.confidence_label),
      recommendationFallbackLabel: getTextValue(
        place.fallback_label || (
          place.result_tier === 'all_conditions_met' ? '' : place.result_tier_label
        ),
      ),
      recommendationFallbackDescription: getTextValue(place.fallback_description),
      recommendationCaution: getTextValue(place.caution_message || place.caution),
      recommendScore: Math.min(
        100,
        Number(place.score ?? place.data_quality_score ?? 0) + preferredMatchCount * 8,
      ),
      recommendationReason: getTextValue(
        place.recommendation_reason || place.recommend_reason || place.reason,
      ),
      personalizationBoost: Number(place.personalization_boost || 0),
      personalizationReasons: toDisplayList(place.personalization_reasons),
      matchedTags: toArray(place.matched_tags || place.runtime_tags),
      matchLevel: place.match_level,
      recommendationConfidence: place.confidence || place.recommendation_confidence,
      recommendationSourceType: sourceType,
      source_type: sourceType,
      fallbackLevel: place.fallback_level ?? null,
      recommendationIntent,
      preferredTags,
      preferredMatchCount,
      waitingPlacePenalty: place.score_breakdown?.unsuitable_place_penalty || 0,
      waitingPlaceExcluded: place.score_breakdown?.excluded_by_waiting_place || false,
      waitingPlacePenaltyReason: place.score_breakdown?.waiting_place_penalty_reason || null,
      resultType: isBackendKakaoCandidate
        ? 'kakao_backend_candidate'
        : isBackendWebCandidate
          ? sourceType
          : 'db_recommendation',
      mainPlaceScore: ancillaryAdjustment.mainPlaceScore,
      ancillaryPlacePenalty: ancillaryAdjustment.ancillaryPlacePenalty,
      intentMismatchPenalty: ancillaryAdjustment.intentMismatchPenalty,
      isAncillaryPlace: ancillaryAdjustment.isAncillaryPlace,
    }, requestedConditions)
    } catch (error) {
      console.warn('[추천 결과 변환 실패]', { place, error })
      return null
    }
  }).filter(Boolean).filter((place) => {
    return !isPlaceExcludedByPlan(place, searchPlan || {})
  })
}

export const assignMarkerLabels = (places) => {
  return places.map((place, index) => ({
    ...place,
    markerLabel: getMarkerLabel(index),
  }))
}
