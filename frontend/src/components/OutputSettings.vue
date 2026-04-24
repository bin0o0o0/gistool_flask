<script setup lang="ts">
import { computed } from 'vue'

import { collectLegendNameOverrides } from '@/utils/legendNameOverrides'
import { useWorkspaceStore } from '@/stores/workspace'
import type { LegendNameOverrideForm, LegendNameSourceType } from '@/types'

// 输出设置面板控制标题、输出尺寸、DPI、底图和模板布局元素开关。
const store = useWorkspaceStore()

const layoutFields = [
  { key: 'x', label: 'X' },
  { key: 'y', label: 'Y' },
  { key: 'width', label: '宽' },
  { key: 'height', label: '高' }
] as const

const legendNameRows = computed(() => collectLegendNameOverrides(store.form))

const markOutput = () => store.markStepConfigured('output')

function updateLegendName(sourceKey: string, sourceType: LegendNameSourceType, defaultName: string, value: string) {
  const normalized = value.trim()
  const overrides = store.form.layout.legend_style.name_overrides
  const overrideIndex = overrides.findIndex((item) => item.source_key === sourceKey)
  if (!normalized || normalized === defaultName) {
    if (overrideIndex >= 0) overrides.splice(overrideIndex, 1)
    markOutput()
    return
  }

  const nextOverride = {
    source_type: sourceType,
    source_key: sourceKey,
    default_name: defaultName,
    legend_name: normalized
  }
  if (overrideIndex >= 0) {
    overrides.splice(overrideIndex, 1, nextOverride)
  } else {
    overrides.push(nextOverride)
  }
  markOutput()
}

function handleLegendNameInput(row: LegendNameOverrideForm, value: string | undefined) {
  updateLegendName(row.source_key, row.source_type, row.default_name, value ?? '')
}
</script>

<template>
  <section class="panel">
    <p class="eyebrow">Step 4: Output</p>
    <h2>输出设置</h2>
    <el-form label-position="top" class="form-grid">
      <el-form-item label="地图标题">
        <el-input v-model="store.form.map_title" @update:model-value="store.markStepConfigured('output')" />
      </el-form-item>
      <el-form-item label="输出目录名">
        <el-input v-model="store.form.output_dir" @update:model-value="store.markStepConfigured('output')" />
      </el-form-item>
      <el-form-item label="宽度 px">
        <el-input-number
          v-model="store.form.output.width_px"
          :min="300"
          :step="100"
          @update:model-value="store.markStepConfigured('output')"
        />
      </el-form-item>
      <el-form-item label="高度 px">
        <el-input-number
          v-model="store.form.output.height_px"
          :min="300"
          :step="100"
          @update:model-value="store.markStepConfigured('output')"
        />
      </el-form-item>
      <el-form-item label="DPI">
        <el-input-number
          v-model="store.form.output.dpi"
          :min="72"
          :step="10"
          @update:model-value="store.markStepConfigured('output')"
        />
      </el-form-item>
      <el-form-item label="底图">
        <el-select v-model="store.form.layout.basemap" @update:model-value="store.markStepConfigured('output')">
          <el-option v-for="basemap in store.options.basemaps" :key="basemap" :label="basemap" :value="basemap" />
        </el-select>
      </el-form-item>
      <el-form-item label="布局元素">
        <el-checkbox
          v-model="store.form.layout.elements.title.enabled"
          @update:model-value="store.markStepConfigured('output')"
        >
          标题
        </el-checkbox>
        <el-checkbox
          v-model="store.form.layout.elements.legend.enabled"
          @update:model-value="store.markStepConfigured('output')"
        >
          图例
        </el-checkbox>
        <el-checkbox
          v-model="store.form.layout.elements.scale_bar.enabled"
          @update:model-value="store.markStepConfigured('output')"
        >
          比例尺
        </el-checkbox>
        <el-checkbox
          v-model="store.form.layout.elements.north_arrow.enabled"
          @update:model-value="store.markStepConfigured('output')"
        >
          指北针
        </el-checkbox>
      </el-form-item>

      <el-form-item label="布局模式">
        <el-segmented
          v-model="store.form.layout.mode"
          :options="[{ label: '人工自定义', value: 'manual' }]"
          @change="markOutput"
        />
      </el-form-item>

      <div class="layout-editor">
        <div class="layout-editor__header">
          <h3>人工布局坐标</h3>
          <p>单位使用模板当前布局单位。当前默认值来自测试样例 frontend_20260421xx_layout_legend_in_map_retry。</p>
        </div>

        <div class="layout-card">
          <div class="layout-card__title">地图框</div>
          <div class="layout-fields">
            <label v-for="field in layoutFields" :key="`map-frame-${field.key}`">
              <span>{{ field.label }}</span>
              <el-input-number
                v-model="store.form.layout.elements.map_frame[field.key]"
                :step="1"
                :precision="2"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
          </div>
        </div>

        <div class="layout-card">
          <div class="layout-card__title">
            <el-checkbox v-model="store.form.layout.elements.title.enabled" @update:model-value="markOutput">
              标题
            </el-checkbox>
          </div>
          <div class="layout-fields">
            <label v-for="field in layoutFields" :key="`title-${field.key}`">
              <span>{{ field.label }}</span>
              <el-input-number
                v-model="store.form.layout.elements.title[field.key]"
                :step="1"
                :precision="2"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>字号</span>
              <el-input-number
                v-model="store.form.layout.elements.title.font_size"
                :min="1"
                :step="1"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <el-checkbox v-model="store.form.layout.elements.title.background" @update:model-value="markOutput">
              白底
            </el-checkbox>
          </div>
        </div>

        <div class="layout-card">
          <div class="layout-card__title">
            <el-checkbox v-model="store.form.layout.elements.legend.enabled" @update:model-value="markOutput">
              图例
            </el-checkbox>
          </div>
          <div class="layout-fields">
            <label v-for="field in layoutFields" :key="`legend-${field.key}`">
              <span>{{ field.label }}</span>
              <el-input-number
                v-model="store.form.layout.elements.legend[field.key]"
                :step="1"
                :precision="2"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <el-checkbox v-model="store.form.layout.elements.legend.background" @update:model-value="markOutput">
              白底
            </el-checkbox>
          </div>
        </div>

        <div class="layout-card">
          <div class="layout-card__title">
            <el-checkbox v-model="store.form.layout.elements.scale_bar.enabled" @update:model-value="markOutput">
              比例尺
            </el-checkbox>
          </div>
          <div class="layout-fields">
            <label v-for="field in layoutFields" :key="`scale-${field.key}`">
              <span>{{ field.label }}</span>
              <el-input-number
                v-model="store.form.layout.elements.scale_bar[field.key]"
                :step="1"
                :precision="2"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
          </div>
        </div>

        <div class="layout-card">
          <div class="layout-card__title">
            <el-checkbox v-model="store.form.layout.elements.north_arrow.enabled" @update:model-value="markOutput">
              指北针
            </el-checkbox>
          </div>
          <div class="layout-fields">
            <label v-for="field in layoutFields" :key="`north-${field.key}`">
              <span>{{ field.label }}</span>
              <el-input-number
                v-model="store.form.layout.elements.north_arrow[field.key]"
                :step="1"
                :precision="2"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
          </div>
        </div>

        <div class="layout-card">
          <div class="layout-card__title">图例内部样式</div>
          <div class="layout-fields">
            <label>
              <span>图样宽</span>
              <el-input-number
                v-model="store.form.layout.legend_style.patch_width"
                :min="1"
                :step="1"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>图样高</span>
              <el-input-number
                v-model="store.form.layout.legend_style.patch_height"
                :min="1"
                :step="1"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>项间距</span>
              <el-input-number
                v-model="store.form.layout.legend_style.item_gap"
                :min="0"
                :step="1"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>文字间距</span>
              <el-input-number
                v-model="store.form.layout.legend_style.text_gap"
                :min="0"
                :step="1"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <el-checkbox v-model="store.form.layout.legend_style.scale_to_patch" @update:model-value="markOutput">
              图样统一缩放
            </el-checkbox>
          </div>
          <div class="legend-name-editor">
            <div class="legend-name-editor__header">
              <h4>图例名称</h4>
              <p>统一在这里修改图例显示名称；留空时使用当前图层名。</p>
            </div>
            <el-table :data="legendNameRows" size="small" empty-text="暂无可命名的图例项">
              <el-table-column label="来源" min-width="170">
                <template #default="{ row }">
                  <span class="legend-source-tag">{{ row.source_key }}</span>
                </template>
              </el-table-column>
              <el-table-column label="当前名称" min-width="180">
                <template #default="{ row }">
                  <span class="legend-default-name">{{ row.default_name }}</span>
                </template>
              </el-table-column>
              <el-table-column label="图例显示名" min-width="220">
                <template #default="{ row }">
                  <el-input
                    :model-value="row.legend_name"
                    placeholder="留空则跟随当前名称"
                    clearable
                    @update:model-value="handleLegendNameInput(row, $event)"
                  />
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <div class="layout-card">
          <div class="layout-card__title">地图视角</div>
          <el-radio-group v-model="store.form.map_view.mode" @change="markOutput">
            <el-radio-button label="auto">自动范围</el-radio-button>
            <el-radio-button label="auto_padding">自动范围 + 留白</el-radio-button>
            <el-radio-button label="manual_extent">手动范围</el-radio-button>
          </el-radio-group>
          <div v-if="store.form.map_view.mode === 'auto_padding'" class="layout-fields">
            <label>
              <span>左留白</span>
              <el-input-number
                v-model="store.form.map_view.padding.left"
                :min="0"
                :step="0.05"
                :precision="4"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>右留白</span>
              <el-input-number
                v-model="store.form.map_view.padding.right"
                :min="0"
                :step="0.05"
                :precision="4"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>上留白</span>
              <el-input-number
                v-model="store.form.map_view.padding.top"
                :min="0"
                :step="0.05"
                :precision="4"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>下留白</span>
              <el-input-number
                v-model="store.form.map_view.padding.bottom"
                :min="0"
                :step="0.05"
                :precision="4"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
          </div>
          <div v-if="store.form.map_view.mode === 'manual_extent'" class="layout-fields">
            <label>
              <span>XMin</span>
              <el-input-number
                v-model="store.form.map_view.extent.xmin"
                :step="0.1"
                :precision="6"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>YMin</span>
              <el-input-number
                v-model="store.form.map_view.extent.ymin"
                :step="0.1"
                :precision="6"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>XMax</span>
              <el-input-number
                v-model="store.form.map_view.extent.xmax"
                :step="0.1"
                :precision="6"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
            <label>
              <span>YMax</span>
              <el-input-number
                v-model="store.form.map_view.extent.ymax"
                :step="0.1"
                :precision="6"
                controls-position="right"
                @update:model-value="markOutput"
              />
            </label>
          </div>
        </div>
      </div>
    </el-form>
  </section>
</template>

<style scoped>
.layout-editor {
  grid-column: 1 / -1;
  display: grid;
  gap: 16px;
  margin-top: 8px;
}

.layout-editor__header h3,
.layout-card__title {
  margin: 0 0 8px;
  font-size: 16px;
  color: #34302c;
}

.layout-editor__header p {
  margin: 0;
  color: #716a62;
}

.layout-card {
  border: 1px solid #e5e0d8;
  border-radius: 8px;
  padding: 14px;
  background: #fffdf8;
}

.layout-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  align-items: end;
}

.layout-fields label {
  display: grid;
  gap: 6px;
  color: #625b53;
  font-size: 13px;
}

.layout-fields :deep(.el-input-number) {
  width: 100%;
}

.legend-name-editor {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.legend-name-editor__header h4 {
  margin: 0;
  font-size: 14px;
  color: #34302c;
}

.legend-name-editor__header p {
  margin: 4px 0 0;
  color: #716a62;
  font-size: 13px;
}

.legend-source-tag,
.legend-default-name {
  color: #544c44;
  word-break: break-word;
}
</style>
