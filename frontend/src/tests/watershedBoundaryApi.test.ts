import { beforeEach, describe, expect, it, vi } from 'vitest'
import { watershedBoundaryApi } from '@/api/watershedBoundary'

const { postMock } = vi.hoisted(() => ({
  postMock: vi.fn()
}))

vi.mock('@/api/client', () => ({
  default: {
    post: postMock
  }
}))

describe('watershedBoundaryApi', () => {
  beforeEach(() => {
    postMock.mockReset()
    postMock.mockResolvedValue({ data: { success: true } })
  })

  it('posts generation payload to /api/watershed-boundary/generate', async () => {
    const payload = {
      dem_path: 'D:\\work\\data\\data\\dem\\dem.tif',
      point: { x: 105.2, y: 27.06 },
      bbox: {
        min_x: 105.0,
        min_y: 26.9,
        max_x: 105.4,
        max_y: 27.2
      },
      snap_threshold: 2000
    }

    await watershedBoundaryApi.generate(payload)

    expect(postMock).toHaveBeenCalledWith('/api/watershed-boundary/generate', payload)
  })
})
