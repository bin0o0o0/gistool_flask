import type {
  LegendNameOverrideForm,
  StationLayerForm,
  WorkspaceForm
} from '@/types'

function preservedLegendName(
  existingOverrides: LegendNameOverrideForm[],
  sourceKey: string,
  defaultName: string
) {
  const matched = existingOverrides.find((item) => item.source_key === sourceKey)
  return matched?.legend_name?.trim() || defaultName
}

function isLegendHidden(existingOverrides: LegendNameOverrideForm[], sourceKey: string) {
  const matched = existingOverrides.find((item) => item.source_key === sourceKey)
  return matched?.legend_visible === false
}

function stationLegendSources(
  layer: StationLayerForm,
  layerIndex: number,
  existingOverrides: LegendNameOverrideForm[]
) {
  const baseName = layer.layer_name || `StationLayer${layerIndex + 1}`
  if (!layer.points.length) {
    return []
  }

  return layer.points.map((point, pointIndex) => {
    const fallbackName = point.display_name || point.raw_name || `${baseName} - ${pointIndex + 1}`
    const default_name = fallbackName
    const source_key = `station-layer-${layerIndex + 1}-point-${point.row_number}`
    const hidden = isLegendHidden(existingOverrides, source_key)
    return {
      source_type: 'station_group' as const,
      source_key,
      default_name,
      legend_name: preservedLegendName(existingOverrides, source_key, default_name),
      symbol: { ...point.symbol },
      ...(hidden ? { legend_visible: false } : {})
    }
  })
}

export function collectLegendNameOverrides(
  form: WorkspaceForm,
  options: { includeHidden?: boolean } = {}
): LegendNameOverrideForm[] {
  const existingOverrides = form.layout.legend_style.name_overrides || []
  const includeHidden = options.includeHidden === true

  const basinOverrides = form.inputs.basin_boundaries.map((layer, index) => {
    const default_name = layer.name || `Basin ${index + 1}`
    const source_key = `basin-layer-${index + 1}`
    return {
      source_type: 'basin' as const,
      source_key,
      default_name,
      legend_name: preservedLegendName(existingOverrides, source_key, default_name),
      ...(isLegendHidden(existingOverrides, source_key) ? { legend_visible: false } : {})
    }
  }).filter((row) => includeHidden || row.legend_visible !== false)

  const riverOverrides = form.inputs.river_networks.map((layer, index) => {
    const default_name = layer.name || `River ${index + 1}`
    const source_key = `river-layer-${index + 1}`
    return {
      source_type: 'river' as const,
      source_key,
      default_name,
      legend_name: preservedLegendName(existingOverrides, source_key, default_name),
      ...(isLegendHidden(existingOverrides, source_key) ? { legend_visible: false } : {})
    }
  }).filter((row) => includeHidden || row.legend_visible !== false)

  const stationOverrides = form.inputs.station_layers.flatMap((layer, index) =>
    stationLegendSources(layer, index, existingOverrides)
  )

  return [...basinOverrides, ...riverOverrides, ...stationOverrides]
}
