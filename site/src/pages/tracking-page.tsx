import { ArrowLeft, Crosshair, LoaderCircle, Play, Square } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { homeService } from '@/services/home-service'
import type { TrackingView } from '@/validators/home-validator'

const POLL_MS = 1000
const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

const STATE_STYLE = {
  active: { label: 'ACTIVE', className: 'bg-green-700 text-white' },
  paused: { label: 'PAUSED', className: 'bg-amber-400 text-black' },
  inactive: { label: 'INACTIVE', className: 'bg-muted text-foreground' },
} as const

/** Screen 6: eye-tracking status, Start/Stop, the user's calibration and live details. */
export function TrackingPage() {
  const navigate = useNavigate()
  const [view, setView] = useState<TrackingView | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  // Kept with the state it happened in, so it clears once the status changes.
  const [actionError, setActionError] = useState<{ message: string; state: TrackingView['state'] } | null>(null)
  const [busy, setBusy] = useState<'start' | 'stop' | null>(null)
  const [confirmStop, setConfirmStop] = useState(false)

  useEffect(() => {
    let current = true
    const refresh = () =>
      homeService
        .getTracking()
        .then((next) => {
          if (!current) return
          setView(next)
          setLoadError(null)
        })
        .catch((err) => current && setLoadError(errorMessage(err, 'Could not read the tracking status.')))
    void refresh()
    const timer = window.setInterval(() => void refresh(), POLL_MS)
    return () => {
      current = false
      window.clearInterval(timer)
    }
  }, [])

  const run = async (action: 'start' | 'stop') => {
    setBusy(action)
    setActionError(null)
    setConfirmStop(false)
    try {
      setView(await (action === 'start' ? homeService.startTracking() : homeService.stopTracking()))
    } catch (err) {
      setActionError({
        message: errorMessage(err, action === 'start' ? 'Eye tracking could not start.' : 'Eye tracking could not stop.'),
        state: view?.state ?? 'inactive',
      })
    } finally {
      setBusy(null)
    }
  }

  const backHome = (
    <GazeButton variant="outline" onClick={() => void navigate('/home')}>
      <ArrowLeft aria-hidden />
      Home
    </GazeButton>
  )

  if (!view) {
    return (
      <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-8 p-6">
        {loadError ? (
          <Alert variant="destructive" role="alert" className="max-w-2xl">
            <AlertDescription className="text-lg">{loadError}</AlertDescription>
          </Alert>
        ) : (
          <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading tracking status" />
        )}
        {backHome}
      </main>
    )
  }

  const running = view.state !== 'inactive'
  const style = STATE_STYLE[view.state]
  const canStart = view.calibration !== null && !(running && view.running_profile_is_mine)

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col gap-8 p-6">
      <header className="top-band flex flex-wrap items-center justify-between gap-6">
        <h1 className="text-4xl font-bold">Gaze Tracking</h1>
        {backHome}
      </header>

      <section aria-live="polite" className="flex flex-wrap items-center gap-6">
        <span className={cn('rounded-2xl px-8 py-4 text-4xl font-black tracking-wider', style.className)}>
          {style.label}
        </span>
        {view.status_text && <span className="text-muted-foreground text-xl">{view.status_text}</span>}
      </section>

      {loadError && (
        <Alert variant="destructive" role="alert">
          <AlertDescription className="text-base">{loadError} Showing the last known status.</AlertDescription>
        </Alert>
      )}
      {actionError && actionError.state === view.state && (
        <Alert variant="destructive" role="alert">
          <AlertDescription className="text-base">{actionError.message}</AlertDescription>
        </Alert>
      )}
      {running && view.running_profile_is_mine === false && (
        <Alert role="status">
          <AlertTitle className="text-lg">Eye tracking is using someone else's calibration</AlertTitle>
          <AlertDescription className="text-base">
            {view.calibration ? 'Choose Start to switch to your own calibration.' : 'Calibrate first to use your own.'}
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap gap-8">
        <GazeButton disabled={!canStart || busy !== null} onClick={() => void run('start')} className="min-w-56">
          {busy === 'start' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Play aria-hidden />}
          {running && view.running_profile_is_mine === false ? 'Start with mine' : 'Start'}
        </GazeButton>
        {!confirmStop ? (
          <GazeButton
            variant="outline"
            disabled={!running || busy !== null}
            onClick={() => setConfirmStop(true)}
            className="min-w-56"
          >
            {busy === 'stop' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Square aria-hidden />}
            Stop
          </GazeButton>
        ) : (
          <div className="flex flex-wrap items-center gap-6" role="group" aria-label="Confirm stop">
            <GazeButton variant="destructive" onClick={() => void run('stop')} autoFocus>
              <Square aria-hidden />
              Yes, stop tracking
            </GazeButton>
            <GazeButton variant="outline" onClick={() => setConfirmStop(false)}>
              Cancel
            </GazeButton>
          </div>
        )}
      </div>
      {confirmStop && (
        <p className="text-muted-foreground -mt-4 text-lg">
          After stopping, the cursor no longer follows your eyes. You will need a mouse or helper to start it again.
        </p>
      )}

      <CalibrationPanel view={view} onCalibrate={() => void navigate('/calibration')} />
      {running && <LivePanel view={view} />}
    </main>
  )
}

function CalibrationPanel({ view, onCalibrate }: { view: TrackingView; onCalibrate: () => void }) {
  const { calibration } = view
  return (
    <section aria-labelledby="my-calibration" className="bg-card rounded-2xl border-2 p-6">
      <h2 id="my-calibration" className="mb-4 text-2xl font-bold">
        Your calibration
      </h2>
      {calibration ? (
        <dl className="grid gap-x-8 gap-y-2 text-xl sm:grid-cols-[auto_1fr]">
          <dt className="font-semibold">Name</dt>
          <dd>{calibration.profile_name}</dd>
          <dt className="font-semibold">Accuracy</dt>
          <dd>{calibration.accuracy_score === null ? 'Not recorded' : `${calibration.accuracy_score.toFixed(2)}%`}</dd>
          <dt className="font-semibold">Date</dt>
          <dd>{calibration.calibrated_at ? DATE_FORMAT.format(new Date(calibration.calibrated_at)) : 'Not recorded'}</dd>
        </dl>
      ) : (
        <div className="flex flex-wrap items-center gap-6">
          <p className="text-muted-foreground text-xl">{view.calibration_unavailable_reason}</p>
          <GazeButton onClick={onCalibrate}>
            <Crosshair aria-hidden />
            Calibrate
          </GazeButton>
        </div>
      )}
    </section>
  )
}

function LivePanel({ view }: { view: TrackingView }) {
  const { live } = view
  return (
    <section aria-labelledby="live-details" className="bg-card rounded-2xl border-2 p-6">
      <h2 id="live-details" className="mb-4 text-2xl font-bold">
        Live details
      </h2>
      {!live ? (
        <p className="text-muted-foreground text-xl">
          Live details are not available yet. If this stays, stop and start eye tracking once.
        </p>
      ) : (
        <div className="grid items-start gap-8 md:grid-cols-[2fr_1fr]">
          <div className="space-y-3">
            <p className="text-xl font-semibold">Where you are looking</p>
            {live.gaze ? (
              <>
                <div
                  className="bg-muted relative w-full overflow-hidden rounded-lg border-2"
                  style={{ aspectRatio: `${live.gaze.screen_w} / ${live.gaze.screen_h}` }}
                  role="img"
                  aria-label={`Gaze at ${live.gaze.x}, ${live.gaze.y}`}
                >
                  <span
                    className="bg-primary ring-background absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-4"
                    style={{
                      left: `${(live.gaze.x / live.gaze.screen_w) * 100}%`,
                      top: `${(live.gaze.y / live.gaze.screen_h) * 100}%`,
                    }}
                  />
                </div>
                <p className="text-muted-foreground text-lg">
                  x {live.gaze.x}, y {live.gaze.y} on a {live.gaze.screen_w} × {live.gaze.screen_h} screen
                </p>
              </>
            ) : (
              <p className="text-muted-foreground text-xl">
                Not following your eyes right now ({view.state === 'paused' ? 'paused' : 'face or eyes not clear'}).
              </p>
            )}
          </div>
          <dl className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-3 text-xl">
            <dt className="col-span-2 font-semibold">Winks since tracking started</dt>
            <dt>Left eye</dt>
            <dd className="text-right text-3xl font-bold tabular-nums">{live.winks.left}</dd>
            <dt>Right eye</dt>
            <dd className="text-right text-3xl font-bold tabular-nums">{live.winks.right}</dd>
          </dl>
        </div>
      )}
    </section>
  )
}
