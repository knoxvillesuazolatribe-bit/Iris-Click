import { CircleHelp, KeyRound, Square, SquareCheckBig } from 'lucide-react'
import { useEffect, useState } from 'react'
import { GazeButton } from '@/components/gaze-button'
import { PinEntry } from '@/components/pin-entry'
import { Alert, AlertDescription } from '@/components/ui/alert'
import type { AccountRefusal } from '@/validators/accounts-validator'

interface PinScreenProps {
  username: string
  /** "remove" asks for the PIN before removing an account from a shared computer. */
  purpose: 'signin' | 'remove'
  /** Remember me is never offered on a shared computer. */
  showRemember: boolean
  busy: boolean
  /** The server's last answer to a wrong PIN, if any. */
  refusal: AccountRefusal | null
  onSubmit: (pin: string, remember: boolean) => void
  onForgot: () => void
}

function clock(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function triesText(left: number | undefined) {
  if (left === undefined) return ''
  return left === 1 ? ' 1 try left.' : ` ${left} tries left.`
}

/** Screens C1-C3: enter the PIN, see how many tries are left, wait out a lockout, or ask for help. */
export function PinScreen({ username, purpose, showRemember, busy, refusal, onSubmit, onForgot }: PinScreenProps) {
  const [remember, setRemember] = useState(false)
  const [waitLeft, setWaitLeft] = useState(0)

  useEffect(() => {
    setWaitLeft(refusal?.code === 'wait' ? (refusal.wait_seconds ?? 0) : 0)
  }, [refusal])

  useEffect(() => {
    if (waitLeft <= 0) return
    const timer = window.setTimeout(() => setWaitLeft((s) => s - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [waitLeft])

  const locked = refusal?.code === 'reset_needed'
  const waiting = waitLeft > 0
  let note: string | null = null
  if (locked) note = refusal.detail
  else if (waiting) note = `Too many wrong tries. Try again in ${clock(waitLeft)}.`
  else if (refusal && refusal.code !== 'wait') note = refusal.detail + triesText(refusal.tries_left)

  return (
    <section className="flex w-full max-w-5xl flex-col items-center gap-6 text-center">
      <h1 className="text-4xl font-bold break-all">Hello, {username}</h1>
      <p className="text-muted-foreground flex items-center gap-3 text-2xl">
        <KeyRound aria-hidden />
        {purpose === 'remove' ? 'Enter your PIN to remove your account from this shared computer' : 'Enter your PIN'}
      </p>
      {note && (
        <Alert variant={waiting ? 'default' : 'destructive'} role="alert" className="text-left">
          <AlertDescription className="text-lg">{note}</AlertDescription>
        </Alert>
      )}
      <div className="flex w-full flex-wrap items-end justify-center gap-8">
        <PinEntry disabled={busy || waiting || locked} onSubmit={(pin) => onSubmit(pin, remember)} />
        <div className="flex max-w-72 flex-col items-stretch gap-6">
          {showRemember && purpose === 'signin' && (
            <GazeButton variant="outline" className="h-auto py-3 whitespace-normal" aria-pressed={remember} disabled={busy}
              onClick={() => setRemember((r) => !r)}>
              {remember ? <SquareCheckBig aria-hidden /> : <Square aria-hidden />}
              Remember me on this computer
            </GazeButton>
          )}
          <GazeButton variant="outline" disabled={busy} onClick={onForgot}>
            <CircleHelp aria-hidden />
            Forgot PIN?
          </GazeButton>
        </div>
      </div>
    </section>
  )
}

/** Screen F1: until SMS is connected, a forgotten PIN is reset by PDAO staff. */
export function ForgotPinScreen({ onBack, onSetupCode }: { onBack: () => void; onSetupCode?: () => void }) {
  return (
    <section className="flex w-full max-w-3xl flex-col items-center gap-8 text-center">
      <h1 className="text-4xl font-bold">Forgot your PIN?</h1>
      <p className="text-muted-foreground text-2xl">We couldn't send a code. Ask PDAO staff to reset your PIN.</p>
      <p className="text-muted-foreground text-xl">They will give you an 8-number setup code to choose a new PIN.</p>
      <div className="flex flex-wrap justify-center gap-6">
        {onSetupCode && <GazeButton className="min-h-20 min-w-60 text-xl" onClick={onSetupCode}>I have a setup code</GazeButton>}
        <GazeButton autoFocus variant="outline" className="min-h-20 min-w-60 text-xl" onClick={onBack}>Back</GazeButton>
      </div>
    </section>
  )
}
