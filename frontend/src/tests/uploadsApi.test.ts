import { beforeEach, describe, expect, it, vi } from 'vitest'
import { uploadsApi, watershedUploadsApi } from '@/api/uploads'

const { postMock } = vi.hoisted(() => ({
  postMock: vi.fn()
}))

vi.mock('@/api/client', () => ({
  default: {
    post: postMock
  }
}))

function file(name: string) {
  return new File(['fake'], name)
}

describe('uploadsApi', () => {
  beforeEach(() => {
    postMock.mockReset()
    postMock.mockResolvedValue({ data: { success: true } })
  })

  it('单文件上传使用 file 字段', async () => {
    await uploadsApi.upload(file('template.aprx'), 'template_project')

    const formData = postMock.mock.calls[0][1] as FormData
    expect(postMock).toHaveBeenCalledWith('/api/uploads', expect.any(FormData))
    expect(formData.get('kind')).toBe('template_project')
    expect((formData.get('file') as File).name).toBe('template.aprx')
    expect(formData.getAll('files')).toHaveLength(0)
  })

  it('Shapefile 组件多选上传使用 files 字段', async () => {
    await uploadsApi.uploadMany([file('basin.shp'), file('basin.shx'), file('basin.dbf')], 'basin_boundary')

    const formData = postMock.mock.calls[0][1] as FormData
    expect(formData.get('kind')).toBe('basin_boundary')
    expect(formData.get('file')).toBeNull()
    expect(formData.getAll('files').map((item) => (item as File).name)).toEqual([
      'basin.shp',
      'basin.shx',
      'basin.dbf'
    ])
  })

  it('DEM raster upload uses dem kind and the file field', async () => {
    await uploadsApi.upload(file('dem.tif'), 'dem')

    const formData = postMock.mock.calls[0][1] as FormData
    expect(postMock).toHaveBeenCalledWith('/api/uploads', expect.any(FormData))
    expect(formData.get('kind')).toBe('dem')
    expect((formData.get('file') as File).name).toBe('dem.tif')
  })

  it('watershed uploads route to the watershed-specific endpoint', async () => {
    await watershedUploadsApi.upload(file('dem.tif'), 'dem')

    const formData = postMock.mock.calls[0][1] as FormData
    expect(postMock).toHaveBeenCalledWith('/api/watershed/uploads', expect.any(FormData))
    expect(formData.get('kind')).toBe('dem')
    expect((formData.get('file') as File).name).toBe('dem.tif')
  })
})
