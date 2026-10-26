import { z } from 'zod'

export const workerStatusSchema = z.object({
  running: z.boolean(),
  pid: z.number().int().nullish(),
  profile_id: z.string().nullish(),
  started_at: z.string().nullish(),
  message: z.string().nullish(),
})
export type WorkerStatus = z.infer<typeof workerStatusSchema>
