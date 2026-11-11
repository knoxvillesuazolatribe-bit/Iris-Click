import { z } from 'zod'
import { apiClient } from '@/api/api-client'

/**
 * Desktop calibration: which calibration screen this computer uses, asked from
 * IrisClick Desktop (GET /api/desktop/calibration). Anything unexpected — Desktop
 * not answering, an older Desktop without this route — means "web": today's page.
 */
export type CalibrationSurface = 'web' | 'desktop'

const infoSchema = z.object({ surface: z.enum(['web', 'desktop']), linked: z.boolean().optional() })

export async function fetchCalibrationSurface(timeoutMs = 2500): Promise<CalibrationSurface> {
  try {
    const { data } = await apiClient.get('/desktop/calibration', { timeout: timeoutMs })
    return infoSchema.parse(data).surface
  } catch {
    return 'web'
  }
}
