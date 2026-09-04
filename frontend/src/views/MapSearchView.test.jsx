import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MapSearchView from './MapSearchView'

const searchMapPlaces = vi.fn()

vi.mock('@/api/recommendation', () => ({
  searchMapPlaces: (...args) => searchMapPlaces(...args),
}))

vi.mock('@/hooks/useSavedPlaceActions', () => ({
  useSavedPlaceActions: () => ({
    savingPlaceId: null,
    saveMessage: '',
    isPlaceSaved: () => false,
    loadSavedPlaceKeys: vi.fn(),
    savePlace: vi.fn(),
  }),
}))

vi.mock('@/components/KakaoMap', () => ({
  default: ({ places, layoutKey, onCenterChange, onSelectPlace }) => {
    useEffect(() => {
      onCenterChange({ center: { lat: 36.35, lng: 127.8 } })
      // KakaoMap emits its initial viewport once after SDK initialization.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    return (
      <div data-testid="map" data-layout-key={layoutKey}>
        <button
          type="button"
          onClick={() => onCenterChange({ center: { lat: 35.2, lng: 129.1 } })}
        >
          지도 이동
        </button>
        {places[0] ? (
          <button type="button" onClick={() => onSelectPlace(places[0])}>첫 마커</button>
        ) : null}
      </div>
    )
  },
}))

describe('MapSearchView', () => {
  beforeEach(() => {
    searchMapPlaces.mockReset()
    searchMapPlaces.mockResolvedValue({
      candidate_counts: { db: 1, kakao: 0, db_total: 1 },
      results: [{
        id: 1,
        result_source: 'db',
        name: '사상역 4번 출구 흡연구역',
        category: 'smoking_area',
        category_label: '흡연구역',
        address: '부산 사상구',
        lat: 35.1622,
        lng: 128.9846,
        smoking: {
          facility_type: 'designated_smoking_area',
          facility_type_label: '지정 흡연구역',
          verification_level: 'PUBLIC_DATA',
          verification_level_label: '공공데이터 확인',
          location_description: '사상역 4번 출구 밖',
        },
      }],
    })
  })

  it('uses the moved map center and shows public smoking-place details', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <MapSearchView />
      </MemoryRouter>,
    )

    await user.type(screen.getByPlaceholderText(/서면역 약국/), '사상역 흡연구역')
    await user.click(screen.getByRole('button', { name: '지도 이동' }))
    await user.click(screen.getByRole('button', { name: '현재 지도에서 재검색' }))

    await waitFor(() => {
      expect(searchMapPlaces).toHaveBeenCalledWith(expect.objectContaining({
        q: '사상역 흡연구역',
        lat: 35.2,
        lng: 129.1,
      }))
    })

    await user.click(screen.getByRole('button', { name: '첫 마커' }))
    expect(screen.getByText('지정 흡연구역')).toBeInTheDocument()
    expect(screen.getByText('공공데이터 확인')).toBeInTheDocument()
    expect(screen.getByText('사상역 4번 출구 밖')).toBeInTheDocument()
    expect(screen.getByTestId('map')).toHaveAttribute('data-layout-key', 'detail-open')
  })
})
