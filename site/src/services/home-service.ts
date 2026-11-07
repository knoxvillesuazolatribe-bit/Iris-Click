import { z } from 'zod'
import { appClient } from '@/api/app-client'
import { homeSchema, trackingViewSchema } from '@/validators/home-validator'

/** Home Suite and Gaze Tracking page; every call needs a signed-in assistive user. */
export const homeService = {
  getHome: () => appClient.get('/me/home').then((r) => homeSchema.parse(r.data)),
  getTracking: () => appClient.get('/me/tracking').then((r) => trackingViewSchema.parse(r.data)),
  startTracking: () =>
    appClient.post('/me/tracking/start').then((r) => trackingViewSchema.parse(r.data)),
  stopTracking: () =>
    appClient.post('/me/tracking/stop').then((r) => trackingViewSchema.parse(r.data)),
}

/** Stops and starts tracking with the user's calibration so new settings take effect. */
export const restartTracking = () =>
  appClient.post('/me/tracking/restart').then((r) => trackingViewSchema.parse(r.data))

const appSchema = z.object({ app_id: z.string(), label: z.string(), note: z.string().nullable() })
export type AppShortcut = z.infer<typeof appSchema>

/** App shortcuts (Phase 9): only apps found on this computer; the server opens them. */
export const appsService = {
  list: () => appClient.get('/me/apps').then((r) => appSchema.array().parse(r.data)),
  launch: (appId: string) =>
    appClient.post(`/me/apps/${appId}/launch`).then((r) => z.object({ launched: z.boolean(), label: z.string() }).parse(r.data)),
}
