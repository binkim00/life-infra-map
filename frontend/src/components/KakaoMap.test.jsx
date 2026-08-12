import { render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import KakaoMap from './KakaoMap'

vi.mock('@/hooks/useKakaoMapSdk', () => ({
  loadKakaoMapScript: () => Promise.resolve(),
}))

/**
 * 지도는 React 밖에서 DOM 과 전역 리스너를 직접 다룹니다.
 * 언마운트할 때 정리가 빠지면 리스너와 타이머가 남아 콘솔 에러로 이어지므로 여기서 확인합니다.
 */
const createKakaoStub = () => {
  const listeners = []
  const createdMarkers = []

  class LatLng {
    constructor(lat, lng) {
      this.lat = lat
      this.lng = lng
    }

    getLat() { return this.lat }

    getLng() { return this.lng }
  }

  const map = {
    setCenter: vi.fn(),
    setBounds: vi.fn(),
    panTo: vi.fn(),
    relayout: vi.fn(),
    getCenter: () => new LatLng(37.5665, 126.978),
    getBounds: () => ({
      getSouthWest: () => new LatLng(37.5, 126.9),
      getNorthEast: () => new LatLng(37.6, 127.0),
    }),
    getProjection: () => ({
      // 겹침 판정(30px)에 걸리지 않도록 좌표마다 충분히 떨어진 화면 좌표를 돌려줍니다.
      containerPointFromCoords: (position) => ({
        x: (position.getLng() - 126.9) * 100000,
        y: (position.getLat() - 37.5) * 100000,
      }),
    }),
  }

  return {
    kakao: {
      maps: {
        services: {},
        LatLng,
        Size: class {},
        Point: class {},
        MarkerImage: class {},
        LatLngBounds: class {
          extend() {}
        },
        // new 로 부르므로 화살표 함수를 쓰면 안 됩니다.
        Map: vi.fn(function KakaoMapStub() {
          return map
        }),
        Marker: vi.fn(function MarkerStub() {
          const marker = { setMap: vi.fn(), setImage: vi.fn() }
          createdMarkers.push(marker)
          return marker
        }),
        InfoWindow: vi.fn(function InfoWindowStub() {
          return {
            open: vi.fn(),
            close: vi.fn(),
            setPosition: vi.fn(),
          }
        }),
        event: {
          addListener: vi.fn((target, type, handler) => {
            listeners.push({ target, type, handler })
          }),
        },
      },
    },
    map,
    listeners,
    createdMarkers,
  }
}

const PLACES = [
  { id: 'a', name: '카페 A', lat: 37.5, lng: 127.0, markerLabel: '1' },
  { id: 'b', name: '카페 B', lat: 37.51, lng: 127.01, markerLabel: '2' },
]

describe('KakaoMap', () => {
  let stub

  beforeEach(() => {
    stub = createKakaoStub()
    window.kakao = stub.kakao
  })

  afterEach(() => {
    delete window.kakao
    vi.restoreAllMocks()
  })

  it('SDK 가 준비되면 장소마다 마커를 만듭니다', async () => {
    render(<KakaoMap places={PLACES} />)

    await waitFor(() => {
      expect(stub.createdMarkers).toHaveLength(2)
    })
  })

  it('언마운트하면 마커와 전역 리스너를 정리합니다', async () => {
    const removeDocumentListener = vi.spyOn(document, 'removeEventListener')
    const removeWindowListener = vi.spyOn(window, 'removeEventListener')

    const { unmount } = render(<KakaoMap places={PLACES} />)

    await waitFor(() => {
      expect(stub.createdMarkers).toHaveLength(2)
    })

    unmount()

    stub.createdMarkers.forEach((marker) => {
      expect(marker.setMap).toHaveBeenCalledWith(null)
    })
    expect(removeDocumentListener).toHaveBeenCalledWith('click', expect.any(Function), true)
    expect(removeWindowListener).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    expect(removeWindowListener).toHaveBeenCalledWith('resize', expect.any(Function))
  })

  it('언마운트 뒤에는 남은 타이머가 콜백을 부르지 않습니다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const onCenterChange = vi.fn()

    const { unmount, rerender } = render(
      <KakaoMap places={PLACES} layoutKey={1} onCenterChange={onCenterChange} />,
    )

    await vi.waitFor(() => {
      expect(stub.createdMarkers).toHaveLength(2)
    })

    // relayout 은 150ms/320ms 뒤에 다시 도는 타이머를 겁니다.
    rerender(<KakaoMap places={PLACES} layoutKey={2} onCenterChange={onCenterChange} />)
    unmount()
    onCenterChange.mockClear()

    await vi.advanceTimersByTimeAsync(500)

    expect(onCenterChange).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('부모가 같은 내용의 새 배열을 넘겨도 마커를 다시 그리지 않습니다', async () => {
    const { rerender } = render(<KakaoMap places={PLACES} />)

    await waitFor(() => {
      expect(stub.createdMarkers).toHaveLength(2)
    })

    rerender(<KakaoMap places={PLACES.map((place) => ({ ...place }))} />)

    expect(stub.createdMarkers).toHaveLength(2)
  })

  it('장소가 실제로 바뀌면 마커를 다시 그립니다', async () => {
    const { rerender } = render(<KakaoMap places={PLACES} />)

    await waitFor(() => {
      expect(stub.createdMarkers).toHaveLength(2)
    })

    rerender(<KakaoMap places={[...PLACES, { id: 'c', name: '카페 C', lat: 37.52, lng: 127.02, markerLabel: '3' }]} />)

    await waitFor(() => {
      expect(stub.createdMarkers).toHaveLength(5)
    })
  })
})
