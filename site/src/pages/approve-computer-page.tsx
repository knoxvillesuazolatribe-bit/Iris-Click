import { CircleCheck, LoaderCircle, Monitor, Play } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { computersService } from '@/services/computers-service'

type State = { state: 'working' } | { state: 'done'; name: string } | { state: 'error'; message: string }

const NO_CODE = 'This approval link is not complete. Ask your helper or the PDAO office for a new one.'

/**
 * Website: an approval link from the admin page (/approve#<code>), opened on the
 * person's own computer. The code is used once and then removed from the address.
 */
export function ApproveComputerPage() {
  const navigate = useNavigate()
  const [code] = useState(() => window.location.hash.slice(1))
  const started = useRef(false)
  const [result, setResult] = useState<State>(() =>
    code ? { state: 'working' } : { state: 'error', message: NO_CODE })

  useEffect(() => {
    if (!code || started.current) return
    started.current = true
    // Keep the one-time code out of the history and the address bar.
    window.history.replaceState(window.history.state, '', window.location.pathname)
    computersService.claim(code).then(
      (r) => setResult({ state: 'done', name: r.full_name }),
      (e: unknown) => setResult({ state: 'error', message: errorMessage(e, NO_CODE) }),
    )
  }, [code])

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-8 p-6 text-center">
      <Monitor className="text-primary size-16" aria-hidden />
      {result.state === 'working' && (
        <>
          <h1 className="text-4xl font-bold">Approving this computer…</h1>
          <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Approving" />
        </>
      )}
      {result.state === 'done' && (
        <>
          <h1 className="flex items-center gap-3 text-4xl font-bold">
            <CircleCheck className="text-primary size-10" aria-hidden /> This computer is approved
          </h1>
          <p className="max-w-2xl text-2xl">
            {result.name} can now pick their name on this computer. Nothing else is needed.
          </p>
          <GazeButton className="min-h-24 min-w-72 text-2xl" autoFocus onClick={() => void navigate('/user/select', { replace: true })}>
            <Play aria-hidden /> Continue
          </GazeButton>
        </>
      )}
      {result.state === 'error' && (
        <>
          <h1 className="text-4xl font-bold">This computer was not approved</h1>
          <Alert variant="destructive" role="alert" className="max-w-2xl text-left">
            <AlertDescription className="text-lg">{result.message}</AlertDescription>
          </Alert>
          <GazeButton variant="outline" onClick={() => void navigate('/', { replace: true })}>
            Go to the start
          </GazeButton>
        </>
      )}
    </main>
  )
}
