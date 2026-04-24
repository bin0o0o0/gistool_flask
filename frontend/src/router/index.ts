import { createRouter, createWebHistory } from 'vue-router'
import { routes } from '@/router/routes'

// 页面入口和功能路由集中在 routes.ts，便于给导航和预留页做测试保护。
const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
