import { z } from 'zod'
import { openJsonSocket } from '@/api/websocket-client'

/**
 * Desktop calibration: live link to IrisClick Desktop's calibration window
 * (WebSocket /api/ws/desktop-calibration, message version 1).
 * Page -> Desktop: calibration.start, calibration.cancel.
 * Desktop -> page: calibration.state on connect, then started / progress / advice /
 * result / cancelled / error, and tracking.status.
 */
export const DESKTOP_CALIBRATION_VERSION = 1

const resultSchema = z.object({
  status: z.enum(['success', 'failed']),
  accuracy_percent: z.number().nullable().optional(),
  low_accuracy: z.boolean().nullable().optional(),
  message: z.string().nullable().optional(),
})
export type DesktopCalibrationResult = z.infer<typeof resultSchema>

const adviceSchema = z.object({ kind: z.string().nullable(), text: z.string().nullable().optional() })

const v = z.literal(DESKTOP_CALIBRATION_VERSION)
export const desktopCalibrationMessageSchema = z.discriminatedUnion('type', [
  z.object({
    v, type: z.literal('calibration.state'),
    status: z.enum(['idle', 'starting', 'running', 'finished']),
    done: z.number(), total: z.number(),
    advice: z.object({ kind: z.string().nullable(), text: z.string().nullable().optional() }).nullable(),
    last_result: resultSchema.nullable(),
  }),
  z.object({ v, type: z.literal('calibration.started'), total: z.number() }),
  z.object({ v, type: z.literal('calibration.progress'), done: z.number(), total: z.number() }),
  adviceSchema.extend({ v, type: z.literal('calibration.advice') }),
  resultSchema.extend({ v, type: z.literal('calibration.result') }),
  z.object({ v, type: z.literal('calibration.cancelled'), reason: z.string().optional() }),
  z.object({ v, type: z.literal('calibration.error'), message: z.string(), reason: z.string().optional() }),
  z.object({ v, type: z.literal('tracking.status'), status: z.enum(['active', 'paused', 'stopped']) }),
])
export type DesktopCalibrationMessage = z.infer<typeof desktopCalibrationMessageSchema>

export interface DesktopCalibrationLink {
  start: () => void
  cancel: () => void
  close: () => void
}

export function openDesktopCalibration(handlers: {
  onOpen?: () => void
  onMessage: (message: DesktopCalibrationMessage) => void
  onClose?: () => void
}): DesktopCalibrationLink {
  const socket = openJsonSocket('/ws/desktop-calibration', {
    onOpen: handlers.onOpen,
    onMessage: (data) => {
      const parsed = desktopCalibrationMessageSchema.safeParse(data)
      if (parsed.success) handlers.onMessage(parsed.data)
    },
    onClose: () => handlers.onClose?.(),
  })
  return {
    start: () => socket.send({ v: DESKTOP_CALIBRATION_VERSION, type: 'calibration.start' }),
    cancel: () => socket.send({ v: DESKTOP_CALIBRATION_VERSION, type: 'calibration.cancel' }),
    close: () => socket.close(),
  }
}
