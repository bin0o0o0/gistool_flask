import { describe, expect, it } from 'vitest'

import {
  basinBoundaryColorOptions,
  basinFillColorOptions,
  riverColorOptions
} from '@/utils/mapOutputStyleOptions'

describe('map output layer style options', () => {
  it('provides named color palettes for layer style selection', () => {
    expect(basinBoundaryColorOptions.length).toBeGreaterThanOrEqual(6)
    expect(basinFillColorOptions.length).toBeGreaterThanOrEqual(6)
    expect(riverColorOptions.length).toBeGreaterThanOrEqual(6)

    expect(basinBoundaryColorOptions.every((option) => option.label && option.value.startsWith('#'))).toBe(true)
    expect(basinFillColorOptions.every((option) => option.label && option.value.startsWith('#'))).toBe(true)
    expect(riverColorOptions.every((option) => option.label && option.value.startsWith('#'))).toBe(true)
  })

  it('keeps the existing default colors selectable', () => {
    expect(basinBoundaryColorOptions.map((option) => option.value)).toContain('#222222')
    expect(basinFillColorOptions.map((option) => option.value)).toContain('#e6f0d4')
    expect(riverColorOptions.map((option) => option.value)).toContain('#2f80ed')
  })
})
