import { ArrowLeft, LoaderCircle, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { AccountTile } from '@/components/account-tile'
import { DesktopStartButtons } from '@/components/desktop-start-buttons'
import { GazeButton } from '@/components/gaze-button'
import { ForgotPinScreen, PinScreen } from '@/components/pin-screen'
import { ServerDown } from '@/components/server-down'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { linkDesktop } from '@/lib/desktop-link'
import { thisComputerId } from '@/lib/device'
import { ONLINE_COPY } from '@/lib/online-copy'
import { DesktopDownloadPage } from '@/pages/desktop-download-page'
import { accountRefusal, accountsService } from '@/services/accounts-service'
import { useSessionStore } from '@/store/session-store'
import type { AccountRefusal, AccountSession, AccountTile as Tile, Tiles } from '@/validators/accounts-validator'

type Load =
  | { state: 'finding' }
  | { state: 'no-desktop' }
  | { state: 'error'; message: string }
  | { state: 'ready'; deviceId: string; tiles: Tiles }

type View =
  | { kind: 'pick' }
  | { kind: 'remove' }
  | { kind: 'confirm-remove'; tile: Tile }
  | { kind: 'pin'; tile: Tile; purpose: 'signin' | 'remove' }
  | { kind: 'forgot'; tile: Tile; purpose: 'signin' | 'remove' }
  | { kind: 'welcome'; username: string }

/**
 * Accounts on this computer (file 07, screens A1-A4): the accounts added to this
 * computer, Add account, and Remove account with a confirm step. It needs IrisClick
 * Desktop, which gives this computer's ID; without it, the download page shows.
 */
export function AccountsPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [load, setLoad] = useState<Load>({ state: 'finding' })
  const [view, setView] = useState<View>({ kind: 'pick' })
  const [busy, setBusy] = useState(false)
  // Coming back from Add account: "Account created. Look at your name to start."
  const [message, setMessage] = useState<string | null>(
    (location.state as { notice?: string } | null)?.notice ?? null)
  const [refusal, setRefusal] = useState<AccountRefusal | null>(null)

  const askPin = (tile: Tile, purpose: 'signin' | 'remove') => {
    setRefusal(null)
    setView({ kind: 'pin', tile, purpose })
  }

  const refresh = useCallback(async (): Promise<boolean> => {
    const deviceId = await thisComputerId()
    if (!deviceId) {
      setLoad({ state: 'no-desktop' })
      return false
    }
    try {
      setLoad({ state: 'ready', deviceId, tiles: await accountsService.tiles(deviceId) })
    } catch (err) {
      setLoad({ state: 'error', message: accountRefusal(err, 'Could not load the accounts.').detail })
    }
    return true
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const signedIn = (session: AccountSession) => {
    useSessionStore.setState({
      status: 'signed-in',
      user: { user_id: session.user_id, full_name: session.full_name, role: session.role },
    })
    if (ONLINE_COPY) void linkDesktop() // tell IrisClick Desktop who is signed in
    setView({ kind: 'welcome', username: session.username })
  }

  const pick = async (tile: Tile) => {
    setMessage(null)
    if (load.state !== 'ready') return
    if (tile.needs_pin) return askPin(tile, 'signin')
    setBusy(true)
    try {
      signedIn(await accountsService.signInWithTile(load.deviceId, tile.user_id))
    } catch (err) {
      const answer = accountRefusal(err, 'Could not sign you in. Please try again.')
      if (answer.code === 'pin_required') askPin(tile, 'signin')
      else setMessage(answer.detail)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (tile: Tile) => {
    if (load.state !== 'ready') return
    setBusy(true)
    try {
      await accountsService.remove(load.deviceId, tile.user_id)
      setView({ kind: 'pick' })
      setMessage(`${tile.username} was removed from this computer.`)
      await refresh()
    } catch (err) {
      const answer = accountRefusal(err, 'Could not remove the account. Please try again.')
      if (answer.code === 'pin_required') return askPin(tile, 'remove')
      setView({ kind: 'pick' })
      setMessage(answer.detail)
    } finally {
      setBusy(false)
    }
  }

  /** The PIN from the number pad: sign in, or (shared computer) remove the account. */
  const submitPin = async (pin: string, remember: boolean) => {
    if (load.state !== 'ready' || view.kind !== 'pin') return
    const { tile, purpose } = view
    setBusy(true)
    setRefusal(null)
    try {
      if (purpose === 'remove') {
        await accountsService.remove(load.deviceId, tile.user_id, pin)
        setView({ kind: 'pick' })
        setMessage(`${tile.username} was removed from this computer.`)
        await refresh()
      } else {
        signedIn(await accountsService.signInWithTile(load.deviceId, tile.user_id, pin, remember))
      }
    } catch (err) {
      setRefusal(accountRefusal(err, 'Could not check your PIN. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  const back = () => {
    setMessage(null)
    if (view.kind === 'pick' || view.kind === 'welcome') return void navigate('/')
    if (view.kind === 'forgot') return askPin(view.tile, view.purpose)
    setView({ kind: 'pick' })
  }

  if (load.state === 'no-desktop') return <DesktopDownloadPage onRetry={refresh} />

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center gap-10 p-6">
      <div className="top-band flex w-full max-w-6xl justify-start">
        <GazeButton variant="outline" onClick={back} disabled={busy}>
          <ArrowLeft aria-hidden />
          Back
        </GazeButton>
      </div>

      {message && (
        <Alert role="status" className="w-full max-w-3xl">
          <AlertDescription className="text-lg">{message}</AlertDescription>
        </Alert>
      )}

      {view.kind === 'welcome' ? (
        <section className="flex w-full max-w-3xl flex-col items-center gap-8 text-center">
          <h1 className="text-4xl font-bold break-all">Hello, {view.username}</h1>
          <p className="text-muted-foreground text-xl">How would you like to start?</p>
          <DesktopStartButtons signIn={() => Promise.resolve(true)} onError={setMessage} />
        </section>
      ) : view.kind === 'pin' ? (
        <PinScreen username={view.tile.username} purpose={view.purpose} busy={busy} refusal={refusal}
          showRemember={load.state === 'ready' && !load.tiles.is_shared}
          onSubmit={(pin, remember) => void submitPin(pin, remember)}
          onForgot={() => setView({ kind: 'forgot', tile: view.tile, purpose: view.purpose })} />
      ) : view.kind === 'forgot' ? (
        <ForgotPinScreen onBack={back} onSetupCode={() => void navigate('/user/add', { state: { path: 'code' } })} />
      ) : view.kind === 'confirm-remove' ? (
        <section role="alertdialog" aria-labelledby="remove-title"
          className="flex w-full max-w-3xl flex-col items-center gap-8 text-center">
          <h1 id="remove-title" className="text-4xl font-bold break-all">Remove {view.tile.username} from this computer?</h1>
          <p className="text-muted-foreground text-xl">
            The account is not deleted. It can be added again with the username and PIN.
          </p>
          <div className="flex w-full flex-wrap items-center justify-center gap-8">
            <GazeButton autoFocus className="min-h-28 min-w-80 text-2xl" disabled={busy}
              onClick={() => setView({ kind: 'pick' })}>
              Cancel
            </GazeButton>
            <GazeButton variant="destructive" disabled={busy} onClick={() => void remove(view.tile)}>
              {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <Trash2 aria-hidden />}
              Remove
            </GazeButton>
          </div>
        </section>
      ) : (
        <section className="flex w-full max-w-6xl flex-col items-center gap-8">
          <h1 className="text-4xl font-bold">
            {view.kind === 'remove' ? 'Which account do you want to remove?' : 'Who is using IrisClick?'}
          </h1>
          {load.state === 'ready' && load.tiles.is_shared && (
            <p className="bg-card rounded-xl border-2 px-5 py-2 text-lg">
              Shared computer: enter your PIN every time. You are signed out when nobody uses it for a while.
            </p>
          )}
          {load.state === 'finding' && (
            <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading accounts" />
          )}
          {load.state === 'error' && (
            <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'finding' }); void refresh() }} />
          )}
          {load.state === 'ready' && (
            <>
              {load.tiles.accounts.length === 0 ? (
                <p className="text-muted-foreground text-2xl">Add your account to start.</p>
              ) : (
                <p className="text-muted-foreground text-xl">
                  {view.kind === 'remove' ? 'Look at the account and wink your left eye.'
                    : 'Look at your name and wink your left eye.'}
                </p>
              )}
              <div className="grid w-full grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-6">
                {load.tiles.accounts.map((tile) => (
                  <AccountTile key={tile.user_id} tile={tile} removing={view.kind === 'remove'} disabled={busy}
                    onSelect={(t) => (view.kind === 'remove' ? setView({ kind: 'confirm-remove', tile: t }) : void pick(t))} />
                ))}
              </div>
              <div className={`flex w-full flex-wrap items-center gap-6 ${
                load.tiles.accounts.length === 0 ? 'justify-center' : 'justify-between'}`}>
                {view.kind === 'remove' ? (
                  <GazeButton variant="outline" className="ml-auto min-w-48" onClick={() => setView({ kind: 'pick' })}>
                    Cancel
                  </GazeButton>
                ) : (
                  <>
                    <GazeButton className="min-h-20 text-xl" disabled={busy} onClick={() => void navigate('/user/add')}>
                      <Plus aria-hidden />
                      Add account
                    </GazeButton>
                    {load.tiles.accounts.length > 0 && (
                      <GazeButton variant="outline" disabled={busy} onClick={() => { setMessage(null); setView({ kind: 'remove' }) }}>
                        <Trash2 aria-hidden />
                        Remove account
                      </GazeButton>
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </section>
      )}
    </main>
  )
}
