import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { errorMessage } from '@/api/app-client'
import { AdminLayout } from '@/components/admin-layout'
import { ServerDown } from '@/components/server-down'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { adminService } from '@/services/admin-service'
import { useAccountsMode } from '@/lib/use-signin-mode'
import { LOG_TABS, type LogPage, type LogTab } from '@/validators/admin-validator'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; data: LogPage }
const TAB_LABELS: Record<LogTab, string> = {
  all: 'All', calibration: 'Calibration', sos: 'SOS', communication: 'Communication', screenshot: 'Screenshot',
  accounts: 'Accounts',
}
const DATE = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' })

/** Screens 29–30: system logs, newest first. */
export function AdminLogsPage() {
  const accounts = useAccountsMode()
  const [tab, setTab] = useState<LogTab>('all')
  const [page, setPage] = useState(1)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    adminService
      .logs(tab, page, dateFrom, dateTo)
      .then((data) => current && setLoad({ state: 'ready', data }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load the logs.') }))
    return () => {
      current = false
    }
  }, [tab, page, dateFrom, dateTo, attempt])

  const choose = (next: LogTab) => {
    setTab(next)
    setPage(1)
  }

  return (
    <AdminLayout title="Logs" description="Every important action by users and administrators.">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div role="tablist" aria-label="Log type" className="bg-muted flex flex-wrap gap-1 rounded-lg p-1">
          {LOG_TABS.filter((t) => accounts || t !== 'accounts').map((t) => (
            <Button key={t} role="tab" aria-selected={tab === t} size="sm" variant={tab === t ? 'default' : 'ghost'} onClick={() => choose(t)}>
              {TAB_LABELS[t]}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <Label htmlFor="log-from">From</Label>
            <Input id="log-from" type="date" className="h-9" value={dateFrom} max={dateTo || undefined}
              onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="log-to">To</Label>
            <Input id="log-to" type="date" className="h-9" value={dateTo} min={dateFrom || undefined}
              onChange={(e) => { setDateTo(e.target.value); setPage(1) }} />
          </div>
          {(dateFrom || dateTo) && (
            <Button variant="outline" size="sm" onClick={() => { setDateFrom(''); setDateTo(''); setPage(1) }}>Clear dates</Button>
          )}
        </div>
      </div>

      <Card>
        <CardContent className="pt-6">
          {load.state === 'loading' && <p className="text-muted-foreground">Loading…</p>}
          {load.state === 'error' && <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); setAttempt((n) => n + 1) }} />}
          {load.state === 'ready' && load.data.items.length === 0 && <p className="text-muted-foreground">No log entries match.</p>}
          {load.state === 'ready' && load.data.items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-muted-foreground border-b">
                  <tr><th className="py-2 pr-4">ID</th><th className="pr-4">Activity</th><th className="pr-4">User</th><th className="pr-4">Description</th><th>Date</th></tr>
                </thead>
                <tbody>
                  {load.data.items.map((item) => (
                    <tr key={item.log_id} className="border-b align-top last:border-0">
                      <td className="py-2 pr-4 tabular-nums">{item.log_id}</td>
                      <td className="pr-4 font-mono text-xs">{item.activity_type}</td>
                      <td className="pr-4">{item.user_name ?? '—'}</td>
                      <td className="pr-4 break-words">{item.description}</td>
                      <td className="whitespace-nowrap">{DATE.format(new Date(item.log_date))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {load.state === 'ready' && (
        <div className="flex items-center justify-between">
          <p className="text-muted-foreground text-sm">{load.data.total} entries · page {load.data.page} of {load.data.pages}</p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}><ChevronLeft aria-hidden /> Newer</Button>
            <Button variant="outline" size="sm" disabled={page >= load.data.pages} onClick={() => setPage((p) => p + 1)}>Older <ChevronRight aria-hidden /></Button>
          </div>
        </div>
      )}
    </AdminLayout>
  )
}
