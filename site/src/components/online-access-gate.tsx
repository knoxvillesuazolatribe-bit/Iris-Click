import { isAxiosError } from 'axios'
import { Globe, KeyRound, LoaderCircle } from 'lucide-react'
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react'
import { appClient, errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { ServerDown } from '@/components/server-down'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ONLINE_COPY } from '@/lib/online-copy'
import { onlineAccessService } from '@/services/online-access-service'

type GateState = 'checking' | 'locked' | 'not-set-up' | 'open' | 'down'

/**
 * Online copy only: asks for the site access code before anything else loads.
 * On the PC build it renders its children and nothing more.
 */
export function OnlineAccessGate({ children }: { children: ReactNode }) {
  if (!ONLINE_COPY) return children
  return <Gate>{children}</Gate>
}

function Gate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>('checking')
  const [downMessage, setDownMessage] = useState('')

  const check = useCallback(() => {
    onlineAccessService.status().then(
      (s) => setState(!s.ready ? 'not-set-up' : s.access ? 'open' : 'locked'),
      (error: unknown) => {
        setDownMessage(errorMessage(error))
        setState('down')
      },
    )
  }, [])

  useEffect(check, [check])

  // A code changed in Vercel signs this device out: show the code screen again.
  useEffect(() => {
    const id = appClient.interceptors.response.use(undefined, (error: unknown) => {
      const code = isAxiosError(error) ? error.response?.data?.code : undefined
      if (code === 'access_required') setState('locked')
      if (code === 'not_set_up') setState('not-set-up')
      return Promise.reject(error)
    })
    return () => appClient.interceptors.response.eject(id)
  }, [])

  if (state === 'open') {
    return (
      <>
        <OnlineBanner />
        {children}
      </>
    )
  }
  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-6 p-6">
      {state === 'checking' && (
        <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading" />
      )}
      {state === 'down' && (
        <ServerDown message={downMessage} onRetry={() => { setState('checking'); check() }} />
      )}
      {state === 'not-set-up' && (
        <Alert role="alert" className="max-w-xl">
          <AlertDescription className="text-lg">
            The online copy of IrisClick is not set up yet. Ask the PDAO office.
          </AlertDescription>
        </Alert>
      )}
      {state === 'locked' && <CodeForm onOpen={() => setState('open')} />}
    </main>
  )
}

function CodeForm({ onOpen }: { onOpen: () => void }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!code.trim()) {
      setError('Type the access code first.')
      return
    }
    setBusy(true)
    setError(null)
    onlineAccessService.enter(code).then(onOpen, (e: unknown) => {
      setError(errorMessage(e, 'That access code is not right. Please try again.'))
      setCode('')
      setBusy(false)
    })
  }

  return (
    <Card className="w-full max-w-lg">
      <CardHeader className="space-y-2">
        <Globe className="text-primary size-12" aria-hidden />
        <CardTitle className="text-3xl font-bold">IrisClick online</CardTitle>
        <CardDescription className="text-lg">
          This is IrisClick online. Enter the access code from the PDAO office.
          This device remembers it.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} noValidate className="space-y-5">
          {error && (
            <Alert variant="destructive" role="alert">
              <AlertDescription className="text-base">{error}</AlertDescription>
            </Alert>
          )}
          <Field>
            <FieldLabel htmlFor="online-access-code" className="text-base">Access code</FieldLabel>
            <Input id="online-access-code" type="password" autoComplete="off" autoFocus
              className="h-14 text-xl" value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
          <GazeButton type="submit" className="w-full" disabled={busy}>
            <KeyRound aria-hidden />
            {busy ? 'Checking…' : 'Continue'}
          </GazeButton>
        </form>
      </CardContent>
    </Card>
  )
}

function OnlineBanner() {
  return (
    <div role="note" className="bg-muted text-muted-foreground flex items-center justify-center gap-2 px-4 py-1.5 text-center text-sm">
      <Globe className="size-4 shrink-0" aria-hidden />
      Online IrisClick: eye tracking here works inside this website. Use the IrisClick PC to control other apps.
    </div>
  )
}
