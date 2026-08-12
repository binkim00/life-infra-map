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
const saveSearchLog = vi.fn(() => Promise.resolve({}))

vi.mock('@/api/recommendation', () => ({
  aiSearchRecommendations: (...args) => aiSearchRecommendations(...args),
  buildConversationalSearchPlan: () => Promise.resolve(null),
  checkSearchSafety: () => Promise.resolve({ blocked: false }),
  getKakaoPlaceTags: () => Promise.resolve({ results: {} }),
  getSavedPlaces: () => Promise.resolve({ results: [] }),
  runAiWebSearch: () => Promise.resolve({ ai_web_search: {} }),
  saveSearchLog: (...args) => saveSearchLog(...args),
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
        screen.getByText(/조건에 맞는 장소를 찾지 못했어요|조건에 맞는 추천 결과가 없습니다/),
      ).toBeInTheDocument()
    })
  })
})
