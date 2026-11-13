import { Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { errorMessage } from '@/api/app-client'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { thisComputerId } from '@/lib/device'
import { accountsService } from '@/services/accounts-service'
import { adminAccountsService } from '@/services/admin-accounts-service'

type Load =
  | { state: 'loading' }
  | { state: 'no-desktop' }
  | { state: 'error'; message: string }
  | { state: 'ready'; deviceId: string; shared: boolean; idleMinutes: number }

/**
 * Settings → System, accounts on this computer (build step 14): Shared computer on or off
 * for the PC the admin is using. Shared: no "Remember me", and sign-out when nobody uses it.
 */
export function AdminSharedComputerCard() {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    void (async () => {
      const deviceId = await thisComputerId()
      if (!alive) return
      if (!deviceId) return setLoad({ state: 'no-desktop' })
      try {
        const computer = await accountsService.thisComputer(deviceId)
        if (alive) setLoad({ state: 'ready', deviceId, shared: computer.is_shared, idleMinutes: computer.idle_minutes })
      } catch (err) {
        if (alive) setLoad({ state: 'error', message: errorMessage(err, 'Could not read this computer.') })
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  const flip = async () => {
    if (load.state !== 'ready') return
    setBusy(true)
    setError(null)
    try {
      const shared = await adminAccountsService.setShared(load.deviceId, !load.shared)
      setLoad({ ...load, shared })
    } catch (err) {
      setError(errorMessage(err, 'The setting was not changed.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Users aria-hidden /> Shared computer</CardTitle>
        <CardDescription>For this computer only, for example a PDAO office or library PC used by many people.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {load.state === 'loading' && <p className="text-muted-foreground">Loading…</p>}
        {load.state === 'no-desktop' && (
          <p className="text-muted-foreground">Open IrisClick Desktop on this computer to change this setting here.</p>
        )}
        {load.state === 'error' && <p className="text-destructive">{load.message}</p>}
        {load.state === 'ready' && (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p>
              {load.shared
                ? `Shared: everyone enters their PIN every time, and is signed out after ${load.idleMinutes} minutes without use.`
                : 'Personal: people can choose “Remember me” on this computer.'}
            </p>
            <Button variant={load.shared ? 'outline' : 'default'} disabled={busy} aria-pressed={load.shared}
              onClick={() => void flip()}>
              {load.shared ? 'Make it personal' : 'Make it shared'}
            </Button>
          </div>
        )}
        {error && (
          <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>
        )}
      </CardContent>
    </Card>
  )
}
