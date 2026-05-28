import type { GeoJsonFeatureCollection, StationLayerForm, WorkspaceForm } from '@/types'

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

export interface WorkspacePreviewData {
  basinLayer: WorkspacePreviewLayer
  riverLayer: WorkspacePreviewLayer
  stationLayer: WorkspacePreviewLayer
  layoutCard: WorkspacePreviewLayoutCard
}

const DEFAULT_CENTER: [number, number] = [105.2, 27.06]

export function buildWorkspacePreviewData(form: WorkspaceForm): WorkspacePreviewData {
  const stationCoordinates = collectStationCoordinates(form.inputs.station_layers)
  const center = stationCoordinates[0] || DEFAULT_CENTER

  const basinFeatures =
    form.inputs.basin_boundaries.length > 0
      ? form.inputs.basin_boundaries.map((layer, index) => createBasinFeature(layer.name, center, index))
      : [createBasinFeature('Preview Basin', center, 0)]

  const riverFeatures =
    form.inputs.river_networks.length > 0
      ? form.inputs.river_networks.map((layer, index) => createRiverFeature(layer.name, center, index))
      : [createRiverFeature('Main River', center, 0), createRiverFeature('Tributary', center, 1)]

  const stationFeatures = stationCoordinates.map((coordinate, index) => ({
    type: 'Feature',
    geometry: {
      type: 'Point',
      coordinates: coordinate
    },
    properties: {
      layerName: form.inputs.station_layers[0]?.layer_name || 'StationLayer1',
      label: form.inputs.station_layers[0]?.points[index]?.display_name || `Station ${index + 1}`
    }
  }))

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
    }
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
