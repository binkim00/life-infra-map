import {
  getAiEvidenceSources,
  getAiWebCandidateBadge,
  getAiWebCandidateCaution,
  getAiWebCandidateSourceUrl,
  getAiWebCandidateSummary,
  getAiWebSourceChannelLabel,
  isAiWebSourceReference,
} from '@/utils/aiWebCandidateHelpers'

const IS_DEV = import.meta.env.DEV

const getAiWebSearchDebugText = (result) => {
  if (!IS_DEV || !result) return ''

  const detail = result?.error_detail
  const summary = detail?.debug_summary || result?.debug_summary || null
  if (!detail && !summary) return ''

  const summaryText = summary
    ? [
      summary.output_count != null ? `outputs ${summary.output_count}` : '',
      Array.isArray(summary.output_types) && summary.output_types.length
        ? `types ${summary.output_types.join('/')}`
        : '',
      summary.source_count != null ? `sources ${summary.source_count}` : '',
      summary.output_url_count != null ? `output urls ${summary.output_url_count}` : '',
      summary.instruction_url_count != null ? `instruction urls ${summary.instruction_url_count}` : '',
      summary.annotation_count != null ? `annotations ${summary.annotation_count}` : '',
      summary.url_citation_count != null ? `citations ${summary.url_citation_count}` : '',
      summary.message_count != null ? `messages ${summary.message_count}` : '',
      summary.reasoning_count != null ? `reasoning ${summary.reasoning_count}` : '',
      summary.web_search_call_count != null ? `web search ${summary.web_search_call_count}` : '',
      summary.output_text_length != null ? `text ${summary.output_text_length}` : '',
      Array.isArray(summary.web_search_action_keys) && summary.web_search_action_keys.length
        ? `action keys ${summary.web_search_action_keys.join('/')}`
        : '',
    ].filter(Boolean).join(' · ')
    : ''

  return [
    result.reason,
    detail?.status_code ? `status ${detail.status_code}` : '',
    detail?.status || '',
    detail?.type || '',
    summaryText,
  ].filter(Boolean).join(' · ')
}

const AiWebSearchPanel = ({
  status,
  message,
  availability,
  candidates,
  lastResult,
  onSearch,
}) => {
  const isAvailable = Boolean(availability?.enabled && availability?.supported)
  const summary = lastResult?.summary && typeof lastResult.summary === 'object'
    ? lastResult.summary
    : null
  const evidenceCandidates = candidates.slice(0, 5)
  const debugText = getAiWebSearchDebugText(lastResult)

  return (
    <section className={`ai-web-search-panel is-${status}`}>
      <div className="ai-web-search-heading">
        <div>
          <strong>AI 웹 검색 참고 결과</strong>
          <span>웹 검색을 사용하므로 시간이 조금 걸릴 수 있습니다.</span>
        </div>

        {isAvailable ? (
          <button
            type="button"
            className="ai-web-search-button"
            disabled={status === 'loading'}
            onClick={onSearch}
          >
            {status === 'loading' ? '검색 중...' : '웹 검색 참고 링크 보기'}
          </button>
        ) : null}
      </div>

      {!isAvailable ? (
        <p className="ai-web-search-message">AI 웹 검색 기능이 현재 비활성화되어 있습니다.</p>
      ) : message ? (
        <p className="ai-web-search-message">{message}</p>
      ) : null}

      {debugText ? (
        <p className="ai-web-search-message ai-web-search-debug">{debugText}</p>
      ) : null}

      {candidates.length ? (
        <div className="ai-web-search-candidates">
          {summary ? (
            <article className="ai-web-search-summary-card">
              <strong>{summary.title || 'AI 웹 검색 요약'}</strong>
              <p>{summary.main_text}</p>
              {Array.isArray(summary.keywords) && summary.keywords.length ? (
                <p className="ai-web-search-summary-keywords">
                  키워드: {summary.keywords.join(', ')}
                </p>
              ) : null}
              <small>
                {summary.caution || '웹 검색 출처 기반 참고 정보이며, 실제 정보는 방문 전 확인이 필요합니다.'}
              </small>
            </article>
          ) : null}

          <div className="ai-web-search-evidence-heading">
            참고 링크 {evidenceCandidates.length}개
          </div>

          {evidenceCandidates.map((candidate, index) => {
            const isReference = isAiWebSourceReference(candidate)
            const sourceUrl = getAiWebCandidateSourceUrl(candidate)
            const candidateSummary = getAiWebCandidateSummary(candidate)
            const sources = getAiEvidenceSources(candidate)

            return (
              <article
                key={`ai-web-${candidate.name}-${index}`}
                className={`ai-web-search-candidate${isReference ? ' is-reference' : ''}`}
              >
                {isReference ? (
                  <div className="ai-web-search-reference-badges">
                    <span>참고 링크</span>
                    <span>{getAiWebSourceChannelLabel(candidate)}</span>
                  </div>
                ) : null}

                <div className="ai-web-search-candidate-title">
                  {sourceUrl ? (
                    <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                      {candidate.name}
                    </a>
                  ) : (
                    <strong>{candidate.name}</strong>
                  )}
                  {!isReference ? <span>{getAiWebCandidateBadge(candidate)}</span> : null}
                </div>

                {candidate.address_hint ? (
                  <p className="ai-web-search-hint ai-web-search-address">
                    {candidate.address_hint}
                  </p>
                ) : isReference && candidate.source_title && candidate.source_title !== candidate.name ? (
                  <p className="ai-web-search-hint">{candidate.source_title}</p>
                ) : null}

                {candidateSummary ? (
                  <p className="ai-web-search-summary">{candidateSummary}</p>
                ) : null}

                {sources.length ? (
                  <div className="ai-web-search-sources">
                    {sources.map((source, sourceIndex) => (
                      <a
                        key={`ai-web-source-${index}-${sourceIndex}`}
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        출처 보기
                      </a>
                    ))}
                  </div>
                ) : null}

                <p className="ai-web-search-caution">{getAiWebCandidateCaution(candidate)}</p>
              </article>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

export default AiWebSearchPanel
