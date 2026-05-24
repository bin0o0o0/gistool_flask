<script setup lang="ts">
import 'ol/ol.css'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type Feature from 'ol/Feature'
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
import { Circle as CircleStyle, Fill, Stroke, Style } from 'ol/style'

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
  style: new Style({
    stroke: new Stroke({ color: '#2f75db', width: 2.4 }),
    fill: new Fill({ color: 'rgba(183, 220, 181, 0.28)' })
  })
})

const riverLayer = new VectorLayer({
  source: riverSource,
  style: new Style({
    stroke: new Stroke({ color: '#57a4f5', width: 1.8 })
  })
})

const stationLayer = new VectorLayer({
  source: stationSource,
  style: new Style({
    image: new CircleStyle({
      radius: 5,
      fill: new Fill({ color: '#375bff' }),
      stroke: new Stroke({ color: '#ffffff', width: 2 })
    })
  })
})

let map: OLMap | null = null

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
</script>

<template>
  <section class="workspace-preview">
    <button class="preview-badge" type="button">
      <span class="preview-badge__icon">◎</span>
      <span>地图预览</span>
    </button>

    <div class="workspace-preview__canvas-wrap">
      <div class="workspace-preview__fallback"></div>
      <div ref="mapElement" class="workspace-preview__canvas"></div>
      <svg class="preview-illustration" viewBox="0 0 1000 680" aria-hidden="true">
        <path
          d="M365 78 C445 62 514 86 573 138 C613 173 652 184 715 192 C806 204 842 274 822 348 C806 404 760 431 738 484 C712 547 650 582 570 586 C503 590 456 618 390 602 C324 586 297 540 247 520 C180 492 156 423 172 358 C184 302 170 250 199 198 C229 143 290 93 365 78 Z"
          fill="rgba(188, 214, 177, 0.42)"
          stroke="#2f75db"
          stroke-width="4"
        />
        <path d="M475 94 C470 182 484 244 516 318 C540 374 548 450 544 586" fill="none" stroke="#57a4f5" stroke-width="7" stroke-linecap="round" />
        <path d="M369 150 C412 218 458 280 522 336" fill="none" stroke="#5fb4ff" stroke-width="4" stroke-linecap="round" />
        <path d="M642 176 C610 244 562 300 522 336" fill="none" stroke="#5fb4ff" stroke-width="4" stroke-linecap="round" />
        <path d="M284 310 C364 332 425 340 522 336" fill="none" stroke="#5fb4ff" stroke-width="4" stroke-linecap="round" />
        <path d="M713 296 C646 318 592 326 522 336" fill="none" stroke="#5fb4ff" stroke-width="4" stroke-linecap="round" />
        <path d="M304 452 C394 424 466 390 522 336" fill="none" stroke="#5fb4ff" stroke-width="4" stroke-linecap="round" />
        <path d="M668 448 C606 410 560 378 522 336" fill="none" stroke="#5fb4ff" stroke-width="4" stroke-linecap="round" />
        <circle cx="446" cy="238" r="9" fill="#375bff" stroke="#fff" stroke-width="3" />
        <circle cx="517" cy="332" r="9" fill="#375bff" stroke="#fff" stroke-width="3" />
        <circle cx="409" cy="420" r="9" fill="#375bff" stroke="#fff" stroke-width="3" />
        <circle cx="562" cy="454" r="9" fill="#375bff" stroke="#fff" stroke-width="3" />
        <circle cx="488" cy="546" r="9" fill="#375bff" stroke="#fff" stroke-width="3" />
        <polygon points="430,132 444,158 416,158" fill="#7fa43a" stroke="#fff" stroke-width="2" />
        <polygon points="640,176 654,202 626,202" fill="#7fa43a" stroke="#fff" stroke-width="2" />
        <polygon points="716,328 730,354 702,354" fill="#7fa43a" stroke="#fff" stroke-width="2" />
        <polygon points="308,304 322,330 294,330" fill="#7fa43a" stroke="#fff" stroke-width="2" />
      </svg>

      <div class="map-toolbar">
        <button type="button" @click="zoomBy(1)">+</button>
        <button type="button" @click="zoomBy(-1)">−</button>
        <button type="button" @click="resetView()">⌂</button>
        <button type="button">◉</button>
        <button type="button">◫</button>
        <button type="button">▤</button>
      </div>

      <div class="map-north">N</div>

      <div class="map-legend">
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

      <div class="map-statusbar">
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

.preview-badge {
  position: absolute;
  top: -46px;
  right: 22px;
  z-index: 4;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 42px;
  padding: 0 18px;
  border: 1px solid rgba(130, 255, 240, 0.22);
  border-radius: 10px;
  background: rgba(13, 45, 68, 0.86);
  color: #dffcff;
  cursor: default;
  font-weight: 700;
}

.preview-badge__icon {
  color: #82fff0;
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

.workspace-preview__canvas {
  position: absolute;
  inset: 0;
}

.preview-illustration {
  position: absolute;
  inset: 0;
  z-index: 2;
  width: 100%;
  height: 100%;
  pointer-events: none;
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
    padding-top: 48px;
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
