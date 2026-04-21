<script setup lang="ts">
import { useWorkspaceStore } from '@/stores/workspace'

// 输出设置面板控制标题、输出尺寸、DPI、底图、图例和比例尺开关。
const store = useWorkspaceStore()
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
        <el-checkbox v-model="store.form.layout.legend.enabled" @update:model-value="store.markStepConfigured('output')">
          图例
        </el-checkbox>
        <el-checkbox
          v-model="store.form.layout.scale_bar.enabled"
          @update:model-value="store.markStepConfigured('output')"
        >
          比例尺
        </el-checkbox>
      </el-form-item>
    </el-form>
  </section>
</template>
