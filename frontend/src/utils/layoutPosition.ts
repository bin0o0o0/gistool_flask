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
