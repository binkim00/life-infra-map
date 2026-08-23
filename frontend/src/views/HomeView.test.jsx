import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import HomeView from './HomeView'

vi.mock('@/hooks/useKakaoMapSdk', () => ({
  loadKakaoMapScript: () => Promise.resolve(),
  waitForKakaoServices: () => Promise.resolve(),
}))

const aiSearchRecommendations = vi.fn()
const aiSearchCandidateRecommendations = vi.fn()
const saveSearchLog = vi.fn(() => Promise.resolve({}))

vi.mock('@/api/recommendation', () => ({
  aiSearchCandidateRecommendations: (...args) => aiSearchCandidateRecommendations(...args),
  aiSearchRecommendations: (...args) => aiSearchRecommendations(...args),
  buildConversationalSearchPlan: () => Promise.resolve(null),
  checkSearchSafety: () => Promise.resolve({ blocked: false }),
  getKakaoPlaceTags: () => Promise.resolve({ results: {} }),
  getSavedPlaces: () => Promise.resolve({ results: [] }),
  runAiWebSearch: () => Promise.resolve({ ai_web_search: {} }),
  saveSearchLog: (...args) => saveSearchLog(...args),
  savePlaceInteractions: () => Promise.resolve({ count: 0 }),
  startNewConversationSession: () => {},
  fetchUserSavedPlaces: () => Promise.resolve({ results: [] }),
  saveUserSavedPlace: () => Promise.resolve({}),
}))

const renderHome = () => render(
  <MemoryRouter initialEntries={['/']}>
    <HomeView initialTab="search" />
  </MemoryRouter>,
)

/** 지도/검색 SDK 를 흉내 냅니다. 검색 파이프라인이 window.kakao 를 직접 씁니다. */
const installKakaoStub = () => {
  class LatLng {
    constructor(lat, lng) {
      this.lat = lat
      this.lng = lng
    }

    getLat() { return this.lat }

    getLng() { return this.lng }
  }

  window.kakao = {
    maps: {
      services: {
        Places: class {},
        Geocoder: class {},
        Status: { OK: 'OK', ZERO_RESULT: 'ZERO_RESULT' },
        SortBy: { DISTANCE: 'DISTANCE', ACCURACY: 'ACCURACY' },
      },
      LatLng,
      LatLngBounds: class { extend() {} },
      Size: class {},
      Point: class {},
      MarkerImage: class {},
      Map: vi.fn(function MapStub() {
        return {
          setCenter: vi.fn(),
          setBounds: vi.fn(),
          panTo: vi.fn(),
          relayout: vi.fn(),
          getCenter: () => new LatLng(35.1796, 129.0756),
          getBounds: () => ({
            getSouthWest: () => new LatLng(35.1, 129.0),
            getNorthEast: () => new LatLng(35.2, 129.1),
          }),
          getProjection: () => ({ containerPointFromCoords: () => ({ x: 10, y: 10 }) }),
        }
      }),
      Marker: vi.fn(function MarkerStub() {
        return { setMap: vi.fn(), setImage: vi.fn() }
      }),
      InfoWindow: vi.fn(function InfoWindowStub() {
        return { open: vi.fn(), close: vi.fn(), setPosition: vi.fn() }
      }),
      event: { addListener: vi.fn() },
    },
  }
}

describe('HomeView', () => {
  beforeEach(() => {
    localStorage.clear()
    installKakaoStub()
    aiSearchRecommendations.mockReset()
    aiSearchCandidateRecommendations.mockReset()
    aiSearchCandidateRecommendations.mockResolvedValue({ results: [] })
    saveSearchLog.mockClear()
    // 위치 권한을 거부해 지도 중심 기준으로 흐르게 둡니다.
    navigator.geolocation = {
      getCurrentPosition: (_success, failure) => failure(new Error('denied')),
    }
  })

  it('검색 전에는 안내 화면을 보여줍니다', () => {
    renderHome()

    expect(screen.getByText('지금 필요한 장소를 검색해보세요')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('지금 어떤 장소가 필요하신가요?')).toBeInTheDocument()
  })

  it('검색하면 AI 추천 결과와 개수를 표시합니다', async () => {
    aiSearchRecommendations.mockResolvedValue({
      results: [
        {
          id: 1,
          name: '서면 조용한 카페',
          category: '카페',
          address: '부산 진구',
          lat: 35.1579,
          lng: 129.0594,
          distance: 120,
        },
        {
          id: 2,
          name: '노트북 하기 좋은 카페',
          category: '카페',
          address: '부산 진구',
          lat: 35.1581,
          lng: 129.0599,
          distance: 240,
        },
      ],
      scenario: 'work_cafe',
      execution_mode: 'ai_first_orchestrator',
      ai_parse: { parser_provider: 'ai_intent_planner', parser_fallback: false },
    })

    const user = userEvent.setup()
    renderHome()

    await user.type(
      screen.getByPlaceholderText('지금 어떤 장소가 필요하신가요?'),
      '서면에서 조용히 노트북 하기 좋은 카페',
    )
    await user.click(screen.getByRole('button', { name: '검색' }))

    await waitFor(() => {
      expect(aiSearchRecommendations).toHaveBeenCalledTimes(1)
    })

    await waitFor(() => {
      expect(screen.getByText('서면 조용한 카페')).toBeInTheDocument()
    })
    expect(screen.getByText('노트북 하기 좋은 카페')).toBeInTheDocument()
  })

  it('결과가 없으면 못 찾았다고 알려줍니다', async () => {
    aiSearchRecommendations.mockResolvedValue({
      results: [],
      execution_mode: 'ai_first_orchestrator',
      ai_parse: { parser_provider: 'ai_intent_planner', parser_fallback: false },
    })

    const user = userEvent.setup()
    renderHome()

    await user.type(
      screen.getByPlaceholderText('지금 어떤 장소가 필요하신가요?'),
      '존재하지 않는 조건',
    )
    await user.click(screen.getByRole('button', { name: '검색' }))

    await waitFor(() => {
      expect(aiSearchRecommendations).toHaveBeenCalledTimes(1)
    })

    await waitFor(() => {
      expect(
        screen.getAllByText(/조건에 맞는 장소를 찾지 못했어요|조건에 맞는 추천 결과가 없습니다/).length,
      ).toBeGreaterThan(0)
    })
  })

  it('빠른 후보를 먼저 표시한 뒤 AI 재정렬 결과로 교체합니다', async () => {
    let resolveFinalSearch
    aiSearchCandidateRecommendations.mockResolvedValue({
      provisional: true,
      search_phase: 'candidates',
      unified_candidate_pipeline: true,
      frontend_should_preserve_order: true,
      results: [{
        id: 'preview-1',
        name: '빠른 후보 카페',
        category: '카페',
        address: '부산 진구',
        lat: 35.1579,
        lng: 129.0594,
        distance: 120,
      }],
    })
    aiSearchRecommendations.mockReturnValue(new Promise((resolve) => {
      resolveFinalSearch = resolve
    }))

    const user = userEvent.setup()
    renderHome()

    await user.type(
      screen.getByPlaceholderText('지금 어떤 장소가 필요하신가요?'),
      '조용한 작업 카페',
    )
    await user.click(screen.getByRole('button', { name: '검색' }))

    await waitFor(() => {
      expect(screen.getByText('빠른 후보 카페')).toBeInTheDocument()
      expect(screen.getByText('빠른 후보를 먼저 보여드리고 있어요.')).toBeInTheDocument()
    })

    resolveFinalSearch({
      results: [{
        id: 'final-1',
        name: 'AI 최종 추천 카페',
        category: '카페',
        address: '부산 진구',
        lat: 35.1581,
        lng: 129.0599,
        distance: 180,
      }],
      scenario: 'work_cafe',
      execution_mode: 'ai_first_orchestrator',
      unified_candidate_pipeline: true,
      frontend_should_preserve_order: true,
      ai_parse: { parser_provider: 'ai_intent_planner', parser_fallback: false },
    })

    await waitFor(() => {
      expect(screen.getByText('AI 최종 추천 카페')).toBeInTheDocument()
      expect(screen.queryByText('빠른 후보 카페')).not.toBeInTheDocument()
    })
  })

  it('후속 검색에 이전 검색 문장과 조건 프레임을 전달합니다', async () => {
    aiSearchRecommendations
      .mockResolvedValueOnce({
        results: [{
          id: 'first-1',
          name: '광안리 첫 식당',
          category: '식당',
          address: '부산 수영구',
          lat: 35.1532,
          lng: 129.1187,
          distance: 150,
        }],
        scenario: 'ai_place_search',
        execution_mode: 'ai_first_orchestrator',
        unified_candidate_pipeline: true,
        frontend_should_preserve_order: true,
        search_plan: {
          originalQuery: '광안리 식당',
          locationQuery: '광안리',
          targetQuery: '식당',
          place_intent_frame: {
            location_mode: 'explicit',
            anchor_location: '광안리',
            target_objects: ['식당'],
            constraints: [],
          },
        },
        ai_parse: { parser_provider: 'ai_intent_planner', parser_fallback: false },
      })
      .mockResolvedValueOnce({
        results: [{
          id: 'second-1',
          name: '광안리 조용한 식당',
          category: '식당',
          address: '부산 수영구',
          lat: 35.1535,
          lng: 129.1190,
          distance: 180,
        }],
        scenario: 'ai_place_search',
        execution_mode: 'ai_first_orchestrator',
        unified_candidate_pipeline: true,
        frontend_should_preserve_order: true,
        search_plan: {
          originalQuery: '좀 더 조용한 곳',
          locationQuery: '광안리',
          targetQuery: '식당',
          place_intent_frame: {
            location_mode: 'explicit',
            anchor_location: '광안리',
            target_objects: ['식당'],
            constraints: ['조용함'],
          },
        },
        ai_parse: { parser_provider: 'ai_intent_planner', parser_fallback: false },
      })

    const user = userEvent.setup()
    renderHome()
    const input = screen.getByPlaceholderText('지금 어떤 장소가 필요하신가요?')

    await user.type(input, '광안리 식당')
    await user.click(screen.getByRole('button', { name: '검색' }))
    await waitFor(() => {
      expect(screen.getByText('광안리 첫 식당')).toBeInTheDocument()
    })

    const followUpInput = screen.getByLabelText('상황을 입력해 주세요')
    await user.clear(followUpInput)
    await user.type(followUpInput, '좀 더 조용한 곳')
    await user.click(screen.getByRole('button', { name: '검색' }))
    await waitFor(() => {
      expect(aiSearchRecommendations).toHaveBeenCalledTimes(2)
    })

    const followUpPayload = aiSearchRecommendations.mock.calls[1][0]
    expect(followUpPayload.previous_context.previous_user_query).toBe('광안리 식당')
    expect(followUpPayload.previous_context.place_intent_frame).toEqual(expect.objectContaining({
      anchor_location: '광안리',
      target_objects: ['식당'],
    }))
    await waitFor(() => {
      expect(screen.getByText('광안리 조용한 식당')).toBeInTheDocument()
    })
  })
})
