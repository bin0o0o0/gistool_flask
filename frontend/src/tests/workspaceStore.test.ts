import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspaceStore } from '@/stores/workspace'

const mocks = vi.hoisted(() => ({
  readXlsxFile: vi.fn(),
  upload: vi.fn(),
  uploadMany: vi.fn()
}))

vi.mock('read-excel-file/browser', () => ({
  default: mocks.readXlsxFile
}))

vi.mock('@/api/uploads', () => ({
  uploadsApi: {
    upload: mocks.upload,
    uploadMany: mocks.uploadMany
  }
}))

describe('workspace store navigation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mocks.readXlsxFile.mockReset()
    mocks.upload.mockReset()
    mocks.uploadMany.mockReset()
  })

  it('starts on data step and can switch to stations', () => {
    const store = useWorkspaceStore()

    expect(store.activeStep).toBe('data')

    store.setActiveStep('stations')

    expect(store.activeStep).toBe('stations')
  })

  it('uses the approved manual layout defaults from frontend_20260423-8', () => {
    const store = useWorkspaceStore()

    expect(store.form.layout.elements.title).toMatchObject({
      x: 97.54,
      y: 188,
      width: 69.86,
      height: 11.18,
      font_size: 20
    })
    expect(store.form.layout.elements.legend).toMatchObject({
      x: 12.19,
      y: 45.34,
      width: 59.61,
      height: 77.22
    })
    expect(store.form.layout.legend_style.patch_width).toBe(12)
    expect(store.form.layout.legend_style.patch_height).toBe(6)
    expect(store.form.layout.legend_style.name_overrides).toEqual([])
    expect(store.form.map_view.padding).toMatchObject({
      left: 0.2408,
      right: 0.1808,
      top: 0.14,
      bottom: 0.14
    })
  })

  it('marks sidebar steps ready from configured form state', () => {
    const store = useWorkspaceStore()

    expect(store.stepReadiness.data).toBe(false)
    expect(store.stepReadiness.output).toBe(false)
    expect(store.stepReadiness.style).toBe(false)
    expect(store.stepReadiness.stations).toBe(false)

    store.uploads.template_project.result = fakeUpload('template.aprx')
    store.form.inputs.basin_boundaries.push({
      id: 'basin-1',
      upload: fakeUpload('basin.shp'),
      name: 'Basin 1',
      path: 'D:/uploads/basin.shp',
      style: {
        boundary_color: '#222222',
        boundary_width_pt: 1.2,
        fill_color: '#e6f0d4',
        fill_opacity: 0.45
      }
    })
    store.form.inputs.river_networks.push({
      id: 'river-1',
      upload: fakeUpload('river.shp'),
      name: 'River 1',
      path: 'D:/uploads/river.shp',
      style: {
        color: '#2f80ed',
        width_pt: 2.5
      }
    })
    store.form.inputs.station_layers[0].upload = fakeUpload('stations.xlsx', 'station_excel')

    expect(store.stepReadiness.data).toBe(true)
    expect(store.stepReadiness.stations).toBe(true)
    expect(store.stepReadiness.output).toBe(false)
    expect(store.stepReadiness.style).toBe(false)

    store.markStepConfigured('style')
    store.markStepConfigured('output')

    expect(store.stepReadiness.output).toBe(true)
    expect(store.stepReadiness.style).toBe(true)
  })

  it('creates per-point station configs from uploaded Excel rows', async () => {
    mocks.readXlsxFile.mockResolvedValue([
      {
        sheet: 'Sheet1',
        data: [
          ['lon', 'lat', 'name', 'alias'],
          [100, 30, 'Duplicate Station', 'A1'],
          [101, 31, 'Duplicate Station', 'A2']
        ]
      }
    ])
    mocks.upload.mockResolvedValue({
      data: {
        success: true,
        data: fakeUpload('stations.xlsx', 'station_excel')
      }
    })
    const store = useWorkspaceStore()
    const layerId = store.form.inputs.station_layers[0].id

    await store.uploadStationExcel(layerId, { name: 'stations.xlsx' } as File)

    const layer = store.form.inputs.station_layers[0]
    expect(layer.headers).toEqual(['lon', 'lat', 'name', 'alias'])
    expect(layer.points).toHaveLength(2)
    expect(layer.points.map((point) => point.row_number)).toEqual([2, 3])
    expect(layer.points.map((point) => point.display_name)).toEqual(['Duplicate Station', 'Duplicate Station'])

    store.setStationNameField(layerId, 'alias')

    expect(layer.name_field).toBe('alias')
    expect(layer.points.map((point) => point.display_name)).toEqual(['A1', 'A2'])
  })
})

function fakeUpload(name: string, kind: 'basin_boundary' | 'station_excel' = 'basin_boundary') {
  return {
    file_id: name,
    kind,
    original_name: name,
    path: `D:/uploads/${name}`,
    suffix: name.slice(name.lastIndexOf('.')),
    size_bytes: 1
  }
}
