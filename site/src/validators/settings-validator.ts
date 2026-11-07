import { z } from 'zod'

export const DWELL_MS = { min: 400, max: 1500, step: 100 } as const
export const VOLUME = { min: 0, max: 100, step: 10 } as const
export const BLINK_STEPS = { min: 1, max: 5 } as const

export const accessibilityValuesSchema = z.object({
  dwell_enabled: z.boolean(),
  dwell_ms: z.number().int().min(DWELL_MS.min).max(DWELL_MS.max),
  smoothing: z.enum(['low', 'medium', 'high']),
  blink_to_click: z.boolean(),
  blink_sensitivity: z.number().int().min(BLINK_STEPS.min).max(BLINK_STEPS.max),
  edge_scroll_enabled: z.boolean(),
  voice_volume: z.number().int().min(VOLUME.min).max(VOLUME.max),
})
export type AccessibilityValues = z.infer<typeof accessibilityValuesSchema>

export const accessibilitySettingsSchema = accessibilityValuesSchema.extend({
  is_default: z.boolean(),
  defaults: accessibilityValuesSchema,
})
export type AccessibilitySettings = z.infer<typeof accessibilitySettingsSchema>
