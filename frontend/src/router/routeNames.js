import { matchPath } from 'react-router-dom'

/**
 * 화면 전환에서 공통으로 사용하는 라우트 이름입니다.
 * 헤더/마스코트가 화면을 이름으로 구분하고 있어서, 이름이 사라지면 그 분기가 전부 무너집니다.
 * 순서도 의미가 있습니다. /boards/:boardType/write 가 /boards/:boardType/:postId 보다 앞이어야 합니다.
 */
export const ROUTE_DEFINITIONS = [
  { path: '/admin/reports', name: 'admin-reports' },
  { path: '/admin/place-reports', name: 'admin-place-reports' },
  { path: '/admin/users', name: 'admin-users' },
  { path: '/admin/users/:userId', name: 'admin-user-profile' },
  { path: '/admin/inquiries', name: 'admin-inquiries' },
  { path: '/mypage', name: 'mypage' },
  { path: '/mypage/preferences', name: 'mypage-preferences' },
  { path: '/mypage/search-history', name: 'mypage-search-history' },
  { path: '/mypage/reports', name: 'mypage-place-reports' },
  { path: '/place-report', name: 'place-report' },
  { path: '/settings', name: 'settings' },
  { path: '/guide', name: 'guide' },
  { path: '/upgrade-guide', name: 'upgrade-guide' },
  { path: '/inquiries/new', name: 'inquiry-create' },
  { path: '/inquiries/my', name: 'my-inquiries' },
  { path: '/boards/:boardType/write', name: 'board-create' },
  { path: '/boards/:boardType/:postId/edit', name: 'board-edit' },
  { path: '/boards/:boardType/:postId', name: 'board-detail' },
  { path: '/boards/:boardType', name: 'board-list' },
  { path: '/', name: 'home' },
  { path: '/map', name: 'map-search' },
  { path: '/login', name: 'login' },
  { path: '/signup', name: 'signup' },
]

export const resolveRouteName = (pathname = '') => {
  const matched = ROUTE_DEFINITIONS.find(({ path }) => matchPath(path, pathname))

  return matched?.name || ''
}
