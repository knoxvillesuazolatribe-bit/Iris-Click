import { CircleCheck, LoaderCircle, MessageSquare, Smartphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { GazeButton } from '@/components/gaze-button'
import { SmsCodeEntry } from '@/components/sms-code-entry'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { accountRefusal, accountsService } from '@/services/accounts-service'
import type { CodeSent, MyMobile } from '@/validators/accounts-validator'

type Step = { kind: 'idle' } | { kind: 'code'; sent: CodeSent } | { kind: 'done' }

/**
 * Accessibility Settings: verify the mobile number already on the account, so Forgot PIN can text a
 * code. Accounts made while SMS was off have an unverified number. Hidden when this does not apply
 * (old sign-in, no number on the account, or the server could not be asked).
 */
export function MyMobileCard() {
  const [mobile, setMobile] = useState<MyMobile | null>(null)
  const [step, setStep] = useState<Step>({ kind: 'idle' })
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    let current = true
    accountsService.myMobile().then((m) => current && setMobile(m)).catch(() => undefined)
    return () => {
      current = false
    }
  }, [])

  if (!mobile || !mobile.to) return null

  const send = async (): Promise<number | string> => {
    try {
      const sent = await accountsService.myMobileSend()
      return sent.resend_after
    } catch (err) {
      return accountRefusal(err, 'We could not send a code. Please try again later.').detail
    }
  }

  const start = async () => {
    setBusy(true)
    setNotice(null)
    try {
      setStep({ kind: 'code', sent: await accountsService.myMobileSend() })
    } catch (err) {
      setNotice(accountRefusal(err, 'We could not send a code. Please try again later.').detail)
    } finally {
      setBusy(false)
    }
  }

  if (step.kind === 'code') {
    return (
      <section aria-label="Verify your mobile number" className="flex flex-col items-center gap-4 rounded-xl border-2 p-6">
        <SmsCodeEntry title="Verify your mobile number" to={step.sent.to} resendAfter={step.sent.resend_after}
          busy={busy} onResend={send}
          onSubmit={async (code) => {
            try {
              await accountsService.myMobileVerify(code)
              setMobile({ ...mobile, verified: true })
              setStep({ kind: 'done' })
              return null
            } catch (err) {
              const answer = accountRefusal(err, 'Could not check the code. Please try again.')
              return answer.tries_left !== undefined ? `${answer.detail} ${answer.tries_left} tries left.` : answer.detail
            }
          }} />
        <GazeButton variant="outline" onClick={() => setStep({ kind: 'idle' })}>Cancel</GazeButton>
      </section>
    )
  }

  return (
    <Alert className="flex flex-col gap-4">
      <AlertTitle className="flex items-center gap-3 text-2xl">
        <Smartphone aria-hidden /> Mobile number
      </AlertTitle>
      <AlertDescription className="flex flex-col gap-4 text-lg">
        {mobile.verified ? (
          <p className="flex items-center gap-2">
            <CircleCheck className="text-primary" aria-hidden />
            {mobile.to} is verified{step.kind === 'done' ? ' now' : ''}. If you forget your PIN, we can text you a code.
          </p>
        ) : mobile.sms_enabled ? (
          <>
            <p>{mobile.to} is not verified yet. Verify it so you can reset your PIN by text if you forget it.</p>
            {notice && <p role="status" className="text-destructive">{notice}</p>}
            <div>
              <GazeButton disabled={busy} onClick={() => void start()}>
                {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <MessageSquare aria-hidden />}
                Verify by text
              </GazeButton>
            </div>
          </>
        ) : (
          <p>{mobile.to} is not verified yet. Texting is not available right now; if you forget your PIN, ask PDAO staff.</p>
        )}
      </AlertDescription>
    </Alert>
  )
}
