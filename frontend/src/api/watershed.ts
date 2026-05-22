import api from './client'
import type {
  WatershedPlanNameValidationPayload,
  WatershedPlanNameValidationResponse,
  WatershedPreviewPayload,
  WatershedPreviewResponse,
  WatershedStep0Payload,
  WatershedStep0Response,
  WatershedStep1Payload,
  WatershedStep1Response,
  WatershedStep2Payload,
  WatershedStep2Response,
  WatershedThresholdPayload,
  WatershedThresholdResponse
} from '@/types'

export const watershedApi = {
  calculateThreshold(payload: WatershedThresholdPayload) {
    return api.post<WatershedThresholdResponse>('/api/watershed/acc_threshold', payload)
  },

  initializeStreams(payload: WatershedStep0Payload) {
    return api.post<WatershedStep0Response>('/api/watershed/step0_streams', payload)
  },

  generateWatersheds(payload: WatershedStep1Payload) {
    return api.post<WatershedStep1Response>('/api/watershed/step1', payload)
  },

  mergeOrDelete(payload: WatershedStep2Payload) {
    return api.post<WatershedStep2Response>('/api/watershed/step2', payload)
  },

  previewLayer(payload: WatershedPreviewPayload) {
    return api.post<WatershedPreviewResponse>('/api/watershed/preview-layer', payload)
  },

  validatePlanName(payload: WatershedPlanNameValidationPayload) {
    return api.post<WatershedPlanNameValidationResponse>('/api/watershed/validate-plan-name', payload)
  }
}
