<script setup lang="ts">
import { useWorkspaceStore } from '@/stores/workspace'

// 图层样式面板现在按“每个流域面 / 每个河流水系”分别配置样式。
const store = useWorkspaceStore()

const basinFillPresets = [
  '#e6f0d4',
  '#f6d7a7',
  '#d7ecf2',
  '#eadcf8',
  '#f4c6b8',
  '#d8ead8',
  '#fff1bf',
  '#d5e8d4'
]

const riverColorPresets = ['#2f80ed', '#00a6c8', '#4f8a8b', '#1f5f99', '#6aaed6', '#2b9c67']
</script>

<template>
  <section class="panel">
    <p class="eyebrow">Step 2: Style</p>
    <h2>流域与河流样式</h2>
    <p class="panel-copy">每个上传的流域面和河流水系都可以单独设置颜色、透明度和线宽。</p>

    <div class="style-section">
      <div class="panel-heading">
        <div>
          <h3>流域面图层</h3>
          <p>{{ store.form.inputs.basin_boundaries.length }} 个流域面</p>
        </div>
      </div>

      <el-empty v-if="!store.form.inputs.basin_boundaries.length" description="请先在基础数据步骤上传流域边界" />

      <div v-for="layer in store.form.inputs.basin_boundaries" :key="layer.id" class="layer-style-card">
        <div class="layer-style-card__title">
          <el-input v-model="layer.name" @update:model-value="store.markStepConfigured('style')" />
          <el-button
            text
            type="danger"
            @click="
              store.markStepConfigured('style');
              store.removeBasinLayer(layer.id)
            "
          >
            移除
          </el-button>
        </div>

        <el-form label-position="top" class="form-grid">
          <el-form-item label="边界颜色">
            <el-color-picker
              v-model="layer.style.boundary_color"
              @update:model-value="store.markStepConfigured('style')"
            />
          </el-form-item>
          <el-form-item label="边界线宽">
            <el-input-number
              v-model="layer.style.boundary_width_pt"
              :min="0.1"
              :step="0.1"
              @update:model-value="store.markStepConfigured('style')"
            />
          </el-form-item>
          <el-form-item label="填充颜色">
            <div class="color-preset-row">
              <button
                v-for="color in basinFillPresets"
                :key="color"
                type="button"
                class="color-swatch"
                :class="{ 'color-swatch--active': layer.style.fill_color === color }"
                :style="{ backgroundColor: color }"
                @click="
                  layer.style.fill_color = color;
                  store.markStepConfigured('style')
                "
              />
              <el-color-picker
                v-model="layer.style.fill_color"
                @update:model-value="store.markStepConfigured('style')"
              />
            </div>
          </el-form-item>
          <el-form-item label="填充透明度">
            <el-slider
              v-model="layer.style.fill_opacity"
              :min="0"
              :max="1"
              :step="0.05"
              @update:model-value="store.markStepConfigured('style')"
            />
          </el-form-item>
        </el-form>
      </div>
    </div>

    <div class="style-section">
      <div class="panel-heading">
        <div>
          <h3>河流水系图层</h3>
          <p>{{ store.form.inputs.river_networks.length }} 个河流水系</p>
        </div>
      </div>

      <el-empty v-if="!store.form.inputs.river_networks.length" description="请先在基础数据步骤上传河流水系" />

      <div v-for="layer in store.form.inputs.river_networks" :key="layer.id" class="layer-style-card">
        <div class="layer-style-card__title">
          <el-input v-model="layer.name" @update:model-value="store.markStepConfigured('style')" />
          <el-button
            text
            type="danger"
            @click="
              store.markStepConfigured('style');
              store.removeRiverLayer(layer.id)
            "
          >
            移除
          </el-button>
        </div>

        <el-form label-position="top" class="form-grid">
          <el-form-item label="河流颜色">
            <div class="color-preset-row">
              <button
                v-for="color in riverColorPresets"
                :key="color"
                type="button"
                class="color-swatch"
                :class="{ 'color-swatch--active': layer.style.color === color }"
                :style="{ backgroundColor: color }"
                @click="
                  layer.style.color = color;
                  store.markStepConfigured('style')
                "
              />
              <el-color-picker v-model="layer.style.color" @update:model-value="store.markStepConfigured('style')" />
            </div>
          </el-form-item>
          <el-form-item label="河流线宽">
            <el-input-number
              v-model="layer.style.width_pt"
              :min="0.1"
              :step="0.1"
              @update:model-value="store.markStepConfigured('style')"
            />
          </el-form-item>
        </el-form>
      </div>
    </div>
  </section>
</template>
