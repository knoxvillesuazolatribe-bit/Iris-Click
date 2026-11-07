import { isAxiosError } from 'axios'
import { ArrowLeft, Crosshair, LoaderCircle, Play, Square } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { apiClient } from '@/api/api-client'
import { openJsonSocket } from '@/api/websocket-client'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { trackingViewSchema, type TrackingView } from '@/validators/home-validator'

const POLL_MS = 1000
const STATE_STYLE = {
  active: { label: 'ACTIVE', className: 'bg-green-700 text-white' },
  paused: { label: 'PAUSED', className: 'bg-amber-400 text-black' },
  inactive: { label: 'INACTIVE', className: 'bg-muted text-foreground' },
} as const

const detail = (err: unknown, fallback: string) => {
  const d = isAxiosError(err) ? err.response?.data?.detail : undefined
  return typeof d === 'string' ? d : fallback
}

/**
 * Hosted website: Gaze Tracking, served by IrisClick Desktop on this PC (shown inside
 * DesktopGate). Live status comes over the WebSocket /api/ws/tracking; if it drops,
 * the page asks every second instead.
 */
export function DesktopTrackingPage() {
  const navigate = useNavigate()
  const [view, setView] = useState<TrackingView | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState<'start' | 'stop' | null>(null)
  const [confirmStop, setConfirmStop] = useState(false)

  useEffect(() => {
    let timer = 0
    let closed = false
    const poll = () => {
      apiClient.get('/desktop/tracking').then(
        (r) => { setView(trackingViewSchema.parse(r.data)); setProblem(null) },
        (err) => setProblem(detail(err, 'IrisClick Desktop does not answer.')),
      )
    }
    const socket = openJsonSocket('/ws/tracking', {
      onMessage: (data) => {
        const msg = data as { ok: boolean; view?: unknown; detail?: string }
        if (msg.ok) {
          setView(trackingViewSchema.parse(msg.view))
          setProblem(null)
        } else setProblem(msg.detail ?? 'Not ready yet.')
      },
      onClose: () => {
        if (!closed) timer = window.setInterval(poll, POLL_MS) // fall back to asking every second
      },
    })
    return () => {
      closed = true
      socket.close()
      window.clearInterval(timer)
    }
  }, [])

  const run = async (action: 'start' | 'stop') => {
    setBusy(action)
    setConfirmStop(false)
    try {
      const r = await apiClient.post(`/desktop/tracking/${action}`)
      setView(trackingViewSchema.parse(r.data))
      setProblem(null)
    } catch (err) {
      setProblem(detail(err, action === 'start' ? 'Eye tracking could not start.' : 'Eye tracking could not stop.'))
    } finally {
      setBusy(null)
    }
  }

  const running = view ? view.state !== 'inactive' : false
  const style = STATE_STYLE[view?.state ?? 'inactive']
  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col gap-8 p-6">
      <header className="top-band flex flex-wrap items-center justify-between gap-6">
        <h1 className="text-4xl font-bold">Gaze Tracking</h1>
        <GazeButton variant="outline" onClick={() => void navigate('/home')}><ArrowLeft aria-hidden /> Home</GazeButton>
      </header>

      <section aria-live="polite" className="flex flex-wrap items-center gap-6">
        {view ? (
          <span className={cn('rounded-2xl px-8 py-4 text-4xl font-black tracking-wider', style.className)}>{style.label}</span>
        ) : (
          <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading tracking status" />
        )}
        {view?.status_text && <span className="text-muted-foreground text-xl">{view.status_text}</span>}
      </section>

      {problem && (
        <Alert variant="destructive" role="alert"><AlertDescription className="text-base">{problem}</AlertDescription></Alert>
      )}

      <div className="flex flex-wrap gap-8">
        <GazeButton className="min-w-56" disabled={!view?.calibration || (running && view?.running_profile_is_mine === true) || busy !== null}
          onClick={() => void run('start')}>
          {busy === 'start' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Play aria-hidden />} Start
        </GazeButton>
        {!confirmStop ? (
          <GazeButton variant="outline" className="min-w-56" disabled={!running || busy !== null} onClick={() => setConfirmStop(true)}>
            {busy === 'stop' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Square aria-hidden />} Stop
          </GazeButton>
        ) : (
          <div className="flex flex-wrap items-center gap-6" role="group" aria-label="Confirm stop">
            <GazeButton variant="destructive" autoFocus onClick={() => void run('stop')}><Square aria-hidden /> Yes, stop tracking</GazeButton>
            <GazeButton variant="outline" onClick={() => setConfirmStop(false)}>Cancel</GazeButton>
          </div>
        )}
        <GazeButton variant="outline" className="min-w-56" onClick={() => void navigate('/calibration')}>
          <Crosshair aria-hidden /> Calibrate
        </GazeButton>
      </div>

      <section className="rounded-xl border p-5 text-lg">
        <h2 className="mb-2 text-xl font-semibold">Your calibration</h2>
        {view?.calibration ? (
          <p>{view.calibration.profile_name}{view.calibration.accuracy_score !== null ? `, accuracy ${view.calibration.accuracy_score}%` : ''}</p>
        ) : (
          <p>{view?.calibration_unavailable_reason ?? 'No calibration on this computer yet. Choose Calibrate.'}</p>
        )}
      </section>
    </main>
  )
}
