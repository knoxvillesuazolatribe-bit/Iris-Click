import { Accessibility, Mail, MessageSquare, Save, Server, ShieldBan } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { AdminLayout } from '@/components/admin-layout'
import { AdminSharedComputerCard } from '@/components/admin-shared-computer-card'
import { ServerDown } from '@/components/server-down'
import { SettingsEditor } from '@/components/settings-editor'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { pickValues } from '@/lib/settings'
import { useAccountsMode } from '@/lib/use-signin-mode'
import { adminService } from '@/services/admin-service'
import type { AdminUserRow, GlobalDefaults, SystemInfo, TestResult } from '@/validators/admin-validator'

/** Screen 26: settings menu. */
export function AdminSettingsPage() {
  const accounts = useAccountsMode()
  const items = [
    ...(accounts ? [] : [{ to: '/admin/settings/accessibility', title: 'Accessibility', text: 'Global defaults, and any user’s own settings.', icon: Accessibility }]),
    { to: '/admin/settings/system', title: 'System', text: accounts ? 'Email and SMS status and tests, app name.' : 'Email and SMS status and tests, app name, default dwell time.', icon: Server },
    { to: '/admin/settings/word-filter', title: 'Word Filter', text: 'Blocked and allowed words for Voice Communication (extension).', icon: ShieldBan },
  ]
  return (
    <AdminLayout title="Settings">
      <div className="grid gap-4 md:grid-cols-2">
        {items.map(({ to, title, text, icon: Icon }) => (
          <Link key={to} to={to} className="focus-visible:ring-ring rounded-xl outline-none focus-visible:ring-4">
            <Card className="hover:border-primary h-full transition-colors">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl"><Icon aria-hidden />{title}</CardTitle>
                <CardDescription>{text}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </AdminLayout>
  )
}

type DefaultsLoad = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; defaults: GlobalDefaults; users: AdminUserRow[] }

/** Screen 27: global accessibility defaults and a way to any user's settings. */
export function AdminAccessibilityPage() {
  const [load, setLoad] = useState<DefaultsLoad>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    Promise.all([adminService.defaults(), adminService.users()])
      .then(([defaults, users]) => current && setLoad({ state: 'ready', defaults, users: users.filter((u) => u.role === 'assistive_user') }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load the settings.') }))
    return () => {
      current = false
    }
  }, [attempt])

  return (
    <AdminLayout title="Accessibility settings"
      description="Order for each person: their own settings → these global defaults → this computer's standard (.env).">
      {load.state === 'loading' && <p className="text-muted-foreground">Loading…</p>}
      {load.state === 'error' && <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); setAttempt((n) => n + 1) }} />}
      {load.state === 'ready' && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Global defaults</CardTitle>
              <CardDescription>
                {load.defaults.is_default ? 'Currently the computer’s standard settings.' : 'Changed by an administrator.'}{' '}
                Used by everyone who has not saved their own settings, from their next tracking start.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <SettingsEditor
                saved={pickValues(load.defaults)}
                isDefault={load.defaults.is_default}
                resetLabel="Reset to the computer’s standard"
                onSave={async (v) => pickValues(await adminService.saveDefaults(v))}
                onReset={async () => pickValues(await adminService.resetDefaults())}
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>One person’s settings</CardTitle>
              <CardDescription>Open a user to edit their own settings.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {load.users.length === 0 && <p className="text-muted-foreground">No assistive users yet.</p>}
              {load.users.map((u) => (
                <Button key={u.user_id} asChild variant="outline"><Link to={`/admin/users/${u.user_id}`}>{u.full_name}</Link></Button>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </AdminLayout>
  )
}

type SystemLoad = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; system: SystemInfo; defaults: GlobalDefaults }

/** Screen 28: email/SMS status and tests, app name, default dwell time. */
export function AdminSystemPage() {
  const accounts = useAccountsMode()
  const [load, setLoad] = useState<SystemLoad>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [appName, setAppName] = useState('')
  const [nameNotice, setNameNotice] = useState<string | null>(null)
  const [to, setTo] = useState('')
  const [emailResult, setEmailResult] = useState<TestResult | null>(null)
  const [smsResult, setSmsResult] = useState<TestResult | null>(null)
  const [busy, setBusy] = useState<'name' | 'email' | 'sms' | null>(null)

  useEffect(() => {
    let current = true
    Promise.all([adminService.system(), adminService.defaults()])
      .then(([system, defaults]) => {
        if (!current) return
        setLoad({ state: 'ready', system, defaults })
        setAppName(system.app_name)
      })
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load the system settings.') }))
    return () => {
      current = false
    }
  }, [attempt])

  if (load.state !== 'ready') {
    return (
      <AdminLayout title="System">
        {load.state === 'loading' ? <p className="text-muted-foreground">Loading…</p>
          : <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); setAttempt((n) => n + 1) }} />}
      </AdminLayout>
    )
  }
  const { system, defaults } = load

  const saveName = async () => {
    setBusy('name')
    setNameNotice(null)
    try {
      const next = await adminService.saveAppName(appName)
      setLoad({ ...load, system: next })
      setAppName(next.app_name)
      setNameNotice(`Saved. The app is now called “${next.app_name}”.`)
    } catch (err) {
      setNameNotice(errorMessage(err, 'The app name was not saved.'))
    } finally {
      setBusy(null)
    }
  }

  const test = async (kind: 'email' | 'sms') => {
    setBusy(kind)
    try {
      if (kind === 'email') setEmailResult(await adminService.testEmail(to.trim()))
      else setSmsResult(await adminService.testSms())
    } catch (err) {
      const result = { sent: false, detail: errorMessage(err, 'The test could not run.') }
      if (kind === 'email') setEmailResult(result)
      else setSmsResult(result)
    } finally {
      setBusy(null)
    }
  }

  const resultAlert = (result: TestResult | null) => result && (
    <Alert variant={result.sent ? 'default' : 'destructive'} role="status">
      <AlertTitle>{result.sent ? 'Sent' : 'Not sent'}</AlertTitle>
      <AlertDescription>{result.detail}</AlertDescription>
    </Alert>
  )

  return (
    <AdminLayout title="System">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Mail aria-hidden /> Email for SOS</CardTitle>
          <CardDescription>The email account is set in server\.env (passwords never appear here).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="font-medium">Status</dt>
            <dd><Badge variant={system.email.configured ? 'secondary' : 'destructive'}>{system.email.configured ? 'Set up' : 'Not set up'}</Badge></dd>
            <dt className="font-medium">Server</dt>
            <dd>{system.email.host ? `${system.email.host}:${system.email.port} (${system.email.security})` : '—'}</dd>
            <dt className="font-medium">Sends from</dt>
            <dd>{system.email.from_address ?? '—'}</dd>
          </dl>
          <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); void test('email') }}>
            <div className="grid gap-1">
              <Label htmlFor="test-to">Send a test email to</Label>
              <Input id="test-to" type="email" required className="h-10 w-72" value={to} onChange={(e) => setTo(e.target.value)} placeholder="you@example.com" />
            </div>
            <Button type="submit" disabled={busy !== null || !to.includes('@')}>{busy === 'email' ? 'Sending…' : 'Send test email'}</Button>
          </form>
          {resultAlert(emailResult)}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><MessageSquare aria-hidden /> SMS</CardTitle>
          <CardDescription>{load.system.sms_configured
            ? 'Semaphore is connected. Test texts go only to the number in SMS_ONLY_TO.'
            : 'Needs a paid SMS gateway, which is not connected yet.'}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button variant="outline" disabled={busy !== null} onClick={() => void test('sms')}>Test SMS</Button>
          {resultAlert(smsResult)}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>App name</CardTitle>
          <CardDescription>Shown on the sign-in screen, the browser tab and SOS emails. Leave empty for “{system.app_name_default}”.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <Input aria-label="App name" className="h-10 w-72" maxLength={60} value={appName} onChange={(e) => setAppName(e.target.value)} />
            <Button disabled={busy !== null || appName.trim() === system.app_name} onClick={() => void saveName()}>
              <Save aria-hidden /> Save name
            </Button>
          </div>
          {nameNotice && <p className="text-sm">{nameNotice}</p>}
        </CardContent>
      </Card>

      {!accounts && <Card>
        <CardHeader>
          <CardTitle>Default dwell time</CardTitle>
          <CardDescription>Part of the global accessibility defaults.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-4">
          <p className="text-2xl font-bold">{(defaults.dwell_ms / 1000).toFixed(1)} s</p>
          <p className="text-muted-foreground">Dwell click is {defaults.dwell_enabled ? 'on' : 'off'} by default.</p>
          <Button asChild variant="outline"><Link to="/admin/settings/accessibility">Change defaults</Link></Button>
        </CardContent>
      </Card>}
      {accounts && <AdminSharedComputerCard />}
    </AdminLayout>
  )
}
