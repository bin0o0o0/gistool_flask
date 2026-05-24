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
  { id: 'data', index: '1', title: '数据准备', description: '上传模板与必要数据，检查数据完整性' },
  { id: 'style', index: '2', title: '图层配置', description: '配置图层样式，可见性与渲染规则' },
  { id: 'stations', index: '3', title: '出图参数', description: '设置标注、图例、版式与导出参数' },
  { id: 'output', index: '4', title: '导出结果', description: '预览版式并导出专题图成果' }
]

const summaryRows = computed(() => [
  {
    label: '流域边界',
    value: store.form.inputs.basin_boundaries.length ? 'DEM 提取结果' : '待加载',
    status: store.form.inputs.basin_boundaries.length ? '已加载' : '待上传'
  },
  {
    label: '河流网络',
    value: store.form.inputs.river_networks.length ? '主干河流（等级 > 3）' : '待加载',
    status: store.form.inputs.river_networks.length ? '已加载' : '待上传'
  },
  {
    label: '站点数据',
    value: store.form.inputs.station_layers.filter((layer) => layer.upload).length
      ? `水文站点（共 ${store.form.inputs.station_layers.filter((layer) => layer.upload).length} 个 Excel）`
      : '待加载',
    status: store.form.inputs.station_layers.some((layer) => layer.upload) ? '已加载' : '待上传'
  },
  {
    label: '输出格式',
    value: 'PNG / PDF / GeoTIFF',
    status: '可选择'
  }
])
</script>

<template>
  <aside class="workspace-sidebar sidebar-card">
    <div class="sidebar-block">
      <div class="sidebar-block__title">出图流程</div>
      <div class="flow-list">
        <button
          v-for="step in steps"
          :key="step.id"
          class="flow-card"
          :class="{ active: store.activeStep === step.id, ready: store.stepReadiness[step.id] }"
          type="button"
          @click="store.setActiveStep(step.id)"
        >
          <span class="flow-card__index">{{ step.index }}</span>
          <span class="flow-card__body">
            <strong>{{ step.title }}</strong>
            <small>{{ step.description }}</small>
          </span>
          <span class="flow-card__check">{{ store.stepReadiness[step.id] ? '●' : '' }}</span>
        </button>
      </div>
    </div>

    <div class="sidebar-block sidebar-block--summary">
      <div class="sidebar-block__title">已继承的流域参数</div>
      <div class="summary-list">
        <div v-for="row in summaryRows" :key="row.label" class="summary-row">
          <div>
            <strong>{{ row.label }}</strong>
            <small>{{ row.value }}</small>
          </div>
          <span class="summary-tag">{{ row.status }}</span>
        </div>
      </div>

      <button class="summary-cta" type="button">查看流域详情</button>
    </div>
  </aside>
</template>

<style scoped>
.workspace-sidebar {
  display: flex;
  flex-direction: column;
  height: var(--workbench-card-height);
  min-height: 0;
  overflow: hidden;
  padding: 11px;
  border: 1px solid rgba(168, 247, 255, 0.2);
  border-radius: 10px;
  background:
    linear-gradient(180deg, rgba(5, 32, 55, 0.82), rgba(3, 22, 39, 0.78)),
    rgba(4, 26, 45, 0.72);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.32);
  backdrop-filter: blur(22px);
  box-sizing: border-box;
}

.sidebar-block {
  padding: 0;
}

.sidebar-block__title {
  margin-bottom: 9px;
  color: #7cefff;
  font-size: 1rem;
  font-weight: 800;
}

.flow-list {
  display: grid;
  gap: 7px;
}

.flow-card {
  position: relative;
  display: grid;
  grid-template-columns: 42px 1fr 18px;
  gap: 10px;
  align-items: center;
  width: 100%;
  padding: 9px 10px 9px 9px;
  border: 1px solid rgba(168, 247, 255, 0.18);
  border-radius: 10px;
  background: rgba(8, 29, 49, 0.76);
  color: #eafcff;
  text-align: left;
  cursor: pointer;
}

.flow-card::after {
  position: absolute;
  left: 35px;
  bottom: -7px;
  width: 1px;
  height: 7px;
  background: rgba(130, 255, 240, 0.28);
  content: "";
}

.flow-card:last-child::after {
  display: none;
}

.flow-card.active {
  border-color: rgba(130, 255, 240, 0.4);
  background: rgba(14, 40, 63, 0.86);
}

.flow-card.ready .flow-card__check {
  color: #79f0c0;
}

.flow-card__index {
  display: grid;
  place-items: center;
  width: 40px;
  height: 50px;
  border-radius: 8px;
  border: 1px solid rgba(130, 255, 240, 0.18);
  color: #94f7ff;
  font-size: 1.78rem;
  font-style: italic;
  font-weight: 800;
}

.flow-card__body {
  display: grid;
  gap: 3px;
}

.flow-card__body strong {
  font-size: 0.98rem;
}

.flow-card__body small {
  color: rgba(230, 244, 250, 0.68);
  font-size: 0.74rem;
  line-height: 1.32;
}

.flow-card__check {
  justify-self: end;
  color: transparent;
}

.summary-list {
  display: grid;
  gap: 7px;
}

.sidebar-block--summary {
  margin-top: 13px;
}

.summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 44px;
  padding: 8px 9px;
  border: 1px solid rgba(168, 247, 255, 0.14);
  border-radius: 10px;
  background: rgba(8, 29, 49, 0.58);
}

.summary-row strong,
.summary-row small {
  display: block;
}

.summary-row strong {
  color: #edfaff;
  font-size: 0.88rem;
}

.summary-row small {
  margin-top: 2px;
  color: rgba(230, 244, 250, 0.7);
  font-size: 0.74rem;
  line-height: 1.28;
}

.summary-tag {
  flex: 0 0 auto;
  padding: 4px 7px;
  border-radius: 999px;
  background: rgba(103, 240, 190, 0.14);
  color: #7bf2c0;
  font-size: 0.68rem;
  font-weight: 700;
}

.summary-cta {
  width: 100%;
  min-height: 38px;
  margin-top: 9px;
  border: 1px solid rgba(168, 247, 255, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: #edfaff;
  cursor: pointer;
  font-size: 0.86rem;
  font-weight: 700;
}
</style>
