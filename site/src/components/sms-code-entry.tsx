import { MessageSquare, RotateCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { GazeButton } from '@/components/gaze-button'
import { NumberPad } from '@/components/number-pad'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'

export const SMS_CODE_DIGITS = 6

interface SmsCodeEntryProps {
  title: string
  /** Masked number the code went to, e.g. 09** *** 2488. */
  to: string
  /** Seconds until Resend may be picked. */
  resendAfter: number
  /** Check the code; resolve with an error message to show, or null when it was right. */
  onSubmit: (code: string) => Promise<string | null>
  /** Text a new code; resolve with the new wait in seconds, or an error message. */
  onResend: () => Promise<number | string>
  busy?: boolean
}

/**
 * Screens B4b and F3: "Enter the 6-digit code we sent to 09** *** 2488" on the large number
 * pad, with Resend after 60 s. The code lives only in this component's memory.
 */
export function SmsCodeEntry({ title, to, resendAfter, onSubmit, onResend, busy }: SmsCodeEntryProps) {
  const [code, setCode] = useState('')
  const [wait, setWait] = useState(resendAfter)
  const [message, setMessage] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    if (wait <= 0) return
    const timer = window.setTimeout(() => setWait((s) => s - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [wait])

  const digit = useCallback((d: string) => setCode((c) => (c.length < SMS_CODE_DIGITS ? c + d : c)), [])
  const erase = useCallback(() => setCode((c) => c.slice(0, -1)), [])
  const ok = useCallback(async () => {
    if (code.length !== SMS_CODE_DIGITS) return
    setChecking(true)
    setMessage(null)
    const problem = await onSubmit(code)
    setChecking(false)
    if (problem) {
      setMessage(problem)
      setCode('')
    }
  }, [code, onSubmit])
  const resend = async () => {
    setChecking(true)
    setMessage(null)
    const answer = await onResend()
    setChecking(false)
    if (typeof answer === 'number') {
      setWait(answer)
      setMessage('A new code is on its way.')
    } else setMessage(answer)
  }

  const disabled = busy || checking
  return (
    <section className="flex w-full max-w-5xl flex-col items-center gap-5 text-center">
      <h1 className="text-4xl font-bold">{title}</h1>
      <p className="text-muted-foreground flex items-center gap-3 text-2xl">
        <MessageSquare aria-hidden /> Enter the 6-digit code we sent to {to}
      </p>
      {message && (
        <Alert role="status" className="max-w-3xl text-left">
          <AlertDescription className="text-lg">{message}</AlertDescription>
        </Alert>
      )}
      <div className="flex w-full flex-wrap items-end justify-center gap-8">
        <div className="flex flex-col items-center gap-6">
          <div role="status" aria-label={`${code.length} of ${SMS_CODE_DIGITS} digits entered`} className="flex gap-3">
            {Array.from({ length: SMS_CODE_DIGITS }, (_, i) => (
              <span key={i} aria-hidden
                className={cn('flex size-14 items-center justify-center rounded-xl border-2 text-3xl font-bold tabular-nums',
                  i < code.length ? 'border-primary' : 'border-muted-foreground/50')}>
                {code[i] ?? ''}
              </span>
            ))}
          </div>
          <NumberPad onDigit={digit} onDelete={erase} onOk={() => void ok()} okDisabled={code.length !== SMS_CODE_DIGITS}
            disabled={disabled} />
        </div>
        <div className="flex max-w-72 flex-col items-stretch gap-4">
          <GazeButton variant="outline" className="h-auto py-3 whitespace-normal" disabled={disabled || wait > 0}
            onClick={() => void resend()}>
            <RotateCw aria-hidden />
            {wait > 0 ? `Resend code (${wait} s)` : 'Resend code'}
          </GazeButton>
        </div>
      </div>
    </section>
  )
}
