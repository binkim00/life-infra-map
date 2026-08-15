import { createBrowserRouter, Navigate } from 'react-router-dom'

import App from '@/App'
import AdminInquiryView from '@/views/AdminInquiryView'
import AdminPlaceReportsView from '@/views/AdminPlaceReportsView'
import AdminUserProfileView from '@/views/AdminUserProfileView'
import AdminUserView from '@/views/AdminUserView'
import BoardCreateView from '@/views/BoardCreateView'
import BoardDetailView from '@/views/BoardDetailView'
import BoardEditView from '@/views/BoardEditView'
import BoardListView from '@/views/BoardListView'
import GuideView from '@/views/GuideView'
import HomeView from '@/views/HomeView'
import InquiryCreateView from '@/views/InquiryCreateView'
import LoginView from '@/views/LoginView'
import MapSearchView from '@/views/MapSearchView'
import MyInquiryView from '@/views/MyInquiryView'
import MypageView from '@/views/MypageView'
import MyPlaceReportsView from '@/views/MyPlaceReportsView'
import PlaceReportView from '@/views/PlaceReportView'
import PreferenceSettingsView from '@/views/PreferenceSettingsView'
import ReportListView from '@/views/ReportListView'
import SearchHistoryView from '@/views/SearchHistoryView'
import SettingsView from '@/views/SettingsView'
import SignupView from '@/views/SignupView'
import UpgradeGuideView from '@/views/UpgradeGuideView'

/**
 * 애플리케이션 경로와 라우트 우선순위를 정의합니다.
 * 화면 이름은 @/router/routeNames.js 가 들고 있습니다.
 */
const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { path: 'admin/reports', element: <ReportListView /> },
      { path: 'admin/place-reports', element: <AdminPlaceReportsView /> },
      { path: 'admin/users', element: <AdminUserView /> },
      { path: 'admin/users/:userId', element: <AdminUserProfileView /> },
      { path: 'admin/inquiries', element: <AdminInquiryView /> },
      { path: 'mypage', element: <MypageView /> },
      { path: 'mypage/preferences', element: <PreferenceSettingsView /> },
      { path: 'mypage/search-history', element: <SearchHistoryView /> },
      { path: 'mypage/reports', element: <MyPlaceReportsView /> },
      { path: 'place-report', element: <PlaceReportView /> },
      { path: 'settings', element: <SettingsView /> },
      { path: 'guide', element: <GuideView /> },
      { path: 'upgrade-guide', element: <UpgradeGuideView /> },
      { path: 'inquiries/new', element: <InquiryCreateView /> },
      { path: 'inquiries/my', element: <MyInquiryView /> },
      { path: 'boards/:boardType/write', element: <BoardCreateView /> },
      { path: 'boards/:boardType/:postId/edit', element: <BoardEditView /> },
      { path: 'boards/:boardType/:postId', element: <BoardDetailView /> },
      { path: 'boards/:boardType', element: <BoardListView /> },
      { index: true, element: <HomeView initialTab="search" /> },
      { path: 'map', element: <MapSearchView /> },
      { path: 'recommendation-test', element: <Navigate to="/map" replace /> },
      { path: 'login', element: <LoginView /> },
      { path: 'signup', element: <SignupView /> },
    ],
  },
])

export default router
