import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAdminOperations } from '@/api/recommendation'
import { useAuthStore } from '@/stores/auth'
import AdminOperationsView from './AdminOperationsView'

vi.mock('@/api/recommendation', () => ({ fetchAdminOperations: vi.fn() }))

const payload = {
  period: { new_evidence: 12, new_active_evidence: 8, new_place_tags: 4, processed_places: 10 },
  cumulative: { places: 100, evidence: 20 },
  growth: [{ date: '2026-08-17', new_active_evidence: 8 }],
  top_active_tags: [{ tag: '조용함', count: 5 }],
  providers: [
    { provider: 'naver_search', calls: 10, failures: 0, rate_limited: 0, today_usage_rate: 0.01, total_tokens: null },
    { provider: 'openai_evidence', calls: 2, failures: 0, rate_limited: 0, estimated_cost_usd: null, total_tokens: null },
  ],
  strategies: [{ strategy: 'candidate_hint', places: 10, calls: 10, evidence: 12, active: 8, evidence_per_call: 1.2, active_per_call: 0.8 }],
  regions: [{ region: '서울', places: 100, evidence_places: 20, active_evidence_places: 10, place_coverage: 0.1, stale_ratio: 0.2, readiness: 'PARTIAL' }],
  categories: [{ category: 'cafe', places: 100, evidence_places: 20, active_evidence_places: 10, place_coverage: 0.1, stale_ratio: 0.2, readiness: 'PARTIAL' }],
  tag_coverage_category: 'cafe',
  tag_coverage: { 서울: [{ tag: '조용함', active_places: 10, coverage: 0.1, period_increase: 2 }] },
  queue: { queued: 0, processing: 0, retry: 0, failed: 0, completed_period: 10 },
  runtime: { worker_last_success_at: '2026-08-17T00:00:00Z' },
  source_freshness: [{ source: 'toilet', latest_source_date: '2026-08-15', current_evidence: 10, stale_evidence: 1, stale_ratio: 0.09, refresh_needed: false }],
  search_performance: { status: 'NOT_AVAILABLE', reason: 'search latency is not persisted' },
  semantic_pilot: { feature_documents: 1000, embedded_documents: 1000, model: 'text-embedding-3-small', dimensions: 512, retrieval_enabled: false, candidate_injection_enabled: false, operating_scope: 'OPERATING_JSON_DOCUMENT_REGISTRY', pgvector_staging_scope: 'ISOLATED_NOT_OPERATING' },
}

describe('AdminOperationsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({ user: { id: 1, is_staff: true }, isLoggedIn: true, token: 'token' })
    fetchAdminOperations.mockResolvedValue(payload)
  })

  it('renders admin KPIs and strategy efficiency', async () => {
    render(<MemoryRouter><AdminOperationsView /></MemoryRouter>)
    expect(await screen.findByText('장소 데이터 운영 현황')).toBeInTheDocument()
    expect(await screen.findByText('candidate_hint')).toBeInTheDocument()
    expect(screen.getAllByText('12').length).toBeGreaterThan(0)
    expect(screen.getAllByText('NOT_MEASURED').length).toBeGreaterThan(0)
    expect(screen.getByText('text-embedding-3-small')).toBeInTheDocument()
    expect(screen.getByText(/ISOLATED_NOT_OPERATING/)).toBeInTheDocument()
  })

  it('sends selected filters to the backend', async () => {
    render(<MemoryRouter><AdminOperationsView /></MemoryRouter>)
    await screen.findByText('장소 데이터 운영 현황')
    fireEvent.change(screen.getByLabelText('기간'), { target: { value: '7' } })
    fireEvent.change(screen.getByLabelText('지역'), { target: { value: '서울' } })
    await waitFor(() => expect(fetchAdminOperations).toHaveBeenLastCalledWith({ days: 7, region: '서울', category: '' }))
  })

  it('does not call the API for a normal user', async () => {
    useAuthStore.setState({ user: { id: 2, is_staff: false }, isLoggedIn: true, token: 'token' })
    render(<MemoryRouter><AdminOperationsView /></MemoryRouter>)
    await waitFor(() => expect(fetchAdminOperations).not.toHaveBeenCalled())
  })
})
