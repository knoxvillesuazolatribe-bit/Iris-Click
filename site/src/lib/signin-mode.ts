import { appClient } from '@/api/app-client'
import { signinModeSchema, type SigninMode } from '@/validators/accounts-validator'

/**
 * Which assistive sign-in the server wants: "legacy" (today's name tiles) or
 * "device_accounts" (accounts on this computer, file 07). Anything that goes
 * wrong means legacy, so the site never shows a half-working new screen.
 */
let cached: Promise<SigninMode> | null = null

export function signinMode(): Promise<SigninMode> {
  cached ??= appClient
    .get('/signin/mode', { timeout: 8000 })
    .then((r) => signinModeSchema.parse(r.data).mode)
    .catch(() => {
      cached = null // ask again next time
      return 'legacy' as const
    })
  return cached
}
