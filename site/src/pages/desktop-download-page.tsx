import { ArrowLeft, Download, LoaderCircle, Monitor, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { browserName, FALLBACK_DOWNLOAD, latestDesktop, type Latest } from '@/lib/desktop-status'

const ALLOW_STEPS: Record<ReturnType<typeof browserName>, string[]> = {
  edge: ['When Edge asks to let this site "access other apps and services on this device", choose Allow.',
    'If you chose Block: click the lock icon left of the address, set "Local network access" to Allow, then Try again.'],
  chrome: ['When Chrome asks to let this site "access other apps and services on this device", choose Allow.',
    'If you chose Block: click the icon left of the address, set "Local network access" to Allow, then Try again.'],
  brave: ['Brave blocks this without asking. Open brave://settings/content/localhostAccess (copy it into the address bar).',
    'Under "Allowed to access localhost", add this website’s address, then come back and choose Try again.',
    'Easier: open IrisClick from the IrisClick shortcut; it uses Microsoft Edge.'],
  other: ['Allow this website to reach apps on this computer if your browser asks, then choose Try again.',
    'For the best experience, open IrisClick from the IrisClick shortcut (Microsoft Edge).'],
}

interface Props {
  /** Called by Try again; resolves true when the desktop app now answers. */
  onRetry?: () => Promise<boolean>
}

/**
 * Hosted website: shown when IrisClick Desktop does not answer (not installed, not
 * running, or blocked by the browser). Admin pages never need it.
 */
export function DesktopDownloadPage({ onRetry }: Props) {
  const navigate = useNavigate()
  const [latest, setLatest] = useState<Latest | null>(null)
  const [checking, setChecking] = useState(false)
  const [stillMissing, setStillMissing] = useState(false)
  const browser = browserName()

  useEffect(() => {
    void latestDesktop().then(setLatest)
  }, [])

  const retry = async () => {
    if (!onRetry) return window.location.reload()
    setChecking(true)
    setStillMissing(!(await onRetry()))
    setChecking(false)
  }

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-4xl flex-col gap-8 p-6">
      <header className="top-band flex flex-wrap items-center justify-between gap-6">
        <h1 className="flex items-center gap-3 text-4xl font-bold"><Monitor className="text-primary size-10" aria-hidden /> IrisClick Desktop</h1>
        <GazeButton variant="outline" onClick={() => void navigate('/home')}>
          <ArrowLeft aria-hidden /> Home
        </GazeButton>
      </header>

      <p className="text-xl">
        Eye tracking runs on your own computer with the free <strong>IrisClick Desktop</strong> app.
        Install it once; after that, this page opens by itself.
      </p>

      {stillMissing && (
        <Alert variant="destructive" role="alert">
          <AlertDescription className="text-base">
            IrisClick Desktop still does not answer. Check that it is running (the eye icon near the clock) and
            that the browser allows this website to reach it (steps below).
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap gap-6">
        <GazeButton asChild>
          <a href={latest?.download_url ?? FALLBACK_DOWNLOAD} rel="noopener">
            <Download aria-hidden /> Download IrisClick Desktop{latest ? ` ${latest.version}` : ''}
          </a>
        </GazeButton>
        <GazeButton variant="outline" disabled={checking} onClick={() => void retry()}>
          {checking ? <LoaderCircle className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />} Try again
        </GazeButton>
      </div>

      <section className="space-y-3">
        <h2 className="text-2xl font-semibold">Install (Windows, about 2 minutes)</h2>
        <ol className="list-decimal space-y-2 pl-6 text-lg">
          <li>Open the downloaded <strong>IrisClick-Desktop-Setup.exe</strong>. No administrator password is needed.</li>
          <li>Keep <strong>Start IrisClick when Windows starts</strong> ticked for hands-free use.</li>
          <li>Finish. IrisClick opens in Microsoft Edge and the eye icon appears near the clock.</li>
          <li>Come back here and choose <strong>Try again</strong>.</li>
        </ol>
      </section>

      <section className="space-y-3">
        <h2 className="text-2xl font-semibold">Already installed? Let this website reach it</h2>
        <ul className="list-disc space-y-2 pl-6 text-lg">
          {ALLOW_STEPS[browser].map((step) => <li key={step}>{step}</li>)}
        </ul>
      </section>
    </main>
  )
}
