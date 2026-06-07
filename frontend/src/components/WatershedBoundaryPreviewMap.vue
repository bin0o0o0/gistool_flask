<script setup lang="ts">
import 'ol/ol.css'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type Feature from 'ol/Feature'
import type Geometry from 'ol/geom/Geometry'
import OLMap from 'ol/Map'
import View from 'ol/View'
import { createEmpty, extend as extendExtent, isEmpty } from 'ol/extent'
import GeoJSON from 'ol/format/GeoJSON'
import TileLayer from 'ol/layer/Tile'
import VectorLayer from 'ol/layer/Vector'
import { fromLonLat, toLonLat } from 'ol/proj'
import OSM from 'ol/source/OSM'
import VectorSource from 'ol/source/Vector'
import { Circle as CircleStyle, Fill, Stroke, Style } from 'ol/style'

import type { GeoJsonFeatureCollection, WatershedBoundaryBbox, WatershedBoundaryPoint } from '@/types'
import { formatLonLatDisplay } from '@/utils/mapCoordinate'

const props = defineProps<{
  point: WatershedBoundaryPoint
  bbox: WatershedBoundaryBbox
  result: GeoJsonFeatureCollection | null
}>()

const mapElement = ref<HTMLElement | null>(null)
const pointerCoordinateText = ref('移动鼠标查看经纬度')
const format = new GeoJSON()
const defaultCenter = fromLonLat([105.2, 27.06])

const previewCollection = computed<GeoJsonFeatureCollection>(() => ({
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [props.bbox.min_x, props.bbox.max_y],
          [props.bbox.max_x, props.bbox.max_y],
          [props.bbox.max_x, props.bbox.min_y],
          [props.bbox.min_x, props.bbox.min_y],
          [props.bbox.min_x, props.bbox.max_y]
        ]]
      },
      properties: { role: 'bbox' }
    },
    {
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [props.point.x, props.point.y]
      },
      properties: { role: 'point' }
    }
  ]
}))

const previewSource = new VectorSource<Feature<Geometry>>()
const resultSource = new VectorSource<Feature<Geometry>>()

const previewLayer = new VectorLayer({
  source: previewSource,
  style: (feature) => {
    const role = String(feature.get('role') || feature.get('properties')?.role || '')
    if (role === 'point') {
      return new Style({
        image: new CircleStyle({
          radius: 7,
          fill: new Fill({ color: '#ffd27a' }),
          stroke: new Stroke({ color: '#082033', width: 2 })
        })
      })
    }
    return new Style({
      stroke: new Stroke({
        color: '#88eaff',
        width: 2,
        lineDash: [8, 6]
      }),
      fill: new Fill({
        color: 'rgba(136, 234, 255, 0.08)'
      })
    })
  }
})

const resultLayer = new VectorLayer({
  source: resultSource,
  style: new Style({
    stroke: new Stroke({
      color: '#3affe0',
      width: 2.8
    }),
    fill: new Fill({
      color: 'rgba(58, 255, 224, 0.16)'
    })
  })
})

let map: OLMap | null = null

function updatePointerCoordinate(coordinate: number[]) {
  const [lon, lat] = toLonLat(coordinate)
  pointerCoordinateText.value = formatLonLatDisplay([lon, lat])
}

function resetPointerCoordinate() {
  pointerCoordinateText.value = '移动鼠标查看经纬度'
}

function refreshSources() {
  previewSource.clear(true)
  resultSource.clear(true)

  const previewFeatures = format.readFeatures(previewCollection.value, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857'
  }) as Feature<Geometry>[]
  previewFeatures.forEach((feature, index) => {
    feature.set('role', index === 0 ? 'bbox' : 'point')
  })
  previewSource.addFeatures(previewFeatures)

  if (props.result) {
    const resultFeatures = format.readFeatures(props.result, {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857'
    }) as Feature<Geometry>[]
    resultSource.addFeatures(resultFeatures)
  }

  fitLayers()
}

function fitLayers() {
  if (!map) return
  const extent = createEmpty()
  const previewExtent = previewSource.getExtent()
  const resultExtent = resultSource.getExtent()
  if (previewSource.getFeatures().length && previewExtent) extendExtent(extent, previewExtent)
  if (resultSource.getFeatures().length && resultExtent) extendExtent(extent, resultExtent)

  if (isEmpty(extent)) {
    map.getView().setCenter(defaultCenter)
    map.getView().setZoom(9)
    return
  }

  map.getView().fit(extent, {
    padding: [42, 42, 42, 42],
    duration: 240,
    maxZoom: 13
  })
}

onMounted(() => {
  if (!mapElement.value) return
  map = new OLMap({
    target: mapElement.value,
    layers: [
      new TileLayer({ source: new OSM() }),
      resultLayer,
      previewLayer
    ],
    view: new View({
      center: defaultCenter,
      zoom: 9
    })
  })
  map.on('pointermove', (event) => {
    updatePointerCoordinate(event.coordinate)
  })
  mapElement.value.addEventListener('pointerleave', resetPointerCoordinate)
  refreshSources()
})

onBeforeUnmount(() => {
  mapElement.value?.removeEventListener('pointerleave', resetPointerCoordinate)
  if (map) {
    map.setTarget(undefined)
    map = null
  }
})

watch(
  () => [props.point, props.bbox, props.result],
  () => {
    refreshSources()
  },
  { deep: true }
)
</script>

<template>
  <section class="boundary-map">
    <div ref="mapElement" class="boundary-map__canvas"></div>

    <div class="boundary-map__legend">
      <div class="legend-row">
        <span class="legend-swatch legend-swatch--result"></span>
        <strong>流域边界结果</strong>
      </div>
      <div class="legend-row">
        <span class="legend-swatch legend-swatch--bbox"></span>
        <span>矩形范围</span>
      </div>
      <div class="legend-row">
        <span class="legend-swatch legend-swatch--point"></span>
        <span>目标点</span>
      </div>
    </div>

    <div class="boundary-map__coordinate">
      {{ pointerCoordinateText }}
    </div>
  </section>
</template>

<style scoped>
.boundary-map {
  position: relative;
  width: 100%;
  flex: 1 1 auto;
  min-height: 680px;
  overflow: hidden;
  border: 1px solid rgba(168, 247, 255, 0.2);
  border-radius: 8px;
  background: rgba(2, 12, 25, 0.72);
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.34);
}

.boundary-map__canvas {
  position: absolute;
  inset: 0;
}

.boundary-map :deep(.ol-viewport) {
  background: #081524;
}

.boundary-map :deep(.ol-control button) {
  border-radius: 6px;
  background: rgba(4, 26, 45, 0.88);
}

.boundary-map__legend {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 3;
  display: grid;
  gap: 10px;
  min-width: 190px;
  padding: 14px;
  border: 1px solid rgba(168, 247, 255, 0.18);
  border-radius: 8px;
  background: rgba(2, 12, 25, 0.84);
  backdrop-filter: blur(16px);
}

.legend-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: rgba(244, 252, 255, 0.84);
}

.legend-swatch {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 999px;
}

.legend-swatch--result {
  background: #3affe0;
}

.legend-swatch--bbox {
  border: 2px dashed #88eaff;
  border-radius: 3px;
  background: rgba(136, 234, 255, 0.12);
}

.legend-swatch--point {
  background: #ffd27a;
}

.boundary-map__coordinate {
  position: absolute;
  right: 16px;
  bottom: 14px;
  z-index: 3;
  max-width: calc(100% - 32px);
  padding: 9px 12px;
  border: 1px solid rgba(168, 247, 255, 0.2);
  border-radius: 8px;
  background: rgba(2, 12, 25, 0.82);
  color: rgba(244, 252, 255, 0.9);
  font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0;
  pointer-events: none;
  backdrop-filter: blur(14px);
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.24);
}

@media (max-width: 860px) {
  .boundary-map {
    min-height: 520px;
  }

  .boundary-map__coordinate {
    right: 10px;
    bottom: 10px;
    font-size: 0.72rem;
  }
}
</style>
