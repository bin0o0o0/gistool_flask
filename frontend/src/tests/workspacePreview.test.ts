import { describe, expect, it } from 'vitest'

import { buildWorkspacePreviewData } from '@/utils/workspacePreview'
import type { WorkspaceForm } from '@/types'

describe('buildWorkspacePreviewData', () => {
  it('builds preview layers from current workspace form state', () => {
    const form = createWorkspaceForm()
    form.inputs.basin_boundaries.push({
      id: 'basin-1',
      name: 'Main Basin',
      path: 'D:/uploads/basin.geojson',
      style: {
        boundary_color: '#1d3557',
        boundary_width_pt: 1.4,
        fill_color: '#d7ecf2',
        fill_opacity: 0.45
      }
    })
    form.inputs.river_networks.push({
      id: 'river-1',
      name: 'River Network',
      path: 'D:/uploads/rivers.geojson',
      style: {
        color: '#2f80ed',
        width_pt: 2.5
      }
    })
    form.inputs.station_layers[0].points = [
      {
        row_number: 2,
        raw_name: 'Station A',
        display_name: 'Station A',
        values: { lon: '105.12', lat: '27.05' },
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
          font_size_pt: 16,
          position: 'top_right'
        }
      }
    ]

    const preview = buildWorkspacePreviewData(form)

    expect(preview.basinLayer.features).toHaveLength(1)
    expect(preview.riverLayer.features).toHaveLength(1)
    expect(preview.stationLayer.features).toHaveLength(1)
    expect(preview.stationLayer.features[0].properties).toMatchObject({
      layerName: 'StationLayer1',
      label: 'Station A'
    })
    expect(preview.layoutCard.paperLabel).toBe('1600 x 1200 / 150 DPI')
  })

  it('falls back to scaffold preview when no uploads are ready', () => {
    const preview = buildWorkspacePreviewData(createWorkspaceForm())

    expect(preview.basinLayer.features).toHaveLength(1)
    expect(preview.riverLayer.features).toHaveLength(2)
    expect(preview.stationLayer.features).toHaveLength(0)
    expect(preview.layoutCard.legendEnabled).toBe(true)
  })
})

function createWorkspaceForm(): WorkspaceForm {
  return {
    output_dir: 'frontend_20260524',
    template_project: '',
    map_title: 'Basin river network map',
    output: {
      width_px: 1600,
      height_px: 1200,
      dpi: 150
    },
    inputs: {
      basin_boundary: '',
      river_network: '',
      basin_boundaries: [],
      river_networks: [],
      station_layers: [
        {
          id: 'station-layer-1',
          headers: ['lon', 'lat', 'name'],
          sampleName: 'Station 1',
          sheet_name: 'Sheet1',
          x_field: 'lon',
          y_field: 'lat',
          name_field: 'name',
          layer_name: 'StationLayer1',
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
            font_size_pt: 20,
            position: 'top_right'
          },
          points: []
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
        title: { enabled: true, x: 97.54, y: 188, width: 69.86, height: 11.18, font_size: 20, background: true },
        legend: { enabled: true, x: 12.19, y: 45.34, width: 59.61, height: 77.22, background: true },
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
        background: {
          enabled: true,
          color: '#ffffff',
          gap_x: 1,
          gap_y: 1
        },
        name_overrides: []
      }
    },
    map_view: {
      mode: 'auto_padding',
      padding: { left: 0.2408, right: 0.1808, top: 0.14, bottom: 0.14 },
      extent: { xmin: 0, ymin: 0, xmax: 10, ymax: 10 }
    },
    style: {
      basin_boundary: { color: '#222222', width_pt: 1.2 },
      basin_fill: { color: '#e6f0d4', opacity: 0.45 },
      river_network: { color: '#2f80ed', width_pt: 2.5 }
    }
  }
}
