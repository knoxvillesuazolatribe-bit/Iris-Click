import { Crosshair, FileText, ScrollText, Settings, Siren, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { AdminLayout } from '@/components/admin-layout'
import { ServerDown } from '@/components/server-down'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { adminService } from '@/services/admin-service'
import type { Dashboard } from '@/validators/admin-validator'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; data: Dashboard }

const MENU = [
  { to: '/admin/users', label: 'Users', text: 'Create users, edit their settings and contacts, deactivate.', icon: Users },
  { to: '/admin/settings', label: 'Settings', text: 'Global accessibility defaults, email test, app name.', icon: Settings },
  { to: '/admin/logs', label: 'Logs', text: 'Everything users and admins did, newest first.', icon: ScrollText },
  { to: '/admin/reports', label: 'Reports', text: 'Calibration, Communication and SOS: preview or PDF.', icon: FileText },
]

/** Screen 18: admin dashboard with real counts. */
export function AdminPage() {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    adminService
      .dashboard()
      .then((data) => current && setLoad({ state: 'ready', data }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load the dashboard.') }))
    return () => {
      current = false
    }
  }, [attempt])

  const cards = load.state === 'ready'
    ? [
        { label: 'Active Users', value: load.data.active_users, week: `${load.data.active_users_week} signed in this week`, icon: Users, to: '/admin/users' },
        { label: 'SOS Events', value: load.data.sos_events, week: `${load.data.sos_events_week} in the last 7 days`, icon: Siren, to: '/admin/reports/sos' },
        { label: 'Calibrations', value: load.data.calibrations, week: `${load.data.calibrations_week} in the last 7 days`, icon: Crosshair, to: '/admin/reports/calibration' },
      ]
    : []

  return (
    <AdminLayout title="Dashboard" description="IrisClick at a glance for PDAO Lapu-Lapu City.">
      {load.state === 'loading' && <p className="text-muted-foreground">Loading…</p>}
      {load.state === 'error' && (
        <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); setAttempt((n) => n + 1) }} />
      )}
      {load.state === 'ready' && (
        <div className="grid gap-4 md:grid-cols-3">
          {cards.map(({ label, value, week, icon: Icon, to }) => (
            <Link key={label} to={to} className="focus-visible:ring-ring rounded-xl outline-none focus-visible:ring-4">
              <Card className="hover:border-primary h-full transition-colors">
                <CardHeader>
                  <CardDescription className="flex items-center gap-2 text-base"><Icon className="size-5" aria-hidden />{label}</CardDescription>
                  <CardTitle className="text-5xl tabular-nums">{value}</CardTitle>
                </CardHeader>
                <CardContent className="text-muted-foreground text-sm">{week}</CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {MENU.map(({ to, label, text, icon: Icon }) => (
          <Link key={to} to={to} className="focus-visible:ring-ring rounded-xl outline-none focus-visible:ring-4">
            <Card className="hover:border-primary h-full transition-colors">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl"><Icon aria-hidden />{label}</CardTitle>
                <CardDescription>{text}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </AdminLayout>
  )
}
