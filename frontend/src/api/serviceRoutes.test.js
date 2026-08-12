import { describe, expect, it } from 'vitest'

import { isSpringPath, stripTrailingSlash } from './serviceRoutes'

/**
 * 백엔드가 둘로 나뉜 사실은 코드만 봐서는 눈에 띄지 않습니다.
 * React 전환 중에 라우팅 규칙이 하나의 axios 인스턴스로 되돌아가면
 * 요청의 절반이 잘못된 서버로 가면서 404 가 납니다. 그 회귀를 여기서 잡습니다.
 */

describe('isSpringPath - Spring 이 담당하는 경로', () => {
  it.each([
    '/accounts/login/',
    '/accounts/signup/',
    '/accounts/me/',
    '/accounts/mypage/',
    '/accounts/me/nickname/',
    '/accounts/me/profile-image/',
    '/auth/login',
    '/boards/posts/',
    '/boards/posts/12/comments/',
    '/boards/reports/',
    '/notifications/',
    '/notifications/3/read/',
    '/inquiries/',
    '/inquiries/my/',
    '/admin/inquiries/',
    '/admin/users/',
    '/admin/users/7/penalties/',
    '/tiers',
    '/recommendations/saved-places/',
    '/recommendations/saved-places/5/',
  ])('%s 는 Spring 으로 보냅니다', (path) => {
    expect(isSpringPath(path)).toBe(true)
  })
})

describe('isSpringPath - Django 가 계속 담당하는 경로', () => {
  it.each([
    '/recommendations/ai-search/',
    '/recommendations/search-safety/',
    '/recommendations/conversational-search-plan/',
    '/recommendations/ai-web-search/',
    '/recommendations/places/',
    '/recommendations/map-search/',
    '/recommendations/kakao-place-tags/',
    '/recommendations/search-logs/',
    '/recommendations/preferences/',
    '/recommendations/preference-tags/',
    '/recommendations/place-reports/',
    '/recommendations/admin/place-reports/',
    '/recommendations/admin/place-reports/9/approve/',
  ])('%s 는 Django 로 보냅니다', (path) => {
    expect(isSpringPath(path)).toBe(false)
  })

  it('저장 장소만 Spring 이고 나머지 recommendations 는 Django 입니다', () => {
    expect(isSpringPath('/recommendations/saved-places/')).toBe(true)
    expect(isSpringPath('/recommendations/')).toBe(false)
  })

  it('/recommendations/admin 은 경로에 admin 이 들어가도 Django 입니다', () => {
    // '/admin/' 접두사 규칙은 앞에서부터 일치할 때만 적용됩니다.
    expect(isSpringPath('/recommendations/admin/place-reports/')).toBe(false)
  })
})

describe('isSpringPath - 경로 정규화', () => {
  it('앞 슬래시가 없어도 같게 판단합니다', () => {
    expect(isSpringPath('boards/posts/')).toBe(true)
    expect(isSpringPath('recommendations/ai-search/')).toBe(false)
  })

  it('빈 값이면 Django 기본값입니다', () => {
    expect(isSpringPath('')).toBe(false)
    expect(isSpringPath(undefined)).toBe(false)
    expect(isSpringPath(null)).toBe(false)
  })
})

describe('stripTrailingSlash - Spring 은 경로 끝 슬래시를 받지 않습니다', () => {
  it('끝 슬래시를 떼어 냅니다', () => {
    expect(stripTrailingSlash('/boards/posts/')).toBe('/boards/posts')
    expect(stripTrailingSlash('/accounts/me/')).toBe('/accounts/me')
  })

  it('슬래시가 없으면 그대로 둡니다', () => {
    expect(stripTrailingSlash('/auth/login')).toBe('/auth/login')
  })

  it('루트는 슬래시를 남깁니다', () => {
    expect(stripTrailingSlash('/')).toBe('/')
  })

  it('쿼리스트링은 보존하고 경로 끝만 정리합니다', () => {
    expect(stripTrailingSlash('/boards/posts/?board_type=free'))
      .toBe('/boards/posts?board_type=free')
  })

  it('슬래시가 여러 개여도 모두 떼어 냅니다', () => {
    expect(stripTrailingSlash('/notifications///')).toBe('/notifications')
  })
})
