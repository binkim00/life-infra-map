import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/Homeview.vue'
import LoginView from '@/views/LoginView.vue'
import SignupView from '@/views/SignupView.vue'
import BoardListView from '@/views/BoardListView.vue'
import BoardCreateView from '@/views/BoardCreateView.vue'
import BoardDetailView from '@/views/BoardDetailView.vue'
import BoardEditView from '@/views/BoardEditView.vue'
import ReportListView from '@/views/ReportListView.vue'
import MypageView from '@/views/MypageView.vue'
import InquiryCreateView from '@/views/InquiryCreateView.vue'
import AdminInquiryView from '@/views/AdminInquiryView.vue'
import AdminUserView from '@/views/AdminUserView.vue'
import AdminUserProfileView from '@/views/AdminUserProfileView.vue'
import NotificationView from '@/views/NotificationView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/boards/:boardType/:postId/edit',
      name: 'board-edit',
      component: BoardEditView,
    },
    {
      path: '/admin/reports',
      name: 'admin-reports',
      component: ReportListView,
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: AdminUserView,
    },
    {
      path: '/admin/users/:userId',
      name: 'admin-user-profile',
      component: AdminUserProfileView,
    },
    {
      path: '/admin/inquiries',
      name: 'admin-inquiries',
      component: AdminInquiryView,
    },
    {
      path: '/mypage',
      name: 'mypage',
      component: MypageView,
    },
    {
      path: '/notifications',
      name: 'notifications',
      component: NotificationView,
    },
    {
      path: '/inquiries/new',
      name: 'inquiry-create',
      component: InquiryCreateView,
    },
    {
      path: '/boards/:boardType/write',
      name: 'board-create',
      component: BoardCreateView,
    },
    {
      path: '/boards/:boardType/:postId/edit',
      name: 'board-edit',
      component: BoardEditView,
    },
    {
      path: '/boards/:boardType/:postId',
      name: 'board-detail',
      component: BoardDetailView,
    },
    {
      path: '/boards/:boardType',
      name: 'board-list',
      component: BoardListView,
    },
    {
      path: '/boards/:boardType/write',
      name: 'board-create',
      component: BoardCreateView,
    },
    {
      path: '/boards/:boardType/:postId',
      name: 'board-detail',
      component: BoardDetailView,
    },
    {
      path: '/',
      name: 'home',
      component: HomeView,
      props: {
        initialTab: 'search',
      },
    },
    {
      path: '/recommendation-test',
      name: 'recommendation-test',
      component: HomeView,
      props: {
        initialTab: 'recommendation',
      },
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
    },
    {
      path: '/signup',
      name: 'signup',
      component: SignupView,
    },
  ],
})

export default router
