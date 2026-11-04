import { appClient } from '@/api/app-client'
import { accessibilitySettingsSchema, type AccessibilityValues } from '@/validators/settings-validator'

/** Accessibility Settings; every call needs a signed-in assistive user. */
export const settingsService = {
  get: () => appClient.get('/me/settings').then((r) => accessibilitySettingsSchema.parse(r.data)),
  save: (values: AccessibilityValues) =>
    appClient.put('/me/settings', values).then((r) => accessibilitySettingsSchema.parse(r.data)),
  reset: () => appClient.post('/me/settings/reset').then((r) => accessibilitySettingsSchema.parse(r.data)),
}
