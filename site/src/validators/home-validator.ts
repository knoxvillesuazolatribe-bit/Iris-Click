import { z } from 'zod'

export const gestureSchema = z.object({ gesture: z.string(), action: z.string() })
export type Gesture = z.infer<typeof gestureSchema>

export const homeSchema = z.object({
  full_name: z.string(),
  gestures: z.array(gestureSchema),
})
export type Home = z.infer<typeof homeSchema>

export const trackingViewSchema = z.object({
  state: z.enum(['active', 'paused', 'inactive']),
  status_text: z.string().nullable(),
  running_profile_is_mine: z.boolean().nullable(),
  started_at: z.string().nullable(),
  calibration: z
    .object({
      profile_id: z.string(),
      profile_name: z.string(),
      calibrated_at: z.string().nullable(),
      accuracy_score: z.coerce.number().nullable(),
    })
    .nullable(),
  calibration_unavailable_reason: z.string().nullable(),
  live: z
    .object({
      status: z.string(),
      kind: z.string(),
      paused: z.boolean(),
      gaze: z
        .object({ x: z.number(), y: z.number(), screen_w: z.number(), screen_h: z.number() })
        .nullable(),
      winks: z.object({ left: z.number(), right: z.number() }),
    })
    .nullable(),
})
export type TrackingView = z.infer<typeof trackingViewSchema>
