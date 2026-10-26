import { apiClient } from '@/api/api-client'
import { workerStatusSchema } from '@/validators/tracking-validator'

export const trackingService = {
  getStatus: () => apiClient.get('/tracking/status').then((r) => workerStatusSchema.parse(r.data)),
  start: (profileId?: string) =>
    apiClient
      .post('/tracking/start', { profile_id: profileId ?? null })
      .then((r) => workerStatusSchema.parse(r.data)),
  stop: () => apiClient.post('/tracking/stop').then((r) => workerStatusSchema.parse(r.data)),
}
