import { z } from 'zod'

/** Shapes of /api/signin/mode, /api/accounts/* and IrisClick Desktop's /api/desktop/device. */

export const signinModeSchema = z.object({
  mode: z.enum(['legacy', 'device_accounts']),
  sms_enabled: z.boolean().default(false),
})
export type SigninMode = z.infer<typeof signinModeSchema>['mode']

export const deviceSchema = z.object({ device_id: z.string().regex(/^[A-Za-z0-9_-]{32,64}$/) })

export const accountTileSchema = z.object({
  user_id: z.number().int(),
  username: z.string(),
  needs_pin: z.boolean(),
})
export type AccountTile = z.infer<typeof accountTileSchema>

export const tilesSchema = z.object({
  is_shared: z.boolean(),
  accounts: z.array(accountTileSchema),
})
export type Tiles = z.infer<typeof tilesSchema>

export const thisComputerSchema = z.object({ is_shared: z.boolean(), idle_minutes: z.number().int() })
export type ThisComputer = z.infer<typeof thisComputerSchema>

export const accountSessionSchema = z.object({
  user_id: z.number().int(),
  full_name: z.string(),
  username: z.string(),
  role: z.literal('assistive_user'),
})
export type AccountSession = z.infer<typeof accountSessionSchema>

export const usernameCheckSchema = z.object({
  available: z.boolean(),
  problem: z.string().nullable(),
  message: z.string().nullable(),
  suggestions: z.array(z.string()),
})
export type UsernameCheck = z.infer<typeof usernameCheckSchema>

export const pendingCalibrationSchema = z.object({
  pending: z.boolean(),
  profile_file_id: z.string().nullable(),
  accuracy_score: z.number().nullable(),
  low_accuracy: z.boolean(),
})
export type PendingCalibration = z.infer<typeof pendingCalibrationSchema>

/** A refusal from /api/accounts: a plain message plus a stable code (and sometimes more). */
export const accountRefusalSchema = z.object({
  detail: z.string(),
  code: z.string(),
  tries_left: z.number().int().optional(),
  wait_seconds: z.number().int().optional(),
  suggestions: z.array(z.string()).optional(),
})
export type AccountRefusal = z.infer<typeof accountRefusalSchema>
