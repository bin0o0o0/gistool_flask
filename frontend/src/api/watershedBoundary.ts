import api from './client'
import type {
  WatershedBoundaryDefaultsResponse,
  WatershedBoundaryGeneratePayload,
  WatershedBoundaryGenerateResponse
} from '@/types'

export const watershedBoundaryApi = {
  getDefaults() {
    return api.get<WatershedBoundaryDefaultsResponse>('/api/watershed-boundary/defaults')
  },

  generate(payload: WatershedBoundaryGeneratePayload) {
    return api.post<WatershedBoundaryGenerateResponse>('/api/watershed-boundary/generate', payload)
  }
}
