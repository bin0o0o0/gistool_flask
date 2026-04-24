import type { WorkspaceForm } from '@/types'
import { collectLegendNameOverrides } from '@/utils/legendNameOverrides'

// 将表单状态转换成后端 /api/render 需要的 JSON。这里刻意不掺杂 UI 字段，比如上传进度。
export function buildRenderPayload(form: WorkspaceForm) {
  return {
    output_dir: form.output_dir,
    template_project: form.template_project,
    map_title: form.map_title,
    output: {
      width_px: form.output.width_px,
      height_px: form.output.height_px,
      dpi: form.output.dpi
    },
    inputs: {
      basin_boundary: {
        path: form.inputs.basin_boundaries[0]?.path || form.inputs.basin_boundary
      },
      river_network: {
        path: form.inputs.river_networks[0]?.path || form.inputs.river_network
      },
      basin_boundaries: form.inputs.basin_boundaries.map((layer) => ({
        path: layer.path,
        layer_name: layer.name,
        style: {
          basin_boundary: {
            color: layer.style.boundary_color,
            width_pt: layer.style.boundary_width_pt
          },
          basin_fill: {
            color: layer.style.fill_color,
            opacity: layer.style.fill_opacity
          }
        }
      })),
      river_networks: form.inputs.river_networks.map((layer) => ({
        path: layer.path,
        layer_name: layer.name,
        style: {
          river_network: {
            color: layer.style.color,
            width_pt: layer.style.width_pt
          }
        }
      })),
      station_layers: form.inputs.station_layers
        // 没上传 Excel 的站点层只用于前端预览，不传给后端，避免 ArcPy 读空路径。
        .filter((layer) => !!layer.upload?.path)
        .map((layer) => ({
          path: layer.upload?.path,
          sheet_name: layer.sheet_name,
          x_field: layer.x_field,
          y_field: layer.y_field,
          name_field: layer.name_field,
          layer_name: layer.layer_name,
          symbol: {
            shape: layer.symbol.shape,
            color_preset: layer.symbol.color_preset,
            color: layer.symbol.color,
            size_pt: layer.symbol.size_pt,
            rotation_deg: layer.symbol.rotation_deg
          },
          label: {
            enabled: layer.label.enabled,
            color: layer.label.color,
            font_size_pt: layer.label.font_size_pt,
            position: layer.label.position
          },
          points: layer.points.map((point) => ({
            row_number: point.row_number,
            name: point.display_name,
            symbol: {
              shape: point.symbol.shape,
              color_preset: point.symbol.color_preset,
              color: point.symbol.color,
              size_pt: point.symbol.size_pt,
              rotation_deg: point.symbol.rotation_deg
            },
            label: {
              enabled: point.label.enabled,
              color: point.label.color,
              font_size_pt: point.label.font_size_pt,
              position: point.label.position
            }
          }))
        }))
    },
    layout: {
      basemap: form.layout.basemap,
      mode: form.layout.mode,
      title: {
        enabled: form.layout.elements.title.enabled
      },
      legend: {
        enabled: form.layout.elements.legend.enabled
      },
      scale_bar: {
        enabled: form.layout.elements.scale_bar.enabled
      },
      north_arrow: {
        enabled: form.layout.elements.north_arrow.enabled
      },
      elements: form.layout.elements,
      legend_style: {
        ...form.layout.legend_style,
        name_overrides: collectLegendNameOverrides(form)
      }
    },
    map_view: form.map_view,
    style: {
      basin_boundary: {
        color: form.style.basin_boundary.color,
        width_pt: form.style.basin_boundary.width_pt
      },
      basin_fill: {
        color: form.style.basin_fill.color,
        opacity: form.style.basin_fill.opacity
      },
      river_network: {
        color: form.style.river_network.color,
        width_pt: form.style.river_network.width_pt
      }
    }
  }
}
