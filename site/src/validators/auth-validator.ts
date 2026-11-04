import { z } from 'zod'

export const sessionUserSchema = z.object({
  user_id: z.number().int(),
  full_name: z.string(),
  role: z.enum(['assistive_user', 'admin']),
})
export type SessionUser = z.infer<typeof sessionUserSchema>

export const adminLoginSchema = z.object({
  email: z.string().trim().min(1, 'Enter your email').email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
})
export type AdminLoginInput = z.infer<typeof adminLoginSchema>

export const assistiveTileSchema = z.object({
  user_id: z.number().int(),
  full_name: z.string(),
  last_calibrated_at: z.string().nullable(),
  // Decimal from the server arrives as a string, e.g. "95.77".
  accuracy_score: z.coerce.number().nullable(),
  continue_profile_id: z.string().nullable(),
  continue_unavailable_reason: z.string().nullable(),
})
export type AssistiveTile = z.infer<typeof assistiveTileSchema>

export const adminUserSchema = z.object({
  user_id: z.number().int(),
  full_name: z.string(),
  email: z.string().nullable(),
  role: z.enum(['assistive_user', 'admin']),
  status: z.enum(['active', 'inactive']),
  address: z.string().nullable(),
  barangay: z.string().nullable(),
  created_at: z.string(),
})
export type AdminUser = z.infer<typeof adminUserSchema>

export const assistiveCreateSchema = z.object({
  full_name: z
    .string()
    .trim()
    .min(1, 'Enter the full name')
    .max(100, 'Use 100 characters or fewer'),
  barangay: z.string().trim().max(100, 'Use 100 characters or fewer'),
  address: z.string().trim().max(255, 'Use 255 characters or fewer'),
})
export type AssistiveCreateInput = z.infer<typeof assistiveCreateSchema>
