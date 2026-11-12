import { isAxiosError } from 'axios'
import { appClient, errorMessage } from '@/api/app-client'
import { deviceHeaders } from '@/lib/device'
import {
  accountRefusalSchema,
  accountSessionSchema,
  canSignUpSchema,
  codeSentSchema,
  setupCodeSchema,
  thisComputerSchema,
  ticketSchema,
  tilesSchema,
  usernameCheckSchema,
  type AccountRefusal,
} from '@/validators/accounts-validator'

/** Accounts on this computer (file 07). Every call carries this computer's ID in a header. */
export const accountsService = {
  tiles: (deviceId: string) =>
    appClient.get('/accounts/tiles', { headers: deviceHeaders(deviceId) }).then((r) => tilesSchema.parse(r.data)),

  thisComputer: (deviceId: string) =>
    appClient.get('/accounts/this-computer', { headers: deviceHeaders(deviceId) })
      .then((r) => thisComputerSchema.parse(r.data)),

  /** A tile: no PIN when this computer remembers the account. */
  signInWithTile: (deviceId: string, userId: number, pin?: string, remember = false) =>
    appClient
      .post('/accounts/signin', { user_id: userId, pin: pin ?? null, remember }, { headers: deviceHeaders(deviceId) })
      .then((r) => accountSessionSchema.parse(r.data)),

  remove: (deviceId: string, userId: number, pin?: string) =>
    appClient.post('/accounts/remove', { user_id: userId, pin: pin ?? null }, { headers: deviceHeaders(deviceId) }),

  signOut: (deviceId: string | null) =>
    appClient.post('/accounts/signout', null, { headers: deviceId ? deviceHeaders(deviceId) : {} }),

  // ---------- SMS (Phase 5): verify the mobile number, Forgot PIN ----------
  mobileSend: (deviceId: string, mobileNumber: string) =>
    appClient.post('/accounts/mobile/send', { mobile_number: mobileNumber }, { headers: deviceHeaders(deviceId) })
      .then((r) => codeSentSchema.parse(r.data)),
  mobileVerify: (deviceId: string, mobileNumber: string, code: string) =>
    appClient.post('/accounts/mobile/verify', { mobile_number: mobileNumber, code }, { headers: deviceHeaders(deviceId) })
      .then((r) => ticketSchema.parse(r.data).ticket),
  /** Signed in: mark the number verified (after the account was made). */
  mobileConfirm: (deviceId: string, mobileTicket: string) =>
    appClient.post('/accounts/mobile/confirm', { mobile_ticket: mobileTicket }, { headers: deviceHeaders(deviceId) }),
  forgotSend: (deviceId: string, userId: number) =>
    appClient.post('/accounts/forgot-pin/send', { user_id: userId }, { headers: deviceHeaders(deviceId) })
      .then((r) => codeSentSchema.parse(r.data)),
  forgotVerify: (deviceId: string, userId: number, code: string) =>
    appClient.post('/accounts/forgot-pin/verify', { user_id: userId, code }, { headers: deviceHeaders(deviceId) })
      .then((r) => ticketSchema.parse(r.data).ticket),
  forgotComplete: (deviceId: string, ticket: string, pin: string, pinConfirm: string, remember: boolean) =>
    appClient.post('/accounts/forgot-pin/complete', { ticket, pin, pin_confirm: pinConfirm, remember },
      { headers: deviceHeaders(deviceId) }).then((r) => accountSessionSchema.parse(r.data)),

  /** May this computer still make a new account today? Asked before the new person calibrates. */
  canSignUp: (deviceId: string) =>
    appClient
      .get('/accounts/can-sign-up', { headers: deviceHeaders(deviceId) })
      .then((r) => canSignUpSchema.parse(r.data)),
  usernameCheck: (deviceId: string, username: string) =>
    appClient
      .post('/accounts/username-check', { username }, { headers: deviceHeaders(deviceId) })
      .then((r) => usernameCheckSchema.parse(r.data)),

  signUp: (deviceId: string, input: SignupInput) =>
    appClient
      .post('/accounts/signup', { ...input, consent: true }, { headers: deviceHeaders(deviceId) })
      .then((r) => accountSessionSchema.parse(r.data)),

  /** PDAO's 8-digit setup code: a short ticket for the next screens. */
  redeemCode: (deviceId: string, code: string) =>
    appClient.post('/accounts/setup-code', { code }, { headers: deviceHeaders(deviceId) })
      .then((r) => setupCodeSchema.parse(r.data)),

  completeSetup: (deviceId: string, input: SetupCompleteInput) =>
    appClient.post('/accounts/setup-complete', { ...input, consent: true }, { headers: deviceHeaders(deviceId) })
      .then((r) => accountSessionSchema.parse(r.data)),

  /** "I already have an account": username + PIN, which also adds the account to this computer. */
  signInWithUsername: (deviceId: string, username: string, pin: string, remember = false) =>
    appClient
      .post('/accounts/signin', { username, pin, remember }, { headers: deviceHeaders(deviceId) })
      .then((r) => accountSessionSchema.parse(r.data)),
}

export interface SetupCompleteInput {
  ticket: string
  pin: string
  pin_confirm: string
  username?: string
  mobile_number?: string
}

export interface SignupInput {
  username: string
  mobile_number: string
  pin: string
  pin_confirm: string
  remember: boolean
}

/** The server's refusal (code, message, tries left...), or a plain message when it was not reached. */
export function accountRefusal(error: unknown, fallback: string): AccountRefusal {
  if (isAxiosError(error)) {
    const parsed = accountRefusalSchema.safeParse(error.response?.data)
    if (parsed.success) return parsed.data
  }
  return { detail: errorMessage(error, fallback), code: 'unknown' }
}
