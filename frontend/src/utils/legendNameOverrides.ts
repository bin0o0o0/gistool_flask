import type {
  LegendNameOverrideForm,
  StationLabelForm,
  StationLayerForm,
  StationSymbolForm,
  WorkspaceForm
} from '@/types'

function stationStyleKey(symbol: StationSymbolForm, label: StationLabelForm) {
  return JSON.stringify({ symbol, label })
}

function preservedLegendName(
  existingOverrides: LegendNameOverrideForm[],
  sourceKey: string,
  defaultName: string
) {
  const matched = existingOverrides.find((item) => item.source_key === sourceKey)
  return matched?.legend_name?.trim() || defaultName
}

function stationLegendSources(
  layer: StationLayerForm,
  layerIndex: number,
  existingOverrides: LegendNameOverrideForm[]
) {
  const baseName = layer.layer_name || `StationLayer${layerIndex + 1}`
  if (!layer.points.length) {
    const source_key = `station-layer-${layerIndex + 1}`
    return [
      {
        source_type: 'station_layer' as const,
        source_key,
        default_name: baseName,
        legend_name: preservedLegendName(existingOverrides, source_key, baseName)
      }
    ]
  }

  const groups = new Map<string, number>()
  const sources: LegendNameOverrideForm[] = []
  layer.points.forEach((point) => {
    const key = stationStyleKey(point.symbol, point.label)
    if (groups.has(key)) return
    const groupIndex = groups.size + 1
    groups.set(key, groupIndex)
    const default_name = `${baseName} - ${groupIndex}`
    const source_key = `station-layer-${layerIndex + 1}-group-${groupIndex}`
    sources.push({
      source_type: 'station_group',
      source_key,
      default_name,
      legend_name: preservedLegendName(existingOverrides, source_key, default_name)
    })
  })
  return sources
}

export function collectLegendNameOverrides(form: WorkspaceForm): LegendNameOverrideForm[] {
  const existingOverrides = form.layout.legend_style.name_overrides || []

  const basinOverrides = form.inputs.basin_boundaries.map((layer, index) => {
    const default_name = layer.name || `Basin ${index + 1}`
    const source_key = `basin-layer-${index + 1}`
    return {
      source_type: 'basin' as const,
      source_key,
      default_name,
      legend_name: preservedLegendName(existingOverrides, source_key, default_name)
    }
  })

  const riverOverrides = form.inputs.river_networks.map((layer, index) => {
    const default_name = layer.name || `River ${index + 1}`
    const source_key = `river-layer-${index + 1}`
    return {
      source_type: 'river' as const,
      source_key,
      default_name,
      legend_name: preservedLegendName(existingOverrides, source_key, default_name)
    }
  })

  const stationOverrides = form.inputs.station_layers.flatMap((layer, index) =>
    stationLegendSources(layer, index, existingOverrides)
  )

  return [...basinOverrides, ...riverOverrides, ...stationOverrides]
}
