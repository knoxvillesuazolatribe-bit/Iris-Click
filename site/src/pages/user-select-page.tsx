import { ArrowLeft, Crosshair, LoaderCircle, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { DesktopStartButtons } from '@/components/desktop-start-buttons'
import { GazeButton } from '@/components/gaze-button'
import { ServerDown } from '@/components/server-down'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { UserTile } from '@/components/user-tile'
import { linkDesktop } from '@/lib/desktop-link'
import { ONLINE_COPY } from '@/lib/online-copy'
import { assistiveService } from '@/services/auth-service'
import { trackingService } from '@/services/tracking-service'
import { useSessionStore } from '@/store/session-store'
import type { AssistiveTile } from '@/validators/auth-validator'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; tiles: AssistiveTile[] }

/**
 * Assistive-user sign-in: pick your name tile, then continue with your saved
 * calibration or calibrate. Two steps, so a stray wink never starts anything.
 */
export function UserSelectPage() {
  const navigate = useNavigate()
  const selectUser = useSessionStore((s) => s.selectUser)
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [chosen, setChosen] = useState<AssistiveTile | null>(null)
  const [busy, setBusy] = useState<'continue' | 'calibrate' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    assistiveService
      .getTiles()
      .then((tiles) => current && setLoad({ state: 'ready', tiles }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load the names.') }))
    return () => {
      current = false
    }
  }, [attempt])

  const retry = () => {
    setLoad({ state: 'loading' })
    setAttempt((n) => n + 1)
  }

  const choose = (tile: AssistiveTile | null) => {
    setChosen(tile)
    setError(null)
  }

  const signIn = async (tile: AssistiveTile) => {
    const current = useSessionStore.getState().user
    if (current?.role === 'assistive_user' && current.user_id === tile.user_id) {
      if (ONLINE_COPY) void linkDesktop() // hybrid hook: tell IrisClick Desktop who is signed in
      return true
    }
    const message = await selectUser(tile.user_id)
    if (message) setError(message)
    if (message === null && ONLINE_COPY) void linkDesktop() // hybrid hook
    return message === null
  }

  const continueSaved = async (tile: AssistiveTile) => {
    if (!tile.continue_profile_id) return
    setBusy('continue')
    setError(null)
    try {
      if (!(await signIn(tile))) return
      await trackingService.start(tile.continue_profile_id)
      void navigate('/home')
    } catch (err) {
      setError(`${errorMessage(err, 'Eye tracking could not start.')} You can choose Calibrate instead.`)
    } finally {
      setBusy(null)
    }
  }

  const calibrate = async (tile: AssistiveTile) => {
    setBusy('calibrate')
    setError(null)
    try {
      if (await signIn(tile)) void navigate('/calibration')
    } finally {
      setBusy(null)
    }
  }

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center gap-10 p-6">
      <div className="top-band flex w-full max-w-6xl justify-start">
        <GazeButton variant="outline" onClick={() => (chosen ? choose(null) : void navigate('/'))}>
          <ArrowLeft aria-hidden />
          Back
        </GazeButton>
      </div>

      {chosen ? (
        <section className="flex w-full max-w-3xl flex-col items-center gap-8 text-center">
          <h1 className="text-4xl font-bold">Hello, {chosen.full_name}</h1>
          <p className="text-muted-foreground text-xl">What would you like to do?</p>
          {error && (
            <Alert variant="destructive" role="alert" className="text-left">
              <AlertDescription className="text-base">{error}</AlertDescription>
            </Alert>
          )}
          {ONLINE_COPY ? (
            <DesktopStartButtons signIn={() => signIn(chosen)} onError={setError} />
          ) : (
          <div className="flex w-full flex-col gap-6">
            <GazeButton
              className="min-h-28 w-full text-2xl"
              disabled={!chosen.continue_profile_id || busy !== null}
              onClick={() => void continueSaved(chosen)}
            >
              {busy === 'continue' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Play aria-hidden />}
              Continue with saved calibration
            </GazeButton>
            {chosen.continue_unavailable_reason && (
              <p className="text-muted-foreground -mt-3 text-lg">{chosen.continue_unavailable_reason}</p>
            )}
            <GazeButton
              variant="outline"
              className="min-h-28 w-full text-2xl"
              disabled={busy !== null}
              onClick={() => void calibrate(chosen)}
            >
              {busy === 'calibrate' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Crosshair aria-hidden />}
              Calibrate
            </GazeButton>
          </div>
          )}
        </section>
      ) : (
        <section className="flex w-full max-w-6xl flex-col items-center gap-8">
          <h1 className="text-4xl font-bold">Who is using IrisClick?</h1>
          {load.state === 'loading' && (
            <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading names" />
          )}
          {load.state === 'error' && <ServerDown message={load.message} onRetry={retry} />}
          {load.state === 'ready' && load.tiles.length === 0 && (
            <p className="text-muted-foreground max-w-xl text-center text-2xl">
              No accounts yet. Ask your administrator to create your account.
            </p>
          )}
          {load.state === 'ready' && load.tiles.length > 0 && (
            <>
              <p className="text-muted-foreground text-xl">Look at your name and wink your left eye.</p>
              <div className="grid w-full grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-6">
                {load.tiles.map((tile) => (
                  <UserTile key={tile.user_id} tile={tile} onSelect={choose} />
                ))}
              </div>
            </>
          )}
        </section>
      )}
    </main>
  )
}
