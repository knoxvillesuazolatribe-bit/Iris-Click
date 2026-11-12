import { z } from 'zod'
import { adminUserSchema } from '@/validators/auth-validator'
import { sosContactSchema } from '@/validators/sos-validator'
import { accessibilitySettingsSchema, accessibilityValuesSchema } from '@/validators/settings-validator'

export const dashboardSchema = z.object({
  active_users: z.number(),
  active_users_week: z.number(),
  sos_events: z.number(),
  sos_events_week: z.number(),
  calibrations: z.number(),
  calibrations_week: z.number(),
})
export type Dashboard = z.infer<typeof dashboardSchema>

export const adminUserRowSchema = adminUserSchema.extend({
  calibration_count: z.number(),
  // Decimal from the server arrives as a string, e.g. "95.77".
  latest_accuracy: z.coerce.number().nullable(),
  last_calibrated_at: z.string().nullable(),
})
export type AdminUserRow = z.infer<typeof adminUserRowSchema>

export const adminUserDetailSchema = z.object({
  user: adminUserRowSchema,
  sos_location: z.string().nullable(),
  settings: accessibilitySettingsSchema,
  contacts: z.array(sosContactSchema),
})
export type AdminUserDetail = z.infer<typeof adminUserDetailSchema>

export const profileFormSchema = z.object({
  full_name: z.string().trim().min(1, 'Enter the full name').max(100, 'Use 100 characters or fewer'),
  address: z.string().trim().max(255, 'Use 255 characters or fewer'),
  barangay: z.string().trim().max(100, 'Use 100 characters or fewer'),
})
export type ProfileForm = z.infer<typeof profileFormSchema>

export const globalDefaultsSchema = accessibilityValuesSchema.extend({
  is_default: z.boolean(),
  env_defaults: accessibilityValuesSchema,
})
export type GlobalDefaults = z.infer<typeof globalDefaultsSchema>

export const systemSchema = z.object({
  app_name: z.string(),
  app_name_default: z.string(),
  email: z.object({
    configured: z.boolean(),
    host: z.string().nullable(),
    port: z.number(),
    security: z.string(),
    from_address: z.string().nullable(),
  }),
  sms_configured: z.boolean(),
})
export type SystemInfo = z.infer<typeof systemSchema>

export const testResultSchema = z.object({ sent: z.boolean(), detail: z.string() })
export type TestResult = z.infer<typeof testResultSchema>

export const LOG_TABS = ['all', 'calibration', 'sos', 'communication', 'screenshot', 'accounts'] as const
export type LogTab = (typeof LOG_TABS)[number]

export const logPageSchema = z.object({
  items: z.array(
    z.object({
      log_id: z.number(),
      activity_type: z.string(),
      user_name: z.string().nullable(),
      description: z.string().nullable(),
      log_date: z.string(),
    }),
  ),
  total: z.number(),
  page: z.number(),
  pages: z.number(),
})
export type LogPage = z.infer<typeof logPageSchema>

export const REPORT_TYPES = ['calibration', 'communication', 'sos'] as const
export type ReportType = (typeof REPORT_TYPES)[number]

export const reportSchema = z.object({
  type: z.string(),
  title: z.string(),
  columns: z.array(z.string()),
  rows: z.array(z.array(z.string())),
  date_from: z.string(),
  date_to: z.string(),
  user_name: z.string().nullable(),
  note: z.string().nullable(),
  // Feature C: totals (counts and averages only).
  summary: z.array(z.object({ label: z.string(), value: z.string() })).default([]),
})
export type Report = z.infer<typeof reportSchema>

export const appInfoSchema = z.object({ app_name: z.string() })
