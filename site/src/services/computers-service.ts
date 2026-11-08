import { isAxiosError } from 'axios'
import { z } from 'zod'
import { appClient } from '@/api/app-client'

/** Computer lock on the website (server/app/cloud/computers.py). */

const computerSchema = z.object({
  computer_id: z.number(),
  label: z.string(),
  status: z.enum(['approved', 'waiting', 'expired']),
  created_at: z.string(),
  approved_at: z.string().nullable(),
  last_used_at: z.string().nullable(),
  code_expires_at: z.string().nullable(),
  this_computer: z.boolean(),
})

const computerListSchema = z.object({ lock_on: z.boolean(), computers: computerSchema.array() })
const linkSchema = z.object({ code: z.string(), path: z.string(), expires_at: z.string() })
const claimSchema = z.object({ full_name: z.string() })

export type ApprovedComputer = z.infer<typeof computerSchema>
export type ComputerList = z.infer<typeof computerListSchema>
export type ApprovalLink = z.infer<typeof linkSchema>

/** The server's answer when this computer, or this name, is not approved here. */
export const NOT_APPROVED_CODE = 'computer_not_approved'

export function isNotApproved(error: unknown): boolean {
  return isAxiosError(error) && error.response?.data?.code === NOT_APPROVED_CODE
}

export const computersService = {
  list: (userId: number) =>
    appClient.get(`/admin/users/${userId}/computers`).then((r) => computerListSchema.parse(r.data)),
  makeLink: (userId: number, label: string) =>
    appClient.post(`/admin/users/${userId}/computers/link`, { label }).then((r) => linkSchema.parse(r.data)),
  approveHere: (userId: number, label: string) =>
    appClient.post(`/admin/users/${userId}/computers/this`, { label }).then((r) => computerSchema.parse(r.data)),
  remove: (userId: number, computerId: number) =>
    appClient.delete(`/admin/users/${userId}/computers/${computerId}`).then(() => undefined),
  claim: (code: string) =>
    appClient.post('/cloud/computers/claim', { code }).then((r) => claimSchema.parse(r.data)),
}
