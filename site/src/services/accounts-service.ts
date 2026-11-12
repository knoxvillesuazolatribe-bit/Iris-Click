import { isAxiosError } from 'axios'
import { appClient, errorMessage } from '@/api/app-client'
import { deviceHeaders } from '@/lib/device'
import {
  accountRefusalSchema,
  accountSessionSchema,
  tilesSchema,
  type AccountRefusal,
} from '@/validators/accounts-validator'

/** Accounts on this computer (file 07). Every call carries this computer's ID in a header. */
export const accountsService = {
  tiles: (deviceId: string) =>
    appClient.get('/accounts/tiles', { headers: deviceHeaders(deviceId) }).then((r) => tilesSchema.parse(r.data)),

  /** A tile: no PIN when this computer remembers the account. */
  signInWithTile: (deviceId: string, userId: number, pin?: string, remember = false) =>
    appClient
      .post('/accounts/signin', { user_id: userId, pin: pin ?? null, remember }, { headers: deviceHeaders(deviceId) })
      .then((r) => accountSessionSchema.parse(r.data)),

  remove: (deviceId: string, userId: number, pin?: string) =>
    appClient.post('/accounts/remove', { user_id: userId, pin: pin ?? null }, { headers: deviceHeaders(deviceId) }),

  signOut: (deviceId: string | null) =>
    appClient.post('/accounts/signout', null, { headers: deviceId ? deviceHeaders(deviceId) : {} }),
}

/** The server's refusal (code, message, tries left...), or a plain message when it was not reached. */
export function accountRefusal(error: unknown, fallback: string): AccountRefusal {
  if (isAxiosError(error)) {
    const parsed = accountRefusalSchema.safeParse(error.response?.data)
    if (parsed.success) return parsed.data
  }
  return { detail: errorMessage(error, fallback), code: 'unknown' }
}
