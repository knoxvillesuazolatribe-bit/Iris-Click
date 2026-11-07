import { LoaderCircle } from 'lucide-react'
import { type ReactNode, useCallback, useEffect, useState } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { linkDesktop } from '@/lib/desktop-link'
import { checkDesktop, isOlder, latestDesktop, type Latest } from '@/lib/desktop-status'
import { DesktopDownloadPage } from '@/pages/desktop-download-page'

type Gate = { state: 'checking' } | { state: 'missing' } | { state: 'ready'; version: string; latest: Latest | null }

/** Finds IrisClick Desktop; when it answers, tells it who is signed in. */
async function probe(): Promise<Gate> {
  const desktop = await checkDesktop()
  if (!desktop.running) return { state: 'missing' }
  await linkDesktop()
  return { state: 'ready', version: desktop.version, latest: await latestDesktop() }
}

/**
 * Hosted website: shows ``children`` (the existing calibration page, the Gaze Tracking
 * page) only when IrisClick Desktop answers on this PC, after telling it who is signed
 * in. Otherwise shows the download page with Try again.
 */
export function DesktopGate({ children }: { children: ReactNode }) {
  const [gate, setGate] = useState<Gate>({ state: 'checking' })

  const check = useCallback(async () => {
    const next = await probe()
    setGate(next)
    return next.state === 'ready'
  }, [])

  useEffect(() => {
    let current = true
    void probe().then((next) => current && setGate(next))
    return () => {
      current = false
    }
  }, [])

  if (gate.state === 'checking') {
    return (
      <main className="bg-background flex min-h-svh items-center justify-center">
        <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Looking for IrisClick Desktop" />
      </main>
    )
  }
  if (gate.state === 'missing') return <DesktopDownloadPage onRetry={check} />
  const update = gate.latest && isOlder(gate.version, gate.latest.version) ? gate.latest : null
  return (
    <>
      {update && (
        <Alert role="status" className="mx-auto mt-2 max-w-4xl">
          <AlertDescription className="text-base">
            IrisClick Desktop {update.version} is available (this PC has {gate.version}).{' '}
            <a className="underline" href={update.download_url} rel="noopener">Download the update</a>.
          </AlertDescription>
        </Alert>
      )}
      {children}
    </>
  )
}
