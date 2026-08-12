import { beforeEach, describe, expect, it, vi } from 'vitest'

import api, { setUnauthorizedHandler } from './axios'

const DJANGO_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
const SPRING_BASE_URL = import.meta.env.VITE_SPRING_API_BASE_URL || 'http://127.0.0.1:8081/api'

/**
 * 인터셉터가 실제로 baseURL 을 바꾸는지 확인합니다.
 * serviceRoutes 규칙이 살아 있어도 인터셉터가 빠지면 전부 Django 로 갑니다.
 */
const runRequestInterceptors = async (config) => {
  const handlers = api.interceptors.request.handlers.filter(Boolean)

  return handlers.reduce(
    (chain, handler) => chain.then(handler.fulfilled),
    Promise.resolve({ headers: {}, ...config }),
  )
}

describe('요청 인터셉터 - 담당 서비스 라우팅', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('Spring 경로는 baseURL 을 Spring 으로 바꾸고 끝 슬래시를 뗍니다', async () => {
    const config = await runRequestInterceptors({ url: '/boards/posts/', method: 'get' })

    expect(config.baseURL).toBe(SPRING_BASE_URL)
    expect(config.url).toBe('/boards/posts')
  })

  it('Django 경로는 baseURL 과 끝 슬래시를 그대로 둡니다', async () => {
    const config = await runRequestInterceptors({
      url: '/recommendations/ai-search/',
      method: 'post',
    })

    // baseURL 을 건드리지 않으므로 인스턴스 기본값(Django)이 그대로 쓰입니다.
    expect(config.baseURL ?? api.defaults.baseURL).toBe(DJANGO_BASE_URL)
    expect(config.url).toBe('/recommendations/ai-search/')
  })

  it('저장 장소는 Spring, 장소 제보는 Django 입니다', async () => {
    const saved = await runRequestInterceptors({
      url: '/recommendations/saved-places/',
      method: 'get',
    })
    const reports = await runRequestInterceptors({
      url: '/recommendations/place-reports/',
      method: 'get',
    })

    expect(saved.baseURL).toBe(SPRING_BASE_URL)
    expect(reports.baseURL ?? api.defaults.baseURL).toBe(DJANGO_BASE_URL)
  })

  it('토큰이 있으면 두 서비스 모두 같은 Bearer 헤더를 받습니다', async () => {
    localStorage.setItem('authToken', 'jwt-token')

    const spring = await runRequestInterceptors({ url: '/boards/posts/', method: 'get' })
    const django = await runRequestInterceptors({
      url: '/recommendations/ai-search/',
      method: 'post',
    })

    expect(spring.headers.Authorization).toBe('Bearer jwt-token')
    expect(django.headers.Authorization).toBe('Bearer jwt-token')
  })

  it('토큰이 없으면 인증 헤더를 붙이지 않습니다', async () => {
    const config = await runRequestInterceptors({ url: '/boards/posts/', method: 'get' })

    expect(config.headers.Authorization).toBeUndefined()
  })
})

describe('응답 인터셉터 - 401 처리', () => {
  const runResponseErrorInterceptor = (error) => {
    const handler = api.interceptors.response.handlers.filter(Boolean)[0]

    return handler.rejected(error).catch((rejected) => rejected)
  }

  beforeEach(() => {
    localStorage.clear()
    setUnauthorizedHandler(null)
  })

  it('로그인한 사용자의 401 은 인증 상태를 지웁니다', async () => {
    localStorage.setItem('authToken', 'jwt-token')
    localStorage.setItem('authUser', '{"id":1}')
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)

    await runResponseErrorInterceptor({
      response: { status: 401 },
      config: { url: '/accounts/me/', method: 'get', headers: {} },
    })

    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('authToken')).toBeNull()
    expect(localStorage.getItem('authUser')).toBeNull()
  })

  it('로그인 실패(401)는 로그아웃 처리로 이어지지 않습니다', async () => {
    localStorage.setItem('authToken', 'jwt-token')
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)

    await runResponseErrorInterceptor({
      response: { status: 401 },
      config: { url: '/auth/login', method: 'post', headers: {} },
    })

    expect(onUnauthorized).not.toHaveBeenCalled()
    expect(localStorage.getItem('authToken')).toBe('jwt-token')
  })

  it('비로그인 상태의 401 은 무시합니다', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)

    await runResponseErrorInterceptor({
      response: { status: 401 },
      config: { url: '/boards/posts', method: 'get', headers: {} },
    })

    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})
