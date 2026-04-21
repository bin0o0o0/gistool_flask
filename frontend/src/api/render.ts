import api from './client'
import type { ApiResponse, RenderOptions, RenderResult } from '@/types'

// 出图相关 API：获取后端可选项、提交 ArcPy 渲染任务、把本机输出路径转换成图片预览 URL。
export const renderApi = {
  getOptions() {
    return api.get<ApiResponse<RenderOptions>>('/api/render-options')
  },

  render(payload: Record<string, unknown>) {
    return api.post<ApiResponse<RenderResult>>('/api/render', payload)
  },

  previewUrl(path: string) {
    return `/api/render/file?path=${encodeURIComponent(path)}`
  }
}
