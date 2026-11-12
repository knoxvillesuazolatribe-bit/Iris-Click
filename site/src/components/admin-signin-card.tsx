import { KeyRound, LockOpen, LogOut, Ticket } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { errorMessage } from '@/api/app-client'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { adminAccountsService } from '@/services/admin-accounts-service'
import type { AdminAccountDetail, SetupCodeMade } from '@/validators/accounts-validator'

type Action = 'reset' | 'unlock' | 'signout'
type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; account: AdminAccountDetail | null }

const CONFIRM: Record<Action, { ask: string; yes: string }> = {
  reset: {
    ask: 'Make a setup code? Their current PIN stops working; they choose a new one with the code.',
    yes: 'Yes, make a code',
  },
  unlock: { ask: 'Clear their wrong PIN tries on every computer?', yes: 'Yes, unlock' },
  signout: {
    ask: 'Sign them out on every computer? Each computer will ask for their PIN next time.',
    yes: 'Yes, sign out everywhere',
  },
}
const LOCK_TEXT = { ok: 'Not locked', locked: 'Locked: too many wrong PINs', needs_new_pin: 'Needs a new PIN' } as const
const DATE = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/**
 * Admin user page, accounts on this computer (build step 14): username, masked mobile,
 * computers, lock state, and Reset PIN / Unlock / Sign out everywhere. Admins never see a PIN;
 * Reset PIN shows an 8-digit setup code once.
 */
export function AdminSigninCard({ userId, name }: { userId: number; name: string }) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [confirm, setConfirm] = useState<Action | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [code, setCode] = useState<SetupCodeMade | null>(null)

  const refresh = useCallback(async () => {
    try {
      setLoad({ state: 'ready', account: await adminAccountsService.detail(userId) })
    } catch (err) {
      setLoad({ state: 'error', message: errorMessage(err, 'Could not load the sign-in details.') })
    }
  }, [userId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const run = async (action: Action) => {
    setBusy(true)
    setNotice(null)
    setCode(null)
    try {
      if (action === 'reset') setCode(await adminAccountsService.resetPin(userId))
      if (action === 'unlock') {
        await adminAccountsService.unlock(userId)
        setNotice({ kind: 'ok', text: `${name} can try their PIN again.` })
      }
      if (action === 'signout') {
        await adminAccountsService.signOutEverywhere(userId)
        setNotice({ kind: 'ok', text: `${name} was signed out on every computer.` })
      }
      await refresh()
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'That did not work. Please try again.') })
    } finally {
      setBusy(false)
      setConfirm(null)
    }
  }

  const account = load.state === 'ready' ? load.account : null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><KeyRound aria-hidden /> Sign-in</CardTitle>
        <CardDescription>
          {name} signs in on their computer with a username and a 6-digit PIN. You never see their PIN.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {load.state === 'loading' && <p className="text-muted-foreground">Loading…</p>}
        {load.state === 'error' && <p className="text-destructive">{load.message}</p>}
        {load.state === 'ready' && !account && (
          <p className="text-muted-foreground">
            No account on a computer yet. Make a setup code so they can choose a username and PIN on their computer.
          </p>
        )}
        {account && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2">
            <dt className="text-muted-foreground">Username</dt><dd className="font-medium">{account.username}</dd>
            <dt className="text-muted-foreground">Mobile</dt>
            <dd>{account.mobile || '—'}{account.mobile && !account.mobile_verified && <span className="text-muted-foreground"> · not verified</span>}</dd>
            <dt className="text-muted-foreground">Computers</dt>
            <dd>{account.computers}{account.shared_computers > 0 && ` (${account.shared_computers} shared)`}</dd>
            <dt className="text-muted-foreground">PIN</dt>
            <dd className="flex flex-wrap gap-2">
              <Badge variant={account.lock === 'ok' ? 'secondary' : 'destructive'}>{LOCK_TEXT[account.lock]}</Badge>
              {account.must_reset_pin && <Badge variant="outline">Waiting for a new PIN</Badge>}
            </dd>
          </dl>
        )}

        {code && (
          <Alert role="status">
            <Ticket aria-hidden />
            <AlertTitle>Setup code for {name}</AlertTitle>
            <AlertDescription>
              <p className="my-1 font-mono text-3xl font-bold tracking-widest">{code.code}</p>
              <p>Shown only now. Give it to {name}; it works once, until {DATE.format(new Date(code.expires_at))}.</p>
              <p>On their computer: Add account → I have a setup code from PDAO.</p>
            </AlertDescription>
          </Alert>
        )}
        {notice && (
          <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status">
            <AlertDescription>{notice.text}</AlertDescription>
          </Alert>
        )}

        {confirm ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="w-full">{CONFIRM[confirm].ask}</p>
            <Button variant={confirm === 'reset' ? 'default' : 'destructive'} disabled={busy} onClick={() => void run(confirm)}>
              {CONFIRM[confirm].yes}
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => setConfirm(null)}>Cancel</Button>
          </div>
        ) : (
          load.state === 'ready' && (
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => setConfirm('reset')}><Ticket aria-hidden /> {account ? 'Reset PIN' : 'Make setup code'}</Button>
              {account && (
                <>
                  <Button variant="outline" disabled={account.lock === 'ok'} onClick={() => setConfirm('unlock')}>
                    <LockOpen aria-hidden /> Unlock
                  </Button>
                  <Button variant="outline" onClick={() => setConfirm('signout')}><LogOut aria-hidden /> Sign out everywhere</Button>
                </>
              )}
            </div>
          )
        )}
      </CardContent>
    </Card>
  )
}
