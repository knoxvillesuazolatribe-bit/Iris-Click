import { CircleCheck, CircleX, Home, LoaderCircle, MapPin, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { errorMessage, errorStatus } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { sosService } from '@/services/sos-service'
import type { AlertStatus, SosActivation } from '@/validators/sos-validator'

const POLL_MS = 1000
const TIME_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' })

function headline(a: SosActivation): { text: string; tone: 'ok' | 'bad' | 'busy' } {
  if (a.sent === a.total) return { text: 'SOS Alerts Sent', tone: 'ok' }
  if (a.pending > 0) return { text: 'Sending SOS alerts…', tone: 'busy' }
  if (a.sent > 0) return { text: 'Some SOS alerts were not sent', tone: 'bad' }
  return { text: 'SOS alerts were NOT sent', tone: 'bad' }
}

const STATUS_LABEL: Record<AlertStatus['status'], string> = {
  sent: 'Sent',
  pending: 'Not sent yet, retrying',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

/** Screen 17: the real result of an SOS, refreshed until every alert is settled. */
export function SosSentPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const activationId = params.get('activation') ?? ''
  const [activation, setActivation] = useState<SosActivation | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let current = true
    let timer: number | undefined
    if (!activationId) {
      void navigate('/sos', { replace: true }) // opened on its own: nothing was sent
      return
    }
    const refresh = () =>
      sosService
        .getActivation(activationId)
        .then((next) => {
          if (!current) return
          setActivation(next)
          setError(null)
          if (next.pending > 0) timer = window.setTimeout(() => void refresh(), POLL_MS)
        })
        .catch((err) => {
          if (!current) return
          setError(errorMessage(err, 'Could not read the SOS status.'))
          if (errorStatus(err) !== 404) timer = window.setTimeout(() => void refresh(), POLL_MS * 3)
        })
    void refresh()
    return () => {
      current = false
      window.clearTimeout(timer)
    }
  }, [activationId, navigate])

  const dismiss = (
    <GazeButton className="min-h-24 min-w-72 text-2xl" onClick={() => void navigate('/home', { replace: true })}>
      <Home className="size-8" aria-hidden />
      Dismiss &amp; Reset
    </GazeButton>
  )

  if (!activation) {
    return (
      <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-8 p-6">
        {error ? (
          <Alert variant="destructive" role="alert" className="max-w-2xl">
            <AlertDescription className="text-xl">{error}</AlertDescription>
          </Alert>
        ) : (
          <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading" />
        )}
        {dismiss}
      </main>
    )
  }

  const head = headline(activation)
  const nothingSent = activation.sent === 0 && activation.pending === 0

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-4xl flex-col gap-8 p-6">
      <header aria-live="polite" className="space-y-3 text-center">
        <h1
          className={cn(
            'flex items-center justify-center gap-4 text-5xl font-black',
            head.tone === 'ok' && 'text-green-700',
            head.tone === 'bad' && 'text-destructive',
          )}
        >
          {head.tone === 'ok' && <CircleCheck className="size-14" aria-hidden />}
          {head.tone === 'bad' && <CircleX className="size-14" aria-hidden />}
          {head.tone === 'busy' && <LoaderCircle className="size-14 animate-spin" aria-hidden />}
          {head.text}
        </h1>
        <p className="text-3xl font-bold">
          {activation.sent} of {activation.total} contact{activation.total === 1 ? '' : 's'} notified
        </p>
        <p className="text-muted-foreground text-xl">{TIME_FORMAT.format(new Date(activation.activated_at))}</p>
      </header>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription className="text-lg">{error} Showing the last known status.</AlertDescription>
        </Alert>
      )}

      <section className="bg-card rounded-2xl border-2 p-6">
        <h2 className="mb-2 flex items-center gap-3 text-2xl font-bold">
          <MapPin className="size-8" aria-hidden />
          Location shared
        </h2>
        <p className="text-xl">{activation.location_text ?? 'No address on file. Contacts were asked to call.'}</p>
      </section>

      <section className="bg-card rounded-2xl border-2 p-6">
        <h2 className="mb-4 text-2xl font-bold">Each contact</h2>
        <ul className="flex flex-col gap-5">
          {activation.alerts.map((alert, i) => (
            <li key={`${alert.recipient}-${i}`} className="flex flex-wrap items-start justify-between gap-4 border-b pb-5 last:border-0 last:pb-0">
              <div className="min-w-0 flex-1">
                <p className="text-2xl font-semibold">
                  {alert.contact_name}
                  {alert.relationship && <span className="text-muted-foreground font-normal"> ({alert.relationship})</span>}
                </p>
                <p className="text-muted-foreground text-lg break-words">
                  {alert.channel === 'email' ? 'Email' : 'SMS'} · {alert.recipient}
                </p>
                {alert.detail && <p className="mt-1 text-lg break-words">{alert.detail}</p>}
              </div>
              <span
                className={cn(
                  'rounded-xl px-4 py-2 text-xl font-bold',
                  alert.status === 'sent' && 'bg-green-700 text-white',
                  alert.status === 'failed' && 'bg-destructive text-white',
                  alert.status === 'pending' && 'bg-amber-400 text-black',
                )}
              >
                {STATUS_LABEL[alert.status]}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex flex-wrap justify-center gap-8">
        {nothingSent && (
          <GazeButton variant="destructive" className="bg-destructive hover:bg-destructive/90 min-h-24 text-2xl text-white" onClick={() => void navigate('/sos/confirm', { replace: true })}>
            <RotateCcw className="size-8" aria-hidden />
            Try sending again
          </GazeButton>
        )}
        {dismiss}
      </div>
    </main>
  )
}
