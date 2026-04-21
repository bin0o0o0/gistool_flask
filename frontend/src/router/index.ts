import { createRouter, createWebHistory } from 'vue-router'
import WorkspaceView from '@/views/WorkspaceView.vue'

// 第一版只做单用户本机工作台，所以路由保持极简；以后接入任务中心时再扩展。
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'workspace',
      component: WorkspaceView
    }
  ]
})

export default router
