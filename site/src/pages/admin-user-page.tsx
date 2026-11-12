import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, Save, UserCheck, UserX } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { AdminLayout } from '@/components/admin-layout'
import { AdminApprovedComputersCard } from '@/components/admin-approved-computers-card'
import { AdminUserAppsCard } from '@/components/admin-user-apps-card'
import { AdminUserLanguageCard } from '@/components/admin-user-language-card'
import { AdminUserVoiceCard } from '@/components/admin-user-voice-card'
import { ContactsManager } from '@/components/contacts-manager'
import { SilentBoundary } from '@/components/silent-boundary'
import { ServerDown } from '@/components/server-down'
import { SettingsEditor } from '@/components/settings-editor'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ONLINE_COPY } from '@/lib/online-copy'
import { useAccountsMode } from '@/lib/use-signin-mode'
import { pickValues } from '@/lib/settings'
import { adminService } from '@/services/admin-service'
import { profileFormSchema, type AdminUserDetail, type ProfileForm } from '@/validators/admin-validator'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; detail: AdminUserDetail }
const DATE = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const FIELDS = [
  { name: 'full_name', label: 'Full name' },
  { name: 'barangay', label: 'Barangay' },
  { name: 'address', label: 'Address' },
] as const

/** Screens 22–25: one assistive user (profile, calibration, settings, contacts, status). */
export function AdminUserPage() {
  const accounts = useAccountsMode()
  const userId = Number(useParams().id)
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const reload = () => setAttempt((n) => n + 1)

  useEffect(() => {
    let current = true
    adminService
      .user(userId)
      .then((detail) => current && setLoad({ state: 'ready', detail }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load this user.') }))
    return () => {
      current = false
    }
  }, [userId, attempt])

  const back = (
    <Button asChild variant="outline"><Link to="/admin/users"><ArrowLeft aria-hidden /> All users</Link></Button>
  )

  if (load.state !== 'ready') {
    return (
      <AdminLayout title="User" actions={back}>
        {load.state === 'loading' ? <p className="text-muted-foreground">Loading…</p>
          : <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); reload() }} />}
      </AdminLayout>
    )
  }

  const { user, settings, contacts, sos_location: location } = load.detail
  return (
    <AdminLayout title={user.full_name} actions={back}
      description={user.status === 'active'
        ? (accounts ? 'Active: can sign in on their computers.' : 'Active: can sign in from the name tiles.')
        : 'Inactive: hidden from the name tiles and cannot sign in.'}>
      <div className="grid gap-6 lg:grid-cols-2">
        <ProfileCard key={`${user.user_id}-${user.full_name}-${user.address}-${user.barangay}`} detail={load.detail} onSaved={reload} />
        <Card>
          <CardHeader>
            <CardTitle>Calibration</CardTitle>
            <CardDescription>From the person's successful calibrations.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2">
              <dt className="font-medium">Accuracy</dt>
              <dd>{user.latest_accuracy !== null ? `${user.latest_accuracy.toFixed(2)}%` : 'Not calibrated yet'}</dd>
              <dt className="font-medium">Last calibrated</dt>
              <dd>{user.last_calibrated_at ? DATE.format(new Date(user.last_calibrated_at)) : '—'}</dd>
              <dt className="font-medium">Calibrations</dt>
              <dd>{user.calibration_count}</dd>
              <dt className="font-medium">Dwell duration</dt>
              <dd>{(settings.dwell_ms / 1000).toFixed(1)} s ({settings.dwell_enabled ? 'dwell click on' : 'dwell click off'})</dd>
              <dt className="font-medium">SOS location</dt>
              <dd>{location ?? <span className="text-destructive">No address on file</span>}</dd>
            </dl>
          </CardContent>
        </Card>
      </div>

      <StatusCard key={user.status} detail={load.detail} onChanged={reload} />

      {!accounts && <Card>
        <CardHeader>
          <CardTitle>Accessibility settings</CardTitle>
          <CardDescription>
            {settings.is_default ? 'Using the standard settings.' : 'Using their own settings.'} Changes take effect the next time their eye tracking starts.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SettingsEditor
            key={userId}
            saved={pickValues(settings)}
            isDefault={settings.is_default}
            resetLabel="Reset to Default"
            onSave={async (v) => pickValues(await adminService.saveUserSettings(userId, v))}
            onReset={async () => pickValues(await adminService.resetUserSettings(userId))}
            onSaved={reload}
          />
        </CardContent>
      </Card>}

      <Card>
        <CardHeader>
          <CardTitle>Emergency contacts</CardTitle>
          <CardDescription>Alerted by email when {user.full_name} presses SOS.</CardDescription>
        </CardHeader>
        <CardContent>
          <ContactsManager
            contacts={contacts}
            onAdd={(form) => adminService.addContact(userId, form)}
            onUpdate={(id, form) => adminService.updateContact(userId, id, form)}
            onDelete={(id) => adminService.deleteContact(userId, id)}
            onChanged={reload}
          />
        </CardContent>
      </Card>
      <SilentBoundary><AdminUserAppsCard userId={userId} name={user.full_name} /></SilentBoundary>
      {!accounts && <SilentBoundary><AdminUserLanguageCard userId={userId} name={user.full_name} /></SilentBoundary>}
      {!accounts && <SilentBoundary><AdminUserVoiceCard userId={userId} name={user.full_name} /></SilentBoundary>}
      {ONLINE_COPY && !accounts && <SilentBoundary><AdminApprovedComputersCard userId={userId} name={user.full_name} /></SilentBoundary>}
    </AdminLayout>
  )
}

function ProfileCard({ detail, onSaved }: { detail: AdminUserDetail; onSaved: () => void }) {
  const { user } = detail
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const form = useForm<ProfileForm>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: { full_name: user.full_name, address: user.address ?? '', barangay: user.barangay ?? '' },
  })
  const onSubmit = form.handleSubmit(async (values) => {
    setNotice(null)
    try {
      await adminService.updateProfile(user.user_id, values)
      onSaved()
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'The profile was not saved.') })
    }
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>The address and barangay are the location shared by SOS.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="grid gap-4">
          {FIELDS.map(({ name, label }) => (
            <Controller key={name} control={form.control} name={name}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor={`profile-${name}`}>{label}</FieldLabel>
                  <Input id={`profile-${name}`} className="h-11" aria-invalid={fieldState.invalid} {...field} />
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )} />
          ))}
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={form.formState.isSubmitting || !form.formState.isDirty}>
              <Save aria-hidden /> Save profile
            </Button>
            {notice && (
              <Alert variant="destructive" className="w-auto flex-1"><AlertDescription>{notice.text}</AlertDescription></Alert>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function StatusCard({ detail, onChanged }: { detail: AdminUserDetail; onChanged: () => void }) {
  const { user } = detail
  const active = user.status === 'active'
  const [confirm, setConfirm] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const change = async () => {
    setError(null)
    try {
      await adminService.setStatus(user.user_id, active ? 'inactive' : 'active')
      onChanged()
    } catch (err) {
      setError(errorMessage(err, 'The status was not changed.'))
      setConfirm(false)
    }
  }
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-6">
        <div className="space-y-1">
          <p className="flex items-center gap-2 font-semibold">
            Status <Badge variant={active ? 'secondary' : 'destructive'}>{active ? 'Active' : 'Inactive'}</Badge>
          </p>
          <p className="text-muted-foreground text-sm">
            {active
              ? 'Deactivating hides their name tile and ends their sign-in now. Their history is kept, and eye tracking keeps running until it is closed.'
              : 'Reactivating shows their name tile again.'}
          </p>
          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>
        {confirm ? (
          <div className="flex gap-2">
            <Button variant={active ? 'destructive' : 'default'} onClick={() => void change()}>
              Yes, {active ? 'deactivate' : 'reactivate'}
            </Button>
            <Button variant="outline" onClick={() => setConfirm(false)}>Cancel</Button>
          </div>
        ) : (
          <Button variant={active ? 'outline' : 'default'} onClick={() => setConfirm(true)}>
            {active ? <UserX aria-hidden /> : <UserCheck aria-hidden />}
            {active ? 'Deactivate' : 'Reactivate'}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
