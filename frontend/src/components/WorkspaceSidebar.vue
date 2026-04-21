<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import type { WorkspaceStepId } from '@/types'

const store = useWorkspaceStore()

const steps: Array<{
  id: WorkspaceStepId
  index: string
  title: string
  description: string
}> = [
  { id: 'data', index: '01', title: '基础数据', description: '模板、边界、水系' },
  { id: 'style', index: '02', title: '图层样式', description: '多流域和多水系视觉' },
  { id: 'stations', index: '03', title: '站点图层', description: 'Excel、符号、标注' },
  { id: 'output', index: '04', title: '输出设置', description: '标题、尺寸、DPI' }
]

const completedCount = computed(() => {
  return steps.filter((step) => store.stepReadiness[step.id]).length
})
</script>

<template>
  <aside class="workspace-sidebar">
    <div class="sidebar-card sidebar-card--hero">
      <p class="eyebrow">Render Flow</p>
      <h2>出图流程</h2>
      <p>按步骤配置；完成的步骤会自动变成绿色，最后在页面底部发起 ArcPy 出图。</p>
      <div class="progress-pill">{{ completedCount }}/4 数据就绪</div>
    </div>

    <nav class="step-nav" aria-label="出图配置步骤">
      <button
        v-for="step in steps"
        :key="step.id"
        class="step-button"
        :class="{
          'step-button--active': store.activeStep === step.id,
          'step-button--ready': store.stepReadiness[step.id]
        }"
        type="button"
        @click="store.setActiveStep(step.id)"
      >
        <span class="step-button__index">{{ step.index }}</span>
        <span>
          <strong>{{ step.title }}</strong>
          <small>{{ step.description }}</small>
        </span>
      </button>
    </nav>
  </aside>
</template>
