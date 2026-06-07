import type { LayoutBoxForm } from '@/types'

export type LayoutCorner = 'top-left' | 'top-right' | 'bottom-right' | 'bottom-left'

const DEFAULT_PADDING = 4

function round2(value: number) {
  return Number(value.toFixed(2))
}

export function placeBoxInMapFrame(
  box: LayoutBoxForm,
  mapFrame: LayoutBoxForm,
  corner: LayoutCorner,
  padding = DEFAULT_PADDING
): LayoutBoxForm {
  const left = mapFrame.x + padding
  const right = mapFrame.x + mapFrame.width - box.width - padding
  const bottom = mapFrame.y + padding
  const top = mapFrame.y + mapFrame.height - box.height - padding

  return {
    ...box,
    x: round2(corner.endsWith('right') ? right : left),
    y: round2(corner.startsWith('top') ? top : bottom)
  }
}

export function nearestBoxCornerInMapFrame(box: LayoutBoxForm, mapFrame: LayoutBoxForm, padding = DEFAULT_PADDING) {
  const corners: LayoutCorner[] = ['top-left', 'top-right', 'bottom-right', 'bottom-left']
  return corners.reduce(
    (best, corner) => {
      const placed = placeBoxInMapFrame(box, mapFrame, corner, padding)
      const distance = Math.abs(placed.x - box.x) + Math.abs(placed.y - box.y)
      return distance < best.distance ? { corner, distance } : best
    },
    { corner: 'top-left' as LayoutCorner, distance: Number.POSITIVE_INFINITY }
  ).corner
}

export function resizeBoxFromCenter(box: LayoutBoxForm, field: keyof LayoutBoxForm, value: number): LayoutBoxForm {
  if (field === 'width') {
    const delta = value - box.width
    return {
      ...box,
      x: round2(box.x - delta / 2),
      width: round2(value)
    }
  }

  if (field === 'height') {
    const delta = value - box.height
    return {
      ...box,
      y: round2(box.y - delta / 2),
      height: round2(value)
    }
  }

  return {
    ...box,
    [field]: round2(value)
  }
}
