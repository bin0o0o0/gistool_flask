<script setup lang="ts">
import { onMounted, ref } from 'vue'

import MapOutputControlPanel from '@/components/MapOutputControlPanel.vue'
import SiteNav from '@/components/SiteNav.vue'
import WorkspacePreviewMap from '@/components/WorkspacePreviewMap.vue'
import WorkspaceSidebar from '@/components/WorkspaceSidebar.vue'
import { useWorkspaceStore } from '@/stores/workspace'
import heroBackground from '@/assets/home-water-basin-bg.png'

const store = useWorkspaceStore()
const previewMode = ref<'map' | 'layout'>('map')

onMounted(() => {
  store.fetchOptions()
})
</script>

<template>
  <div class="workspace-page" :style="{ '--hero-background': `url(${heroBackground})` }">
    <SiteNav />

    <main class="workspace-workbench">
      <section class="workspace-hero">
        <div>
          <p class="workspace-hero__kicker">WATERSHED MAP RENDERING WORKBENCH</p>
          <h1>流域出图</h1>
          <p>上传 APRX 模板，配置流域边界、河流网络与站点数据，生成高质量专题地图。</p>
        </div>
      </section>

      <section class="workspace-grid workspace-stage">
        <WorkspaceSidebar />

        <section class="workspace-map-column">
          <WorkspacePreviewMap :form="store.form" :render-result="store.renderResult" :layout-mode="previewMode" />
        </section>

        <aside class="workspace-control-column">
          <section class="panel-card workspace-control-card">
            <MapOutputControlPanel @preview-layout="previewMode = 'layout'" />
          </section>
        </aside>
      </section>

      <footer class="workspace-footer-note">
        <span class="workspace-footer-note__icon">i</span>
        <span>提示：建议先预览版式，确认无误后再生成正式成果。</span>
      </footer>
    </main>
  </div>
</template>

<style scoped>
.workspace-page {
  min-height: 100vh;
  background:
    linear-gradient(180deg, rgba(2, 11, 29, 0.78) 0%, rgba(2, 11, 29, 0.62) 40%, rgba(2, 11, 29, 0.84) 100%),
    linear-gradient(115deg, rgba(7, 32, 52, 0.7) 0%, rgba(7, 32, 52, 0.35) 46%, rgba(7, 32, 52, 0.08) 100%),
    var(--hero-background) center / cover no-repeat,
    #03162d;
  color: #eefbff;
}

.workspace-workbench {
  --workbench-card-height: clamp(680px, calc(100vh - 276px), 720px);

  width: min(100% - 48px, 1760px);
  margin: 0 auto;
  padding: 2px 0 28px;
}

.workspace-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
  margin: 4px 0 14px;
}

.workspace-hero__kicker {
  margin: 0 0 12px;
  color: #82fff0;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.workspace-hero h1 {
  margin: 0;
  font-family: "STKaiti", "KaiTi", "FangSong", serif;
  font-size: clamp(3.4rem, 5.8vw, 6rem);
  line-height: 0.92;
  text-shadow: 0 0 18px rgba(106, 244, 240, 0.22);
}

.workspace-hero p:last-child {
  margin: 12px 0 0;
  max-width: 840px;
  color: rgba(234, 250, 255, 0.82);
  font-size: 1.02rem;
  line-height: 1.72;
}

.workspace-grid {
  display: grid;
  grid-template-columns: 280px minmax(420px, 1fr) 340px;
  gap: 14px;
  align-items: start;
}

.workspace-map-column,
.workspace-control-column {
  min-width: 0;
}

.workspace-map-column {
  height: var(--workbench-card-height);
}

.workspace-control-column {
  height: var(--workbench-card-height);
}

.panel-card {
  border: 1px solid rgba(168, 247, 255, 0.2);
  border-radius: 10px;
  background:
    linear-gradient(180deg, rgba(5, 32, 55, 0.86), rgba(3, 22, 39, 0.84)),
    rgba(4, 26, 45, 0.78);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.32);
  backdrop-filter: blur(22px);
}

.workspace-control-card {
  display: flex;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: 16px;
  box-sizing: border-box;
}

.workspace-control-card :deep(.el-input__wrapper),
.workspace-control-card :deep(.el-textarea__inner),
.workspace-control-card :deep(.el-select__wrapper),
.workspace-control-card :deep(.el-input-number__wrapper) {
  border-color: rgba(168, 247, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  box-shadow: none;
}

.workspace-control-card :deep(.el-input__inner),
.workspace-control-card :deep(.el-select__selected-item),
.workspace-control-card :deep(.el-input-number__input),
.workspace-control-card :deep(.el-textarea__inner) {
  color: #edfaff;
}

.workspace-control-card :deep(.el-switch__core),
.workspace-control-card :deep(.el-slider__runway) {
  background: rgba(255, 255, 255, 0.12);
}

.workspace-footer-note {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  margin-top: 14px;
  padding-top: 16px;
  border-top: 1px solid rgba(168, 247, 255, 0.12);
  color: rgba(230, 244, 250, 0.76);
  font-size: 0.96rem;
}

.workspace-footer-note__icon {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid rgba(230, 244, 250, 0.42);
  border-radius: 50%;
  font-size: 0.74rem;
  font-weight: 800;
}

@media (max-width: 1180px) {
  .workspace-grid {
    grid-template-columns: 290px minmax(0, 1fr);
  }

  .workspace-control-column {
    grid-column: 1 / -1;
    height: auto;
  }
}

@media (max-width: 860px) {
  .workspace-workbench {
    width: min(100% - 28px, 1760px);
  }

  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .workspace-hero h1 {
    font-size: clamp(3rem, 15vw, 4.6rem);
  }
}
</style>
