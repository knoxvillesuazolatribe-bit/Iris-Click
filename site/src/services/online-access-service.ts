import { z } from 'zod'
import { appClient } from '@/api/app-client'

const accessStatusSchema = z.object({
  online_copy: z.boolean(),
  ready: z.boolean(),
  access: z.boolean(),
})

export type AccessStatus = z.infer<typeof accessStatusSchema>

/** Site access code for the online copy (server/app/cloud/access.py). */
export const onlineAccessService = {
  status: () => appClient.get('/cloud/status').then((r) => accessStatusSchema.parse(r.data)),
  enter: (code: string) =>
    appClient.post('/cloud/access', { code }).then((r) => accessStatusSchema.parse(r.data)),
}
