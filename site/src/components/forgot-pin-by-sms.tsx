import { MessageSquare } from 'lucide-react'
import { useState } from 'react'
import { GazeButton } from '@/components/gaze-button'
import { PinEntry } from '@/components/pin-entry'
import { ForgotPinScreen } from '@/components/pin-screen'
import { SmsCodeEntry } from '@/components/sms-code-entry'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { accountRefusal, accountsService } from '@/services/accounts-service'
import type { AccountSession, AccountTile, CodeSent } from '@/validators/accounts-validator'

type Step =
  | { kind: 'offer' }
  | { kind: 'cant-send' }
  | { kind: 'code'; sent: CodeSent }
  | { kind: 'pin'; ticket: string }
  | { kind: 'confirm'; ticket: string; pin: string }

interface Props {
  deviceId: string
  tile: AccountTile
  onDone: (session: AccountSession) => void
  onBack: () => void
  onSetupCode: () => void
}

/**
 * Forgot PIN by text (screens F2-F4): send a code to the account's verified number, enter it,
 * choose a new PIN and confirm it, then signed in. Every other session of the account ends.
 * It never pretends a code was sent: anything that fails shows F1 (ask PDAO staff).
 */
export function ForgotPinBySms({ deviceId, tile, onDone, onBack, onSetupCode }: Props) {
  const [step, setStep] = useState<Step>({ kind: 'offer' })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const send = async () => {
    setBusy(true)
    setMessage(null)
    try {
      setStep({ kind: 'code', sent: await accountsService.forgotSend(deviceId, tile.user_id) })
    } catch (err) {
      const answer = accountRefusal(err, 'We could not send a code.')
      if (answer.code === 'resend_wait' || answer.code === 'sms_limit') setMessage(answer.detail)
      else setStep({ kind: 'cant-send' })
    } finally {
      setBusy(false)
    }
  }

  const finish = async (ticket: string, pin: string, confirm: string) => {
    if (pin !== confirm) {
      setMessage("The PINs don't match. Try again.")
      return setStep({ kind: 'pin', ticket })
    }
    setBusy(true)
    setMessage(null)
    try {
      onDone(await accountsService.forgotComplete(deviceId, ticket, pin, confirm, false))
    } catch (err) {
      const answer = accountRefusal(err, 'Could not save your new PIN. Please try again.')
      setMessage(answer.detail)
      if (answer.code === 'ticket_expired') setStep({ kind: 'offer' })
      else setStep({ kind: 'pin', ticket })
    } finally {
      setBusy(false)
    }
  }

  if (step.kind === 'cant-send') return <ForgotPinScreen onBack={onBack} onSetupCode={onSetupCode} />

  const note = message && (
    <Alert role="status" className="w-full max-w-3xl text-left">
      <AlertDescription className="text-lg">{message}</AlertDescription>
    </Alert>
  )

  if (step.kind === 'code') {
    return (
      <SmsCodeEntry title={`Forgot your PIN, ${tile.username}?`} to={step.sent.to} resendAfter={step.sent.resend_after}
        busy={busy}
        onSubmit={async (code) => {
          try {
            setStep({ kind: 'pin', ticket: await accountsService.forgotVerify(deviceId, tile.user_id, code) })
            return null
          } catch (err) {
            const answer = accountRefusal(err, 'Could not check the code. Please try again.')
            return answer.tries_left !== undefined ? `${answer.detail} ${answer.tries_left} tries left.` : answer.detail
          }
        }}
        onResend={async () => {
          try {
            return (await accountsService.forgotSend(deviceId, tile.user_id)).resend_after
          } catch (err) {
            return accountRefusal(err, 'We could not send a code.').detail
          }
        }} />
    )
  }

  if (step.kind === 'pin' || step.kind === 'confirm') {
    return (
      <section className="flex w-full max-w-3xl flex-col items-center gap-6 text-center">
        <h1 className="text-4xl font-bold">{step.kind === 'pin' ? 'Choose a new PIN' : 'Confirm your new PIN'}</h1>
        {step.kind === 'pin' && <p className="text-muted-foreground text-xl">6 numbers that are easy for you to remember.</p>}
        {note}
        <PinEntry key={step.kind} disabled={busy} okLabel={step.kind === 'confirm' ? 'Save' : undefined}
          onSubmit={(pin) => {
            setMessage(null)
            if (step.kind === 'pin') setStep({ kind: 'confirm', ticket: step.ticket, pin })
            else void finish(step.ticket, step.pin, pin)
          }} />
      </section>
    )
  }

  return (
    <section className="flex w-full max-w-3xl flex-col items-center gap-8 text-center">
      <h1 className="text-4xl font-bold">Forgot your PIN?</h1>
      <p className="text-muted-foreground flex items-center gap-3 text-2xl">
        <MessageSquare aria-hidden /> We will text a 6-digit code to your mobile number.
      </p>
      {note}
      <div className="flex flex-wrap justify-center gap-6">
        <GazeButton autoFocus className="min-h-20 min-w-60 text-xl" disabled={busy} onClick={() => void send()}>
          Send code
        </GazeButton>
        <GazeButton variant="outline" className="min-h-20 min-w-60 text-xl" disabled={busy} onClick={onBack}>Back</GazeButton>
      </div>
    </section>
  )
}
