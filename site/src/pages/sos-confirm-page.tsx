import { LoaderCircle, RotateCcw, Send, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage, errorStatus } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { sosService } from '@/services/sos-service'

const COUNTDOWN_S = 4

type Phase = 'counting' | 'sending' | 'error' | 'cancelled'

/** Screen 16: 4-second countdown, Send Now or Cancel; sends automatically at 0. */
export function SosConfirmPage() {
  const navigate = useNavigate()
  const [secondsLeft, setSecondsLeft] = useState(COUNTDOWN_S)
  const [phase, setPhase] = useState<Phase>('counting')
  const [error, setError] = useState<string | null>(null)
  // One id per visit: "Try again" after a network error can never alert twice.
  const activationId = useRef<string>(crypto.randomUUID())
  const inFlight = useRef(false)

  const send = useCallback(async () => {
    if (inFlight.current) return
    inFlight.current = true
    setPhase('sending')
    setError(null)
    try {
      const activation = await sosService.activate(activationId.current)
      void navigate(`/sos/sent?activation=${activation.activation_id}`, { replace: true })
    } catch (err) {
      inFlight.current = false
      setPhase('error')
      const reached = errorStatus(err) !== null
      setError(reached ? errorMessage(err, 'The SOS could not be sent.') : 'Could not reach the IrisClick server.')
    }
  }, [navigate])

  useEffect(() => {
    if (phase !== 'counting') return
    const timer = window.setTimeout(() => {
      if (secondsLeft <= 1) void send()
      else setSecondsLeft((s) => s - 1)
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [secondsLeft, phase, send])

  const cancel = () => {
    setPhase('cancelled')
    void sosService.cancel().catch(() => undefined)
    void navigate('/home', { replace: true })
  }

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-12 p-6 text-center">
      {phase === 'error' ? (
        <Alert variant="destructive" role="alert" className="max-w-3xl text-left">
          <AlertTitle className="text-3xl font-black">SOS was NOT sent</AlertTitle>
          <AlertDescription className="text-xl">{error}</AlertDescription>
        </Alert>
      ) : (
        <div aria-live="assertive" className="space-y-4">
          <h1 className="text-destructive text-5xl font-black">
            {phase === 'sending' ? 'Sending SOS…' : 'Sending SOS in'}
          </h1>
          {phase === 'sending' ? (
            <LoaderCircle className="text-destructive mx-auto size-40 animate-spin" aria-hidden />
          ) : (
            <p className="text-destructive text-[10rem] leading-none font-black tabular-nums">{secondsLeft}</p>
          )}
          <p className="text-muted-foreground text-2xl">Your emergency contacts will be alerted.</p>
        </div>
      )}

      <div className="flex w-full max-w-4xl flex-wrap items-center justify-between gap-24">
        <GazeButton
          variant="outline"
          className="min-h-28 min-w-72 border-4 text-3xl"
          disabled={phase === 'sending'}
          onClick={cancel}
        >
          <X className="size-10" aria-hidden />
          Cancel
        </GazeButton>
        <GazeButton
          variant="destructive"
          className="bg-destructive hover:bg-destructive/90 min-h-28 min-w-72 text-3xl text-white"
          disabled={phase === 'sending'}
          onClick={() => void send()}
        >
          {phase === 'error' ? <RotateCcw className="size-10" aria-hidden /> : <Send className="size-10" aria-hidden />}
          {phase === 'error' ? 'Try again' : 'Send Now'}
        </GazeButton>
      </div>
    </main>
  )
}
