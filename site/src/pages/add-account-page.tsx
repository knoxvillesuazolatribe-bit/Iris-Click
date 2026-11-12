import { ArrowLeft, KeyRound, LoaderCircle, ShieldCheck, Sparkles, UserRoundPlus } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { NewAccountCalibration } from '@/components/new-account-calibration'
import { NumberPad } from '@/components/number-pad'
import { PinEntry } from '@/components/pin-entry'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { USERNAME_MAX, UsernameKeys } from '@/components/username-keys'
import { linkDesktop } from '@/lib/desktop-link'
import { thisComputerId } from '@/lib/device'
import { ONLINE_COPY } from '@/lib/online-copy'
import { DesktopDownloadPage } from '@/pages/desktop-download-page'
import { accountRefusal, accountsService } from '@/services/accounts-service'
import { pendingCalibrationService } from '@/services/pending-calibration-service'
import { useSessionStore } from '@/store/session-store'
import type { AccountSession, PendingCalibration } from '@/validators/accounts-validator'

type Path = 'new' | 'existing'
type Step = 'choose' | 'consent' | 'calibrate' | 'username' | 'mobile' | 'pin' | 'pin-confirm' | 'saving'

const NEW_STEPS: Step[] = ['choose', 'consent', 'calibrate', 'username', 'mobile', 'pin', 'pin-confirm']
const EXISTING_STEPS: Step[] = ['choose', 'calibrate', 'username', 'pin']
const USERNAME_STEP_CODES = ['too_short', 'too_long', 'bad_characters', 'needs_letter', 'bad_edges', 'reserved',
  'not_allowed', 'taken']
const MOBILE_STEP_CODES = ['bad_mobile', 'mobile_limit']
const PIN_STEP_CODES = ['not_six_digits', 'too_easy', 'pin_mismatch']
const MOBILE_DIGITS = 11

function formatMobile(digits: string) {
  return [digits.slice(0, 4), digits.slice(4, 7), digits.slice(7, 11)].filter(Boolean).join(' ')
}

/**
 * Add account (file 07, screens B0-B7, Figure 16): a new person accepts the consent,
 * calibrates in IrisClick Desktop, then chooses a username, a mobile number for PIN
 * recovery and a PIN. "I already have an account" calibrates on this computer and signs
 * in with username and PIN, which adds the account here. The calibration is kept by
 * IrisClick Desktop until the account exists, then attached to it; leaving discards it.
 */
export function AddAccountPage() {
  const navigate = useNavigate()
  const [deviceId, setDeviceId] = useState<string | null | undefined>(undefined)
  const [path, setPath] = useState<Path>('new')
  const [step, setStep] = useState<Step>('choose')
  const [username, setUsername] = useState('')
  const [mobile, setMobile] = useState('')
  const [pin, setPin] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const calibration = useRef<PendingCalibration | null>(null)
  const finished = useRef(false)

  const findDesktop = useCallback(async () => {
    const id = await thisComputerId()
    setDeviceId(id)
    return id !== null
  }, [])

  useEffect(() => {
    void findDesktop()
  }, [findDesktop])

  // Leaving the flow without an account: IrisClick Desktop deletes the calibration made for it.
  useEffect(() => () => {
    if (!finished.current && calibration.current) void pendingCalibrationService.discard(calibration.current.profile_file_id)
  }, [])

  const steps = path === 'new' ? NEW_STEPS : EXISTING_STEPS
  const go = (next: Step) => {
    setMessage(null)
    setSuggestions([])
    setStep(next)
  }

  const discardCalibration = () => {
    if (calibration.current) void pendingCalibrationService.discard(calibration.current.profile_file_id)
    calibration.current = null
  }

  const back = () => {
    if (busy) return
    const i = steps.indexOf(step)
    if (i <= 0) return void navigate('/user/select')
    const previous = step === 'pin-confirm' ? 'pin' : steps[i - 1]
    if (previous === 'calibrate' || previous === 'consent' || previous === 'choose') discardCalibration()
    if (step === 'pin-confirm') setPin('')
    go(previous)
  }

  const finish = async (session: AccountSession, text: string) => {
    useSessionStore.setState({
      status: 'signed-in',
      user: { user_id: session.user_id, full_name: session.full_name, role: session.role },
    })
    if (ONLINE_COPY) await linkDesktop() // IrisClick Desktop must know the new account before attaching
    let note = text
    try {
      await pendingCalibrationService.attach(calibration.current?.profile_file_id ?? null)
    } catch {
      note += ' The calibration could not be added to the account; you can calibrate again from the welcome screen.'
    }
    finished.current = true
    void navigate('/user/select', { replace: true, state: { notice: note } })
  }

  const refused = (err: unknown, fallback: string) => {
    const answer = accountRefusal(err, fallback)
    if (USERNAME_STEP_CODES.includes(answer.code)) {
      setStep('username')
      setSuggestions(answer.suggestions ?? [])
    } else if (MOBILE_STEP_CODES.includes(answer.code)) setStep('mobile')
    else if (PIN_STEP_CODES.includes(answer.code) || answer.code === 'wrong_pin') setStep('pin')
    else if (answer.code === 'wait' || answer.code === 'reset_needed') setStep('pin')
    setPin('')
    setMessage(answer.detail)
  }

  const checkUsername = async () => {
    if (!deviceId) return
    if (path === 'existing') return go('pin')
    setBusy(true)
    try {
      const check = await accountsService.usernameCheck(deviceId, username)
      if (check.available) return go('mobile')
      setMessage(check.message)
      setSuggestions(check.suggestions)
    } catch (err) {
      setMessage(accountRefusal(err, 'Could not check the username. Please try again.').detail)
    } finally {
      setBusy(false)
    }
  }

  const submitNew = async (confirm: string) => {
    if (!deviceId) return
    if (confirm !== pin) {
      setPin('')
      setStep('pin')
      return setMessage("The PINs don't match. Try again.")
    }
    setBusy(true)
    setStep('saving')
    try {
      const session = await accountsService.signUp(deviceId, {
        username, mobile_number: mobile, pin, pin_confirm: confirm, remember: false,
      })
      await finish(session, 'Account created. Look at your name to start.')
    } catch (err) {
      refused(err, 'Could not create your account. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const submitExisting = async (enteredPin: string) => {
    if (!deviceId) return
    setBusy(true)
    setStep('saving')
    try {
      const session = await accountsService.signInWithUsername(deviceId, username, enteredPin)
      await finish(session, `${session.username} was added to this computer.`)
    } catch (err) {
      refused(err, 'Could not sign you in. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  if (deviceId === null) return <DesktopDownloadPage onRetry={findDesktop} />

  const numbered = (label: string) => {
    const order: Step[] = steps.filter((s) => s !== 'choose' && s !== 'consent' && s !== 'pin-confirm')
    const at = order.indexOf(step === 'pin-confirm' ? 'pin' : step)
    return at >= 0 ? `Step ${at + 1} of ${order.length}: ${label}` : label
  }

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center gap-8 p-6">
      <div className="top-band flex w-full max-w-6xl justify-start">
        <GazeButton variant="outline" onClick={back} disabled={busy}>
          <ArrowLeft aria-hidden />
          Back
        </GazeButton>
      </div>

      {message && (
        <Alert variant="destructive" role="alert" className="w-full max-w-3xl">
          <AlertDescription className="text-lg">{message}</AlertDescription>
        </Alert>
      )}

      {deviceId === undefined && <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading" />}

      {deviceId && step === 'choose' && (
        <section className="flex w-full max-w-3xl flex-col items-center gap-6 text-center">
          <h1 className="text-4xl font-bold">Add your account</h1>
          <GazeButton autoFocus className="min-h-24 w-full text-2xl" onClick={() => { setPath('new'); go('consent') }}>
            <UserRoundPlus aria-hidden /> I'm new: create my account
          </GazeButton>
          <GazeButton variant="outline" className="min-h-24 w-full text-2xl" onClick={() => { setPath('existing'); go('calibrate') }}>
            <KeyRound aria-hidden /> I already have an account
          </GazeButton>
        </section>
      )}

      {deviceId && step === 'consent' && (
        <section className="flex w-full max-w-3xl flex-col items-center gap-6 text-center">
          <h1 className="flex items-center gap-3 text-4xl font-bold"><ShieldCheck className="text-primary size-10" aria-hidden /> Before you start</h1>
          <div className="bg-card space-y-3 rounded-2xl border-2 p-6 text-left text-xl">
            <p>IrisClick saves: your username, mobile number, eye calibration, settings, messages and SOS contacts.</p>
            <p>Why: so IrisClick works for you on this computer.</p>
            <p>Your camera picture stays on this computer. It is not saved or sent.</p>
            <p className="text-muted-foreground text-base">Data Privacy Act of 2012 (Republic Act No. 10173)</p>
          </div>
          <GazeButton autoFocus className="min-h-24 min-w-80 text-2xl" onClick={() => go('calibrate')}>I agree</GazeButton>
        </section>
      )}

      {deviceId && step === 'calibrate' && (
        <NewAccountCalibration
          stepLabel={numbered(path === 'new' ? 'Calibrate your eyes' : 'Calibrate your eyes on this computer')}
          onDone={(pending) => { calibration.current = pending; go('username') }} />
      )}

      {deviceId && step === 'username' && (
        <section className="flex w-full max-w-4xl flex-col items-center gap-5 text-center">
          <h1 className="text-4xl font-bold">{numbered(path === 'new' ? 'Choose a username' : 'Your username')}</h1>
          <p aria-live="polite" className="bg-card min-h-16 w-full max-w-xl rounded-2xl border-2 p-3 text-3xl font-bold break-all">
            {username || <span className="text-muted-foreground text-xl font-normal">3 to {USERNAME_MAX} letters, numbers, _ .</span>}
          </p>
          {suggestions.length > 0 && (
            <div className="flex flex-wrap items-center justify-center gap-4">
              <span className="text-xl">Try:</span>
              {suggestions.map((s) => (
                <GazeButton key={s} variant="outline" onClick={() => { setUsername(s); setSuggestions([]); setMessage(null) }}>{s}</GazeButton>
              ))}
            </div>
          )}
          <UsernameKeys value={username} onChange={(v) => { setUsername(v); setMessage(null) }} disabled={busy}
            okDisabled={username.length < 3} onOk={() => void checkUsername()} />
        </section>
      )}

      {deviceId && step === 'mobile' && (
        <section className="flex w-full max-w-3xl flex-col items-center gap-6 text-center">
          <h1 className="text-4xl font-bold">{numbered('Your mobile number')}</h1>
          <p className="text-muted-foreground text-xl">For when you forget your PIN.</p>
          <p aria-live="polite" className="bg-card min-h-16 min-w-80 rounded-2xl border-2 p-3 text-3xl font-bold tabular-nums">
            {formatMobile(mobile) || <span className="text-muted-foreground text-xl font-normal">0917 123 4567</span>}
          </p>
          <NumberPad
            onDigit={(d) => { setMobile((m) => (m.length < MOBILE_DIGITS ? m + d : m)); setMessage(null) }}
            onDelete={() => setMobile((m) => m.slice(0, -1))}
            okDisabled={!/^09\d{9}$/.test(mobile)}
            onOk={() => go('pin')} />
          <p className="text-muted-foreground max-w-2xl text-lg">
            We can't text you yet. If you forget your PIN, ask PDAO staff.
          </p>
        </section>
      )}

      {deviceId && step === 'pin' && (
        <section className="flex w-full max-w-3xl flex-col items-center gap-6 text-center">
          <h1 className="text-4xl font-bold">{numbered(path === 'new' ? 'Create your PIN' : 'Enter your PIN')}</h1>
          {path === 'new' && <p className="text-muted-foreground text-xl">6 numbers that are easy for you to remember.</p>}
          <PinEntry disabled={busy}
            onSubmit={(entered) => (path === 'new' ? (setPin(entered), go('pin-confirm')) : void submitExisting(entered))} />
        </section>
      )}

      {deviceId && step === 'pin-confirm' && (
        <section className="flex w-full max-w-3xl flex-col items-center gap-6 text-center">
          <h1 className="text-4xl font-bold">{numbered('Confirm your PIN')}</h1>
          <PinEntry disabled={busy} okLabel="Create" onSubmit={(entered) => void submitNew(entered)} />
        </section>
      )}

      {step === 'saving' && (
        <section className="flex flex-col items-center gap-6 text-center">
          <Sparkles className="text-primary size-12" aria-hidden />
          <p className="text-2xl">{path === 'new' ? 'Creating your account…' : 'Adding your account to this computer…'}</p>
          <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Saving" />
        </section>
      )}
    </main>
  )
}
