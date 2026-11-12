import { CircleCheck, LoaderCircle, Monitor, RotateCcw, TriangleAlert, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Progress } from '@/components/ui/progress'
import { pendingCalibrationService } from '@/services/pending-calibration-service'
import {
  openDesktopCalibration,
  type DesktopCalibrationLink,
  type DesktopCalibrationMessage,
} from '@/services/desktop-calibration-service'
import type { PendingCalibration } from '@/validators/accounts-validator'

type View =
  | { kind: 'ready' }
  | { kind: 'opening' }
  | { kind: 'running'; done: number; total: number; advice: string | null; retrying: string | null }
  | { kind: 'done'; pending: PendingCalibration }
  | { kind: 'stopped'; message: string }

const LOST = 'IrisClick Desktop stopped answering. Make sure it is running, then try again.'
const STOPPED = 'The calibration did not finish.'

interface Props {
  /** Step 1 of 4 heading text, e.g. "Calibrate your eyes". */
  stepLabel: string
  onDone: (pending: PendingCalibration) => void
}

/**
 * Screen B2: the 13-point calibration for a person who has no account yet. It runs full
 * screen in IrisClick Desktop (which first allows a calibration with nobody linked) and
 * stays on this computer until the account is created.
 */
export function NewAccountCalibration({ stepLabel, onDone }: Props) {
  const [view, setView] = useState<View>({ kind: 'ready' })
  const [attempt, setAttempt] = useState(0)
  const link = useRef<DesktopCalibrationLink | null>(null)

  useEffect(() => {
    if (attempt === 0) return
    let current: View = { kind: 'opening' }
    let closedByUs = false
    let requested = false
    const show = (next: View) => {
      current = next
      setView(next)
    }
    const finish = async () => {
      try {
        const pending = await pendingCalibrationService.current()
        if (pending.pending) show({ kind: 'done', pending })
        else show({ kind: 'stopped', message: STOPPED })
      } catch {
        show({ kind: 'stopped', message: LOST })
      }
    }
    const onMessage = (m: DesktopCalibrationMessage) => {
      switch (m.type) {
        case 'calibration.state':
          if (m.status === 'idle' && !requested) {
            requested = true
            socket.start()
          } else if (m.status === 'running') {
            show({ kind: 'running', done: m.done, total: m.total, advice: m.advice?.text ?? null, retrying: null })
          }
          break
        case 'calibration.started':
          show({ kind: 'running', done: 0, total: m.total, advice: null, retrying: null })
          break
        case 'calibration.progress':
          show(current.kind === 'running' ? { ...current, done: m.done, total: m.total, retrying: null }
            : { kind: 'running', done: m.done, total: m.total, advice: null, retrying: null })
          break
        case 'calibration.advice':
          if (current.kind === 'running') show({ ...current, advice: m.text ?? null })
          break
        case 'calibration.result':
          if (m.status === 'success') void finish()
          else show(current.kind === 'running'
            ? { ...current, advice: null, retrying: m.message ?? 'Calibration was not accurate enough.' }
            : { kind: 'running', done: 0, total: 13, advice: null, retrying: m.message ?? 'Calibration was not accurate enough.' })
          break
        case 'calibration.cancelled':
          if (current.kind !== 'done') show({ kind: 'stopped', message: STOPPED })
          break
        case 'calibration.error':
          show({ kind: 'stopped', message: m.message })
          break
        case 'tracking.status':
          break
      }
    }
    show({ kind: 'opening' })
    let socket: DesktopCalibrationLink = { start: () => undefined, cancel: () => undefined, close: () => undefined }
    void pendingCalibrationService.allow().then(
      () => {
        if (closedByUs) return
        socket = openDesktopCalibration({
          onMessage,
          onClose: () => {
            if (!closedByUs && current.kind !== 'done') show({ kind: 'stopped', message: LOST })
          },
        })
        link.current = socket
      },
      () => show({ kind: 'stopped', message: LOST }),
    )
    return () => {
      closedByUs = true
      link.current = null
      socket.close()
    }
  }, [attempt])

  const start = () => setAttempt((n) => n + 1)

  return (
    <section className="flex w-full max-w-3xl flex-col items-center gap-8 text-center">
      <h1 className="text-4xl font-bold">{stepLabel}</h1>
      {view.kind === 'ready' && (
        <>
          <ul className="text-muted-foreground grid gap-2 text-left text-xl sm:grid-cols-2 sm:gap-x-10">
            <li>• Good light on your face</li>
            <li>• Sit upright and still</li>
            <li>• Keep your head steady</li>
            <li>• Tilt glasses to cut glare</li>
          </ul>
          <GazeButton autoFocus className="min-h-24 min-w-80 text-2xl" onClick={start}>
            <Monitor aria-hidden /> Start calibration
          </GazeButton>
        </>
      )}
      {view.kind === 'opening' && (
        <>
          <p className="max-w-2xl text-2xl">Look at your screen: the calibration opens in IrisClick Desktop.</p>
          <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Opening" />
        </>
      )}
      {view.kind === 'running' && (
        <>
          <p className="max-w-2xl text-2xl">Look at the IrisClick Desktop screen.</p>
          <div className="w-full max-w-xl" aria-live="polite">
            <Progress value={(view.done / Math.max(1, view.total)) * 100} className="h-4" />
            <p className="mt-3 text-2xl font-semibold tabular-nums">Calibrating… {view.done} of {view.total}</p>
          </div>
          {view.advice && <p className="flex items-center gap-2 text-xl text-amber-500"><TriangleAlert aria-hidden /> {view.advice}</p>}
          {view.retrying && (
            <Alert role="status" className="text-left">
              <AlertDescription className="text-lg">{view.retrying} IrisClick Desktop will try again.</AlertDescription>
            </Alert>
          )}
          <GazeButton variant="outline" onClick={() => link.current?.cancel()}><X aria-hidden /> Cancel</GazeButton>
        </>
      )}
      {view.kind === 'done' && (
        <>
          <p className="flex items-center gap-3 text-3xl font-bold">
            <CircleCheck className="text-primary size-10" aria-hidden /> Calibration done
            {view.pending.accuracy_score !== null && ` · ${view.pending.accuracy_score.toFixed(2)}%`}
          </p>
          {view.pending.low_accuracy && (
            <p className="text-muted-foreground text-xl">This may be the light or your glasses. You can try again.</p>
          )}
          <div className="flex flex-wrap justify-center gap-6">
            <GazeButton autoFocus className="min-h-24 min-w-64 text-2xl" onClick={() => onDone(view.pending)}>Next</GazeButton>
            <GazeButton variant="outline" onClick={start}><RotateCcw aria-hidden /> Try again</GazeButton>
          </div>
        </>
      )}
      {view.kind === 'stopped' && (
        <>
          <p className="text-2xl">{view.message}</p>
          <GazeButton autoFocus className="min-h-20 min-w-60 text-xl" onClick={start}><RotateCcw aria-hidden /> Try again</GazeButton>
        </>
      )}
    </section>
  )
}
