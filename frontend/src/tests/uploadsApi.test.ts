import { beforeEach, describe, expect, it, vi } from 'vitest'
import { uploadsApi } from '@/api/uploads'

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
})
