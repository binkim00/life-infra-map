import { NavLink, Link } from 'react-router-dom'

import { getTierIcon, getTierLabel } from '@/utils/tierIcons'

import NotificationMenu from './NotificationMenu'

/**
 * app.css 가 `.nav-link.router-link-active` 를 보고 있습니다.
 * 스타일시트를 그대로 쓰기 위해 Vue Router 가 붙이던 클래스 이름을 유지합니다.
 */
const navLinkClassName = ({ isActive }, extraClass = '') => (
  ['nav-link', extraClass, isActive ? 'router-link-active' : ''].filter(Boolean).join(' ')
)

const AppHeader = ({
  user,
  isLoggedIn,
  isMypageActive,
  isCustomerCenterActive,
  isNotificationMenuOpen,
  isAccountMenuOpen,
  unreadNotificationCount,
  recentNotifications,
  notificationMenuRef,
  accountMenuRef,
  onToggleNotificationMenu,
  onToggleAccountMenu,
  onCloseAccountMenu,
  onMarkAllNotificationsRead,
  onSelectNotification,
  onLogout,
}) => {
  const isStaff = Boolean(user?.is_staff)
  const nicknameStyle = user?.nickname_color ? { color: user.nickname_color } : undefined

  return (
    <header className="app-header">
      <Link to="/" className="brand">
        <span className="brand-mark" aria-hidden="true">
          <span className="brand-pin">
            <span className="brand-dog">
              <span className="brand-dog-ear left" />
              <span className="brand-dog-ear right" />
              <span className="brand-dog-eye left" />
              <span className="brand-dog-eye right" />
              <span className="brand-dog-nose" />
              <span className="brand-dog-mouth" />
              <span className="brand-dog-cheek left" />
              <span className="brand-dog-cheek right" />
            </span>
          </span>
        </span>
        <span className="brand-text">
          <strong>여기일지도</strong>
        </span>
      </Link>

      <nav className="side-nav top-nav" aria-label="페이지 이동">
        <NavLink to="/" end className={navLinkClassName}>
          <span className="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="m3 10 9-7 9 7" />
              <path d="M5 9v11h5v-6h4v6h5V9" />
            </svg>
          </span>
          <span className="nav-text">홈</span>
        </NavLink>

        <NavLink to="/map" className={navLinkClassName}>
          <span className="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M9 18 3 21V6l6-3 6 3 6-3v15l-6 3-6-3Z" />
              <path d="M9 3v15" />
              <path d="M15 6v15" />
            </svg>
          </span>
          <span className="nav-text">지도</span>
        </NavLink>

        <NavLink to="/boards/notice" className={navLinkClassName}>
          <span className="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M6 4h11a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
              <path d="M8 8h.01" />
              <path d="M8 12h.01" />
              <path d="M11 8h5" />
              <path d="M11 12h5" />
            </svg>
          </span>
          <span className="nav-text">공지사항</span>
        </NavLink>

        <NavLink to="/boards/free" className={navLinkClassName}>
          <span className="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M4 5h16" />
              <path d="M4 12h16" />
              <path d="M4 19h10" />
            </svg>
          </span>
          <span className="nav-text">자유게시판</span>
        </NavLink>

        {isLoggedIn ? (
          <NavLink to="/mypage" className={navLinkClassName}>
            <span className="nav-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M20 21a8 8 0 0 0-16 0" />
                <path d="M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z" />
              </svg>
            </span>
            <span className="nav-text">마이페이지</span>
          </NavLink>
        ) : null}

        {isLoggedIn ? (
          <NavLink to="/inquiries/my" className={navLinkClassName}>
            <span className="nav-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z" />
                <path d="M8 9h8" />
                <path d="M8 13h5" />
              </svg>
            </span>
            <span className="nav-text">고객센터</span>
          </NavLink>
        ) : null}

        {isLoggedIn ? (
          <NavLink to="/place-report" className={navLinkClassName}>
            <span className="nav-text">장소 제보</span>
          </NavLink>
        ) : null}

        {isStaff ? (
          <NavLink to="/admin/reports" className={navLinkClassName}>
            <span className="nav-text">신고 내역</span>
          </NavLink>
        ) : null}

        {isStaff ? (
          <NavLink to="/admin/place-reports" className={navLinkClassName}>
            <span className="nav-text">장소 제보 검증</span>
          </NavLink>
        ) : null}

        {isStaff ? (
          <NavLink to="/admin/users" className={navLinkClassName}>
            <span className="nav-text">유저 관리</span>
          </NavLink>
        ) : null}

        {isStaff ? (
          <NavLink to="/admin/inquiries" className={navLinkClassName}>
            <span className="nav-text">문의 관리</span>
          </NavLink>
        ) : null}
      </nav>

      <nav className="sidebar-bottom-nav top-utility-nav" aria-label="설정 및 이용가이드">
        <NavLink to="/settings" className={(state) => navLinkClassName(state, 'utility-link')}>
          <span className="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z" />
              <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.36a1.7 1.7 0 0 0-1 .58V20a2 2 0 1 1-4 0v-.08a1.7 1.7 0 0 0-1-.58 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.64 15a1.7 1.7 0 0 0-.58-1H4a2 2 0 1 1 0-4h.08a1.7 1.7 0 0 0 .58-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.64a1.7 1.7 0 0 0 1-.58V4a2 2 0 1 1 4 0v.08a1.7 1.7 0 0 0 1 .58 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.36 9c.2.35.39.69.58 1H20a2 2 0 1 1 0 4h-.08a1.7 1.7 0 0 0-.52 1Z" />
            </svg>
          </span>
          <span className="nav-text">설정</span>
        </NavLink>

        <NavLink to="/guide" className={(state) => navLinkClassName(state, 'utility-link')}>
          <span className="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z" />
              <path d="M12 8v5" />
              <path d="M12 16h.01" />
            </svg>
          </span>
          <span className="nav-text">이용가이드</span>
        </NavLink>

        <NavLink to="/upgrade-guide" className={(state) => navLinkClassName(state, 'utility-link')}>
          <span className="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M12 3 4 7l8 4 8-4-8-4Z" />
              <path d="m4 11 8 4 8-4" />
              <path d="m4 15 8 4 8-4" />
            </svg>
          </span>
          <span className="nav-text">승급가이드</span>
        </NavLink>
      </nav>

      <div className="global-account-bar">
        {isLoggedIn ? (
          <>
            <div ref={notificationMenuRef} className="global-notification-menu">
              <NotificationMenu
                isOpen={isNotificationMenuOpen}
                unreadCount={unreadNotificationCount}
                recentNotifications={recentNotifications}
                onToggle={onToggleNotificationMenu}
                onMarkAllRead={onMarkAllNotificationsRead}
                onSelectNotification={onSelectNotification}
              />
            </div>

            <div ref={accountMenuRef} className="global-account-menu">
              <button
                type="button"
                className="global-user-link"
                aria-expanded={isAccountMenuOpen}
                onClick={onToggleAccountMenu}
              >
                <span className="global-avatar">
                  {user?.profile_image_url ? (
                    <img
                      src={user.profile_image_url}
                      alt={user?.nickname || user?.username}
                    />
                  ) : (
                    <span className="default-avatar" aria-hidden="true" />
                  )}
                </span>
                <span className="global-user-name">
                  <span style={nicknameStyle}>
                    {user?.nickname || user?.username}
                  </span>
                </span>
                {user?.tier ? (
                  <img
                    src={getTierIcon(user.tier)}
                    alt={user?.tier_label || getTierLabel(user.tier)}
                    className="global-tier-icon"
                  />
                ) : null}
                <span className="global-menu-caret" aria-hidden="true">▾</span>
              </button>

              {isAccountMenuOpen ? (
                <div className="account-dropdown">
                  <Link
                    to="/mypage?section=profile"
                    className={`account-menu-button${isMypageActive ? ' active' : ''}`}
                    onClick={onCloseAccountMenu}
                  >
                    <span>마이페이지</span>
                  </Link>

                  <Link
                    to="/inquiries/my"
                    className={`account-menu-button${isCustomerCenterActive ? ' active' : ''}`}
                    onClick={onCloseAccountMenu}
                  >
                    <span>고객센터</span>
                  </Link>

                  <button type="button" className="account-logout-button" onClick={onLogout}>
                    로그아웃
                  </button>
                </div>
              ) : null}
            </div>
          </>
        ) : (
          <>
            <Link to="/login" className="global-auth-button">
              로그인
            </Link>
            <Link to="/signup" className="global-auth-button signup">
              회원가입
            </Link>
          </>
        )}
      </div>
    </header>
  )
}

export default AppHeader
