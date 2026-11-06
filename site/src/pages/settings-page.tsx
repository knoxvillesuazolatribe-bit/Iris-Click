import { ArrowLeft, LoaderCircle, Play, RefreshCw, RotateCcw, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { AccessibilityFields } from '@/components/accessibility-fields'
import { SilentBoundary } from '@/components/silent-boundary'
import { VoiceSettingsPanel } from '@/components/voice-settings-panel'
import { myVoiceSettings } from '@/services/voice-settings-service'
import { GazeButton } from '@/components/gaze-button'
import { ServerDown } from '@/components/server-down'
import { TwoPressButton } from '@/components/two-press-button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { homeService, restartTracking } from '@/services/home-service'
import { settingsService } from '@/services/settings-service'
import { type AccessibilitySettings, type AccessibilityValues } from '@/validators/settings-validator'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; saved: AccessibilitySettings }
type Notice = { kind: 'ok' | 'error'; title: string; text: string } | null
type Restart = 'idle' | 'confirm' | 'busy' | 'failed'

const KEYS: (keyof AccessibilityValues)[] = [
  'dwell_enabled', 'dwell_ms', 'smoothing', 'blink_to_click', 'blink_sensitivity', 'edge_scroll_enabled', 'voice_volume',
]

const valuesOf = (s: AccessibilitySettings): AccessibilityValues =>
  Object.fromEntries(KEYS.map((k) => [k, s[k]])) as AccessibilityValues

/** Screens 26–28: the signed-in user's accessibility settings. */
export function SettingsPage() {
  const navigate = useNavigate()
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [draft, setDraft] = useState<AccessibilityValues | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)
  const [restart, setRestart] = useState<Restart>('idle')

  useEffect(() => {
    let current = true
    settingsService
      .get()
      .then((saved) => {
        if (!current) return
        setLoad({ state: 'ready', saved })
        setDraft(valuesOf(saved))
      })
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load your settings.') }))
    return () => {
      current = false
    }
  }, [attempt])

  const header = (
    <header className="top-band flex flex-wrap items-center justify-between gap-6">
      <div>
        <h1 className="text-4xl font-bold">Accessibility Settings</h1>
        <p className="text-muted-foreground mt-2 text-xl">Change one thing at a time, then choose Save.</p>
      </div>
      <GazeButton variant="outline" onClick={() => void navigate('/home')}>
        <ArrowLeft aria-hidden />
        Home
      </GazeButton>
    </header>
  )

  if (load.state !== 'ready' || !draft) {
    return (
      <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col gap-8 p-6">
        {header}
        {load.state === 'error' ? (
          <div className="flex justify-center">
            <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); setAttempt((n) => n + 1) }} />
          </div>
        ) : (
          <LoaderCircle className="text-muted-foreground mx-auto size-12 animate-spin" aria-label="Loading" />
        )}
      </main>
    )
  }

  const saved = valuesOf(load.saved)
  const changed = KEYS.some((k) => draft[k] !== saved[k])
  const set = <K extends keyof AccessibilityValues>(key: K, value: AccessibilityValues[K]) => {
    setDraft({ ...draft, [key]: value })
    setConfirming(false)
    setNotice(null)
  }

  const apply = async (action: () => Promise<AccessibilitySettings>, title: string) => {
    setBusy(true)
    setConfirming(false)
    try {
      const next = await action()
      setLoad({ state: 'ready', saved: next })
      setDraft(valuesOf(next))
      setNotice({ kind: 'ok', title, text: 'Voice volume works now. The other settings take effect the next time eye tracking starts.' })
      setRestart('idle')
    } catch (err) {
      setNotice({ kind: 'error', title: 'Not saved', text: errorMessage(err, 'Your settings were not saved.') })
    } finally {
      setBusy(false)
    }
  }

  const runRestart = async (start = false) => {
    setRestart('busy')
    try {
      await (start ? homeService.startTracking() : restartTracking())
      setRestart('idle')
      setNotice({ kind: 'ok', title: 'Eye tracking restarted', text: 'Your new settings are in use now.' })
    } catch (err) {
      setRestart('failed')
      setNotice({ kind: 'error', title: 'Eye tracking is not running', text: errorMessage(err, 'Eye tracking could not start.') })
    }
  }

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col gap-6 p-6">
      {header}

      {notice && (
        <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status">
          <AlertTitle className="text-xl">{notice.title}</AlertTitle>
          <AlertDescription className="text-lg">{notice.text}</AlertDescription>
          {notice.kind === 'ok' && restart === 'idle' && notice.title !== 'Eye tracking restarted' && (
            <div className="mt-4 flex flex-wrap items-center gap-6">
              <GazeButton variant="outline" onClick={() => setRestart('confirm')}>
                <RefreshCw aria-hidden />
                Restart eye tracking now
              </GazeButton>
            </div>
          )}
          {restart === 'confirm' && (
            <div className="mt-4 space-y-4">
              <p className="text-lg font-semibold">The cursor stops for about 5 seconds while eye tracking restarts.</p>
              <div className="flex flex-wrap gap-6">
                <GazeButton onClick={() => void runRestart()} autoFocus>
                  <RefreshCw aria-hidden />
                  Yes, restart
                </GazeButton>
                <GazeButton variant="outline" onClick={() => setRestart('idle')}>Cancel</GazeButton>
              </div>
            </div>
          )}
          {restart === 'busy' && <LoaderCircle className="mt-4 size-10 animate-spin" aria-label="Restarting" />}
          {restart === 'failed' && (
            <div className="mt-4">
              <GazeButton onClick={() => void runRestart(true)}>
                <Play aria-hidden />
                Start eye tracking
              </GazeButton>
            </div>
          )}
        </Alert>
      )}

      <AccessibilityFields draft={draft} set={set} />
      <SilentBoundary><VoiceSettingsPanel api={myVoiceSettings} volume={draft.voice_volume} /></SilentBoundary>

      <footer className="bg-background sticky bottom-0 flex flex-wrap items-center justify-between gap-6 border-t-2 py-6">
        {confirming ? (
          <div className="flex flex-wrap items-center gap-6" role="group" aria-label="Confirm save">
            <span className="text-2xl font-bold">Are you sure?</span>
            <GazeButton autoFocus disabled={busy} onClick={() => void apply(() => settingsService.save(draft), 'Your settings are saved')}>
              {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <Save aria-hidden />}
              Yes, save
            </GazeButton>
            <GazeButton variant="outline" onClick={() => setConfirming(false)}>Cancel</GazeButton>
          </div>
        ) : (
          <GazeButton disabled={!changed || busy} onClick={() => setConfirming(true)} className="min-w-56">
            <Save aria-hidden />
            {changed ? 'Save' : 'No changes'}
          </GazeButton>
        )}
        <TwoPressButton icon={RotateCcw} label="Reset to Default" confirmLabel="Yes, reset"
          disabled={busy || (load.saved.is_default && !changed)}
          onConfirm={() => void apply(() => settingsService.reset(), 'Settings are back to default')} />
      </footer>
    </main>
  )
}
