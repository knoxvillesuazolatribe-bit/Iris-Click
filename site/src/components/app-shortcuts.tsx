import { AppWindow, Calculator, CalendarDays, FileSpreadsheet, FileText, Globe, LoaderCircle, Presentation } from 'lucide-react'
import { useEffect, useState } from 'react'
import { errorMessage } from '@/api/app-client'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { appsService, type AppShortcut } from '@/services/home-service'

const ICONS: Record<string, typeof Globe> = {
  browser: Globe, calculator: Calculator, calendar: CalendarDays,
  word: FileText, excel: FileSpreadsheet, powerpoint: Presentation,
}
type Notice = { kind: 'ok' | 'error'; text: string } | null

/** Home Suite app shortcuts: only apps this computer has; one wink opens one. */
export function AppShortcuts() {
  const [apps, setApps] = useState<AppShortcut[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice>(null)

  useEffect(() => {
    let current = true
    appsService
      .list()
      .then((list) => current && setApps(list))
      .catch(() => current && setApps([]))
    return () => {
      current = false
    }
  }, [])

  const open = async (app: AppShortcut) => {
    setBusy(app.app_id)
    setNotice(null)
    try {
      const result = await appsService.launch(app.app_id)
      setNotice({ kind: 'ok', text: `${result.label} is opening. Use Home on the control bar to come back.` })
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, `${app.label} could not be opened.`) })
    } finally {
      setBusy(null)
    }
  }

  if (!apps || apps.length === 0) return null
  return (
    <section aria-labelledby="apps" className="flex flex-col gap-4">
      <h2 id="apps" className="flex items-center gap-3 text-2xl font-bold">
        <AppWindow className="size-8" aria-hidden />
        Apps
      </h2>
      {notice && (
        <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status">
          <AlertDescription className="text-lg">{notice.text}</AlertDescription>
        </Alert>
      )}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(13rem,1fr))] gap-6">
        {apps.map((app) => {
          const Icon = ICONS[app.app_id] ?? AppWindow
          return (
            <button
              key={app.app_id}
              type="button"
              disabled={busy !== null}
              onClick={() => void open(app)}
              className={cn(
                'bg-card border-primary flex min-h-28 flex-col items-center justify-center gap-2 rounded-2xl border-2 p-4 text-center',
                'outline-none disabled:opacity-60',
                'hover:border-primary hover:ring-ring/70 focus-visible:ring-ring hover:ring-4 focus-visible:ring-4',
              )}
            >
              {busy === app.app_id ? <LoaderCircle className="text-primary size-10 animate-spin" aria-hidden /> : <Icon className="text-primary size-10" aria-hidden />}
              <span className="text-xl font-semibold">{app.label}</span>
              {app.note && <span className="text-muted-foreground text-sm">{app.note}</span>}
            </button>
          )
        })}
      </div>
    </section>
  )
}
