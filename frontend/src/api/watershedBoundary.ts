import api from './client'
import type { WatershedBoundaryGeneratePayload, WatershedBoundaryGenerateResponse } from '@/types'

export const watershedBoundaryApi = {
  generate(payload: WatershedBoundaryGeneratePayload) {
    return api.post<WatershedBoundaryGenerateResponse>('/api/watershed-boundary/generate', payload)
  }
}
