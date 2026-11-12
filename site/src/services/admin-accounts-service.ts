import { appClient } from '@/api/app-client'
import { deviceHeaders } from '@/lib/device'
import {
  adminAccountDetailSchema,
  adminAccountRowSchema,
  setupCodeMadeSchema,
  sharedSchema,
} from '@/validators/accounts-validator'

/** Admin side of accounts on this computer (server/app/api/routes/admin_accounts.py). */
export const adminAccountsService = {
  list: () => appClient.get('/admin/accounts').then((r) => adminAccountRowSchema.array().parse(r.data)),
  /** null when the person has no account on a computer yet. */
  detail: (userId: number) =>
    appClient
      .get(`/admin/accounts/${userId}`, { validateStatus: (s) => s === 200 || s === 404 })
      .then((r) => (r.status === 404 ? null : adminAccountDetailSchema.parse(r.data))),
  /** An 8-digit setup code, shown once. Admins never see or set a PIN. */
  resetPin: (userId: number) =>
    appClient.post(`/admin/accounts/${userId}/reset-pin`).then((r) => setupCodeMadeSchema.parse(r.data)),
  unlock: (userId: number) => appClient.post(`/admin/accounts/${userId}/unlock`),
  signOutEverywhere: (userId: number) => appClient.post(`/admin/accounts/${userId}/sign-out-everywhere`),
  setShared: (deviceId: string, shared: boolean) =>
    appClient
      .put('/admin/accounts/this-computer', { shared }, { headers: deviceHeaders(deviceId) })
      .then((r) => sharedSchema.parse(r.data).shared),
}
