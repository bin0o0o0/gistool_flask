import api from './client'
import type { ApiResponse, UploadKind, UploadResult } from '@/types'

// 上传接口只负责把浏览器文件交给后端保存，真正的 ArcPy 出图仍使用后端返回的本机路径。
export const uploadsApi = {
  upload(file: File, kind: UploadKind) {
    const formData = new FormData()
    formData.append('kind', kind)
    formData.append('file', file)
    return api.post<ApiResponse<UploadResult>>('/api/uploads', formData)
  },

  uploadMany(files: File[], kind: UploadKind) {
    const formData = new FormData()
    formData.append('kind', kind)
    for (const file of files) {
      // Shapefile 组件文件使用后端约定的 files 字段，一次请求整体上传。
      formData.append('files', file)
    }
    return api.post<ApiResponse<UploadResult>>('/api/uploads', formData)
  }
}
