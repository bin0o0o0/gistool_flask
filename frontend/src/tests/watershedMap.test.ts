import { describe, expect, it } from 'vitest'

import {
  buildActivePreviewStateFromSteps,
  getHoverSummary,
  getPrimaryFeatureLabel,
  manualBreakPointsToCollection
} from '@/utils/watershedMap'

describe('watershedMap utilities', () => {
  it('converts manual break points into a feature collection', () => {
    const collection = manualBreakPointsToCollection([
      [105.1, 27.2, 1],
      [105.2, 27.3, 2]
    ])

    expect(collection.type).toBe('FeatureCollection')
    expect(collection.features).toHaveLength(2)
    expect(collection.features[0]).toMatchObject({
      geometry: { type: 'Point', coordinates: [105.1, 27.2] },
      properties: { id: 1 }
    })
  })

  it('prefers step2 outputs, then step1, then step0, then upload preview', () => {
    const boundaryPreview = {
      type: 'FeatureCollection' as const,
      features: [{ type: 'Feature', geometry: null, properties: { id: 'upload-boundary' } }]
    }
    const step0Boundary = {
      type: 'FeatureCollection' as const,
      features: [{ type: 'Feature', geometry: null, properties: { id: 'step0-boundary' } }]
    }
    const step0Streams = {
      type: 'FeatureCollection' as const,
      features: [{ type: 'Feature', geometry: null, properties: { id: 'step0-stream' } }]
    }
    const step1Outputs = {
      subWatersheds: {
        type: 'FeatureCollection' as const,
        features: [{ type: 'Feature', geometry: null, properties: { id: 'step1-sub' } }]
      },
      reaches: {
        type: 'FeatureCollection' as const,
        features: [{ type: 'Feature', geometry: null, properties: { id: 'step1-reach' } }]
      },
      breakPoints: {
        type: 'FeatureCollection' as const,
        features: [{ type: 'Feature', geometry: null, properties: { id: 'step1-break' } }]
      }
    }
    const step2Outputs = {
      subWatersheds: {
        type: 'FeatureCollection' as const,
        features: [{ type: 'Feature', geometry: null, properties: { id: 'step2-sub' } }]
      },
      reaches: {
        type: 'FeatureCollection' as const,
        features: [{ type: 'Feature', geometry: null, properties: { id: 'step2-reach' } }]
      }
    }

    const uploadState = buildActivePreviewStateFromSteps({
      boundaryPreview,
      step0Boundary: null,
      step0Streams: null,
      step1Outputs: null,
      step2Outputs: null,
      manualBreakPoints: []
    })
    expect(uploadState.stage).toBe('upload')
    expect(uploadState.groups[0].items[0].label).toBe('upload-boundary')

    const step0State = buildActivePreviewStateFromSteps({
      boundaryPreview,
      step0Boundary,
      step0Streams,
      step1Outputs: null,
      step2Outputs: null,
      manualBreakPoints: []
    })
    expect(step0State.stage).toBe('step0')
    expect(step0State.groups[0].items[0].label).toBe('step0-boundary')
    expect(step0State.groups[1].items[0].label).toBe('step0-stream')

    const step1State = buildActivePreviewStateFromSteps({
      boundaryPreview,
      step0Boundary,
      step0Streams,
      step1Outputs,
      step2Outputs: null,
      manualBreakPoints: []
    })
    expect(step1State.stage).toBe('step1')
    expect(step1State.groups[0].items[0].label).toBe('step1-sub')

    const step2State = buildActivePreviewStateFromSteps({
      boundaryPreview,
      step0Boundary,
      step0Streams,
      step1Outputs,
      step2Outputs,
      manualBreakPoints: []
    })
    expect(step2State.stage).toBe('step2')
    expect(step2State.groups[0].items[0].label).toBe('step2-sub')
    expect(step2State.groups.find((group) => group.key === 'breakPoints')?.items[0].label).toBe('step1-break')
  })

  it('falls back from id to name to generated labels', () => {
    const byName = getPrimaryFeatureLabel({ properties: { name: 'Reach-A' } }, 'Reach1')
    const generated = getPrimaryFeatureLabel({ properties: {} }, 'Reach1')

    expect(byName).toBe('Reach-A')
    expect(generated).toBe('Reach1')
  })

  it('builds hover summaries from normalized items', () => {
    const state = buildActivePreviewStateFromSteps({
      boundaryPreview: {
        type: 'FeatureCollection',
        features: [{ type: 'Feature', geometry: null, properties: { id: 'Watershed6.1' } }]
      },
      step0Boundary: null,
      step0Streams: null,
      step1Outputs: null,
      step2Outputs: null,
      manualBreakPoints: []
    })

    const summary = getHoverSummary(state.groups[0].items[0])
    expect(summary).toEqual({
      title: 'Watershed6.1',
      type: '边界',
      id: 'Watershed6.1'
    })
  })
})
