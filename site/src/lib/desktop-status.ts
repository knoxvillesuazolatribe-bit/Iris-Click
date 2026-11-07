import { z } from 'zod'
import { apiClient } from '@/api/api-client'

/** Hosted website: is IrisClick Desktop running on this PC, and is it up to date? */

const versionSchema = z.object({ app: z.string(), version: z.string() })
const latestSchema = z.object({ version: z.string(), download_url: z.url(), notes: z.string().optional() })

export type Latest = z.infer<typeof latestSchema>
export type DesktopStatus = { running: true; version: string } | { running: false }

export const FALLBACK_DOWNLOAD =
  'https://github.com/knoxvillesuazolatribe-bit/Iris-Click/releases/latest/download/IrisClick-Desktop-Setup.exe'

/** Asks the desktop app on 127.0.0.1. No answer: not installed, not running, or blocked by the browser. */
export async function checkDesktop(timeoutMs = 2500): Promise<DesktopStatus> {
  try {
    const { data } = await apiClient.get('/desktop/version', { timeout: timeoutMs })
    return { running: true, version: versionSchema.parse(data).version }
  } catch {
    return { running: false }
  }
}

/** The newest installer this website offers (public/desktop-latest.json). */
export async function latestDesktop(): Promise<Latest | null> {
  try {
    const response = await fetch('/desktop-latest.json', { cache: 'no-cache' })
    return latestSchema.parse(await response.json())
  } catch {
    return null
  }
}

/** True when version ``a`` is older than ``b`` (1.2.10 < 1.10.0). */
export function isOlder(a: string, b: string): boolean {
  const pa = a.split('.').map((n) => Number.parseInt(n, 10) || 0)
  const pb = b.split('.').map((n) => Number.parseInt(n, 10) || 0)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    if ((pa[i] ?? 0) !== (pb[i] ?? 0)) return (pa[i] ?? 0) < (pb[i] ?? 0)
  }
  return false
}

/** Which browser, for the right "allow access to this PC" steps. */
export function browserName(): 'brave' | 'edge' | 'chrome' | 'other' {
  const nav = navigator as Navigator & { brave?: unknown }
  if (nav.brave) return 'brave'
  if (/Edg\//.test(navigator.userAgent)) return 'edge'
  if (/Chrome\//.test(navigator.userAgent)) return 'chrome'
  return 'other'
}
