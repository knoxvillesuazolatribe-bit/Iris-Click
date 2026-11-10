import { CircleCheck, CircleX, Crosshair, LoaderCircle, Monitor, RotateCcw, TriangleAlert, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { GoToHomeSuite } from '@/components/go-to-home-suite'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Progress } from '@/components/ui/progress'
import {
  openDesktopCalibration,
  type DesktopCalibrationLink,
  type DesktopCalibrationMessage,
  type DesktopCalibrationResult,
} from '@/services/desktop-calibration-service'

type View =
  | { kind: 'connecting' }
  | { kind: 'opening' }
  | { kind: 'running'; done: number; total: number; advice: string | null; retrying: string | null }
  | { kind: 'success'; result: DesktopCalibrationResult }
  | { kind: 'stopped'; message: string }
  | { kind: 'not-linked'; message: string }

const LOST = 'IrisClick Desktop stopped answering. Make sure it is running, then try again.'
const STOPPED = 'The calibration did not finish.'

/**
 * Desktop calibration: the 13-point calibration runs full screen in IrisClick Desktop;
 * this card shows its progress live and moves on by itself when it finishes.
 */
export function DesktopCalibrationCard({ onUseWeb }: { onUseWeb: () => void }) {
  const navigate = useNavigate()
  const [view, setView] = useState<View>({ kind: 'connecting' })
  const [attempt, setAttempt] = useState(0)
  const link = useRef<DesktopCalibrationLink | null>(null)

  useEffect(() => {
    let requested = false
    let closedByUs = false
    let current: View = { kind: 'connecting' }
    const show = (next: View) => {
      current = next
      setView(next)
    }
    const start = () => {
      requested = true
      show({ kind: 'opening' })
      socket.start()
    }
    const onMessage = (m: DesktopCalibrationMessage) => {
      switch (m.type) {
        case 'calibration.state':
          if (m.status === 'idle') {
            if (!requested) start()
            else if (current.kind !== 'success' && current.kind !== 'stopped' && current.kind !== 'not-linked')
              show({ kind: 'stopped', message: STOPPED })
          } else if (m.status === 'starting') {
            requested = true
            if (current.kind === 'connecting') show({ kind: 'opening' })
          } else if (m.status === 'running') {
            requested = true
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
          if (m.status === 'success') show({ kind: 'success', result: m })
          else if (current.kind === 'running')
            show({ ...current, advice: null, retrying: m.message ?? 'Calibration was not accurate enough.' })
          else show({ kind: 'running', done: 0, total: 13, advice: null,
            retrying: m.message ?? 'Calibration was not accurate enough.' })
          break
        case 'calibration.cancelled':
          if (current.kind !== 'success') show({ kind: 'stopped', message: STOPPED })
          break
        case 'calibration.error':
          if (m.reason === 'not_linked') show({ kind: 'not-linked', message: m.message })
          else if (m.reason !== 'version' || current.kind === 'connecting') show({ kind: 'stopped', message: m.message })
          break
        case 'tracking.status':
          break
      }
    }
    const socket = openDesktopCalibration({
      onMessage,
      onClose: () => {
        if (!closedByUs && current.kind !== 'success') show({ kind: 'stopped', message: LOST })
      },
    })
    link.current = socket
    return () => {
      closedByUs = true
      link.current = null
      socket.close()
    }
  }, [attempt])

  const tryAgain = () => setAttempt((n) => n + 1)
  const cancel = () => link.current?.cancel()

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-8 p-6 text-center">
      <Monitor className="text-primary size-16" aria-hidden />
      {(view.kind === 'connecting' || view.kind === 'opening') && (
        <>
          <h1 className="text-4xl font-bold">Opening the calibration on your computer…</h1>
          <p className="max-w-2xl text-2xl">Look at the IrisClick Desktop screen. It starts by itself.</p>
          <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Opening" />
        </>
      )}
      {view.kind === 'running' && (
        <>
          <h1 className="text-4xl font-bold">Calibrating on your computer</h1>
          <p className="max-w-2xl text-2xl">Look at the IrisClick Desktop screen.</p>
          <div className="w-full max-w-xl" aria-live="polite">
            <Progress value={(view.done / Math.max(1, view.total)) * 100} className="h-4" />
            <p className="mt-3 text-2xl font-semibold tabular-nums">{view.done} of {view.total}</p>
          </div>
          {view.advice && (
            <p className="flex items-center gap-2 text-xl text-amber-500"><TriangleAlert aria-hidden /> {view.advice}</p>
          )}
          {view.retrying && (
            <Alert className="max-w-2xl text-left" role="status">
              <AlertDescription className="text-lg">{view.retrying} IrisClick Desktop will try again.</AlertDescription>
            </Alert>
          )}
          <GazeButton variant="outline" onClick={cancel}><X aria-hidden /> Cancel</GazeButton>
        </>
      )}
      {view.kind === 'success' && (
        <>
          <h1 className="flex items-center gap-3 text-4xl font-bold">
            <CircleCheck className="text-primary size-10" aria-hidden /> Calibration complete
          </h1>
          {view.result.accuracy_percent != null && (
            <p className="text-2xl">Accuracy {view.result.accuracy_percent.toFixed(1)} %</p>
          )}
          {view.result.low_accuracy && (
            <p className="max-w-2xl text-xl">Saved with low accuracy. Large buttons will work; you can calibrate again later.</p>
          )}
          <GoToHomeSuite />
        </>
      )}
      {(view.kind === 'stopped' || view.kind === 'not-linked') && (
        <>
          <h1 className="flex items-center gap-3 text-4xl font-bold">
            <CircleX className="text-destructive size-10" aria-hidden /> Calibration not finished
          </h1>
          <Alert variant="destructive" role="alert" className="max-w-2xl text-left">
            <AlertDescription className="text-lg">{view.message}</AlertDescription>
          </Alert>
          <div className="flex flex-wrap justify-center gap-4">
            {view.kind === 'stopped' ? (
              <GazeButton autoFocus onClick={tryAgain}><RotateCcw aria-hidden /> Try again</GazeButton>
            ) : (
              <GazeButton autoFocus onClick={() => void navigate('/user/select')}>Choose your name</GazeButton>
            )}
            <GazeButton variant="outline" onClick={() => void navigate(-1)}>Back</GazeButton>
          </div>
        </>
      )}
      {view.kind !== 'success' && (
        <button type="button" className="text-muted-foreground flex items-center gap-2 text-lg underline" onClick={onUseWeb}>
          <Crosshair className="size-5" aria-hidden /> Use the web calibration instead
        </button>
      )}
    </main>
  )
}
