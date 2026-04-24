// 前端和 Flask 后端之间共用的数据结构都放在这里，避免组件里散落大量 any。
export interface ApiResponse<T> {
  success: boolean
  data?: T
  message?: string
}

export interface UploadResult {
  file_id: string
  kind: UploadKind
  original_name: string
  path: string
  suffix: string
  size_bytes: number
}

export type UploadKind = 'template_project' | 'basin_boundary' | 'river_network' | 'station_excel'

export type StationShape = 'circle' | 'triangle' | 'square' | 'diamond' | 'rectangle'

export type WorkspaceStepId = 'data' | 'output' | 'style' | 'stations'

export interface RenderOptions {
  label_positions: string[]
  basemaps: string[]
  station_symbol_shapes: StationShape[]
  station_symbol_color_presets: Record<string, string>
}

export interface UploadedFileState {
  result?: UploadResult
  error?: string
  uploading: boolean
}

export interface StationSymbolForm {
  shape: StationShape
  color_preset: string
  color: string
  size_pt: number
  rotation_deg: number
}

export interface StationLabelForm {
  enabled: boolean
  color: string
  font_size_pt: number
  position: string
}

export interface StationPointForm {
  row_number: number
  raw_name: string
  display_name: string
  values: Record<string, string>
  symbol: StationSymbolForm
  label: StationLabelForm
}

export interface StationLayerForm {
  id: string
  upload?: UploadResult
  headers: string[]
  sampleName: string
  sheet_name: string
  x_field: string
  y_field: string
  name_field: string
  layer_name: string
  symbol: StationSymbolForm
  label: StationLabelForm
  points: StationPointForm[]
}

export type LegendNameSourceType = 'basin' | 'river' | 'station_layer' | 'station_group'

export interface LegendNameOverrideForm {
  source_type: LegendNameSourceType
  source_key: string
  default_name: string
  legend_name: string
}

export interface BasinLayerForm {
  id: string
  upload?: UploadResult
  name: string
  path: string
  style: {
    boundary_color: string
    boundary_width_pt: number
    fill_color: string
    fill_opacity: number
  }
}

export interface RiverLayerForm {
  id: string
  upload?: UploadResult
  name: string
  path: string
  style: {
    color: string
    width_pt: number
  }
}

export interface WorkspaceForm {
  output_dir: string
  template_project: string
  map_title: string
  output: {
    width_px: number
    height_px: number
    dpi: number
  }
  inputs: {
    basin_boundary: string
    river_network: string
    basin_boundaries: BasinLayerForm[]
    river_networks: RiverLayerForm[]
    station_layers: StationLayerForm[]
  }
  layout: {
    basemap: string
    mode: 'manual'
    title: { enabled: boolean }
    legend: { enabled: boolean }
    scale_bar: { enabled: boolean }
    north_arrow: { enabled: boolean }
    elements: {
      map_frame: LayoutBoxForm
      title: LayoutTextElementForm
      legend: LayoutElementForm & { background: boolean }
      scale_bar: LayoutElementForm
      north_arrow: LayoutElementForm
    }
    legend_style: LegendStyleForm
  }
  map_view: MapViewForm
  style: {
    basin_boundary: { color: string; width_pt: number }
    basin_fill: { color: string; opacity: number }
    river_network: { color: string; width_pt: number }
  }
}

export interface LayoutBoxForm {
  x: number
  y: number
  width: number
  height: number
}

export interface LayoutElementForm extends LayoutBoxForm {
  enabled: boolean
}

export interface LayoutTextElementForm extends LayoutElementForm {
  font_size: number
  background: boolean
}

export interface LegendStyleForm {
  scale_symbols: boolean
  patch_width: number
  patch_height: number
  scale_to_patch: boolean
  item_gap: number
  class_gap: number
  layer_name_gap: number
  patch_gap: number
  text_gap: number
  min_font_size: number
  auto_fonts: boolean
  background: {
    enabled: boolean
    color: string
    gap_x: number
    gap_y: number
  }
  name_overrides: LegendNameOverrideForm[]
}

export interface MapViewForm {
  mode: 'auto' | 'auto_padding' | 'manual_extent'
  padding: {
    left: number
    right: number
    top: number
    bottom: number
  }
  extent: {
    xmin: number
    ymin: number
    xmax: number
    ymax: number
  }
}

export interface RenderResult {
  status: string
  output_png: string
  result_json?: string
  feature_counts?: { station_layers: number }
  warnings?: string[]
  elapsed_seconds?: number
  requested_output?: Record<string, unknown>
  requested_title?: string
  error?: string
}
