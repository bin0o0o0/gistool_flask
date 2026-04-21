<script setup lang="ts">
import { computed } from 'vue'
import { markerPolygonPoints, labelPositionStyle, markerRotationStyle, stationColor } from '@/utils/symbolPreview'
import type { StationLayerForm } from '@/types'

const props = defineProps<{
  layer: StationLayerForm
  colorPresets: Record<string, string>
}>()

// 符号预览是轻量 SVG，不做完整 GIS 地图预览；它只验证站点形状、颜色和标注方向。
const color = computed(() => stationColor(props.layer, props.colorPresets))
const points = computed(() => markerPolygonPoints(props.layer.symbol.shape))
const markerStyle = computed(() => ({
  width: `${props.layer.symbol.size_pt * 3}px`,
  ...markerRotationStyle(props.layer)
}))
const labelStyle = computed(() => {
  const positionStyle = labelPositionStyle(props.layer.label.position)
  return {
    ...positionStyle,
    color: props.layer.label.color,
    fontSize: `${props.layer.label.font_size_pt}px`,
    transform: positionStyle.transform
  }
})
</script>

<template>
  <div class="symbol-preview">
    <div class="symbol-canvas">
      <svg viewBox="0 0 100 100" class="marker-svg" :style="markerStyle">
        <circle v-if="layer.symbol.shape === 'circle'" cx="50" cy="50" r="26" :fill="color" />
        <polygon v-else :points="points" :fill="color" />
      </svg>
      <span v-if="layer.label.enabled" class="symbol-label" :style="labelStyle">
        {{ layer.sampleName || layer.layer_name }}
      </span>
    </div>
    <p>{{ layer.symbol.shape }} · {{ color }} · {{ layer.label.position }}</p>
  </div>
</template>
