import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import readXlsxFile from 'read-excel-file/browser'

import { getApiErrorMessage } from '@/api/client'
import { renderApi } from '@/api/render'
import { uploadsApi } from '@/api/uploads'
import { buildRenderPayload } from '@/utils/renderPayload'
import type {
  BasinLayerForm,
  RenderOptions,
  RenderResult,
  RiverLayerForm,
  StationLabelForm,
  StationLayerForm,
  StationPointForm,
  StationShape,
  StationSymbolForm,
  UploadKind,
  UploadedFileState,
  UploadResult,
  WorkspaceForm,
  WorkspaceStepId
} from '@/types'

type ConfigurableStepId = Exclude<WorkspaceStepId, 'data'>
type SheetRow = unknown[]

function defaultStationLayer(index = 1): StationLayerForm {
  return {
    id: crypto.randomUUID(),
    headers: [],
    sampleName: `Station ${index}`,
    sheet_name: 'Sheet1',
    x_field: 'lon',
    y_field: 'lat',
    name_field: 'name',
    layer_name: `StationLayer${index}`,
    symbol: {
      shape: index === 1 ? 'circle' : 'triangle',
      color_preset: index === 1 ? 'green' : 'red',
      color: index === 1 ? '#00a651' : '#ff0000',
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
}

const basinFillPalette = ['#e6f0d4', '#f6d7a7', '#d7ecf2', '#eadcf8', '#f4c6b8', '#d8ead8']
const riverColorPalette = ['#2f80ed', '#00a6c8', '#4f8a8b', '#1f5f99', '#6aaed6']

function defaultBasinLayer(upload: UploadResult, index: number): BasinLayerForm {
  return {
    id: crypto.randomUUID(),
    upload,
    name: `Basin ${index}`,
    path: upload.path,
    style: {
      boundary_color: '#222222',
      boundary_width_pt: 1.2,
      fill_color: basinFillPalette[(index - 1) % basinFillPalette.length],
      fill_opacity: 0.45
    }
  }
}

function defaultRiverLayer(upload: UploadResult, index: number): RiverLayerForm {
  return {
    id: crypto.randomUUID(),
    upload,
    name: `River ${index}`,
    path: upload.path,
    style: {
      color: riverColorPalette[(index - 1) % riverColorPalette.length],
      width_pt: 2.5
    }
  }
}

const defaultOptions: RenderOptions = {
  basemaps: ['Topographic'],
  label_positions: ['top_left', 'top', 'top_right', 'right', 'bottom_right', 'bottom', 'bottom_left', 'left'],
  station_symbol_shapes: ['circle', 'triangle', 'square', 'diamond', 'rectangle'],
  station_symbol_color_presets: {
    green: '#00a651',
    red: '#ff0000',
    blue: '#1f78ff',
    black: '#000000'
  }
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const options = ref<RenderOptions>(defaultOptions)
  const loadingOptions = ref(false)
  const rendering = ref(false)
  const error = ref('')
  const renderResult = ref<RenderResult | null>(null)
  const activeStep = ref<WorkspaceStepId>('data')
  const configuredSteps = ref<Record<ConfigurableStepId, boolean>>({
    output: false,
    style: false,
    stations: false
  })

  const uploads = ref<Record<Exclude<UploadKind, 'station_excel'>, UploadedFileState>>({
    template_project: { uploading: false },
    basin_boundary: { uploading: false },
    river_network: { uploading: false }
  })

  const form = ref<WorkspaceForm>({
    output_dir: `frontend_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}`,
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
      station_layers: [defaultStationLayer(1)]
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
        }
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
  })

  const payload = computed(() => buildRenderPayload(form.value))
  const payloadJson = computed(() => JSON.stringify(payload.value, null, 2))
  const stepReadiness = computed(() => ({
    data: Boolean(
      uploads.value.template_project.result &&
        form.value.inputs.basin_boundaries.length > 0 &&
        form.value.inputs.river_networks.length > 0
    ),
    output: Boolean(
      configuredSteps.value.output &&
        form.value.map_title &&
        form.value.output_dir &&
        form.value.output.width_px > 0 &&
        form.value.output.height_px > 0 &&
        form.value.output.dpi > 0
    ),
    style: Boolean(
      configuredSteps.value.style &&
        form.value.inputs.basin_boundaries.length > 0 &&
        form.value.inputs.river_networks.length > 0 &&
        form.value.inputs.basin_boundaries.every(
          (layer) =>
            layer.name &&
            layer.style.boundary_color &&
            layer.style.boundary_width_pt > 0 &&
            layer.style.fill_color &&
            layer.style.fill_opacity >= 0
        ) &&
        form.value.inputs.river_networks.every((layer) => layer.name && layer.style.color && layer.style.width_pt > 0)
    ),
    stations: form.value.inputs.station_layers.some((layer) => Boolean(layer.upload))
  }))
  const previewImageUrl = computed(() => {
    if (!renderResult.value?.output_png || renderResult.value.status !== 'succeeded') return ''
    return renderApi.previewUrl(renderResult.value.output_png)
  })

  async function fetchOptions() {
    loadingOptions.value = true
    try {
      const response = await renderApi.getOptions()
      if (response.data.success && response.data.data) {
        options.value = response.data.data
      }
    } catch (caught) {
      error.value = getApiErrorMessage(caught)
    } finally {
      loadingOptions.value = false
    }
  }

  async function uploadDataFiles(kind: Exclude<UploadKind, 'station_excel'>, files: File[]) {
    const primaryFile = files[0]
    if (!primaryFile) return

    uploads.value[kind].uploading = true
    uploads.value[kind].error = ''
    uploads.value[kind].result = undefined
    error.value = ''
    try {
      const results = await uploadDatasetFiles(files, kind)
      const latestResult = results[results.length - 1]
      uploads.value[kind].result = latestResult
      if (kind === 'template_project') form.value.template_project = latestResult.path
      if (kind === 'basin_boundary') results.forEach(addBasinLayer)
      if (kind === 'river_network') results.forEach(addRiverLayer)
    } catch (caught) {
      const message = getApiErrorMessage(caught)
      uploads.value[kind].error = message
      error.value = message
    } finally {
      uploads.value[kind].uploading = false
    }
  }

  async function uploadDataFile(kind: Exclude<UploadKind, 'station_excel'>, file: File) {
    await uploadDataFiles(kind, [file])
  }

  async function uploadStationExcel(layerId: string, file: File) {
    const layer = form.value.inputs.station_layers.find((item) => item.id === layerId)
    if (!layer) return
    error.value = ''
    try {
      const excelInfo = await readExcelInfo(file)
      const upload = await uploadFile(file, 'station_excel')
      layer.upload = upload
      layer.headers = excelInfo.headers
      layer.sampleName = excelInfo.sampleName || layer.sampleName
      layer.sheet_name = excelInfo.sheetName || 'Sheet1'
      layer.x_field = chooseField(excelInfo.headers, ['lon', 'lng', 'longitude', 'x'], layer.x_field)
      layer.y_field = chooseField(excelInfo.headers, ['lat', 'latitude', 'y'], layer.y_field)
      layer.name_field = chooseField(excelInfo.headers, ['name', 'station', 'station_name', 'Name'], layer.name_field)
      layer.points = buildStationPoints(layer, excelInfo.rows)
    } catch (caught) {
      error.value = getApiErrorMessage(caught)
    }
  }

  async function uploadFile(file: File, kind: UploadKind): Promise<UploadResult> {
    const response = await uploadsApi.upload(file, kind)
    if (!response.data.success || !response.data.data) {
      throw new Error(response.data.message || 'Upload failed')
    }
    return response.data.data
  }

  async function uploadDatasetFiles(files: File[], kind: Exclude<UploadKind, 'station_excel'>): Promise<UploadResult[]> {
    if (kind === 'template_project') {
      return [await uploadFile(files[0], kind)]
    }

    const shouldUseComponentUpload = isShapefileComponentSelection(files)
    if (shouldUseComponentUpload) {
      const response = await uploadsApi.uploadMany(files, kind)
      if (!response.data.success || !response.data.data) {
        throw new Error(response.data.message || 'Upload failed')
      }
      return [response.data.data]
    }

    const results: UploadResult[] = []
    for (const file of files) {
      results.push(await uploadFile(file, kind))
    }
    return results
  }

  function isShapefileComponentSelection(files: File[]) {
    const shapefileSuffixes = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.qix', '.xml']
    return files.some((file) => shapefileSuffixes.includes(fileSuffix(file.name)))
  }

  function fileSuffix(filename: string) {
    const dotIndex = filename.lastIndexOf('.')
    return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : ''
  }

  async function readExcelInfo(file: File) {
    const sheets = (await readXlsxFile(file)) as Array<{ sheet?: string; data?: SheetRow[] } | SheetRow>
    const firstSheet = sheets[0]
    const rows = Array.isArray((firstSheet as { data?: SheetRow[] })?.data)
      ? ((firstSheet as { sheet?: string; data: SheetRow[] }).data ?? [])
      : (sheets as SheetRow[])
    const headerRow = rows[0] || []
    const headers = headerRow.map((cell) => normalizeCellValue(cell)).filter(Boolean)
    const dataRows = rows.slice(1).filter((row) => row.some((cell) => normalizeCellValue(cell)))
    const firstValues = rowValues(headers, dataRows[0] || [])
    const sampleName = firstValues.name || firstValues.Name || firstValues.station || firstValues[headers[0]] || ''
    const sheetName = Array.isArray(firstSheet) ? 'Sheet1' : firstSheet?.sheet || 'Sheet1'
    return { sheetName, headers, sampleName, rows: dataRows }
  }

  function chooseField(headers: string[], candidates: string[], fallback: string) {
    const lowerMap = new Map(headers.map((header) => [header.toLowerCase(), header]))
    for (const candidate of candidates) {
      const matched = lowerMap.get(candidate.toLowerCase())
      if (matched) return matched
    }
    return headers.includes(fallback) ? fallback : headers[0] || fallback
  }

  function normalizeCellValue(value: unknown) {
    if (value === null || value === undefined) return ''
    if (value instanceof Date) return value.toISOString().slice(0, 10)
    return String(value).trim()
  }

  function rowValues(headers: string[], row: SheetRow) {
    return Object.fromEntries(headers.map((header, index) => [header, normalizeCellValue(row[index])]))
  }

  function cloneSymbol(symbol: StationSymbolForm): StationSymbolForm {
    return { ...symbol }
  }

  function cloneLabel(label: StationLabelForm): StationLabelForm {
    return { ...label }
  }

  function stationPointName(layer: StationLayerForm, values: Record<string, string>, rowNumber: number) {
    return values[layer.name_field] || values[layer.headers[0]] || `Row ${rowNumber}`
  }

  function buildStationPoints(layer: StationLayerForm, rows: SheetRow[]): StationPointForm[] {
    return rows.map((row, index) => {
      const rowNumber = index + 2
      const values = rowValues(layer.headers, row)
      const rawName = stationPointName(layer, values, rowNumber)
      return {
        row_number: rowNumber,
        raw_name: rawName,
        display_name: rawName,
        values,
        symbol: cloneSymbol(layer.symbol),
        label: cloneLabel(layer.label)
      }
    })
  }

  function refreshStationPointNames(layer: StationLayerForm) {
    layer.points.forEach((point) => {
      const rawName = stationPointName(layer, point.values, point.row_number)
      point.raw_name = rawName
      point.display_name = rawName
    })
    layer.sampleName = layer.points[0]?.display_name || layer.sampleName
  }

  function setStationNameField(layerId: string, field: string) {
    const layer = form.value.inputs.station_layers.find((item) => item.id === layerId)
    if (!layer) return
    layer.name_field = field
    refreshStationPointNames(layer)
  }

  function addStationLayer() {
    form.value.inputs.station_layers.push(defaultStationLayer(form.value.inputs.station_layers.length + 1))
  }

  function addBasinLayer(upload: UploadResult) {
    const layer = defaultBasinLayer(upload, form.value.inputs.basin_boundaries.length + 1)
    form.value.inputs.basin_boundaries.push(layer)
    form.value.inputs.basin_boundary = form.value.inputs.basin_boundaries[0]?.path || ''
  }

  function addRiverLayer(upload: UploadResult) {
    const layer = defaultRiverLayer(upload, form.value.inputs.river_networks.length + 1)
    form.value.inputs.river_networks.push(layer)
    form.value.inputs.river_network = form.value.inputs.river_networks[0]?.path || ''
  }

  function removeBasinLayer(id: string) {
    form.value.inputs.basin_boundaries = form.value.inputs.basin_boundaries.filter((layer) => layer.id !== id)
    form.value.inputs.basin_boundary = form.value.inputs.basin_boundaries[0]?.path || ''
  }

  function removeRiverLayer(id: string) {
    form.value.inputs.river_networks = form.value.inputs.river_networks.filter((layer) => layer.id !== id)
    form.value.inputs.river_network = form.value.inputs.river_networks[0]?.path || ''
  }

  function removeStationLayer(id: string) {
    if (form.value.inputs.station_layers.length <= 1) return
    form.value.inputs.station_layers = form.value.inputs.station_layers.filter((layer) => layer.id !== id)
  }

  function syncPresetColor(layer: StationLayerForm) {
    layer.symbol.color = options.value.station_symbol_color_presets[layer.symbol.color_preset] || layer.symbol.color
  }

  function syncPointPresetColor(point: StationPointForm) {
    point.symbol.color = options.value.station_symbol_color_presets[point.symbol.color_preset] || point.symbol.color
  }

  function setShape(layer: StationLayerForm, shape: StationShape) {
    layer.symbol.shape = shape
  }

  function applyLayerStyleToStationPoints(layerId: string) {
    const layer = form.value.inputs.station_layers.find((item) => item.id === layerId)
    if (!layer) return
    layer.points.forEach((point) => {
      point.symbol = cloneSymbol(layer.symbol)
      point.label = cloneLabel(layer.label)
    })
  }

  function resetStationPointStyle(layerId: string, rowNumber: number) {
    const layer = form.value.inputs.station_layers.find((item) => item.id === layerId)
    const point = layer?.points.find((item) => item.row_number === rowNumber)
    if (!layer || !point) return
    point.symbol = cloneSymbol(layer.symbol)
    point.label = cloneLabel(layer.label)
  }

  function setActiveStep(step: WorkspaceStepId) {
    activeStep.value = step
  }

  function markStepConfigured(step: ConfigurableStepId) {
    configuredSteps.value[step] = true
  }

  async function submitRender() {
    rendering.value = true
    error.value = ''
    renderResult.value = null
    try {
      const response = await renderApi.render(payload.value)
      if (!response.data.success || !response.data.data) {
        throw new Error(response.data.message || 'Render failed')
      }
      renderResult.value = response.data.data
    } catch (caught) {
      error.value = getApiErrorMessage(caught)
    } finally {
      rendering.value = false
    }
  }

  return {
    options,
    loadingOptions,
    rendering,
    error,
    renderResult,
    activeStep,
    configuredSteps,
    stepReadiness,
    uploads,
    form,
    payload,
    payloadJson,
    previewImageUrl,
    fetchOptions,
    uploadDataFile,
    uploadDataFiles,
    uploadStationExcel,
    removeBasinLayer,
    removeRiverLayer,
    addStationLayer,
    removeStationLayer,
    syncPresetColor,
    syncPointPresetColor,
    setShape,
    setStationNameField,
    applyLayerStyleToStationPoints,
    resetStationPointStyle,
    setActiveStep,
    markStepConfigured,
    submitRender
  }
})
