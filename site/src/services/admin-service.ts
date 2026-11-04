import { isAxiosError } from 'axios'
import { appClient, errorMessage } from '@/api/app-client'
import {
  adminUserDetailSchema,
  adminUserRowSchema,
  appInfoSchema,
  dashboardSchema,
  globalDefaultsSchema,
  logPageSchema,
  reportSchema,
  systemSchema,
  testResultSchema,
  type LogTab,
  type ProfileForm,
  type ReportType,
} from '@/validators/admin-validator'
import { sosContactSchema, type SosContactForm } from '@/validators/sos-validator'
import { accessibilitySettingsSchema, type AccessibilityValues } from '@/validators/settings-validator'

export interface ReportQuery {
  date_from: string
  date_to: string
  user_id?: number | null
  include_text?: boolean
}

const contactBody = (form: SosContactForm) => ({
  contact_name: form.contact_name,
  contact_number: form.contact_number || null,
  email_address: form.email_address || null,
  relationship: form.relationship || null,
})

const reportParams = (q: ReportQuery) => ({
  date_from: q.date_from,
  date_to: q.date_to,
  ...(q.user_id ? { user_id: q.user_id } : {}),
  ...(q.include_text ? { include_text: true } : {}),
})

/** Admin module; every call needs an admin session. */
export const adminService = {
  dashboard: () => appClient.get('/admin/dashboard').then((r) => dashboardSchema.parse(r.data)),

  users: () => appClient.get('/admin/users').then((r) => adminUserRowSchema.array().parse(r.data)),
  user: (id: number) => appClient.get(`/admin/users/${id}`).then((r) => adminUserDetailSchema.parse(r.data)),
  updateProfile: (id: number, form: ProfileForm) =>
    appClient
      .put(`/admin/users/${id}`, { full_name: form.full_name, address: form.address || null, barangay: form.barangay || null })
      .then((r) => adminUserRowSchema.parse(r.data)),
  setStatus: (id: number, status: 'active' | 'inactive') =>
    appClient.post(`/admin/users/${id}/status`, { status }).then((r) => adminUserRowSchema.parse(r.data)),
  saveUserSettings: (id: number, values: AccessibilityValues) =>
    appClient.put(`/admin/users/${id}/settings`, values).then((r) => accessibilitySettingsSchema.parse(r.data)),
  resetUserSettings: (id: number) =>
    appClient.post(`/admin/users/${id}/settings/reset`).then((r) => accessibilitySettingsSchema.parse(r.data)),
  addContact: (id: number, form: SosContactForm) =>
    appClient.post(`/admin/users/${id}/contacts`, contactBody(form)).then((r) => sosContactSchema.parse(r.data)),
  updateContact: (id: number, contactId: number, form: SosContactForm) =>
    appClient
      .put(`/admin/users/${id}/contacts/${contactId}`, contactBody(form))
      .then((r) => sosContactSchema.parse(r.data)),
  deleteContact: (id: number, contactId: number) =>
    appClient.delete(`/admin/users/${id}/contacts/${contactId}`).then(() => undefined),

  defaults: () => appClient.get('/admin/settings/defaults').then((r) => globalDefaultsSchema.parse(r.data)),
  saveDefaults: (values: AccessibilityValues) =>
    appClient.put('/admin/settings/defaults', values).then((r) => globalDefaultsSchema.parse(r.data)),
  resetDefaults: () => appClient.post('/admin/settings/defaults/reset').then((r) => globalDefaultsSchema.parse(r.data)),

  system: () => appClient.get('/admin/settings/system').then((r) => systemSchema.parse(r.data)),
  saveAppName: (appName: string) =>
    appClient.put('/admin/settings/system/app-name', { app_name: appName }).then((r) => systemSchema.parse(r.data)),
  testEmail: (to: string) =>
    appClient.post('/admin/settings/system/test-email', { to }).then((r) => testResultSchema.parse(r.data)),
  testSms: () => appClient.post('/admin/settings/system/test-sms').then((r) => testResultSchema.parse(r.data)),

  logs: (tab: LogTab, page: number, dateFrom: string, dateTo: string) =>
    appClient
      .get('/admin/logs', { params: { tab, page, ...(dateFrom ? { date_from: dateFrom } : {}), ...(dateTo ? { date_to: dateTo } : {}) } })
      .then((r) => logPageSchema.parse(r.data)),

  report: (type: ReportType, q: ReportQuery) =>
    appClient.get(`/admin/reports/${type}`, { params: reportParams(q) }).then((r) => reportSchema.parse(r.data)),

  /** Downloads the PDF; resolves with its file name and size once the file is really received. */
  exportPdf: async (type: ReportType, q: ReportQuery): Promise<{ fileName: string; bytes: number }> => {
    try {
      const r = await appClient.get(`/admin/reports/${type}/pdf`, { params: reportParams(q), responseType: 'blob' })
      const blob = r.data as Blob
      if (blob.type !== 'application/pdf' || blob.size === 0) throw new Error('The server did not send a PDF.')
      const match = /filename="([^"]+)"/.exec(String(r.headers['content-disposition'] ?? ''))
      const fileName = match?.[1] ?? `${type}_report.pdf`
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = fileName
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
      return { fileName, bytes: blob.size }
    } catch (err) {
      // A failed blob request carries its JSON error as a Blob; read the real reason.
      if (isAxiosError(err) && err.response?.data instanceof Blob) {
        const text = await err.response.data.text()
        let detail: unknown
        try {
          detail = JSON.parse(text).detail
        } catch {
          detail = undefined
        }
        throw new Error(typeof detail === 'string' ? detail : errorMessage(err, 'The PDF could not be made.'))
      }
      throw err instanceof Error && !isAxiosError(err) ? err : new Error(errorMessage(err, 'The PDF could not be made.'))
    }
  },
}

export const appInfoService = {
  get: () => appClient.get('/app-info').then((r) => appInfoSchema.parse(r.data)),
}
