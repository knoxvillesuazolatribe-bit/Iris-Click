import { ArrowLeft, Crosshair, LoaderCircle, Pause, Play, Square } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { onlineCalibrationService, type SavedOnlineCalibration } from '@/services/online-calibration-service'
import { gaze, GUIDANCE_TEXT, useGaze } from './engine'
import { startSavedTracking } from './start'

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

const STATE_STYLE = {
  tracking: { label: 'ACTIVE', className: 'bg-green-700 text-white' },
  paused: { label: 'PAUSED', className: 'bg-amber-400 text-black' },
  off: { label: 'INACTIVE', className: 'bg-muted text-foreground' },
} as const

/** Online copy: the Gaze Tracking page for eye tracking in this browser. */
export function OnlineTrackingPage() {
  const navigate = useNavigate()
  const { status, error, guidance } = useGaze()
  const [saved, setSaved] = useState<SavedOnlineCalibration | null | undefined>(undefined)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  useEffect(() => {
    onlineCalibrationService.latest().then(setSaved, (err: unknown) => {
      setSaved(null)
      setLoadError(errorMessage(err, 'Could not read your calibration.'))
    })
  }, [])

  const start = async () => {
    setBusy(true)
    setStartError(null)
    try {
      if ((await startSavedTracking()) === 'no_calibration') void navigate('/calibration')
    } catch (err) {
      setStartError(gaze.getSnapshot().error ?? errorMessage(err, 'Eye tracking could not start.'))
    } finally {
      setBusy(false)
    }
  }

  const state = status === 'tracking' ? 'tracking' : status === 'paused' ? 'paused' : 'off'
  const style = STATE_STYLE[state]
  const screenChanged = saved?.viewport &&
    (Math.abs(saved.viewport.w - window.innerWidth) > saved.viewport.w * 0.15 ||
      Math.abs(saved.viewport.h - window.innerHeight) > saved.viewport.h * 0.15)

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center gap-8 p-6">
      <div className="top-band flex w-full max-w-4xl items-center justify-between gap-4">
        <h1 className="text-4xl font-bold">Gaze Tracking</h1>
        <GazeButton variant="outline" onClick={() => void navigate('/home')}>
          <ArrowLeft aria-hidden /> Home
        </GazeButton>
      </div>

      <section className="flex w-full max-w-4xl flex-col gap-6">
        <p className={cn('w-fit rounded-xl px-6 py-3 text-2xl font-bold', style.className)} role="status">{style.label}</p>
        <p className="text-muted-foreground text-lg">
          Eye tracking runs in this browser with your webcam and controls this website only. To control other apps,
          use the IrisClick PC.
        </p>
        {status === 'tracking' && guidance && <p className="text-destructive text-lg">{GUIDANCE_TEXT[guidance]}</p>}
        {(startError || (status === 'error' && error)) && (
          <Alert variant="destructive" role="alert">
            <AlertDescription className="text-base">{startError ?? error}</AlertDescription>
          </Alert>
        )}

        <div className="flex flex-wrap gap-4">
          {state === 'off' && (
            <GazeButton className="min-h-24 text-2xl" disabled={busy || saved === undefined} onClick={() => void start()}>
              {busy || status === 'starting' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Play aria-hidden />}
              Start
            </GazeButton>
          )}
          {state !== 'off' && (
            <GazeButton variant="outline" className="min-h-24 text-2xl"
              onClick={() => (state === 'paused' ? gaze.resume() : gaze.pause())}>
              {state === 'paused' ? <Play aria-hidden /> : <Pause aria-hidden />}
              {state === 'paused' ? 'Resume' : 'Pause'}
            </GazeButton>
          )}
          {state !== 'off' && (
            <GazeButton variant="outline" className="min-h-24 text-2xl" onClick={() => gaze.stop()}>
              <Square aria-hidden /> Stop
            </GazeButton>
          )}
          <GazeButton variant="outline" className="min-h-24 text-2xl" onClick={() => void navigate('/calibration')}>
            <Crosshair aria-hidden /> Calibrate
          </GazeButton>
        </div>

        <div className="rounded-xl border p-5">
          <h2 className="mb-2 text-xl font-semibold">Your calibration</h2>
          {saved === undefined && <LoaderCircle className="text-muted-foreground animate-spin" aria-label="Loading" />}
          {loadError && <p className="text-destructive text-lg">{loadError}</p>}
          {saved === null && !loadError && <p className="text-lg">No online calibration yet. Choose Calibrate.</p>}
          {saved && (
            <div className="space-y-1 text-lg">
              <p>Online (browser), {DATE_FORMAT.format(new Date(saved.calibrated_at))}</p>
              {saved.accuracy_score !== null && <p>Accuracy {saved.accuracy_score.toFixed(2)}%</p>}
              {screenChanged && (
                <p className="text-destructive">This screen is a different size from when you calibrated. Calibrate again for better aim.</p>
              )}
            </div>
          )}
        </div>
      </section>
    </main>
  )
}
