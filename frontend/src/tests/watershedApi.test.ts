import { beforeEach, describe, expect, it, vi } from 'vitest'
import { watershedApi } from '@/api/watershed'

const { postMock } = vi.hoisted(() => ({
  postMock: vi.fn()
}))

vi.mock('@/api/client', () => ({
  default: {
    post: postMock
  }
}))

describe('watershedApi', () => {
  beforeEach(() => {
    postMock.mockReset()
    postMock.mockResolvedValue({ data: { success: true } })
  })

  it('posts threshold payload to /api/watershed/acc_threshold', async () => {
    const payload = { dem_path: 'dem.tif', shapefile_path: 'basin.geojson', plan_name: '方案 01' }

    await watershedApi.calculateThreshold(payload)

    expect(postMock).toHaveBeenCalledWith('/api/watershed/acc_threshold', payload)
  })

  it('posts initial stream payload to /api/watershed/step0_streams', async () => {
    const payload = { dem_path: 'dem.tif', area_threshold: 35.95, random_folder_name: 'program', plan_name: '方案 01' }

    await watershedApi.initializeStreams(payload)

    expect(postMock).toHaveBeenCalledWith('/api/watershed/step0_streams', payload)
  })

  it('posts watershed generation payload to /api/watershed/step1', async () => {
    const payload = { dem_path: 'dem.tif', area_threshold: 35.95, random_folder_name: 'program', break_points: [], plan_name: '方案 01' }

    await watershedApi.generateWatersheds(payload)

    expect(postMock).toHaveBeenCalledWith('/api/watershed/step1', payload)
  })

  it('posts merge/delete payload to /api/watershed/step2', async () => {
    const payload = { operation: 'merge' as const, watershed_ids: ['Watershed1.1'], random_folder: 'program', plan_name: '方案 01' }

    await watershedApi.mergeOrDelete(payload)

    expect(postMock).toHaveBeenCalledWith('/api/watershed/step2', payload)
  })

  it('posts preview payload to /api/watershed/preview-layer', async () => {
    const payload = { path: 'basin.geojson' }

    await watershedApi.previewLayer(payload)

    expect(postMock).toHaveBeenCalledWith('/api/watershed/preview-layer', payload)
  })

  it('posts plan-name validation payload to /api/watershed/validate-plan-name', async () => {
    const payload = { plan_name: '方案 01' }

    await watershedApi.validatePlanName(payload)

    expect(postMock).toHaveBeenCalledWith('/api/watershed/validate-plan-name', payload)
  })
})
