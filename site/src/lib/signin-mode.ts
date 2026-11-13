import { appClient } from '@/api/app-client'
import { signinModeSchema, type SigninMode } from '@/validators/accounts-validator'

/**
 * Which assistive sign-in the server wants: "legacy" (today's name tiles) or
 * "device_accounts" (accounts on this computer, file 07). Anything that goes
 * wrong means legacy, so the site never shows a half-working new screen.
 */
let cached: Promise<{ mode: SigninMode; smsEnabled: boolean }> | null = null

function ask() {
  cached ??= appClient
    .get('/signin/mode', { timeout: 8000 })
    .then((r) => {
      const parsed = signinModeSchema.parse(r.data)
      return { mode: parsed.mode, smsEnabled: parsed.sms_enabled }
    })
    .catch(() => {
      cached = null // ask again next time
      return { mode: 'legacy' as const, smsEnabled: false }
    })
  return cached
}

export function signinMode(): Promise<SigninMode> {
  return ask().then((answer) => answer.mode)
}

/** Can the server text codes (Semaphore set up)? False whenever anything goes wrong. */
export function smsEnabled(): Promise<boolean> {
  return ask().then((answer) => answer.smsEnabled)
}
