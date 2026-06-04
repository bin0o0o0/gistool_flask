<script setup lang="ts">
import 'ol/ol.css'

import { computed, onBeforeUnmount, onMounted, ref, watch, type CSSProperties } from 'vue'
import type Feature from 'ol/Feature'
import type { FeatureLike } from 'ol/Feature'
import type Geometry from 'ol/geom/Geometry'
import GeoJSON from 'ol/format/GeoJSON'
import TileLayer from 'ol/layer/Tile'
import VectorLayer from 'ol/layer/Vector'
import OLMap from 'ol/Map'
import View from 'ol/View'
import { createEmpty, extend as extendExtent, isEmpty } from 'ol/extent'
import { fromLonLat } from 'ol/proj'
import OSM from 'ol/source/OSM'
import VectorSource from 'ol/source/Vector'
import { Circle as CircleStyle, Fill, RegularShape, Stroke, Style, Text } from 'ol/style'

import { renderApi } from '@/api/render'
import type { RenderResult, WorkspaceForm } from '@/types'
import { buildWorkspacePreviewData, toFeatureCollection } from '@/utils/workspacePreview'

const props = defineProps<{
  form: WorkspaceForm
  renderResult: RenderResult | null
  layoutMode: 'map' | 'layout'
}>()

const mapElement = ref<HTMLElement | null>(null)
const geojson = new GeoJSON()
const defaultCenter = fromLonLat([112.623, 28.567])
const preview = computed(() => buildWorkspacePreviewData(props.form))
const resultPreviewUrl = computed(() => {
  if (!props.renderResult?.output_png || props.renderResult.status !== 'succeeded') return ''
  return renderApi.previewUrl(props.renderResult.output_png)
})

const basinSource = new VectorSource<Feature<Geometry>>()
const riverSource = new VectorSource<Feature<Geometry>>()
const stationSource = new VectorSource<Feature<Geometry>>()

const basinLayer = new VectorLayer({
  source: basinSource,
  style: basinStyle
})

const riverLayer = new VectorLayer({
  source: riverSource,
  style: riverStyle
})

const stationLayer = new VectorLayer({
  source: stationSource,
  style: stationStyle
})

let map: OLMap | null = null

const mapFrameStyle = computed<CSSProperties>(() => {
  if (props.layoutMode !== 'layout') return { inset: '0' }
  return preview.value.layoutPreview.mapFrame.style as CSSProperties
})

function labelOffset(position: string, fontSize: number) {
  const distance = Math.max(12, fontSize * 0.85)
  const offsets: Record<string, [number, number]> = {
    top_left: [-distance, -distance],
    top: [0, -distance],
    top_right: [distance, -distance],
    right: [distance, 0],
    bottom_right: [distance, distance],
    bottom: [0, distance],
    bottom_left: [-distance, distance],
    left: [-distance, 0]
  }
  return offsets[position] || offsets.top_right
}

function colorWithOpacity(color: string, opacity: number) {
  const normalized = color.trim()
  const alpha = Math.max(0, Math.min(1, Number.isFinite(opacity) ? opacity : 0.35))
  const hex = normalized.startsWith('#') ? normalized.slice(1) : normalized
  if (/^[0-9a-fA-F]{6}$/.test(hex)) {
    const red = Number.parseInt(hex.slice(0, 2), 16)
    const green = Number.parseInt(hex.slice(2, 4), 16)
    const blue = Number.parseInt(hex.slice(4, 6), 16)
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`
  }
  return normalized
}

function basinStyle(feature: FeatureLike) {
  const style = (feature.get('previewStyle') || {}) as Record<string, unknown>
  const boundaryColor = String(style.boundaryColor || '#2f75db')
  const fillColor = String(style.fillColor || '#b7dcb5')
  const fillOpacity = Number(style.fillOpacity ?? 0.28)
  const boundaryWidth = Math.max(0.5, Number(style.boundaryWidth || 2.4))

  return new Style({
    stroke: new Stroke({ color: boundaryColor, width: boundaryWidth }),
    fill: new Fill({ color: colorWithOpacity(fillColor, fillOpacity) })
  })
}

function riverStyle(feature: FeatureLike) {
  const style = (feature.get('previewStyle') || {}) as Record<string, unknown>
  const color = String(style.color || '#57a4f5')
  const width = Math.max(0.5, Number(style.width || 1.8))

  return new Style({
    stroke: new Stroke({ color, width })
  })
}

function stationImageStyle(symbol: Record<string, unknown>) {
  const color = String(symbol.color || '#375bff')
  const size = Math.max(5, Number(symbol.size_pt || 16) * 0.45)
  const rotation = (Number(symbol.rotation_deg || 0) * Math.PI) / 180
  const stroke = new Stroke({ color: '#ffffff', width: 2 })
  const fill = new Fill({ color })

  if (symbol.shape === 'triangle') {
    return new RegularShape({ points: 3, radius: size, rotation, fill, stroke })
  }
  if (symbol.shape === 'square') {
    return new RegularShape({ points: 4, radius: size, angle: Math.PI / 4 + rotation, fill, stroke })
  }
  if (symbol.shape === 'diamond') {
    return new RegularShape({ points: 4, radius: size, angle: rotation, fill, stroke })
  }
  if (symbol.shape === 'rectangle') {
    return new RegularShape({ points: 4, radius: size * 1.15, radius2: size * 0.72, angle: Math.PI / 4 + rotation, fill, stroke })
  }
  return new CircleStyle({ radius: size, fill, stroke })
}

function stationStyle(feature: FeatureLike) {
  const symbol = (feature.get('symbol') || {}) as Record<string, unknown>
  const label = (feature.get('text') || {}) as Record<string, unknown>
  const fontSize = Number(label.font_size_pt || 14)
  const [offsetX, offsetY] = labelOffset(String(label.position || 'top_right'), fontSize)

  return new Style({
    image: stationImageStyle(symbol),
    text:
      label.enabled === false
        ? undefined
        : new Text({
            text: String(feature.get('label') || ''),
            font: `700 ${fontSize}px Arial, sans-serif`,
            fill: new Fill({ color: String(label.color || '#111827') }),
            stroke: new Stroke({ color: 'rgba(255,255,255,0.92)', width: 3 }),
            offsetX,
            offsetY
          })
  })
}

function syncSources() {
  basinSource.clear(true)
  riverSource.clear(true)
  stationSource.clear(true)

  basinSource.addFeatures(
    geojson.readFeatures(toFeatureCollection(preview.value.basinLayer), {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857'
    }) as Feature<Geometry>[]
  )
  riverSource.addFeatures(
    geojson.readFeatures(toFeatureCollection(preview.value.riverLayer), {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857'
    }) as Feature<Geometry>[]
  )
  stationSource.addFeatures(
    geojson.readFeatures(toFeatureCollection(preview.value.stationLayer), {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857'
    }) as Feature<Geometry>[]
  )

  fitLayers()
}

function fitLayers() {
  if (!map) return
  const extent = createEmpty()
  for (const source of [basinSource, riverSource, stationSource]) {
    const sourceExtent = source.getExtent()
    if (source.getFeatures().length && sourceExtent) extendExtent(extent, sourceExtent)
  }

  if (isEmpty(extent)) {
    map.getView().setCenter(defaultCenter)
    map.getView().setZoom(9)
    return
  }

  map.getView().fit(extent, {
    padding: [58, 96, 58, 58],
    duration: 180,
    maxZoom: 11
  })
}

function zoomBy(delta: number) {
  if (!map) return
  const view = map.getView()
  view.setZoom((view.getZoom() || 8) + delta)
}

function resetView() {
  fitLayers()
}

onMounted(() => {
  if (!mapElement.value) return
  map = new OLMap({
    target: mapElement.value,
    layers: [
      new TileLayer({
        source: new OSM()
      }),
      basinLayer,
      riverLayer,
      stationLayer
    ],
    controls: [],
    view: new View({
      center: defaultCenter,
      zoom: 8
    })
  })
  syncSources()
})

onBeforeUnmount(() => {
  if (map) {
    map.setTarget(undefined)
    map = null
  }
})

watch(
  () => props.form,
  () => {
    syncSources()
  },
  { deep: true }
)

watch(
  () => [props.layoutMode, preview.value.layoutPreview.mapFrame.style],
  () => {
    requestAnimationFrame(() => map?.updateSize())
  },
  { deep: true }
)
</script>

<template>
  <section class="workspace-preview">
    <div class="workspace-preview__canvas-wrap">
      <div class="workspace-preview__fallback"></div>
      <div class="workspace-preview__paper" :class="{ 'workspace-preview__paper--layout': layoutMode === 'layout' }" :style="preview.layoutPreview.paperStyle">
        <div class="layout-map-frame" :style="mapFrameStyle">
          <div ref="mapElement" class="workspace-preview__canvas"></div>
        </div>

        <template v-if="layoutMode === 'layout'">
          <div
            v-if="preview.layoutPreview.title"
            class="layout-title"
            :class="{ 'layout-element--background': preview.layoutPreview.title.background }"
            :style="{ ...preview.layoutPreview.title.style, fontSize: `${preview.layoutPreview.title.fontSizePx}px` }"
          >
            {{ preview.layoutPreview.title.text }}
          </div>

          <div
            v-if="preview.layoutPreview.legend"
            class="layout-legend"
            :style="preview.layoutPreview.legend.style"
          >
            <div class="layout-legend__content" :class="{ 'layout-element--background': preview.layoutPreview.legend.background }">
              <strong>{{ preview.layoutPreview.legend.title }}</strong>
              <div
                v-for="row in preview.layoutPreview.legend.rows"
                :key="`${row.sourceType}-${row.label}`"
                class="layout-legend__row"
                :style="{ marginTop: `${preview.layoutPreview.legend.rowGapPx}px` }"
              >
                <span class="layout-legend__patch" :data-kind="row.sourceType" :style="preview.layoutPreview.legend.patchStyle"></span>
                <span>{{ row.label }}</span>
              </div>
            </div>
          </div>

          <div v-if="preview.layoutPreview.scaleBar" class="layout-scale-bar" :style="preview.layoutPreview.scaleBar.style">
            <span></span>
            <small>比例尺</small>
          </div>

          <div v-if="preview.layoutPreview.northArrow" class="layout-north-arrow" :style="preview.layoutPreview.northArrow.style">
            <span>N</span>
            <svg viewBox="0 0 24 42" aria-hidden="true">
              <path d="M12 1 22 40 12 32 2 40Z" fill="currentColor" />
            </svg>
          </div>
        </template>
      </div>

      <div class="map-toolbar">
        <button type="button" @click="zoomBy(1)">+</button>
        <button type="button" @click="zoomBy(-1)">−</button>
        <button type="button" @click="resetView()">⌂</button>
        <button type="button">◉</button>
        <button type="button">◫</button>
        <button type="button">▤</button>
      </div>

      <div v-if="layoutMode !== 'layout'" class="map-north">N</div>

      <div v-if="layoutMode !== 'layout'" class="map-legend">
        <strong>图例</strong>
        <div class="legend-row">
          <span class="legend-line legend-line--basin"></span>
          <span>流域边界</span>
        </div>
        <div class="legend-row">
          <span class="legend-line legend-line--river"></span>
          <span>河流（分段显示）</span>
        </div>
        <div class="legend-row">
          <span class="legend-point legend-point--water"></span>
          <span>水文站点</span>
        </div>
        <div class="legend-row">
          <span class="legend-point legend-point--rain"></span>
          <span>雨量站点</span>
        </div>
      </div>

      <div v-if="layoutMode !== 'layout'" class="map-statusbar">
        <span>经度 112.6234° E</span>
        <span>纬度 28.5671° N</span>
        <span>比例尺 1:250,000</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.workspace-preview {
  position: relative;
  height: 100%;
  min-height: 0;
}

.workspace-preview__canvas-wrap {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(240, 247, 250, 0.24);
  border-radius: 10px;
  background: #edf2ef;
  box-shadow: 0 28px 84px rgba(0, 0, 0, 0.32);
}

.workspace-preview__fallback {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 20% 32%, rgba(137, 171, 108, 0.2), transparent 22%),
    radial-gradient(circle at 72% 28%, rgba(130, 171, 112, 0.16), transparent 20%),
    radial-gradient(circle at 42% 70%, rgba(132, 166, 104, 0.16), transparent 24%),
    linear-gradient(135deg, rgba(214, 228, 205, 0.9), rgba(239, 242, 236, 0.96)),
    repeating-linear-gradient(
      -24deg,
      rgba(111, 129, 99, 0.05) 0,
      rgba(111, 129, 99, 0.05) 2px,
      transparent 2px,
      transparent 14px
    );
}

.workspace-preview__paper {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.workspace-preview__paper--layout {
  inset: 24px;
  margin: auto;
  border: 1px solid rgba(21, 48, 74, 0.2);
  background: #f6f1e8;
  box-shadow: 0 22px 64px rgba(17, 31, 47, 0.24);
}

.layout-map-frame {
  position: absolute;
  overflow: hidden;
  background: #eaf0ec;
}

.workspace-preview__paper--layout .layout-map-frame {
  border: 2px solid rgba(16, 39, 64, 0.72);
  box-shadow: 0 10px 28px rgba(21, 48, 74, 0.16);
}

.workspace-preview__canvas {
  position: absolute;
  inset: 0;
}

.workspace-preview :deep(.ol-viewport) {
  background: #eff4f0;
  filter: saturate(0.82) brightness(1.02);
}

.map-toolbar,
.map-legend,
.map-statusbar {
  position: absolute;
  z-index: 3;
}

.layout-title,
.layout-legend,
.layout-scale-bar,
.layout-north-arrow {
  position: absolute;
  z-index: 4;
  box-sizing: border-box;
  color: #172536;
}

.layout-element--background {
  background: rgba(255, 255, 255, 0.9);
}

.layout-title {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px 8px;
  overflow: hidden;
  font-family: Georgia, "Times New Roman", serif;
  font-weight: 800;
  text-align: center;
  white-space: nowrap;
}

.layout-legend {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  overflow: hidden;
  box-sizing: border-box;
  font-size: 12px;
  line-height: 1.2;
}

.layout-legend__content {
  display: flex;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  flex-direction: column;
  justify-content: flex-start;
  align-items: flex-start;
  padding: 4px 6px;
  border: 1px solid rgba(23, 37, 54, 0.18);
  border-radius: 3px;
  overflow: hidden;
}

.layout-legend strong {
  display: block;
  margin-bottom: 2px;
  font-size: 13px;
}

.layout-legend__row {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 14px;
  white-space: nowrap;
}

.layout-legend__patch {
  display: inline-block;
  flex-shrink: 0;
  box-sizing: border-box;
  border: 1px solid rgba(23, 37, 54, 0.55);
  background: rgba(215, 236, 242, 0.82);
}

.layout-legend__patch[data-kind='river'] {
  height: 3px !important;
  border: 0;
  border-radius: 999px;
  background: #2f80ed;
}

.layout-legend__patch[data-kind='station_layer'],
.layout-legend__patch[data-kind='station_group'] {
  width: 10px !important;
  height: 10px !important;
  border-radius: 50%;
  background: #00a651;
}

.layout-scale-bar {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 2px;
  padding: 2px;
  font-size: 10px;
}

.layout-scale-bar span {
  display: block;
  height: 8px;
  border: 2px solid #172536;
  border-top: 0;
}

.layout-scale-bar small {
  color: #172536;
  font-size: 10px;
  font-weight: 700;
}

.layout-north-arrow {
  display: grid;
  place-items: center;
  color: #172536;
  font-family: Georgia, "Times New Roman", serif;
  font-weight: 900;
}

.layout-north-arrow span {
  font-size: 12px;
  line-height: 1;
}

.layout-north-arrow svg {
  width: 100%;
  height: calc(100% - 12px);
  min-height: 18px;
}

.map-toolbar {
  top: 14px;
  left: 14px;
  display: grid;
  gap: 8px;
}

.map-toolbar button {
  width: 38px;
  height: 38px;
  border: 1px solid rgba(18, 33, 52, 0.18);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.88);
  color: #15304a;
  cursor: pointer;
  font-size: 1.35rem;
}

.map-north {
  position: absolute;
  top: 18px;
  right: 22px;
  z-index: 3;
  color: #122337;
  font-size: 2.5rem;
  font-family: "Times New Roman", serif;
}

.map-legend {
  top: 110px;
  right: 18px;
  display: grid;
  gap: 10px;
  min-width: 168px;
  padding: 16px;
  border: 1px solid rgba(21, 48, 74, 0.22);
  border-radius: 10px;
  background: rgba(20, 35, 55, 0.88);
  color: #f2fbff;
}

.map-legend strong {
  font-size: 1rem;
}

.legend-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: rgba(240, 248, 252, 0.9);
  font-size: 0.92rem;
}

.legend-line {
  display: inline-block;
  width: 18px;
  height: 4px;
  border-radius: 999px;
}

.legend-line--basin {
  border: 2px solid #ffffff;
  background: transparent;
  height: 12px;
}

.legend-line--river {
  background: #67b9ff;
}

.legend-point {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.legend-point--water {
  background: #375bff;
  border: 2px solid #ffffff;
}

.legend-point--rain {
  width: 0;
  height: 0;
  border-left: 7px solid transparent;
  border-right: 7px solid transparent;
  border-bottom: 13px solid #7fa43a;
}

.map-statusbar {
  left: 0;
  right: 0;
  bottom: 0;
  display: inline-flex;
  gap: 18px;
  align-items: center;
  padding: 10px 18px;
  background: rgba(21, 37, 58, 0.86);
  color: rgba(240, 248, 252, 0.92);
  font-size: 0.94rem;
}

@media (max-width: 860px) {
  .workspace-preview {
    min-height: auto;
  }

  .workspace-preview__canvas-wrap {
    min-height: 560px;
  }

  .map-legend {
    top: 92px;
  }

  .map-statusbar {
    gap: 10px;
    flex-wrap: wrap;
    font-size: 0.82rem;
  }
}
</style>
