import { z } from 'zod'

export const calibrationStartSchema = z.object({
  profile_name: z
    .string()
    .trim()
    .min(1, 'Enter a name for this calibration')
    .max(60, 'Use 60 characters or fewer'),
  camera_index: z.number({ error: 'Choose a camera' }).int().min(0),
})
export type CalibrationStartInput = z.infer<typeof calibrationStartSchema>

const point2 = z.tuple([z.number(), z.number()])

export const eyeLineSchema = z.object({
  pointer: point2,
  line_centre: point2,
  left_eye: point2,
  right_eye: point2,
  left_iris: point2,
  right_iris: point2,
  eye_distance: z.number(),
  nose_bridge: point2.nullish(),
  nose_tip: point2.nullish(),
})
export type EyeLine = z.infer<typeof eyeLineSchema>

export const calibrationProfileSchema = z.object({
  id: z.string(),
  profile_name: z.string(),
  created_at: z.string(),
  feature_source: z.string(),
  accuracy_fraction: z.number(),
  low_accuracy: z.boolean(),
  sample_count: z.number().int(),
  screen: z.object({ width: z.number(), height: z.number() }).nullish(),
  camera_index: z.number().int().nullish(),
  deep_gaze_available: z.boolean(),
  candidates: z.array(z.object({ feature_source: z.string(), error_fraction: z.number() })),
})
export type CalibrationProfile = z.infer<typeof calibrationProfileSchema>

export const calibrationPointSchema = z.object({ x: z.number(), y: z.number() })
export type CalibrationPoint = z.infer<typeof calibrationPointSchema>

export const frameStatusSchema = z.object({
  type: z.literal('frame_status'),
  face_found: z.boolean(),
  eyes_open: z.boolean(),
  registered: z.boolean(),
  eye_line: eyeLineSchema.nullish(),
  distance_advice: z.enum(['closer', 'back']).nullish(),
  guidance: z.string().nullish(),
  pupils_detected: z.boolean(),
  deep_active: z.boolean(),
})
export type FrameStatus = z.infer<typeof frameStatusSchema>

export const calibrationResultSchema = z.object({
  type: z.literal('result'),
  status: z.enum(['success', 'failed']),
  message: z.string(),
  profile: calibrationProfileSchema.nullish(),
  worker_started: z.boolean(),
})
export type CalibrationResult = z.infer<typeof calibrationResultSchema>

export const calibrationServerMessageSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('ready'),
    points: z.array(calibrationPointSchema).min(1),
    deep_gaze_available: z.boolean(),
    max_point_retries: z.number().int(),
  }),
  frameStatusSchema,
  z.object({
    type: z.literal('point_result'),
    index: z.number().int(),
    status: z.enum(['accepted', 'retry', 'failed']),
    sample_count: z.number().int(),
    message: z.string().nullish(),
  }),
  calibrationResultSchema,
  z.object({ type: z.literal('error'), message: z.string(), fatal: z.boolean() }),
])
export type CalibrationServerMessage = z.infer<typeof calibrationServerMessageSchema>
