import { create } from 'zustand'
import {
  calibrationService,
  type CalibrationSocket,
  type ScreenSize,
} from '@/services/calibration-service'
import {
  calibrationServerMessageSchema,
  type CalibrationPoint,
  type CalibrationResult,
  type CalibrationStartInput,
  type FrameStatus,
} from '@/validators/calibration-validator'

export type CalibrationPhase =
  | 'idle'
  | 'connecting'
  | 'registering'
  | 'dots'
  | 'fitting'
  | 'success'
  | 'failed'

interface CalibrationState {
  phase: CalibrationPhase
  points: CalibrationPoint[]
  pointIndex: number
  isCollecting: boolean
  isAccepted: boolean
  paused: boolean
  restMessage: string | null
  frame: FrameStatus | null
  deepGazeAvailable: boolean
  result: CalibrationResult | null
  error: string | null
  begin: (input: CalibrationStartInput, screen: ScreenSize) => void
  finishRegistration: () => void
  collectCurrentPoint: () => void
  advancePoint: () => void
  endRest: () => void
  setPaused: (paused: boolean) => void
  cancel: () => void
  reset: () => void
}

const initialState = {
  phase: 'idle' as CalibrationPhase,
  points: [],
  pointIndex: 0,
  isCollecting: false,
  isAccepted: false,
  paused: false,
  restMessage: null,
  frame: null,
  deepGazeAvailable: false,
  result: null,
  error: null,
}

// Not React state: the socket is an imperative handle shared by the actions.
let session: CalibrationSocket | null = null

function closeSession() {
  const current = session
  session = null
  current?.close()
}

export const useCalibrationStore = create<CalibrationState>((set, get) => {
  const fail = (error: string) => {
    closeSession()
    set({ phase: 'failed', error, isCollecting: false })
  }

  const handleMessage = (raw: unknown) => {
    const parsed = calibrationServerMessageSchema.safeParse(raw)
    if (!parsed.success) return
    const message = parsed.data
    switch (message.type) {
      case 'ready':
        set({
          phase: 'registering',
          points: message.points,
          deepGazeAvailable: message.deep_gaze_available,
        })
        break
      case 'frame_status':
        set({ frame: message })
        break
      case 'point_result':
        if (message.status === 'accepted') {
          // Dot stays on screen (green) until the flow hook calls advancePoint.
          set({ isCollecting: false, isAccepted: true })
        } else if (message.status === 'retry') {
          set({ isCollecting: false, restMessage: message.message ?? 'That dot was not clear.' })
        } else {
          set({ isCollecting: false })
        }
        break
      case 'result':
        closeSession()
        set({
          phase: message.status === 'success' ? 'success' : 'failed',
          result: message,
          error: message.status === 'failed' ? message.message : null,
          isCollecting: false,
        })
        break
      case 'error':
        if (message.fatal) fail(message.message)
        else set({ error: message.message, isCollecting: false })
        break
    }
  }

  return {
    ...initialState,

    begin: (input, screen) => {
      closeSession()
      set({ ...initialState, phase: 'connecting' })
      const socket = calibrationService.openSession({
        onOpen: () => socket.start(input, screen),
        onMessage: handleMessage,
        onClose: () => {
          if (session === socket && !['success', 'failed', 'idle'].includes(get().phase)) {
            fail('Lost the connection to the IrisClick server.')
          }
        },
        onError: () => {
          if (session === socket && get().phase === 'connecting') {
            fail('Cannot reach the IrisClick server. Make sure it is running, then try again.')
          }
        },
      })
      session = socket
    },

    finishRegistration: () => {
      if (get().phase === 'registering') set({ phase: 'dots' })
    },

    collectCurrentPoint: () => {
      const { phase, isCollecting, isAccepted, paused, restMessage, pointIndex } = get()
      if (phase !== 'dots' || isCollecting || isAccepted || paused || restMessage || !session) return
      set({ isCollecting: true, error: null })
      session.collect(pointIndex)
    },

    advancePoint: () => {
      const { phase, isAccepted, pointIndex, points } = get()
      if (phase !== 'dots' || !isAccepted) return
      const next = pointIndex + 1
      set({
        pointIndex: next,
        isAccepted: false,
        phase: next >= points.length ? 'fitting' : 'dots',
      })
    },

    endRest: () => set({ restMessage: null }),

    setPaused: (paused) => set({ paused }),

    cancel: () => {
      session?.cancel()
      closeSession()
      set({ ...initialState })
    },

    reset: () => {
      closeSession()
      set({ ...initialState })
    },
  }
})
