import {
  getTextValue,
  normalizeLocationText,
} from '@/utils/homePlaceHelpers'

export const getAiEvidenceSources = (candidate = {}) => {
  return Array.isArray(candidate.evidence_sources)
    ? candidate.evidence_sources.filter((source) => source?.url)
    : []
}

export const getAiWebCandidateSourceUrl = (candidate = {}) => {
  return getTextValue(candidate.source_url || getAiEvidenceSources(candidate)[0]?.url)
}

export const normalizeAiWebReferenceTitle = (candidate = {}) => {
  return normalizeLocationText(
    getTextValue(candidate.source_title || candidate.name)
      .replace(/[\[\](){}<>]/g, ' ')
      .replace(/[|｜].*$/g, ' ')
      .replace(/\s+/g, ' ')
      .trim(),
  )
}

export const getAiWebTitleTokens = (candidate = {}) => {
  const title = getTextValue(candidate.source_title || candidate.name)
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .map((token) => normalizeLocationText(token))
    .filter((token) => token.length >= 2)

  return [...new Set(title)]
}

export const hasSimilarAiWebReferenceTitle = (candidate, seenTokenSets) => {
  const tokens = getAiWebTitleTokens(candidate)
  if (!tokens.length) return false

  return seenTokenSets.some((seenTokens) => {
    const overlapCount = tokens.filter((token) => seenTokens.has(token)).length
    const smallerTokenCount = Math.min(tokens.length, seenTokens.size)
    return overlapCount >= 3 || (smallerTokenCount >= 2 && overlapCount >= smallerTokenCount)
  })
}

export const dedupeAiWebSearchCandidates = (candidates = []) => {
  const seenUrls = new Set()
  const seenTitles = new Set()
  const seenTokenSets = []
  const deduped = []

  candidates.forEach((candidate) => {
    const url = getTextValue(candidate.source_url)
    const normalizedTitle = normalizeAiWebReferenceTitle(candidate)

    if (url && seenUrls.has(url)) return
    if (normalizedTitle && seenTitles.has(normalizedTitle)) return

    if (isAiWebSourceReference(candidate) && hasSimilarAiWebReferenceTitle(candidate, seenTokenSets)) {
      return
    }

    if (url) seenUrls.add(url)
    if (normalizedTitle) seenTitles.add(normalizedTitle)
    if (isAiWebSourceReference(candidate)) {
      seenTokenSets.push(new Set(getAiWebTitleTokens(candidate)))
    }
    deduped.push(candidate)
  })

  return deduped
}

export const getAiWebCandidateSummary = (candidate = {}) => {
  return getTextValue(candidate.evidence_summary || candidate.recommendation_reason)
}

export const isAiWebSourceReference = (candidate = {}) => {
  return candidate?.candidate_type === 'web_source_reference'
}

export const getAiWebCandidateBadge = (candidate = {}) => {
  return isAiWebSourceReference(candidate)
    ? '참고 링크'
    : (candidate.category_hint || 'AI 웹 검색 후보')
}

export const getAiWebSourceChannelLabel = (candidate = {}) => {
  const channel = getTextValue(candidate.source_channel)
  if (channel === 'local') return '네이버 지역'
  if (channel === 'blog') return '네이버 블로그'
  if (channel === 'webkr') return '네이버 웹문서'
  return '웹 검색'
}

export const getAiWebCandidateCaution = (candidate = {}) => {
  if (isAiWebSourceReference(candidate)) {
    if (candidate.source_channel === 'local') {
      return '네이버 지역 검색 참고 결과입니다. 방문 전 상세 정보를 확인해 주세요.'
    }

    return '이 결과는 웹 검색 출처 기반 참고 정보이며, 실제 장소 정보는 방문 전 확인이 필요합니다.'
  }

  return candidate.caution_message || 'AI 웹 검색 기반 후보입니다. 위치, 운영 여부, 메뉴, 분위기는 방문 전 확인이 필요합니다.'
}
