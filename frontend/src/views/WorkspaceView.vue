<script setup lang="ts">
import { onMounted } from 'vue'
import AppShell from '@/components/AppShell.vue'
import FileUploadCard from '@/components/FileUploadCard.vue'
import LayerStylePanel from '@/components/LayerStylePanel.vue'
import OutputSettings from '@/components/OutputSettings.vue'
import RequestPreview from '@/components/RequestPreview.vue'
import ResultPanel from '@/components/ResultPanel.vue'
import StationLayerEditor from '@/components/StationLayerEditor.vue'
import WorkspaceSidebar from '@/components/WorkspaceSidebar.vue'
import { useWorkspaceStore } from '@/stores/workspace'

const store = useWorkspaceStore()

// 页面加载时同步后端能力列表，让前端选项始终跟当前 Flask/ArcPy 渲染器一致。
onMounted(() => {
  store.fetchOptions()
})
</script>

<template>
  <AppShell
    title="流域图出图工作台"
    description="上传数据，调整站点符号、标注和流域样式，最后用 ArcGIS Pro 后端导出可交付的 PNG。"
>
    <div class="workspace-shell">
      <WorkspaceSidebar />

      <main class="workspace-stage">
        <Transition name="workspace-fade" mode="out-in">
          <FileUploadCard v-if="store.activeStep === 'data'" key="data" />
          <OutputSettings v-else-if="store.activeStep === 'output'" key="output" />
          <LayerStylePanel v-else-if="store.activeStep === 'style'" key="style" />
          <StationLayerEditor v-else-if="store.activeStep === 'stations'" key="stations" />
          <StationLayerEditor v-else key="stations-fallback" />
        </Transition>
        <div class="workspace-bottom">
          <RequestPreview />
          <ResultPanel />
        </div>
      </main>
    </div>
  </AppShell>
</template>
