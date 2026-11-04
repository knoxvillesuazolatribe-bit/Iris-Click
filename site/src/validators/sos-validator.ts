import { z } from 'zod'

const PHONE = /^\+?[0-9][0-9 -]{5,18}[0-9]$/

export const sosContactSchema = z.object({
  contact_id: z.number().int(),
  contact_name: z.string(),
  contact_number: z.string().nullable(),
  email_address: z.string().nullable(),
  relationship: z.string().nullable(),
})
export type SosContact = z.infer<typeof sosContactSchema>

export const sosContactFormSchema = z
  .object({
    contact_name: z.string().trim().min(1, 'Enter a name.').max(100),
    contact_number: z
      .string()
      .trim()
      .max(30)
      .refine((v) => v === '' || PHONE.test(v), 'Enter a mobile number like 0917 123 4567 or +63 917 123 4567.'),
    email_address: z
      .string()
      .trim()
      .max(255)
      .refine((v) => v === '' || z.email().safeParse(v).success, 'Enter a valid email address.'),
    relationship: z.string().trim().max(50),
  })
  .refine((v) => v.contact_number !== '' || v.email_address !== '', {
    message: 'Add a mobile number or an email so SOS can reach this contact.',
    path: ['email_address'],
  })
export type SosContactForm = z.infer<typeof sosContactFormSchema>

export const sosOverviewSchema = z.object({
  contacts: z.array(sosContactSchema),
  location_text: z.string().nullable(),
  email_configured: z.boolean(),
  sms_configured: z.boolean(),
})
export type SosOverview = z.infer<typeof sosOverviewSchema>

export const alertStatusSchema = z.object({
  contact_name: z.string(),
  relationship: z.string().nullable(),
  channel: z.enum(['email', 'sms']),
  recipient: z.string().nullable(),
  status: z.enum(['pending', 'sent', 'failed', 'cancelled']),
  detail: z.string().nullable(),
})
export type AlertStatus = z.infer<typeof alertStatusSchema>

export const sosActivationSchema = z.object({
  activation_id: z.string(),
  activated_at: z.string(),
  location_text: z.string().nullable(),
  total: z.number().int(),
  sent: z.number().int(),
  failed: z.number().int(),
  pending: z.number().int(),
  alerts: z.array(alertStatusSchema),
})
export type SosActivation = z.infer<typeof sosActivationSchema>
