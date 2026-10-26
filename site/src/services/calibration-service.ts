import { apiClient } from '@/api/api-client'
import { openJsonSocket, type JsonSocketHandlers } from '@/api/websocket-client'
import {
  calibrationProfileSchema,
  type CalibrationStartInput,
} from '@/validators/calibration-validator'

export interface ScreenSize {
  width: number
  height: number
}

export interface CalibrationSocket {
  start: (input: CalibrationStartInput, screen: ScreenSize) => void
  collect: (index: number) => void
  cancel: () => void
  close: () => void
}

export const calibrationService = {
  getProfiles: () =>
    apiClient
      .get('/calibration-profiles')
      .then((r) => calibrationProfileSchema.array().parse(r.data)),

  getLatestProfile: () =>
    apiClient
      .get('/calibration-profiles/latest')
      .then((r) => calibrationProfileSchema.parse(r.data)),

  openSession: (handlers: JsonSocketHandlers): CalibrationSocket => {
    const socket = openJsonSocket('/ws/calibration', handlers)
    return {
      start: (input, screen) => socket.send({ type: 'start', ...input, screen }),
      collect: (index) => socket.send({ type: 'collect', index }),
      cancel: () => socket.send({ type: 'cancel' }),
      close: socket.close,
    }
  },
}
