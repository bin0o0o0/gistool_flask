<script setup lang="ts">
import { useWorkspaceStore } from '@/stores/workspace'
import type { WorkspaceStepId } from '@/types'

const store = useWorkspaceStore()

const steps: Array<{
  id: WorkspaceStepId
  index: string
  title: string
}> = [
  { id: 'data', index: '1', title: '数据准备' },
  { id: 'style', index: '2', title: '图层配置' },
  { id: 'stations-style', index: '3', title: '标注样式与位置' },
  { id: 'stations-attrs', index: '4', title: '标注属性' },
  { id: 'output', index: '5', title: '导出结果' }
]
</script>

<template>
  <nav class="step-nav">
    <button
      v-for="(step, i) in steps"
      :key="step.id"
      class="step-btn"
      :class="{ active: store.activeStep === step.id, ready: store.stepReadiness[step.id] }"
      type="button"
      @click="store.setActiveStep(step.id)"
    >
      <span class="step-btn__index">{{ step.index }}</span>
      <span class="step-btn__title">{{ step.title }}</span>
      <span v-if="i < steps.length - 1" class="step-connector"></span>
    </button>
  </nav>
</template>

<style scoped>
.step-nav {
  display: flex;
  justify-content: center;
  gap: 0;
  align-items: stretch;
}

.step-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 140px;
  max-width: 180px;
  min-height: 44px;
  padding: 0 16px;
  border: 1px solid rgba(168, 247, 255, 0.18);
  border-radius: 10px;
  background: rgba(8, 29, 49, 0.76);
  color: #eafcff;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.step-btn:not(:last-child) {
  margin-right: 28px;
}

.step-btn:hover {
  border-color: rgba(130, 255, 240, 0.35);
  background: rgba(14, 40, 63, 0.86);
}

.step-btn.active {
  border-color: rgba(130, 255, 240, 0.55);
  background: rgba(14, 40, 63, 0.92);
  box-shadow: 0 0 20px rgba(130, 255, 240, 0.12);
}

.step-btn.ready::before {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #79f0c0;
  content: "";
}

.step-btn__index {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid rgba(130, 255, 240, 0.2);
  color: #94f7ff;
  font-size: 1rem;
  font-style: italic;
  font-weight: 800;
  flex-shrink: 0;
}

.step-btn.active .step-btn__index {
  border-color: rgba(130, 255, 240, 0.45);
  background: rgba(130, 255, 240, 0.12);
}

.step-btn__title {
  font-size: 0.92rem;
  font-weight: 700;
}

.step-connector {
  position: absolute;
  top: 50%;
  right: -28px;
  width: 28px;
  height: 2px;
  background: rgba(130, 255, 240, 0.28);
  transform: translateY(-50%);
  pointer-events: none;
}

@media (max-width: 860px) {
  .step-nav {
    gap: 6px;
  }

  .step-btn {
    min-width: auto;
    min-height: 38px;
    padding: 0 10px;
    gap: 6px;
  }

  .step-btn:not(:last-child) {
    margin-right: 16px;
  }

  .step-connector {
    right: -16px;
    width: 16px;
  }

  .step-btn__index {
    width: 24px;
    height: 24px;
    font-size: 0.85rem;
  }

  .step-btn__title {
    font-size: 0.78rem;
  }
}
</style>
