import { apiClient } from '@/api/api-client'
import { appClient } from '@/api/app-client'

/**
 * Hosted website only: tells IrisClick Desktop (on this PC, 127.0.0.1) who is signed in,
 * so calibrations are saved to the right person and tracking uses their settings.
 * The hosted server signs a 5-minute link token; the desktop app exchanges it.
 * Returns false when the desktop app is not running or not reachable (no error shown here;
 * the download page handles that).
 */
export async function linkDesktop(): Promise<boolean> {
  try {
    const { data } = await appClient.post<{ link_token: string }>('/me/desktop-link')
    await apiClient.post('/desktop/link', { link_token: data.link_token }, { timeout: 20000 })
    return true
  } catch {
    return false
  }
}
