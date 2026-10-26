import { apiClient } from '@/api/api-client'
import { cameraSchema } from '@/validators/camera-validator'

export const cameraService = {
  // Opens every camera on the server for a moment; takes a few seconds.
  getCameras: () => apiClient.get('/cameras').then((r) => cameraSchema.array().parse(r.data)),

  // `scan` busts the browser cache: each scan replaces the server's snapshot.
  snapshotUrl: (index: number, scan: number) =>
    `${apiClient.defaults.baseURL}/cameras/${index}/snapshot?scan=${scan}`,
}
