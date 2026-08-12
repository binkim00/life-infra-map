/**
 * 요청을 어느 서비스로 보낼지 정합니다.
 *
 * 검색은 Django, 나머지(인증/게시판/알림/문의/저장장소/제보/관리자)는 Spring 이 담당합니다.
 * 이관 중에는 두 서비스가 같은 DB 를 보고 있어 어느 쪽으로 보내도 데이터는 같지만,
 * 담당이 정해진 경로는 담당 서비스로 보냅니다.
 */

// Spring 이 담당하는 경로입니다. 앞에서부터 일치하는지로 판단합니다.
const SPRING_PATH_PREFIXES = [
  '/accounts/',
  '/auth/',
  '/boards/',
  '/notifications',
  '/inquiries',
  '/admin/',
  '/tiers',
  '/recommendations/saved-places',
  '/recommendations/place-reports',
  '/recommendations/admin/place-reports',
]

// 이관이 끝나 Django 로 돌려보낼 경로는 없습니다.
// 되돌릴 일이 생기면 여기에 경로를 넣으면 그 경로만 Django 로 갑니다.
const DJANGO_OVERRIDE_PREFIXES = []

const normalize = (url = '') => {
  const path = String(url || '')
  return path.startsWith('/') ? path : `/${path}`
}

export const isSpringPath = (url) => {
  const path = normalize(url)
  if (DJANGO_OVERRIDE_PREFIXES.some((prefix) => path.startsWith(prefix))) {
    return false
  }
  return SPRING_PATH_PREFIXES.some((prefix) => path.startsWith(prefix))
}

/**
 * Django 는 경로 끝 슬래시를 요구하지만 Spring 은 붙으면 404 가 납니다.
 * 프론트 호출부를 전부 고치지 않도록 Spring 으로 보낼 때만 떼어 냅니다.
 */
export const stripTrailingSlash = (url) => {
  const path = normalize(url)
  const [pathname, query = ''] = path.split('?')
  const trimmed = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  return query ? `${trimmed}?${query}` : trimmed
}
