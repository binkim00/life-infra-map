import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
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

const LocationProbe = () => {
  const location = useLocation()
  return <output data-testid="location-probe">{location.pathname}{location.search}</output>
}

const renderHome = () => render(
  <MemoryRouter initialEntries={['/']}>
    <HomeView initialTab="search" />
    <LocationProbe />
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
    expect(screen.getByPlaceholderText('예: 서면역 약국, 광안리 주차장')).toBeInTheDocument()
  })

  it('일반 장소 검색은 추천 API를 호출하지 않고 지도 검색으로 이동합니다', async () => {
    const user = userEvent.setup()
    renderHome()

    await user.type(
      screen.getByPlaceholderText('예: 서면역 약국, 광안리 주차장'),
      '서면역 약국',
    )
    await user.click(screen.getByRole('button', { name: '일반 검색' }))

    expect(screen.getByTestId('location-probe')).toHaveTextContent('/map?q=%EC%84%9C%EB%A9%B4%EC%97%AD%20%EC%95%BD%EA%B5%AD')
    expect(aiSearchRecommendations).not.toHaveBeenCalled()
  })

  it('검색하면 AI 추천 결과와 개수를 표시합니다', async () => {
    const getCurrentPosition = vi.fn((_success, failure) => failure(new Error('denied')))
    navigator.geolocation.getCurrentPosition = getCurrentPosition
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
    expect(getCurrentPosition).not.toHaveBeenCalled()

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
  const cafe = { id: 71, name: '상태 보존 카페', category: '카페', lat: 35.15, lng: 129.06 }
  const plan = { place_intent_frame: { anchor_location: '서면', candidate_place_types: ['카페'], required_features: ['주차'], radius_m: 1000 } }
  const response = { results: [cafe], decision_action: 'search', search_plan: plan, frontend_should_preserve_order: true }
  const send = async (user, text, first = false) => {
    const input = first ? screen.getByPlaceholderText('지금 어떤 장소가 필요하신가요?') : screen.getByLabelText('상황을 입력해 주세요')
    await user.clear(input)
    await user.type(input, text)
    await user.click(screen.getByRole('button', { name: '검색' }))
  }

  it('clarification은 기존 카드와 canonical 조건을 유지하고 action/value를 보냅니다', async () => {
    const action = { type: 'relax_constraints', condition_labels: ['주차'], value: 1000 }
    aiSearchRecommendations.mockResolvedValueOnce(response).mockResolvedValueOnce({ decision_action: 'ask_clarification', message: '반경을 좁힐까요?', search_plan: plan, clarification_options: [{ label: '1km로 변경', value: '1km', action }] }).mockResolvedValueOnce(response)
    const user = userEvent.setup(); renderHome()
    await send(user, '서면 카페', true)
    await screen.findByText(cafe.name)
    await send(user, '범위를 바꿔줘')
    await screen.findByRole('button', { name: '1km로 변경' })
    expect(screen.getByText(cafe.name)).toBeInTheDocument()
    expect(screen.getByText('주차 · 필수')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '1km로 변경' }))
    await waitFor(() => expect(aiSearchRecommendations).toHaveBeenCalledTimes(3))
    expect(aiSearchRecommendations.mock.calls[2][0].conversation_action).toEqual(action)
  })

  it('비교 답변은 기존 리스트를 유지하며 서버가 참조한 카드와 연결됩니다', async () => {
    aiSearchRecommendations.mockResolvedValueOnce({ ...response, results: [cafe, { ...cafe, id: 72, name: '두 번째 카페' }] }).mockResolvedValueOnce({ decision_action: 'compare_previous_results', results: [cafe], result_indexes: [0], message: '첫 번째 장소의 주차는 확인됐어요.' })
    const user = userEvent.setup(); renderHome()
    await send(user, '서면 카페', true); await screen.findByText(cafe.name)
    await send(user, '첫 번째와 두 번째 비교해줘')
    await screen.findByRole('button', { name: `${cafe.name} 카드 보기` })
    expect(screen.getByText('두 번째 카페')).toBeInTheDocument()
    expect(screen.getByText('주차 · 필수')).toBeInTheDocument()
  })

  it('서버 오류 뒤에도 카드·조건·검색어가 남고 동일 요청으로 재시도합니다', async () => {
    aiSearchRecommendations.mockResolvedValueOnce(response).mockRejectedValueOnce({ response: { status: 500, data: { detail: 'Django exception HTTP 500' } } }).mockResolvedValueOnce(response)
    const user = userEvent.setup(); renderHome()
    await send(user, '서면 카페', true); await screen.findByText(cafe.name)
    await send(user, '주차도 확인해줘')
    await screen.findByRole('alert')
    expect(screen.getByText(cafe.name)).toBeInTheDocument()
    expect(screen.getByText('주차 · 필수')).toBeInTheDocument()
    expect(screen.getByLabelText('상황을 입력해 주세요')).toHaveValue('주차도 확인해줘')
    expect(screen.queryByText(/Django exception/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '같은 조건으로 다시 시도' }))
    await waitFor(() => expect(aiSearchRecommendations).toHaveBeenCalledTimes(3))
    expect(aiSearchRecommendations.mock.calls[2][0].query).toBe(aiSearchRecommendations.mock.calls[1][0].query)
  })

  it('새 대화 뒤 도착한 이전 응답은 화면에 적용되지 않습니다', async () => {
    let resolveOld
    aiSearchRecommendations.mockReturnValue(new Promise(resolve => { resolveOld = resolve }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup(); renderHome()
    await send(user, '서면 카페', true)
    await waitFor(() => expect(aiSearchRecommendations).toHaveBeenCalledTimes(1))
    await user.click(screen.getByRole('button', { name: '새 대화' }))
    await act(async () => resolveOld(response))
    expect(screen.queryByText(cafe.name)).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText('지금 어떤 장소가 필요하신가요?')).toHaveValue('')
    expect(screen.queryByText('주차 · 필수')).not.toBeInTheDocument()
  })

  it('되돌리기는 저장된 결과 목록도 복원합니다', async () => {
    const replacement = { ...cafe, id: 73, name: '변경 후 카페' }
    aiSearchRecommendations.mockResolvedValueOnce(response)
      .mockResolvedValueOnce({ ...response, results: [replacement] })
      .mockResolvedValueOnce({ ...response, decision_action: 'undo_last_change', message: '마지막 변경을 되돌렸어요.' })
    const user = userEvent.setup(); renderHome()
    await send(user, '서면 카페', true); await screen.findByText(cafe.name)
    await send(user, '콘센트 필수'); await screen.findByText(replacement.name)
    await send(user, '방금 변경 취소')
    await waitFor(() => expect(screen.getAllByText(cafe.name).length).toBeGreaterThan(0))
    expect(screen.queryByText(replacement.name)).not.toBeInTheDocument()
  })

})
