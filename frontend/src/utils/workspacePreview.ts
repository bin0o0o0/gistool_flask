import { collectLegendNameOverrides } from '@/utils/legendNameOverrides'
import type {
  GeoJsonFeatureCollection,
  LayoutBoxForm,
  StationLayerForm,
  StationPointForm,
  WorkspaceForm
} from '@/types'

export interface WorkspacePreviewLayer {
  features: Array<Record<string, unknown>>
}

export interface WorkspacePreviewLayoutCard {
  title: string
  paperLabel: string
  basemap: string
  legendEnabled: boolean
  northArrowEnabled: boolean
  scaleBarEnabled: boolean
}

export interface WorkspacePreviewBox {
  style: Record<string, string>
}

export interface WorkspacePreviewLegendRow {
  sourceType: string
  label: string
}

export interface WorkspacePreviewLegend extends WorkspacePreviewBox {
  rows: WorkspacePreviewLegendRow[]
  patchStyle: Record<string, string>
  rowGapPx: number
  background: boolean
}

export interface WorkspaceLayoutPreview {
  paperStyle: Record<string, string>
  mapFrame: WorkspacePreviewBox
  title: (WorkspacePreviewBox & { text: string; fontSizePx: number; background: boolean }) | null
  legend: WorkspacePreviewLegend | null
  scaleBar: WorkspacePreviewBox | null
  northArrow: WorkspacePreviewBox | null
}

export interface WorkspacePreviewData {
  basinLayer: WorkspacePreviewLayer
  riverLayer: WorkspacePreviewLayer
  stationLayer: WorkspacePreviewLayer
  layoutCard: WorkspacePreviewLayoutCard
  layoutPreview: WorkspaceLayoutPreview
}

const DEFAULT_CENTER: [number, number] = [105.2, 27.06]
const LAYOUT_WIDTH_UNITS = 270
const LAYOUT_HEIGHT_UNITS = 200

export function buildWorkspacePreviewData(form: WorkspaceForm): WorkspacePreviewData {
  const stationCoordinates = collectStationCoordinates(form.inputs.station_layers)
  const center = stationCoordinates[0] || DEFAULT_CENTER

  const basinFeatures =
    form.inputs.basin_boundaries.length > 0
      ? form.inputs.basin_boundaries.map((layer, index) => createBasinFeature(layer.name, center, index))
      : []

  const riverFeatures =
    form.inputs.river_networks.length > 0
      ? form.inputs.river_networks.map((layer, index) => createRiverFeature(layer.name, center, index))
      : []

  const stationFeatures = createStationFeatures(form.inputs.station_layers)

  return {
    basinLayer: {
      features: basinFeatures
    },
    riverLayer: {
      features: riverFeatures
    },
    stationLayer: {
      features: stationFeatures
    },
    layoutCard: {
      title: form.map_title || '流域专题图',
      paperLabel: `${form.output.width_px} x ${form.output.height_px} / ${form.output.dpi} DPI`,
      basemap: form.layout.basemap,
      legendEnabled: form.layout.elements.legend.enabled,
      northArrowEnabled: form.layout.elements.north_arrow.enabled,
      scaleBarEnabled: form.layout.elements.scale_bar.enabled
    },
    layoutPreview: buildLayoutPreview(form)
  }
}

export function toFeatureCollection(layer: WorkspacePreviewLayer): GeoJsonFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: layer.features
  }
}

function collectStationCoordinates(layers: StationLayerForm[]): Array<[number, number]> {
  return layers.flatMap((layer) =>
    layer.points
      .map((point) => {
        const lon = Number(point.values[layer.x_field])
        const lat = Number(point.values[layer.y_field])
        if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null
        return [lon, lat] as [number, number]
      })
      .filter((value): value is [number, number] => Array.isArray(value))
  )
}

function createStationFeatures(layers: StationLayerForm[]) {
  const features: Record<string, unknown>[] = []
  layers.forEach((layer) => {
    layer.points.forEach((point: StationPointForm, pointIndex) => {
      const lon = Number(point.values[layer.x_field])
      const lat = Number(point.values[layer.y_field])
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) return
      features.push({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [lon, lat]
        },
        properties: {
          layerName: layer.layer_name || 'StationLayer1',
          label: point.display_name || `Station ${pointIndex + 1}`,
          symbol: point.symbol || layer.symbol,
          text: point.label || layer.label
        }
      })
    })
  })
  return features
}

function percent(value: number) {
  return `${((value * 100) / 1).toFixed(2)}%`
}

function boxStyle(box: LayoutBoxForm) {
  return {
    left: percent(box.x / LAYOUT_WIDTH_UNITS),
    bottom: percent(box.y / LAYOUT_HEIGHT_UNITS),
    width: percent(box.width / LAYOUT_WIDTH_UNITS),
    height: percent(box.height / LAYOUT_HEIGHT_UNITS)
  }
}

function buildLayoutPreview(form: WorkspaceForm): WorkspaceLayoutPreview {
  const elements = form.layout.elements
  const legendStyle = form.layout.legend_style

  return {
    paperStyle: {
      aspectRatio: `${form.output.width_px} / ${form.output.height_px}`
    },
    mapFrame: {
      style: boxStyle(elements.map_frame)
    },
    title: elements.title.enabled
      ? {
          style: boxStyle(elements.title),
          text: form.map_title,
          fontSizePx: elements.title.font_size,
          background: elements.title.background
        }
      : null,
    legend: elements.legend.enabled
      ? {
          style: boxStyle(elements.legend),
          rows: collectLegendNameOverrides(form).map((row) => ({
            sourceType: row.source_type,
            label: row.legend_name
          })),
          patchStyle: {
            width: `${legendStyle.patch_width}px`,
            height: `${legendStyle.patch_height}px`,
            marginRight: `${legendStyle.text_gap}px`
          },
          rowGapPx: legendStyle.item_gap,
          background: elements.legend.background
        }
      : null,
    scaleBar: elements.scale_bar.enabled ? { style: boxStyle(elements.scale_bar) } : null,
    northArrow: elements.north_arrow.enabled ? { style: boxStyle(elements.north_arrow) } : null
  }
}

function createBasinFeature(name: string, center: [number, number], index: number) {
  const shift = index * 0.12
  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [[
        [center[0] - 0.24 + shift, center[1] + 0.18 - shift * 0.18],
        [center[0] + 0.3 + shift * 0.1, center[1] + 0.14],
        [center[0] + 0.26 + shift * 0.08, center[1] - 0.18],
        [center[0] - 0.2 + shift * 0.1, center[1] - 0.24],
        [center[0] - 0.28 + shift * 0.04, center[1] - 0.02],
        [center[0] - 0.24 + shift, center[1] + 0.18 - shift * 0.18]
      ]]
    },
    properties: {
      name
    }
  }
}

function createRiverFeature(name: string, center: [number, number], index: number) {
  const offset = index * 0.08
  return {
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates: [
        [center[0] - 0.22 + offset, center[1] + 0.2 - offset * 0.25],
        [center[0] - 0.08 + offset * 0.4, center[1] + 0.08],
        [center[0] + 0.04 + offset * 0.3, center[1] - 0.02],
        [center[0] + 0.18 + offset * 0.2, center[1] - 0.18]
      ]
    },
    properties: {
      name
    }
  }
}
