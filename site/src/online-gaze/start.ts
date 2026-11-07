import { settingsService } from '@/services/settings-service'
import { onlineCalibrationService } from '@/services/online-calibration-service'
import { DEFAULT_SETTINGS, gaze, toTrackerSettings, type TrackerSettings } from './engine'

export const loadTrackerSettings = (): Promise<TrackerSettings> =>
  settingsService.get().then(toTrackerSettings).catch(() => DEFAULT_SETTINGS)

/** Starts eye tracking with the signed-in user's saved online calibration. */
export async function startSavedTracking(): Promise<'started' | 'no_calibration'> {
  const saved = await onlineCalibrationService.latest()
  if (!saved) return 'no_calibration'
  await gaze.startTracking(saved.model, await loadTrackerSettings())
  return 'started'
}
