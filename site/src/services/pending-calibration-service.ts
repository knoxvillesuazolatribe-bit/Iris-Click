import { apiClient } from '@/api/api-client'
import { pendingCalibrationSchema } from '@/validators/accounts-validator'

/**
 * IrisClick Desktop (127.0.0.1): the calibration a new person does before their account
 * exists (build step 8). It stays on this computer with no owner until the account is
 * created, then is attached to it; Back or Cancel discards it.
 */
export const pendingCalibrationService = {
  /** Let the next calibration start with nobody linked (IrisClick Desktop allows 15 minutes). */
  allow: () => apiClient.post('/desktop/pending-calibration/allow'),
  current: () => apiClient.get('/desktop/pending-calibration').then((r) => pendingCalibrationSchema.parse(r.data)),
  /** After sign-up or sign-in, once IrisClick Desktop is linked to the account. */
  attach: (profileFileId: string | null) =>
    apiClient.post('/desktop/pending-calibration/attach', { profile_file_id: profileFileId }, { timeout: 20000 }),
  discard: (profileFileId: string | null) =>
    apiClient.post('/desktop/pending-calibration/discard', { profile_file_id: profileFileId }).catch(() => undefined),
}
