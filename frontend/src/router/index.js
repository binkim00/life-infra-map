import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/Homeview.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
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
  ],
})

export default router
