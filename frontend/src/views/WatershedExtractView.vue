<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { DataLine, Location, Refresh, UploadFilled } from '@element-plus/icons-vue'

import SiteNav from '@/components/SiteNav.vue'
import WatershedPreviewMap from '@/components/WatershedPreviewMap.vue'
import { getApiErrorMessage } from '@/api/client'
import { watershedUploadsApi } from '@/api/uploads'
import { watershedApi } from '@/api/watershed'
import heroBackground from '@/assets/home-water-basin-bg.png'
import {
  collectBoundaryFiles,
  firstDemFile,
  isShapefileComponentSelection
} from '@/utils/watershedUpload'
import type {
  BreakPoint,
  GeoJsonFeatureCollection,
  UploadResult,
  WatershedOutputs,
  WatershedStep0Response,
  WatershedStep1Response,
  WatershedStep2Response,
  WatershedThresholdResponse
} from '@/types'

type StepId = 1 | 2 | 3 | 4
type StepStatus = 'idle' | 'running' | 'done' | 'error'
type OperationMode = 'merge' | 'delete'

interface WorkflowState {
  planName: string
  demPath: string
  shapefilePath: string
  randomFolderName: string
  areaThreshold: number | null
  breakPoints: BreakPoint[]
}

const DEFAULT_DEM_PATH = 'D:\\work\\data\\data\\dem\\dem.tif'

const steps: Array<{ id: StepId; title: string; endpoint: string; description: string }> = [
  { id: 1, title: '累计流阈值设置', endpoint: '/api/watershed/acc_threshold', description: '上传边界并计算默认面积阈值' },
  { id: 2, title: '初始化流域', endpoint: '/api/watershed/step0_streams', description: '生成初始边界和河网' },
  { id: 3, title: '生成流域', endpoint: '/api/watershed/step1', description: '生成子流域、河段和控制点' },
  { id: 4, title: '合并 / 删除', endpoint: '/api/watershed/step2', description: '调整子流域拓扑结果' }
]

const activeStep = ref<StepId>(1)
const statusByStep = ref<Record<StepId, StepStatus>>({ 1: 'idle', 2: 'idle', 3: 'idle', 4: 'idle' })
const errorMessage = ref('')
const successMessage = ref('')
const boundaryUpload = ref<UploadResult | null>(null)
const demUpload = ref<UploadResult | null>(null)
const boundaryPreview = ref<GeoJsonFeatureCollection | null>(null)
const planNameWarning = ref('')
const defaultAreaThreshold = ref<number | null>(null)
const step0AreaThresholdInput = ref('')
const step0Result = ref<WatershedStep0Response | null>(null)
const step1Result = ref<WatershedStep1Response | null>(null)
const step2Result = ref<WatershedStep2Response | null>(null)
const operationMode = ref<OperationMode>('merge')
const selectedWatershedIds = ref<string[]>([])
const manualWatershedIdsText = ref('')
const dropTarget = ref<'dem' | 'boundary' | null>(null)

const state = ref<WorkflowState>({
  planName: '',
  demPath: DEFAULT_DEM_PATH,
  shapefilePath: '',
  randomFolderName: '',
  areaThreshold: null,
  breakPoints: []
})

const activeOutputs = computed<WatershedOutputs | null>(() => step2Result.value?.outputs || step1Result.value?.outputs || null)
const step0BoundaryPreview = computed(() => step0Result.value?.buffered_boundary || null)
const step0StreamsPreview = computed(() => step0Result.value?.streams_ori || null)
const watershedIds = computed(() => {
  const features = activeOutputs.value?.subWatersheds?.features || []
  return features
    .map((feature, index) => {
      const properties = (feature.properties || {}) as Record<string, unknown>
      return String(properties.id || properties.name || properties.ID || `Watershed${index + 1}`)
    })
    .filter(Boolean)
})

const inheritedRows = computed(() => [
  ['dem_path', state.value.demPath || '未设置'],
  ['shapefile_path', state.value.shapefilePath || '等待上传边界'],
  ['random_folder_name', state.value.randomFolderName || '步骤一返回后固定'],
  ['area_threshold', state.value.areaThreshold == null ? '步骤一返回后固定' : `${state.value.areaThreshold} km²`],
  ['break_points', state.value.breakPoints.length ? `${state.value.breakPoints.length} 个控制点` : '可为空，后端自动选点']
])

function setStepStatus(step: StepId, status: StepStatus) {
  statusByStep.value[step] = status
}

function clearNotice() {
  errorMessage.value = ''
  successMessage.value = ''
}

function showSuccess(message: string) {
  errorMessage.value = ''
  successMessage.value = message
}

function showError(error: unknown) {
  successMessage.value = ''
  errorMessage.value = getApiErrorMessage(error)
}

function resolveStep0AreaThreshold() {
  const rawValue = String(step0AreaThresholdInput.value ?? '').trim()
  if (!rawValue) {
    throw new Error('请输入面积阈值，或沿用步骤一返回的默认阈值。')
  }

  const parsed = Number(rawValue)
  if (!Number.isFinite(parsed)) {
    throw new Error('面积阈值必须是有效数字。')
  }

  return parsed
}

async function validatePlanName() {
  const planName = state.value.planName.trim()
  if (!planName) {
    planNameWarning.value = ''
    return
  }

  try {
    const response = await watershedApi.validatePlanName({ plan_name: planName })
    planNameWarning.value = response.data.exists ? response.data.message || '检测到同名方案，继续可能复用旧结果，建议更换名称' : ''
  } catch (caught) {
    planNameWarning.value = ''
    console.warn('validatePlanName failed', caught)
  }
}

async function uploadDem(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await uploadDemFiles([file])
}

async function uploadDemFiles(files: File[]) {
  const file = firstDemFile(files)
  if (!file) {
    errorMessage.value = '请拖入或选择 .tif / .tiff 的 DEM 文件。'
    return
  }
  clearNotice()
  try {
    const response = await watershedUploadsApi.upload(file, 'dem')
    if (!response.data.success || !response.data.data) throw new Error(response.data.message || 'DEM 上传失败')
    demUpload.value = response.data.data
    state.value.demPath = response.data.data.path
    showSuccess('DEM 已上传，后续步骤会直接复用这个服务器路径。')
  } catch (caught) {
    showError(caught)
  }
}

async function uploadBoundary(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  await uploadBoundaryFiles(files)
}

async function uploadBoundaryFiles(files: File[]) {
  const boundaryFiles = collectBoundaryFiles(files)
  if (!boundaryFiles.length) {
    errorMessage.value = '请拖入或选择边界文件，支持 .shp 组件 / .geojson / .kml / .zip。'
    return
  }
  clearNotice()
  try {
    const response = isShapefileComponentSelection(boundaryFiles)
      ? await watershedUploadsApi.uploadMany(boundaryFiles, 'basin_boundary')
      : await watershedUploadsApi.upload(boundaryFiles[0], 'basin_boundary')
    if (!response.data.success || !response.data.data) throw new Error(response.data.message || '边界上传失败')
    boundaryUpload.value = response.data.data
    state.value.shapefilePath = response.data.data.path
    const previewResponse = await watershedApi.previewLayer({ path: response.data.data.path })
    boundaryPreview.value = previewResponse.data.layer
    showSuccess('流域边界已上传，地图会先显示边界预览。')
  } catch (caught) {
    showError(caught)
  }
}

function resetDemPath() {
  demUpload.value = null
  state.value.demPath = DEFAULT_DEM_PATH
}

function startDrop(target: 'dem' | 'boundary', event: DragEvent) {
  event.preventDefault()
  dropTarget.value = target
}

function endDrop() {
  dropTarget.value = null
}

async function handleDrop(target: 'dem' | 'boundary', event: DragEvent) {
  event.preventDefault()
  dropTarget.value = null
  const files = Array.from(event.dataTransfer?.files || [])
  if (!files.length) return
  if (target === 'dem') {
    await uploadDemFiles(files)
    return
  }
  await uploadBoundaryFiles(files)
}

function dropZoneClass(target: 'dem' | 'boundary') {
  return {
    'drop-zone': true,
    'drop-zone--active': dropTarget.value === target
  }
}

async function runThreshold() {
  clearNotice()
  if (!state.value.planName.trim()) {
    errorMessage.value = '请先填写方案名称。'
    return
  }
  setStepStatus(1, 'running')
  try {
    const response = await watershedApi.calculateThreshold({
      dem_path: state.value.demPath,
      shapefile_path: state.value.shapefilePath || undefined,
      plan_name: state.value.planName
    })
    const data = response.data as WatershedThresholdResponse
    if (!data.success) throw new Error(data.message || '计算默认阈值失败')
    state.value.areaThreshold = data.area_threshold
    defaultAreaThreshold.value = data.area_threshold
    step0AreaThresholdInput.value = String(data.area_threshold)
    state.value.randomFolderName = data.random_folder_name
    setStepStatus(1, 'done')
    activeStep.value = 2
    showSuccess(`默认阈值计算完成，功能二默认面积阈值为 ${data.area_threshold} km²。`)
  } catch (caught) {
    setStepStatus(1, 'error')
    showError(caught)
  }
}

async function runStep0() {
  clearNotice()
  if (state.value.areaThreshold == null || !state.value.randomFolderName) {
    errorMessage.value = '请先完成步骤一，获取 area_threshold 和 random_folder_name。'
    return
  }
  setStepStatus(2, 'running')
  try {
    const areaThreshold = resolveStep0AreaThreshold()
    state.value.areaThreshold = areaThreshold
    const response = await watershedApi.initializeStreams({
      dem_path: state.value.demPath,
      area_threshold: areaThreshold,
      shapefile_path: state.value.shapefilePath || undefined,
      random_folder_name: state.value.randomFolderName,
      plan_name: state.value.planName
    })
    const data = response.data as WatershedStep0Response
    if (!data.success) throw new Error(data.message || '初始化失败')
    step0Result.value = data
    setStepStatus(2, 'done')
    activeStep.value = 3
    showSuccess('初始流域边界和河网已生成，地图已切到真实结果预览。')
  } catch (caught) {
    setStepStatus(2, 'error')
    showError(caught)
  }
}

async function runStep1() {
  clearNotice()
  if (state.value.areaThreshold == null || !state.value.randomFolderName) {
    errorMessage.value = '请先完成步骤一，获取 area_threshold 和 random_folder_name。'
    return
  }
  setStepStatus(3, 'running')
  try {
    const response = await watershedApi.generateWatersheds({
      dem_path: state.value.demPath,
      area_threshold: state.value.areaThreshold,
      shapefile_path: state.value.shapefilePath || undefined,
      random_folder_name: state.value.randomFolderName,
      break_points: state.value.breakPoints,
      plan_name: state.value.planName
    })
    const data = response.data as WatershedStep1Response
    if (!data.success) throw new Error('流域生成失败')
    step1Result.value = data
    clearStep2Selection()
    setStepStatus(3, 'done')
    activeStep.value = 4
    showSuccess('子流域结果已生成，可以继续合并或删除。')
  } catch (caught) {
    setStepStatus(3, 'error')
    showError(caught)
  }
}

async function runStep2() {
  clearNotice()
  const ids = normalizedSelectedIds()
  if (!state.value.randomFolderName) {
    errorMessage.value = '缺少 random_folder_name，请先完成步骤一。'
    return
  }
  if (!ids.length) {
    errorMessage.value = '请至少选择或输入一个子流域 ID。'
    return
  }
  setStepStatus(4, 'running')
  try {
    const response = await watershedApi.mergeOrDelete({
      operation: operationMode.value,
      watershed_ids: ids,
      random_folder: state.value.randomFolderName,
      break_points: state.value.breakPoints,
      plan_name: state.value.planName
    })
    const data = response.data as WatershedStep2Response
    if (!data.success) throw new Error('合并 / 删除失败')
    step2Result.value = data
    clearStep2Selection()
    setStepStatus(4, 'done')
    showSuccess(operationMode.value === 'merge' ? '流域合并完成。' : '流域删除完成。')
  } catch (caught) {
    setStepStatus(4, 'error')
    showError(caught)
  }
}

function addBreakPoint() {
  const nextId = state.value.breakPoints.length + 1
  state.value.breakPoints.push([105.1, 27.0, nextId])
}

function addBreakPointFromMap([lon, lat]: [number, number]) {
  state.value.breakPoints.push([lon, lat, state.value.breakPoints.length + 1])
}

function removeBreakPoint(index: number) {
  state.value.breakPoints.splice(index, 1)
}

function updateBreakPoint(index: number, axis: 0 | 1 | 2, value: string) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return
  const point = state.value.breakPoints[index]
  point[axis] = axis === 2 ? Math.round(numeric) : Number(numeric.toFixed(6))
}

function clearStep2Selection() {
  selectedWatershedIds.value = []
  manualWatershedIdsText.value = ''
}

function syncStep2SelectionWithAvailableIds() {
  const validIds = new Set(watershedIds.value)
  if (!validIds.size) {
    clearStep2Selection()
    return
  }

  selectedWatershedIds.value = selectedWatershedIds.value.filter((id) => validIds.has(id))

  const manualIds = manualWatershedIdsText.value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((id) => validIds.has(id))

  manualWatershedIdsText.value = manualIds.join(', ')
}

function toggleWatershedId(id: string) {
  const set = new Set(normalizedSelectedIds())
  if (set.has(id)) set.delete(id)
  else set.add(id)
  selectedWatershedIds.value = Array.from(set)
  manualWatershedIdsText.value = selectedWatershedIds.value.join(', ')
}

function normalizedSelectedIds() {
  const manual = manualWatershedIdsText.value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  return Array.from(new Set([...selectedWatershedIds.value, ...manual]))
}

watch(watershedIds, () => {
  syncStep2SelectionWithAvailableIds()
})
</script>

<template>
  <div class="watershed-page" :style="{ '--hero-background': `url(${heroBackground})` }">
    <SiteNav />

    <main class="watershed-workbench">
      <section class="watershed-hero">
        <p class="watershed-hero__kicker">DEM Hydrology Workbench</p>
        <h1>流域提取</h1>
        <p>
          以 DEM 和流域边界为起点，完成阈值计算、初始河网、子流域生成以及后续合并删除。
          第一步确认的关键参数会自动贯穿整条流程，地图预览会随着步骤结果实时更新。
        </p>
      </section>

      <section class="workflow-grid">
        <aside class="step-rail" aria-label="流域提取步骤">
          <button
            v-for="step in steps"
            :key="step.id"
            class="step-item"
            :class="{ active: activeStep === step.id, done: statusByStep[step.id] === 'done' }"
            type="button"
            @click="activeStep = step.id"
          >
            <span class="step-item__badge">{{ step.id }}</span>
            <span>
              <strong>{{ step.title }}</strong>
              <small>{{ step.endpoint }}</small>
              <em>{{ step.description }}</em>
            </span>
          </button>

          <div class="state-ledger">
            <h2>继承参数</h2>
            <dl>
              <template v-for="[key, value] in inheritedRows" :key="key">
                <dt>{{ key }}</dt>
                <dd>{{ value }}</dd>
              </template>
            </dl>
          </div>
        </aside>

        <WatershedPreviewMap
          class="map-stage"
          :step1-outputs="step1Result?.outputs || null"
          :step2-outputs="step2Result?.outputs || null"
          :boundary-preview="boundaryPreview"
          :step0-boundary="step0BoundaryPreview"
          :step0-streams="step0StreamsPreview"
          :manual-break-points="state.breakPoints"
          :interactive-break-point-mode="activeStep === 3"
          @add-break-point="addBreakPointFromMap"
        />

        <aside class="operation-panel">
          <div class="panel-stack">
            <div v-if="successMessage" class="notice success">{{ successMessage }}</div>
            <div v-if="errorMessage" class="notice error">{{ errorMessage }}</div>

            <section v-show="activeStep === 1" class="panel-section panel-card">
              <div class="panel-header">
                <p class="panel-eyebrow">POST /api/watershed/acc_threshold</p>
                <h2>累计流阈值设置</h2>
                <p class="panel-copy">先确定方案名称，再上传 DEM 与边界数据。关键路径会在后续步骤中自动继承。</p>
              </div>

              <label class="field field--compact">
                <span>方案名称</span>
                <input v-model="state.planName" type="text" placeholder="请输入方案名称，也作为后端计划目录名" @blur="validatePlanName" />
              </label>
              <p v-if="planNameWarning" class="field-warning">{{ planNameWarning }}</p>

              <div
                :class="['upload-slab', dropZoneClass('dem')]"
                @dragenter="startDrop('dem', $event)"
                @dragover="startDrop('dem', $event)"
                @dragleave="endDrop"
                @drop="handleDrop('dem', $event)"
              >
                <label class="upload-slab__action upload-button">
                  <input type="file" accept=".tif,.tiff" @change="uploadDem" />
                  <el-icon><UploadFilled /></el-icon>
                  <span>{{ demUpload ? demUpload.original_name : '拖入或上传 DEM，可选' }}</span>
                </label>
                <p class="upload-slab__meta">如果不上传，默认使用系统 DEM 路径。</p>
                <label class="field field--compact">
                  <span>DEM 路径 dem_path</span>
                  <div class="field-row field-row--stacked">
                    <input v-model="state.demPath" type="text" />
                    <button class="icon-button icon-button--inline" type="button" title="恢复默认 DEM" @click="resetDemPath">
                      <el-icon><Refresh /></el-icon>
                    </button>
                  </div>
                </label>
              </div>

              <div
                :class="['upload-slab', dropZoneClass('boundary')]"
                @dragenter="startDrop('boundary', $event)"
                @dragover="startDrop('boundary', $event)"
                @dragleave="endDrop"
                @drop="handleDrop('boundary', $event)"
              >
                <label class="upload-slab__action upload-button">
                  <input
                    type="file"
                    accept=".shp,.shx,.dbf,.prj,.cpg,.geojson,.json,.kml,.zip"
                    multiple
                    @change="uploadBoundary"
                  />
                  <el-icon><UploadFilled /></el-icon>
                  <span>{{ boundaryUpload ? boundaryUpload.original_name : '拖入或上传边界' }}</span>
                </label>
                <p class="upload-slab__meta">支持 .shp 组件、.geojson、.kml、.zip，支持从文件夹直接拖动文件。</p>
                <label class="field field--compact">
                  <span>流域边界 shapefile_path</span>
                  <input v-model="state.shapefilePath" type="text" placeholder="上传后自动写入服务器路径" />
                </label>
              </div>

              <p class="drop-caption">地图会先预览上传边界；真正的河网和子流域结果会在后面步骤自动接上。</p>

              <button class="primary-action primary-action--full" type="button" :disabled="statusByStep[1] === 'running'" @click="runThreshold">
                <el-icon><DataLine /></el-icon>
                <span>{{ statusByStep[1] === 'running' ? '计算中...' : '计算默认阈值' }}</span>
              </button>
            </section>

            <section v-show="activeStep === 2" class="panel-section panel-card">
              <div class="panel-header">
                <p class="panel-eyebrow">POST /api/watershed/step0_streams</p>
                <h2>初始化流域</h2>
                <p class="panel-copy">沿用步骤一的 DEM、边界、方案名称和默认阈值。你也可以在这里改成自定义阈值；提交后，后续步骤会继续沿用这次最终采用的值。</p>
              </div>

              <div class="summary-stack">
                <div class="summary-item">
                  <span>默认阈值</span>
                  <strong>{{ defaultAreaThreshold == null ? '等待步骤一' : `${defaultAreaThreshold} km²` }}</strong>
                </div>
                <div class="summary-item">
                  <span>工作目录</span>
                  <strong>{{ state.randomFolderName || '等待步骤一' }}</strong>
                </div>
              </div>

              <label class="field field--compact">
                <span>面积阈值 area_threshold（km²）</span>
                <input
                  v-model="step0AreaThresholdInput"
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="默认使用步骤一返回的阈值"
                />
              </label>

              <button class="primary-action primary-action--full" type="button" :disabled="statusByStep[2] === 'running'" @click="runStep0">
                <el-icon><Location /></el-icon>
                <span>{{ statusByStep[2] === 'running' ? '初始化中...' : '生成初始边界与河网' }}</span>
              </button>

              <div v-if="step0Result" class="output-paths panel-soft-card">
                <p>boundary: {{ step0Result.buffered_boundary_geojson }}</p>
                <p>streams: {{ step0Result.streams_ori_geojson }}</p>
              </div>
            </section>

            <section v-show="activeStep === 3" class="panel-section panel-card">
              <div class="panel-header">
                <p class="panel-eyebrow">POST /api/watershed/step1</p>
                <h2>生成流域</h2>
                <p class="panel-copy">控制点可以留空；为空时后端会在边界内自动选点。也可以直接点击地图添加。</p>
              </div>

              <div class="panel-soft-card">
                <div class="break-table">
                  <div class="break-table__head">
                    <span>ID</span>
                    <span>Lon</span>
                    <span>Lat</span>
                    <span></span>
                  </div>
                  <div v-for="(point, index) in state.breakPoints" :key="index" class="break-table__row">
                    <input :value="point[2]" type="number" @input="updateBreakPoint(index, 2, ($event.target as HTMLInputElement).value)" />
                    <input :value="point[0]" type="number" step="0.000001" @input="updateBreakPoint(index, 0, ($event.target as HTMLInputElement).value)" />
                    <input :value="point[1]" type="number" step="0.000001" @input="updateBreakPoint(index, 1, ($event.target as HTMLInputElement).value)" />
                    <button type="button" @click="removeBreakPoint(index)">删除</button>
                  </div>
                </div>
              </div>

              <div class="action-stack">
                <button class="secondary-action secondary-action--full" type="button" @click="addBreakPoint">添加控制点</button>
                <button class="primary-action primary-action--full" type="button" :disabled="statusByStep[3] === 'running'" @click="runStep1">
                  <el-icon><Location /></el-icon>
                  <span>{{ statusByStep[3] === 'running' ? '生成中...' : '生成子流域' }}</span>
                </button>
              </div>
            </section>

            <section v-show="activeStep === 4" class="panel-section panel-card">
              <div class="panel-header">
                <p class="panel-eyebrow">POST /api/watershed/step2</p>
                <h2>流域合并 / 删除</h2>
                <p class="panel-copy">先选择操作方式，再勾选或输入目标子流域 ID，提交后会直接刷新本轮结果。</p>
              </div>

              <div class="mode-switch panel-soft-card">
                <button type="button" :class="{ active: operationMode === 'merge' }" @click="operationMode = 'merge'">合并</button>
                <button type="button" :class="{ active: operationMode === 'delete' }" @click="operationMode = 'delete'">删除</button>
              </div>

              <div class="watershed-picker panel-soft-card">
                <button
                  v-for="id in watershedIds"
                  :key="id"
                  type="button"
                  :class="{ selected: normalizedSelectedIds().includes(id) }"
                  @click="toggleWatershedId(id)"
                >
                  {{ id }}
                </button>
                <p v-if="!watershedIds.length">生成子流域后，这里会显示可选 ID；你也可以直接在下方手动输入。</p>
              </div>

              <label class="field field--compact">
                <span>目标 watershed_ids，逗号分隔</span>
                <input v-model="manualWatershedIdsText" type="text" placeholder="Watershed1.1, Watershed1.2" />
              </label>

              <button class="primary-action primary-action--full" type="button" :disabled="statusByStep[4] === 'running'" @click="runStep2">
                <el-icon><DataLine /></el-icon>
                <span>{{ statusByStep[4] === 'running' ? '处理中...' : '提交合并 / 删除' }}</span>
              </button>
            </section>
          </div>
        </aside>
      </section>
    </main>
  </div>
</template>

<style scoped>
.watershed-page {
  min-height: 100vh;
  overflow: hidden;
  background:
    linear-gradient(180deg, rgba(2, 11, 29, 0.72) 0%, rgba(2, 11, 29, 0.6) 40%, rgba(2, 11, 29, 0.78) 100%),
    linear-gradient(115deg, rgba(7, 32, 52, 0.68) 0%, rgba(7, 32, 52, 0.34) 46%, rgba(7, 32, 52, 0.08) 100%),
    var(--hero-background) center / cover no-repeat,
    #03162d;
  color: #eefbff;
}

.watershed-workbench {
  position: relative;
  z-index: 1;
  width: min(100% - 52px, 1760px);
  margin: 0 auto;
  padding: 8px 0 32px;
}

.watershed-hero {
  display: grid;
  grid-template-columns: minmax(0, 0.75fr) minmax(320px, 0.5fr);
  gap: 28px;
  align-items: end;
  margin: 10px 0 18px;
}

.watershed-hero__kicker,
.panel-eyebrow {
  margin: 0 0 10px;
  color: #82fff0;
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.watershed-hero h1 {
  margin: 0;
  font-size: clamp(2.8rem, 5.4vw, 6.8rem);
  line-height: 0.88;
}

.watershed-hero p:last-child {
  margin: 0;
  color: rgba(234, 250, 255, 0.78);
  line-height: 1.85;
}

.workflow-grid {
  display: grid;
  grid-template-columns: 284px minmax(420px, 1fr) 430px;
  gap: 16px;
  align-items: stretch;
  min-height: 680px;
}

.step-rail,
.operation-panel,
.state-ledger {
  border: 1px solid rgba(168, 247, 255, 0.18);
  border-radius: 8px;
  background: rgba(4, 26, 45, 0.72);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.32);
  backdrop-filter: blur(22px);
}

.step-rail {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
}

.step-item {
  display: grid;
  grid-template-columns: 34px 1fr;
  gap: 10px;
  width: 100%;
  padding: 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.step-item.active {
  border-color: rgba(130, 255, 240, 0.5);
  background: rgba(130, 255, 240, 0.1);
}

.step-item.done .step-item__badge {
  background: rgba(92, 236, 154, 0.18);
  color: #8ff0ae;
}

.step-item__badge {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid rgba(168, 247, 255, 0.3);
  border-radius: 50%;
  color: #82fff0;
  font-weight: 900;
}

.step-item strong,
.step-item small,
.step-item em {
  display: block;
}

.step-item strong {
  font-size: 0.95rem;
}

.step-item small,
.step-item em,
.panel-copy,
.output-paths,
.watershed-picker p {
  color: rgba(234, 250, 255, 0.62);
}

.step-item small {
  margin-top: 3px;
  font-family: Consolas, monospace;
  font-size: 0.74rem;
}

.step-item em {
  margin-top: 5px;
  font-size: 0.78rem;
  font-style: normal;
}

.state-ledger {
  margin-top: auto;
  padding: 14px;
}

.state-ledger h2 {
  margin: 0 0 12px;
  font-size: 0.96rem;
}

.state-ledger dl {
  display: grid;
  gap: 10px;
  margin: 0;
}

.state-ledger dt {
  color: #82fff0;
  font-family: Consolas, monospace;
  font-size: 0.72rem;
}

.state-ledger dd {
  min-width: 0;
  margin: 3px 0 0;
  overflow-wrap: anywhere;
  color: rgba(244, 252, 255, 0.82);
  font-size: 0.8rem;
}

.map-stage {
  min-height: 680px;
}

.operation-panel {
  padding: 14px;
  overflow: auto;
}

.panel-stack {
  display: grid;
  gap: 12px;
}

.panel-section {
  display: grid;
  gap: 12px;
}

.panel-section h2 {
  margin: 0;
  font-size: 1.28rem;
}

.panel-card {
  padding: 16px;
  border: 1px solid rgba(168, 247, 255, 0.14);
  border-radius: 10px;
  background:
    linear-gradient(180deg, rgba(7, 27, 45, 0.92), rgba(4, 18, 33, 0.9)),
    rgba(4, 26, 45, 0.74);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.panel-header {
  display: grid;
  gap: 8px;
}

.panel-header .panel-eyebrow {
  margin-bottom: 0;
}

.panel-copy {
  margin: 0;
  line-height: 1.65;
}

.panel-soft-card {
  padding: 12px;
  border: 1px solid rgba(168, 247, 255, 0.12);
  border-radius: 9px;
  background: rgba(2, 12, 25, 0.42);
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  color: rgba(234, 250, 255, 0.72);
  font-size: 0.78rem;
  font-weight: 800;
}

.field--compact {
  gap: 6px;
}

.field-warning {
  margin: -2px 0 0;
  padding: 8px 10px;
  border: 1px solid rgba(255, 196, 107, 0.28);
  border-radius: 7px;
  background: rgba(112, 76, 25, 0.24);
  color: #ffdca4;
  font-size: 0.78rem;
  line-height: 1.55;
}

.field input,
.break-table input {
  width: 100%;
  min-width: 0;
  padding: 10px 11px;
  border: 1px solid rgba(168, 247, 255, 0.22);
  border-radius: 7px;
  outline: none;
  background: rgba(2, 12, 25, 0.58);
  color: #f4fcff;
}

.field input:focus,
.break-table input:focus {
  border-color: #82fff0;
  box-shadow: 0 0 0 3px rgba(130, 255, 240, 0.12);
}

.field-row {
  display: flex;
  gap: 8px;
}

.field-row--stacked {
  align-items: stretch;
}

.icon-button,
.primary-action,
.secondary-action,
.upload-button,
.mode-switch button,
.watershed-picker button,
.break-table button {
  border: 0;
  border-radius: 7px;
  cursor: pointer;
  font-weight: 800;
}

.icon-button {
  display: grid;
  flex: 0 0 42px;
  place-items: center;
  background: rgba(130, 255, 240, 0.12);
  color: #82fff0;
}

.icon-button--inline {
  align-self: stretch;
}

.upload-button {
  display: inline-flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 48px;
  padding: 0 12px;
  border: 1px dashed rgba(168, 247, 255, 0.32);
  background: rgba(130, 255, 240, 0.08);
  color: rgba(244, 252, 255, 0.9);
}

.upload-slab {
  display: grid;
  gap: 9px;
  padding: 12px;
  border: 1px solid rgba(168, 247, 255, 0.16);
  border-radius: 10px;
  background: rgba(6, 26, 43, 0.56);
}

.upload-slab__action {
  min-height: 58px;
}

.upload-slab__meta {
  margin: 0;
  color: rgba(234, 250, 255, 0.58);
  font-size: 0.74rem;
  line-height: 1.55;
}

.drop-zone {
  border-radius: 8px;
}

.drop-zone--active {
  background: rgba(130, 255, 240, 0.09);
  box-shadow: 0 0 0 2px rgba(130, 255, 240, 0.22);
}

.drop-caption {
  margin: -2px 0 0;
  color: rgba(234, 250, 255, 0.68);
  font-size: 0.78rem;
  line-height: 1.65;
}

.upload-button input {
  display: none;
}

.primary-action,
.secondary-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 48px;
  padding: 0 16px;
}

.primary-action--full,
.secondary-action--full {
  width: 100%;
}

.primary-action {
  background: linear-gradient(135deg, #a3fff2, #31c8ed);
  color: #04233f;
  box-shadow: 0 18px 44px rgba(49, 200, 237, 0.24);
}

.primary-action:disabled {
  cursor: wait;
  opacity: 0.62;
}

.secondary-action {
  border: 1px solid rgba(168, 247, 255, 0.24);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(244, 252, 255, 0.86);
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

.summary-stack {
  display: grid;
  gap: 10px;
}

.summary-item {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid rgba(168, 247, 255, 0.12);
  border-radius: 9px;
  background: rgba(2, 12, 25, 0.42);
}

.summary-item span {
  color: rgba(234, 250, 255, 0.58);
}

.summary-item strong {
  overflow-wrap: anywhere;
}

.output-paths {
  display: grid;
  gap: 8px;
  font-family: Consolas, monospace;
  font-size: 0.76rem;
}

.output-paths p {
  margin: 0;
  overflow-wrap: anywhere;
}

.break-table {
  display: grid;
  gap: 7px;
}

.break-table__head,
.break-table__row {
  display: grid;
  grid-template-columns: 58px 1fr 1fr 56px;
  gap: 7px;
  align-items: center;
}

.break-table__head {
  color: rgba(234, 250, 255, 0.56);
  font-size: 0.75rem;
  font-weight: 800;
}

.break-table button {
  min-height: 38px;
  background: rgba(255, 122, 122, 0.14);
  color: #ffc4c4;
}

.action-stack {
  display: grid;
  gap: 10px;
}

.mode-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 5px;
}

.mode-switch button {
  min-height: 40px;
  background: transparent;
  color: rgba(244, 252, 255, 0.68);
}

.mode-switch button.active {
  background: rgba(130, 255, 240, 0.16);
  color: #82fff0;
}

.watershed-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-content: flex-start;
}

.watershed-picker button {
  min-height: 34px;
  padding: 0 10px;
  background: rgba(255, 255, 255, 0.07);
  color: rgba(244, 252, 255, 0.86);
}

.watershed-picker button.selected {
  background: rgba(255, 204, 102, 0.18);
  color: #ffd98a;
}

@media (max-width: 1280px) {
  .workflow-grid {
    grid-template-columns: 250px minmax(0, 1fr);
  }

  .operation-panel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 860px) {
  .watershed-workbench {
    width: min(100% - 28px, 1760px);
  }

  .watershed-hero,
  .workflow-grid {
    grid-template-columns: 1fr;
  }

  .map-stage {
    min-height: 520px;
  }

  .field-row {
    flex-direction: column;
  }
}
</style>
