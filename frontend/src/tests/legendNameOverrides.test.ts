import { describe, expect, it } from 'vitest'

import { collectLegendNameOverrides } from '@/utils/legendNameOverrides'
import { buildRenderPayload } from '@/utils/renderPayload'
import type { WorkspaceForm } from '@/types'

function formWithStations(): WorkspaceForm {
  return {
    output_dir: 'frontend_20260610',
    template_project: 'D:/uploads/template.aprx',
    map_title: 'Basin river network map',
    output: { width_px: 1600, height_px: 1200, dpi: 150 },
    inputs: {
      basin_boundary: '',
      river_network: '',
      basin_boundaries: [],
      river_networks: [],
      station_layers: [
        {
          id: 'station-layer-1',
          upload: {
            file_id: 'station-1',
            kind: 'station_excel',
            original_name: 'stations.xlsx',
            path: 'D:/uploads/stations.xlsx',
            suffix: '.xlsx',
            size_bytes: 100
          },
          headers: ['lon', 'lat', 'name'],
          sampleName: 'Station A',
          sheet_name: 'Sheet1',
          x_field: 'lon',
          y_field: 'lat',
          name_field: 'name',
          layer_name: 'StationLayer1',
          symbol: { shape: 'circle', color_preset: 'green', color: '#00a651', size_pt: 12, rotation_deg: 0 },
          label: { enabled: true, color: '#000000', font_size_pt: 10, position: 'top_right' },
          points: [
            {
              row_number: 2,
              raw_name: 'A',
              display_name: 'A',
              values: { lon: '105', lat: '27', name: 'A' },
              symbol: { shape: 'circle', color_preset: 'green', color: '#00a651', size_pt: 12, rotation_deg: 0 },
              label: { enabled: true, color: '#000000', font_size_pt: 10, position: 'top_right' }
            },
            {
              row_number: 3,
              raw_name: 'B',
              display_name: 'B',
              values: { lon: '106', lat: '28', name: 'B' },
              symbol: { shape: 'circle', color_preset: 'green', color: '#00a651', size_pt: 12, rotation_deg: 0 },
              label: { enabled: true, color: '#000000', font_size_pt: 10, position: 'bottom' }
            },
            {
              row_number: 4,
              raw_name: 'C',
              display_name: 'C',
              values: { lon: '107', lat: '29', name: 'C' },
              symbol: { shape: 'diamond', color_preset: 'orange', color: '#f59e0b', size_pt: 12, rotation_deg: 0 },
              label: { enabled: true, color: '#000000', font_size_pt: 10, position: 'top_right' }
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
      north_arrow: { enabled: true },
      elements: {
        map_frame: { x: 6.53, y: 7.31, width: 257.15, height: 191.01 },
        title: { enabled: true, x: 97.54, y: 174.75, width: 75.86, height: 11.18, font_size: 18, background: true },
        legend: { enabled: true, x: 12.19, y: 85.34, width: 59.61, height: 77.22, background: true },
        scale_bar: { enabled: true, x: 83.99, y: 11.18, width: 92.12, height: 7.11 },
        north_arrow: { enabled: true, x: 249.26, y: 158.5, width: 7.04, height: 16.26 }
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
        background: { enabled: true, color: '#ffffff', gap_x: 1, gap_y: 1 },
        name_overrides: []
      }
    },
    map_view: {
      mode: 'auto',
      padding: { left: 0.14, right: 0.14, top: 0.14, bottom: 0.14 },
      extent: { xmin: 0, ymin: 0, xmax: 1, ymax: 1 }
    },
    style: {
      basin_boundary: { color: '#222222', width_pt: 1.2 },
      basin_fill: { color: '#e6f0d4', opacity: 0.45 },
      river_network: { color: '#2f80ed', width_pt: 2.5 }
    }
  }
}

describe('collectLegendNameOverrides', () => {
  it('creates one editable legend row for each station point using station names', () => {
    const rows = collectLegendNameOverrides(formWithStations())

    expect(rows.map((row) => row.default_name)).toEqual(['A', 'B', 'C'])
    expect(rows.map((row) => row.source_key)).toEqual([
      'station-layer-1-point-2',
      'station-layer-1-point-3',
      'station-layer-1-point-4'
    ])
  })

  it('keeps hidden rows editable and sends the visibility switch in render payload', () => {
    const form = formWithStations()
    form.layout.legend_style.name_overrides = [
      {
        source_type: 'station_group',
        source_key: 'station-layer-1-point-3',
        default_name: 'B',
        legend_name: 'B',
        legend_visible: false
      }
    ]

    expect(collectLegendNameOverrides(form).map((row) => row.source_key)).toEqual([
      'station-layer-1-point-2',
      'station-layer-1-point-3',
      'station-layer-1-point-4'
    ])
    expect(buildRenderPayload(form).layout.legend_style.name_overrides).toContainEqual(
      expect.objectContaining({
        source_key: 'station-layer-1-point-3',
        legend_visible: false
      })
    )
  })
})
