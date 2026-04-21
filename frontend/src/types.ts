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
    legend: { enabled: boolean }
    scale_bar: { enabled: boolean }
  }
  style: {
    basin_boundary: { color: string; width_pt: number }
    basin_fill: { color: string; opacity: number }
    river_network: { color: string; width_pt: number }
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
