import type { StationLayerForm, StationShape } from '@/types'

// 站点符号的 SVG 多边形点位。圆形在组件里用 <circle> 单独画，所以这里返回空字符串。
export function markerPolygonPoints(shape: StationShape): string {
  // SVG 使用 100x100 视口，点位围绕中心设计，方便不同形状共用同一套预览。
  const points: Record<StationShape, string> = {
    circle: '',
    triangle: '50,16 86,82 14,82',
    square: '24,24 76,24 76,76 24,76',
    diamond: '50,16 84,50 50,84 16,50',
    rectangle: '16,32 84,32 84,68 16,68'
  }
  return points[shape]
}

export function labelPositionStyle(position: string) {
  // 八方向标注位置和后端协议保持一致，预览里用 CSS 百分比模拟相对站点的偏移。
  const base = {
    top_left: { left: '8%', top: '8%', transform: 'translate(-100%, -100%)' },
    top: { left: '50%', top: '4%', transform: 'translate(-50%, -100%)' },
    top_right: { left: '92%', top: '8%', transform: 'translate(0, -100%)' },
    right: { left: '96%', top: '50%', transform: 'translate(0, -50%)' },
    bottom_right: { left: '92%', top: '92%', transform: 'translate(0, 0)' },
    bottom: { left: '50%', top: '96%', transform: 'translate(-50%, 0)' },
    bottom_left: { left: '8%', top: '92%', transform: 'translate(-100%, 0)' },
    left: { left: '4%', top: '50%', transform: 'translate(-100%, -50%)' }
  }
  return base[position as keyof typeof base] || base.top_right
}

export function stationColor(layer: StationLayerForm, presets: Record<string, string>) {
  // 自定义颜色优先；如果用户清空颜色，再退回颜色预设。
  return layer.symbol.color || presets[layer.symbol.color_preset] || '#1f78ff'
}

export function markerRotationStyle(layer: StationLayerForm) {
  return {
    transform: `rotate(${layer.symbol.rotation_deg || 0}deg)`
  }
}
