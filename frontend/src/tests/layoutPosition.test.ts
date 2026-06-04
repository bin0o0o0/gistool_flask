import { describe, expect, it } from 'vitest'

import { placeBoxInMapFrame, resizeBoxFromCenter } from '@/utils/layoutPosition'
import type { LayoutBoxForm } from '@/types'

describe('placeBoxInMapFrame', () => {
  const mapFrame: LayoutBoxForm = { x: 6.53, y: 7.31, width: 257.15, height: 191.01 }
  const legend: LayoutBoxForm = { x: 12.19, y: 45.34, width: 59.61, height: 77.22 }

  it('places the legend in the four map frame corners without changing its size', () => {
    expect(placeBoxInMapFrame(legend, mapFrame, 'top-left')).toEqual({
      x: 10.53,
      y: 117.1,
      width: 59.61,
      height: 77.22
    })

    expect(placeBoxInMapFrame(legend, mapFrame, 'top-right')).toEqual({
      x: 200.07,
      y: 117.1,
      width: 59.61,
      height: 77.22
    })

    expect(placeBoxInMapFrame(legend, mapFrame, 'bottom-right')).toEqual({
      x: 200.07,
      y: 11.31,
      width: 59.61,
      height: 77.22
    })

    expect(placeBoxInMapFrame(legend, mapFrame, 'bottom-left')).toEqual({
      x: 10.53,
      y: 11.31,
      width: 59.61,
      height: 77.22
    })
  })
})

describe('resizeBoxFromCenter', () => {
  it('keeps the box center stable when width changes', () => {
    expect(resizeBoxFromCenter({ x: 97.54, y: 188, width: 69.86, height: 11.18 }, 'width', 100)).toEqual({
      x: 82.47,
      y: 188,
      width: 100,
      height: 11.18
    })
  })
})
