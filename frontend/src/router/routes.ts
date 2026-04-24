import type { RouteRecordRaw } from 'vue-router'
import ComingSoonView from '@/views/ComingSoonView.vue'
import HomeView from '@/views/HomeView.vue'
import WorkspaceView from '@/views/WorkspaceView.vue'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: HomeView
  },
  {
    path: '/watershed-extract',
    name: 'watershed-extract',
    component: ComingSoonView,
    props: {
      eyebrow: 'Reserved Feature',
      title: '流域提取功能建设中',
      description: '流域提取功能正在规划中，后续将接入 DEM 分析、河网提取与子流域划分流程。'
    }
  },
  {
    path: '/map-output',
    name: 'map-output',
    component: WorkspaceView
  },
  {
    path: '/guide',
    name: 'guide',
    component: ComingSoonView,
    props: {
      eyebrow: 'Documentation',
      title: '使用指南整理中',
      description: '使用指南正在整理中，后续将提供数据准备、APRX 模板、站点 Excel 和出图流程说明。'
    }
  },
  {
    path: '/workspace',
    redirect: '/map-output'
  }
]
