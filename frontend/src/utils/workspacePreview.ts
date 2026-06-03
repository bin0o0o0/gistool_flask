import { collectLegendNameOverrides } from '@/utils/legendNameOverrides'
import type {
  BasinLayerForm,
  GeoJsonFeatureCollection,
  LayoutBoxForm,
  RiverLayerForm,
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
const FALLBACK_LAYOUT_WIDTH_UNITS = 270
const FALLBACK_LAYOUT_HEIGHT_UNITS = 200
const MILLIMETERS_PER_INCH = 25.4

export function buildWorkspacePreviewData(form: WorkspaceForm): WorkspacePreviewData {
  const stationCoordinates = collectStationCoordinates(form.inputs.station_layers)
  const center = stationCoordinates[0] || DEFAULT_CENTER

  const basinFeatures =
    form.inputs.basin_boundaries.length > 0
      ? form.inputs.basin_boundaries.flatMap((layer, index) =>
          layer.preview?.features?.length ? previewFeatures(layer.preview, layer.name, basinPreviewStyle(layer)) : [createBasinFeature(layer, center, index)]
        )
      : []

  const riverFeatures =
    form.inputs.river_networks.length > 0
      ? form.inputs.river_networks.flatMap((layer, index) =>
          layer.preview?.features?.length ? previewFeatures(layer.preview, layer.name, riverPreviewStyle(layer)) : [createRiverFeature(layer, center, index)]
        )
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

function previewFeatures(collection: GeoJsonFeatureCollection, layerName: string, previewStyle: Record<string, unknown>) {
  return collection.features.map((feature) => ({
    ...feature,
    properties: {
      ...(feature.properties || {}),
      name: (feature.properties as Record<string, unknown> | undefined)?.name || layerName,
      previewStyle
    }
  }))
}

function basinPreviewStyle(layer: BasinLayerForm) {
  return {
    boundaryColor: layer.style.boundary_color,
    boundaryWidth: layer.style.boundary_width_pt,
    fillColor: layer.style.fill_color,
    fillOpacity: layer.style.fill_opacity
  }
}

function riverPreviewStyle(layer: RiverLayerForm) {
  return {
    color: layer.style.color,
    width: layer.style.width_pt
  }
}

function percent(value: number) {
  return `${((value * 100) / 1).toFixed(2)}%`
}

function layoutPageUnits(form: WorkspaceForm) {
  const dpi = Number(form.output.dpi)
  const widthPx = Number(form.output.width_px)
  const heightPx = Number(form.output.height_px)
  if (dpi > 0 && widthPx > 0 && heightPx > 0) {
    return {
      width: (widthPx / dpi) * MILLIMETERS_PER_INCH,
      height: (heightPx / dpi) * MILLIMETERS_PER_INCH
    }
  }
  return {
    width: FALLBACK_LAYOUT_WIDTH_UNITS,
    height: FALLBACK_LAYOUT_HEIGHT_UNITS
  }
}

function boxStyle(box: LayoutBoxForm, pageUnits: { width: number; height: number }) {
  return {
    left: percent(box.x / pageUnits.width),
    bottom: percent(box.y / pageUnits.height),
    width: percent(box.width / pageUnits.width),
    height: percent(box.height / pageUnits.height)
  }
}

function buildLayoutPreview(form: WorkspaceForm): WorkspaceLayoutPreview {
  const elements = form.layout.elements
  const legendStyle = form.layout.legend_style
  const pageUnits = layoutPageUnits(form)

  return {
    paperStyle: {
      aspectRatio: `${form.output.width_px} / ${form.output.height_px}`
    },
    mapFrame: {
      style: boxStyle(elements.map_frame, pageUnits)
    },
    title: elements.title.enabled
      ? {
          style: boxStyle(elements.title, pageUnits),
          text: form.map_title,
          fontSizePx: elements.title.font_size,
          background: elements.title.background
        }
      : null,
    legend: elements.legend.enabled
      ? {
          style: boxStyle(elements.legend, pageUnits),
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
    scaleBar: elements.scale_bar.enabled ? { style: boxStyle(elements.scale_bar, pageUnits) } : null,
    northArrow: elements.north_arrow.enabled ? { style: boxStyle(elements.north_arrow, pageUnits) } : null
  }
}

function createBasinFeature(layer: BasinLayerForm, center: [number, number], index: number) {
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
      name: layer.name,
      previewStyle: basinPreviewStyle(layer)
    }
  }
}

function createRiverFeature(layer: RiverLayerForm, center: [number, number], index: number) {
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
      name: layer.name,
      previewStyle: riverPreviewStyle(layer)
    }
  }
}
