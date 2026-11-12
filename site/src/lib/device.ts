import { apiClient } from '@/api/api-client'
import { deviceSchema } from '@/validators/accounts-validator'

/** The header the server reads the computer ID from (app/accounts/devices.py). */
export const DEVICE_HEADER = 'X-IrisClick-Device'

/**
 * This computer's ID, from IrisClick Desktop on 127.0.0.1 (GET /api/desktop/device).
 * Kept in memory only: never in a URL or browser storage. Null when IrisClick Desktop
 * does not answer (not installed, not running, or blocked by the browser).
 */
let known: string | null = null

export async function thisComputerId(timeoutMs = 2500): Promise<string | null> {
  if (known) return known
  try {
    const { data } = await apiClient.get('/desktop/device', { timeout: timeoutMs })
    known = deviceSchema.parse(data).device_id
    return known
  } catch {
    return null
  }
}

export function deviceHeaders(deviceId: string) {
  return { [DEVICE_HEADER]: deviceId }
}
