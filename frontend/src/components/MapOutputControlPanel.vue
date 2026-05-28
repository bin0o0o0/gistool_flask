<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, MagicStick, UploadFilled, View } from '@element-plus/icons-vue'

import { collectLegendNameOverrides } from '@/utils/legendNameOverrides'
import { useWorkspaceStore } from '@/stores/workspace'
import type {
  LegendNameOverrideForm,
  LegendNameSourceType,
  LayoutBoxForm,
  StationLayerForm,
  StationPointForm,
  StationShape,
  UploadKind
} from '@/types'

const emit = defineEmits<{
  (event: 'preview-layout'): void
}>()

const store = useWorkspaceStore()
type WorkspaceUploadKind = Exclude<UploadKind, 'station_excel' | 'dem'>

const fontOptions = ['思源黑体', '微软雅黑', '苹方', '等线']
const paperPresets = [
  { label: 'A4 竖版', width: 1240, height: 1754 },
  { label: 'A4 横版', width: 1754, height: 1240 },
  { label: 'A3 竖版', width: 1754, height: 2480 },
  { label: 'A3 横版', width: 2480, height: 1754 }
]
const dpiPresets = [150, 300, 600]
const layoutFields: Array<{ key: keyof LayoutBoxForm; label: string }> = [
  { key: 'x', label: 'X' },
  { key: 'y', label: 'Y' },
  { key: 'width', label: '宽' },
  { key: 'height', label: '高' }
]
const layoutElementKeys = ['legend', 'scale_bar', 'north_arrow'] as const
const exportFormats = ref({
  png: true,
  pdf: true,
  geotiff: false
})

const legendRows = computed(() => collectLegendNameOverrides(store.form))
const primaryLegendRow = computed(() => legendRows.value[0] || null)
const stationLayers = computed(() => store.form.inputs.station_layers)
const firstStationLayer = computed(() => store.form.inputs.station_layers[0])
const templateName = computed(() => store.uploads.template_project.result?.original_name || '')

function uploadInputId(kind: WorkspaceUploadKind) {
  return `map-output-upload-${kind}`
}

function stationInputId(layerId: string) {
  return `map-output-station-${layerId}`
}

function openInput(id: string) {
  document.getElementById(id)?.click()
}

async function handleDatasetSelection(kind: WorkspaceUploadKind, event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  await store.uploadDataFiles(kind, files)
  const error = store.uploads[kind].error || store.error
  if (error) {
    ElMessage.error(error)
    return
  }
  ElMessage.success('数据已更新')
  if (kind !== 'template_project') store.markStepConfigured('style')
}

async function handleStationSelection(layer: StationLayerForm, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await store.uploadStationExcel(layer.id, file)
  if (store.error) {
    ElMessage.error(store.error)
    return
  }
  ElMessage.success('站点 Excel 已上传')
  store.markStepConfigured('stations')
}

function setPaperPreset(width: number, height: number) {
  store.form.output.width_px = width
  store.form.output.height_px = height
  store.markStepConfigured('output')
}

function setDpiPreset(dpi: number) {
  store.form.output.dpi = dpi
  store.markStepConfigured('output')
}

function activePaperLabel(label: string) {
  return paperPresets.some(
    (preset) =>
      preset.label === label &&
      preset.width === store.form.output.width_px &&
      preset.height === store.form.output.height_px
  )
}

function stationLabel(index: number) {
  return index === 0 ? '水文站点' : '雨量站点'
}

function shapeLabel(shape: StationShape) {
  const labels: Record<StationShape, string> = {
    circle: '圆形',
    triangle: '三角形',
    square: '正方形',
    diamond: '菱形',
    rectangle: '矩形'
  }
  return labels[shape] || shape
}

function positionLabel(position: string) {
  const labels: Record<string, string> = {
    top_left: '左上',
    top: '上方',
    top_right: '右上',
    right: '右侧',
    bottom_right: '右下',
    bottom: '下方',
    bottom_left: '左下',
    left: '左侧'
  }
  return labels[position] || position
}

function colorLabel(key: string, value: string) {
  const labels: Record<string, string> = {
    green: '绿色',
    red: '红色',
    blue: '蓝色',
    black: '黑色'
  }
  return `${labels[key] || key} ${value}`
}

function activeLegendPosition() {
  const legend = store.form.layout.elements.legend
  if (legend.x > 180) return 'right'
  if (legend.x > 80) return 'center'
  return 'left'
}

function setLegendPosition(position: 'left' | 'center' | 'right') {
  if (position === 'left') store.form.layout.elements.legend.x = 12.19
  if (position === 'center') store.form.layout.elements.legend.x = 110
  if (position === 'right') store.form.layout.elements.legend.x = 196
  store.markStepConfigured('output')
}

function updateLegendName(row: LegendNameOverrideForm | null | undefined, value: string | undefined) {
  if (!row) return
  const normalized = (value || '').trim()
  const overrides = store.form.layout.legend_style.name_overrides
  const index = overrides.findIndex((item) => item.source_key === row.source_key)
  if (!normalized || normalized === row.default_name) {
    if (index >= 0) overrides.splice(index, 1)
  } else {
    const next: LegendNameOverrideForm = {
      source_type: row.source_type as LegendNameSourceType,
      source_key: row.source_key,
      default_name: row.default_name,
      legend_name: normalized
    }
    if (index >= 0) overrides.splice(index, 1, next)
    else overrides.push(next)
  }
  store.markStepConfigured('output')
}

function markOutput() {
  store.markStepConfigured('output')
}

function applyLayerSettings(layer: StationLayerForm) {
  store.applyLayerStyleToStationPoints(layer.id)
  store.markStepConfigured('stations')
}

function syncLayerColor(layer: StationLayerForm) {
  store.syncPresetColor(layer)
  store.markStepConfigured('stations')
}

function syncPointColor(point: StationPointForm) {
  store.syncPointPresetColor(point)
  store.markStepConfigured('stations')
}

function onStepBack(step: 'data' | 'style' | 'stations' | 'output') {
  store.setActiveStep(step)
}

</script>

<template>
  <div class="control-root">
    <section v-if="store.activeStep === 'data'" class="step-panel">
      <div class="section-title">
        <el-icon><UploadFilled /></el-icon>
        <span>模板与数据</span>
      </div>

      <div class="step-body step-body--scroll">
        <div class="upload-card">
          <div>
            <label class="field-label">模板文件（APRX）</label>
            <p>上传 ArcGIS Pro 专题图模板工程。</p>
          </div>
          <div class="chip-row chip-row--single">
            <span class="data-chip" :class="{ 'data-chip--filled': !!templateName }">
              {{ templateName || '未上传模板' }}
            </span>
            <button class="mini-action" type="button" @click="openInput(uploadInputId('template_project'))">更换</button>
          </div>
          <input
            :id="uploadInputId('template_project')"
            class="native-file-input"
            type="file"
            accept=".aprx"
            @change="handleDatasetSelection('template_project', $event)"
          />
        </div>

        <div class="upload-card">
          <div>
            <label class="field-label">流域边界</label>
            <p>支持 GeoJSON、KML、zip 或 Shapefile 组件。</p>
          </div>
          <button class="full-action" type="button" @click="openInput(uploadInputId('basin_boundary'))">添加流域边界</button>
          <input
            :id="uploadInputId('basin_boundary')"
            class="native-file-input"
            type="file"
            accept=".geojson,.json,.kml,.zip,.shp,.shx,.dbf,.prj,.cpg,.sbn,.sbx,.qix,.xml"
            multiple
            @change="handleDatasetSelection('basin_boundary', $event)"
          />
          <div v-if="store.form.inputs.basin_boundaries.length" class="dataset-list">
            <div v-for="layer in store.form.inputs.basin_boundaries" :key="layer.id" class="dataset-row">
              <span>{{ layer.name }}</span>
              <button type="button" @click="store.removeBasinLayer(layer.id)">移除</button>
            </div>
          </div>
        </div>

        <div class="upload-card">
          <div>
            <label class="field-label">河流网络</label>
            <p>导入主干河流或河网线图层。</p>
          </div>
          <button class="full-action" type="button" @click="openInput(uploadInputId('river_network'))">添加河流网络</button>
          <input
            :id="uploadInputId('river_network')"
            class="native-file-input"
            type="file"
            accept=".geojson,.json,.kml,.zip,.shp,.shx,.dbf,.prj,.cpg,.sbn,.sbx,.qix,.xml"
            multiple
            @change="handleDatasetSelection('river_network', $event)"
          />
          <div v-if="store.form.inputs.river_networks.length" class="dataset-list">
            <div v-for="layer in store.form.inputs.river_networks" :key="layer.id" class="dataset-row">
              <span>{{ layer.name }}</span>
              <button type="button" @click="store.removeRiverLayer(layer.id)">移除</button>
            </div>
          </div>
        </div>
      </div>

      <div class="action-row action-row--bottom">
        <button class="primary-cta primary-cta--wide" type="button" @click="onStepBack('style')">下一步：图层配置</button>
      </div>
    </section>

    <section v-else-if="store.activeStep === 'style'" class="step-panel">
      <div class="section-title">
        <el-icon><MagicStick /></el-icon>
        <span>图层样式</span>
      </div>

      <div class="step-body step-body--scroll">
        <div v-for="layer in store.form.inputs.basin_boundaries" :key="layer.id" class="style-block">
          <div class="style-block__head">
            <input v-model="layer.name" class="ghost-input" @input="store.markStepConfigured('style')" />
            <button class="more-button" type="button" @click="store.removeBasinLayer(layer.id)">...</button>
          </div>

          <div class="style-row">
            <span class="style-row__name">边界颜色</span>
            <el-input v-model="layer.style.boundary_color" class="row-input row-input--color" @change="store.markStepConfigured('style')" />
            <el-input-number v-model="layer.style.boundary_width_pt" :min="0.1" :step="0.1" controls-position="right" class="row-input row-input--num" @change="store.markStepConfigured('style')" />
          </div>

          <div class="style-row">
            <span class="style-row__name">填充样式</span>
            <el-input v-model="layer.style.fill_color" class="row-input row-input--color" @change="store.markStepConfigured('style')" />
            <el-input-number v-model="layer.style.fill_opacity" :min="0" :max="1" :step="0.05" controls-position="right" class="row-input row-input--num" @change="store.markStepConfigured('style')" />
          </div>
        </div>

        <div v-for="layer in store.form.inputs.river_networks" :key="layer.id" class="style-block">
          <div class="style-block__head">
            <input v-model="layer.name" class="ghost-input" @input="store.markStepConfigured('style')" />
            <button class="more-button" type="button" @click="store.removeRiverLayer(layer.id)">...</button>
          </div>

          <div class="style-row">
            <span class="style-row__name">河流样式</span>
            <el-input v-model="layer.style.color" class="row-input row-input--color" @change="store.markStepConfigured('style')" />
            <el-input-number v-model="layer.style.width_pt" :min="0.1" :step="0.1" controls-position="right" class="row-input row-input--num" @change="store.markStepConfigured('style')" />
          </div>
        </div>

        <div v-if="!store.form.inputs.basin_boundaries.length && !store.form.inputs.river_networks.length" class="empty-state">
          请先在“数据准备”中上传流域边界和河流网络。
        </div>
      </div>

      <div class="action-row action-row--bottom">
        <button class="secondary-cta" type="button" @click="onStepBack('data')">返回数据</button>
        <button class="primary-cta" type="button" @click="onStepBack('stations')">下一步：出图参数</button>
      </div>
    </section>

    <section v-else-if="store.activeStep === 'stations'" class="step-panel">
      <div class="section-title">
        <el-icon><View /></el-icon>
        <span>标注与图例</span>
      </div>

      <div class="step-body step-body--scroll">
        <div v-for="(layer, index) in stationLayers" :key="layer.id" class="style-block">
          <div class="style-block__head style-block__head--stack">
            <div class="layer-headline">
              <input v-model="layer.layer_name" class="ghost-input" @input="store.markStepConfigured('stations')" />
              <small v-if="layer.upload" class="path-text">{{ layer.upload.original_name }}</small>
            </div>
            <div class="button-cluster">
              <button class="mini-action" type="button" @click="openInput(stationInputId(layer.id))">上传 Excel</button>
              <button class="mini-action" type="button" @click="applyLayerSettings(layer)">应用到全部点位</button>
            </div>
            <input
              :id="stationInputId(layer.id)"
              class="native-file-input"
              type="file"
              accept=".xlsx"
              @change="handleStationSelection(layer, $event)"
            />
          </div>

          <div class="form-grid">
            <label>
              <span>工作表</span>
              <el-input v-model="layer.sheet_name" @change="store.markStepConfigured('stations')" />
            </label>
            <label>
              <span>经度字段</span>
              <el-select v-model="layer.x_field" filterable allow-create @change="store.markStepConfigured('stations')">
                <el-option v-for="header in layer.headers" :key="header" :label="header" :value="header" />
              </el-select>
            </label>
            <label>
              <span>纬度字段</span>
              <el-select v-model="layer.y_field" filterable allow-create @change="store.markStepConfigured('stations')">
                <el-option v-for="header in layer.headers" :key="header" :label="header" :value="header" />
              </el-select>
            </label>
            <label>
              <span>名称字段</span>
              <el-select v-model="layer.name_field" filterable allow-create @change="store.setStationNameField(layer.id, layer.name_field)">
                <el-option v-for="header in layer.headers" :key="header" :label="header" :value="header" />
              </el-select>
            </label>
          </div>

          <div class="style-row style-row--station">
            <span class="style-row__name">{{ stationLabel(index) }}</span>
            <el-select v-model="layer.symbol.shape" class="row-input row-input--select" @change="store.markStepConfigured('stations')">
              <el-option v-for="shape in store.options.station_symbol_shapes" :key="shape" :label="shapeLabel(shape)" :value="shape" />
            </el-select>
            <el-input-number v-model="layer.symbol.size_pt" :min="4" :step="1" class="row-input row-input--num" @change="store.markStepConfigured('stations')" />
          </div>

          <div class="form-grid">
            <label>
              <span>颜色预设</span>
              <el-select v-model="layer.symbol.color_preset" @change="syncLayerColor(layer)">
                <el-option
                  v-for="(value, key) in store.options.station_symbol_color_presets"
                  :key="key"
                  :label="colorLabel(key, value)"
                  :value="key"
                />
              </el-select>
            </label>
            <label>
              <span>自定义颜色</span>
              <el-input v-model="layer.symbol.color" class="row-input row-input--color" @change="store.markStepConfigured('stations')" />
            </label>
            <label>
              <span>旋转角度</span>
              <el-input-number v-model="layer.symbol.rotation_deg" :min="-180" :max="180" :step="5" @change="store.markStepConfigured('stations')" />
            </label>
            <label>
              <span>标注位置</span>
              <el-select v-model="layer.label.position" @change="store.markStepConfigured('stations')">
                <el-option v-for="position in store.options.label_positions" :key="position" :label="positionLabel(position)" :value="position" />
              </el-select>
            </label>
            <label>
              <span>标注字号</span>
              <el-input-number v-model="layer.label.font_size_pt" :min="8" :step="1" @change="store.markStepConfigured('stations')" />
            </label>
            <label>
              <span>标注颜色</span>
              <el-input v-model="layer.label.color" class="row-input row-input--color" @change="store.markStepConfigured('stations')" />
            </label>
          </div>

          <details v-if="layer.points.length" class="detail-block">
            <summary>逐点样式（{{ layer.points.length }} 个点）</summary>
            <div class="point-list">
              <div v-for="point in layer.points.slice(0, 6)" :key="`${layer.id}-${point.row_number}`" class="point-row">
                <strong>{{ point.display_name }}</strong>
                <div class="point-row__controls">
                  <el-select v-model="point.symbol.shape" size="small" @change="store.markStepConfigured('stations')">
                    <el-option v-for="shape in store.options.station_symbol_shapes" :key="shape" :label="shapeLabel(shape)" :value="shape" />
                  </el-select>
                  <el-select v-model="point.symbol.color_preset" size="small" @change="syncPointColor(point)">
                    <el-option
                      v-for="(value, key) in store.options.station_symbol_color_presets"
                      :key="key"
                      :label="colorLabel(key, value)"
                      :value="key"
                    />
                  </el-select>
                  <el-switch v-model="point.label.enabled" @change="store.markStepConfigured('stations')" />
                </div>
              </div>
            </div>
          </details>
        </div>

        <div class="style-block">
          <div class="subsection-title">图例与标注总设置</div>

          <div class="inline-form">
            <label>标注字体</label>
            <el-select v-model="store.form.layout.basemap" class="stretch">
              <el-option v-for="font in fontOptions" :key="font" :label="font" :value="font" />
            </el-select>
              <el-input-number v-model="firstStationLayer.label.font_size_pt" :min="8" :step="1" class="tiny-num" @change="store.markStepConfigured('stations')" />
            <el-input v-model="firstStationLayer.label.color" class="color-box" @change="store.markStepConfigured('stations')" />
          </div>

          <div class="slider-row">
            <span>图例间距</span>
            <span>低</span>
            <el-slider v-model="store.form.layout.legend_style.item_gap" :min="0" :max="10" :step="1" class="slider-field" @change="markOutput" />
            <span>高</span>
          </div>

          <div class="form-grid">
            <label>
              <span>图例图样宽</span>
              <el-input-number v-model="store.form.layout.legend_style.patch_width" :min="1" :step="1" @change="markOutput" />
            </label>
            <label>
              <span>图例图样高</span>
              <el-input-number v-model="store.form.layout.legend_style.patch_height" :min="1" :step="1" @change="markOutput" />
            </label>
            <label>
              <span>文字间距</span>
              <el-input-number v-model="store.form.layout.legend_style.text_gap" :min="0" :step="1" @change="markOutput" />
            </label>
            <label>
              <span>最小字号</span>
              <el-input-number v-model="store.form.layout.legend_style.min_font_size" :min="1" :step="1" @change="markOutput" />
            </label>
          </div>

          <div class="legend-position">
            <span>图例位置</span>
            <div class="legend-position__buttons">
              <button :class="{ active: activeLegendPosition() === 'left' }" type="button" @click="setLegendPosition('left')"></button>
              <button :class="{ active: activeLegendPosition() === 'center' }" type="button" @click="setLegendPosition('center')"></button>
              <button :class="{ active: activeLegendPosition() === 'right' }" type="button" @click="setLegendPosition('right')"></button>
              <button class="active accent" type="button" @click="$emit('preview-layout')"></button>
            </div>
          </div>

          <div class="inline-form inline-form--legend">
            <label>图例标题</label>
            <el-input
              :model-value="primaryLegendRow?.legend_name || '图例'"
              class="stretch"
              @update:model-value="updateLegendName(primaryLegendRow, $event)"
            />
            <span class="toggle-inline">
              显示
              <el-switch v-model="store.form.layout.elements.legend.enabled" @change="markOutput" />
            </span>
          </div>

          <div v-if="legendRows.length" class="legend-table">
            <div v-for="row in legendRows.slice(0, 6)" :key="row.source_key" class="legend-table__row">
              <span>{{ row.default_name }}</span>
              <el-input
                :model-value="row.legend_name"
                placeholder="图例显示名"
                @update:model-value="updateLegendName(row, $event)"
              />
            </div>
          </div>
        </div>
      </div>

      <div class="action-row action-row--bottom">
        <button class="secondary-cta" type="button" @click="onStepBack('style')">返回样式</button>
        <button class="primary-cta" type="button" @click="onStepBack('output')">下一步：导出结果</button>
      </div>
    </section>

    <section v-else class="step-panel">
      <div class="section-title">
        <el-icon><Download /></el-icon>
        <span>页面与导出</span>
      </div>

      <div class="step-body step-body--scroll">
        <div class="style-block">
          <div class="subsection-title">导出设置</div>

          <div class="preset-block">
            <span>纸张尺寸</span>
            <div class="pill-grid">
              <button
                v-for="preset in paperPresets"
                :key="preset.label"
                :class="{ active: activePaperLabel(preset.label) }"
                type="button"
                @click="setPaperPreset(preset.width, preset.height)"
              >
                {{ preset.label }}
              </button>
            </div>
          </div>

          <div class="preset-block">
            <span>分辨率（DPI）</span>
            <div class="pill-grid pill-grid--tight">
              <button
                v-for="dpi in dpiPresets"
                :key="dpi"
                :class="{ active: store.form.output.dpi === dpi }"
                type="button"
                @click="setDpiPreset(dpi)"
              >
                {{ dpi }}
              </button>
            </div>
          </div>

          <div class="form-grid">
            <label>
              <span>地图标题</span>
              <el-input v-model="store.form.map_title" @change="markOutput" />
            </label>
            <label>
              <span>输出目录</span>
              <el-input v-model="store.form.output_dir" @change="markOutput" />
            </label>
            <label>
              <span>宽度 px</span>
              <el-input-number v-model="store.form.output.width_px" :min="300" :step="100" @change="markOutput" />
            </label>
            <label>
              <span>高度 px</span>
              <el-input-number v-model="store.form.output.height_px" :min="300" :step="100" @change="markOutput" />
            </label>
            <label>
              <span>底图</span>
              <el-select v-model="store.form.layout.basemap" @change="markOutput">
                <el-option v-for="basemap in store.options.basemaps" :key="basemap" :label="basemap" :value="basemap" />
              </el-select>
            </label>
          </div>

          <div class="export-row">
            <span>输出格式</span>
            <label><input v-model="exportFormats.png" type="checkbox" /> PNG</label>
            <label><input v-model="exportFormats.pdf" type="checkbox" /> PDF</label>
            <label><input v-model="exportFormats.geotiff" type="checkbox" /> GeoTIFF</label>
          </div>
        </div>

        <div class="style-block">
          <div class="subsection-title">人工布局坐标</div>

          <div class="layout-block">
            <div class="layout-block__title">地图框</div>
            <div class="form-grid form-grid--layout">
              <label v-for="field in layoutFields" :key="`map-frame-${field.key}`">
                <span>{{ field.label }}</span>
                <el-input-number
                  v-model="store.form.layout.elements.map_frame[field.key]"
                  :step="1"
                  :precision="2"
                  @change="markOutput"
                />
              </label>
            </div>
          </div>

          <div class="layout-block">
            <div class="layout-block__title">标题</div>
            <div class="form-grid form-grid--layout">
              <label v-for="field in layoutFields" :key="`title-${field.key}`">
                <span>{{ field.label }}</span>
                <el-input-number
                  v-model="store.form.layout.elements.title[field.key]"
                  :step="1"
                  :precision="2"
                  controls-position="right"
                  @change="markOutput"
                />
              </label>
              <label>
                <span>字号</span>
                <el-input-number v-model="store.form.layout.elements.title.font_size" :min="1" :step="1" @change="markOutput" />
              </label>
              <label class="checkbox-field">
                <span>白底</span>
                <el-switch v-model="store.form.layout.elements.title.background" @change="markOutput" />
              </label>
            </div>
          </div>

          <div class="layout-block">
            <div class="layout-block__title">图例 / 比例尺 / 指北针</div>
            <div class="layout-columns">
              <div v-for="item in layoutElementKeys" :key="item" class="layout-subblock">
                <div class="layout-subblock__title">{{ item === 'legend' ? '图例' : item === 'scale_bar' ? '比例尺' : '指北针' }}</div>
                <div class="form-grid form-grid--layout">
                  <label v-for="field in layoutFields" :key="`${item}-${field.key}`">
                    <span>{{ field.label }}</span>
                    <el-input-number
                      v-model="store.form.layout.elements[item][field.key]"
                      :step="1"
                      :precision="2"
                      @change="markOutput"
                    />
                  </label>
                  <label v-if="item === 'legend'" class="checkbox-field">
                    <span>白底</span>
                    <el-switch v-model="store.form.layout.elements.legend.background" @change="markOutput" />
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="style-block">
          <div class="subsection-title">地图视角</div>
          <el-radio-group v-model="store.form.map_view.mode" @change="markOutput">
            <el-radio-button label="auto">自动范围</el-radio-button>
            <el-radio-button label="auto_padding">自动范围 + 留白</el-radio-button>
            <el-radio-button label="manual_extent">手动范围</el-radio-button>
          </el-radio-group>

          <div v-if="store.form.map_view.mode === 'auto_padding'" class="form-grid">
            <label>
              <span>左留白</span>
              <el-input-number v-model="store.form.map_view.padding.left" :min="0" :step="0.05" :precision="4" @change="markOutput" />
            </label>
            <label>
              <span>右留白</span>
              <el-input-number v-model="store.form.map_view.padding.right" :min="0" :step="0.05" :precision="4" @change="markOutput" />
            </label>
            <label>
              <span>上留白</span>
              <el-input-number v-model="store.form.map_view.padding.top" :min="0" :step="0.05" :precision="4" @change="markOutput" />
            </label>
            <label>
              <span>下留白</span>
              <el-input-number v-model="store.form.map_view.padding.bottom" :min="0" :step="0.05" :precision="4" @change="markOutput" />
            </label>
          </div>

          <div v-if="store.form.map_view.mode === 'manual_extent'" class="form-grid">
            <label>
              <span>XMin</span>
              <el-input-number v-model="store.form.map_view.extent.xmin" :step="0.1" :precision="6" @change="markOutput" />
            </label>
            <label>
              <span>YMin</span>
              <el-input-number v-model="store.form.map_view.extent.ymin" :step="0.1" :precision="6" @change="markOutput" />
            </label>
            <label>
              <span>XMax</span>
              <el-input-number v-model="store.form.map_view.extent.xmax" :step="0.1" :precision="6" @change="markOutput" />
            </label>
            <label>
              <span>YMax</span>
              <el-input-number v-model="store.form.map_view.extent.ymax" :step="0.1" :precision="6" @change="markOutput" />
            </label>
          </div>
        </div>

        <div v-if="store.error" class="error-strip">{{ store.error }}</div>
        <div v-if="store.renderResult?.output_png" class="result-strip">
          <span>{{ store.renderResult.status }}</span>
          <small>{{ store.renderResult.output_png }}</small>
        </div>
      </div>

      <div class="action-row action-row--bottom">
        <button class="secondary-cta" type="button" @click="emit('preview-layout')">
          <el-icon><View /></el-icon>
          <span>预览版式</span>
        </button>
        <button class="primary-cta" type="button" :disabled="store.rendering" @click="store.submitRender">
          <el-icon><MagicStick /></el-icon>
          <span>{{ store.rendering ? '生成中...' : '生成专题图' }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.control-root {
  display: flex;
  flex: 1;
  min-height: 0;
}

.step-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.step-body {
  display: grid;
  gap: 12px;
  min-height: 0;
}

.step-body--scroll {
  flex: 1;
  overflow: auto;
  padding-right: 4px;
}

.step-body--scroll::-webkit-scrollbar {
  width: 6px;
}

.step-body--scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(130, 255, 240, 0.28);
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  color: #7cefff;
  font-size: 1.12rem;
  font-weight: 800;
}

.upload-card,
.style-block,
.layout-block,
.layout-subblock {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(168, 247, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.035);
  box-sizing: border-box;
}

.field-label,
.preset-block > span,
.export-row > span,
.subsection-title,
.layout-block__title,
.layout-subblock__title {
  color: rgba(232, 247, 255, 0.88);
  font-size: 0.88rem;
  font-weight: 700;
}

.upload-card p,
.path-text {
  margin: 2px 0 0;
  color: rgba(232, 247, 255, 0.64);
  font-size: 0.8rem;
  line-height: 1.4;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip-row--single {
  align-items: center;
}

.data-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  max-width: 100%;
  padding: 0 11px;
  border: 1px solid rgba(168, 247, 255, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(228, 246, 255, 0.68);
  font-size: 0.82rem;
}

.data-chip--filled {
  color: #e9f9ff;
}

.mini-action,
.full-action,
.more-button,
.pill-grid button,
.secondary-cta,
.primary-cta,
.legend-position__buttons button {
  border: 1px solid rgba(168, 247, 255, 0.14);
  border-radius: 8px;
  cursor: pointer;
}

.mini-action,
.full-action,
.more-button {
  min-height: 32px;
  padding: 0 12px;
  background: rgba(255, 255, 255, 0.04);
  color: #e9f9ff;
}

.full-action {
  width: 100%;
  border-style: dashed;
}

.native-file-input {
  display: none;
}

.dataset-list,
.point-list,
.legend-table,
.layout-columns {
  display: grid;
  gap: 8px;
}

.dataset-row,
.style-block__head,
.button-cluster,
.point-row__controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dataset-row,
.point-row,
.legend-table__row {
  padding: 8px 10px;
  border: 1px solid rgba(168, 247, 255, 0.1);
  border-radius: 8px;
  color: #eafcff;
  background: rgba(255, 255, 255, 0.02);
}

.dataset-row,
.legend-table__row {
  justify-content: space-between;
}

.dataset-row button {
  border: 0;
  background: transparent;
  color: #7cefff;
  cursor: pointer;
}

.style-block__head {
  justify-content: space-between;
}

.style-block__head--stack {
  display: grid;
  gap: 8px;
}

.layer-headline {
  display: grid;
  gap: 2px;
}

.button-cluster {
  flex-wrap: wrap;
}

.ghost-input {
  min-width: 0;
  width: 100%;
  border: 0;
  background: transparent;
  color: #edf9ff;
  font: inherit;
  font-weight: 800;
  outline: 0;
}

.style-row {
  display: grid;
  grid-template-columns: 1fr minmax(72px, 0.9fr) minmax(88px, 0.8fr);
  gap: 8px;
  align-items: center;
}

.style-row--station {
  grid-template-columns: 1fr minmax(90px, 1fr) minmax(88px, 0.8fr);
}

.style-row__name {
  color: #edf9ff;
  font-weight: 700;
  font-size: 0.86rem;
}

.row-switch {
  justify-self: center;
}

.row-input {
  width: 100%;
}

.row-input--color :deep(.el-input__wrapper),
.color-box :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.04);
}

.row-input--num :deep(.el-input-number),
.tiny-num :deep(.el-input-number),
.form-grid :deep(.el-input-number) {
  width: 100%;
}

.control-root :deep(.el-input-number .el-input__wrapper),
.control-root :deep(.el-input__wrapper),
.control-root :deep(.el-select__wrapper) {
  min-height: 34px;
  background: rgba(255, 255, 255, 0.07);
  box-shadow: inset 0 0 0 1px rgba(168, 247, 255, 0.12);
}

.control-root :deep(.el-input-number__input),
.control-root :deep(.el-input__inner),
.control-root :deep(.el-select__selected-item) {
  color: #eefcff;
  font-size: 0.92rem;
  font-weight: 700;
}

.form-grid--layout :deep(.el-input-number__input) {
  text-align: center;
  letter-spacing: 0;
}

.control-root :deep(.el-input-number__decrease),
.control-root :deep(.el-input-number__increase) {
  display: none;
}

.control-root :deep(.el-input-number .el-input__wrapper) {
  padding-right: 11px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.form-grid--layout {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.form-grid label {
  display: grid;
  gap: 6px;
  color: rgba(232, 247, 255, 0.78);
  font-size: 0.8rem;
}

.checkbox-field {
  align-content: end;
}

.inline-form,
.slider-row,
.legend-position,
.export-row {
  display: grid;
  gap: 10px;
  align-items: center;
}

.inline-form {
  grid-template-columns: 74px minmax(0, 1fr) 78px 44px;
}

.inline-form--legend {
  grid-template-columns: 74px minmax(0, 1fr) 94px;
}

.stretch {
  width: 100%;
}

.color-box {
  width: 44px;
}

.slider-row {
  grid-template-columns: 74px 24px minmax(0, 1fr) 24px;
  color: rgba(232, 247, 255, 0.82);
}

.slider-field {
  margin: 0 8px;
}

.legend-position {
  grid-template-columns: 74px minmax(0, 1fr);
}

.legend-position__buttons {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.legend-position__buttons button {
  position: relative;
  min-height: 32px;
  background: rgba(255, 255, 255, 0.04);
}

.legend-position__buttons button::before {
  position: absolute;
  inset: 7px 9px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  content: "";
}

.legend-position__buttons button::after {
  position: absolute;
  top: 8px;
  bottom: 8px;
  width: 8px;
  background: rgba(255, 255, 255, 0.24);
  content: "";
}

.legend-position__buttons button:nth-child(1)::after {
  left: 10px;
}

.legend-position__buttons button:nth-child(2)::after {
  left: calc(50% - 4px);
}

.legend-position__buttons button:nth-child(3)::after {
  right: 10px;
}

.legend-position__buttons button.active {
  border-color: rgba(130, 255, 240, 0.42);
}

.legend-position__buttons button.accent {
  background: rgba(130, 255, 240, 0.14);
}

.toggle-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: rgba(232, 247, 255, 0.82);
  font-size: 0.82rem;
}

.detail-block {
  padding-top: 4px;
}

.detail-block summary {
  cursor: pointer;
  color: #7cefff;
  font-size: 0.84rem;
  font-weight: 700;
}

.point-row {
  display: grid;
  gap: 8px;
}

.point-row strong {
  font-size: 0.82rem;
}

.point-row__controls {
  flex-wrap: wrap;
}

.legend-table__row {
  display: grid;
  grid-template-columns: minmax(0, 120px) minmax(0, 1fr);
  align-items: center;
}

.preset-block {
  display: grid;
  gap: 10px;
}

.pill-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.pill-grid--tight {
  grid-template-columns: repeat(3, minmax(0, 96px));
}

.pill-grid button {
  min-height: 36px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(232, 247, 255, 0.84);
}

.pill-grid button.active {
  border-color: rgba(130, 255, 240, 0.42);
  background: rgba(130, 255, 240, 0.14);
  color: #eafcff;
}

.export-row {
  grid-template-columns: 74px repeat(3, auto);
  color: rgba(232, 247, 255, 0.82);
}

.export-row label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.action-row {
  display: grid;
  grid-template-columns: 1fr 1.15fr;
  gap: 12px;
}

.action-row--bottom {
  margin-top: 12px;
  flex-shrink: 0;
}

.secondary-cta,
.primary-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 52px;
  font-size: 1rem;
  font-weight: 800;
}

.primary-cta--wide {
  width: 100%;
}

.secondary-cta {
  background: rgba(5, 24, 41, 0.52);
  color: #edf9ff;
}

.primary-cta {
  background: linear-gradient(135deg, #8ff7ed, #35c8ed);
  color: #04233f;
  box-shadow: 0 18px 40px rgba(45, 219, 240, 0.22);
}

.primary-cta:disabled {
  opacity: 0.68;
}

.empty-state,
.error-strip,
.result-strip {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 0.84rem;
}

.empty-state {
  border: 1px solid rgba(168, 247, 255, 0.12);
  color: rgba(232, 247, 255, 0.7);
}

.error-strip {
  border: 1px solid rgba(255, 128, 128, 0.34);
  background: rgba(93, 34, 34, 0.52);
  color: #ffd3d3;
}

.result-strip {
  border: 1px solid rgba(121, 236, 160, 0.3);
  background: rgba(30, 91, 57, 0.38);
  color: #dbfff0;
}

.result-strip small {
  overflow-wrap: anywhere;
  color: rgba(226, 248, 239, 0.76);
}

@media (max-width: 860px) {
  .style-row,
  .style-row--station,
  .form-grid,
  .form-grid--layout,
  .inline-form,
  .inline-form--legend,
  .slider-row,
  .legend-position,
  .export-row,
  .action-row,
  .legend-table__row {
    grid-template-columns: 1fr;
  }

  .pill-grid,
  .pill-grid--tight {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
