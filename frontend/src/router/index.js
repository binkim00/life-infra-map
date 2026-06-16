import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/Homeview.vue'
import RecommendationTestView from '../views/RecommendationTestView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/recommendation-test',
      name: 'recommendation-test',
      component: RecommendationTestView,
    },
  ],
})

export default router
