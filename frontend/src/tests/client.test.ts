import { describe, expect, it } from 'vitest'
import { AxiosError } from 'axios'
import { getApiErrorMessage } from '@/api/client'

describe('getApiErrorMessage', () => {
  it('把 Vite 代理后端未启动的空 500 转成中文提示', () => {
    // Flask 没启动时，Vite 代理会返回空文本 500；这里要提示用户启动后端。
    const error = new AxiosError('Request failed with status code 500', undefined, undefined, undefined, {
      data: '',
      status: 500,
      statusText: 'Internal Server Error',
      headers: {},
      config: {} as never
    })

    expect(getApiErrorMessage(error)).toContain('后端服务不可用')
  })
})
