<script setup lang="ts">
import type { UploadRequestOptions } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import type { StationLayerForm, StationPointForm, StationShape } from '@/types'
import { markerPolygonPoints } from '@/utils/symbolPreview'

const store = useWorkspaceStore()

async function handleStationUpload(layer: StationLayerForm, options: UploadRequestOptions) {
  await store.uploadStationExcel(layer.id, options.file)
}

function stationUploadRequest(layer: StationLayerForm) {
  return (options: UploadRequestOptions) => handleStationUpload(layer, options)
}

function shapeLabel(shape: StationShape) {
  const labels: Record<StationShape, string> = {
    circle: '圆形',
    triangle: '三角形',
    square: '正方形',
    diamond: '菱形',
    rectangle: '矩形'
  }
  return labels[shape]
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
    blue: '蓝色',
    cyan: '青色',
    purple: '紫色',
    orange: '橙色',
    green: '绿色',
    red: '红色',
    black: '黑色'
  }
  return `${labels[key] || key} ${value}`
}

function pointColor(point: StationPointForm) {
  return point.symbol.color || store.options.station_symbol_color_presets[point.symbol.color_preset] || '#1f78ff'
}

function pointRotation(point: StationPointForm) {
  return `rotate(${point.symbol.rotation_deg || 0}deg)`
}
</script>

<template>
  <section class="panel station-panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">步骤 03：站点图层</p>
        <h2>站点图层</h2>
      </div>
      <el-button round @click="store.addStationLayer">新增站点图层</el-button>
    </div>

    <el-collapse>
      <el-collapse-item
        v-for="(layer, index) in store.form.inputs.station_layers"
        :key="layer.id"
        :title="`${index + 1}. ${layer.layer_name}`"
        :name="layer.id"
      >
        <div class="station-layer-grid">
          <div class="station-layer-main">
            <div class="station-upload-row">
              <div>
                <el-upload
                  action="#"
                  accept=".xlsx"
                  :show-file-list="false"
                  :http-request="stationUploadRequest(layer)"
                >
                  <el-button round>上传站点 Excel</el-button>
                </el-upload>
                <p v-if="layer.upload" class="path-text">{{ layer.upload.original_name }}</p>
              </div>

              <el-button
                v-if="store.form.inputs.station_layers.length > 1"
                type="danger"
                plain
                round
                @click="store.removeStationLayer(layer.id)"
              >
                删除此图层
              </el-button>
            </div>

            <el-form label-position="top" class="form-grid form-grid--compact">
              <el-form-item label="图层名称">
                <el-input v-model="layer.layer_name" />
              </el-form-item>
              <el-form-item label="工作表">
                <el-input v-model="layer.sheet_name" />
              </el-form-item>
              <el-form-item label="经度字段">
                <el-select v-model="layer.x_field" filterable allow-create>
                  <el-option v-for="header in layer.headers" :key="header" :label="header" :value="header" />
                </el-select>
              </el-form-item>
              <el-form-item label="纬度字段">
                <el-select v-model="layer.y_field" filterable allow-create>
                  <el-option v-for="header in layer.headers" :key="header" :label="header" :value="header" />
                </el-select>
              </el-form-item>
              <el-form-item label="名称字段">
                <el-select
                  v-model="layer.name_field"
                  filterable
                  allow-create
                  @change="store.setStationNameField(layer.id, layer.name_field)"
                >
                  <el-option v-for="header in layer.headers" :key="header" :label="header" :value="header" />
                </el-select>
              </el-form-item>
            </el-form>

            <div class="point-style-section point-style-section--defaults">
              <div class="mini-heading">
                <div>
                  <h3>图层默认样式</h3>
                  <p class="panel-copy">默认样式会用于新点位，以及没有单独配置的 Excel 数据行。</p>
                </div>
                <el-button round plain :disabled="!layer.points.length" @click="store.applyLayerStyleToStationPoints(layer.id)">
                  套用到全部点位
                </el-button>
              </div>

              <el-form label-position="top" class="form-grid form-grid--dense">
                <el-form-item label="符号形状">
                  <el-select v-model="layer.symbol.shape">
                    <el-option
                      v-for="shape in store.options.station_symbol_shapes"
                      :key="shape"
                      :label="shapeLabel(shape)"
                      :value="shape"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="颜色预设">
                  <el-select v-model="layer.symbol.color_preset" @change="store.syncPresetColor(layer)">
                    <el-option
                      v-for="(value, key) in store.options.station_symbol_color_presets"
                      :key="key"
                      :label="colorLabel(key, value)"
                      :value="key"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="自定义颜色">
                  <el-color-picker v-model="layer.symbol.color" />
                </el-form-item>
                <el-form-item label="符号大小">
                  <el-input-number v-model="layer.symbol.size_pt" :min="4" :step="1" />
                </el-form-item>
                <el-form-item label="旋转角度">
                  <el-input-number v-model="layer.symbol.rotation_deg" :min="-180" :max="180" :step="5" />
                </el-form-item>
                <el-form-item label="标注位置">
                  <el-select v-model="layer.label.position">
                    <el-option
                      v-for="position in store.options.label_positions"
                      :key="position"
                      :label="positionLabel(position)"
                      :value="position"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="标注字号">
                  <el-input-number v-model="layer.label.font_size_pt" :min="8" :step="1" />
                </el-form-item>
                <el-form-item label="标注颜色">
                  <el-color-picker v-model="layer.label.color" />
                </el-form-item>
              </el-form>
            </div>

            <div class="point-style-section point-style-section--table">
              <div class="mini-heading">
                <div>
                  <h3>逐点样式</h3>
                  <p class="panel-copy">已从当前 Excel 图层识别到 {{ layer.points.length }} 个点位数据行。</p>
                </div>
              </div>

              <el-empty v-if="!layer.points.length" description="上传站点 Excel 后，可在这里逐点配置样式。" />
              <el-table v-else :data="layer.points" class="point-style-table" max-height="560">
                <el-table-column prop="row_number" label="行号" width="72" />
                <el-table-column label="点位" min-width="210">
                  <template #default="{ row }">
                    <div class="point-name-cell">
                      <svg class="point-symbol-icon" viewBox="0 0 100 100" aria-hidden="true">
                        <g :style="{ transform: pointRotation(row), transformOrigin: '50px 50px' }">
                          <circle v-if="row.symbol.shape === 'circle'" cx="50" cy="50" r="28" :fill="pointColor(row)" />
                          <polygon v-else :points="markerPolygonPoints(row.symbol.shape)" :fill="pointColor(row)" />
                        </g>
                      </svg>
                      <span>{{ row.display_name }}</span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="形状" min-width="150">
                  <template #default="{ row }">
                    <el-select v-model="row.symbol.shape" size="small">
                      <el-option
                        v-for="shape in store.options.station_symbol_shapes"
                        :key="shape"
                        :label="shapeLabel(shape)"
                        :value="shape"
                      />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="颜色" min-width="210">
                  <template #default="{ row }">
                    <div class="point-color-controls">
                      <el-select v-model="row.symbol.color_preset" size="small" @change="store.syncPointPresetColor(row)">
                        <el-option
                          v-for="(value, key) in store.options.station_symbol_color_presets"
                          :key="key"
                          :label="colorLabel(key, value)"
                          :value="key"
                        />
                      </el-select>
                      <el-color-picker v-model="row.symbol.color" size="small" />
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="大小" min-width="136">
                  <template #default="{ row }">
                    <el-input-number v-model="row.symbol.size_pt" size="small" :min="4" :step="1" />
                  </template>
                </el-table-column>
                <el-table-column label="旋转" min-width="136">
                  <template #default="{ row }">
                    <el-input-number v-model="row.symbol.rotation_deg" size="small" :min="-180" :max="180" :step="5" />
                  </template>
                </el-table-column>
                <el-table-column label="标注" min-width="88">
                  <template #default="{ row }">
                    <el-switch v-model="row.label.enabled" />
                  </template>
                </el-table-column>
                <el-table-column label="标注位置" min-width="150">
                  <template #default="{ row }">
                    <el-select v-model="row.label.position" size="small">
                      <el-option
                        v-for="position in store.options.label_positions"
                        :key="position"
                        :label="positionLabel(position)"
                        :value="position"
                      />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="字号" min-width="126">
                  <template #default="{ row }">
                    <el-input-number v-model="row.label.font_size_pt" size="small" :min="8" :step="1" />
                  </template>
                </el-table-column>
                <el-table-column label="标注颜色" min-width="118">
                  <template #default="{ row }">
                    <el-color-picker v-model="row.label.color" size="small" />
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="96" fixed="right">
                  <template #default="{ row }">
                    <el-button text size="small" @click="store.resetStationPointStyle(layer.id, row.row_number)">
                      重置
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>
