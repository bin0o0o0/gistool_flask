<script setup lang="ts">
import 'ol/ol.css'

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ArrowDown, ArrowRight, Connection, Hide, View } from '@element-plus/icons-vue'
import type Feature from 'ol/Feature'
import type Geometry from 'ol/geom/Geometry'
import type { FeatureLike } from 'ol/Feature'
import OLMap from 'ol/Map'
import ViewOL from 'ol/View'
import type { Extent } from 'ol/extent'
import { createEmpty, extend as extendExtent, isEmpty } from 'ol/extent'
import GeoJSON from 'ol/format/GeoJSON'
import { defaults as defaultInteractions } from 'ol/interaction'
import TileLayer from 'ol/layer/Tile'
import VectorLayer from 'ol/layer/Vector'
import { fromLonLat, toLonLat } from 'ol/proj'
import OSM from 'ol/source/OSM'
import VectorSource from 'ol/source/Vector'
import { Circle as CircleStyle, Fill, Stroke, Style } from 'ol/style'

import type { BreakPoint, GeoJsonFeatureCollection, WatershedOutputs } from '@/types'
import {
  buildActivePreviewStateFromSteps,
  emptyFeatureCollection,
  getHoverSummary,
  type ActivePreviewState,
  type PreviewLayerGroup,
  type PreviewLayerItem,
  type PreviewLayerKey
} from '@/utils/watershedMap'

const props = defineProps<{
  step1Outputs: WatershedOutputs | null
  step2Outputs: WatershedOutputs | null
  boundaryPreview: GeoJsonFeatureCollection | null
  step0Boundary: GeoJsonFeatureCollection | null
  step0Streams: GeoJsonFeatureCollection | null
  manualBreakPoints: BreakPoint[]
  interactiveBreakPointMode: boolean
}>()

const emit = defineEmits<{
  (event: 'add-break-point', coordinates: [number, number]): void
}>()

const mapElement = ref<HTMLElement | null>(null)
const format = new GeoJSON()
const defaultCenter = fromLonLat([105.6, 27.2])
const selectedItemId = ref<string | null>(null)
const hoveredItemId = ref<string | null>(null)
const hoverCard = ref<{ item: PreviewLayerItem; x: number; y: number } | null>(null)

const visibility = reactive<Record<PreviewLayerKey, boolean>>({
  boundary: true,
  reaches: true,
  junctions: true,
  breakPoints: true
})

const expandedGroups = reactive<Record<PreviewLayerKey, boolean>>({
  boundary: true,
  reaches: true,
  junctions: true,
  breakPoints: true
})

const activePreviewState = computed<ActivePreviewState>(() =>
  buildActivePreviewStateFromSteps({
    step2Outputs: props.step2Outputs,
    step1Outputs: props.step1Outputs,
    boundaryPreview: props.boundaryPreview,
    step0Boundary: props.step0Boundary,
    step0Streams: props.step0Streams,
    manualBreakPoints: props.manualBreakPoints
  })
)

const groups = computed(() => activePreviewState.value.groups)

const itemsById = computed(() => {
  const map = new globalThis.Map<string, PreviewLayerItem>()
  for (const group of groups.value) {
    for (const item of group.items) map.set(item.id, item)
  }
  return map
})

const selectedItem = computed(() => (selectedItemId.value ? itemsById.value.get(selectedItemId.value) || null : null))

const vectorSources: Record<PreviewLayerKey, VectorSource<Feature<Geometry>>> = {
  boundary: new VectorSource(),
  reaches: new VectorSource(),
  junctions: new VectorSource(),
  breakPoints: new VectorSource()
}

const featureRegistry = new Map<string, Feature<Geometry>>()

function layerStyle(layerKey: PreviewLayerKey) {
  return (featureLike: FeatureLike) => {
    const feature = featureLike as Feature<Geometry>
    const itemId = String(feature.get('__previewItemId') || '')
    const isSelected = selectedItemId.value === itemId
    const isHovered = hoveredItemId.value === itemId
    const emphasis = isSelected || isHovered

    if (layerKey === 'boundary') {
      return new Style({
        stroke: new Stroke({
          color: emphasis ? '#ffe08c' : '#ff5d5d',
          width: emphasis ? 3 : 2
        }),
        fill: new Fill({
          color: emphasis ? 'rgba(255, 214, 102, 0.18)' : 'rgba(91, 190, 255, 0.10)'
        })
      })
    }

    if (layerKey === 'reaches') {
      return new Style({
        stroke: new Stroke({
          color: emphasis ? '#ffe08c' : '#39d6ff',
          width: emphasis ? 3.2 : 2.4
        })
      })
    }

    return new Style({
      image: new CircleStyle({
        radius: emphasis ? 8 : layerKey === 'junctions' ? 5 : 7,
        fill: new Fill({
          color: layerKey === 'junctions' ? '#d7f7ff' : '#ffd27a'
        }),
        stroke: new Stroke({
          color: emphasis ? '#ffffff' : '#0e1d2b',
          width: emphasis ? 2.4 : 1.8
        })
      })
    })
  }
}

const vectorLayers: Record<PreviewLayerKey, VectorLayer<VectorSource<Feature<Geometry>>>> = {
  boundary: new VectorLayer({ source: vectorSources.boundary, style: layerStyle('boundary') }),
  reaches: new VectorLayer({ source: vectorSources.reaches, style: layerStyle('reaches') }),
  junctions: new VectorLayer({ source: vectorSources.junctions, style: layerStyle('junctions') }),
  breakPoints: new VectorLayer({ source: vectorSources.breakPoints, style: layerStyle('breakPoints') })
}

let olMap: OLMap | null = null

function setLayerFeatures(layerKey: PreviewLayerKey, collection: GeoJsonFeatureCollection | null, group: PreviewLayerGroup | undefined) {
  const source = vectorSources[layerKey]
  source.clear(true)

  if (!collection || !group) return

  const features = format.readFeatures(collection, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857'
  }) as Feature<Geometry>[]

  features.forEach((feature, index) => {
    const item = group.items[index]
    if (!item) return
    feature.set('__previewItemId', item.id)
    feature.set('__previewLayerKey', layerKey)
    feature.set('__previewLabel', item.label)
    feature.set('__previewShortType', item.shortType)
    featureRegistry.set(item.id, feature)
  })

  if (features.length > 0) source.addFeatures(features)
}

function clearFeatureRegistry() {
  featureRegistry.clear()
}

function fitFeature(itemId: string) {
  if (!olMap) return
  const feature = featureRegistry.get(itemId)
  const geometry = feature?.getGeometry()
  if (!geometry) return
  olMap.getView().fit(geometry.getExtent(), {
    padding: [56, 280, 56, 56],
    duration: 260,
    maxZoom: 15
  })
}

function fitToVisibleLayers() {
  if (!olMap) return

  const extent: Extent = createEmpty()
  for (const key of Object.keys(vectorSources) as PreviewLayerKey[]) {
    if (!visibility[key]) continue
    const source = vectorSources[key]
    if (source.getFeatures().length === 0) continue
    const sourceExtent = source.getExtent()
    if (sourceExtent) extendExtent(extent, sourceExtent)
  }

  if (isEmpty(extent)) {
    olMap.getView().setCenter(defaultCenter)
    olMap.getView().setZoom(8)
    return
  }

  olMap.getView().fit(extent, { padding: [42, 260, 42, 42], duration: 320, maxZoom: 14 })
}

function refreshVectorLayers() {
  clearFeatureRegistry()
  const empty = emptyFeatureCollection()
  const groupMap = new globalThis.Map(groups.value.map((group) => [group.key, group] as const))

  setLayerFeatures('boundary', groupMap.get('boundary')?.collection || empty, groupMap.get('boundary'))
  setLayerFeatures('reaches', groupMap.get('reaches')?.collection || empty, groupMap.get('reaches'))
  setLayerFeatures('junctions', groupMap.get('junctions')?.collection || empty, groupMap.get('junctions'))
  setLayerFeatures('breakPoints', groupMap.get('breakPoints')?.collection || empty, groupMap.get('breakPoints'))

  applyVisibility()
  if (selectedItemId.value && !featureRegistry.has(selectedItemId.value)) {
    selectedItemId.value = null
  }
  fitToVisibleLayers()
  refreshLayerStyles()
}

function refreshLayerStyles() {
  for (const layer of Object.values(vectorLayers)) layer.changed()
}

function applyVisibility() {
  for (const key of Object.keys(vectorLayers) as PreviewLayerKey[]) {
    vectorLayers[key].setVisible(visibility[key])
  }
}

function selectItem(itemId: string, shouldFit: boolean) {
  selectedItemId.value = itemId
  refreshLayerStyles()
  if (shouldFit) fitFeature(itemId)
}

function clearHoverCard() {
  hoveredItemId.value = null
  hoverCard.value = null
  refreshLayerStyles()
}

function updateHoverCard(itemId: string, pixel: [number, number]) {
  const item = itemsById.value.get(itemId)
  if (!item || !['boundary', 'reaches'].includes(item.layerKey)) {
    clearHoverCard()
    return
  }

  hoveredItemId.value = itemId
  hoverCard.value = {
    item,
    x: pixel[0] + 18,
    y: pixel[1] + 18
  }
  refreshLayerStyles()
}

function hitPreviewFeature(pixel: [number, number]) {
  if (!olMap) return null
  let matched: Feature<Geometry> | null = null
  olMap.forEachFeatureAtPixel(pixel, (feature) => {
    matched = feature as Feature<Geometry>
    return true
  })
  return matched
}

function initializeMap() {
  if (!mapElement.value) return

  olMap = new OLMap({
    target: mapElement.value,
    layers: [
      new TileLayer({ source: new OSM() }),
      vectorLayers.boundary,
      vectorLayers.reaches,
      vectorLayers.junctions,
      vectorLayers.breakPoints
    ],
    interactions: defaultInteractions(),
    view: new ViewOL({
      center: defaultCenter,
      zoom: 8
    })
  })

  olMap.on('pointermove', (event) => {
    if (!olMap) return
    const feature = hitPreviewFeature(event.pixel as [number, number]) as Feature<Geometry> | null
    if (!feature) {
      clearHoverCard()
      if (mapElement.value) mapElement.value.style.cursor = props.interactiveBreakPointMode ? 'crosshair' : 'grab'
      return
    }

    const itemId = String(feature.get('__previewItemId') || '')
    updateHoverCard(itemId, event.pixel as [number, number])
    if (mapElement.value) mapElement.value.style.cursor = 'pointer'
  })

  olMap.on('singleclick', (event) => {
    const feature = hitPreviewFeature(event.pixel as [number, number]) as Feature<Geometry> | null
    if (feature) {
      const itemId = String(feature.get('__previewItemId') || '')
      if (itemId) selectItem(itemId, false)
      return
    }

    if (props.interactiveBreakPointMode) {
      const [lng, lat] = toLonLat(event.coordinate)
      emit('add-break-point', [Number(lng.toFixed(6)), Number(lat.toFixed(6))])
    }
  })

  refreshVectorLayers()
}

function toggleGroup(key: PreviewLayerKey) {
  expandedGroups[key] = !expandedGroups[key]
}

function toggleVisibility(key: PreviewLayerKey) {
  visibility[key] = !visibility[key]
  applyVisibility()
}

onMounted(() => {
  initializeMap()
})

onBeforeUnmount(() => {
  if (olMap) {
    olMap.setTarget(undefined)
    olMap = null
  }
})

watch(groups, () => {
  refreshVectorLayers()
}, { deep: true })

watch(
  () => props.interactiveBreakPointMode,
  (enabled) => {
    if (mapElement.value) mapElement.value.style.cursor = enabled ? 'crosshair' : 'grab'
  },
  { immediate: true }
)
</script>

<template>
  <section class="preview-map">
    <div ref="mapElement" class="preview-map__canvas"></div>

    <div class="preview-map__legend">
      <div class="preview-map__legend-head">
        <Connection />
        <span>图层</span>
      </div>

      <section v-for="group in groups" :key="group.key" class="tree-group">
        <div class="tree-group__head">
          <button class="tree-group__collapse" type="button" @click="toggleGroup(group.key)">
            <el-icon><ArrowDown v-if="expandedGroups[group.key]" /><ArrowRight v-else /></el-icon>
            <span>{{ group.label }}</span>
            <small>{{ group.items.length }}</small>
          </button>

          <button class="tree-group__visibility" type="button" @click="toggleVisibility(group.key)">
            <el-icon><View v-if="visibility[group.key]" /><Hide v-else /></el-icon>
          </button>
        </div>

        <div v-show="expandedGroups[group.key]" class="tree-group__items">
          <button
            v-for="item in group.items"
            :key="item.id"
            class="tree-group__item"
            :class="{ selected: selectedItemId === item.id }"
            type="button"
            @click="selectItem(item.id, true)"
          >
            <span class="tree-group__swatch" :data-kind="group.key"></span>
            <span class="tree-group__label">{{ item.label }}</span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="hoverCard"
      class="preview-map__hover-card"
      :style="{ left: `${hoverCard.x}px`, top: `${hoverCard.y}px` }"
    >
      <div class="preview-map__hover-type">{{ getHoverSummary(hoverCard.item).type }}</div>
      <strong>{{ getHoverSummary(hoverCard.item).title }}</strong>
      <small>ID: {{ getHoverSummary(hoverCard.item).id }}</small>
    </div>
  </section>
</template>

<style scoped>
.preview-map {
  position: relative;
  min-height: 680px;
  overflow: hidden;
  border: 1px solid rgba(168, 247, 255, 0.2);
  border-radius: 8px;
  background: rgba(2, 12, 25, 0.72);
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.34);
}

.preview-map__canvas {
  position: absolute;
  inset: 0;
}

.preview-map :deep(.ol-viewport) {
  background: #081524;
}

.preview-map :deep(.ol-control button) {
  border-radius: 6px;
  background: rgba(4, 26, 45, 0.88);
}

.preview-map__legend,
.preview-map__hover-card {
  position: absolute;
  z-index: 3;
  border: 1px solid rgba(168, 247, 255, 0.18);
  border-radius: 8px;
  background: rgba(2, 12, 25, 0.84);
  backdrop-filter: blur(16px);
}

.preview-map__legend {
  top: 14px;
  right: 14px;
  display: grid;
  gap: 10px;
  width: 228px;
  max-height: calc(100% - 28px);
  padding: 10px;
  overflow: auto;
}

.preview-map__legend-head {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #dffcff;
  font-size: 0.84rem;
  font-weight: 800;
  padding-bottom: 2px;
}

.preview-map__legend-head :deep(svg),
.tree-group__head :deep(svg) {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
}

.tree-group {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid rgba(168, 247, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
}

.tree-group__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tree-group__collapse,
.tree-group__visibility,
.tree-group__item {
  border: 0;
  border-radius: 7px;
  cursor: pointer;
}

.tree-group__collapse {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 0;
  background: transparent;
  color: #f4fcff;
}

.tree-group__collapse small {
  color: rgba(244, 252, 255, 0.52);
  font-size: 0.72rem;
}

.tree-group__visibility {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  background: rgba(130, 255, 240, 0.08);
  color: #dffcff;
}

.tree-group__items {
  display: grid;
  gap: 6px;
  max-height: 220px;
  overflow: auto;
}

.tree-group__item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
  padding: 8px 9px;
  background: rgba(255, 255, 255, 0.03);
  color: rgba(244, 252, 255, 0.8);
  text-align: left;
}

.tree-group__item.selected {
  background: rgba(255, 214, 102, 0.14);
  color: #fff2c7;
  box-shadow: inset 0 0 0 1px rgba(255, 214, 102, 0.24);
}

.tree-group__swatch {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  flex: 0 0 10px;
}

.tree-group__swatch[data-kind='boundary'] {
  background: #ff5d5d;
}

.tree-group__swatch[data-kind='reaches'] {
  background: #39d6ff;
}

.tree-group__swatch[data-kind='junctions'] {
  background: #d7f7ff;
}

.tree-group__swatch[data-kind='breakPoints'] {
  background: #ffd27a;
}

.tree-group__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-map__hover-card {
  min-width: 190px;
  max-width: 240px;
  padding: 12px 14px;
  pointer-events: none;
}

.preview-map__hover-card strong {
  display: block;
  margin-top: 5px;
  font-size: 1.02rem;
}

.preview-map__hover-card small {
  display: inline-block;
  margin-top: 8px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(244, 252, 255, 0.72);
}

.preview-map__hover-type {
  color: #9aa7ff;
  font-size: 0.76rem;
  font-weight: 800;
}

@media (max-width: 860px) {
  .preview-map {
    min-height: 520px;
  }

  .preview-map__legend {
    width: 206px;
  }
}
</style>
