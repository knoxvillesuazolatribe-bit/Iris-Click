import { z } from 'zod'
import { appClient } from '@/api/app-client'
import { isGazeModel, type GazeModel } from '@/online-gaze/regression'

const savedSchema = z.object({
  calibration_id: z.number(),
  calibrated_at: z.string(),
  accuracy_score: z.number().nullable(),
  low_accuracy: z.boolean(),
  model: z.custom<GazeModel>(isGazeModel, 'Saved calibration is damaged.'),
  viewport: z.object({ w: z.number(), h: z.number() }).nullable().optional(),
})

export type SavedOnlineCalibration = z.infer<typeof savedSchema>

export interface OnlineCalibrationResult {
  status: 'Successful' | 'Failed'
  error_fraction: number | null
  sample_count: number
  reason?: 'dot_not_clear' | 'fit_failed' | 'not_accurate_enough'
  model?: GazeModel
  viewport?: { w: number; h: number }
}

/** Online (browser) calibrations: server/app/cloud/calibration.py. */
export const onlineCalibrationService = {
  latest: () =>
    appClient.get('/me/online-calibration').then((r) => (r.data === null ? null : savedSchema.parse(r.data))),
  save: (result: OnlineCalibrationResult) =>
    appClient.post('/me/online-calibration', result).then((r) => (r.data === null ? null : savedSchema.parse(r.data))),
}
