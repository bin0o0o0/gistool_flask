import { describe, expect, it } from 'vitest'
import { buildRenderPayload } from '@/utils/renderPayload'
import type { WorkspaceForm } from '@/types'

// 构造一份接近真实 Apifox 请求的表单，验证前端不会把上传路径组装错。
function sampleForm(): WorkspaceForm {
  return {
    output_dir: 'frontend_test',
    template_project: 'D:/uploads/template.aprx',
    map_title: '示例流域水系图',
    output: {
      width_px: 1600,
      height_px: 1200,
      dpi: 150
    },
    inputs: {
      basin_boundary: 'D:/uploads/basin.geojson',
      river_network: 'D:/uploads/rivers.geojson',
      basin_boundaries: [
        {
          id: 'basin-1',
          name: '上游流域',
          path: 'D:/uploads/basin.geojson',
          upload: {
            file_id: 'basin-1',
            kind: 'basin_boundary',
            original_name: 'basin.geojson',
            path: 'D:/uploads/basin.geojson',
            suffix: '.geojson',
            size_bytes: 12
          },
          style: {
            boundary_color: '#222222',
            boundary_width_pt: 1.2,
            fill_color: '#e6f0d4',
            fill_opacity: 0.45
          }
        },
        {
          id: 'basin-2',
          name: '下游流域',
          path: 'D:/uploads/basin2.geojson',
          upload: {
            file_id: 'basin-2',
            kind: 'basin_boundary',
            original_name: 'basin2.geojson',
            path: 'D:/uploads/basin2.geojson',
            suffix: '.geojson',
            size_bytes: 12
          },
          style: {
            boundary_color: '#7a4f2a',
            boundary_width_pt: 0.8,
            fill_color: '#f6d7a7',
            fill_opacity: 0.35
          }
        }
      ],
      river_networks: [
        {
          id: 'river-1',
          name: '主干河流',
          path: 'D:/uploads/rivers.geojson',
          upload: {
            file_id: 'river-1',
            kind: 'river_network',
            original_name: 'rivers.geojson',
            path: 'D:/uploads/rivers.geojson',
            suffix: '.geojson',
            size_bytes: 12
          },
          style: {
            color: '#2f80ed',
            width_pt: 2.5
          }
        },
        {
          id: 'river-2',
          name: '支流',
          path: 'D:/uploads/rivers2.geojson',
          upload: {
            file_id: 'river-2',
            kind: 'river_network',
            original_name: 'rivers2.geojson',
            path: 'D:/uploads/rivers2.geojson',
            suffix: '.geojson',
            size_bytes: 12
          },
          style: {
            color: '#00a6c8',
            width_pt: 1.2
          }
        }
      ],
      station_layers: [
        {
          id: 'layer-1',
          upload: {
            file_id: 'file-1',
            kind: 'station_excel',
            original_name: 'stations.xlsx',
            path: 'D:/uploads/stations.xlsx',
            suffix: '.xlsx',
            size_bytes: 123
          },
          headers: ['lon', 'lat', 'name'],
          sampleName: '站点A',
          sheet_name: 'Sheet1',
          x_field: 'lon',
          y_field: 'lat',
          name_field: 'name',
          layer_name: 'GreenCircleStations',
          symbol: {
            shape: 'rectangle',
            color_preset: 'green',
            color: '#00a651',
            size_pt: 20,
            rotation_deg: 15
          },
          label: {
            enabled: true,
            color: '#000000',
            font_size_pt: 18,
            position: 'top_right'
          },
          points: [
            {
              row_number: 2,
              values: { lon: '100', lat: '30', name: 'Station A' },
              raw_name: '绔欑偣A',
              display_name: '绔欑偣A',
              symbol: {
                shape: 'circle',
                color_preset: 'green',
                color: '#00a651',
                size_pt: 20,
                rotation_deg: 0
              },
              label: {
                enabled: true,
                color: '#000000',
                font_size_pt: 18,
                position: 'top_right'
              }
            },
            {
              row_number: 3,
              values: { lon: '101', lat: '31', name: 'Station B' },
              raw_name: '绔欑偣B',
              display_name: '绔欑偣B',
              symbol: {
                shape: 'triangle',
                color_preset: 'red',
                color: '#ff0000',
                size_pt: 22,
                rotation_deg: 15
              },
              label: {
                enabled: true,
                color: '#111111',
                font_size_pt: 20,
                position: 'left'
              }
            }
          ]
        }
      ]
    },
    layout: {
      basemap: 'Topographic',
      mode: 'manual',
      title: { enabled: true },
      legend: { enabled: true },
      scale_bar: { enabled: true },
      north_arrow: { enabled: false },
      elements: {
        map_frame: { x: 6.53, y: 7.31, width: 257.15, height: 191.01 },
        title: { enabled: true, x: 97.54, y: 174.75, width: 75.86, height: 11.18, font_size: 18, background: true },
        legend: { enabled: true, x: 12.19, y: 85.34, width: 59.61, height: 77.22, background: true },
        scale_bar: { enabled: true, x: 83.99, y: 11.18, width: 92.12, height: 7.11 },
        north_arrow: { enabled: false, x: 249.26, y: 158.5, width: 7.04, height: 16.26 }
      },
      legend_style: {
        scale_symbols: false,
        patch_width: 12,
        patch_height: 6,
        scale_to_patch: true,
        item_gap: 2,
        class_gap: 2,
        layer_name_gap: 2,
        patch_gap: 2,
        text_gap: 2,
        min_font_size: 5,
        auto_fonts: true,
        background: {
          enabled: true,
          color: '#ffffff',
          gap_x: 1,
          gap_y: 1
        }
      }
    },
    map_view: {
      mode: 'auto_padding',
      padding: { left: 0.46, right: 0.14, top: 0.14, bottom: 0.5667 },
      extent: { xmin: 0, ymin: 0, xmax: 10, ymax: 10 }
    },
    style: {
      basin_boundary: { color: '#222222', width_pt: 1.2 },
      basin_fill: { color: '#e6f0d4', opacity: 0.45 },
      river_network: { color: '#2f80ed', width_pt: 2.5 }
    }
  }
}

describe('buildRenderPayload', () => {
  it('把上传返回的路径组装成后端 /api/render 请求体', () => {
    const payload = buildRenderPayload(sampleForm())

    expect(payload.template_project).toBe('D:/uploads/template.aprx')
    expect(payload.inputs.basin_boundary.path).toBe('D:/uploads/basin.geojson')
    expect(payload.inputs.river_network.path).toBe('D:/uploads/rivers.geojson')
    expect(payload.inputs.basin_boundaries).toHaveLength(2)
    expect(payload.inputs.basin_boundaries[1].style.basin_fill.color).toBe('#f6d7a7')
    expect(payload.inputs.river_networks).toHaveLength(2)
    expect(payload.inputs.river_networks[1].style.river_network.width_pt).toBe(1.2)
    expect(payload.inputs.station_layers[0].path).toBe('D:/uploads/stations.xlsx')
    expect(payload.inputs.station_layers[0].symbol.shape).toBe('rectangle')
    expect(payload.inputs.station_layers[0].symbol.rotation_deg).toBe(15)
    expect('rotation_deg' in payload.inputs.station_layers[0].label).toBe(false)
    expect(payload.inputs.station_layers[0].points).toHaveLength(2)
    expect(payload.inputs.station_layers[0].points[0].row_number).toBe(2)
    expect(payload.inputs.station_layers[0].points[1].symbol.shape).toBe('triangle')
    expect(payload.inputs.station_layers[0].points[1].label.position).toBe('left')
    expect(payload.layout.title.enabled).toBe(true)
    expect(payload.layout.legend.enabled).toBe(true)
    expect(payload.layout.scale_bar.enabled).toBe(true)
    expect(payload.layout.north_arrow.enabled).toBe(false)
    expect(payload.layout.mode).toBe('manual')
    expect(payload.layout.elements.title.x).toBe(97.54)
    expect(payload.layout.elements.map_frame.width).toBe(257.15)
    expect(payload.layout.legend_style.patch_width).toBe(12)
    expect(payload.layout.legend_style.patch_height).toBe(6)
    expect(payload.map_view.mode).toBe('auto_padding')
    expect(payload.map_view.padding.left).toBe(0.46)
  })
})
