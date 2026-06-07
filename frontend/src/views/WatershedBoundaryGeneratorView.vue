<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Download, Location } from '@element-plus/icons-vue'

import SiteNav from '@/components/SiteNav.vue'
import WatershedBoundaryPreviewMap from '@/components/WatershedBoundaryPreviewMap.vue'
import { getApiErrorMessage } from '@/api/client'
import { watershedBoundaryApi } from '@/api/watershedBoundary'
import heroBackground from '@/assets/home-water-basin-bg.png'
import type {
  GeoJsonFeatureCollection,
  WatershedBoundaryBbox,
  WatershedBoundaryGenerateData,
  WatershedBoundaryPoint
} from '@/types'

const DEFAULT_DEM_PATH = 'D:\\work\\data\\data\\dem\\dem.tif'
const DEFAULT_SNAP_THRESHOLD = 2000

const state = reactive({
  demPath: DEFAULT_DEM_PATH,
  pointX: '105.20',
  pointY: '27.06',
  minX: '105.00',
  minY: '26.95',
  maxX: '105.30',
  maxY: '27.12',
  snapThreshold: String(DEFAULT_SNAP_THRESHOLD)
})

const isSubmitting = ref(false)
const successMessage = ref('')
const errorMessage = ref('')
const resultData = ref<WatershedBoundaryGenerateData | null>(null)

const previewPoint = computed<WatershedBoundaryPoint>(() => ({
  x: Number(state.pointX) || 105.2,
  y: Number(state.pointY) || 27.06
}))

const previewBbox = computed<WatershedBoundaryBbox>(() => ({
  min_x: Number(state.minX) || 105.0,
  min_y: Number(state.minY) || 26.95,
  max_x: Number(state.maxX) || 105.3,
  max_y: Number(state.maxY) || 27.12
}))

const mapResult = computed<GeoJsonFeatureCollection | null>(() => resultData.value?.result || null)

onMounted(async () => {
  try {
    const response = await watershedBoundaryApi.getDefaults()
    if (!response.data.success || !response.data.data) return
    state.demPath = response.data.data.dem_path || DEFAULT_DEM_PATH
    state.snapThreshold = String(response.data.data.snap_threshold || DEFAULT_SNAP_THRESHOLD)
  } catch {
    // Keep the local fallback defaults when the service-specific defaults API is unavailable.
  }
})

function clearNotice() {
  successMessage.value = ''
  errorMessage.value = ''
}

function parseNumber(value: string, label: string) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) throw new Error(`${label} 必须是有效数字。`)
  return parsed
}

function buildPayload() {
  const point = {
    x: parseNumber(state.pointX, '流域出口经度'),
    y: parseNumber(state.pointY, '流域出口纬度')
  }
  const bbox = {
    min_x: parseNumber(state.minX, '左上角经度'),
    min_y: parseNumber(state.minY, '右下角纬度'),
    max_x: parseNumber(state.maxX, '右下角经度'),
    max_y: parseNumber(state.maxY, '左上角纬度')
  }

  if (bbox.min_x >= bbox.max_x) throw new Error('矩形范围的左边界必须小于右边界。')
  if (bbox.min_y >= bbox.max_y) throw new Error('矩形范围的下边界必须小于上边界。')

  return {
    dem_path: state.demPath.trim() || DEFAULT_DEM_PATH,
    point,
    bbox,
    snap_threshold: Math.round(parseNumber(state.snapThreshold, '吸附阈值'))
  }
}

async function submit() {
  clearNotice()
  isSubmitting.value = true
  try {
    const response = await watershedBoundaryApi.generate(buildPayload())
    if (!response.data.success || !response.data.data) throw new Error(response.data.message || '流域边界生成失败')
    resultData.value = response.data.data
    successMessage.value = '流域边界已生成，右侧地图已刷新，可直接下载 GeoJSON。'
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSubmitting.value = false
  }
}

function downloadGeoJson() {
  if (!resultData.value) return
  const blob = new Blob([JSON.stringify(resultData.value.result, null, 2)], { type: 'application/geo+json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'watershed-boundary.geojson'
  anchor.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="boundary-page" :style="{ '--hero-background': `url(${heroBackground})` }">
    <SiteNav />

    <main class="boundary-workbench">
      <section class="boundary-hero">
        <div>
          <p class="boundary-hero__kicker">Point To Basin Boundary</p>
          <h1>生成流域边界</h1>
          <p>
            输入流域出口坐标和矩形范围，调用后端生成裁切后的流域边界 GeoJSON。默认使用
            <code>{{ DEFAULT_DEM_PATH }}</code>。当前仅支持本机绝对路径模式，不再复制 DEM 副本。
          </p>
        </div>
      </section>

      <section class="boundary-grid">
        <div class="boundary-form">
          <article class="panel-soft-card control-panel">
            <div class="control-panel__header">
              <div>
                <p class="panel-eyebrow">输入面板</p>
                <h2>生成参数</h2>
              </div>
              <div class="control-panel__chips">
                <span class="status-chip">本机 DEM 路径</span>
                <span class="status-chip">{{ resultData ? '结果已就绪' : '等待生成' }}</span>
              </div>
            </div>

            <section class="compact-section">
              <div class="section-head">
                <strong>DEM 设置</strong>
              </div>
              <label class="field">
                <span>DEM 路径</span>
                <input v-model="state.demPath" type="text" spellcheck="false" />
              </label>
              <div class="path-chip path-chip--helper">
                本地化部署推荐直接填写本机绝对路径，例如 <code>{{ DEFAULT_DEM_PATH }}</code>。生成时后端会直接读取这个路径，不再复制文件到 uploads 目录。
              </div>
            </section>

            <section class="compact-section">
              <div class="section-stack">
                <strong>流域出口</strong>
                <small>经纬度</small>
              </div>
              <div class="field-grid field-grid--two">
                <label class="field">
                  <span>流域出口经度</span>
                  <input v-model="state.pointX" type="text" inputmode="decimal" />
                </label>
                <label class="field">
                  <span>流域出口纬度</span>
                  <input v-model="state.pointY" type="text" inputmode="decimal" />
                </label>
              </div>
            </section>

            <section class="compact-section">
              <div class="section-stack">
                <strong>矩形范围</strong>
                <small>左上角到右下角</small>
              </div>
              <div class="field-grid">
                <label class="field">
                  <span>左上角经度</span>
                  <input v-model="state.minX" type="text" inputmode="decimal" />
                </label>
                <label class="field">
                  <span>左上角纬度</span>
                  <input v-model="state.maxY" type="text" inputmode="decimal" />
                </label>
                <label class="field">
                  <span>右下角经度</span>
                  <input v-model="state.maxX" type="text" inputmode="decimal" />
                </label>
                <label class="field">
                  <span>右下角纬度</span>
                  <input v-model="state.minY" type="text" inputmode="decimal" />
                </label>
              </div>
            </section>

            <section class="compact-section compact-section--bottom">
              <div class="section-stack">
                <strong>吸附阈值</strong>
                <small>snap_threshold</small>
              </div>
              <label class="field">
                <span>吸附阈值</span>
                <input v-model="state.snapThreshold" type="text" inputmode="numeric" />
              </label>
              <div class="button-stack">
                <button class="primary-action" type="button" :disabled="isSubmitting" @click="submit">
                  <el-icon aria-hidden="true"><Location /></el-icon>
                  <span>{{ isSubmitting ? '生成中...' : '生成流域边界' }}</span>
                </button>
                <button class="secondary-action" type="button" :disabled="!resultData" @click="downloadGeoJson">
                  <el-icon aria-hidden="true"><Download /></el-icon>
                  <span>下载 GeoJSON</span>
                </button>
              </div>
            </section>

            <div v-if="successMessage" class="notice success">{{ successMessage }}</div>
            <div v-if="errorMessage" class="notice error">{{ errorMessage }}</div>
          </article>
        </div>

        <div class="map-stage">
          <WatershedBoundaryPreviewMap :point="previewPoint" :bbox="previewBbox" :result="mapResult" />
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.boundary-page {
  min-height: 100vh;
  background:
    linear-gradient(180deg, rgba(2, 11, 29, 0.72) 0%, rgba(2, 11, 29, 0.6) 40%, rgba(2, 11, 29, 0.78) 100%),
    linear-gradient(115deg, rgba(7, 32, 52, 0.68) 0%, rgba(7, 32, 52, 0.34) 46%, rgba(7, 32, 52, 0.08) 100%),
    var(--hero-background) center / cover no-repeat,
    #03162d;
  color: #f4fbff;
}

.boundary-workbench {
  display: grid;
  gap: 22px;
  width: min(100% - 64px, 1760px);
  margin: 0 auto;
  padding: 18px 0 42px;
}

.boundary-hero {
  max-width: 980px;
}

.boundary-hero__kicker,
.panel-eyebrow {
  margin: 0 0 14px;
  color: #90fff4;
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.boundary-hero h1,
.form-card h2 {
  margin: 0;
}

.boundary-hero h1 {
  font-family: "STKaiti", "KaiTi", "FangSong", serif;
  font-size: clamp(3rem, 4.7vw, 5rem);
  line-height: 1.04;
  text-shadow: 0 0 18px rgba(106, 244, 240, 0.22);
}

.boundary-hero p:last-child,
.panel-copy {
  margin: 14px 0 0;
  color: rgba(230, 244, 250, 0.8);
  line-height: 1.78;
}

.boundary-grid {
  display: grid;
  grid-template-columns: minmax(360px, 520px) minmax(0, 1fr);
  gap: 24px;
  align-items: stretch;
}

.boundary-form {
  min-width: 0;
}

.panel-soft-card {
  border: 1px solid rgba(168, 247, 255, 0.16);
  border-radius: 8px;
  background: rgba(5, 22, 39, 0.62);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 24px 66px rgba(0, 0, 0, 0.22);
  backdrop-filter: blur(18px);
}

.path-chip {
  padding: 11px 12px;
  border: 1px solid rgba(168, 247, 255, 0.18);
  border-radius: 8px;
  background: rgba(2, 12, 25, 0.46);
  font-family: Consolas, monospace;
  font-size: 0.78rem;
  overflow-wrap: anywhere;
}

.path-chip--helper {
  color: rgba(230, 244, 250, 0.74);
  font-family: inherit;
  font-size: 0.82rem;
  line-height: 1.6;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.field-grid--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.field {
  display: grid;
  gap: 8px;
}

.field span,
.field small {
  color: rgba(234, 250, 255, 0.68);
}

.field span {
  font-size: 0.84rem;
  font-weight: 700;
}

.field small {
  margin-top: -4px;
  font-size: 0.74rem;
}

.field input {
  min-height: 44px;
  padding: 0 14px;
  border: 1px solid rgba(168, 247, 255, 0.16);
  border-radius: 8px;
  background: rgba(2, 12, 25, 0.52);
  color: #f4fbff;
  font: inherit;
}

.field input:focus {
  outline: none;
  border-color: rgba(130, 255, 240, 0.5);
  box-shadow: 0 0 0 3px rgba(130, 255, 240, 0.12);
}

.primary-action,
.secondary-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 44px;
  padding: 0 18px;
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  font: inherit;
  font-weight: 800;
}

.primary-action {
  background: linear-gradient(135deg, #a3fff2, #31c8ed);
  color: #04233f;
  box-shadow: 0 18px 44px rgba(49, 200, 237, 0.24);
}

.secondary-action {
  border: 1px solid rgba(168, 247, 255, 0.24);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(244, 252, 255, 0.86);
}

.primary-action:disabled,
.secondary-action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.notice {
  padding: 11px 12px;
  border-radius: 7px;
  line-height: 1.5;
}

.notice.success {
  border: 1px solid rgba(121, 236, 160, 0.34);
  background: rgba(30, 91, 57, 0.48);
}

.notice.error {
  border: 1px solid rgba(255, 128, 128, 0.34);
  background: rgba(93, 34, 34, 0.52);
}

.map-stage {
  min-width: 0;
  display: flex;
}

.control-panel {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 680px;
  padding: 18px;
}

.control-panel__header,
.section-head,
.control-panel__chips {
  display: flex;
  align-items: center;
}

.control-panel__header,
.section-head {
  justify-content: space-between;
  gap: 12px;
}

.control-panel__chips {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.status-chip {
  padding: 7px 10px;
  border: 1px solid rgba(168, 247, 255, 0.16);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(234, 250, 255, 0.72);
  font-size: 0.76rem;
  white-space: nowrap;
}

.compact-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 0;
  border-top: 1px solid rgba(168, 247, 255, 0.1);
}

.compact-section:first-of-type {
  border-top: 0;
  padding-top: 4px;
}

.section-head strong {
  font-size: 1rem;
}

.section-head small {
  color: rgba(234, 250, 255, 0.54);
  font-size: 0.76rem;
}

.section-stack {
  display: grid;
  gap: 4px;
}

.section-stack strong {
  font-size: 0.98rem;
}

.section-stack small {
  color: rgba(234, 250, 255, 0.54);
  font-size: 0.76rem;
}

.button-stack {
  display: grid;
  gap: 8px;
}

.compact-section--bottom {
  margin-top: auto;
}

@media (max-width: 1280px) {
  .boundary-grid {
    grid-template-columns: 1fr;
  }

  .control-panel {
    min-height: auto;
  }
}

@media (max-width: 860px) {
  .boundary-workbench {
    width: min(100% - 28px, 1760px);
  }

  .boundary-hero,
  .field-grid,
  .field-grid--two {
    grid-template-columns: 1fr;
  }

  .control-panel__header,
  .section-head {
    align-items: start;
    flex-direction: column;
  }

  .field--threshold {
    max-width: none;
  }
}
</style>
