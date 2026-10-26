import { z } from 'zod'

export const cameraSchema = z.object({
  index: z.number().int(),
  available: z.boolean(),
  in_use: z.boolean(),
  width: z.number().int(),
  height: z.number().int(),
  brightness: z.number(),
  face_found: z.boolean(),
  has_snapshot: z.boolean(),
  selected: z.boolean(),
})
export type Camera = z.infer<typeof cameraSchema>
