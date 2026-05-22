import type { BreakPoint, GeoJsonFeatureCollection, WatershedOutputs } from '@/types'

export type PreviewLayerKey = 'boundary' | 'reaches' | 'junctions' | 'breakPoints'
export type PreviewSourceStage = 'upload' | 'step0' | 'step1' | 'step2'

export interface PreviewLayerItem {
  id: string
  label: string
  shortType: string
  layerKey: PreviewLayerKey
  featureIndex: number
  feature: Record<string, unknown>
}

export interface PreviewLayerGroup {
  key: PreviewLayerKey
  label: string
  shortType: string
  visible: boolean
  collection: GeoJsonFeatureCollection | null
  items: PreviewLayerItem[]
}

export interface ActivePreviewState {
  stage: PreviewSourceStage
  outputs: WatershedOutputs | null
  groups: PreviewLayerGroup[]
}

interface PreviewCollectionOptions {
  outputs: WatershedOutputs | null
  fallbackBreakPoints?: GeoJsonFeatureCollection | null
  boundaryPreview: GeoJsonFeatureCollection | null
  step0Boundary: GeoJsonFeatureCollection | null
  step0Streams: GeoJsonFeatureCollection | null
  manualBreakPoints: BreakPoint[]
}

function emptyFeatureCollection(): GeoJsonFeatureCollection {
  return { type: 'FeatureCollection', features: [] }
}

export { emptyFeatureCollection }

export function manualBreakPointsToCollection(points: BreakPoint[]): GeoJsonFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: points.map(([lon, lat, id]) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [lon, lat]
      },
      properties: { id }
    }))
  }
}

export function getPrimaryFeatureLabel(feature: Record<string, unknown>, fallback: string) {
  const properties = (feature.properties || {}) as Record<string, unknown>
  const candidate = properties.id ?? properties.name ?? properties.ID
  if (candidate != null && String(candidate).trim()) {
    return String(candidate).trim()
  }
  return fallback
}

function buildLayerItems(
  layerKey: PreviewLayerKey,
  shortType: string,
  labelPrefix: string,
  collection: GeoJsonFeatureCollection | null
): PreviewLayerItem[] {
  const features = collection?.features || []
  return features.map((feature, index) => {
    const fallback = `${labelPrefix}${index + 1}`
    const label = getPrimaryFeatureLabel(feature, fallback)
    return {
      id: `${layerKey}:${label}:${index}`,
      label,
      shortType,
      layerKey,
      featureIndex: index,
      feature
    }
  })
}

export function collectPreviewCollections({
  outputs,
  fallbackBreakPoints,
  boundaryPreview,
  step0Boundary,
  step0Streams,
  manualBreakPoints
}: PreviewCollectionOptions) {
  const manualBreakCollection = manualBreakPointsToCollection(manualBreakPoints)

  return {
    boundary: outputs?.subWatersheds || step0Boundary || boundaryPreview || null,
    reaches: outputs?.reaches || step0Streams || null,
    junctions: outputs?.junctions || null,
    breakPoints:
      outputs?.breakPoints?.features?.length
        ? outputs.breakPoints
        : fallbackBreakPoints?.features?.length
          ? fallbackBreakPoints
          : manualBreakCollection.features.length
            ? manualBreakCollection
            : null
  }
}

export function buildActivePreviewState(options: PreviewCollectionOptions): ActivePreviewState {
  const collections = collectPreviewCollections(options)
  const stage: PreviewSourceStage = options.outputs ? 'step1' : options.step0Boundary || options.step0Streams ? 'step0' : 'upload'

  const groups = [
    {
      key: 'boundary' as const,
      label: options.outputs?.subWatersheds ? '子流域' : '边界',
      shortType: options.outputs?.subWatersheds ? '子流域' : '边界',
      visible: true,
      collection: collections.boundary,
      items: buildLayerItems('boundary', options.outputs?.subWatersheds ? '子流域' : '边界', options.outputs?.subWatersheds ? 'Watershed' : 'Boundary', collections.boundary)
    },
    {
      key: 'reaches' as const,
      label: '河段',
      shortType: '河段',
      visible: true,
      collection: collections.reaches,
      items: buildLayerItems('reaches', '河段', 'Reach', collections.reaches)
    },
    {
      key: 'junctions' as const,
      label: '节点',
      shortType: '节点',
      visible: true,
      collection: collections.junctions,
      items: buildLayerItems('junctions', '节点', 'Junction', collections.junctions)
    },
    {
      key: 'breakPoints' as const,
      label: '控制点',
      shortType: '控制点',
      visible: true,
      collection: collections.breakPoints,
      items: buildLayerItems('breakPoints', '控制点', 'Point', collections.breakPoints)
    }
  ].filter((group) => (group.collection?.features?.length || 0) > 0) as PreviewLayerGroup[]

  return {
    stage,
    outputs: options.outputs,
    groups
  }
}

export function getHoverSummary(item: PreviewLayerItem) {
  return {
    title: item.label,
    type: item.shortType,
    id: getPrimaryFeatureLabel(item.feature, item.label)
  }
}

export function getStageFromSources(options: {
  step2Outputs?: WatershedOutputs | null
  step1Outputs?: WatershedOutputs | null
  step0Boundary?: GeoJsonFeatureCollection | null
  step0Streams?: GeoJsonFeatureCollection | null
  boundaryPreview?: GeoJsonFeatureCollection | null
}) {
  if (options.step2Outputs) return { stage: 'step2' as const, outputs: options.step2Outputs }
  if (options.step1Outputs) return { stage: 'step1' as const, outputs: options.step1Outputs }
  if (options.step0Boundary || options.step0Streams) return { stage: 'step0' as const, outputs: null }
  if (options.boundaryPreview) return { stage: 'upload' as const, outputs: null }
  return { stage: 'upload' as const, outputs: null }
}

export function buildActivePreviewStateFromSteps(args: {
  step2Outputs?: WatershedOutputs | null
  step1Outputs?: WatershedOutputs | null
  boundaryPreview: GeoJsonFeatureCollection | null
  step0Boundary: GeoJsonFeatureCollection | null
  step0Streams: GeoJsonFeatureCollection | null
  manualBreakPoints: BreakPoint[]
}) {
  const source = getStageFromSources({
    step2Outputs: args.step2Outputs,
    step1Outputs: args.step1Outputs,
    step0Boundary: args.step0Boundary,
    step0Streams: args.step0Streams,
    boundaryPreview: args.boundaryPreview
  })

  const state = buildActivePreviewState({
    outputs: source.outputs,
    fallbackBreakPoints: args.step1Outputs?.breakPoints || null,
    boundaryPreview: args.boundaryPreview,
    step0Boundary: args.step0Boundary,
    step0Streams: args.step0Streams,
    manualBreakPoints: args.manualBreakPoints
  })

  return {
    ...state,
    stage: source.stage
  }
}
