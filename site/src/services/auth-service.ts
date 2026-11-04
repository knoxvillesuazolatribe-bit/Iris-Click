import { appClient } from '@/api/app-client'
import {
  adminUserSchema,
  assistiveTileSchema,
  sessionUserSchema,
  type AdminLoginInput,
  type AssistiveCreateInput,
} from '@/validators/auth-validator'

export const authService = {
  me: () => appClient.get('/auth/me').then((r) => sessionUserSchema.parse(r.data)),
  adminLogin: (input: AdminLoginInput) =>
    appClient.post('/auth/admin/login', input).then((r) => sessionUserSchema.parse(r.data)),
  logout: () => appClient.post('/auth/logout'),
}

export const assistiveService = {
  getTiles: () =>
    appClient.get('/assistive/users').then((r) => assistiveTileSchema.array().parse(r.data)),
  select: (userId: number) =>
    appClient
      .post('/assistive/select', { user_id: userId })
      .then((r) => sessionUserSchema.parse(r.data)),
}

export const adminUsersService = {
  list: () => appClient.get('/admin/users').then((r) => adminUserSchema.array().parse(r.data)),
  createAssistive: (input: AssistiveCreateInput) =>
    appClient
      .post('/admin/users', {
        full_name: input.full_name,
        barangay: input.barangay || null,
        address: input.address || null,
      })
      .then((r) => adminUserSchema.parse(r.data)),
}
