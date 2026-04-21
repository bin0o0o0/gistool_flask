import { describe, expect, it } from 'vitest'
import { labelPositionStyle, markerPolygonPoints, markerRotationStyle, stationColor } from '@/utils/symbolPreview'
import type { StationLayerForm } from '@/types'

// 站点预览测试只关心前端 SVG/CSS 逻辑，不需要启动 Flask 或 ArcPy。
function sampleLayer(): StationLayerForm {
  return {
    id: 'layer-1',
    headers: [],
    sampleName: '站点A',
    sheet_name: 'Sheet1',
    x_field: 'lon',
    y_field: 'lat',
    name_field: 'name',
    layer_name: 'Stations',
    symbol: {
      shape: 'rectangle',
      color_preset: 'green',
      color: '',
      size_pt: 20,
      rotation_deg: 35
    },
    label: {
      enabled: true,
      color: '#000000',
      font_size_pt: 20,
      position: 'left'
    },
    points: []
  }
}

describe('symbol preview helpers', () => {
  it('为长方形生成比正方形更宽的 SVG 点位', () => {
    expect(markerPolygonPoints('rectangle')).toBe('16,32 84,32 84,68 16,68')
  })

  it('根据标注位置返回 CSS 定位规则', () => {
    expect(labelPositionStyle('left')).toMatchObject({
      left: '4%',
      top: '50%',
      transform: 'translate(-100%, -50%)'
    })
  })

  it('自定义颜色为空时使用颜色预设', () => {
    expect(stationColor(sampleLayer(), { green: '#00a651' })).toBe('#00a651')
  })

  it('根据符号配置返回站点样式旋转规则', () => {
    expect(markerRotationStyle(sampleLayer())).toEqual({ transform: 'rotate(35deg)' })
  })
})
