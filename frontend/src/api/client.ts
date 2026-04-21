import axios, { AxiosError } from 'axios'

// 统一的 Axios 客户端。开发时走 Vite 代理，部署时可通过环境变量指定后端地址。
const api = axios.create({
  // 开发时优先走 Vite 代理；部署时可以通过 VITE_API_BASE_URL 指向后端地址。
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 300000
})

// 把 Axios、普通 Error 和未知异常统一转成中文提示，组件里就不用重复判断异常类型。
export function getApiErrorMessage(error: unknown): string {
  if (error instanceof AxiosError) {
    const status = error.response?.status
    const data = error.response?.data as { message?: string } | string | undefined

    // Vite 代理找不到 Flask 后端时，经常会返回一个空的 500 文本响应。
    // 对用户来说真正的问题是“后端没启动”，不是上传文件本身坏了。
    if (status === 500 && (typeof data === 'string' || data == null)) {
      return '后端服务不可用：请确认 Flask 已在 http://localhost:5000 启动。'
    }

    if (error.code === 'ERR_NETWORK') {
      return '无法连接后端服务：请确认 Flask 已启动，并检查端口是否为 5000。'
    }

    if (typeof data === 'string' && data.trim()) {
      return data.trim()
    }
    if (data && typeof data === 'object') {
      return data.message || error.message || '接口请求失败'
    }
    return error.message || '接口请求失败'
  }
  if (error instanceof Error) {
    return error.message
  }
  return '发生未知错误'
}

export default api
