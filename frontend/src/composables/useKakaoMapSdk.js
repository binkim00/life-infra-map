const KAKAO_MAP_SDK_SELECTOR =
  'script[data-kakao-map-sdk="true"], script[src*="dapi.kakao.com/v2/maps/sdk.js"]'
const DEFAULT_KAKAO_MAP_LOAD_TIMEOUT_MS = 12000
const DEFAULT_KAKAO_MAP_LOAD_ERROR_MESSAGE =
  '카카오맵 SDK를 불러오지 못했습니다.'

let kakaoMapSdkLoadPromise = null

export const hasKakaoMapServices = () => {
  return typeof window !== 'undefined' && Boolean(window.kakao?.maps?.services)
}

export const loadKakaoMapScript = ({
  timeoutMs = DEFAULT_KAKAO_MAP_LOAD_TIMEOUT_MS,
  errorMessage = DEFAULT_KAKAO_MAP_LOAD_ERROR_MESSAGE,
} = {}) => {
  if (hasKakaoMapServices()) {
    return Promise.resolve()
  }

  if (kakaoMapSdkLoadPromise) {
    return kakaoMapSdkLoadPromise
  }

  kakaoMapSdkLoadPromise = new Promise((resolve, reject) => {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      reject(new Error(errorMessage))
      return
    }

    const kakaoKey = import.meta.env.VITE_KAKAO_JAVASCRIPT_KEY
    const existingScript = document.querySelector(KAKAO_MAP_SDK_SELECTOR)
    let settled = false
    let timeoutId = null

    const settle = (callback) => {
      if (settled) return
      settled = true
      if (timeoutId) {
        window.clearTimeout(timeoutId)
      }
      callback()
    }

    const rejectLoad = () => {
      settle(() => reject(new Error(errorMessage)))
    }

    const resolveAfterMapsLoad = () => {
      if (hasKakaoMapServices()) {
        settle(resolve)
        return
      }

      if (!window.kakao?.maps?.load) {
        rejectLoad()
        return
      }

      window.kakao.maps.load(() => {
        if (hasKakaoMapServices()) {
          settle(resolve)
          return
        }

        rejectLoad()
      })
    }

    timeoutId = window.setTimeout(rejectLoad, timeoutMs)

    if (existingScript) {
      existingScript.dataset.kakaoMapSdk = 'true'
      if (window.kakao?.maps) {
        resolveAfterMapsLoad()
        return
      }

      existingScript.addEventListener('load', resolveAfterMapsLoad, { once: true })
      existingScript.addEventListener('error', rejectLoad, { once: true })
      return
    }

    if (!kakaoKey) {
      settle(() => reject(new Error('VITE_KAKAO_JAVASCRIPT_KEY가 설정되지 않았습니다.')))
      return
    }

    const script = document.createElement('script')
    script.dataset.kakaoMapSdk = 'true'
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(kakaoKey)}&autoload=false&libraries=services`
    script.async = true
    script.onload = resolveAfterMapsLoad
    script.onerror = rejectLoad
    document.head.appendChild(script)
  }).catch((error) => {
    kakaoMapSdkLoadPromise = null
    throw error
  })

  return kakaoMapSdkLoadPromise
}

export const waitForKakaoServices = loadKakaoMapScript
